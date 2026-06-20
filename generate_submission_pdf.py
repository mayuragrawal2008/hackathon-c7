"""Build SUBMISSION.pdf from SUBMISSION.md (images embedded) via headless Chromium."""
import re
import html
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
img_re = re.compile(r"(evidence/[A-Za-z0-9_\-]+\.(?:jpg|jpeg|png))")

body = []
for raw in Path("SUBMISSION.md").read_text().splitlines():
    line = raw.rstrip()
    if not line.strip():
        continue
    if line.lstrip().startswith("*[") and "evidence/" in line:
        m = img_re.search(line)
        if m and (ROOT / m.group(1)).exists():
            body.append(f"<img src='file://{ROOT / m.group(1)}'/>")
        continue
    if line.startswith("# "):
        body.append(f"<h1>{html.escape(line[2:])}</h1>")
    elif line.startswith("## "):
        body.append(f"<h2>{html.escape(line[3:])}</h2>")
    elif line.startswith("### "):
        body.append(f"<h3>{html.escape(line[4:])}</h3>")
    elif line.strip() == "---":
        body.append("<hr/>")
    else:
        t = html.escape(line)
        t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
        t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
        body.append(f"<p>{t}</p>")

doc = f"""<html><head><meta charset='utf-8'><style>
body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#111;max-width:760px;
margin:0 auto;padding:24px;line-height:1.5;font-size:13px}}
h1{{color:#0b6;border-bottom:2px solid #ddd;padding-bottom:6px}}
h2{{color:#06c;margin-top:22px}} h3{{color:#333}}
img{{max-width:100%;border:1px solid #ccc;border-radius:8px;margin:8px 0}}
code{{background:#f2f2f2;padding:1px 4px;border-radius:4px;font-size:12px}}
hr{{border:none;border-top:1px solid #e2e2e2;margin:18px 0}}
p{{margin:4px 0}}</style></head><body>{''.join(body)}</body></html>"""

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    pg.set_content(doc, wait_until="load")
    pg.pdf(path="SUBMISSION.pdf", format="A4",
           margin={"top": "14mm", "bottom": "14mm", "left": "14mm", "right": "14mm"},
           print_background=True)
    b.close()
print("SUBMISSION.pdf written")
