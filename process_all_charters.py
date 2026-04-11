"""
Batch watermark removal for all charter image folders.

Usage:
    python process_all_charters.py [--dry-run] [--resume] [--workers N]

Processes every subfolder under images/charters/ and writes results to
images_clean/<folder_name>/.  Skips any folder that already has output
(unless --overwrite is passed).

Run from the repo root:
    e:\\tfwork\\webscrapwatermarkremoval>
    .\\WatermarkRemover-AI\\venv\\Scripts\\python.exe process_all_charters.py
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT         = Path(__file__).parent
VENV_PYTHON  = ROOT / "WatermarkRemover-AI" / "venv" / "Scripts" / "python.exe"
REMWM        = ROOT / "WatermarkRemover-AI" / "remwm.py"
IMAGES_DIR   = ROOT / "images" / "charters"
OUTPUT_DIR   = ROOT / "images_clean"
MASKS_DIR    = ROOT / "masks"
WATERMARKED  = ROOT / "watermarked"


def get_pending_folders(overwrite: bool) -> list[Path]:
    """Return charter folders that still need processing."""
    all_folders = sorted(IMAGES_DIR.iterdir())
    if overwrite:
        return all_folders

    # ACTA was processed with an inverted mask bug — always reprocess it.
    FORCE_REPROCESS = {"ACTA"}

    pending = []
    for folder in all_folders:
        if not folder.is_dir():
            continue
        if folder.name in FORCE_REPROCESS:
            pending.append(folder)
            continue
        out_folder = OUTPUT_DIR / folder.name
        # Consider done if output folder exists AND has at least one image file
        if out_folder.exists():
            existing = list(out_folder.glob("*.png")) + list(out_folder.glob("*.jpg")) + list(out_folder.glob("*.webp"))
            if existing:
                continue
        pending.append(folder)
    return pending


FORCE_REPROCESS = {"ACTA"}  # folders reprocessed unconditionally due to past bugs


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
        "--force-format", "PNG",
    ]
    # Force overwrite for folders that need reprocessing due to past bugs
    if overwrite or folder.name in FORCE_REPROCESS:
        cmd.append("--overwrite")

    if dry_run:
        print(f"  [DRY RUN] Would run: {' '.join(cmd)}")
        return True, "dry-run"

    try:
        result = subprocess.run(cmd, capture_output=False, text=True, timeout=3600)
        if result.returncode != 0:
            return False, f"exit code {result.returncode}"
        return True, "ok"
    except subprocess.TimeoutExpired:
        return False, "timeout (>1h)"
    except Exception as e:
        return False, str(e)


def main():
    parser = argparse.ArgumentParser(description="Batch remove watermarks from charter image folders")
    parser.add_argument("--dry-run",   action="store_true", help="Print commands without running them")
    parser.add_argument("--overwrite", action="store_true", help="Re-process folders that already have output")
    parser.add_argument("--only",      type=str, default=None, help="Comma-separated folder names to process (e.g. ACTA,ADVENTURE)")
    args = parser.parse_args()

    if not VENV_PYTHON.exists():
        print(f"ERROR: venv python not found at {VENV_PYTHON}")
        print("Run setup.bat first.")
        sys.exit(1)

    pending = get_pending_folders(args.overwrite)

    if args.only:
        names = {n.strip().upper() for n in args.only.split(",")}
        pending = [f for f in pending if f.name.upper() in names]

    total = len(pending)
    if total == 0:
        print("Nothing to process — all folders already have output. Use --overwrite to re-run.")
        sys.exit(0)

    print(f"Processing {total} charter folder(s)  ->  {OUTPUT_DIR}")
    print(f"Mask dir : {MASKS_DIR}")
    print(f"Device   : CPU (no CUDA detected)")
    print()

    done = 0
    failed = []
    t_start = time.time()

    for i, folder in enumerate(pending, 1):
        images_in_folder = list(folder.glob("*.webp")) + list(folder.glob("*.jpg")) + list(folder.glob("*.png"))
        n_images = len(images_in_folder)
        print(f"[{i}/{total}] {folder.name}  ({n_images} images)")

        t0 = time.time()
        ok, msg = process_folder(folder, args.overwrite, args.dry_run)
        elapsed = time.time() - t0

        if ok:
            done += 1
            print(f"         done in {elapsed:.0f}s")
        else:
            failed.append(folder.name)
            print(f"         FAILED: {msg}")

        # ETA estimate after first folder
        if i == 1 and not args.dry_run:
            eta_sec = elapsed * (total - 1)
            eta_h   = int(eta_sec // 3600)
            eta_m   = int((eta_sec % 3600) // 60)
            print(f"         ETA for remaining {total-1} folders: ~{eta_h}h {eta_m}m")

    total_elapsed = time.time() - t_start
    print()
    print("=" * 60)
    print(f"Finished: {done}/{total} folders in {total_elapsed/3600:.1f}h")
    if failed:
        print(f"Failed  : {len(failed)} folders:")
        for name in failed:
            print(f"  - {name}")
    else:
        print("No failures.")


if __name__ == "__main__":
    main()
