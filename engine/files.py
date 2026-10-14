"""Files on disk: hashing, folder scanning, the content registry and primitive names.

viCheck never writes to the files or folders it compares. Every file it parses is first
copied to a private temporary folder, and the copy is checked against the hash taken when
the comparison was made.
"""
import fnmatch
import hashlib
import json
import os
import shutil
import threading

DEFAULT_IGNORE = [
    ".git/", ".svn/", ".hg/", ".viver/",
    "*.lvlps", "*.aliases", "*.lvbitx.tmp",
    "*.bak", "*.tmp", "~$*", "Thumbs.db", ".DS_Store", "desktop.ini",
]

VI_EXT = (".vi", ".vit", ".ctl", ".ctt", ".vim")
TEXT_EXT = (".lvproj", ".lvlib", ".lvclass", ".xctl", ".lvsc", ".lvtest", ".xml", ".txt", ".md", ".ini",
            ".csv", ".json", ".py", ".m", ".c", ".h", ".cpp", ".cs", ".bat", ".sh", ".cfg", ".yml", ".yaml",
            ".html", ".css", ".js", ".vipb", ".lvtst", ".gitignore")


class CompareError(Exception):
    pass


# ---------------------------------------------------------------- small helpers
def is_vi(path):
    return path.lower().endswith(VI_EXT)


def is_text(path, data=None):
    if path.lower().endswith(TEXT_EXT):
        return True
    if data is not None and len(data) < 2_000_000:
        sample = data[:4096]
        if b"\x00" in sample:
            return False
        try:
            sample.decode("utf-8")
            return True
        except UnicodeDecodeError:
            return False
    return False


def file_kind(path):
    p = path.lower()
    if p.endswith((".vi", ".vit", ".vim")):
        return "vi"
    if p.endswith((".ctl", ".ctt")):
        return "ctl"
    if p.endswith(".lvproj"):
        return "proj"
    if p.endswith((".lvlib", ".lvclass", ".xctl", ".lvsc")):
        return "lib"
    if p.endswith(".llb"):
        return "llb"
    return "file"


def human_size(n):
    n = n or 0
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%d %s" % (n, unit)) if unit == "B" else ("%.1f %s" % (n, unit))
        n /= 1024.0


def is_ignored(relpath, rules):
    parts = relpath.split("/")
    name = parts[-1]
    for r in rules:
        if r.endswith("/"):
            d = r.rstrip("/")
            if d in parts[:-1] or any(fnmatch.fnmatch(p, d) for p in parts[:-1]):
                return True
        elif "/" in r:
            if fnmatch.fnmatch(relpath, r.lstrip("/")):
                return True
        elif fnmatch.fnmatch(name, r):
            return True
    return False


def parse_rules(text):
    return [l.strip() for l in (text or "").replace(",", "\n").splitlines() if l.strip() and not l.strip().startswith("#")]


def diff_trees(old, new, include_same=False):
    """Compares two {relpath: (sha, size)} trees. Same-content moves are reported as 'renamed'."""
    out = []
    for p in sorted(set(old) | set(new), key=str.lower):
        a, b = old.get(p), new.get(p)
        if a and not b:
            out.append({"path": p, "status": "deleted", "old_sha": a[0], "new_sha": None, "old_size": a[1], "new_size": 0})
        elif b and not a:
            out.append({"path": p, "status": "added", "old_sha": None, "new_sha": b[0], "old_size": 0, "new_size": b[1]})
        elif a[0] != b[0]:
            out.append({"path": p, "status": "modified", "old_sha": a[0], "new_sha": b[0], "old_size": a[1], "new_size": b[1]})
        elif include_same:
            out.append({"path": p, "status": "same", "old_sha": a[0], "new_sha": b[0], "old_size": a[1], "new_size": b[1]})
    # rename detection: the same content was deleted in one place and added in another
    deleted = {}
    for c in out:
        if c["status"] == "deleted":
            deleted.setdefault(c["old_sha"], c)
    renamed, used = [], set()
    for c in out:
        if c["status"] == "added" and c["new_sha"] in deleted and c["new_sha"] not in used:
            d = deleted[c["new_sha"]]
            used.add(c["new_sha"])
            c["_gone"] = d["_gone"] = True
            renamed.append({"path": c["path"], "old_path": d["path"], "status": "renamed", "old_sha": d["old_sha"],
                            "new_sha": c["new_sha"], "old_size": d["old_size"], "new_size": c["new_size"]})
    final = [c for c in out if not c.pop("_gone", False)] + renamed
    final.sort(key=lambda c: c["path"].lower())
    for c in final:
        c["kind"] = file_kind(c["path"])
        c["is_vi"] = is_vi(c["path"])
    return final


# ---------------------------------------------------------------- the registry
class LocalStore:
    """Maps content hashes to files on disk and keeps the app's own data (cache, names, recents).

    The parser/diff service asks for content by hash; we answer from the file that had that
    hash when it was scanned, and refuse if it has changed since.
    """

    def __init__(self, data_dir):
        self.data_dir = os.path.abspath(data_dir)
        self.cache_dir = os.path.join(self.data_dir, "cache")
        self.export_dir = os.path.join(self.data_dir, "exports")
        os.makedirs(self.cache_dir, exist_ok=True)
        self._paths = {}          # sha -> set(abs paths)
        self._hash_cache = {}     # (path, size, mtime_ns) -> sha
        self._lock = threading.Lock()
        self.names_path = os.path.join(self.data_dir, "prim_names.json")
        self.recent_path = os.path.join(self.data_dir, "recent.json")
        self.settings_path = os.path.join(self.data_dir, "settings.json")
        self._names = self._load_json(self.names_path, {})

    # ------------------------------------------------------------ json helpers
    @staticmethod
    def _load_json(path, default):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return default

    @staticmethod
    def _save_json(path, data):
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)

    # ------------------------------------------------------------ hashing
    def hash_file(self, full):
        st = os.stat(full)
        key = (full, st.st_size, st.st_mtime_ns)
        sha = self._hash_cache.get(key)
        if sha is None:
            h = hashlib.sha256()
            with open(full, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            sha = h.hexdigest()
            self._hash_cache[key] = sha
        with self._lock:
            self._paths.setdefault(sha, set()).add(full)
        return sha, st.st_size

    def register(self, full):
        return self.hash_file(os.path.abspath(full))[0]

    def scan_folder(self, root, rules=None, progress=None):
        """{relpath: (sha, size)} for every file below root that is not ignored."""
        root = os.path.abspath(root)
        if not os.path.isdir(root):
            raise CompareError("Folder not found: " + root)
        rules = list(DEFAULT_IGNORE) + list(rules or [])
        tree = {}
        for dirpath, dirnames, filenames in os.walk(root):
            rel_dir = os.path.relpath(dirpath, root).replace("\\", "/")
            rel_dir = "" if rel_dir == "." else rel_dir
            dirnames[:] = sorted(d for d in dirnames if not is_ignored((rel_dir + "/" if rel_dir else "") + d + "/x", rules))
            for fn in sorted(filenames):
                rel = (rel_dir + "/" if rel_dir else "") + fn
                if is_ignored(rel, rules):
                    continue
                full = os.path.join(dirpath, fn)
                try:
                    tree[rel] = self.hash_file(full)
                except OSError:
                    continue
                if progress:
                    progress(len(tree), rel)
        return tree

    # ------------------------------------------------------------ content by hash
    def _source(self, sha):
        with self._lock:
            paths = list(self._paths.get(sha, ()))
        for p in paths:
            try:
                if os.path.exists(p) and self.hash_file(p)[0] == sha:
                    return p
            except OSError:
                continue
        raise CompareError("The file for this comparison has changed or is missing on disk. Run the comparison again.")

    def has(self, sha):
        with self._lock:
            return sha in self._paths

    def path_of(self, sha):
        return self._source(sha)

    def get_blob(self, sha, verify=False):
        with open(self._source(sha), "rb") as f:
            data = f.read()
        if hashlib.sha256(data).hexdigest() != sha:
            raise CompareError("The file changed while it was being read. Run the comparison again.")
        return data

    def blob_to_file(self, sha, dest):
        """Private copy for the parser; the copy is verified against the hash."""
        src = self._source(sha)
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        shutil.copyfile(src, dest)
        h = hashlib.sha256()
        with open(dest, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        if h.hexdigest() != sha:
            raise CompareError("The file changed while it was being copied. Run the comparison again.")

    # ------------------------------------------------------------ primitive names
    def prim_names(self):
        return {k: v["name"] for k, v in self._names.items()}

    def prim_name_rows(self):
        return [{"res_id": k, "name": v["name"], "source": v.get("source", "user")} for k, v in self._names.items()]

    def set_prim_name(self, res_id, name, source="user"):
        res_id = str(res_id).strip()
        name = (name or "").strip()
        with self._lock:
            if not name:
                self._names.pop(res_id, None)
            else:
                self._names[res_id] = {"name": name[:60], "source": source}
            self._save_json(self.names_path, self._names)

    def import_prim_names(self, mapping, source):
        n = 0
        with self._lock:
            for rid, name in mapping.items():
                cur = self._names.get(rid)
                if cur and cur.get("source", "user") == "user":
                    continue
                self._names[rid] = {"name": name[:60], "source": source}
                n += 1
            self._save_json(self.names_path, self._names)
        return n

    # ------------------------------------------------------------ recent comparisons / settings
    def recent(self):
        return self._load_json(self.recent_path, [])

    def add_recent(self, a, b, kind):
        items = [r for r in self.recent() if not (r["a"] == a and r["b"] == b)]
        items.insert(0, {"a": a, "b": b, "kind": kind})
        self._save_json(self.recent_path, items[:12])

    def clear_recent(self):
        self._save_json(self.recent_path, [])

    def settings(self):
        s = {"ignore": "", "auto_prims": True}
        s.update(self._load_json(self.settings_path, {}))
        return s

    def save_settings(self, **kw):
        s = self.settings()
        s.update(kw)
        self._save_json(self.settings_path, s)
        return s
