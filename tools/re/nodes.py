import os as _os, sys as _sys; _sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "..")))
import sys, os, glob, tempfile, shutil, collections, json, re
from concurrent.futures import ProcessPoolExecutor
import xml.etree.ElementTree as ET

from engine import vi_parser

def one(f):
    out = []
    d = tempfile.mkdtemp()
    try:
        main, _ = vi_parser.extract_with_pylabview(f, d)
        bd = os.path.join(d, "vi_BDHb.xml")
        if not os.path.exists(bd): return out
        B = ET.parse(bd).getroot()
        byuid = {e.get("uid"): e for e in B.iter() if e.get("uid") and len(e)}
        for el in B.iter():
            c = el.get("class")
            if c in ("propNode", "invokeNode", "ctlRefConst", "callByRefNode"):
                kids = sorted({k.tag for k in el})
                props = [p.findtext("PropItemName") for p in el.iter("SL__arrayElement") if p.get("class") == "propItemInfo"]
                lab = vi_parser._first_text(el.find("label"))
                ddo = el.find("ddo")
                out.append({"c": c, "kids": kids, "nodeName": el.findtext("nodeName"), "meth": el.findtext("methName"),
                            "props": props, "label": lab, "oMId": el.findtext("oMId"),
                            "ddo": (ddo.get("uid"), ddo.get("class")) if ddo is not None else None,
                            "f": os.path.basename(f)})
    except Exception as e:
        pass
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return out

if __name__ == "__main__":
    files = sorted(glob.glob(sys.argv[1] + "/**/*.vi", recursive=True))
    allr = []
    with ProcessPoolExecutor(8) as ex:
        for r in ex.map(one, files): allr += r
    pass
    for c in ("propNode", "invokeNode", "ctlRefConst", "callByRefNode"):
        rows = [r for r in allr if r["c"] == c]
        print("=====", c, len(rows))
        print("  kids:", collections.Counter(t for r in rows for t in r["kids"]).most_common())
        print("  nodeName:", collections.Counter(r["nodeName"] for r in rows).most_common(8))
        print("  with props:", sum(1 for r in rows if r["props"]), " meth:", collections.Counter(r["meth"] for r in rows).most_common(6))
        print("  label:", collections.Counter(r["label"] for r in rows).most_common(6))
        print("  ddo:", collections.Counter((r["ddo"] or (None, None))[1] for r in rows).most_common(6), "oMId:", collections.Counter(r["oMId"] for r in rows).most_common(5))
