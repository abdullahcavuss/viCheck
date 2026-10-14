"""
viCheck — compare two LabVIEW VIs or two folders of VIs, with block diagram diffs drawn as SVG.

This module is the web application. Start the program with vicheck.py (or viCheck.exe),
which opens it in a desktop window.
"""
import copy
import datetime
import difflib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import zipfile

from flask import (Flask, Response, abort, jsonify, redirect, render_template, request, send_file, url_for)

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from engine.files import (LocalStore, CompareError, diff_trees, file_kind, human_size, is_text, is_vi,  # noqa: E402
                          parse_rules, DEFAULT_IGNORE)
from engine.service import VIService  # noqa: E402
from engine import palettes, mdlite, pylv  # noqa: E402
from engine import changelog as report_mod  # noqa: E402
from engine import svgrender, pdfout  # noqa: E402
from engine.vi_diff import CATEGORIES  # noqa: E402
import i18n  # noqa: E402

APP_NAME = "viCheck"
VERSION = "1.0.0"


def default_data_dir():
    if os.environ.get("VICHECK_DATA"):
        return os.environ["VICHECK_DATA"]
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return os.path.join(os.environ["LOCALAPPDATA"], APP_NAME)
    return os.path.join(os.path.expanduser("~"), ".vicheck")


DATA_DIR = default_data_dir()
os.makedirs(DATA_DIR, exist_ok=True)

app = Flask(__name__, template_folder=os.path.join(HERE, "templates"), static_folder=os.path.join(HERE, "static"))
app.config["TEMPLATES_AUTO_RELOAD"] = True

store = LocalStore(DATA_DIR)
vis = VIService(store)

# set by the launcher: "webview" (desktop window), "app" (Edge/Chrome app window) or "browser"
UI = {"mode": "browser", "base_url": ""}

app.jinja_env.filters["hsize"] = human_size
app.jinja_env.globals["file_kind"] = file_kind
app.jinja_env.globals["is_vi"] = is_vi
app.jinja_env.globals["is_text_ext"] = lambda p: is_text(p)


# ------------------------------------------------------------------ language
def get_lang():
    """Chosen language: saved setting, else cookie, else the browser/Windows language."""
    try:
        lang = store.settings().get("lang") or request.cookies.get("lang")
        if lang in i18n.LANGS:
            return lang
        return i18n.detect(request.headers.get("Accept-Language"))
    except RuntimeError:   # outside a request (background jobs)
        return store.settings().get("lang") or i18n.DEFAULT


def _(text, **values):
    return i18n.translate(text, get_lang(), **values)


def _n(singular, plural, n, **values):
    return i18n.plural(singular, plural, n, get_lang(), **values)


_DYN = None


def translate_message(msg, lang=None):
    """Translates a message that was built from a template key, e.g. 'Not found: C:\\x' (error texts)."""
    global _DYN
    lang = lang or get_lang()
    if lang == "en" or not msg:
        return msg
    if msg in i18n.TR:
        return i18n.TR[msg]
    if _DYN is None:
        _DYN = []
        for key in i18n.TR:
            if "{" in key:
                rx = "^" + re.sub(r"\\\{(\w+)\\\}", lambda m: "(?P<%s>.+?)" % m.group(1), re.escape(key)) + "$"
                try:
                    _DYN.append((re.compile(rx, re.S), key))
                except re.error:
                    pass
    for rx, key in _DYN:
        m = rx.match(msg)
        if m:
            return i18n.TR[key].format(**m.groupdict())
    return msg


@app.context_processor
def inject_globals():
    lang = get_lang()
    return {"app_name": APP_NAME, "app_version": VERSION, "ui_mode": UI["mode"], "lang": lang,
            "langs": i18n.LANGS, "_": _, "_n": _n, "i18n_js": json.dumps(i18n.js_table(lang), ensure_ascii=False),
            "show_welcome": not store.settings().get("welcome_seen"), "prim_status": prim_status}


def prim_status():
    """For the first-start help: how many primitive names are known and where they came from."""
    rows = store.prim_name_rows()
    srcs = sorted({r["source"] for r in rows if r["source"] != "user"})
    return {"count": len(rows), "sources": [s.replace("palette: ", "") for s in srcs],
            "running": bool(PRIM_JOB.get("running")), "installs": palettes.find_installations()}


@app.route("/api/welcome-seen", methods=["POST"])
def api_welcome_seen():
    """The first-start help was closed: do not open it by itself again (the ? button still shows it)."""
    store.save_settings(welcome_seen=True)
    return jsonify({"ok": True})


@app.route("/lang/<code>")
def set_lang(code):
    if code not in i18n.LANGS:
        abort(404)
    store.save_settings(lang=code)
    nxt = request.args.get("next") or "/"
    if not nxt.startswith("/"):
        nxt = "/"
    resp = redirect(nxt)
    resp.set_cookie("lang", code, max_age=10 * 365 * 24 * 3600, samesite="Lax")
    return resp


@app.errorhandler(CompareError)
def handle_compare_error(e):
    msg = translate_message(str(e))
    if request.path.startswith("/api/"):
        return jsonify({"error": msg}), 400
    return render_template("home.html", error=msg, a=request.args.get("a", ""), b=request.args.get("b", ""),
                           recent=store.recent(), settings=store.settings(), default_ignore=DEFAULT_IGNORE), 400


# ------------------------------------------------------------------ helpers
def clean_path(p):
    p = (p or "").strip().strip('"').strip("'").strip()
    if not p:
        return ""
    p = os.path.expandvars(os.path.expanduser(p))
    return os.path.normpath(os.path.abspath(p))


def kind_of(p):
    if not p:
        return None
    if os.path.isdir(p):
        return "folder"
    if os.path.isfile(p):
        return "file"
    return None


def short_label(path, root=None):
    if root:
        return os.path.basename(root.rstrip("\\/")) or root
    return os.path.basename(path) or path


def ignore_rules():
    return parse_rules(store.settings().get("ignore", ""))


# ------------------------------------------------------------------ home
@app.route("/")
def index():
    return render_template("home.html", a=request.args.get("a", ""), b=request.args.get("b", ""),
                           recent=store.recent(), settings=store.settings(), default_ignore=DEFAULT_IGNORE,
                           error=None)


@app.route("/settings", methods=["POST"])
def save_settings():
    store.save_settings(ignore=request.form.get("ignore", ""))
    return redirect(request.referrer or url_for("index"))


@app.route("/recent/clear", methods=["POST"])
def clear_recent():
    store.clear_recent()
    return redirect(url_for("index"))


@app.route("/compare")
def compare():
    a, b = clean_path(request.args.get("a")), clean_path(request.args.get("b"))
    if not a or not b:
        raise CompareError(_("Choose two VIs or two folders to compare."))
    ka, kb = kind_of(a), kind_of(b)
    if ka is None:
        raise CompareError(_("Not found: {path}", path=a))
    if kb is None:
        raise CompareError(_("Not found: {path}", path=b))
    if ka != kb:
        raise CompareError(_("Both sides must be of the same kind: two files or two folders (A is a {a}, B is a {b}).",
                              a=_(ka), b=_(kb)))
    if os.path.normcase(a) == os.path.normcase(b):
        raise CompareError(_("A and B are the same {kind}.", kind=_(ka)))
    store.add_recent(a, b, ka)
    if ka == "file":
        return redirect(url_for("vidiff_view", a=a, b=b))
    return folder_compare(a, b)


def folder_compare(a, b):
    rules = ignore_rules()
    ta = store.scan_folder(a, rules)
    tb = store.scan_folder(b, rules)
    allc = diff_trees(ta, tb, include_same=True)
    changes = [c for c in allc if c["status"] != "same"]
    same = [c for c in allc if c["status"] == "same"]
    stats = {k: sum(1 for c in changes if c["status"] == k) for k in ("added", "deleted", "modified", "renamed")}
    return render_template("compare.html", a=a, b=b, changes=changes, same=same, stats=stats,
                           count_a=len(ta), count_b=len(tb), la=short_label(a, a), lb=short_label(b, b),
                           categories=CATEGORIES, default_cats=report_mod.DEFAULT_CATS, rules=rules)


# ------------------------------------------------------------------ VI diff
@app.route("/vidiff")
def vidiff_view():
    """Side-by-side block diagram diff of two files. Either side may be empty (added / deleted VI)."""
    a, b = clean_path(request.args.get("a")), clean_path(request.args.get("b"))
    ra, rb = clean_path(request.args.get("ra")), clean_path(request.args.get("rb"))
    if not a and not b:
        abort(404)
    for p in (a, b):
        if p and not os.path.isfile(p):
            raise CompareError(_("File not found: {path}", path=p))
    old_sha = store.register(a) if a else None
    new_sha = store.register(b) if b else None
    fname = os.path.basename(b or a)
    if not is_vi(fname) and not is_vi(os.path.basename(a or b)):
        return textdiff_page(a, b)
    rel_a = os.path.relpath(a, ra) if a and ra else a
    rel_b = os.path.relpath(b, rb) if b and rb else b
    back = request.args.get("back") or ""
    if back and not back.startswith("/"):
        back = ""
    return render_template("vidiff.html", a=a, b=b, old_sha=old_sha, new_sha=new_sha, fname=fname,
                           old_label=rel_a if a else _("(no file)"), new_label=rel_b if b else _("(no file)"),
                           back_url=back or url_for("index", a=a, b=b), back_label=_("Back to the comparison") if back else _("New comparison"),
                           ra=ra, rb=rb)


def textdiff_page(a, b):
    return render_template("textdiff.html", a=a, b=b, fname=os.path.basename(b or a),
                           back_url=request.args.get("back") or url_for("index"))


@app.route("/api/vidiff")
def api_vidiff():
    old = request.args.get("old") or None
    new = request.args.get("new") or None
    for s in (old, new):
        if s and (len(s) != 64 or not all(ch in "0123456789abcdef" for ch in s) or not store.has(s)):
            return jsonify({"error": _("Unknown file. Reload the page to scan the files again.")}), 400
    try:
        d = vis.diff(old, new, request.args.get("name", "x.vi"))
    except CompareError as e:
        return jsonify({"error": translate_message(str(e))}), 400
    d = i18n.localize_diff(copy.deepcopy(d), get_lang())
    return Response(json.dumps(d, ensure_ascii=False), mimetype="application/json")


@app.route("/api/visummary")
def api_visummary():
    old = request.args.get("old") or None
    new = request.args.get("new") or None
    for s in (old, new):
        if s and not store.has(s):
            return jsonify({"error": _("Unknown file — run the comparison again.")}), 400
    try:
        return jsonify(i18n.localize_summary(vis.summary(old, new, request.args.get("name", "x.vi")), get_lang()))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/textdiff")
def api_textdiff():
    a, b = clean_path(request.args.get("a")), clean_path(request.args.get("b"))

    def read(p):
        if not p or not os.path.isfile(p):
            return ""
        with open(p, "rb") as f:
            return f.read().decode("utf-8", "replace")
    return jsonify({"rows": text_diff_rows(read(a), read(b))})


def text_diff_rows(old, new, context=3):
    a = old.splitlines()
    b = new.splitlines()
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    rows = []
    for group in sm.get_grouped_opcodes(context):
        i1, j1 = group[0][1], group[0][3]
        i2, j2 = group[-1][2], group[-1][4]
        rows.append({"t": "hunk", "text": "@@ -%d,%d +%d,%d @@" % (i1 + 1, i2 - i1, j1 + 1, j2 - j1)})
        for tag, a1, a2, b1, b2 in group:
            if tag == "equal":
                for k in range(a2 - a1):
                    rows.append({"t": "eq", "o": a1 + k + 1, "n": b1 + k + 1, "text": a[a1 + k]})
            else:
                for k in range(a1, a2):
                    rows.append({"t": "del", "o": k + 1, "text": a[k]})
                for k in range(b1, b2):
                    rows.append({"t": "add", "n": k + 1, "text": b[k]})
    if len(rows) > 6000:
        rows = rows[:6000] + [{"t": "hunk", "text": "… diff too large, truncated"}]
    return rows


# ------------------------------------------------------------------ SVG export of one VI pair
def _slug(s):
    return report_mod.slug(s)


@app.route("/export-svg")
def export_svg():
    """Draws the old and new block diagram into SVG files (one per view) and shows them."""
    a, b = clean_path(request.args.get("a")), clean_path(request.args.get("b"))
    def flag(k, default):   # a checkbox after a hidden "0" field: the last value wins
        v = request.args.getlist(k)
        return v[-1] == "1" if v else default
    want_pdf = flag("pdf", False)
    # PDF: Stacked Sequences frame by frame (unfolded they make very wide, tiny pages); SVG: as in the viewer
    flat = flag("flat", not want_pdf)
    # report contents: the options form sends inc=… for every ticked part (and inc_sent=1)
    include = request.args.getlist("inc") if request.args.get("inc_sent") else list(report_mod.INCLUDE_ALL)
    details = "details" in include
    old_sha = store.register(a) if a else None
    new_sha = store.register(b) if b else None
    name = os.path.basename(b or a)
    d = vis.diff(old_sha, new_sha, name)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    jid = "%s-%s" % (_slug(name), stamp)
    out = os.path.join(store.export_dir, jid)
    os.makedirs(os.path.join(out, report_mod.IMG_DIR), exist_ok=True)
    status = "modified" if (a and b) else ("added" if b else "deleted")
    item = {"c": {"path": name, "status": status, "old_sha": old_sha, "new_sha": new_sha},
            "d": d, "verdict": d["diff"].get("verdict") or {"level": "functional", "parts": []},
            "parts": (d["diff"].get("verdict") or {}).get("parts", []),
            "base_short": "A", "head_short": "B", "old_title": "A", "new_title": "B"}
    cats = set(c for c, _ in CATEGORIES)
    lang = get_lang()
    lines = report_mod._vi_section(item, out, store.prim_names(), False, cats, flat=flat, include=include)
    img_dir = os.path.join(out, report_mod.IMG_DIR)
    svgs = sorted(f for f in os.listdir(img_dir) if f.endswith(".svg")) if os.path.isdir(img_dir) else []
    if not svgs and include and {"overview", "details"} & set(include):
        # no marked block diagram changes: still draw both diagrams so they can be looked at as SVG
        old_bd = d["old"].get("bd") if not d["old"].get("empty") else None
        new_bd = d["new"].get("bd") if not d["new"].get("empty") else None
        if (old_bd and old_bd.get("nodes")) or (new_bd and new_bd.get("nodes")):
            os.makedirs(img_dir, exist_ok=True)
            views = svgrender.render_pair(old_bd if old_bd and old_bd.get("nodes") else None, {}, [],
                                          new_bd if new_bd and new_bd.get("nodes") else None, {}, [],
                                          os.path.join(img_dir, report_mod.slug(name)), store.prim_names(),
                                          old_title="A", new_title="B", flat=flat)
            for v in views:
                rel = os.path.relpath(v["file"], out).replace(os.sep, "/").replace(" ", "%20")
                lines += ["**Block diagrams of A and B** _(no block diagram changes to mark)_", "",
                          "[![%s](%s)](%s)" % (name, rel, rel), ""]
            svgs = sorted(f for f in os.listdir(img_dir) if f.endswith(".svg"))
    section = i18n.report_markdown("\n".join(lines[2:]), lang)
    md = "# %s\n\n**A:** `%s`  \n**B:** `%s`\n\n" % (name, a or "—", b or "—") + section
    with open(os.path.join(out, "README.md"), "w", encoding="utf-8") as f:
        f.write(md)
    pdf, pdf_error = None, None
    if want_pdf:
        try:
            pdf = pdfout.make_pdf(md, out, report_mod.slug(name) + ".pdf", name, lang)
        except Exception as e:
            pdf_error = str(e)
    body = mdlite.render(section, url_for("export_file", jid=jid, fpath=""))
    return render_template("export.html", jid=jid, name=name, a=a, b=b, svgs=svgs, out=out, body=body,
                           back=url_for("vidiff_view", a=a, b=b), pdf=pdf, pdf_error=pdf_error,
                           opts={"pdf": want_pdf, "flat": flat, "details": details, "include": include})


@app.route("/api/save-svg", methods=["POST"])
def api_save_svg():
    """Saves the SVG the diff page built from its current view (what you see, at the current zoom)."""
    data = request.get_json(force=True, silent=True) or {}
    svg = data.get("svg") or ""
    if not svg.lstrip().startswith("<?xml") and not svg.lstrip().startswith("<svg"):
        return jsonify({"error": "not an SVG"}), 400
    jid = "views"
    out = os.path.join(store.export_dir, jid)
    os.makedirs(out, exist_ok=True)
    fn = "%s-view-%s.svg" % (_slug(data.get("name") or "vi"), datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
    path = os.path.join(out, fn)
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    return jsonify({"path": path, "url": url_for("export_file", jid=jid, fpath=fn)})


@app.route("/exports/<jid>/f/<path:fpath>")
def export_file(jid, fpath):
    if not re.match(r"^[A-Za-z0-9._-]+$", jid):
        abort(404)
    base = os.path.realpath(os.path.join(store.export_dir, jid))
    full = os.path.realpath(os.path.join(base, fpath))
    if not full.startswith(base + os.sep) or not os.path.isfile(full):
        abort(404)
    if full.lower().endswith(".svg"):
        return send_file(full, mimetype="image/svg+xml")
    return send_file(full)


# ------------------------------------------------------------------ folder comparison report (Markdown + SVGs)
REPORTS = {}


class _ReportStore:
    """Presents the two folders to the CHANGELOG generator as two 'commits'."""

    def __init__(self, a, b, ta, tb):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        self.commits = {
            "A": {"id": "A", "short": "A", "title": a, "time": now, "tree": ta, "parent": None, "branch": "-",
                  "author": "", "body": "", "image_title": "A"},
            "B": {"id": "B", "short": "B", "title": b, "time": now, "tree": tb, "parent": "A", "branch": "-",
                  "author": "", "body": "", "image_title": "B"},
        }

    def get_commit(self, repo, ref):
        return self.commits.get(ref)

    def prim_names(self):
        return store.prim_names()

    def get_blob(self, sha, verify=False):
        return store.get_blob(sha)


report_mod.commits_between = lambda *a, **k: []   # folders have no commit history


@app.route("/report", methods=["POST"])
def report_start():
    a, b = clean_path(request.form.get("a")), clean_path(request.form.get("b"))
    if kind_of(a) != "folder" or kind_of(b) != "folder":
        raise CompareError(_("A report can be made for two folders."))
    cats = request.form.getlist("cat") or list(report_mod.DEFAULT_CATS)
    want_pdf = request.form.get("pdf") == "1"
    flat = request.form.get("flat") == "1"
    include = request.form.getlist("inc")
    details = "details" in include
    jid = "report-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = os.path.join(store.export_dir, jid)
    os.makedirs(out, exist_ok=True)
    meta = {"id": jid, "a": a, "b": b, "running": True, "done": 0, "total": 0, "current": "", "error": None,
            "result": None, "cats": cats, "out": out, "pdf": None, "pdf_error": None,
            "opts": {"pdf": want_pdf, "flat": flat, "details": details, "include": include}}
    REPORTS[jid] = meta
    lang = get_lang()   # the worker thread has no request

    def run():
        try:
            rules = ignore_rules()
            ta, tb = store.scan_folder(a, rules), store.scan_folder(b, rules)
            rs = _ReportStore(a, b, ta, tb)

            def prog(d, t, cur):
                meta.update(done=d, total=t, current=cur)
            meta["result"] = report_mod.generate(rs, vis, {"name": "viCheck"}, "A", "B", out, progress=prog, cats=cats,
                                                 flat=flat, include=include)
            md_path = os.path.join(out, "CHANGELOG.md")
            with open(md_path, encoding="utf-8") as f:
                md = f.read()
            m = re.search(r"^## ", md, re.M)   # drop the generator's own title (viCheck writes its own header)
            body = md[m.start():] if m else ""
            head = i18n.REPORT_HEAD[lang].format(
                a=a, b=b, now=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), ver=VERSION,
                scope=", ".join(i18n.translate(t, lang) for k, t in CATEGORIES if k in cats))
            report_md = head + i18n.report_markdown(body, lang)
            with open(os.path.join(out, "REPORT.md"), "w", encoding="utf-8") as f:
                f.write(report_md)
            os.remove(md_path)
            if want_pdf:
                meta["current"] = "PDF…"
                try:
                    meta["pdf"] = pdfout.make_pdf(report_md, out, "REPORT.pdf", "viCheck", lang)
                except Exception as e:
                    meta["pdf_error"] = str(e)
        except Exception as e:
            import traceback
            traceback.print_exc()
            meta["error"] = "%s: %s" % (type(e).__name__, e)
        finally:
            meta["running"] = False
            with open(os.path.join(out, "job.json"), "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False)

    threading.Thread(target=run, daemon=True).start()
    return redirect(url_for("report_view", jid=jid))


def _report_meta(jid):
    if not re.match(r"^[A-Za-z0-9_-]+$", jid or ""):
        abort(404)
    if jid in REPORTS:
        return REPORTS[jid]
    p = os.path.join(store.export_dir, jid, "job.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    abort(404)


@app.route("/report/<jid>")
def report_view(jid):
    meta = _report_meta(jid)
    body = None
    md_path = os.path.join(store.export_dir, jid, "REPORT.md")
    if not meta.get("running") and os.path.exists(md_path):
        with open(md_path, encoding="utf-8") as f:
            body = mdlite.render(f.read(), url_for("export_file", jid=jid, fpath=""))
    return render_template("report.html", meta=meta, body=body, out=os.path.join(store.export_dir, jid))


@app.route("/api/report/<jid>")
def api_report(jid):
    return jsonify(_report_meta(jid))


@app.route("/report/<jid>/zip")
def report_zip(jid):
    _report_meta(jid)
    out = os.path.join(store.export_dir, jid)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for r, _, files in os.walk(out):
            for f in files:
                if f == "job.json":
                    continue
                full = os.path.join(r, f)
                z.write(full, os.path.relpath(full, out))
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="viCheck-%s.zip" % jid, mimetype="application/zip")


# ------------------------------------------------------------------ desktop helpers (file pickers, explorer, browser)
def _self_cmd(*args):
    if pylv.FROZEN:
        return [sys.executable] + list(args)
    return [sys.executable, os.path.join(HERE, "vicheck.py")] + list(args)


@app.route("/api/pick")
def api_pick():
    """Native file / folder dialog, run in a child process (used when not inside the desktop window)."""
    kind = request.args.get("kind", "file")
    initial = request.args.get("initial", "")
    try:
        p = subprocess.run(_self_cmd("--pick", kind, initial), capture_output=True, text=True, timeout=3600,
                           stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace")
        lines = [l for l in (p.stdout or "").splitlines() if l.strip()]
        return jsonify({"path": lines[-1].strip() if lines else ""})
    except Exception as e:
        return jsonify({"path": "", "error": str(e)})


@app.route("/api/kind")
def api_kind():
    p = clean_path(request.args.get("path"))
    k = kind_of(p)
    info = {"path": p, "kind": k}
    if k == "file":
        info["is_vi"] = is_vi(p)
        info["size"] = human_size(os.path.getsize(p))
    elif k == "folder":
        n = vi = 0
        for _, dirs, files in os.walk(p):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            n += len(files)
            vi += sum(1 for f in files if is_vi(f))
            if n > 20000:
                break
        info.update(files=n, vis=vi)
    return jsonify(info)


@app.route("/api/reveal", methods=["POST"])
def api_reveal():
    """Shows a file or folder in Windows Explorer (or the platform's file manager)."""
    p = clean_path((request.get_json(silent=True) or {}).get("path"))
    if not p or not os.path.exists(p):
        return jsonify({"ok": False, "error": "Not found"}), 404
    try:
        if os.name == "nt":
            if os.path.isdir(p):
                os.startfile(p)  # noqa
            else:
                subprocess.Popen(["explorer", "/select,", p])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", p])
        else:
            subprocess.Popen(["xdg-open", p if os.path.isdir(p) else os.path.dirname(p)])
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True})


@app.route("/api/open-file", methods=["POST"])
def api_open_file():
    """Opens a generated file (the PDF) with its default application. Only files under the export folder."""
    p = os.path.realpath(clean_path((request.get_json(silent=True) or {}).get("path")) or "")
    base = os.path.realpath(store.export_dir)
    if not p.startswith(base + os.sep) or not os.path.isfile(p):
        return jsonify({"ok": False, "error": "Not found"}), 404
    try:
        if os.name == "nt":
            os.startfile(p)  # noqa
        elif sys.platform == "darwin":
            subprocess.Popen(["open", p])
        else:
            subprocess.Popen(["xdg-open", p])
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True})


@app.route("/api/open-browser", methods=["POST"])
def api_open_browser():
    """Opens a page of the app in the default browser (e.g. to inspect the SVG with its developer tools)."""
    import webbrowser
    path = (request.get_json(silent=True) or {}).get("path") or "/"
    if not path.startswith("/"):
        path = "/"
    webbrowser.open(UI["base_url"] + path)
    return jsonify({"ok": True})


# ------------------------------------------------------------------ primitive names (from the LabVIEW palettes)
PRIM_JOB = {"running": False, "done": 0, "total": 0, "added": 0, "found": 0, "path": None, "error": None, "finished": None}


def start_prim_import(lv_dir):
    if PRIM_JOB["running"]:
        return False

    def run():
        PRIM_JOB.update(running=True, done=0, total=0, added=0, found=0, path=lv_dir, error=None, finished=None)
        try:
            def prog(d, t):
                PRIM_JOB["done"], PRIM_JOB["total"] = d, t
            mapping, total = palettes.scan_installation(lv_dir, progress=prog)
            PRIM_JOB["found"] = len(mapping)
            PRIM_JOB["added"] = store.import_prim_names(mapping, "palette: " + os.path.basename(lv_dir))
            if total == 0:
                PRIM_JOB["error"] = "No menus/*.mnu palette files were found in this folder."
        except Exception as e:  # pragma: no cover
            PRIM_JOB["error"] = str(e)
        finally:
            PRIM_JOB["running"] = False
            PRIM_JOB["finished"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    threading.Thread(target=run, daemon=True).start()
    return True


@app.route("/primitives", methods=["GET", "POST"])
def primitives_page():
    if request.method == "POST":
        path = (request.form.get("lv_dir") or "").strip()
        if not path or not os.path.isdir(path):
            raise CompareError(_("LabVIEW folder not found: {path}", path=path))
        start_prim_import(path)
        return redirect(url_for("primitives_page"))
    rows = sorted(store.prim_name_rows(), key=lambda r: int(r["res_id"]) if r["res_id"].isdigit() else 0)
    return render_template("primitives.html", rows=rows, installs=palettes.find_installations(), job=PRIM_JOB)


@app.route("/api/prim-import")
def api_prim_import():
    return jsonify(PRIM_JOB)


@app.route("/api/prim-names", methods=["GET", "POST"])
def api_prim_names():
    if request.method == "POST":
        data = request.get_json(force=True)
        store.set_prim_name(data.get("id"), data.get("name"))
    return jsonify(store.prim_names())


def auto_import_prims():
    """On first run: if there are no palette names yet, import them from the newest LabVIEW installation found."""
    try:
        if any(r["source"] != "user" for r in store.prim_name_rows()):
            return
        inst = palettes.find_installations()
        if inst:
            start_prim_import(inst[0])
    except Exception:
        pass


@app.route("/about")
def about():
    return render_template("about.html", data_dir=DATA_DIR)
