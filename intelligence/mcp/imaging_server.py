"""FastMCP server exposing medical imaging analysis tools (MONAI-backed)."""

from pathlib import Path
from typing import Any, Dict

from fastmcp import FastMCP

mcp = FastMCP(
    name="medical-imaging",
    instructions="Medical image loading and analysis for X-Ray, CT, MRI, ultrasound.",
)

SUPPORTED_MODALITIES = ["xray", "ct", "mri", "ultrasound", "pathology"]


@mcp.tool
def inspect_medical_image(image_path: str) -> Dict[str, Any]:
    """Load a medical image (DICOM, NIfTI, PNG/JPG) and return its metadata:
    dimensions, modality hints, pixel statistics. Use before analysis to
    confirm the file is readable."""
    path = Path(image_path)
    if not path.exists():
        return {"error": f"File not found: {image_path}"}

    suffix = path.suffix.lower()
    info: Dict[str, Any] = {"path": str(path), "format": suffix, "size_bytes": path.stat().st_size}

    try:
        if suffix in {".dcm", ""}:
            import pydicom  # noqa: PLC0415

            ds = pydicom.dcmread(str(path), stop_before_pixels=True)
            info.update(
                {
                    "modality": getattr(ds, "Modality", "unknown"),
                    "patient_id": str(getattr(ds, "PatientID", "")),
                    "study_date": str(getattr(ds, "StudyDate", "")),
                    "rows": int(getattr(ds, "Rows", 0)),
                    "columns": int(getattr(ds, "Columns", 0)),
                }
            )
        elif suffix in {".nii", ".gz"}:
            import nibabel as nib  # noqa: PLC0415

            img = nib.load(str(path))
            info.update({"shape": list(img.shape), "modality": "volume"})
        else:
            from PIL import Image  # noqa: PLC0415

            with Image.open(path) as img:
                info.update({"shape": [img.height, img.width], "mode": img.mode})
    except Exception as exc:
        info["error"] = f"Could not parse image: {exc}"

    return info


@mcp.tool
def analyze_medical_image(image_path: str, modality: str, target: str = "") -> Dict[str, Any]:
    """Run AI analysis on a medical image. `modality` must be one of
    xray|ct|mri|ultrasound|pathology. Optional `target` names a structure to
    focus on (e.g. 'lung', 'liver'). Returns findings with confidence scores.

    NOTE: returns a structured placeholder until MONAI model weights are
    configured (settings.monai_model_path); the response shape is final."""
    if modality not in SUPPORTED_MODALITIES:
        return {"error": f"Unsupported modality '{modality}'. Use one of {SUPPORTED_MODALITIES}"}

    path = Path(image_path)
    if not path.exists():
        return {"error": f"File not found: {image_path}"}

    try:
        from core.config import settings  # noqa: PLC0415

        weights_configured = bool(settings.monai_model_path)
    except Exception:
        weights_configured = False

    if not weights_configured:
        return {
            "status": "model_not_configured",
            "message": (
                "MONAI model weights are not configured (MONAI_MODEL_PATH). "
                "Set the path to enable real inference. Response shape below is final."
            ),
            "modality": modality,
            "target": target or None,
            "findings": [],
            "requires_professional_review": True,
        }

    # Real MONAI inference path (activated once weights are configured).
    import torch  # noqa: PLC0415
    from monai.networks.nets import DenseNet121  # noqa: PLC0415
    from monai.transforms import (  # noqa: PLC0415
        Compose,
        EnsureChannelFirst,
        LoadImage,
        Resize,
        ScaleIntensity,
    )

    from core.config import settings  # noqa: PLC0415

    transforms = Compose(
        [LoadImage(image_only=True), EnsureChannelFirst(), ScaleIntensity(), Resize((224, 224))]
    )
    tensor = transforms(str(path)).unsqueeze(0)
    model = DenseNet121(spatial_dims=2, in_channels=1, out_channels=2)
    model.load_state_dict(torch.load(settings.monai_model_path, map_location="cpu"))
    model.eval()
    with torch.no_grad():
        logits = model(tensor)
        probs = torch.softmax(logits, dim=1).squeeze().tolist()

    return {
        "status": "ok",
        "modality": modality,
        "target": target or None,
        "findings": [
            {"label": "abnormal", "probability": round(probs[1], 4)},
            {"label": "normal", "probability": round(probs[0], 4)},
        ],
        "requires_professional_review": True,
    }
