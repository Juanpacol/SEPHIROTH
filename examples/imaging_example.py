"""
Example: run the imaging + vision pipeline against a real chest X-ray.

Requires a sample image first — see real_data/imaging/README.md:

    PYTHONPATH=. python3 real_data/imaging/fetch_rsna_samples.py --count 5

Run from the repo root:

    PYTHONPATH=.:platform .venv/bin/python examples/imaging_example.py \
        real_data/imaging/samples/<filename>.png
"""

import asyncio
import sys

from sephiroth.tools import get_tool_runtime


async def main(image_path: str) -> None:
    registry = get_tool_runtime()
    await registry.load()

    print(f"--- inspect_medical_image({image_path}) ---")
    info = await registry.execute("inspect_medical_image", {"image_path": image_path})
    print(info)

    print("\n--- analyze_medical_image (MONAI) ---")
    analysis = await registry.execute("analyze_medical_image", {"image_path": image_path, "modality": "xray"})
    print(analysis)

    print("\n--- describe_medical_image (Gemini vision) ---")
    description = await registry.execute(
        "describe_medical_image", {"image_path": image_path, "clinical_focus": "lungs"}
    )
    print(description.get("description") or description)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(1)
    asyncio.run(main(sys.argv[1]))
