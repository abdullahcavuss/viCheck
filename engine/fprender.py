"""
Front panel drawing.

The front panel heap (FPHb) does not contain pixels, but it has every control with its parts: label, caption,
frame, numeric display, increment arrows, boolean button, text, scroll bars, tab pages, cluster contents ...
each with bounds and colors. From these the panel is drawn schematically as SVG: the layout, sizes, colors
and texts are the real ones; LabVIEW's bitmaps (glyphs, button images, graphs) are not available, so those
areas are drawn as plain shapes.

Coordinates (found by comparing with LabVIEW):
- top-level objects: panel coordinates; the bounds are '(top, left, bottom, right)'
- the parts of a control, and nested controls in its partsList: relative to the control's top-left
- tab pages and the controls on them: relative to the tab control's top-left
- cluster contents (the cluster's own pane): scrolled pane coordinates; the contents are placed at the top-left
  of the pane (LabVIEW lays them out there; the stored scroll origin is not reliable)
- label/caption with objFlags bit 0 set: hidden

Model (stored in the parsed VI model as "fp_draw", cached):
  {"bg": "#rrggbb", "ctls": [ctl], "deco": [item]}
  ctl  = {"uid", "name", "box": [l, t, r, b], "items": [item], "kids": [ctl], "pages": [{"name", "items", "kids"}]}
  item = ["r", l, t, r, b, fill, stroke]  |  ["t", l, t, r, b, text, color, align]
"""
import html
import re
import xml.etree.ElementTree as ET

PANEL_BG = "#E6E6E6"
LABELS = {"label", "multiLabel", "numLabel", "selLabel"}
COSM = {"cosm", "multiCosm", "bigMultiCosm"}
SKIP = {"annex", "TabInfoItem", "SubCosm", "scale"}
FONT = 'Segoe UI, Arial, sans-serif'

# status colors, the same as on the block diagram
COLORS = {"added": "#1a7f37", "removed": "#cf222e", "modified": "#d97706", "moved": "#2f6feb", "typedef": "#8c959f",
          "minor": "#a8b1bb"}


def _rect(text):
    try:
        p = [int(x) for x in (text or "").strip().strip("()").split(",")]
        return tuple(p) if len(p) == 4 else None
    except ValueError:
        return None


def _color(v, role):
    """'00RRGGBB' -> '#rrggbb'; '01xxxxxx' (system color) -> a typical value or None (transparent)."""
    if not v or len(v) != 8:
        return None
    if v.startswith("00"):
        return "#" + v[2:].lower()
    if v.startswith("01"):
        idx = int(v[2:], 16)
        if idx == 0:
            return None                    # transparent
        if idx == 0x0C:
            return "#000000"               # text
        if idx == 0x0A:
            return "#ffffff"               # control / window background
        if idx == 0x16:
            return PANEL_BG if role == "bg" else "#a0a0a0"
        return "#d9d9d9" if role == "bg" else "#606060"
    return None


def _fix_enc(t):
    """pylabview decodes LabVIEW text as Mac Roman; VIs saved on Windows use the Windows code page
    (Turkish Windows: cp1254, which also covers the Western cp1252 letters and ™). Only for the drawing."""
    if not t or all(ord(ch) < 128 for ch in t):
        return t
    try:
        return t.encode("mac_roman").decode("cp1254")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return t


def _text(el, fix=True):
    tx = el.find("textRec/text")
    if tx is None or not tx.text:
        return None
    t = tx.text.strip()
    if t.startswith('"') and t.endswith('"'):
        t = t[1:-1]
    t = t.replace("&#x00;", "").replace("\x00", "")
    t = re.sub(r"\\r\\n|\\n|\\r", "\n", t)
    return (_fix_enc(t) if fix else t) or None


def _hex_text(v):
    try:
        return bytes.fromhex(v or "").decode("utf-8", "replace").replace("\x00", "")
    except ValueError:
        return v or ""


def _flags(el):
    try:
        return int(el.findtext("objFlags") or 0)
    except ValueError:
        return 0


class _Builder:
    def __init__(self):
        self.ctls = []

    # ------------------------------------------------------------ one control (ddo) and its parts
    def ddo(self, ddo, ox, oy, items, kids):
        """Draws a ddo (or a ddo-like part) whose bounds are relative to (ox, oy). Returns its absolute top-left."""
        b = _rect(ddo.findtext("bounds"))
        if b is None:
            return ox, oy
        ax, ay = ox + b[1], oy + b[0]
        pl = ddo.find("partsList")
        parts = list(pl) if pl is not None else []
        # LabVIEW lists the parts from top to bottom: draw them in reverse
        for p in reversed(parts):
            cls = p.get("class")
            if cls in SKIP:
                continue
            if cls == "fPDCO":                                  # a control inside a group (grouper)
                c = self.control(p, ax, ay)
                if c:
                    kids.append(c)
                continue
            if p.find("partsList") is not None or p.find("paneHierarchy") is not None:
                self.ddo(p, ax, ay, items, kids)          # a nested control (cluster element, typedef body ...)
                continue
            pb = _rect(p.findtext("bounds"))
            if pb is None or (pb[2] - pb[0] <= 0 and pb[3] - pb[1] <= 0):
                continue
            l, t, r, bt = ax + pb[1], ay + pb[0], ax + pb[3], ay + pb[2]
            fill = _color(p.findtext("bgColor"), "bg")
            stroke = _color(p.findtext("fgColor"), "fg")
            if cls in LABELS:
                if cls == "label" and _flags(p) & 1:
                    continue                                   # hidden label / caption
                txt = _text(p)
                if fill:
                    items.append(["r", l, t, r, bt, fill, None])
                if txt:
                    items.append(["t", l, t, r, bt, txt, stroke or "#000000", "c" if cls == "multiLabel" else "l"])
            elif cls in COSM or cls in ("grid", "listbox", "tabArray"):
                if fill or stroke:
                    items.append(["r", l, t, r, bt, fill, stroke if stroke != fill else None])
        # tab control: the pages
        pages = []
        pli = ddo.find("pageList")
        if pli is not None:
            caps = [_hex_text(x.findtext("caption")) for x in ddo.findall("tabControlPageInfoArray/*")]
            for i, pg in enumerate(pli):
                pitems, pkids = [], []
                self.zplane(pg.find("zPlaneList"), ax, ay, pitems, pkids)
                pages.append({"name": caps[i] if i < len(caps) else "#%d" % (i + 1), "items": pitems, "kids": pkids})
        # cluster: its own pane
        pane = ddo.find("paneHierarchy")
        if pane is not None:
            pb = _rect(pane.findtext("bounds"))
            if pb is not None:
                z = pane.find("zPlaneList")
                els = [e for e in (z if z is not None else []) if e.get("class") not in COSM and e.get("class") != "label"]
                u = None
                for e in els:
                    eb = _rect((e.find("ddo") if e.get("class") == "fPDCO" else e).findtext("bounds")) if (
                        e.get("class") != "fPDCO" or e.find("ddo") is not None) else None
                    if eb:
                        top = eb[0] - 17          # leave room for the label above the element
                        u = (top, eb[1]) if u is None else (min(u[0], top), min(u[1], eb[1]))
                if u is not None:
                    sub_items = []
                    self.zplane(z, ax + pb[1] + 3 - u[1], ay + pb[0] + 3 - u[0], sub_items, kids, skip_cosm=True)
                    items.append(["c", ax + pb[1], ay + pb[0], ax + pb[3], ay + pb[2], sub_items])
        return ax, ay, pages, (ax, ay, ax + b[3] - b[1], ay + b[2] - b[0])

    def zplane(self, z, ox, oy, items, kids, skip_cosm=False):
        for e in (z if z is not None else []):
            cls = e.get("class")
            if cls == "fPDCO":
                c = self.control(e, ox, oy)
                if c:
                    kids.append(c)
            elif e.find("partsList") is not None:
                self.ddo(e, ox, oy, items, kids)
            elif not skip_cosm:
                b = _rect(e.findtext("bounds"))
                if b is None:
                    continue
                l, t, r, bt = ox + b[1], oy + b[0], ox + b[3], oy + b[2]
                if cls == "label":
                    txt = _text(e)
                    if txt:
                        items.append(["t", l, t, r, bt, txt, _color(e.findtext("fgColor"), "fg") or "#000000", "l"])
                elif cls in COSM:
                    fill = _color(e.findtext("bgColor"), "bg")
                    stroke = _color(e.findtext("fgColor"), "fg")
                    if fill or stroke:
                        items.append(["r", l, t, r, bt, fill, stroke if stroke != fill else None])

    def control(self, fpdco, ox, oy):
        ddo = fpdco.find("ddo")
        if ddo is None:
            return None
        name = None
        pl = ddo.find("partsList")
        for p in (pl if pl is not None else []):
            if p.get("class") == "label":
                name = _text(p, fix=False)      # the same as the diff's control names (vi_parser)
                if name:
                    break
        items, kids = [], []
        res = self.ddo(ddo, ox, oy, items, kids)
        pages = res[2] if len(res) > 2 else []
        c = {"uid": fpdco.get("uid"), "name": name or "(unnamed)", "items": items, "kids": kids, "pages": pages}
        if pages:
            c["clip"] = list(res[3])     # tab pages are clipped to the tab control
        c["box"] = _box(c)
        return c


def _box(c, page=0):
    xs, ys = [], []

    def add(items, kids, clip=None):
        for it in items:
            xs.extend((it[1], it[3]))
            ys.extend((it[2], it[4]))
        for k in kids:
            b = k["box"]
            if b:
                if clip:
                    b = [max(b[0], clip[0]), max(b[1], clip[1]), min(b[2], clip[2]), min(b[3], clip[3])]
                xs.extend((b[0], b[2]))
                ys.extend((b[1], b[3]))
    if c.get("pages"):
        add(c["items"], [])
        xs.extend((c["clip"][0], c["clip"][2]))
        ys.extend((c["clip"][1], c["clip"][3]))
    else:
        add(c["items"], c["kids"])
    return [min(xs), min(ys), max(xs), max(ys)] if xs else None


def parse_panel(fp_path):
    """FPHb XML -> drawing model (see the module docstring)."""
    root = ET.parse(fp_path).getroot()
    pane = root.find("root/paneHierarchy")
    if pane is None:
        return None
    bg = PANEL_BG
    for p in (pane.find("partsList") or []):
        if p.findtext("partID") == "28":
            bg = _color(p.findtext("bgColor"), "bg") or PANEL_BG
    b = _Builder()
    deco, ctls = [], []
    b.zplane(pane.find("zPlaneList"), 0, 0, deco, ctls)
    return {"bg": bg, "ctls": ctls, "deco": deco}


# ---------------------------------------------------------------- changes
def walk(ctls):
    """All controls, nested ones (in clusters and on tab pages) included."""
    for c in ctls:
        yield c
        yield from walk(c["kids"])
        for pg in c.get("pages") or []:
            yield from walk(pg["kids"])


def marks(old_model, new_model, fp_diff, accept=()):
    """Numbered front panel changes: the diff's own list (added/removed/modified) and controls that only moved
    or were resized. Returns [{"num", "kind", "name", "detail"}].
    accept: rules not counted as changes (vi_diff.ACCEPT_RULES); such marks get the faint kind "minor"."""
    out = []
    seen = set()
    accept = set(accept or ())
    for x in fp_diff or []:
        kind = "typedef" if x["kind"] == "modified" and x.get("detail") == "typedef contents updated" else x["kind"]
        if kind != "typedef":
            rule = "fp_look" if x.get("detail") == "appearance/property changed" else "fp"
            if rule in accept:
                kind = "minor"
        out.append({"num": len(out) + 1, "kind": kind, "name": x["name"],
                    "detail": "the typedef it uses changed" if kind == "typedef" else x.get("detail", "")})
        seen.add(x["name"])
    ob = {c["name"]: c.get("bounds") for c in old_model.get("fp") or []}
    for c in new_model.get("fp") or []:
        o = ob.get(c["name"])
        if c["name"] in seen or o is None or c.get("bounds") is None or list(o) == list(c["bounds"]):
            continue
        ot, ol, obt, orr = o
        nt, nl, nbt, nr = c["bounds"]
        what = []
        if (ot, ol) != (nt, nl):
            what.append("moved")
        if (obt - ot, orr - ol) != (nbt - nt, nr - nl):
            what.append("resized")
        out.append({"num": len(out) + 1, "kind": "minor" if "fp_layout" in accept else "moved", "name": c["name"],
                    "detail": " / ".join(what)})
        seen.add(c["name"])
    return out


# ---------------------------------------------------------------- SVG
def _n(v):
    return ("%.1f" % v).rstrip("0").rstrip(".")


class _Ids:
    n = 0


def _clip_open(l, t, r, b, out):
    _Ids.n += 1
    cid = "fpc%d" % _Ids.n
    out.append('<clipPath id="%s"><rect x="%s" y="%s" width="%s" height="%s"/></clipPath><g clip-path="url(#%s)">' % (
        cid, _n(l), _n(t), _n(max(0, r - l)), _n(max(0, b - t)), cid))


def _items_svg(items, out):
    for it in items:
        if it[0] == "c":
            _clip_open(it[1], it[2], it[3], it[4], out)
            _items_svg(it[5], out)
            out.append("</g>")
        elif it[0] == "r":
            _, l, t, r, b, fill, stroke = it
            if r - l <= 0 or b - t <= 0:
                continue
            out.append('<rect x="%s" y="%s" width="%s" height="%s" fill="%s"%s/>' % (
                _n(l), _n(t), _n(r - l), _n(b - t), fill or "none",
                (' stroke="%s" stroke-width="1"' % stroke) if stroke else ""))
        else:
            _, l, t, r, b, txt, col, align = it
            lines = txt.split("\n")
            fs = 12 if (b - t) >= 15 * len(lines) else max(8, (b - t) / max(1, len(lines)) - 2)
            x = (l + r) / 2 if align == "c" else l + 1
            anchor = ' text-anchor="middle"' if align == "c" else ""
            for k, line in enumerate(lines):
                y = t + fs + 1 + k * (fs + 3)
                out.append('<text x="%s" y="%s" font-size="%s" fill="%s"%s>%s</text>' % (
                    _n(x), _n(y), _n(fs), col, anchor, html.escape(line, quote=False)))


def _ctl_svg(c, out, ctx):
    """One control with its kids and tab pages, and its change marker (so it hides with its tab page)."""
    out.append('<g class="fpc" data-name="%s">' % html.escape(_fix_enc(c["name"])))
    _items_svg(c["items"], out)
    for k in c["kids"]:
        _ctl_svg(k, out, ctx)
    if c.get("pages"):
        cur = min(ctx.page_of(c), len(c["pages"]) - 1)
        cl = c["clip"]
        shown = range(len(c["pages"])) if ctx.all_pages else [cur]
        for i in shown:
            pg = c["pages"][i]
            out.append('<g class="fppage" data-tab="%s" data-page="%d"%s>' % (
                html.escape(c["name"]), i, "" if i == cur else ' style="display:none"'))
            _clip_open(*cl, out)
            _items_svg(pg["items"], out)
            for k in pg["kids"]:
                _ctl_svg(k, out, ctx)
            out.append("</g></g>")
        if len(c["pages"]) > 1:
            # page selector above the tab control: the page names, the shown one bold, a dot where changes are
            x = cl[0]
            for i, pg in enumerate(c["pages"]):
                n = ctx.changes_on_page(pg)
                label = pg["name"] or "#%d" % (i + 1)
                w = 9 + 6.2 * len(label) + (10 if n else 0)
                out.append('<g class="fptab%s" data-tab="%s" data-page="%d">'
                           '<rect x="%s" y="%s" width="%s" height="15" rx="3" fill="%s" stroke="#8c959f" stroke-width=".7"/>'
                           '<text x="%s" y="%s" font-size="10.5" fill="#1c2128"%s>%s</text>%s</g>' % (
                               " on" if i == cur else "", html.escape(c["name"]), i,
                               _n(x), _n(cl[1] - 18), _n(w), "#ffffff" if i == cur else "#eef0f2",
                               _n(x + 4.5), _n(cl[1] - 7), ' font-weight="bold"' if i == cur else "",
                               html.escape(label, quote=False),
                               ('<circle cx="%s" cy="%s" r="3.2" fill="%s"/>' % (_n(x + w - 7), _n(cl[1] - 10.5), COLORS["modified"])) if n else ""))
                x += w + 3
    out.append('</g>')
    m = ctx.mark_of(c)
    if m:
        b = _box(c, ctx.page_of(c))
        if b:
            col = COLORS.get(m["kind"], COLORS["modified"])
            dash = ' stroke-dasharray="6 3"' if m["kind"] == "moved" else ' stroke-dasharray="2 3"' if m["kind"] in ("typedef", "minor") else ""
            out.append('<rect class="fpmark" data-num="%d" x="%s" y="%s" width="%s" height="%s" rx="3" fill="%s" fill-opacity="%s"'
                       ' stroke="%s" stroke-width="2.5"%s/>' % (
                           m["num"], _n(b[0] - 4), _n(b[1] - 4), _n(b[2] - b[0] + 8), _n(b[3] - b[1] + 8), col,
                           "0.06" if m["kind"] in ("moved", "typedef", "minor") else "0.14", col, dash))
            out.append('<g class="fpbadge" data-num="%d"><circle cx="%s" cy="%s" r="9" fill="%s"/>'
                       '<text x="%s" y="%s" font-size="11" font-weight="bold" fill="#fff" text-anchor="middle">%d</text></g>' % (
                           m["num"], _n(b[0] - 4), _n(b[1] - 4), col, _n(b[0] - 4), _n(b[1]), m["num"]))
            ctx.drawn.add(m["num"])


def panel_bounds(model, page_of=lambda c: 0):
    xs, ys = [], []
    for c in model["ctls"]:
        b = _box(c, page_of(c))
        if b:
            xs.extend((b[0], b[2]))
            ys.extend((b[1], b[3] + (0 if not c.get("pages") or len(c["pages"]) < 2 else 0)))
            if c.get("pages") and len(c["pages"]) > 1:
                ys.append(c["clip"][1] - 20)
    for it in model["deco"]:
        xs.extend((it[1], it[3]))
        ys.extend((it[2], it[4]))
    if not xs:
        return [0, 0, 300, 200]
    return [min(xs), min(ys), max(xs), max(ys)]


class _Ctx:
    def __init__(self, model, mk, side, pages=None, all_pages=False):
        self.by_name = {}
        for m in mk:
            if side == "old" and m["kind"] == "added" or side == "new" and m["kind"] == "removed":
                continue
            self.by_name.setdefault(m["name"], m)
        self.all_pages = all_pages
        self.drawn = set()
        self.choice = {}
        # on a tab control, show the page that holds the most changes (or the one asked for)
        for c in walk(model["ctls"]) if model else []:
            if c.get("pages"):
                best, bc = 0, 0
                for i, pg in enumerate(c["pages"]):
                    n = self.changes_on_page(pg)
                    if n > bc:
                        best, bc = i, n
                self.choice[c["uid"]] = best
                if pages and c["name"] in pages:
                    self.choice[c["uid"]] = min(pages[c["name"]], len(c["pages"]) - 1)

    def page_of(self, c):
        return self.choice.get(c["uid"], 0)

    def mark_of(self, c):
        return self.by_name.get(c["name"])

    def changes_on_page(self, pg):
        return sum(1 for k in walk(pg["kids"]) if k["name"] in self.by_name)


def side_body(model, mk, side, pages=None, all_pages=False):
    """SVG elements of one panel with the change markers. mk: marks(); side: 'old' or 'new';
    pages: {tab control name: page index} to show; all_pages: write every tab page (hidden ones with display:none)
    so the viewer can switch pages. Returns (elements, bounds, ctx)."""
    if not model:
        return [], [0, 0, 300, 120], _Ctx(None, mk, side)
    ctx = _Ctx(model, mk, side, pages, all_pages)
    out = []
    _items_svg(model["deco"], out)
    for c in model["ctls"]:
        _ctl_svg(c, out, ctx)
    bb = panel_bounds(model, ctx.page_of)
    return out, [bb[0] - 16, bb[1] - 16, bb[2] + 16, bb[3] + 16], ctx


def page_views(model_old, model_new, mk):
    """For reports: page choices so that every change on a tab page is shown once. [{tab name: page index}]"""
    views = [{}]
    shown = set()
    for side, model in (("new", model_new), ("old", model_old)):
        if not model:
            continue
        _, _, ctx = side_body(model, mk, side)
        shown |= ctx.drawn
    for side, model in (("new", model_new), ("old", model_old)):
        if not model:
            continue
        ctx = _Ctx(model, mk, side)
        for c in walk(model["ctls"]):
            for i, pg in enumerate(c.get("pages") or []):
                nums = {ctx.by_name[k["name"]]["num"] for k in walk(pg["kids"]) if k["name"] in ctx.by_name}
                if nums - shown:
                    views.append({c["name"]: i})
                    shown |= nums
    return views


def side_svg(model, mk, side, empty_text="(not in this version)"):
    """One panel as a standalone SVG (for the viewer): every tab page is included, the viewer switches them."""
    body, b, _ = side_body(model, mk, side, all_pages=True)
    bg = (model or {}).get("bg") or PANEL_BG
    w, h = b[2] - b[0], b[3] - b[1]
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" class="fp" viewBox="%s %s %s %s" width="%s" height="%s" font-family="%s">' % (
        _n(b[0]), _n(b[1]), _n(w), _n(h), _n(w), _n(h), FONT),
        # the panel color fills the whole viewer pane, whatever the zoom
        '<rect x="%s" y="%s" width="%s" height="%s" fill="%s"/>' % (_n(b[0] - 20000), _n(b[1] - 20000), _n(w + 40000), _n(h + 40000), bg)]
    if not model:
        parts.append('<text x="150" y="60" font-size="13" fill="#8c959f" text-anchor="middle">%s</text>' % html.escape(empty_text))
    parts.extend(body)
    parts.append("</svg>")
    return "\n".join(parts)


def pair_svg(old_model, new_model, mk, out_file, old_title="A", new_title="B", empty_text="(not in this version)",
             pages=None):
    """A and B front panels in one SVG file (reports and PDF): side by side, or one above the other for wide panels."""
    sides = []
    for model, tag, title in ((old_model, "old", old_title), (new_model, "new", new_title)):
        body, b, _ = side_body(model, mk, tag, pages)
        sides.append((model, tag, title, body, b))
    HEAD, GAP = 28, 14
    ws = [s[4][2] - s[4][0] for s in sides]
    hs = [s[4][3] - s[4][1] for s in sides]
    side_by_side = (sum(ws) + GAP) / (max(hs) + HEAD) <= 1.55 * 1.6
    if side_by_side:
        W, H = sum(ws) + GAP, max(hs) + HEAD
        offs = [(0, 0), (ws[0] + GAP, 0)]
    else:
        W, H = max(ws), sum(hs) + 2 * HEAD + GAP
        offs = [(0, 0), (0, hs[0] + HEAD + GAP)]
    p = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<svg xmlns="http://www.w3.org/2000/svg" width="%s" height="%s" viewBox="0 0 %s %s" font-family="%s">' % (
             _n(W), _n(H), _n(W), _n(H), FONT),
         '<rect width="100%" height="100%" fill="#ffffff"/>']
    for (model, tag, title, body, b), (x, y), w, h in zip(sides, offs, ws, hs):
        col = "#1a7f37" if tag == "new" else "#57606a"
        p.append('<g transform="translate(%s,%s)">' % (_n(x), _n(y)))
        p.append('<rect x="0" y="0" width="%s" height="%s" rx="4" fill="%s"/>' % (_n(w), _n(HEAD - 5), col))
        p.append('<text x="8" y="%s" font-size="13" font-weight="bold" fill="#fff">%s</text>' % (
            _n(HEAD - 10), html.escape(title, quote=False)))
        p.append('<svg x="0" y="%s" width="%s" height="%s" viewBox="%s %s %s %s">' % (
            _n(HEAD), _n(w), _n(h), _n(b[0]), _n(b[1]), _n(w), _n(h)))
        p.append('<rect x="%s" y="%s" width="%s" height="%s" fill="%s" stroke="#d0d7de"/>' % (
            _n(b[0]), _n(b[1]), _n(w), _n(h), (model or {}).get("bg") or PANEL_BG))
        if not model:
            p.append('<text x="%s" y="%s" font-size="13" fill="#8c959f" text-anchor="middle">%s</text>' % (
                _n(b[0] + w / 2), _n(b[1] + h / 2), html.escape(empty_text)))
        p.extend(body)
        p.append('</svg></g>')
    p.append('</svg>')
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("\n".join(p))
    return out_file
