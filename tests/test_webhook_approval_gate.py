"""Route-level regression test for the approval gate: a reply flagged
requires_human_approval must never be auto-sent by the inbound email
webhook. This is the most safety-critical behavior in the codebase (the
whole "human-in-the-loop" design depends on it), so it's covered end to end
through the actual route, not just the orchestrator unit tests.

booking_agent.process_message and email_service.send_email are both
replaced with spies - no real LLM, DB, or Resend calls happen.
"""

import json
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from svix.webhooks import Webhook

from app.api.routes import webhooks
from app.config import settings

client = TestClient(FastAPI(routes=webhooks.router.routes))


def _signed_payload(payload: dict):
    body = json.dumps(payload)
    msg_id = "msg_test123"
    timestamp = datetime.now(timezone.utc)
    signature = Webhook(settings.webhook_signing_secret).sign(msg_id, timestamp, body)
    headers = {
        "svix-id": msg_id,
        "svix-timestamp": str(int(timestamp.timestamp())),
        "svix-signature": signature,
        "content-type": "application/json",
    }
    return body, headers


INBOUND_EMAIL = {
    "type": "email.received",
    "data": {
        "from": "venue@example.com",
        "to": ["agent@sickdaywithferris.band"],
        "subject": "Booking inquiry",
        "text": "We'd like to book you for a show",
        "message_id": "inbound-msg-1",
    },
}


@pytest.mark.asyncio
async def test_held_reply_is_not_auto_sent(monkeypatch):
    sent_emails = []

    async def fake_process_message(**kwargs):
        return {
            "response": "This offer is acceptable, pending approval.",
            "conversation_id": "conv-1",
            "intent": "negotiation",
            "requires_human_approval": True,
            "next_action": "pending_approval",
        }

    async def fake_send_email(**kwargs):
        sent_emails.append(kwargs)
        return {"email_id": "should-not-happen"}

    monkeypatch.setattr(webhooks.booking_agent, "process_message", fake_process_message)
    monkeypatch.setattr(webhooks.email_service, "send_email", fake_send_email)

    body, headers = _signed_payload(INBOUND_EMAIL)
    response = client.post("/webhooks/email", content=body, headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "pending_approval"
    assert sent_emails == []


@pytest.mark.asyncio
async def test_auto_approved_reply_is_still_sent(monkeypatch):
    sent_emails = []

    async def fake_process_message(**kwargs):
        return {
            "response": "Thanks for reaching out, checking availability now.",
            "conversation_id": "conv-1",
            "intent": "venue_inquiry",
            "requires_human_approval": False,
            "next_action": None,
        }

    async def fake_send_email(**kwargs):
        sent_emails.append(kwargs)
        return {"email_id": "sent-123"}

    monkeypatch.setattr(webhooks.booking_agent, "process_message", fake_process_message)
    monkeypatch.setattr(webhooks.email_service, "send_email", fake_send_email)

    body, headers = _signed_payload(INBOUND_EMAIL)
    response = client.post("/webhooks/email", content=body, headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "processed"
    assert len(sent_emails) == 1
    assert sent_emails[0]["to"] == ["venue@example.com"]
