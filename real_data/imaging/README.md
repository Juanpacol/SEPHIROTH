# Medical images — RSNA Pneumonia Detection Challenge

**Source:** [RSNA Pneumonia Detection Challenge](https://www.rsna.org/artificial-intelligence/ai-image-challenge/rsna-pneumonia-detection-challenge-2018) (via Kaggle) — real chest X-rays, the **same underlying imagery as NIH ChestX-ray14**, but re-labeled with bounding-box annotations from **6 board-certified radiologists** (3 more confirmed the test set) — meaningfully more reliable labels than NIH's original NLP-extracted-from-reports labels.

## ⚠️ LICENSE — READ BEFORE USING

This data is licensed for **academic research, education, and non-commercial use only**. Redistributing it outside Kaggle's platform is **not clearly authorized** by the competition rules.

**Therefore, in this repo:**
- Images are **NEVER committed**. `samples/` is gitignored.
- `fetch_rsna_samples.py` downloads a handful of images (5-10) **directly to your own machine**, using **your own** Kaggle account and credentials — nothing is bundled or redistributed by this project.
- If SEPHIROTH is ever used commercially, this fixture path must not be relied on — either negotiate a commercial license with RSNA/the data sponsors, or use only user-uploaded images (the vision pipeline already supports that as its primary path).

## Setup

1. Create a free [Kaggle account](https://www.kaggle.com) if you don't have one, and accept the [RSNA Pneumonia Detection Challenge](https://www.kaggle.com/competitions/rsna-pneumonia-detection-challenge/rules) competition rules (required before the API will let you download).
2. Install the Kaggle CLI and configure **your own** credentials:
   ```bash
   pip install kaggle
   # Get an API token from https://www.kaggle.com/settings -> "Create New Token"
   # Place the downloaded kaggle.json at ~/.kaggle/kaggle.json
   chmod 600 ~/.kaggle/kaggle.json
   ```
3. Fetch a handful of sample images:
   ```bash
   PYTHONPATH=. python3 real_data/imaging/fetch_rsna_samples.py --count 10
   ```

This converts each downloaded DICOM to PNG (matching the extensions `intelligence/mcp/vision_server.py::READABLE_FORMATS` already handles) and writes them to `samples/` — never fetches the full training set archive.

## Using the samples

```bash
PYTHONPATH=.:platform .venv/bin/python examples/imaging_example.py real_data/imaging/samples/<filename>.png
```

Demonstrates `describe_medical_image` (Gemini vision) and `analyze_medical_image` (MONAI) against a real chest X-ray for the first time in this project — until now the vision pipeline was only ever exercised against whatever a user uploaded live.
