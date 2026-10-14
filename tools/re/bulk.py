import os as _os, sys as _sys; _sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "..")))
import sys, glob, collections
from concurrent.futures import ProcessPoolExecutor

from engine import vi_parser
def walk(d):
    for n in d.get("nodes", []):
        yield n
        for f in n.get("frames") or []: yield from walk(f["diagram"])
def one(f):
    try:
        m = vi_parser.parse_vi(f)
    except Exception as e:
        return ("EXC", f, repr(e)), collections.Counter()
    if m.get("error"):
        return ("ERR", f, m["error"]), collections.Counter()
    c = collections.Counter()
    for n in walk(m["bd"] or {}):
        c["nodes"] += 1
        if n["cls"] in ("propNode", "invokeNode"): c["refnodes"] += 1; c["refnodes_named"] += ":" in n["name"] and "(no property)" not in n["name"]
        if n["cls"] == "eventStruct":
            for fr in n["frames"]:
                c["evframes"] += 1
                c["ev_certain"] += "(#" not in fr["name"] and "event #" not in fr["name"]
                c["ev_inferred"] += "(#" in fr["name"]
                c["ev_raw"] += "event #" in fr["name"]
                c["ev_ctl_unknown"] += "<control>" in fr["name"]
        if n["kind"] == "const" and n.get("vtype") == "Cluster":
            c["clusters"] += 1; c["clusters_read"] += (n.get("value") or "").startswith("{") and n["value"] != "{default}"
            c["clusters_default"] += n.get("value") == "{default}"
    return None, c
if __name__ == "__main__":
    files = sorted(set(glob.glob(sys.argv[1] + "/**/*.vi", recursive=True)))
    tot = collections.Counter(); bad = []
    with ProcessPoolExecutor(8) as ex:
        for b, c in ex.map(one, files):
            tot.update(c)
            if b: bad.append(b)
    print(len(files), "files;", dict(tot))
    print("problems:", len(bad))
    for b in bad[:10]: print("  ", b[0], b[1][-60:], b[2][:120])
