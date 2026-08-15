"""
Download a small handful of real chest X-ray images from the RSNA
Pneumonia Detection Challenge (via Kaggle) to use as fixtures for
SEPHIROTH's vision pipeline (`intelligence/mcp/imaging_server.py`,
`vision_server.py`).

⚠️  READ `real_data/imaging/README.md` BEFORE RUNNING THIS. The RSNA
competition data is licensed for academic/non-commercial research use —
it is intentionally never committed to this repo (images are written to
`real_data/imaging/samples/`, which is gitignored).

Requires the Kaggle CLI, configured with YOUR OWN credentials (never this
project's) — see https://www.kaggle.com/docs/api:

    pip install kaggle
    # place your kaggle.json at ~/.kaggle/kaggle.json (chmod 600)

Run manually (network + Kaggle account required, never in CI/tests):

    PYTHONPATH=. python3 real_data/imaging/fetch_rsna_samples.py --count 10
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

COMPETITION = "rsna-pneumonia-detection-challenge"
SAMPLES_DIR = Path(__file__).parent / "samples"
STAGING_DIR = Path(__file__).parent / "_kaggle_download"


def _check_kaggle_cli() -> bool:
    return shutil.which("kaggle") is not None


def _list_training_image_files(limit: int) -> list[str]:
    """Ask Kaggle which files actually exist in the competition dataset,
    rather than guessing filenames — the training set's exact file names
    aren't predictable/stable enough to hardcode."""
    result = subprocess.run(
        ["kaggle", "competitions", "files", "-c", COMPETITION, "-v"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Could not list competition files: {result.stderr}", file=sys.stderr)
        return []

    files = []
    for line in result.stdout.splitlines()[1:]:  # skip CSV header
        name = line.split(",")[0].strip()
        if "train_images" in name and name.endswith(".dcm"):
            files.append(name)
        if len(files) >= limit:
            break
    return files


def _to_png(dicom_path: Path, out_path: Path) -> bool:
    """Convert a downloaded DICOM sample to PNG so it matches the
    extensions `describe_medical_image`/`inspect_medical_image` already
    handle (READABLE_FORMATS in vision_server.py)."""
    try:
        import pydicom
        from PIL import Image

        ds = pydicom.dcmread(str(dicom_path))
        arr = ds.pixel_array
        Image.fromarray(arr).convert("L").save(out_path)
        return True
    except Exception as exc:
        print(f"Could not convert {dicom_path.name} to PNG: {exc}", file=sys.stderr)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=5, help="how many sample images to fetch")
    parser.add_argument("--keep-dicom", action="store_true", help="also keep the raw .dcm files")
    args = parser.parse_args()

    if not _check_kaggle_cli():
        print(
            "Kaggle CLI not found. Install it and configure your own credentials:\n"
            "  pip install kaggle\n"
            "  # then place your kaggle.json at ~/.kaggle/kaggle.json (chmod 600)\n"
            "See https://www.kaggle.com/docs/api",
            file=sys.stderr,
        )
        return 1

    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    files = _list_training_image_files(args.count)
    if not files:
        print("No files found — check your Kaggle credentials and competition access.", file=sys.stderr)
        return 1

    for filename in files:
        print(f"Downloading {filename} from Kaggle competition {COMPETITION}...", file=sys.stderr)
        result = subprocess.run(
            ["kaggle", "competitions", "download", "-c", COMPETITION, "-f", filename, "-p", str(STAGING_DIR)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"Failed to download {filename}: {result.stderr}", file=sys.stderr)
            continue

        zip_path = STAGING_DIR / (Path(filename).name + ".zip")
        dicom_path = STAGING_DIR / Path(filename).name
        if zip_path.exists():
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(STAGING_DIR)
            zip_path.unlink()

        if dicom_path.exists():
            png_path = SAMPLES_DIR / (dicom_path.stem + ".png")
            if _to_png(dicom_path, png_path):
                print(f"Wrote {png_path}", file=sys.stderr)
            if args.keep_dicom:
                shutil.move(str(dicom_path), SAMPLES_DIR / dicom_path.name)
            else:
                dicom_path.unlink()

    shutil.rmtree(STAGING_DIR, ignore_errors=True)
    print(f"Done. Samples in {SAMPLES_DIR}/ (gitignored — never commit these).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
