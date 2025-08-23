from setuptools import setup
import re
import pathlib
import os
import subprocess

here = pathlib.Path(__file__).parent

# Prefer an explicit env var set by CI
version = os.environ.get("NETSPLIT_VERSION")
display_name = os.environ.get("RELEASE_DISPLAY_NAME")

def _candidate_from_commit_messages(max_commits=200):
    try:
        revs = subprocess.check_output(["git", "rev-list", f"--max-count={max_commits}", "HEAD"], text=True)
    except Exception:
        return None
    for rev in revs.splitlines():
        try:
            msg = subprocess.check_output(["git", "log", "-1", "--pretty=%B", rev], text=True)
        except Exception:
            continue
        first = msg.splitlines()[0].strip() if msg else ""
        if "-" in first:
            candidate = first.split("-", 1)[0].strip()
            if re.match(r"^[0-9]+[A-Za-z]?$", candidate):
                return candidate
    return None

def _map_candidate_to_version(candidate):
    m = re.match(r"^([0-9]+)([A-Za-z])?$", candidate)
    if not m:
        return candidate, "0.0"
    major = m[1]
    letter = m[2]
    minor = (ord(letter.upper()) - ord('A')) if letter else 0
    return candidate, f"{major}.{minor}"

if not version:
    cand = _candidate_from_commit_messages()
    if cand:
        disp, num = _map_candidate_to_version(cand)
        version = num
        if not display_name:
            display_name = disp

if not version:
    version = "0.0.0"

setup(
    version=version,
    description=(f"NetSplit release {display_name}" if display_name else "NetSplit"),
    long_description=(here / "README.md").read_text(encoding="utf8"),
    long_description_content_type="text/markdown",
)
