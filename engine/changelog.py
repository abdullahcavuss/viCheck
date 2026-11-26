"""
Generates CHANGELOG.md between two versions (with images).

Output folder:
    CHANGELOG.md
    changelog-images/<vi>_v1.svg ...   (previous + new version in the same SVG)
"""
import datetime
import difflib
import os
import re
import shutil
import unicodedata
import zipfile

from .files import diff_trees, is_vi, is_text, human_size
from . import render, svgrender
from .vi_diff import apply_typedef_priority, CATEGORIES, CHANGE_CATEGORY, change_cat

DEFAULT_CATS = ("logic", "fp", "typedef")

# parts of the report that can be left out (PDF / Markdown):
#   summary  summary tables          lists     change lists of every VI
#   overview whole A + B diagram     details   cropped A + B views of the changes
#   others   unreadable / out of scope / re-saved VIs and the other files
#   panel    front panel of A and B with the numbered control changes
#   typedef  typedef / global updates whose value did not change (off by default: not a real difference)
INCLUDE_ALL = ("summary", "lists", "overview", "details", "panel", "others", "typedef")
INCLUDE_DEFAULT = tuple(k for k in INCLUDE_ALL if k != "typedef")

IMG_DIR = "changelog-images"

KIND_TXT = {
    "added": "Added", "removed": "Removed", "modified": "Modified",
    "wire_added": "Wire added", "wire_removed": "Wire removed", "wire_modified": "Wire changed",
    "note_added": "Comment added", "note_removed": "Comment removed",
}
KIND_MARK = {"added": "🟩", "wire_added": "🟩", "note_added": "🟩",
             "removed": "🟥", "wire_removed": "🟥", "note_removed": "🟥",
             "modified": "🟧", "wire_modified": "🟧", "moved": "🟦", "reframed": "🟪", "typedef": "⬜", "minor": "⬜"}
FILE_TXT = {"added": "added", "deleted": "deleted", "modified": "modified", "renamed": "moved/renamed"}


def _ascii(text):
    """Transliterate accented letters to ASCII (dotless i is not decomposed by NFKD)."""
    text = text.replace("\u0131", "i").replace("\u0130", "I")
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def slug(path):
    path = _ascii(path)
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", path.replace("/", "__"))
    s = re.sub(r"\.(vi|ctl|vit|vim|ctt)$", "", s, flags=re.I)
    return s.strip("_")[:80] or "vi"


def anchor(path):
    return "vi-" + slug(path).lower().replace(".", "-")


def _short(t, n=60):
    t = str(t)
    return t if len(t) <= n else t[:n - 1].rstrip() + "…"


def _brief(item, names, cats, max_items=3):
    """Summarizes the changes in one VI on a single line."""
    c, res = item["c"], item["d"]["diff"]
    if c["status"] == "added":
        n = len((item["d"]["new"].get("bd") or {}).get("nodes") or [])
        return "New VI added" + (" (%d top-level items on the block diagram)" % n if n else "")
    if c["status"] == "deleted":
        return "VI deleted"
    bits = []
    changes = [ch for ch in res["changes"] if change_cat(ch) in cats]
    logic = [ch for ch in changes if change_cat(ch) == "logic"]
    if logic:
        cnt = {}
        for ch in logic:
            k = "reframed" if ch.get("reframe") else ch["kind"].replace("wire_", "").replace("note_", "")
            cnt[k] = cnt.get(k, 0) + 1
        marks = " ".join("%s%d" % (KIND_MARK.get(k, "•"), v) for k, v in sorted(cnt.items()))
        pri = {"modified": 0, "added": 1, "removed": 2}
        ranked = sorted(logic, key=lambda ch: (bool(ch.get("reframe")), ch["kind"].startswith(("wire_", "note_")),
                                                pri.get(ch["kind"].split("_")[-1], 3)))
        titles = []
        for ch in ranked[:max_items]:
            t = _short(_prim_sub(ch["title"], names))
            if ch.get("detail") and ch["kind"] == "modified":
                t += " (%s)" % _short(_prim_sub(ch["detail"], names), 40)
            titles.append(t)
        more = len(logic) - len(titles)
        bits.append("**Block diagram** %s: %s%s" % (marks, "; ".join(titles), (" (+%d more)" % more) if more else ""))
    moved = [ch for ch in changes if ch["kind"] == "moved"]
    if moved:
        bits.append("Block diagram layout: %d item(s) moved/resized" % len(moved))
    for p in item["parts"]:
        if p["key"] in ("bd", "version", "bd_notes") or (p["key"] == "bd_layout" and moved):
            continue
        det = _short(_prim_sub(p.get("detail") or "", names), 70)
        bits.append("%s%s" % (p["label"], (": " + det) if det else ""))
    return " · ".join(bits) or "Details below"


def num_ranges(nums):
    """[1,2,3,5,7,8] -> '1–3, 5, 7–8'"""
    nums = sorted(set(nums))
    out, i = [], 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        out.append(str(nums[i]) if i == j else "%d–%d" % (nums[i], nums[j]))
        i = j + 1
    return ", ".join(out)


def md_escape(t):
    return str(t).replace("|", "\\|").replace("\n", " ")


def commits_between(store, repo, base_id, head_id):
    out = []
    cid = head_id
    while cid and cid != base_id and len(out) < 500:
        c = store.get_commit(repo, cid)
        if c is None:
            break
        out.append(c)
        cid = c["parent"]
    return out


def _prim_sub(text, names):
    return re.sub(r"Prim (\d+)", lambda m: names.get(m.group(1), m.group(0)), text or "")


def generate(store, vis, repo, base_ref, head_ref, out_dir, progress=None, all_tiles=False, cats=None,
             flat=True, details=False, include=None, typedef_mode="low", group=False, lang="en", only=None):
    """only: set of VI paths to put in the report (None = every changed VI). The other VIs are left out
    completely; the non-VI files are not affected."""
    cats = set(cats or DEFAULT_CATS)
    inc = set(include) if include is not None else set(INCLUDE_DEFAULT) - ({"details"} if not details else set())
    head = store.get_commit(repo, head_ref)
    if head is None:
        raise ValueError("New version not found")
    base = store.get_commit(repo, base_ref) if base_ref else None
    if base_ref and base is None:
        raise ValueError("Old version not found")
    os.makedirs(os.path.join(out_dir, IMG_DIR), exist_ok=True)
    names = store.prim_names()
    changes = diff_trees(base["tree"] if base else {}, head["tree"])
    vi_changes = [c for c in changes if is_vi(c["path"]) and c["status"] in ("added", "deleted", "modified")]
    other = [c for c in changes if c not in vi_changes]
    vi_all = len(vi_changes)
    if only is not None:
        only = set(only)
        vi_changes = [c for c in vi_changes if c["path"] in only]
    total = len(vi_changes)

    functional, layout, saved, errors, excluded, tdonly, td_hidden = [], [], [], [], [], [], []
    minor_only = []
    for i, c in enumerate(vi_changes, 1):
        if progress:
            progress(i - 1, total, c["path"])
        d = vis.diff(c.get("old_sha"), c.get("new_sha"), c["path"])
        verdict = d["diff"].get("verdict") or {"level": "functional", "parts": [], "cats": ["logic"]}
        # typedef updates hidden from the report: classify them as their own (low) level, then leave such VIs out
        verdict = apply_typedef_priority(verdict, typedef_mode if "typedef" in inc else "low")
        sel = [p for p in verdict["parts"] if p.get("cat", "other") in cats or p["key"] in ("error", "file")]
        if "typedef" not in inc:
            sel = [p for p in sel if p["level"] != "typedef"]
        item = {"c": c, "d": d, "verdict": verdict, "parts": sel,
                "base_short": base["short"] if base else None, "head_short": head["short"],
                "old_title": base.get("image_title") if base else None, "new_title": head.get("image_title")}
        if any(p["key"] == "error" for p in verdict["parts"]):
            errors.append(item)
        elif verdict["level"] == "saved":
            (saved if "saved" in cats else excluded).append(item)
        elif verdict["level"] == "minor":
            # only differences the user does not count as changes (settings → change acceptance)
            minor_only.append(item)
            if "minor" in cats:
                layout.append(item)
        elif verdict["level"] == "typedef":
            if "typedef" not in inc:
                td_hidden.append(item)
            else:
                (tdonly if "typedef" in cats else excluded).append(item)
        elif not [p for p in sel if p["key"] != "version"]:
            # only hidden typedef updates were left: counted with them, not as out of scope
            hid = "typedef" not in inc and any(p["level"] == "typedef" for p in verdict["parts"])
            if hid:
                td_hidden.append(item)
            elif any(p["level"] == "minor" for p in verdict["parts"]):
                minor_only.append(item)
            else:
                excluded.append(item)
        elif any(p["level"] == "functional" for p in sel):
            functional.append(item)
        else:
            layout.append(item)
    if progress:
        progress(total, total, "")

    L = []
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    L.append("# Changelog — %s" % repo["name"])
    L.append("")
    if base:
        L.append("**Range:** `%s` %s (%s) → `%s` %s (%s)  " % (base["short"], md_escape(base["title"]), base["time"],
                                                             head["short"], md_escape(head["title"]), head["time"]))
    else:
        L.append("**Version:** `%s` %s (%s) — first version  " % (head["short"], md_escape(head["title"]), head["time"]))
    L.append("**Branch:** `%s` · **Generated:** %s · VIVER  " % (head["branch"], now))
    L.append("**Scope:** %s  " % ", ".join(t for k, t in CATEGORIES if k in cats))
    L.append("")

    # ---- summary
    if "summary" in inc:
        L.extend(_summary(functional, layout, saved, excluded, errors, other, cats, names, tdonly, len(td_hidden),
                          len(minor_only)))

    # ---- commits
    cl = commits_between(store, repo, base["id"] if base else None, head["id"])
    if cl:
        L.append("## Commits")
        L.append("")
        for c in cl:
            L.append("- `%s` %s — **%s** _(%s)_" % (c["short"], c["time"], md_escape(c["title"]), c["author"] or "?"))
            if c["body"]:
                for line in c["body"].splitlines():
                    L.append("  > %s" % line)
        L.append("")

    # ---- VI sections
    legend = ("Changed items are marked with numbered boxes in the images: 🟩 added, 🟥 removed, 🟧 modified, "
              "🟪 only moved into another structure/frame%s. "
              "Unchanged parts are dimmed. The numbers match the lists below."
              % (", 🟦 moved" if "bd_layout" in cats else ""))
    for heading, group in (("VIs with content changes", functional), ("Visual/layout changes", layout)):
        if not group:
            continue
        L.append("## %s" % heading)
        L.append("")
        L.append(legend)
        L.append("")
        for item in group:
            if progress:
                progress(total, total, "images: " + item["c"]["path"])
            L.extend(_vi_section(item, out_dir, names, all_tiles, cats, flat=flat, include=inc, group=group, lang=lang))

    if errors and "others" in inc:
        L.append("## Unreadable VIs")
        L.append("")
        for item in errors:
            msg = "; ".join(p.get("detail") or p["label"] for p in item["verdict"]["parts"] if p["key"] == "error")
            L.append("- `%s` — %s" % (item["c"]["path"], md_escape(msg)))
        L.append("")

    if excluded and "others" in inc:
        L.append("## VIs out of scope")
        L.append("")
        L.append("<details><summary>%d VI(s) — changes only in categories that were not selected</summary>" % len(excluded))
        L.append("")
        for item in excluded:
            labels = sorted({p["label"] for p in item["verdict"]["parts"] if p["key"] != "version"}) or ["re-saved"]
            L.append("- `%s` — %s" % (item["c"]["path"], ", ".join(labels)))
        L.append("")
        L.append("</details>")
        L.append("")

    if tdonly:
        L.append("## VIs where only typedefs / globals they use changed")
        L.append("")
        L.append("_A typedef (.ctl) or global variable used by these VIs changed and LabVIEW updated them; "
                 "their own code and the values are the same._")
        L.append("")
        for item in tdonly:
            what = "; ".join(p.get("detail") or p["label"] for p in item["verdict"]["parts"] if p["level"] == "typedef")
            L.append("- `%s` — %s" % (item["c"]["path"], md_escape(_prim_sub(what, names))))
        L.append("")

    if saved and "others" in inc:
        L.append("## VIs re-saved only")
        L.append("")
        L.append("<details><summary>%d VI(s) — content unchanged (revision / compiled code / internal numbers)</summary>" % len(saved))
        L.append("")
        for item in saved:
            ver = next((p["detail"] for p in item["verdict"]["parts"] if p["key"] == "version"), "")
            L.append("- `%s`%s" % (item["c"]["path"], (" — LabVIEW " + ver) if ver else ""))
        L.append("")
        L.append("</details>")
        L.append("")

    # ---- other files
    if other and "others" in inc:
        L.append("## Other files")
        L.append("")
        for c in other:
            if c["status"] == "renamed":
                L.append("- `%s` → `%s` (%s)" % (c["old_path"], c["path"], FILE_TXT["renamed"]))
                continue
            size = human_size(c["new_size"] or c["old_size"] or 0)
            L.append("- `%s` — %s (%s)" % (c["path"], FILE_TXT.get(c["status"], c["status"]), size))
            if c["status"] == "modified" and is_text(c["path"]):
                try:
                    a = store.get_blob(c["old_sha"]).decode("utf-8", "replace").splitlines()
                    b = store.get_blob(c["new_sha"]).decode("utf-8", "replace").splitlines()
                    dl = list(difflib.unified_diff(a, b, lineterm="", n=1))[2:]
                    if dl:
                        L.append("")
                        L.append("  ```diff")
                        for line in dl[:60]:
                            L.append("  " + line)
                        if len(dl) > 60:
                            L.append("  … (%d more lines)" % (len(dl) - 60))
                        L.append("  ```")
                except Exception:
                    pass
        L.append("")

    md = "\n".join(L).rstrip() + "\n"
    with open(os.path.join(out_dir, "CHANGELOG.md"), "w", encoding="utf-8") as f:
        f.write(md)
    return {"functional": len(functional), "layout": len(layout), "saved": len(saved), "typedef": len(tdonly),
            "minor": len(minor_only),
            "errors": len(errors), "other": len(other), "commits": len(cl), "excluded": len(excluded),
            "cats": sorted(cats), "vi_selected": total, "vi_all": vi_all}


def _summary(functional, layout, saved, excluded, errors, other, cats, names, tdonly=(), td_hidden=0, minor=0):
    L = []
    L.append("## Summary")

    L.append("")
    L.append("| | Count |")
    L.append("|---|---:|")
    L.append("| VIs with content changes | %d |" % len(functional))
    L.append("| VIs with visual/layout changes only | %d |" % len(layout))
    if td_hidden:
        L.append("| VIs where only typedefs / globals they use changed (value unchanged) — not shown | %d |" % td_hidden)
    elif "typedef" in cats:
        L.append("| VIs where only typedefs / globals they use changed (value unchanged) | %d |" % len(tdonly))
    if minor:
        L.append("| VIs with only differences not counted as changes%s | %d |" % (
            "" if "minor" in cats else " — not shown", minor))
    if "saved" in cats:
        L.append("| VIs re-saved only | %d |" % len(saved))
    if excluded:
        L.append("| VIs out of scope | %d |" % len(excluded))
    if errors:
        L.append("| Unreadable VIs | %d |" % len(errors))
    L.append("| Other file changes | %d |" % len(other))
    L.append("")

    # ---- short summary of the changed VIs (details and images below)
    if functional or layout:
        L.append("### Changed VIs")
        L.append("")
        L.append("| VI | Status | What changed |")
        L.append("|---|---|---|")
        for grp, item in [("content", it) for it in functional] + [("layout", it) for it in layout]:
            c = item["c"]
            name = c["path"].split("/")[-1]
            folder = "/".join(c["path"].split("/")[:-1])
            st = {"added": "🟩 New", "deleted": "🟥 Deleted", "modified": "🟧 Modified"}[c["status"]]
            if grp == "layout":
                st += " (layout)"
            L.append("| [%s](#%s)%s | %s | %s |" % (md_escape(name), anchor(c["path"]),
                                                  ("<br>`%s`" % md_escape(folder)) if folder else "",
                                                  st, md_escape(_brief(item, names, cats))))
        L.append("")
        L.append("_Details and images are below; click a VI name to jump to its section._")
        L.append("")
    return L


def _vi_section(item, out_dir, names, all_tiles, cats, flat=True, details=False, include=None, group=False, lang="en"):
    inc = set(include) if include is not None else set(INCLUDE_DEFAULT) - ({"details"} if not details else set())
    from . import story as ST
    c, d, verdict = item["c"], item["d"], item["verdict"]
    res = d["diff"]
    L = []
    title = c["path"].split("/")[-1]
    L.append('<a id="%s"></a>' % anchor(c["path"]))
    L.append("")
    L.append("### %s" % title)
    L.append("")
    status = {"added": "New VI", "deleted": "Deleted VI", "modified": "Modified"}[c["status"]]
    L.append("`%s` · %s" % (c["path"], status))
    L.append("")
    shown = [p for p in item["parts"] if p["key"] not in ("bd", "version", "bd_notes")
             and ("typedef" in inc or p["level"] != "typedef")
             and not (p["key"] == "bd_layout" and any(ch["kind"] == "moved" for ch in res["changes"]))]
    for p in (shown if "lists" in inc else []):
        L.append("- **%s**%s" % (p["label"], (": " + md_escape(_prim_sub(p["detail"], names))) if p.get("detail") else ""))
    if shown:
        L.append("")

    changes = [ch for ch in res["changes"] if change_cat(ch) in cats or (ch.get("cat") == "typedef" and "typedef" in inc)]
    if "typedef" not in inc:
        changes = [ch for ch in changes if ch.get("cat") != "typedef"]
    order = {"logic": 0, "auto": 1, "bd_layout": 2}
    changes.sort(key=lambda ch: (order.get(change_cat(ch), 0), bool(ch.get("reframe"))))  # frame-only moves last
    if c["status"] != "modified":
        changes = []  # in a new/deleted VI every item is "added/removed"; the image is enough instead of a list
    # numbered entries: one per change, or one per group of related changes (main change first)
    entries = []
    if group:
        allc = {c["id"]: c for c in res["changes"]}
        inlist = {c["id"] for c in changes}
        seen = set()
        for ch in changes:
            g = ch.get("group", ch["id"])
            if g in seen:
                continue
            seen.add(g)
            main = allc.get(g, ch)
            members = [allc[i] for i in (main.get("group_members") or [main["id"]]) if i in inlist]
            head = main if main["id"] in inlist else members[0]
            entries.append((head, [m for m in members if m is not head], main.get("group_title"),
                            [ST.render(it, lang) for it in main.get("gstory") or []]))
    else:
        entries = [(ch, [], None, [ST.render(it, lang) for it in ch.get("story") or []]) for ch in changes]
    if changes and "lists" in inc:
        L.append("**Block diagram changes**" if any(change_cat(ch) == "logic" for ch in changes)
                 else "**Block diagram layout changes**")
        L.append("")
        for i, (ch, rest, gtitle, sents) in enumerate(entries, 1):
            wireish = ch["kind"].startswith("wire") and sents and not gtitle
            t = _prim_sub(sents[0] if wireish else (gtitle or ch["title"]), names)
            line = "%d. %s %s" % (i, KIND_MARK.get(ch["cat"] if ch.get("cat") in ("typedef", "minor") else "reframed" if ch.get("reframe")
                                                  else ch["kind"], "•"), md_escape(t))
            if ch.get("detail") and not wireish:
                line += " — %s" % md_escape(_prim_sub(ch["detail"], names))
            if ch.get("path"):
                line += " _(%s)_" % md_escape(ch["path"])
            if rest and not sents:
                line += " · _+%d related: %s_" % (len(rest), _related_text(rest))
            L.append(line)
            for s_ in (sents[1:] if wireish else sents):
                L.append("    - %s" % md_escape(_prim_sub(s_, names)))
        L.append("")

    # images: every member of a group carries the group's number
    hn, ho, rn, ro = {}, {}, [], []
    numbered = [(i, m) for i, (ch, rest, _, _s) in enumerate(entries, 1) for m in [ch] + rest]
    for i, ch in numbered:
        k = ch["kind"]
        if ch.get("new_uid") and k == "moved":
            hn[ch["new_uid"]] = ("moved", i)
            rn.append((i, ch.get("new_reveal") or []))
        if ch.get("cat") in ("typedef", "minor"):
            for side, h, r in (("new", hn, rn), ("old", ho, ro)):
                if ch.get(side + "_uid"):
                    h[ch[side + "_uid"]] = (ch["cat"], i)
                    r.append((i, ch.get(side + "_reveal") or []))
            continue
        if ch.get("new_uid") and k in ("added", "modified", "wire_added", "wire_modified", "note_added"):
            hn[ch["new_uid"]] = ("added" if "added" in k else ("reframed" if ch.get("reframe") else "modified"), i)
            rn.append((i, ch.get("new_reveal") or []))
        if ch.get("old_uid") and k in ("removed", "modified", "wire_removed", "wire_modified", "note_removed"):
            ho[ch["old_uid"]] = ("removed" if "removed" in k else ("reframed" if ch.get("reframe") else "modified"), i)
            ro.append((i, ch.get("old_reveal") or []))
    base = os.path.join(out_dir, IMG_DIR, slug(c["path"]))
    new_bd = d["new"].get("bd") if not d["new"].get("empty") else None
    old_bd = d["old"].get("bd") if not d["old"].get("empty") else None

    old_t = item.get("old_title") or ("Previous version" + (" (%s)" % item["base_short"] if item.get("base_short") else ""))
    new_t = item.get("new_title") or ("New version" + (" (%s)" % item["head_short"] if item.get("head_short") else ""))
    if c["status"] == "added":
        old_bd, ho, ro = None, {}, []
    elif c["status"] == "deleted":
        new_bd, hn, rn = None, {}, []
    has_old = bool(old_bd and old_bd.get("nodes"))
    has_new = bool(new_bd and new_bd.get("nodes"))
    if (has_old or has_new) and not (c["status"] == "modified" and not (rn or ro)) and inc & {"overview", "details"}:
        try:
            views = svgrender.render_pair(old_bd if has_old else None, ho, ro, new_bd if has_new else None, hn, rn,
                                          base, names, old_title=old_t, new_title=new_t, flat=flat,
                                          details="details" in inc)
        except Exception as e:  # an image failure for one VI must not stop the whole CHANGELOG
            import logging
            logging.exception("Could not render CHANGELOG image: %s", c["path"])
            L.append("> ⚠ Could not render an image for this VI (%s: %s). The list of changes is above." % (type(e).__name__, e))
            L.append("")
            views = []
        if views:
            L.append("**Block diagram — previous and new version**")
            L.append("")
        for vi, v in enumerate(views, 1):
            if "overview" in inc:
                if len(views) > 1 or v["desc"]:
                    L.append("_View %d%s%s_" % (vi, (" — " + "; ".join(v["desc"])) if v["desc"] else "",
                                                  (" · change " + num_ranges(v["nums"])) if v["nums"] else ""))
                    L.append("")
                rel = os.path.relpath(v["file"], out_dir).replace(os.sep, "/").replace(" ", "%20")
                L.append("[![%s — previous and new version](%s)](%s)" % (md_escape(title), rel, rel))
                L.append("")
            else:
                os.remove(v["file"])   # the whole diagram is not wanted in the report
            for k, dv in enumerate(v.get("details") or [], 1):
                drel = os.path.relpath(dv["file"], out_dir).replace(os.sep, "/").replace(" ", "%20")
                L.append("_Detail %d · change %s_" % (k, num_ranges(dv["nums"])))
                L.append("")
                L.append("[![%s — detail](%s)](%s)" % (md_escape(title), drel, drel))
                L.append("")
        if views and "overview" in inc:
            L.append("_The image is an SVG: click to open it full size; it stays sharp when you zoom in the browser._")
            L.append("")
    if "panel" in inc and "fp" in cats and c["status"] == "modified":
        L.extend(_panel_section(d, res, base, out_dir, title, old_t, new_t, inc, cats))
    L.append("---")
    L.append("")
    return L


def _related_text(rest):
    n = {}
    for m in rest:
        k = ("wire(s)" if m["kind"].startswith("wire") else "typedef/global update(s)" if m.get("cat") == "typedef"
             else "moved into/out of it" if m.get("reframe") else m["kind"])
        n[k] = n.get(k, 0) + 1
    order = ["added", "removed", "modified", "moved into/out of it", "typedef/global update(s)", "wire(s)"]
    return ", ".join("%d %s" % (n[k], k) for k in order + sorted(set(n) - set(order)) if k in n)


def _panel_section(d, res, base, out_dir, title, old_t, new_t, inc, cats=()):
    """Front panel: numbered list of control changes and the A + B panels (one image per tab page with changes)."""
    from . import fprender
    L = []
    mk = fprender.marks(d["old"], d["new"], res.get("fp"), res.get("accept"))
    hide = ({"typedef"} if "typedef" not in inc else set()) | ({"minor"} if "minor" not in cats else set())
    if hide:          # typedef updates with the value unchanged / differences not counted are not shown
        mk = [m for m in mk if m["kind"] not in hide]
        for k, m in enumerate(mk, 1):
            m["num"] = k
    od, nd = d["old"].get("fp_draw"), d["new"].get("fp_draw")
    if not mk or not (od or nd):
        return L
    if "lists" in inc:
        L.append("**Front panel changes**")
        L.append("")
        for m in mk:
            L.append("%d. %s “%s” — %s" % (m["num"], KIND_MARK.get(m["kind"], "•"), md_escape(m["name"]), md_escape(m["detail"])))
        L.append("")
    try:
        views = fprender.page_views(od, nd, mk)
        L.append("**Front panel — previous and new version**")
        L.append("")
        for k, pv in enumerate(views, 1):
            fn = "%s_fp%d.svg" % (base, k)
            fprender.pair_svg(od, nd, mk, fn, old_t, new_t, pages=pv)
            if len(views) > 1:
                page = "; ".join("%s: %s" % (tab, _page_name(nd or od, tab, i)) for tab, i in pv.items())
                L.append("_Front panel view %d%s_" % (k, (" — " + page + " page") if page else ""))
                L.append("")
            rel = os.path.relpath(fn, out_dir).replace(os.sep, "/").replace(" ", "%20")
            L.append("[![%s — front panel](%s)](%s)" % (md_escape(title), rel, rel))
            L.append("")
    except Exception as e:
        import logging
        logging.exception("Could not render the front panel image")
        L.append("> ⚠ Could not draw the front panel (%s: %s)." % (type(e).__name__, e))
        L.append("")
    return L


def _page_name(model, tab, i):
    from . import fprender
    for c in fprender.walk(model["ctls"]):
        if c["name"] == tab and c.get("pages") and i < len(c["pages"]):
            return c["pages"][i]["name"] or "#%d" % (i + 1)
    return "#%d" % (i + 1)


def zip_dir(out_dir, zip_path, root_name="CHANGELOG"):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for r, _, files in os.walk(out_dir):
            for f in files:
                full = os.path.join(r, f)
                if full == zip_path:
                    continue
                z.write(full, os.path.join(root_name, os.path.relpath(full, out_dir)))
