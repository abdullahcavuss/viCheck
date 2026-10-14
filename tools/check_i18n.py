"""Lists texts used with _() / _n() in templates and T() in scripts that have no Turkish translation."""
import os, re, sys, glob
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import i18n

def strings(pattern, text):
    out = []
    for m in re.finditer(pattern, text, re.S):
        raw = m.group(2)
        try:
            out.append(eval(m.group(1) + raw + m.group(1)))   # unescape like the language would
        except Exception:
            out.append(raw)
    return out

missing = {}
for f in glob.glob(os.path.join(ROOT, "templates", "*.html")):
    t = open(f, encoding="utf-8").read()
    for s in strings(r'\b_n?\(\s*(["\'])((?:\\.|(?!\1).)*)\1', t):
        missing.setdefault(s, set()).add(os.path.basename(f))
    for m in re.finditer(r'_n\(\s*"[^"]*"\s*,\s*"([^"]*)"', t):
        missing.setdefault(m.group(1), set()).add(os.path.basename(f))
for f in glob.glob(os.path.join(ROOT, "static", "*.js")) + glob.glob(os.path.join(ROOT, "templates", "*.html")):
    t = open(f, encoding="utf-8").read()
    for s in strings(r'\bT\(\s*(["\'])((?:\\.|(?!\1).)*)\1', t):
        missing.setdefault(s, set()).add(os.path.basename(f))
for f in [os.path.join(ROOT, "app.py")]:
    t = open(f, encoding="utf-8").read()
    for s in strings(r'\b_n?\(\s*(["\'])((?:\\.|(?!\1).)*)\1', t):
        missing.setdefault(s, set()).add("app.py")
bad = {k: v for k, v in missing.items() if k not in i18n.TR}
for k, v in sorted(bad.items()):
    print("MISSING", repr(k), sorted(v))
print(len(missing), "texts,", len(bad), "without translation")
