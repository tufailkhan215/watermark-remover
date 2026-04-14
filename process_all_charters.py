"""
Batch watermark removal for all charter image folders.

Usage:
    python process_all_charters.py [--dry-run] [--overwrite] [--only NAME,NAME]
    python process_all_charters.py --fix-format          # re-process only folders still in old PNG format
    python process_all_charters.py --fix-format --report # report how many folders need conversion

Processes every subfolder under images/charters/ and writes results to
images_clean/<folder_name>/.  Skips folders where output count matches
source count (fully done). Retries partial folders automatically.

--fix-format: smarter resume after a crash during --overwrite.
  Checks the actual file format (PNG vs WebP) of each output folder.
  Only re-processes folders that still contain old PNG-in-webp files.
  Safe to run multiple times — already-converted folders are skipped.

Run from the repo root:
    e:\\tfwork\\webscrapwatermarkremoval>
    .\\WatermarkRemover-AI\\venv\\Scripts\\python.exe process_all_charters.py
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

# Force UTF-8 output so progress bars and Unicode folder names don't crash
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).parent
VENV_PYTHON = ROOT / "WatermarkRemover-AI" / "venv" / "Scripts" / "python.exe"
REMWM       = ROOT / "WatermarkRemover-AI" / "remwm.py"
IMAGES_DIR  = ROOT / "images" / "charters"
OUTPUT_DIR  = ROOT / "images_clean"
MASKS_DIR   = ROOT / "masks"
WATERMARKED = ROOT / "watermarked"

IMAGE_EXTS = ("*.webp", "*.jpg", "*.jpeg", "*.png")


def count_source_images(folder: Path) -> int:
    total = 0
    for ext in IMAGE_EXTS:
        total += len(list(folder.glob(ext)))
    return total


def count_output_images(folder: Path) -> int:
    out = OUTPUT_DIR / folder.name
    if not out.exists():
        return 0
    return (len(list(out.glob("*.png"))) + len(list(out.glob("*.jpg")))
            + len(list(out.glob("*.jpeg"))) + len(list(out.glob("*.webp"))))


def folder_status(folder: Path) -> str:
    """Return 'done', 'partial', or 'empty'."""
    src = count_source_images(folder)
    out = count_output_images(folder)
    if src == 0:
        return "empty-src"
    if out == 0:
        return "empty"
    if out >= src:
        return "done"
    return "partial"


def get_pending_folders(overwrite: bool) -> list[Path]:
    """Return folders that need (re)processing."""
    pending = []
    for folder in sorted(IMAGES_DIR.iterdir()):
        if not folder.is_dir():
            continue
        if overwrite:
            pending.append(folder)
            continue
        status = folder_status(folder)
        if status in ("empty", "partial"):
            pending.append(folder)
        # "done" and "empty-src" are skipped
    return pending


def output_is_old_format(folder: Path) -> bool:
    """
    Return True if the output folder still contains PNG-in-webp files (old format).
    Samples the first output file found. Returns False if folder is empty or already WebP.
    """
    from PIL import Image, UnidentifiedImageError
    out_dir = OUTPUT_DIR / folder.name
    if not out_dir.exists():
        return False
    for f in sorted(out_dir.iterdir()):
        if f.suffix.lower() in {".webp", ".png", ".jpg", ".jpeg"} and f.is_file():
            try:
                with Image.open(f) as img:
                    return img.format == "PNG"  # True = old PNG-in-webp, needs conversion
            except (UnidentifiedImageError, Exception):
                continue
    return False


def get_unconverted_folders() -> list[Path]:
    """Return folders whose output is still in old PNG-in-webp format."""
    pending = []
    for folder in sorted(IMAGES_DIR.iterdir()):
        if not folder.is_dir():
            continue
        if folder_status(folder) == "empty-src":
            continue
        if output_is_old_format(folder):
            pending.append(folder)
    return pending


def print_format_report():
    """Report how many folders are converted vs still in old PNG format."""
    from PIL import Image, UnidentifiedImageError
    converted = old_format = empty = 0
    old_folders = []

    for folder in sorted(IMAGES_DIR.iterdir()):
        if not folder.is_dir():
            continue
        out_dir = OUTPUT_DIR / folder.name
        if not out_dir.exists() or count_output_images(folder) == 0:
            empty += 1
            continue
        if output_is_old_format(folder):
            old_format += 1
            old_folders.append(folder.name)
        else:
            converted += 1

    total = converted + old_format + empty
    print("=" * 62)
    print("  FORMAT CONVERSION REPORT")
    print("=" * 62)
    print(f"  Total folders        : {total}")
    print(f"  Converted (WebP q90) : {converted}  ({converted/total*100:.1f}%)")
    print(f"  Old format (PNG)     : {old_format}  ({old_format/total*100:.1f}%)")
    print(f"  Not yet processed    : {empty}")
    print("=" * 62)
    if old_folders:
        print(f"\n  Still needs conversion ({old_format}):")
        for name in old_folders[:20]:
            print(f"    {name}")
        if len(old_folders) > 20:
            print(f"    ... and {len(old_folders)-20} more")
    print()


def process_folder(folder: Path, overwrite: bool, dry_run: bool) -> tuple[bool, str]:
    """Run remwm.py on a single charter folder. Returns (success, message)."""
    out_folder = OUTPUT_DIR / folder.name
    out_folder.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(VENV_PYTHON),
        str(REMWM),
        str(folder),
        str(out_folder),
        "--masks-dir", str(MASKS_DIR),
        "--watermarked-dir", str(WATERMARKED),
        "--force-format", "WEBP",
        "--overwrite",  # always overwrite so partial folders get completed
    ]

    if dry_run:
        print(f"  [DRY RUN] {' '.join(cmd)}")
        return True, "dry-run"

    # Pass UTF-8 encoding to subprocess so tqdm/loguru don't crash on Unicode
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONLEGACYWINDOWSSTDIO"] = "0"
    # Force offline mode — Florence-2 (1.67 GB) is fully cached locally.
    # Without this, from_pretrained() pings HuggingFace Hub on EVERY folder,
    # causing rate-limit failures and random stops after ~100 folders.
    env["TRANSFORMERS_OFFLINE"] = "1"
    env["HF_HUB_OFFLINE"] = "1"

    try:
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=False,
            timeout=7200,  # 2h max per folder
        )
        if result.returncode != 0:
            return False, f"exit code {result.returncode}"
        return True, "ok"
    except subprocess.TimeoutExpired:
        return False, "timeout (>2h)"
    except Exception as e:
        return False, str(e)


def print_progress_report():
    """Print a full progress report of images_clean vs images/charters."""
    all_folders = sorted(f for f in IMAGES_DIR.iterdir() if f.is_dir())
    done_count = partial_count = empty_count = 0
    done_imgs = total_imgs = 0
    partial_folders = []

    for folder in all_folders:
        src = count_source_images(folder)
        out = count_output_images(folder)
        total_imgs += src
        done_imgs += out
        status = folder_status(folder)
        if status == "done":
            done_count += 1
        elif status == "partial":
            partial_count += 1
            partial_folders.append((folder.name, out, src))
        else:
            empty_count += 1

    total_folders = len(all_folders)
    print("=" * 62)
    print("  PROGRESS REPORT")
    print("=" * 62)
    print(f"  Charter folders  : {total_folders}")
    print(f"  Fully done       : {done_count}  ({done_count/total_folders*100:.1f}%)")
    print(f"  Partial (some)   : {partial_count}")
    print(f"  Not started      : {empty_count}")
    print(f"  Images processed : {done_imgs} / {total_imgs}  ({done_imgs/total_imgs*100:.1f}%)")
    print("=" * 62)
    if partial_folders:
        print(f"\n  Partial folders ({partial_count}):")
        for name, out, src in partial_folders[:20]:
            pct = out / src * 100
            print(f"    {name}: {out}/{src} ({pct:.0f}%)")
        if len(partial_folders) > 20:
            print(f"    ... and {len(partial_folders)-20} more")
    print()


def main():
    parser = argparse.ArgumentParser(description="Batch remove watermarks from charter image folders")
    parser.add_argument("--dry-run",    action="store_true", help="Print commands without running them")
    parser.add_argument("--overwrite",  action="store_true", help="Re-process fully-done folders too")
    parser.add_argument("--report",     action="store_true", help="Print progress report and exit")
    parser.add_argument("--fix-format", action="store_true", help="Re-process only folders still in old PNG-in-webp format")
    parser.add_argument("--only",       type=str, default=None, help="Comma-separated folder names to process")
    args = parser.parse_args()

    if not VENV_PYTHON.exists():
        print(f"ERROR: venv python not found at {VENV_PYTHON}")
        print("Run setup.bat first.")
        sys.exit(1)

    if args.fix_format:
        print_format_report()
        if args.report:
            return
        pending = get_unconverted_folders()
    else:
        print_progress_report()
        if args.report:
            return
        pending = get_pending_folders(args.overwrite)

    if args.only:
        names = {n.strip().upper() for n in args.only.split(",")}
        pending = [f for f in pending if f.name.upper() in names]

    total = len(pending)
    if total == 0:
        print("Nothing to process — all folders complete. Use --overwrite to re-run.")
        return

    print(f"Processing {total} pending folder(s)  ->  {OUTPUT_DIR}")
    print(f"Mask dir  : {MASKS_DIR}")
    print()

    done_run = 0
    failed = []
    t_start = time.time()

    for i, folder in enumerate(pending, 1):
        src = count_source_images(folder)
        out = count_output_images(folder)
        status = folder_status(folder)
        tag = f"partial {out}/{src}" if status == "partial" else f"{src} images"

        try:
            print(f"[{i}/{total}] {folder.name}  ({tag})", flush=True)
        except UnicodeEncodeError:
            print(f"[{i}/{total}] {folder.name.encode('ascii', 'replace').decode()}  ({tag})", flush=True)

        t0 = time.time()
        ok, msg = process_folder(folder, args.overwrite, args.dry_run)
        elapsed = time.time() - t0

        if ok:
            done_run += 1
            out_after = count_output_images(folder)
            print(f"         done in {elapsed:.0f}s  ({out_after}/{src} images)", flush=True)
        else:
            failed.append(folder.name)
            out_after = count_output_images(folder)
            print(f"         FAILED: {msg}  ({out_after}/{src} images saved)", flush=True)

        # ETA after first folder
        if i == 1 and not args.dry_run and elapsed > 5:
            eta_sec = elapsed * (total - 1)
            eta_h   = int(eta_sec // 3600)
            eta_m   = int((eta_sec % 3600) // 60)
            print(f"         ETA for remaining {total-1} folders: ~{eta_h}h {eta_m}m", flush=True)

    total_elapsed = time.time() - t_start
    print()
    print("=" * 62)
    print(f"Run complete: {done_run}/{total} folders in {total_elapsed/3600:.1f}h")
    if failed:
        print(f"Failed ({len(failed)}):")
        for name in failed:
            try:
                print(f"  - {name}")
            except UnicodeEncodeError:
                print(f"  - {name.encode('ascii', 'replace').decode()}")
    else:
        print("No failures.")
    print()
    print_progress_report()


if __name__ == "__main__":
    main()
