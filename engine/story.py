"""
Wire changes told in words, by the labels of what they connect.

A wire in the VI does not say which end is the source. The direction is taken from what is at the ends:
- source: a control terminal, a constant, a variable in read mode, the output side of a node
- destination: an indicator terminal, a variable in write mode, the input side of a node
  (subVIs / primitives / other nodes: a terminal on the right half of the node is an output, on the left half an input)
- structure tunnels / shift registers: the wire is followed through the tunnel (the inner and the outer wire end at
  about the same point of the structure border)

Each sentence is stored as a small dict, so it can be written in any language:
  {"k": "assign" | "connect" | "write" | "input" | "given" | "chain", "op": "added" | "removed",
   "src": end, "dst": end}       end = {"role", "name", "value"?}
roles: control, indicator, local, global, const, subvi, prim, node, structure
"""

ROLE_OF_KIND = {"subvi": "subvi", "prim": "prim", "node": "node", "structure": "structure"}


def end_desc(n):
    k = n.get("kind")
    if k == "terminal":
        return {"role": "indicator" if n.get("io") == "indicator" else "control", "name": n["name"]}
    if k == "variable":
        return {"role": "local" if n.get("local") else "global", "name": n["name"]}
    if k == "const":
        v = str(n.get("value") or "")
        return {"role": "const", "name": n["name"], "value": v if len(v) <= 40 else v[:39] + "…"}
    return {"role": ROLE_OF_KIND.get(k, "node"), "name": n["name"]}


def direction(n, e):
    """'out', 'in', 'via' (structure: follow the wire through) or '?' (an end near the middle of a node, where the
    side does not tell; decided from the other ends) for one wire end."""
    k = n.get("kind")
    if k == "const":
        return "out"
    if k == "terminal":
        return "in" if n.get("io") == "indicator" else "out"
    if k == "variable":
        return "out" if n.get("read", True) else "in"
    if k == "structure":
        return "via"
    mid = n["x"] + n["w"] / 2.0
    x = e.get("x", 0)
    if abs(x - mid) <= max(2.0, n["w"] / 8.0):
        return "?"
    return "out" if x > mid else "in"


class Tracer:
    """Real endpoints of a wire on one side (old or new model), following wires through structure tunnels."""

    def __init__(self, nodes, wires):
        self.nodes = nodes
        self.by_struct = {}
        for w in wires:
            for e in w["ends"]:
                n = nodes.get(e["node"])
                if n is not None and n.get("kind") == "structure":
                    self.by_struct.setdefault(e["node"], []).append((w, e))

    def endpoints(self, w, seen=None, depth=0):
        seen = seen if seen is not None else set()
        seen.add(w["uid"])
        out = []
        for e in w["ends"]:
            n = self.nodes.get(e["node"])
            if n is None:
                continue
            d = direction(n, e)
            if d != "via":
                out.append((d, n))
                continue
            found = []
            if depth < 4:
                # the same tunnel / shift register seen from the other side of the structure border
                for w2, e2 in self.by_struct.get(e["node"], []):
                    if w2["uid"] in seen:
                        continue
                    if abs(e2.get("x", 0) - e.get("x", 0)) <= 16 and abs(e2.get("y", 0) - e.get("y", 0)) <= 16:
                        found.extend(self.endpoints(w2, seen, depth + 1))
            # nothing on the other side (case selector, a tunnel left unwired): the structure itself is the end
            out.extend(found or [("?", n)])
        return out


def resolve(endpoints):
    """Gives the undecided ends ('?') the direction the wire needs: a wire has a source and a destination."""
    has_out = any(d == "out" for d, n in endpoints)
    has_in = any(d == "in" for d, n in endpoints)
    und = [(d, n) for d, n in endpoints if d == "?"]
    if not und:
        return endpoints
    if has_out:
        fill = {id(n): "in" for d, n in und}
    elif has_in:
        fill = {id(n): "out" for d, n in und}
    else:
        # all undecided: data flows left to right in a diagram
        und.sort(key=lambda t: t[1].get("x", 0))
        fill = {id(n): "in" for d, n in und}
        fill[id(und[0][1])] = "out"
    return [(fill.get(id(n), "in") if d == "?" else d, n) for d, n in endpoints]


def sentences(endpoints, op):
    """Sentences for one wire from its endpoints [(direction, node)]."""
    endpoints = resolve(endpoints)
    srcs = [end_desc(n) for d, n in endpoints if d == "out"]
    dsts = [end_desc(n) for d, n in endpoints if d == "in"]
    # a structure border is only named when the wire ends there (nothing real on the other side)
    srcs = [e for e in srcs if e["role"] != "structure"] or srcs
    dsts = [e for e in dsts if e["role"] != "structure"] or dsts[:1]
    if not srcs or not dsts:
        return []
    src = srcs[0]
    out = []
    for dst in dsts[:4]:
        data_dst = dst["role"] in ("indicator", "local", "global", "control")
        if src["role"] == "const":
            k = "assign" if data_dst else "given"
        elif src["role"] in ("control", "local", "global"):
            k = "connect" if data_dst else "input"
        else:
            k = "write" if data_dst else "chain"
        out.append({"k": k, "op": op, "src": src, "dst": dst})
    return out


# ---------------------------------------------------------------- text
def _q(e):
    return "“%s”" % e["name"]


EN_NOUN = {"control": "control", "indicator": "indicator", "local": "local variable", "global": "global variable",
           "subvi": "subVI", "prim": "", "node": "", "const": "constant", "structure": ""}


def _en(it):
    s, d = it["src"], it["dst"]
    k = it["k"]
    if k == "assign":
        t = "%s assigned to %s" % (s.get("value") or _q(s), _q(d))
    elif k == "given":
        t = "%s given to %s" % (s.get("value") or _q(s), _q(d))
    elif k == "connect":
        t = "%s read and connected to %s" % (_q(s), _q(d))
    elif k == "input":
        t = "%s connected to %s" % (_q(s), _q(d))
    elif k == "write":
        t = "output of %s written to %s" % (_q(s), _q(d))
    else:
        t = "output of %s connected to %s" % (_q(s), _q(d))
    return {"removed": "no longer: ", "rerouted": "rerouted: "}.get(it["op"], "") + t


# Turkish: the noun after the name carries the case ending, so the name itself needs none
TR_ACC = {"control": "kontrolü", "indicator": "göstergesi", "local": "yerel değişkeni", "global": "global değişkeni",
          "subvi": "", "prim": "", "node": "", "const": "sabiti", "structure": "yapısı"}
TR_DAT = {"control": "kontrolüne", "indicator": "göstergesine", "local": "yerel değişkenine",
          "global": "global değişkenine", "subvi": "girişine", "prim": "girişine", "node": "girişine", "const": "sabitine",
           "structure": "yapısına"}


def _tr(it):
    s, d = it["src"], it["dst"]
    k = it["k"]
    dat = "%s %s" % (_q(d), TR_DAT[d["role"]])
    if k == "assign":
        t = "%s %s atandı" % (dat, s.get("value") or _q(s))
    elif k == "given":
        t = "%s değeri %s verildi" % (s.get("value") or _q(s), dat)
    elif k == "connect":
        t = "%s %s okunup %s bağlandı" % (_q(s), TR_ACC[s["role"]], dat)
    elif k == "input":
        t = "%s %s %s bağlandı" % (_q(s), TR_ACC[s["role"]], dat)
    elif k == "write":
        t = "%s çıkışı %s yazıldı" % (_q(s), dat)
    else:
        t = "%s çıkışı %s bağlandı" % (_q(s), dat)
    t = " ".join(t.split())
    return {"removed": "kaldırıldı: ", "rerouted": "yeniden bağlandı: "}.get(it["op"], "") + t


def render(it, lang="en"):
    return _tr(it) if lang == "tr" else _en(it)


def merge_ops(items):
    """The same connection removed and added again (e.g. moved into a new structure): one "rerouted" sentence."""
    key = lambda it: (it["k"], it["src"]["name"], it["src"].get("value"), it["dst"]["name"])
    ops = {}
    for it in items:
        ops.setdefault(key(it), set()).add(it["op"])
    out, seen = [], set()
    for it in items:
        k = key(it)
        if k in seen:
            continue
        seen.add(k)
        if ops[k] >= {"added", "removed"}:
            it = dict(it, op="rerouted")
        out.append(it)
    # what changed comes first, what was only rerouted last
    return sorted(out, key=lambda it: it["op"] == "rerouted")


def dedupe(items):
    seen, out = set(), []
    for it in items:
        key = (it["k"], it["op"], it["src"]["name"], it["src"].get("value"), it["dst"]["name"])
        if key not in seen:
            seen.add(key)
            out.append(it)
    return out
