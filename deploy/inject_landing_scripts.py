#!/usr/bin/env python3
"""Re-inject the server-only landing enhancement scripts (altsr-final-js builds the
video-tour block + live-profit-numbers strip; altsr-x-js animates them) into the
current landing index.html, which has the button/login/tab fixes but lost those
scripts after a repo rebuild.

Usage: python3 inject_landing_scripts.py <SRC_with_scripts> <DST_current_index>
Idempotent: skips a script id already present in DST. Inserts before </body>.
"""
from __future__ import annotations
import re
import sys

IDS = ["altsr-final-js", "altsr-x-js"]


def extract(src_html: str, script_id: str) -> str | None:
    # <script ... id="altsr-final-js" ...> ... </script>  (DOTALL, non-greedy)
    m = re.search(
        r'<script\b[^>]*\bid=["\']' + re.escape(script_id) + r'["\'][^>]*>.*?</script>',
        src_html,
        re.DOTALL | re.IGNORECASE,
    )
    return m.group(0) if m else None


def main() -> int:
    src_path, dst_path = sys.argv[1], sys.argv[2]
    with open(src_path, encoding="utf-8") as f:
        src = f.read()
    with open(dst_path, encoding="utf-8") as f:
        dst = f.read()

    blocks = []
    for sid in IDS:
        if re.search(r'\bid=["\']' + re.escape(sid) + r'["\']', dst):
            print(f"SKIP {sid}: already present in DST")
            continue
        block = extract(src, sid)
        if not block:
            print(f"WARN {sid}: not found in SRC")
            continue
        blocks.append(block)
        print(f"OK   {sid}: extracted {len(block)} bytes")

    if not blocks:
        print("NOTHING_TO_INJECT")
        return 0

    inject = "\n" + "\n".join(blocks) + "\n"
    if "</body>" in dst:
        dst = dst.replace("</body>", inject + "</body>", 1)
    else:
        dst = dst + inject
    with open(dst_path, "w", encoding="utf-8") as f:
        f.write(dst)
    print(f"INJECTED {len(blocks)} script(s) into {dst_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
