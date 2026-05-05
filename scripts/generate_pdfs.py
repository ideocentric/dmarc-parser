#!/usr/bin/env python3
"""
Generate PDF versions of the documentation using Pandoc (HTML conversion)
and Playwright's Chromium (PDF printing).

No external PDF engine needed beyond what is already installed.

Requirements (already in requirements.txt):
    playwright >= 1.45  +  playwright install chromium

Pandoc must be installed separately:
    macOS:   brew install pandoc
    Ubuntu:  sudo apt install pandoc

Usage:
    python scripts/generate_pdfs.py [options]

Options:
    --docs-dir PATH     Source markdown directory (default: docs)
    --output-dir PATH   Where to write PDFs (default: . — project root)
    --only NAME         Generate a single document by stem name
                        e.g. --only user-guide

Output files:
    user-guide.pdf
    admin-guide.pdf
    deployment-guide.pdf
    developer-guide.pdf
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

DOCS = ["user-guide", "admin-guide", "deployment-guide", "developer-guide"]

CSS = """
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 13px;
    line-height: 1.6;
    color: #1a1a1a;
    max-width: 100%;
}
h1 { font-size: 2em; border-bottom: 2px solid #e5e7eb; padding-bottom: 0.3em; }
h2 { font-size: 1.4em; border-bottom: 1px solid #e5e7eb; padding-bottom: 0.2em; margin-top: 2em; }
h3 { font-size: 1.1em; margin-top: 1.5em; }
code {
    font-family: "SF Mono", "Fira Code", Consolas, monospace;
    font-size: 0.9em;
    background: #f3f4f6;
    padding: 0.15em 0.35em;
    border-radius: 3px;
}
pre {
    background: #f3f4f6;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    padding: 1em;
    overflow-x: auto;
    font-size: 0.85em;
    line-height: 1.5;
}
pre code { background: none; padding: 0; }
table {
    border-collapse: collapse;
    width: 100%;
    margin: 1em 0;
    font-size: 0.9em;
}
th, td {
    border: 1px solid #d1d5db;
    padding: 0.5em 0.75em;
    text-align: left;
}
th { background: #f9fafb; font-weight: 600; }
tr:nth-child(even) { background: #f9fafb; }
img {
    max-width: 100%;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    margin: 0.75em 0;
    display: block;
}
blockquote {
    border-left: 4px solid #e5e7eb;
    margin: 0;
    padding: 0.5em 1em;
    color: #6b7280;
}
a { color: #2563eb; }
"""


def check_pandoc() -> None:
    if not shutil.which("pandoc"):
        print("ERROR: pandoc not found.")
        print("  macOS:  brew install pandoc")
        print("  Ubuntu: sudo apt install pandoc")
        sys.exit(1)


def md_to_html(md_path: Path, css: str) -> str:
    """Convert a markdown file to a self-contained HTML string via Pandoc."""
    result = subprocess.run(
        [
            "pandoc", str(md_path),
            "--from", "gfm",           # GitHub-flavoured Markdown
            "--to", "html5",
            "--standalone",
            "--metadata", f"title={md_path.stem.replace('-', ' ').title()}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    # Inject CSS into <head>
    html = result.stdout
    style_tag = f"<style>\n{css}\n</style>\n"
    return html.replace("</head>", f"{style_tag}</head>", 1)


def html_to_pdf(html: str, output_path: Path, base_dir: Path) -> None:
    """Render HTML to PDF using Playwright's Chromium engine."""
    # Write HTML to a temp file inside docs/ so relative image paths resolve
    tmp = (base_dir / "_tmp_print.html").resolve()
    try:
        tmp.write_text(html, encoding="utf-8")
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(tmp.as_uri(), wait_until="networkidle")
            page.pdf(
                path=str(output_path),
                format="A4",
                margin={
                    "top": "20mm",
                    "bottom": "20mm",
                    "left": "22mm",
                    "right": "22mm",
                },
                print_background=True,
            )
            browser.close()
    finally:
        tmp.unlink(missing_ok=True)


def generate(doc_stem: str, docs_dir: Path, output_dir: Path) -> None:
    md_path = docs_dir / f"{doc_stem}.md"
    if not md_path.exists():
        print(f"  SKIP  {doc_stem}.md not found")
        return

    output_path = output_dir / f"{doc_stem}.pdf"
    print(f"  {doc_stem}.md → {output_path.name} ... ", end="", flush=True)

    html = md_to_html(md_path, CSS)
    html_to_pdf(html, output_path, docs_dir)
    size_kb = output_path.stat().st_size // 1024
    print(f"done ({size_kb} KB)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--docs-dir", default="docs")
    parser.add_argument("--output-dir", default="docs/pdfs")
    parser.add_argument("--only", metavar="NAME",
                        help="Generate one document (e.g. --only user-guide)")
    args = parser.parse_args()

    check_pandoc()

    docs_dir = Path(args.docs_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    targets = [args.only] if args.only else DOCS

    print(f"\n── Generating PDFs ──")
    print(f"  Source : {docs_dir.resolve()}")
    print(f"  Output : {output_dir.resolve()}\n")

    for stem in targets:
        generate(stem, docs_dir, output_dir)

    print("\nDone.")


if __name__ == "__main__":
    main()