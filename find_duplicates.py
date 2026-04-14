"""
find_duplicates.py — Detect and handle duplicate images within each vessel subfolder.

Scans images/charters/, images/sales/, and/or images_clean/ subfolders.
Runs two passes per folder:
  Pass 1 — MD5 hash   : exact byte-for-byte duplicates (fast)
  Pass 2 — pHash      : visually identical images across formats/sizes (smart)

Duplicates are NEVER auto-deleted. Default mode is report-only.
Use --move to safely relocate duplicates to a _duplicates/ subfolder for review.
Use --delete only after reviewing the report.

Usage examples:
  python find_duplicates.py                        # report only (safe, no changes)
  python find_duplicates.py --move                 # move duplicates to _duplicates/
  python find_duplicates.py --delete               # permanently delete duplicates
  python find_duplicates.py --threshold 8          # pHash sensitivity (default 6)
  python find_duplicates.py --dirs charters        # scan images/charters/ only
  python find_duplicates.py --dirs sales           # scan images/sales/ only
  python find_duplicates.py --dirs charters,sales  # scan both raw dirs (default)
  python find_duplicates.py --dirs clean           # scan images_clean/ only
  python find_duplicates.py --only "ACTA,ADVENTURE"# specific folders only
  python find_duplicates.py --move --only "ACTA"   # move dupes in ACTA only

Run from repo root:
  e:\\tfwork\\webscrapwatermarkremoval>
  WatermarkRemover-AI\\venv\\Scripts\\python.exe find_duplicates.py
"""

import argparse
import csv
import hashlib
import shutil
import sys
import time
from pathlib import Path

import imagehash
from PIL import Image, UnidentifiedImageError

# Force UTF-8 for terminals that default to cp1252
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT         = Path(__file__).parent
CHARTERS_DIR = ROOT / "images" / "charters"
SALES_DIR    = ROOT / "images" / "sales"
CLEAN_DIR    = ROOT / "images_clean"
REPORT_CSV   = ROOT / "duplicates_report.csv"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# ── Helpers ────────────────────────────────────────────────────────────────

def md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def phash(path: Path) -> imagehash.ImageHash | None:
    try:
        with Image.open(path) as img:
            return imagehash.phash(img)
    except (UnidentifiedImageError, Exception):
        return None


def best_to_keep(paths: list[Path]) -> Path:
    """
    From a group of duplicates, return the one to KEEP.
    Priority: highest resolution → largest file size → alphabetically first name.
    """
    def score(p: Path):
        try:
            with Image.open(p) as img:
                w, h = img.size
                pixels = w * h
        except Exception:
            pixels = 0
        size = p.stat().st_size
        return (pixels, size, -ord(p.name[0]))

    return max(paths, key=score)


def image_info(path: Path) -> str:
    """Return WxH string for a file, or '?' on error."""
    try:
        with Image.open(path) as img:
            return f"{img.width}x{img.height}"
    except Exception:
        return "?"


# ── Per-folder scan ────────────────────────────────────────────────────────

def scan_folder(folder: Path, threshold: int) -> list[dict]:
    """
    Scan one vessel folder. Returns list of duplicate group dicts:
      {
        "method":    "md5" | "phash",
        "keep":      Path,
        "duplicates": [Path, ...],
        "folder":    Path
      }
    """
    images = [f for f in sorted(folder.iterdir())
              if f.is_file() and f.suffix.lower() in IMAGE_EXTS]

    if len(images) < 2:
        return []

    groups = []
    already_flagged = set()

    # ── Pass 1: MD5 exact match ──────────────────────────────────────────
    md5_map: dict[str, list[Path]] = {}
    for img in images:
        h = md5(img)
        md5_map.setdefault(h, []).append(img)

    for h, group in md5_map.items():
        if len(group) > 1:
            keep = best_to_keep(group)
            dupes = [p for p in group if p != keep]
            groups.append({
                "method": "md5",
                "keep": keep,
                "duplicates": dupes,
                "folder": folder,
            })
            already_flagged.update(p for p in group)

    # ── Pass 2: pHash visual similarity ─────────────────────────────────
    # Only consider images not already caught by MD5
    remaining = [img for img in images if img not in already_flagged]

    phash_list: list[tuple[Path, imagehash.ImageHash]] = []
    for img in remaining:
        h = phash(img)
        if h is not None:
            phash_list.append((img, h))

    visited = set()
    for i, (path_a, hash_a) in enumerate(phash_list):
        if path_a in visited:
            continue
        group = [path_a]
        for path_b, hash_b in phash_list[i + 1:]:
            if path_b in visited:
                continue
            if (hash_a - hash_b) <= threshold:
                group.append(path_b)
                visited.add(path_b)
        if len(group) > 1:
            visited.add(path_a)
            keep = best_to_keep(group)
            dupes = [p for p in group if p != keep]
            groups.append({
                "method": "phash",
                "keep": keep,
                "duplicates": dupes,
                "folder": folder,
            })

    return groups


# ── Actions ────────────────────────────────────────────────────────────────

def move_duplicate(path: Path):
    dest_dir = path.parent / "_duplicates"
    dest_dir.mkdir(exist_ok=True)
    dest = dest_dir / path.name
    # Avoid name collision in _duplicates/
    if dest.exists():
        dest = dest_dir / (path.stem + "_dup" + path.suffix)
    shutil.move(str(path), str(dest))
    return dest


def delete_duplicate(path: Path):
    path.unlink()


# ── Report ─────────────────────────────────────────────────────────────────

def write_csv(all_groups: list[dict]):
    with open(REPORT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "folder", "method", "keep_file", "keep_resolution",
            "keep_size_kb", "duplicate_file", "dup_resolution", "dup_size_kb"
        ])
        for g in all_groups:
            keep = g["keep"]
            for dup in g["duplicates"]:
                writer.writerow([
                    g["folder"].name,
                    g["method"],
                    keep.name,
                    image_info(keep),
                    f"{keep.stat().st_size / 1024:.1f}",
                    dup.name,
                    image_info(dup) if dup.exists() else "moved/deleted",
                    f"{dup.stat().st_size / 1024:.1f}" if dup.exists() else "-",
                ])
    print(f"\n  CSV report saved: {REPORT_CSV}")


def print_summary(all_groups: list[dict], total_folders: int, elapsed: float):
    total_dupes  = sum(len(g["duplicates"]) for g in all_groups)
    md5_groups   = [g for g in all_groups if g["method"] == "md5"]
    phash_groups = [g for g in all_groups if g["method"] == "phash"]
    folders_hit  = len({g["folder"] for g in all_groups})

    saved_bytes = 0
    for g in all_groups:
        for d in g["duplicates"]:
            if d.exists():
                saved_bytes += d.stat().st_size

    print()
    print("=" * 62)
    print("  DUPLICATE SCAN RESULTS")
    print("=" * 62)
    print(f"  Folders scanned     : {total_folders}")
    print(f"  Folders with dupes  : {folders_hit}")
    print(f"  Total duplicate files: {total_dupes}")
    print(f"    Exact (MD5)       : {sum(len(g['duplicates']) for g in md5_groups)}")
    print(f"    Visual (pHash)    : {sum(len(g['duplicates']) for g in phash_groups)}")
    print(f"  Space recoverable   : {saved_bytes / 1e6:.1f} MB")
    print(f"  Scan time           : {elapsed:.1f}s")
    print("=" * 62)

    if all_groups:
        print(f"\n  Top folders with most duplicates:")
        from collections import Counter
        counts = Counter(g["folder"].name for g in all_groups)
        for name, count in counts.most_common(10):
            total = sum(len(g["duplicates"]) for g in all_groups if g["folder"].name == name)
            print(f"    {name}: {total} duplicate(s)")


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Find duplicate images within each vessel subfolder"
    )
    parser.add_argument(
        "--dirs", default="charters,sales",
        help="Which directories to scan: charters, sales, clean, or comma-separated (default: charters,sales)"
    )
    parser.add_argument(
        "--threshold", type=int, default=6,
        help="pHash difference threshold for visual duplicates (default: 6, range: 0-20). "
             "Lower = stricter (only near-identical). Higher = more aggressive."
    )
    parser.add_argument(
        "--move", action="store_true",
        help="Move duplicates into a _duplicates/ subfolder inside each vessel folder"
    )
    parser.add_argument(
        "--delete", action="store_true",
        help="Permanently delete duplicate files (IRREVERSIBLE — review report first)"
    )
    parser.add_argument(
        "--only", type=str, default=None,
        help="Comma-separated folder names to scan (e.g. ACTA,ADVENTURE)"
    )
    parser.add_argument(
        "--no-csv", action="store_true",
        help="Skip writing the CSV report"
    )
    args = parser.parse_args()

    if args.move and args.delete:
        print("ERROR: Use --move OR --delete, not both.")
        sys.exit(1)

    # Determine which root dirs to scan
    scan_dirs: list[Path] = []
    for d in args.dirs.split(","):
        d = d.strip().lower()
        if d == "charters":
            scan_dirs.append(CHARTERS_DIR)
        elif d == "sales":
            scan_dirs.append(SALES_DIR)
        elif d == "clean":
            scan_dirs.append(CLEAN_DIR)
        else:
            print(f"ERROR: Unknown dir '{d}'. Use charters, sales, clean, or a combination.")
            sys.exit(1)

    # Collect all vessel subfolders
    only_names = None
    if args.only:
        only_names = {n.strip().upper() for n in args.only.split(",")}

    all_folders: list[Path] = []
    for root_dir in scan_dirs:
        for folder in sorted(root_dir.iterdir()):
            if not folder.is_dir():
                continue
            if folder.name.startswith("_"):
                continue
            if only_names and folder.name.upper() not in only_names:
                continue
            all_folders.append(folder)

    total_folders = len(all_folders)

    # Choose action label
    if args.delete:
        action_label = "DELETE"
    elif args.move:
        action_label = "MOVE to _duplicates/"
    else:
        action_label = "REPORT ONLY (no files changed)"

    print(f"\n  Scanning {total_folders} folders  [action: {action_label}]")
    print(f"  pHash threshold : {args.threshold}  (0=exact visual, 20=very loose)")
    print()

    all_groups: list[dict] = []
    t_start = time.time()

    for i, folder in enumerate(all_folders, 1):
        images = [f for f in folder.iterdir()
                  if f.is_file() and f.suffix.lower() in IMAGE_EXTS]
        n = len(images)

        try:
            print(f"  [{i:>4}/{total_folders}] {folder.parent.name}/{folder.name}  ({n} images)", end="", flush=True)
        except UnicodeEncodeError:
            print(f"  [{i:>4}/{total_folders}] {folder.name.encode('ascii','replace').decode()}  ({n} images)", end="", flush=True)

        if n < 2:
            print("  — skip", flush=True)
            continue

        groups = scan_folder(folder, args.threshold)

        if not groups:
            print("  — no duplicates", flush=True)
        else:
            n_dupes = sum(len(g["duplicates"]) for g in groups)
            md5_c   = sum(len(g["duplicates"]) for g in groups if g["method"] == "md5")
            pha_c   = sum(len(g["duplicates"]) for g in groups if g["method"] == "phash")
            print(f"  — {n_dupes} duplicate(s)  [md5:{md5_c}  phash:{pha_c}]", flush=True)

            for g in groups:
                keep = g["keep"]
                for dup in g["duplicates"]:
                    method = g["method"].upper()
                    dup_info = image_info(dup) if dup.exists() else "?"
                    keep_info = image_info(keep)
                    print(f"          {method}  KEEP: {keep.name} ({keep_info})  "
                          f"DUP: {dup.name} ({dup_info})")

                    if args.delete and dup.exists():
                        delete_duplicate(dup)
                    elif args.move and dup.exists():
                        dest = move_duplicate(dup)
                        print(f"               → moved to {dest.parent.name}/{dest.name}")

            all_groups.extend(groups)

    elapsed = time.time() - t_start

    # Summary
    print_summary(all_groups, total_folders, elapsed)

    # CSV report
    if all_groups and not args.no_csv:
        write_csv(all_groups)

    if not all_groups:
        print("\n  No duplicates found.")


if __name__ == "__main__":
    main()
