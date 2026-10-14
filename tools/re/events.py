import os as _os, sys as _sys; _sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "..")))
import sys, os, glob, tempfile, shutil, collections, json
from concurrent.futures import ProcessPoolExecutor
import xml.etree.ElementTree as ET

from engine import vi_parser
from engine.lvtypes import Types

def one(f):
    rows = []
    d = tempfile.mkdtemp()
    try:
        main, _ = vi_parser.extract_with_pylabview(f, d)
        bd = os.path.join(d, "vi_BDHb.xml"); fp = os.path.join(d, "vi_FPHb.xml")
        if not os.path.exists(bd): return rows
        T = Types(main)
        B = ET.parse(bd).getroot()
        names = {}
        if os.path.exists(fp):
            for el in ET.parse(fp).getroot().iter():
                if el.get("class") == "fPDCO":
                    ddo = el.find("ddo")
                    if ddo is not None and ddo.get("uid"):
                        nm = None
                        for p in (ddo.find("partsList") or []):
                            if p.get("class") == "label":
                                nm = vi_parser._first_text(p); break
                        names[ddo.get("uid")] = (nm, ddo.get("class"))
        byuid = {e.get("uid"): e for e in B.iter() if e.get("uid") and len(e)}
        for es in B.iter():
            if es.get("class") != "eventStruct": continue
            dl = es.find("diagramList")
            frames = [byuid.get(x.get("uid"), x) for x in dl] if dl is not None else []
            for spec in (es.find("EventNodeEvents") or []):
                g = {k: spec.findtext(k) for k in ("diagramIdx", "source", "type", "eFlags", "ddoUID", "eSource", "dynIndex", "menuTag")}
                agg = None
                try:
                    fr = frames[int(g["diagramIdx"])]
                    for n in fr.iter():
                        if n.get("class") == "eventDataNode":
                            t0 = n.find("termList")[0]
                            dco = t0.find("dco"); dco = byuid.get(dco.get("uid"), dco)
                            agg = T.fields(T.heap_el(dco.findtext("typeDesc"))); break
                except Exception as e:
                    agg = ["ERR"]
                rows.append({"f": os.path.relpath(f), "src": int(g["source"]), "type": int(g["type"]), "ef": g["eFlags"],
                             "ctl": names.get(g["ddoUID"]), "ddo": g["ddoUID"], "fields": agg, "es": g["eSource"], "dyn": g["dynIndex"]})
    except Exception:
        pass
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return rows

if __name__ == "__main__":
    files = sorted(glob.glob(sys.argv[1] + "/**/*.vi", recursive=True))
    allr = []
    with ProcessPoolExecutor(8) as ex:
        for r in ex.map(one, files): allr += r
    pass
    g = collections.defaultdict(list)
    for r in allr:
        t = r["type"] & 0xFFFFFFFF
        g[(r["src"], t >> 28, t & 0xFFFF)].append(r)
    for k, v in sorted(g.items()):
        fs = collections.Counter(tuple(x["fields"] or []) for x in v).most_common(1)[0][0]
        ctls = collections.Counter((x["ctl"] or (None, None))[1] for x in v).most_common(3)
        print(k, "x%d" % len(v), "fields:", list(fs)[3:] if fs else None, "ctl:", ctls, "eS:", sorted({x['es'] for x in v}))
