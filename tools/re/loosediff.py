"""Shows which heap tokens make two VIs differ in 'content' (the loose fingerprint)."""
import os as _os, sys as _sys; _sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "..")))
import sys, os, re, difflib, tempfile, collections

from engine import vi_parser as V
def stream(path):
    root = V._parse_xml(path); out = []
    def tok(el):
        attrs = ",".join("%s=%s" % (k, v) for k, v in sorted(el.attrib.items()) if k != "uid")
        txt = re.sub(r"TypeID\(\d+\)", "TypeID()", (el.text or "").strip())
        return "<%s %s>%s" % (el.tag, attrs, txt)
    def walk(el, cosmetic, chain):
        tag = el.tag
        if tag in V._HEAP_NOISE: return
        if tag == "fr" or el.get("class") == "fontRun": cosmetic = True
        ch = chain + ([el.get("class")] if el.get("class") else [])
        if not (cosmetic or tag in V._HEAP_ROUTE):
            out.append(("<%s/>" % tag if tag in V._HEAP_GEOM else tok(el), " < ".join(reversed(ch[-4:]))))
        for c in el: walk(c, cosmetic, ch)
    walk(root, False, [])
    return out
def heaps(vi):
    d = tempfile.mkdtemp(); V.extract_with_pylabview(vi, d)
    return os.path.join(d, os.environ.get("HEAP", "vi_BDHb.xml"))
a, b = stream(heaps(sys.argv[1])), stream(heaps(sys.argv[2]))
sm = difflib.SequenceMatcher(None, [x[0] for x in a], [x[0] for x in b], autojunk=False)
n = 0
for op, i1, i2, j1, j2 in sm.get_opcodes():
    if op == "equal": continue
    n += 1
    if n > 25: break
    print(op, "A:", [x[0][:60] for x in a[i1:i2]][:4], "B:", [x[0][:60] for x in b[j1:j2]][:4], "|", (a[i1] if i1 < len(a) else b[j1])[1])
