"""SEPHIROTH — evidence-grounded, model-agnostic multi-agent AI runtime.

The runtime is the product; the clinical application in `platform/` is its
primary case study. During the architecture migration (Phases 0–5) this package
grows one subpackage per phase while the legacy tree under `intelligence/` and
`data/` is strangled out. See `docs/00-migration-charter.md`.
"""

__version__ = "0.2.0"

__all__ = ["__version__"]
