# process_all_charters.py — Full Documentation

---

## Overview

`process_all_charters.py` is a batch processing script that removes watermarks from
all yacht charter images. It iterates every vessel folder inside `images/charters/`,
calls the AI watermark removal engine (`remwm.py`) on each one, and writes clean PNG
output to `images_clean/`. It is resumable — interrupted runs pick up exactly where
they left off.

---

## Project Root Structure

```
e:\tfwork\webscrapwatermarkremoval\
│
├── process_all_charters.py       ← THIS SCRIPT (run from here)
│
├── images\
│   ├── charters\                 ← SOURCE: 452 vessel subfolders
│   │   ├── ACTA\
│   │   │   ├── 001.webp
│   │   │   ├── 002.webp
│   │   │   └── ...
│   │   ├── ADVENTURE\
│   │   ├── AELIA\
│   │   └── ... (452 folders total)
│   │
│   └── sales\                    ← SOURCE: sales images (separate dataset)
│       ├── 2008 BENETTI CLASSIC 120\
│       └── ... (404 folders)
│
├── images_clean\                 ← OUTPUT: processed PNG images written here
│   ├── ACTA\
│   │   ├── 001.png
│   │   ├── 002.png
│   │   └── ...
│   ├── ADVENTURE\
│   └── ... (mirrors charters structure)
│
├── masks\                        ← Reference watermark masks
│   ├── mask0.png                 ← Primary mask (black=watermark, white=background)
│   └── mask0.jpg                 ← JPEG copy of same mask
│
├── watermarked\                  ← Example watermarked image for template matching
│   └── watermarked0.jpg
│
└── WatermarkRemover-AI\          ← AI engine (see below)
```

---

## WatermarkRemover-AI Engine Structure

```
WatermarkRemover-AI\
│
├── remwm.py           ← Core CLI: detect watermark → create mask → inpaint
├── remwmgui.py        ← GUI wrapper (pywebview)
├── utils.py           ← Florence-2 helper functions
├── requirements.txt   ← Python dependencies
│
├── setup.bat          ← Windows setup (installs venv + dependencies + models)
├── setup.sh           ← Linux/macOS setup
├── setup.ps1          ← PowerShell setup
│
├── run.bat            ← Windows launcher (activates venv + starts GUI)
├── run.sh             ← Linux/macOS launcher
├── launch.bat         ← Alternative Windows launcher
│
├── ui\                ← Web UI assets (HTML/CSS/JS served by pywebview)
│   ├── index.html
│   ├── themes.css
│   ├── config.json
│   └── lang\
│
├── masks\             ← Local copy of reference masks (same as root masks\)
│
└── venv\              ← Python virtual environment (created by setup)
    └── Scripts\
        └── python.exe ← Python interpreter used for all processing
```

---

## How the Script Works — Step by Step

```
process_all_charters.py
        │
        ├─ 1. SCAN  images\charters\  — find all vessel subfolders
        │
        ├─ 2. STATUS CHECK per folder:
        │       "done"      — output image count >= source image count  → SKIP
        │       "partial"   — some output exists but count < source     → RETRY
        │       "empty"     — no output at all                          → PROCESS
        │       "empty-src" — source folder has no images               → SKIP
        │
        ├─ 3. For each pending folder, call remwm.py:
        │       python remwm.py  <input_folder>  <output_folder>
        │                        --masks-dir     masks\
        │                        --watermarked-dir watermarked\
        │                        --force-format  PNG
        │                        --overwrite
        │
        └─ 4. Print progress report on completion
```

### Inside remwm.py (what happens per image)

```
For each image in folder:
    1. Load Florence-2-large model  (AI vision — detects watermark location)
    2. Load LaMA model              (AI inpainting — reconstructs pixels)
    3. Load reference mask          (masks\mask0.png)
    4. Scale mask to image size     (proportional bbox scaling)
    5. Dilate mask by 8px           (smoother blend at edges)
    6. Run LaMA inpainting          (fills watermark region with sea texture)
    7. Save result as PNG           → images_clean\<vessel>\<image>.png
```

---

## Folder Status Logic

| Condition | Status | Action |
|---|---|---|
| Source images = 0 | `empty-src` | Skip always |
| Output images = 0 | `empty` | Process |
| Output < Source | `partial` | Retry (resume from beginning with --overwrite) |
| Output >= Source | `done` | Skip (unless --overwrite passed) |

---

## All Run Commands

> All commands run from: `e:\tfwork\webscrapwatermarkremoval\`
> Python interpreter: `WatermarkRemover-AI\venv\Scripts\python.exe`

---

### Normal run — process all pending folders
```cmd
WatermarkRemover-AI\venv\Scripts\python.exe process_all_charters.py
```
Processes all `empty` and `partial` folders. Skips `done` ones.
Safe to run multiple times — resumes from where it left off.

---

### Progress report only — no processing
```cmd
WatermarkRemover-AI\venv\Scripts\python.exe process_all_charters.py --report
```
Prints a snapshot of how many folders are done / partial / not started,
and what % of total images have been processed. Does not start any jobs.

**Sample output:**
```
==============================================================
  PROGRESS REPORT
==============================================================
  Charter folders  : 451
  Fully done       : 127  (28.2%)
  Partial (some)   : 2
  Not started      : 322
  Images processed : 5688 / 20106  (28.3%)
==============================================================

  Partial folders (2):
    AZTECA: 1/50 (2%)
    BABBO: 47/54 (87%)
```

---

### Dry run — preview what would be processed (no actual work)
```cmd
WatermarkRemover-AI\venv\Scripts\python.exe process_all_charters.py --dry-run
```
Prints the report, then shows every command that would be executed without
actually running anything. Use this to verify which folders are queued.

---

### Process specific folders only
```cmd
WatermarkRemover-AI\venv\Scripts\python.exe process_all_charters.py --only "ACTA,ADVENTURE"
```
Restricts processing to the named folders. Names are case-insensitive.
Multiple names separated by commas. Still skips folders already done.

---

### Force re-process already completed folders
```cmd
WatermarkRemover-AI\venv\Scripts\python.exe process_all_charters.py --overwrite
```
Runs ALL 452 folders from scratch, even ones already done. Use this if
you change the mask, update the AI models, or want fresh results.

---

### Combine flags — dry run for specific folders
```cmd
WatermarkRemover-AI\venv\Scripts\python.exe process_all_charters.py --only "AZTECA,BABBO" --dry-run
```

### Combine flags — force specific folders only
```cmd
WatermarkRemover-AI\venv\Scripts\python.exe process_all_charters.py --only "AZTECA" --overwrite
```

---

## Live Progress Monitoring (while a run is active)

When the script runs in the background, output goes to a log file.
Use these PowerShell commands to watch it live:

### Stream all output (full detail)
```powershell
Get-Content "C:\Users\ORGANI~1\AppData\Local\Temp\claude\e--tfwork-webscrapwatermarkremoval\509e523e-d1b6-4c6a-a472-a2c98510280c\tasks\bnnx4fl6m.output" -Wait -Tail 5
```

### Folder-level progress only (clean view)
```powershell
Get-Content "C:\Users\ORGANI~1\AppData\Local\Temp\claude\e--tfwork-webscrapwatermarkremoval\509e523e-d1b6-4c6a-a472-a2c98510280c\tasks\bnnx4fl6m.output" -Wait -Tail 20 | Select-String "\[.*\/323\]|done in|FAILED|PROGRESS"
```

### Quick count of completed folders
```powershell
(Get-ChildItem "e:\tfwork\webscrapwatermarkremoval\images_clean" -Directory | Where-Object { (Get-ChildItem $_.FullName).Count -gt 0 }).Count
```

---

## Image Formats Supported

| Input formats accepted | Output format |
|---|---|
| `.webp` `.jpg` `.jpeg` `.png` | Always `.png` (forced by `--force-format PNG`) |

---

## Reference Files Used Per Run

| File | Purpose |
|---|---|
| `masks\mask0.png` | Primary reference — defines watermark bounding box (black pixels = watermark area) |
| `masks\mask0.jpg` | JPEG copy of same mask (fallback) |
| `watermarked\watermarked0.jpg` | Example watermarked image for template matching context |

The mask was created from a 1024×683 source image. For images of different sizes,
the script proportionally scales the watermark bounding box to match.

---

## Timeout and Safety

- Per-folder timeout: **2 hours** (7200s) — if a folder takes longer, it is
  marked FAILED and the script continues with the next one
- The script never deletes source images
- Output is always written to `images_clean\` — original `images\` is never touched
- If the script is interrupted (Ctrl+C, power loss, etc.), re-running it automatically
  resumes from the next unfinished folder

---

## Common Issues and Fixes

| Symptom | Cause | Fix |
|---|---|---|
| `FAILED: exit code 1` on many folders | Unicode characters in stdout (tqdm block chars can't encode to cp1252) | Fixed — script sets `PYTHONIOENCODING=utf-8` for every subprocess |
| Partial folder not retried | Old logic: any output = "done" | Fixed — now compares output count vs source count |
| Script crashes on folder like `SPIRIT OF THE C'S` | Special Unicode char in folder name | Fixed — `sys.stdout.reconfigure(encoding="utf-8")` at startup |
| Glowing blob artifacts in output images | Mask was passed to LaMA uninverted (99.6% of image was being inpainted) | Fixed — mask is now inverted so only the watermark region (0.4%) is inpainted |

---

## Re-running After Completion

Once all 451 folders are done, the script exits immediately:
```
Nothing to process — all folders complete. Use --overwrite to re-run.
```

To reprocess everything with updated masks or models:
```cmd
WatermarkRemover-AI\venv\Scripts\python.exe process_all_charters.py --overwrite
```
