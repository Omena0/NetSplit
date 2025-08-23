from setuptools import setup
import re
import pathlib

here = pathlib.Path(__file__).parent
code = (here / "netSplit.py").read_text(encoding="utf8")
m = re.search(r'^VERSION\s*=\s*["\']([^"\']+)["\']', code, flags=re.M)
rd = re.search(r'^RELEASE_DISPLAY_NAME\s*=\s*["\']([^"\']+)["\']', code, flags=re.M)
if m:
    raw = m.group(1)
    version = raw
else:
    version = "0.0.0"

display_name = rd[1] if rd else None

setup(
    version=version,
    description=(f"NetSplit release {display_name}" if display_name else "NetSplit"),
    long_description=(here / "README.md").read_text(encoding="utf8"),
    long_description_content_type="text/markdown",
)
