"""
viCheck — LabVIEW VI / folder comparison.

    viCheck.exe                      open the start page
    viCheck.exe <A> <B>              compare two VIs or two folders right away
    viCheck.exe --browser [A B]      use the default web browser instead of the app window
    viCheck.exe --port 8765          fixed port (default: a free one)

From source:  python vicheck.py [same options]
"""
import os
import socket
import sys
import threading
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


# ------------------------------------------------------------------ helper modes (child processes)
def pick_dialog(kind, initial):
    """--pick file|folder [initial]: shows a native dialog with Tk and prints the chosen path."""
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    initdir = initial if initial and os.path.isdir(initial) else (os.path.dirname(initial) if initial else "")
    if kind == "folder":
        p = filedialog.askdirectory(parent=root, initialdir=initdir or None, title="Choose a folder")
    else:
        p = filedialog.askopenfilename(parent=root, initialdir=initdir or None, title="Choose a VI",
                                       filetypes=[("LabVIEW files", "*.vi *.ctl *.vit *.vim *.ctt"), ("All files", "*.*")])
    root.destroy()
    if p:
        print(os.path.normpath(p))


def free_port(preferred=None):
    if preferred:
        return preferred
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def start_server(port):
    from app import app
    try:
        from waitress import serve
        t = threading.Thread(target=lambda: serve(app, host="127.0.0.1", port=port, threads=8, _quiet=True), daemon=True)
    except ImportError:
        t = threading.Thread(target=lambda: app.run(host="127.0.0.1", port=port, debug=False, threaded=True,
                                                    use_reloader=False), daemon=True)
    t.start()
    for _ in range(200):
        try:
            urllib.request.urlopen("http://127.0.0.1:%d/about" % port, timeout=1).read()
            return t
        except Exception:
            time.sleep(0.05)
    return t


def start_url(base, paths):
    if len(paths) >= 2:
        return base + "/compare?" + urllib.parse.urlencode({"a": paths[0], "b": paths[1]})
    if len(paths) == 1:
        return base + "/?" + urllib.parse.urlencode({"a": paths[0]})
    return base + "/"


# ------------------------------------------------------------------ desktop window
class JsApi:
    """Functions the page can call as window.pywebview.api.* inside the desktop window."""

    def __init__(self, window=None):
        # Underscore: pywebview walks the public attributes of js_api to expose them to the page. A public
        # reference to the Window would make it walk the native WinForms/WebView2 objects too, which blocks
        # the UI thread (the window freezes while being moved or resized).
        self._window = window

    def pick(self, kind, initial=""):
        import webview
        ftype = getattr(webview, "FOLDER_DIALOG", 20) if kind == "folder" else getattr(webview, "OPEN_DIALOG", 10)
        try:
            from webview import FileDialog  # pywebview >= 5
            ftype = FileDialog.FOLDER if kind == "folder" else FileDialog.OPEN
        except Exception:
            pass
        kw = {"directory": initial if initial and os.path.isdir(initial) else (os.path.dirname(initial) if initial else "")}
        if kind != "folder":
            kw["file_types"] = ("LabVIEW files (*.vi;*.ctl;*.vit;*.vim;*.ctt)", "All files (*.*)")
        res = self._window.create_file_dialog(ftype, **kw)
        if not res:
            return ""
        return res[0] if isinstance(res, (list, tuple)) else str(res)


def run_webview(url, debug):
    import webview
    api = JsApi()
    try:
        webview.settings["OPEN_DEVTOOLS_IN_DEBUG"] = False   # right-click → Inspect, without opening it at start
        webview.settings["ALLOW_DOWNLOADS"] = True
    except Exception:
        pass
    win = webview.create_window("viCheck — LabVIEW VI compare", url, js_api=api, width=1440, height=900,
                                min_size=(900, 600), text_select=True)
    api._window = win

    def bind_drop():
        """Dropped files: the desktop window knows their full paths; hand them to the page."""
        try:
            from webview.dom import DOMEventHandler
        except Exception:
            return

        def on_drop(e):
            try:
                files = e.get("dataTransfer", {}).get("files", [])
                paths = [f.get("pywebviewFullPath") for f in files if f.get("pywebviewFullPath")]
                if paths:
                    import json
                    win.evaluate_js("window.viCheckDropped && window.viCheckDropped(%s)" % json.dumps(paths))
            except Exception:
                pass
        try:
            win.dom.document.events.drop += DOMEventHandler(on_drop, True, True)
        except Exception:
            pass

    win.events.loaded += bind_drop
    gui = "edgechromium" if os.name == "nt" else None
    webview.start(debug=debug, gui=gui, private_mode=False,
                  storage_path=os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "viCheck", "webview"))


def find_app_browser():
    """Microsoft Edge or Google Chrome, used as a chrome-less app window if pywebview is missing."""
    cands = []
    for env in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            cands += [os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"),
                      os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")]
    for c in cands:
        if os.path.exists(c):
            return c
    return None


def main(argv):
    if argv and argv[0] == "--pylabview":
        from engine.pylv import run_readrsrc_inprocess
        sys.exit(run_readrsrc_inprocess(argv[1:]))
    if argv and argv[0] == "--pick":
        pick_dialog(argv[1] if len(argv) > 1 else "file", argv[2] if len(argv) > 2 else "")
        return

    mode = "webview"
    port = None
    debug = True
    paths = []
    it = iter(argv)
    for a in it:
        if a == "--browser":
            mode = "browser"
        elif a == "--app":
            mode = "app"
        elif a == "--port":
            port = int(next(it))
        elif a == "--no-devtools":
            debug = False
        elif a.startswith("-"):
            print(__doc__)
            return
        else:
            paths.append(a)

    port = free_port(port)
    base = "http://127.0.0.1:%d" % port
    import app as appmod
    appmod.UI["base_url"] = base
    start_server(port)
    appmod.auto_import_prims()
    url = start_url(base, paths)

    if mode == "webview":
        try:
            import webview  # noqa: F401
            appmod.UI["mode"] = "webview"
            run_webview(url, debug)
            return
        except Exception as e:  # pywebview / WebView2 not available
            sys.stderr.write("Desktop window not available (%s); using a browser window.\n" % e)
            mode = "app"
    if mode == "app":
        exe = find_app_browser()
        if exe:
            import subprocess
            appmod.UI["mode"] = "app"
            prof = os.path.join(appmod.DATA_DIR, "browser-profile")
            p = subprocess.Popen([exe, "--app=" + url, "--user-data-dir=" + prof, "--no-first-run",
                                  "--window-size=1440,900"])
            p.wait()
            # if the browser handed the window to another of its processes, keep serving while the profile is in use
            _wait_forever_if_needed(prof)
            return
        mode = "browser"
    import webbrowser
    appmod.UI["mode"] = "browser"
    print("viCheck is running at %s  (close this window to stop)" % base)
    webbrowser.open(url)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


def _wait_forever_if_needed(profile_dir):
    """Keeps the server alive while the app window (a browser process using our profile) is open."""
    lock = os.path.join(profile_dir, "lockfile")
    while os.path.exists(lock):
        time.sleep(1.0)


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main(sys.argv[1:])
