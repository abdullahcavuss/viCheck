"""
Creates viCheck's test VIs in testdata/ from the JKI State Machine git history.

The VIs belong to the JKI State Machine project (BSD license), so they are not stored in the viCheck
repository; this script fetches them from https://github.com/JKISoftware/JKI-State-Machine and builds
the same folders every time.

    python tools/make_testdata.py            (needs git on PATH)

Result:
    testdata/vi-pairs/<case>/A/<vi>, B/<vi>   two versions of one VI
    testdata/folders/A, testdata/folders/B    two versions of the library's source folder
    testdata/LICENSE-JKI-State-Machine.txt
"""
import os
import shutil
import subprocess
import sys
import tempfile

REPO = "https://github.com/JKISoftware/JKI-State-Machine.git"
ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "testdata")
TEMPLATE = "source/State Machine Templates/String-Based Queued State Machine (Basic 1.0).vi"

# case folder -> (commit, path); A is the commit's parent, B the commit itself
PAIRS = {
    "01_diagram-disable-to-case-structure": ("c47a9ad", TEMPLATE),
    "02_text-justification-only": ("877d99a", TEMPLATE),
    "03_comment-change": ("e3849c4", TEMPLATE),
}
# a pair taken from two commits further apart
PAIR_RANGE = {"04_subvi-added-and-reentrant": ("39cf4f4~1", "d7905a0",
                                              "source/State Machine Support API/Periodic State String.vi")}
FOLDERS = ("39cf4f4~1", "d7905a0")        # folders/A, folders/B = source/ at these commits
ONLY_A = ("39cf4f4~1", "tests/Error-State/Random String.vi")
ONLY_B = ("d7905a0", "tests/Test Utilities/SimulateButtonPress.vi")


def git(repo, *args, binary=False):
    r = subprocess.run(["git", "-C", repo] + list(args), capture_output=True, check=True)
    return r.stdout if binary else r.stdout.decode("utf-8", "replace")


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def export_tree(repo, rev, sub, dest):
    for name in git(repo, "ls-tree", "-r", "--name-only", rev, "--", sub).splitlines():
        rel = name[len(sub):].lstrip("/")
        write(os.path.join(dest, *rel.split("/")), git(repo, "show", "%s:%s" % (rev, name), binary=True))


def main():
    tmp = tempfile.mkdtemp(prefix="vicheck_jki_")
    try:
        print("Cloning", REPO)
        subprocess.run(["git", "clone", "-q", REPO, tmp], check=True)
        for case, (commit, path) in PAIRS.items():
            name = os.path.basename(path)
            write(os.path.join(ROOT, "vi-pairs", case, "A", name), git(tmp, "show", "%s~1:%s" % (commit, path), binary=True))
            write(os.path.join(ROOT, "vi-pairs", case, "B", name), git(tmp, "show", "%s:%s" % (commit, path), binary=True))
        for case, (a, b, path) in PAIR_RANGE.items():
            name = os.path.basename(path)
            write(os.path.join(ROOT, "vi-pairs", case, "A", name), git(tmp, "show", "%s:%s" % (a, path), binary=True))
            write(os.path.join(ROOT, "vi-pairs", case, "B", name), git(tmp, "show", "%s:%s" % (b, path), binary=True))
        for side, rev in zip("AB", FOLDERS):
            dest = os.path.join(ROOT, "folders", side)
            shutil.rmtree(dest, ignore_errors=True)
            export_tree(tmp, rev, "source", dest)
        rev, path = ONLY_A
        write(os.path.join(ROOT, "folders", "A", os.path.basename(path)), git(tmp, "show", "%s:%s" % (rev, path), binary=True))
        rev, path = ONLY_B
        write(os.path.join(ROOT, "folders", "B", os.path.basename(path)), git(tmp, "show", "%s:%s" % (rev, path), binary=True))
        write(os.path.join(ROOT, "folders", "B", "notes.txt"),
              "Bu dosya sadece B klasorunde var (metin dosyasi ornegi).\n".encode())
        write(os.path.join(ROOT, "LICENSE-JKI-State-Machine.txt"), git(tmp, "show", "HEAD:LICENSE", binary=True))
        print("Test VIs written to", ROOT)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError:
        sys.exit("git was not found on PATH")
    except subprocess.CalledProcessError as e:
        sys.exit("git failed: %s" % (e.stderr or b"").decode("utf-8", "replace").strip())
