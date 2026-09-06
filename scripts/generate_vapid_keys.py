"""Print a VAPID key pair for web push (SPEC-025).

    .venv/bin/python scripts/generate_vapid_keys.py

The private key is a secret: it authorises sending push notifications as this
application. It goes in `.env` alongside `JWT_SECRET`, never in the repository.
The public key is handed to browsers and is not sensitive.

A deployment that sets neither is unaffected: push is disabled and every
notification path behaves exactly as it did before this phase.
"""

import base64

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid01


def _b64(raw: bytes) -> str:
    """Unpadded URL-safe base64 — the encoding both the Push API and
    `pywebpush` expect for VAPID keys."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def main() -> int:
    vapid = Vapid01()
    vapid.generate_keys()

    # The raw scalar and the uncompressed EC point, not a PEM: `py_vapid`
    # exposes `cryptography` key objects, and the browser's
    # `applicationServerKey` is the 65-byte point.
    private_raw = vapid.private_key.private_numbers().private_value.to_bytes(32, "big")
    public_raw = vapid.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )

    print("VAPID_PRIVATE_KEY=" + _b64(private_raw))
    print("VAPID_PUBLIC_KEY=" + _b64(public_raw))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
