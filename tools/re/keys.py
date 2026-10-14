import os as _os, sys as _sys; _sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "..")))
import sys, os, glob, tempfile, shutil, collections
import xml.etree.ElementTree as ET
from concurrent.futures import ProcessPoolExecutor

from engine import vi_parser
def one(f):
    out = []; d = tempfile.mkdtemp()
    try:
        vi_parser.extract_with_pylabview(f, d)
        p = os.path.join(d, "vi_FPHb.xml")
        if not os.path.exists(p): return out
        r = ET.parse(p).getroot(); lab = {}
        for el in r.iter():
            pl = el.find("partsList") if el.get("uid") else None
            if pl is not None:
                for q in pl:
                    if q.get("class") == "label":
                        lab[el.get("uid")] = vi_parser._first_text(q); break
        for b in r.iter("SL__arrayElement"):
            if b.get("class") == "KeyMappingBinding":
                o = b.find("Obj")
                out.append((b.findtext("VKey"), b.findtext("CharCode"), b.findtext("Mods"), b.findtext("Action"), lab.get(o.get("uid") if o is not None else None), os.path.basename(f)))
    except Exception: pass
    finally: shutil.rmtree(d, ignore_errors=True)
    return out
if __name__ == "__main__":
    fs = sorted(glob.glob(sys.argv[1] + "/**/*.vi", recursive=True)); allr = []
    with ProcessPoolExecutor(8) as ex:
        for r in ex.map(one, fs): allr += r
    c = collections.defaultdict(collections.Counter)
    for vk, ch, m, a, l, f in allr: c[(vk, ch, m, a)][l] += 1
    for k, v in sorted(c.items()): print(k, v.most_common(6))
