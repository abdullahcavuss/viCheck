"""
Compares two VI models.

Matching order:
  1. Same uid + same signature (LabVIEW largely preserves object uids between saves)
  2. Same signature in the same parent diagram, nearest position
  3. Same class in the same parent diagram, nearby position  -> "replaced" (e.g. a subVI replaced by another VI)

Every node and wire gets a status:  same | added | removed | modified | moved
"""
import statistics

MOVE_TOLERANCE = 3  # pixels


# Nodes whose settings LabVIEW regenerates without the user touching them (especially on FPGA).
# If only their internal setting changed (wiring/terminals/name unchanged), the change goes into the "auto" category.
AUTO_CLASSES = {"timeLoop", "timeLoopExtNode", "timeDataNode", "timeFlatSequence", "timeSequence",
                "xNode", "xStructure"}
AUTO_LABEL = "Timed Loop / XNode internal setting"


TD_KEPT = "the typedef “%s” it uses changed, value unchanged"
VAR_REFRESHED = "the global “%s” it uses changed"


# ---------------------------------------------------------------------------
# Change acceptance: every kind of difference viCheck finds has a rule key. A rule the user does not count as a
# change ("accepted") is still shown, faintly (status "minor"), but does not make the VI "changed": a VI with only
# accepted differences gets the level "minor", below layout, like the re-saved ones.
#   (key, label, group, counted by default)
ACCEPT_RULES = [
    ("node_added", "Item added (node, subVI, structure, constant…)", "bd", True),
    ("node_removed", "Item removed", "bd", True),
    ("wire_added", "Wire added", "bd", True),
    ("wire_removed", "Wire removed", "bd", True),
    ("wire_type", "Wire data type changed", "bd", False),
    ("subvi_update", "SubVI updated (same subVI; its connector, type or internal setting changed)", "bd", False),
    ("subvi_replace", "SubVI replaced or renamed (another VI is called)", "bd", True),
    ("const_value", "Constant value changed", "bd", True),
    ("renamed", "Item renamed (label, variable, node name)", "bd", True),
    ("node_terms", "Terminal count of a node / structure changed", "bd", True),
    ("node_setting", "Node setting / property / type changed", "bd", True),
    ("io_mode", "Read ↔ write, control ↔ indicator", "bd", True),
    ("frames", "Structure frames added / removed / reordered", "bd", True),
    ("reframed", "Item moved into another structure / frame", "bd", True),
    ("auto", "Timed Loop / XNode internal setting", "bd", True),
    ("bd_layout", "Block diagram layout (moved, resized, text format, wire routing)", "bd", True),
    ("notes", "Block diagram comments added / removed", "bd", True),
    ("bd_other", "Block diagram changes without details", "bd", True),
    ("fp", "Front panel controls added / removed / changed", "fp", True),
    ("fp_look", "Front panel appearance / control properties", "fp", True),
    ("fp_layout", "Front panel layout (moved, resized)", "fp", True),
    ("conpane", "Connector pane", "vi", True),
    ("deps", "Dependencies added / removed", "vi", True),
    ("props", "Important VI properties (reentrancy, priority …)", "vi", True),
    ("props_other", "Other VI settings", "vi", True),
    ("data", "Default values / data space", "vi", True),
    ("icon", "Icon", "vi", True),
    ("desc", "VI description", "vi", True),
]
RULE_LABEL = {k: lbl for k, lbl, g, d in ACCEPT_RULES}
DEFAULT_ACCEPT = frozenset(k for k, lbl, g, d in ACCEPT_RULES if not d)
# verdict part key -> rule (block diagram parts are handled per change)
PART_RULE = {"fp": "fp", "fp_look": "fp_look", "fp_other": "fp_look", "fp_layout": "fp_layout", "conpane": "conpane",
             "deps": "deps", "props": "props", "props_other": "props_other", "data": "data", "icon": "icon",
             "desc": "desc", "bd_other": "bd_other", "bd_notes": "notes", "bd_auto": "auto", "bd_layout": "bd_layout"}


def _hexish(v):
    return not v or str(v).startswith("0x") or "…" in str(v)


def _td_value_kept(o, n):
    """A typedef constant whose flattened data changed: is it only the typedef that changed (the value itself kept)?"""
    ov, nv = o.get("value"), n.get("value")
    if ov == nv and not _hexish(ov):
        return True                      # e.g. an enum item added to the typedef, the selected item is the same
    fo, fn = o.get("vfields"), n.get("vfields")
    if fo and fn and "…" not in fo and "…" not in fn:
        common = set(fo) & set(fn)
        if common and all(fo[k] == fn[k] for k in common):
            return True                  # cluster: fields added/removed, the common fields keep their values
    ro, rn = o.get("raw") or "", n.get("raw") or ""
    if ro and rn and ro != rn and (rn.startswith(ro) or ro.startswith(rn)):
        return True                      # a field appended/removed at the end
    return False


def change_cat(ch):
    return ch.get("cat") or CHANGE_CATEGORY.get(ch["kind"], "logic")


def _walk(diagram, path, reveal, out_nodes, out_diagrams, parent_key):
    """Flatten the diagram tree; record each node's path and the frames needed to make it visible."""
    out_diagrams[parent_key] = diagram
    for n in diagram["nodes"]:
        n["_path"] = list(path)
        n["_reveal"] = list(reveal)
        n["_parent"] = parent_key
        out_nodes[n["uid"]] = n
        for fi, f in enumerate(n.get("frames", [])):
            label = n["name"] + (" [%s]" % f["name"] if len(n.get("frames", [])) > 1 else "")
            _walk(f["diagram"], path + [label], reveal + [[n["uid"], fi]], out_nodes, out_diagrams,
                  "%s#%d" % (n["uid"], fi))
    for w in diagram["wires"]:
        w["_parent"] = parent_key
        w["_path"] = list(path)
        w["_reveal"] = list(reveal)
    for t in diagram["notes"]:
        t["_parent"] = parent_key
        t["_path"] = list(path)
        t["_reveal"] = list(reveal)


def _all_wires(diagram):
    for w in diagram["wires"]:
        yield w
    for n in diagram["nodes"]:
        for f in n.get("frames", []):
            yield from _all_wires(f["diagram"])


def _all_notes(diagram):
    for t in diagram["notes"]:
        yield t
    for n in diagram["nodes"]:
        for f in n.get("frames", []):
            yield from _all_notes(f["diagram"])


def _dist(a, b, dx=0, dy=0):
    return abs(a["x"] + dx - b["x"]) + abs(a["y"] + dy - b["y"])


class Differ:
    def __init__(self, old, new, accept=frozenset()):
        self.old = old
        self.new = new
        self.accept = frozenset(accept or ())
        self.on, self.od = {}, {}
        self.nn, self.nd = {}, {}
        self.pairs = {}      # old uid -> new uid
        self.rpairs = {}     # new uid -> old uid
        self.changes = []
        self.dx = self.dy = 0

    # ------------------------------------------------------------------
    def run(self):
        ob = self.old.get("bd") or {"uid": "root", "nodes": [], "wires": [], "notes": []}
        nb = self.new.get("bd") or {"uid": "root", "nodes": [], "wires": [], "notes": []}
        _walk(ob, [], [], self.on, self.od, "root")
        _walk(nb, [], [], self.nn, self.nd, "root")

        self._match_by_uid()
        self._compute_shift()
        self._match_rest()
        self._classify_nodes()
        self._diff_wires(ob, nb)
        self._diff_notes(ob, nb)
        self._apply_accept()
        self._mark_frames(ob)
        self._mark_frames(nb)
        self._group_changes()
        return self._result()

    # ------------------------------------------------------------------ related changes
    def _group_changes(self):
        """Joins changes that belong together, so the viewer / report can show them as one change:
        - a changed wire and the added/removed/modified node at either of its ends (structures only when they were
          added or removed — a modified structure's tunnels would otherwise join everything inside it)
        - items moved into a structure that was added (or out of one that was removed) and that structure
        - all updates caused by the same typedef / global
        Cosmetic moves and comments stay on their own. Every change gets "group" = id of the group's main change;
        the main change also gets "group_members" (ids, main first)."""
        parent = list(range(len(self.changes)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        node_ch = {}          # ("old"|"new", node uid) -> change id
        for ch in self.changes:
            if ch["kind"] in ("added", "removed", "modified") and ch.get("cat") not in ("typedef", "auto"):
                for side in ("old", "new"):
                    if ch.get(side + "_uid"):
                        node_ch[(side, ch[side + "_uid"])] = ch["id"]

        def struct_change(side, parent_key):
            if not parent_key or parent_key == "root":
                return None
            cid = node_ch.get((side, parent_key.split("#")[0]))
            if cid is not None and self.changes[cid]["kind"] == ("added" if side == "new" else "removed"):
                return cid
            return None

        by_td, by_wtype = {}, {}
        for ch in self.changes:
            k = ch["kind"]
            if k == "wire_modified":
                by_wtype.setdefault(ch["detail"], []).append(ch["id"])
            if k.startswith("wire_"):
                for side, nodes in (("old", self.on), ("new", self.nn)):
                    w = ch.get("_w" + side)
                    for e in (w or {}).get("ends", []):
                        cid = node_ch.get((side, e["node"]))
                        if cid is None:
                            continue
                        other = self.changes[cid]
                        n = nodes.get(e["node"])
                        if n is not None and n.get("kind") == "structure" and other["kind"] == "modified":
                            continue
                        union(cid, ch["id"])
            elif ch.get("reframe"):
                n_new = self.nn.get(ch.get("new_uid"))
                o_old = self.on.get(ch.get("old_uid"))
                cid = struct_change("new", n_new.get("_parent") if n_new else None)
                if cid is None:
                    cid = struct_change("old", o_old.get("_parent") if o_old else None)
                if cid is not None:
                    union(cid, ch["id"])
            elif ch.get("cat") == "typedef" and ch.get("td"):
                if ch["td"] in by_td:
                    union(by_td[ch["td"]], ch["id"])
                else:
                    by_td[ch["td"]] = ch["id"]
            elif k in ("added", "removed") and ch.get("cat") not in ("typedef", "auto"):
                # an item inside an added/removed structure belongs to it
                side = "new" if k == "added" else "old"
                n = (self.nn if side == "new" else self.on).get(ch.get(side + "_uid"))
                cid = struct_change(side, n.get("_parent") if n else None)
                if cid is not None:
                    union(cid, ch["id"])

        # wires whose data type changed the same way (e.g. a type redefined) and that belong to nothing else: one cause
        sizes = {}
        for ch in self.changes:
            sizes[find(ch["id"])] = sizes.get(find(ch["id"]), 0) + 1
        for ids in by_wtype.values():
            alone = [i for i in ids if sizes[find(i)] == 1]
            for i in alone[1:]:
                union(alone[0], i)

        def rank(ch):
            n = self.nn.get(ch.get("new_uid")) or self.on.get(ch.get("old_uid")) or {}
            k = ch["kind"]
            if k in ("added", "removed") and n.get("kind") == "structure":
                return 0
            if k in ("added", "removed"):
                return 1
            if k == "modified" and not ch.get("reframe") and ch.get("cat") != "typedef":
                return 2
            if ch.get("cat") == "typedef":
                return 3
            if ch.get("reframe"):
                return 4
            return 5
        groups = {}
        for ch in self.changes:
            groups.setdefault(find(ch["id"]), []).append(ch)
        for members in groups.values():
            members.sort(key=lambda c: (rank(c), c["id"]))
            main = members[0]
            for c in members:
                c["group"] = main["id"]
            if len(members) > 1:
                main["group_members"] = [c["id"] for c in members]
                # one structure removed and another added in its place: say "replaced"
                rem = [c for c in members if c["kind"] == "removed" and (self.on.get(c["old_uid"]) or {}).get("kind") == "structure"]
                add = [c for c in members if c["kind"] == "added" and (self.nn.get(c["new_uid"]) or {}).get("kind") == "structure"]
                if len(rem) == 1 and len(add) == 1:
                    main["group_title"] = "Structure “%s” replaced by “%s”" % (
                        self.on[rem[0]["old_uid"]]["name"], self.nn[add[0]["new_uid"]]["name"])
        # wires told in words: "“Stop” read and connected to “Exit”", "0 assigned to “Count”" …
        from . import story as ST
        tr_old = ST.Tracer(self.on, [w for dg in self.od.values() for w in dg["wires"]])
        tr_new = ST.Tracer(self.nn, [w for dg in self.nd.values() for w in dg["wires"]])
        for ch in self.changes:
            if ch["kind"] == "wire_added" and ch.get("_wnew"):
                ch["story"] = ST.dedupe(ST.sentences(tr_new.endpoints(ch["_wnew"]), "added"))
            elif ch["kind"] == "wire_removed" and ch.get("_wold"):
                ch["story"] = ST.dedupe(ST.sentences(tr_old.endpoints(ch["_wold"]), "removed"))
        byid = {c["id"]: c for c in self.changes}
        for ch in self.changes:
            if ch.get("group_members"):
                items = [it for i in ch["group_members"] for it in byid[i].get("story") or []]
                if items:
                    ch["gstory"] = ST.merge_ops(ST.dedupe(items))[:8]
        for ch in self.changes:
            ch.pop("_wold", None)
            ch.pop("_wnew", None)

    def _pair(self, ou, nu):
        self.pairs[ou] = nu
        self.rpairs[nu] = ou

    def _parent_pair(self, old_parent):
        """New-side counterpart of an old parent diagram key."""
        if old_parent == "root":
            return "root"
        suid, fi = old_parent.split("#")
        nu = self.pairs.get(suid)
        if nu is None:
            return None
        old_node = self.on[suid]
        new_node = self.nn[nu]
        ofr = old_node.get("frames", [])
        nfr = new_node.get("frames", [])
        fi = int(fi)
        if fi < len(ofr):
            # first by frame name, then by order
            name = ofr[fi]["name"]
            for j, f in enumerate(nfr):
                if f["name"] == name:
                    return "%s#%d" % (nu, j)
        if fi < len(nfr):
            return "%s#%d" % (nu, fi)
        return None

    def _match_by_uid(self):
        for uid, o in self.on.items():
            n = self.nn.get(uid)
            if n is not None and n["sig"] == o["sig"] and n["cls"] == o["cls"]:
                self._pair(uid, uid)

    def _compute_shift(self):
        dxs, dys = [], []
        for ou, nu in self.pairs.items():
            o, n = self.on[ou], self.nn[nu]
            if o["_parent"] == "root" and n["_parent"] == "root":
                dxs.append(n["x"] - o["x"])
                dys.append(n["y"] - o["y"])
        if len(dxs) >= 3:
            # if most items moved by the same amount on each axis, it is a global shift (Clean Up, margins, etc.)
            for axis, vals in (("dx", dxs), ("dy", dys)):
                m = statistics.median(vals)
                if sum(1 for v in vals if abs(v - m) <= 1) >= len(vals) * 0.6:
                    setattr(self, axis, m)

    def _match_rest(self):
        # several passes: once structures are matched, their contents can match too
        for _ in range(4):
            changed = False
            for strict in (True, False):
                groups = {}
                for ou, o in self.on.items():
                    if ou in self.pairs:
                        continue
                    np = self._parent_pair(o["_parent"])
                    if np is None:
                        continue
                    groups.setdefault(np, []).append(o)
                for np, olds in groups.items():
                    cands = [n for nu, n in self.nn.items() if nu not in self.rpairs and n["_parent"] == np]
                    if not cands:
                        continue
                    triples = []
                    for o in olds:
                        for n in cands:
                            if strict and n["sig"] != o["sig"]:
                                continue
                            if not strict:
                                if n["cls"] != o["cls"]:
                                    continue
                                if _dist(o, n, self.dx, self.dy) > 60:
                                    continue
                            triples.append((_dist(o, n, self.dx, self.dy), o["uid"], n["uid"]))
                    triples.sort()
                    for d, ou, nu in triples:
                        if ou in self.pairs or nu in self.rpairs:
                            continue
                        self._pair(ou, nu)
                        changed = True
            if not changed:
                break

    # ------------------------------------------------------------------
    def _add_change(self, kind, node=None, old=None, new=None, title="", detail="", category="node"):
        ref = new if new is not None else old
        ch = {
            "id": len(self.changes),
            "kind": kind,
            "category": category,
            "title": title,
            "detail": detail,
            "path": " › ".join(ref.get("_path", [])) if ref else "",
            "old_uid": old["uid"] if old is not None else None,
            "new_uid": new["uid"] if new is not None else None,
            "old_reveal": old.get("_reveal") if old is not None else None,
            "new_reveal": new.get("_reveal") if new is not None else None,
        }
        self.changes.append(ch)
        for x in (old, new):
            if x is not None:
                x.setdefault("chg", []).append(ch["id"])
        return ch

    def _label(self, n):
        if n["kind"] == "variable":
            return "%s variable “%s”%s" % ("Local" if n.get("local") else "Global", n["name"],
                                        "" if n.get("local") else " (%s)" % n.get("owner", ""))
        kinds = {"subvi": "SubVI", "prim": "Primitive", "structure": "Structure", "const": "Constant",
                 "terminal": "Terminal", "node": "Node"}
        return "%s “%s”" % (kinds.get(n["kind"], "Node"), n["name"])

    def _expected_shift(self, o, n):
        """How much an item is expected to move together with its enclosing structure (not 'moved' if its relative position is unchanged)."""
        po = o.get("_parent", "root")
        if po == "root":
            return self.dx, self.dy
        suid = po.split("#")[0]
        nu = self.pairs.get(suid)
        if nu is None:
            return self.dx, self.dy
        so, sn = self.on[suid], self.nn[nu]
        return sn["x"] - so["x"], sn["y"] - so["y"]

    def _classify_nodes(self):
        pid = 0
        for ou, nu in self.pairs.items():
            pid += 1
            o, n = self.on[ou], self.nn[nu]
            o["pid"] = n["pid"] = "p%d" % pid
            reasons = []
            rules = []     # one rule key per reason
            sub = o["kind"] == "subvi" and n["kind"] == "subvi"
            td = n.get("td") or o.get("td")
            td_reason = None
            if o["kind"] == "const" and (o.get("raw") or "") != (n.get("raw") or ""):
                ov, nv = o.get("value"), n.get("value")
                if td and _td_value_kept(o, n):
                    td_reason = TD_KEPT % td
                    reasons.append(td_reason)
                elif ov == nv:  # same display text but different raw data (e.g. cluster contents)
                    reasons.append("value changed" + (" (typedef “%s” changed too)" % td if td else ""))
                else:
                    reasons.append("value %s → %s" % (ov, nv) + (" (typedef “%s” changed too)" % td if td else ""))
                rules.append("typedef" if td_reason else "const_value")
            elif o["kind"] == "variable" and (o["name"] != n["name"] or o.get("owner") != n.get("owner")):
                reasons.append("“%s” → “%s”%s" % (o["name"], n["name"],
                               "" if o.get("owner") == n.get("owner") else " (%s → %s)" % (o.get("owner"), n.get("owner"))))
                rules.append("renamed")
            elif o["name"] != n["name"]:
                reasons.append("“%s” → “%s”" % (o["name"], n["name"]))
                rules.append("subvi_replace" if sub else "renamed")
            if len(o["terms"]) != len(n["terms"]):
                reasons.append("terminal count %d → %d" % (len(o["terms"]), len(n["terms"])))
                rules.append("subvi_update" if sub else "node_terms")
            ofr = [f["name"] for f in o.get("frames", [])]
            nfr = [f["name"] for f in n.get("frames", [])]
            if ofr != nfr:
                added = [f for f in nfr if f not in ofr]
                removed = [f for f in ofr if f not in nfr]
                parts = []
                if added:
                    parts.append("frame added: " + ", ".join(added))
                if removed:
                    parts.append("frame removed: " + ", ".join(removed))
                if not parts:
                    parts.append("frame order changed")
                reasons.append("; ".join(parts))
                rules.append("frames")
            if o.get("ctype") != n.get("ctype") and (o.get("ctype") or n.get("ctype")):
                reasons.append("type %s → %s" % (o.get("ctype"), n.get("ctype")))
                rules.append("subvi_update" if sub else "node_setting")
            if not reasons and o.get("chash") and n.get("chash") and o["chash"] != n["chash"] and o["kind"] not in ("const", "terminal"):
                reasons.append("setting/property changed")
                rules.append("subvi_update" if sub else "node_setting")
            if o["kind"] == "variable" and reasons == ["setting/property changed"]:
                # the variable node was refreshed because its global VI (or the control's typedef) changed
                td_reason = VAR_REFRESHED % (o.get("owner") or o["name"]) if not o.get("local") else \
                    "the type of “%s” changed" % o["name"]
                reasons = [td_reason]
                rules = ["typedef"]
            if o["kind"] == "variable" and o.get("read") != n.get("read"):
                reasons.append("read → write" if o.get("read") else "write → read")
                rules.append("io_mode")
            if o.get("io") != n.get("io") and o["kind"] == "terminal":
                reasons.append("%s → %s" % (o.get("io"), n.get("io")))
                rules.append("io_mode")
            ex, ey = self._expected_shift(o, n)
            moved = abs(o["x"] + ex - n["x"]) > MOVE_TOLERANCE or abs(o["y"] + ey - n["y"]) > MOVE_TOLERANCE
            resized = (o["w"] != n["w"] or o["h"] != n["h"]) and o["kind"] == "structure"
            if o["_parent"] != "root" and self._parent_pair(o["_parent"]) != n["_parent"]:
                reasons.append("moved to another structure/frame")
                rules.append("reframed")
            if reasons and td_reason and reasons == [td_reason]:
                # only a typedef / global it uses changed: its own status, drawn in a faint color
                o["st"] = n["st"] = "typedef"
                ch = self._add_change("modified", old=o, new=n, title=self._label(n) + " — typedef/global updated",
                                      detail=td_reason)
                ch["cat"] = "typedef"
                ch["td"] = td or o.get("owner")
                ch["rules"] = ["typedef"]
            elif reasons:
                reframe = reasons == ["moved to another structure/frame"]
                o["st"] = n["st"] = "reframed" if reframe else "modified"
                auto = reasons == ["setting/property changed"] and (o.get("cls") in AUTO_CLASSES or n.get("cls") in AUTO_CLASSES)
                ch = self._add_change("modified", old=o, new=n,
                                      title=self._label(n) + (" moved into another structure/frame" if reframe else " modified"),
                                      detail="" if reframe else
                                      "internal setting changed (may have been regenerated by LabVIEW)" if auto else "; ".join(reasons))
                ch["rules"] = ["auto"] if auto else sorted(set(rules) - {"typedef"}) or ["node_setting"]
                if reframe:
                    ch["reframe"] = True
                if auto:
                    ch["cat"] = "auto"
                    o["auto"] = n["auto"] = True
            elif moved or resized or (o.get("fmt") and n.get("fmt") and o["fmt"] != n["fmt"]):
                o["st"] = n["st"] = "moved"
                if moved or resized:
                    title = self._label(n) + (" resized" if resized and not moved else " moved")
                    detail = "position (%d,%d) → (%d,%d)" % (o["x"], o["y"], n["x"], n["y"])
                else:
                    title = self._label(n) + " text format changed"
                    detail = "text/label display (justification, font, style or label visibility)"
                self._add_change("moved", old=o, new=n, title=title, detail=detail, category="cosmetic")["rules"] = ["bd_layout"]
            else:
                o["st"] = n["st"] = "same"
        for ou, o in self.on.items():
            if ou not in self.pairs:
                o["st"] = "removed"
                self._add_change("removed", old=o, title=self._label(o) + " removed")["rules"] = ["node_removed"]
        for nu, n in self.nn.items():
            if nu not in self.rpairs:
                n["st"] = "added"
                self._add_change("added", new=n, title=self._label(n) + " added")["rules"] = ["node_added"]

    def _wire_key(self, w, side):
        nodes = self.on if side == "old" else self.nn
        parts = []
        for e in w["ends"]:
            k = e["key"].split(":")
            n = nodes.get(e["node"])
            pid = n.get("pid") if n is not None else None
            if pid is None:
                pid = side + ":" + e["node"]
            parts.append(":".join([pid] + k[1:]))
        return tuple(sorted(parts))

    def _diff_wires(self, ob, nb):
        old_w = {}
        for w in _all_wires(ob):
            old_w.setdefault(self._wire_key(w, "old"), []).append(w)
        new_w = {}
        for w in _all_wires(nb):
            new_w.setdefault(self._wire_key(w, "new"), []).append(w)
        wid = 0
        for k, ws in old_w.items():
            nws = new_w.get(k, [])
            for i, w in enumerate(ws):
                if i < len(nws):
                    wid += 1
                    w["pid"] = nws[i]["pid"] = "w%d" % wid
                    w["st"] = nws[i]["st"] = "same"
                    if w["cat"] != nws[i]["cat"] or w["arr"] != nws[i]["arr"]:
                        w["st"] = nws[i]["st"] = "modified"
                        ch = self._add_change("wire_modified", old=self._wire_ref(w), new=self._wire_ref(nws[i]),
                                              title="Wire data type changed",
                                              detail="%s%s → %s%s" % (w["cat"], "[]" if w["arr"] else "",
                                                                       nws[i]["cat"], "[]" if nws[i]["arr"] else ""),
                                              category="wire")
                        ch["_wold"], ch["_wnew"] = w, nws[i]
                        ch["rules"] = ["wire_type"]
                else:
                    w["st"] = "removed"
                    ch = self._add_change("wire_removed", old=self._wire_ref(w), title="Wire removed",
                                          detail=self._wire_desc(w, "old"), category="wire")
                    ch["_wold"] = w
                    ch["rules"] = ["wire_removed"]
        for k, ws in new_w.items():
            ows = old_w.get(k, [])
            for i, w in enumerate(ws):
                if i >= len(ows):
                    w["st"] = "added"
                    ch = self._add_change("wire_added", new=self._wire_ref(w), title="Wire added",
                                          detail=self._wire_desc(w, "new"), category="wire")
                    ch["_wnew"] = w
                    ch["rules"] = ["wire_added"]

    def _wire_ref(self, w):
        w.setdefault("uid", "w?")
        return w

    def _wire_desc(self, w, side):
        nodes = self.on if side == "old" else self.nn
        names_ = []
        for e in w["ends"]:
            n = nodes.get(e["node"])
            nm = n["name"] if n else "?"
            if nm not in names_:
                names_.append(nm)
        return " ↔ ".join(names_[:4]) + (" …" if len(names_) > 4 else "")

    def _diff_notes(self, ob, nb):
        on = list(_all_notes(ob))
        nn = list(_all_notes(nb))
        used = set()
        for o in on:
            match = None
            for i, n in enumerate(nn):
                if i in used:
                    continue
                if n["text"] == o["text"]:
                    match = i
                    break
            if match is None:
                o["st"] = "removed"
                self._add_change("note_removed", old=o, title="Comment removed", detail=o["text"][:140], category="note")["rules"] = ["notes"]
            else:
                used.add(match)
                o["st"] = nn[match]["st"] = "same"
        for i, n in enumerate(nn):
            if i not in used:
                n["st"] = "added"
                self._add_change("note_added", new=n, title="Comment added", detail=n["text"][:140], category="note")["rules"] = ["notes"]

    def _apply_accept(self):
        """Changes whose every rule the user does not count as a change: status "minor" (drawn faintly)."""
        if not self.accept:
            return
        for ch in self.changes:
            rules = ch.get("rules") or []
            if not rules or ch.get("cat") == "typedef" or not set(rules) <= self.accept:
                continue
            ch["cat"] = "minor"
            ch["accepted"] = rules
            for side in ("old", "new"):
                ref = ch.get("_w" + side) if ch["kind"].startswith("wire") else \
                    (self.on if side == "old" else self.nn).get(ch.get(side + "_uid"))
                if ref is None and ch["kind"].startswith("wire"):
                    uid = ch.get(side + "_uid")
                    dg = self.od if side == "old" else self.nd
                    ref = next((w for d in dg.values() for w in d["wires"] if w.get("uid") == uid), None)
                if ref is not None and ref.get("st") not in (None, "same"):
                    ref["st"] = "minor"

    def _mark_frames(self, diagram):
        """Number of changes inside each structure frame (for the badge). Returns: subtotal."""
        total = 0
        for n in diagram["nodes"]:
            if n.get("st") not in (None, "same", "moved", "minor"):
                total += 1
            for f in n.get("frames", []):
                c = self._mark_frames(f["diagram"])
                f["changes"] = c
                total += c
        for w in diagram["wires"]:
            if w.get("st") in ("added", "removed", "modified"):
                total += 1
        for t in diagram["notes"]:
            if t.get("st") in ("added", "removed"):
                total += 1
        return total

    # ------------------------------------------------------------------
    def _result(self):
        res = {
            "changes": self.changes,
            "shift": [self.dx, self.dy],
            "fp": diff_fp(self.old.get("fp", []), self.new.get("fp", [])),
            "deps": diff_deps(self.old.get("deps", []), self.new.get("deps", [])),
            "props": diff_props(self.old.get("meta", {}).get("props", {}), self.new.get("meta", {}).get("props", {})),
        }
        counts = {"added": 0, "removed": 0, "modified": 0, "moved": 0, "wire_added": 0, "wire_removed": 0,
                  "wire_modified": 0, "note_added": 0, "note_removed": 0}
        counts["auto"] = 0
        counts["typedef"] = 0
        counts["minor"] = 0
        for c in self.changes:
            if c.get("cat") == "minor":
                counts["minor"] += 1
            elif c.get("cat") == "auto":
                counts["auto"] += 1
            elif c.get("cat") == "typedef":
                counts["typedef"] += 1
            else:
                counts[c["kind"]] = counts.get(c["kind"], 0) + 1
        res["counts"] = counts
        res["functional"] = sum(v for k, v in counts.items() if k not in ("moved", "auto", "typedef", "minor")) + \
            len(res["fp"]) + len(res["deps"]) + len(res["props"])
        # drop internal fields such as _path/_reveal (JSON size)
        for coll in (self.on, self.nn):
            for n in coll.values():
                n.pop("_parent", None)
                n["path"] = " › ".join(n.pop("_path", []))
                n.pop("_reveal", None)
        for b in (self.old.get("bd"), self.new.get("bd")):
            if b:
                for w in _all_wires(b):
                    w.pop("_parent", None); w.pop("_path", None); w.pop("_reveal", None)
                for t in _all_notes(b):
                    t.pop("_parent", None); t.pop("_path", None); t.pop("_reveal", None)
        return res


def diff_fp(old, new):
    out = []
    ob = {c["name"]: c for c in old}
    nb = {c["name"]: c for c in new}
    for name, c in ob.items():
        if name not in nb:
            out.append({"kind": "removed", "name": name, "detail": "%s %s removed" % (c.get("ctype_name") or "", _io(c))})
        else:
            n = nb[name]
            diffs = []
            if c.get("ctype") != n.get("ctype"):
                diffs.append("type %s → %s" % (c.get("ctype_name"), n.get("ctype_name")))
            if c.get("io") != n.get("io"):
                diffs.append("%s → %s" % (_io(c), _io(n)))
            if sorted(c.get("keys") or []) != sorted(n.get("keys") or []):
                diffs.append("keyboard shortcut %s → %s" % (", ".join(c.get("keys") or []) or "none",
                                                          ", ".join(n.get("keys") or []) or "none"))
            if not diffs and c.get("chash") and n.get("chash") and c["chash"] != n["chash"]:
                diffs.append("typedef contents updated" if (c.get("typedef") or n.get("typedef")) else "appearance/property changed")
            if diffs:
                out.append({"kind": "modified", "name": name, "detail": "; ".join(diffs)})
    for name, n in nb.items():
        if name not in ob:
            out.append({"kind": "added", "name": name, "detail": "%s %s added" % (n.get("ctype_name") or "", _io(n))})
    return out


def _io(c):
    return {"control": "control", "indicator": "indicator"}.get(c.get("io"), "")


def diff_deps(old, new):
    out = []
    os_ = {(d["kind"], d["name"]) for d in old}
    ns_ = {(d["kind"], d["name"]) for d in new}
    for k in sorted(os_ - ns_):
        out.append({"kind": "removed", "name": k[1], "link": k[0]})
    for k in sorted(ns_ - os_):
        out.append({"kind": "added", "name": k[1], "link": k[0]})
    return out


IMPORTANT_PROPS = {
    "Execution.IsReentrant": "Reentrant",
    "Execution.Priority": "Priority",
    "Execution.PrefExecSyst": "Preferred execution system",
    "Execution.IsSubroutine": "Subroutine",
    "Execution.RunOnOpen": "Run when opened",
    "Execution.ShowFPOnCall": "Show front panel when called",
    "Execution.CloseAfterCall": "Close afterwards if originally closed",
    "Execution.DebugCapable": "Allow debugging",
    "Execution2.InlineIfPossible": "Inline",
    "Execution2.DefaultErrorHandling": "Automatic error handling",
    "Execution.PooledReentrancy": "Shared clone reentrancy",
    "Library.Protected": "Password protection",
    "FrontPanel.ShowScrollBar": "Scroll bars",
    "FrontPanel.ShowTitleBar": "Title bar",
    "FrontPanel.ShowMenuBar": "Menu bar",
    "FrontPanel.AutoCenter": "Auto center",
}

VOLATILE_PROPS = {"Execution.State", "Execution.BadSignal", "Execution.BadNode", "Execution.BadSubVILink",
                  "Execution.BadSubVI", "Execution.BadCompile", "Execution.CtlChanged",
                  "Execution2.UndoRedoChangedNoTypes", "Execution2.TaggedAndNotEdited",
                  "Execution2.RecalcFPDSOs", "Execution2.UndoRedoInProgress", "Execution.HasSetBP",
                  "Execution2.TransactionFailing", "Execution.BadDDO", "Execution.PropTypesIssues",
                  "Execution2.InlinableDiagram", "Execution.BrokenPolyVI", "Execution.HasInsaneItems",
                  "Execution.LibIssuesNoRun"}


def diff_props(old, new):
    out = []
    for k in sorted(set(old) | set(new)):
        if k in VOLATILE_PROPS:
            continue
        if old.get(k) != new.get(k):
            out.append({"key": k, "label": IMPORTANT_PROPS.get(k, k), "old": old.get(k), "new": new.get(k),
                        "important": k in IMPORTANT_PROPS})
    return out


def diff_models(old, new, accept=frozenset()):
    res = Differ(old, new, accept).run()
    res["verdict"] = file_verdict(old, new, res, accept)
    res["accept"] = sorted(accept or ())
    return res


# ---------------------------------------------------------------------------
# File-level verdict: which part of the VI changed?
#   functional : logic/interface changed (node, wire, constant, control, connector pane, dependency, important property)
#   layout     : visual/layout change or a change whose details cannot be extracted (placement, size, icon, default value…)
#   saved      : only re-saved / recompiled (revision, compiled code, internal numbers)
# ---------------------------------------------------------------------------
# "typedef": only typedefs / globals the VI uses changed (LabVIEW updated and re-saved the VI) — below layout
# "minor": only differences the user does not count as changes (see ACCEPT_RULES)
LEVELS = {"saved": 0, "minor": 0.3, "typedef": 0.5, "layout": 1, "functional": 2}
GEOM_TOLERANCE = 2  # pixels: font metric differences between computers


def compare_heap(a, b):
    if a is None and b is None:
        return "same"
    if a is None or b is None:
        return "content"
    if a["strict"] == b["strict"]:
        return "same"
    if a["loose"] == b["loose"]:
        ga, gb = a.get("geom") or [], b.get("geom") or []
        if a.get("route") == b.get("route") and len(ga) == len(gb) and \
                all(abs(x - y) <= GEOM_TOLERANCE for x, y in zip(ga, gb)):
            return "same"
        return "layout"
    return "content"


def _diff_conpane(a, b):
    if not a and not b:
        return []
    a = a or {"pattern": None, "terms": {}}
    b = b or {"pattern": None, "terms": {}}
    out = []
    if a.get("pattern") != b.get("pattern"):
        out.append("pattern changed")
    ta, tb = a.get("terms", {}), b.get("terms", {})
    for k in sorted(set(ta) | set(tb), key=lambda x: int(x) if str(x).isdigit() else 0):
        if ta.get(k) != tb.get(k):
            if k not in ta:
                out.append("terminal %s ← “%s” connected" % (k, tb[k]))
            elif k not in tb:
                out.append("terminal %s “%s” disconnected" % (k, ta[k]))
            else:
                out.append("terminal %s: “%s” → “%s”" % (k, ta[k], tb[k]))
    return out


def file_verdict(old, new, res, accept=frozenset()):
    """Builds a per-section verdict from two VI models and the diff result.
    accept: rule keys (ACCEPT_RULES) not counted as changes; their parts get the level "minor"."""
    parts = []

    def add(key, label, level, detail=""):
        parts.append({"key": key, "label": label, "level": level, "detail": detail})

    for side, m in (("old", old), ("new", new)):
        if m.get("error"):
            add("error", "Could not be parsed (%s version)" % side, "functional", m["error"])
    if old.get("empty") and not new.get("empty"):
        add("file", "New file", "functional")
    if new.get("empty") and not old.get("empty"):
        add("file", "File deleted", "functional")

    c = res["counts"]
    fo, fn = old.get("fingerprint") or {}, new.get("fingerprint") or {}
    both = not old.get("empty") and not new.get("empty") and not old.get("error") and not new.get("error")

    if both:
        # Block diagram
        nodes = c.get("added", 0) + c.get("removed", 0) + c.get("modified", 0)
        wires = c.get("wire_added", 0) + c.get("wire_removed", 0) + c.get("wire_modified", 0)
        notes = c.get("note_added", 0) + c.get("note_removed", 0)
        bits = []
        if c.get("added"):
            bits.append("+%d" % c["added"])
        if c.get("removed"):
            bits.append("−%d" % c["removed"])
        if c.get("modified"):
            bits.append("~%d" % c["modified"])
        if wires:
            bits.append("%d wire(s)" % wires)
        heap_bd = compare_heap(fo.get("bd"), fn.get("bd"))
        if nodes or wires:
            names_ = [ch["title"].split(" modified")[0] for ch in res["changes"] if ch["kind"] == "modified" and ch.get("cat") not in ("auto", "typedef", "minor")][:3]
            add("bd", "Block diagram", "functional", " ".join(bits) + ((" · " + ", ".join(names_)) if names_ else ""))
        if notes:
            add("bd_notes", "Block diagram comments", "layout", "%d comment(s) added/removed" % notes)
        if c.get("moved"):
            moved_names = [ch["title"].replace(" moved", "").replace(" resized", "").replace(" text format changed", " (text format)")
                           for ch in res["changes"] if ch["kind"] == "moved"]
            add("bd_layout", "Block diagram layout", "layout", "%d item(s) moved/resized/reformatted: %s%s" % (
                c["moved"], ", ".join(moved_names[:4]), " …" if len(moved_names) > 4 else ""))
        elif heap_bd == "layout":
            add("bd_layout", "Block diagram layout", "layout", "placement / wire routing / colors")
        if c.get("typedef"):
            tn, seen = [], set()
            for ch in res["changes"]:
                if ch.get("cat") == "typedef":
                    nm = ch["title"].replace(" — typedef/global updated", "")
                    if nm not in seen:
                        seen.add(nm)
                        tn.append(nm + ((" (%s)" % ch["td"]) if ch.get("td") and ch["td"] not in nm else ""))
            add("bd_typedef", "Typedef/global used on the block diagram changed", "typedef",
                "%d item(s), value unchanged: %s%s" % (c["typedef"], ", ".join(tn[:4]), " …" if len(tn) > 4 else ""))
        if c.get("minor"):
            add("bd_minor", "Block diagram differences not counted as changes", "minor", _minor_detail(res["changes"]))
        if c.get("auto"):
            an = []
            for ch in res["changes"]:
                if ch.get("cat") == "auto":
                    nm = ch["title"].replace(" modified", "")
                    if nm not in an:
                        an.append(nm)
            add("bd_auto", AUTO_LABEL, "layout", "%d item(s): %s%s" % (c["auto"], ", ".join(an[:4]), " …" if len(an) > 4 else ""))
        if not (nodes or wires or notes or c.get("moved") or c.get("auto") or c.get("typedef") or c.get("minor")) \
                and heap_bd == "content":
            add("bd_other", "Block diagram (details not available)", "layout",
                "e.g. property node item, label visibility, structure setting")

        # Front panel
        heap_fp = compare_heap(fo.get("fp"), fn.get("fp"))
        fp_td = [x for x in res["fp"] if x["kind"] == "modified" and x["detail"] == "typedef contents updated"]
        fp_look = [x for x in res["fp"] if x["kind"] == "modified" and x["detail"] == "appearance/property changed"]
        fp_func = [x for x in res["fp"] if x not in fp_td and x not in fp_look]
        if fp_td:
            add("fp_typedef", "Typedef used on the front panel changed", "typedef",
                ", ".join("“%s”" % x["name"] for x in fp_td[:5]) + (" …" if len(fp_td) > 5 else "") +
                " — the typedef (.ctl) changed, LabVIEW updated the VI")
        if fp_func:
            add("fp", "Front panel controls", "functional",
                ", ".join("“%s”: %s" % (x["name"], x["detail"]) for x in fp_func[:4]) + (" …" if len(fp_func) > 4 else ""))
        if fp_look:
            add("fp_look", "Front panel appearance", "layout", ", ".join("“%s”" % x["name"] for x in fp_look[:5]))
        # moved/resized controls
        ob = {x["name"]: x.get("bounds") for x in old.get("fp", [])}
        td_names = {x["name"] for x in fp_td}
        moved_fp = []
        for x in new.get("fp", []):
            if x["name"] in td_names:
                continue      # a typedef control that grew/shrank with its typedef: part of the typedef update
            a, b = ob.get(x["name"]), x.get("bounds")
            if a and b and any(abs(p - q) > GEOM_TOLERANCE for p, q in zip(a, b)):
                moved_fp.append(x["name"])
        if moved_fp:
            add("fp_layout", "Front panel layout", "layout", "moved/resized: " +
                ", ".join("“%s”" % n for n in moved_fp[:6]) + (" …" if len(moved_fp) > 6 else ""))
        elif heap_fp == "layout" and not res["fp"]:
            add("fp_layout", "Front panel layout", "layout", "placement / decorations")
        if heap_fp == "content" and not res["fp"]:
            add("fp_other", "Front panel (control properties/appearance)", "layout")

        cp = _diff_conpane(old.get("conpane"), new.get("conpane"))
        if cp:
            add("conpane", "Connector pane", "functional", "; ".join(cp))
        if res["deps"]:
            add("deps", "Dependencies", "functional",
                ", ".join(("+" if d["kind"] == "added" else "−") + d["name"] for d in res["deps"][:4]) +
                (" …" if len(res["deps"]) > 4 else ""))
        imp = [p for p in res["props"] if p["important"]]
        other = [p for p in res["props"] if not p["important"]]
        if imp:
            add("props", "VI properties", "functional", ", ".join("%s: %s→%s" % (p["label"], p["old"], p["new"]) for p in imp))
        if other:
            add("props_other", "Other VI settings", "layout", ", ".join(p["key"].split(".")[-1] for p in other[:5]))
        if fo.get("data") and fn.get("data") and fo["data"] != fn["data"]:
            if any(p["level"] == "typedef" for p in parts):
                add("data", "Default values / data space", "typedef", "follows the typedef update")
            else:
                add("data", "Default values / data space", "layout")
        if fo.get("icon") != fn.get("icon") and fo.get("icon") and fn.get("icon"):
            add("icon", "Icon", "layout")
        mo, mn = old.get("meta", {}), new.get("meta", {})
        if (mo.get("description") or "") != (mn.get("description") or ""):
            add("desc", "VI description", "layout")
        if mo.get("lv_version") != mn.get("lv_version"):
            add("version", "LabVIEW version", "saved", "%s → %s" % (mo.get("lv_version"), mn.get("lv_version")))

    _accept_parts(parts, accept, c)
    for p in parts:
        p["cat"] = "typedef" if p["level"] == "typedef" else "minor" if p["level"] == "minor" \
            else PART_CATEGORY.get(p["key"], "other")
    return _finish_verdict(parts)


def _minor_detail(changes):
    n = {}
    for ch in changes:
        if ch.get("cat") == "minor":
            for r in ch.get("accepted") or []:
                n[r] = n.get(r, 0) + 1
    return "; ".join("%s: %d" % (RULE_LABEL.get(r, r).split(" (")[0], k) for r, k in sorted(n.items(), key=lambda t: -t[1]))


# parts that follow other differences (LabVIEW re-saves the data space and reroutes wires when a subVI or a typedef
# changes): when every other difference is accepted, these are not counted either
_FOLLOWERS = {"data", "bd_other", "bd_layout"}


def _accept_parts(parts, accept, counts):
    if not accept:
        return
    for p in parts:
        r = PART_RULE.get(p["key"])
        if r and r in accept and p["level"] in ("functional", "layout"):
            p["level"] = "minor"
            p["detail"] = (p.get("detail") or "") + (" — " if p.get("detail") else "") + "not counted as a change"
    # what is left after the accepted ones: if only followers remain and something was accepted, they follow it
    if not (counts.get("minor") or any(p["level"] == "minor" for p in parts)):
        return
    real = [p for p in parts if p["level"] in ("functional", "layout") and p["key"] != "version"]
    if real and all(p["key"] in _FOLLOWERS and not (p["key"] == "bd_layout" and counts.get("moved")) for p in real):
        for p in real:
            p["level"] = "minor"
            p["detail"] = "follows the differences not counted as changes"


def _finish_verdict(parts):
    level = max([LEVELS[p["level"]] for p in parts] + [0])
    name = {v: k for k, v in LEVELS.items()}[level]
    cats = sorted({p["cat"] for p in parts if p["key"] != "version"})
    return {"level": name, "parts": parts, "cats": cats or (["saved"] if name == "saved" else [])}


def note_groups(verdict, changes):
    """Adds to the block diagram part how many changes remain when related ones are joined (for the summaries)."""
    if not verdict:
        return verdict
    real = [c for c in changes if c["kind"] != "moved" and c.get("cat") != "minor"]
    groups = {c.get("group", c["id"]) for c in real}
    if not real or len(groups) == len(real):
        return verdict
    import copy
    v = copy.deepcopy(verdict)
    for p in v["parts"]:
        if p["key"] == "bd":
            p["detail"] = "%d change(s), related ones joined (%d items) · %s" % (len(groups), len(real), p.get("detail") or "")
    return v


def apply_typedef_priority(verdict, mode):
    """mode 'low' (default): typedef/global updates stay a level of their own, below layout.
    mode 'normal': they count like before — block diagram items as content, front panel / data as layout.
    Returns a new verdict (the cached one is not changed)."""
    if mode != "normal" or not verdict:
        return verdict
    import copy
    parts = copy.deepcopy(verdict.get("parts") or [])
    for p in parts:
        if p["level"] == "typedef":
            p["level"] = "functional" if p["key"] == "bd_typedef" else "layout"
    return _finish_verdict(parts)


# Categories for user filters
CATEGORIES = [
    ("logic", "Block diagram logic"),
    ("typedef", "Typedef / global updates"),
    ("minor", "Differences not counted as changes"),
    ("bd_layout", "Block diagram layout"),
    ("fp", "Front panel"),
    ("auto", "Timed Loop / XNode internal settings"),
    ("other", "Other (icon, description, settings)"),
    ("saved", "Re-saved only"),
]
PART_CATEGORY = {
    "bd": "logic", "conpane": "logic", "deps": "logic", "props": "logic", "file": "logic", "error": "logic",
    "bd_layout": "bd_layout", "bd_other": "bd_layout", "bd_notes": "bd_layout",
    "fp": "fp", "fp_look": "fp", "fp_other": "fp", "fp_layout": "fp", "fp_typedef": "typedef", "bd_typedef": "typedef", "data": "fp",
    "bd_auto": "auto",
    "icon": "other", "desc": "other", "props_other": "other", "version": "other",
}
# Block diagram change kind -> category
CHANGE_CATEGORY = {"added": "logic", "removed": "logic", "modified": "logic", "wire_added": "logic",
                   "wire_removed": "logic", "wire_modified": "logic", "note_added": "bd_layout",
                   "note_removed": "bd_layout", "moved": "bd_layout"}

