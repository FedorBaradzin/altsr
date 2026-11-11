#!/usr/bin/env python3
"""Replace the <script id="altsr-x-js"> block in the landing index.html with a new
one (time-based continuous numbers + token auto-rotation).

Usage: python3 swap_altsr_x.py <new_script_html_file> <index_html>
- Removes ALL existing <script id="altsr-x-js">...</script> blocks.
- Inserts the new block (verbatim contents of new_script_html_file) before </body>.
Leaves altsr-final-js and everything else untouched.
"""
from __future__ import annotations
import re
import sys

NEW_PATH, DST_PATH = sys.argv[1], sys.argv[2]

with open(NEW_PATH, encoding="utf-8") as f:
    new_block = f.read().strip()
with open(DST_PATH, encoding="utf-8") as f:
    dst = f.read()

pat = re.compile(
    r'<script\b[^>]*\bid=["\']altsr-x-js["\'][^>]*>.*?</script>',
    re.DOTALL | re.IGNORECASE,
)
dst, n = pat.subn("", dst)
print(f"removed {n} old altsr-x-js block(s)")

if "</body>" in dst:
    dst = dst.replace("</body>", "\n" + new_block + "\n</body>", 1)
else:
    dst = dst + "\n" + new_block + "\n"

with open(DST_PATH, "w", encoding="utf-8") as f:
    f.write(dst)

has_x = len(re.findall(r'id=["\']altsr-x-js["\']', dst))
has_final = len(re.findall(r'id=["\']altsr-final-js["\']', dst))
has_dt = dst.count("data-dt")
print(f"after: altsr-x-js={has_x} altsr-final-js={has_final} data-dt={has_dt}")
