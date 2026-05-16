import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature

KEYS_DIR = Path(__file__).parent.parent / "keys"
PUBLIC_KEY_PATH = KEYS_DIR / "beacon-verdict.pub"


def _canonical_json(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def verify_verdict(verdict: dict) -> bool:
    sig = verdict.get("signature", "")
    if not sig.startswith("beacon-signature:v1:"):
        return False
    raw = sig[len("beacon-signature:v1:"):]
    raw += "=" * (-len(raw) % 4)
    sig_bytes = base64.urlsafe_b64decode(raw)
    payload = {k: v for k, v in verdict.items() if k != "signature"}
    pubkey = serialization.load_pem_public_key(PUBLIC_KEY_PATH.read_bytes())
    try:
        pubkey.verify(sig_bytes, _canonical_json(payload))  # type: ignore[attr-defined]
        return True
    except InvalidSignature:
        return False
