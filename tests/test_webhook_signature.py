"""Tests for verify_svix_signature - the gate that decides whether an inbound
webhook request is actually from Resend/Svix before we let it trigger an
email reply. All signatures here are generated locally; no network calls.
"""

import json
from datetime import datetime, timezone

from svix.webhooks import Webhook

from app.utils.webhook_signature import verify_svix_signature

SECRET = "whsec_MfKQ9r8GKYqrTwjUPD8ILPZIo2LaLaSw"


def _signed_request(secret: str, payload: dict):
    body = json.dumps(payload)
    msg_id = "msg_test123"
    timestamp = datetime.now(timezone.utc)
    signature = Webhook(secret).sign(msg_id, timestamp, body)
    headers = {
        "svix-id": msg_id,
        "svix-timestamp": str(int(timestamp.timestamp())),
        "svix-signature": signature,
    }
    return body.encode("utf-8"), headers


def test_valid_signature_is_accepted():
    payload_bytes, headers = _signed_request(SECRET, {"type": "email.received", "data": {}})
    assert verify_svix_signature(payload_bytes, headers, SECRET) is True


def test_signature_from_wrong_secret_is_rejected():
    payload_bytes, headers = _signed_request("whsec_differentSecretEntirely12345", {"type": "email.received"})
    assert verify_svix_signature(payload_bytes, headers, SECRET) is False


def test_tampered_payload_is_rejected():
    payload_bytes, headers = _signed_request(SECRET, {"type": "email.received", "data": {}})
    tampered = payload_bytes.replace(b"email.received", b"email.sent")
    assert verify_svix_signature(tampered, headers, SECRET) is False


def test_missing_secret_is_rejected():
    payload_bytes, headers = _signed_request(SECRET, {"type": "email.received"})
    assert verify_svix_signature(payload_bytes, headers, "") is False


def test_missing_headers_is_rejected():
    assert verify_svix_signature(b"{}", {}, SECRET) is False
