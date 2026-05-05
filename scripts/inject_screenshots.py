#!/usr/bin/env python3
"""
Replace screenshot placeholder blocks in documentation with actual image tags.

Finds blocks of the form:
    > **📸 Screenshot needed:** `[SS-U-01] Description`
    > *Navigation: ...*
    > Further description...

And replaces them with:
    ![Description](images/ss-u-01-login.png)

Only replaces a placeholder if the corresponding image file exists in docs/images/.
Reports any placeholders whose images are still missing.

Usage:
    python scripts/inject_screenshots.py [--docs-dir docs] [--dry-run]
"""
import argparse
import re
import sys
from pathlib import Path

# Maps screenshot IDs (lower-case) to image filenames — matches capture_screenshots.py
FILENAME_MAP = {
    "ss-u-01": "ss-u-01-login.png",
    "ss-u-02": "ss-u-02-mfa-screen.png",
    "ss-u-03": "ss-u-03-dashboard-overview.png",
    "ss-u-04": "ss-u-04-stat-cards.png",
    "ss-u-05": "ss-u-05-world-map-tooltip.png",
    "ss-u-06": "ss-u-06-reports-list.png",
    "ss-u-07": "ss-u-07-report-detail.png",
    "ss-u-08": "ss-u-08-records-table-badges.png",
    "ss-u-09": "ss-u-09-record-expanded.png",
    "ss-u-10": "ss-u-10-flags-list.png",
    "ss-u-11": "ss-u-11-flag-type-tooltip.png",
    "ss-u-12": "ss-u-12-analytics-top-ips.png",
    "ss-u-13": "ss-u-13-user-menu.png",
    "ss-u-14": "ss-u-14-change-password.png",
    "ss-u-15": "ss-u-15-mfa-setup-qr.png",
    "ss-u-16": "ss-u-16-mfa-disable.png",
    "ss-a-01": "ss-a-01-flag-acknowledge.png",
    "ss-a-02": "ss-a-02-users-list.png",
    "ss-a-03": "ss-a-03-create-user-form.png",
    "ss-a-04": "ss-a-04-reset-password.png",
    "ss-a-05": "ss-a-05-clients-card-expanded.png",
    "ss-a-06": "ss-a-06-add-domain.png",
    "ss-a-07": "ss-a-07-imap-empty-state.png",
    "ss-a-08": "ss-a-08-imap-standard-form.png",
    "ss-a-09": "ss-a-09-imap-m365-form.png",
    "ss-a-10": "ss-a-10-imap-test-connection.png",
}

# Matches the first line of a placeholder block, e.g.:
#   > **📸 Screenshot needed:** `[SS-U-01] Login page`
_FIRST_LINE_RE = re.compile(
    r'^> \*\*📸 Screenshot needed:\*\* `\[(?P<id>SS-[AU]-\d+)\]\s*(?P<desc>[^`]*)`\s*$',
    re.MULTILINE,
)


def _extract_blocks(text: str) -> list[tuple[int, int, str, str]]:
    """
    Return list of (start, end, shot_id, description) for every placeholder block.
    A block is the first matching line plus all immediately following lines that
    start with '>'.
    """
    results = []
    for m in _FIRST_LINE_RE.finditer(text):
        shot_id = m.group("id").lower()
        desc = m.group("desc").strip()
        block_start = m.start()

        # Walk forward to consume all consecutive "> ..." lines
        pos = m.end()
        # Skip the newline at end of first line
        if pos < len(text) and text[pos] == "\n":
            pos += 1
        while pos < len(text):
            line_end = text.find("\n", pos)
            line_end = line_end if line_end != -1 else len(text)
            line = text[pos:line_end]
            if line.startswith(">"):
                pos = line_end + 1
            else:
                break

        block_end = pos
        # Trim any trailing blank line that was absorbed
        results.append((block_start, block_end, shot_id, desc))

    return results


def process_file(md_path: Path, images_dir: Path, dry_run: bool) -> tuple[int, int]:
    """
    Process one markdown file.
    Returns (replaced_count, missing_count).
    """
    text = md_path.read_text(encoding="utf-8")
    blocks = _extract_blocks(text)

    if not blocks:
        return 0, 0

    replaced = 0
    missing = 0
    # Process in reverse order so character offsets stay valid
    for start, end, shot_id, desc in reversed(blocks):
        filename = FILENAME_MAP.get(shot_id)
        if not filename:
            print(f"  WARN  {shot_id}: not in FILENAME_MAP — skipping")
            missing += 1
            continue

        image_path = images_dir / filename
        if not image_path.exists():
            print(f"  SKIP  {shot_id}: image not found ({image_path.name})")
            missing += 1
            continue

        # Build the replacement image tag
        alt = desc if desc else shot_id.upper()
        replacement = f"![{alt}](images/{filename})\n"

        if dry_run:
            print(f"  DRY   {shot_id} → {filename}  (would replace {end - start} chars)")
        else:
            text = text[:start] + replacement + text[end:]
            print(f"  OK    {shot_id} → {filename}")
        replaced += 1

    if not dry_run and replaced:
        md_path.write_text(text, encoding="utf-8")

    return replaced, missing


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--docs-dir", default="docs",
                        help="Directory containing the markdown files (default: docs)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would change without writing any files")
    args = parser.parse_args()

    docs_dir = Path(args.docs_dir)
    images_dir = docs_dir / "images"

    if not docs_dir.exists():
        print(f"ERROR: docs directory not found: {docs_dir}")
        sys.exit(1)

    if not images_dir.exists():
        print(f"ERROR: images directory not found: {images_dir}")
        print("Run: python scripts/capture_screenshots.py")
        sys.exit(1)

    md_files = sorted(docs_dir.glob("*.md"))
    if not md_files:
        print(f"No .md files found in {docs_dir}")
        sys.exit(0)

    total_replaced = 0
    total_missing = 0

    for md_path in md_files:
        if md_path.name == "README.md":
            continue   # README documents the process; don't modify it
        print(f"\n{md_path.name}")
        replaced, missing = process_file(md_path, images_dir, args.dry_run)
        total_replaced += replaced
        total_missing += missing
        if replaced == 0 and missing == 0:
            print("  (no placeholders found)")

    print(f"\n── Summary ──")
    if args.dry_run:
        print(f"  Would replace : {total_replaced}")
    else:
        print(f"  Replaced      : {total_replaced}")
    print(f"  Still missing : {total_missing}")

    if total_missing:
        print("\n  Run to capture missing images:")
        print("  python scripts/capture_screenshots.py")

    if total_missing and not args.dry_run:
        sys.exit(1)


if __name__ == "__main__":
    main()