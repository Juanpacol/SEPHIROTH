# Imaging demo studies

Four images and `analyses.json`, shipped with the deployment so "Recent imaging
analyses" can show an image next to its analysis anywhere (see
`scripts/seed_imaging_demo.py`).

- **The analyses are real Vision AI output** (`gemini-flash-latest`, date in
  `analyses.json`), produced by `scripts/generate_imaging_demo.py` and **not
  clinically reviewed**. They can be wrong. Do not present them as findings.
- **Source and licence of the images are not recorded.** They are the same files
  as the landing page's gallery (`platform/frontend/public/landing/analysis/`),
  supplied by the maintainer; see the LICENCES note in
  `platform/frontend/components/landing/analysis-gallery.tsx`. Replace them with
  images of known licence (CC0 / public domain) before any use beyond a demo.
- The RSNA/Kaggle samples under `real_data/imaging/samples/` are **not** used here
  and must never be: their licence forbids redistribution.
