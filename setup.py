from setuptools import setup
import re
import pathlib

here = pathlib.Path(__file__).parent
code = (here / "netSplit.py").read_text(encoding="utf8")
m = re.search(r'^VERSION\s*=\s*["\']([^"\']+)["\']', code, flags=re.M)
if m:
    raw = m.group(1)
    # Try to extract a numeric version (e.g. 1, 1.2, 1.2.3) from the raw value.
    ver_match = re.search(r'(\d+\.\d+\.\d+|\d+\.\d+|\d+)', raw)
    version = ver_match.group(0) if ver_match else raw
else:
    version = "0.0.0"

setup(
    version=version,
    long_description=(here / "README.md").read_text(encoding="utf8"),
    long_description_content_type="text/markdown",
)
