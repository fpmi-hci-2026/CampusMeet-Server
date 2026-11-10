"""Cryptographic utilities for dynamic HMAC-SHA256 QR-tokens."""
import hashlib
import hmac
import os

SECRET_KEY = os.getenv("CAMPUSMEET_HMAC_SECRET", "campusmeet-fpmibsu-hmac-secret-2026").encode("utf-8")


def sign_ticket(ticket_id: str, user_id: str, event_id: str) -> str:
    """Generate deterministic HMAC-SHA256 signature for ticket validation."""
    message = f"{ticket_id}:{user_id}:{event_id}".encode("utf-8")
    signature = hmac.new(SECRET_KEY, message, hashlib.sha256).hexdigest()[:24]
    return f"v1.{ticket_id}.{user_id}.{signature}"


def verify_ticket_signature(payload: str, event_id: str) -> bool:
    """Validate ticket payload signature against event_id."""
    if not payload or not payload.startswith("v1."):
        # Also support legacy demo codes if present
        return False
    parts = payload.split(".")
    if len(parts) != 4:
        return False
    _, ticket_id, user_id, signature = parts
    expected = sign_ticket(ticket_id, user_id, event_id)
    expected_sig = expected.split(".")[3]
    return hmac.compare_digest(signature, expected_sig)
