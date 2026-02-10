from __future__ import annotations

import json
from pathlib import Path
from typing import Dict


def export_ai_report_html(report: Dict, path: Path) -> None:
    sections = []
    for key, value in report.items():
        sections.append(f"<h2>{key}</h2><pre>{json.dumps(value, ensure_ascii=False, indent=2)}</pre>")
    html = """
    <html>
    <head><meta charset="utf-8"><title>AI 磁盘分析报告</title></head>
    <body>
    <h1>AI 磁盘分析报告</h1>
    {content}
    </body>
    </html>
    """.format(content="\n".join(sections))
    path.write_text(html, encoding="utf-8")
