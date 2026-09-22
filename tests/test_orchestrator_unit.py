"""Unit tests for individual BookingAgent graph nodes, run directly (without
the compiled LangGraph) so each node's logic can be checked in isolation with
llm_service/supabase_client mocked out - no real LLM or DB calls.

These cover three bugs found and fixed in this codebase:
- classify_intent forcing every first-touch message to "venue_inquiry" even
  for a band member, because identity was derived inconsistently
  (now: derived once via supabase_client.is_band_member)
- save_to_database re-inserting the entire conversation history on every
  turn once history-loading was fixed (now: sliced by history_length)
- the negotiation handler's requires_human_approval flag not actually
  blocking the auto-send in the webhook (covered in test_webhook_approval_gate.py)
"""

from langchain_core.messages import AIMessage, HumanMessage

import pytest

from app.agent.orchestrator import BookingAgent
from app.services import supabase_client as supabase_client_module
from app.services import llm_service as llm_service_module
from app.services.llm_service import LLMResponse, LLMProvider


def make_llm_response(text: str) -> LLMResponse:
    return LLMResponse(content=text, model="test-model", provider=LLMProvider.OPENAI)


@pytest.fixture
def agent():
    return BookingAgent()


def base_state(sender_email="venue@example.com", sender_type="venue", messages=None):
    messages = messages if messages is not None else [HumanMessage(content="Hi, want to book you for March 15th")]
    return {
        "messages": messages,
        "conversation_id": "conv-1",
        "sender_email": sender_email,
        "sender_name": "Test Sender",
        "sender_type": sender_type,
        "intent": "",
        "booking_id": None,
        "booking_constraints": [],
        "requires_human_approval": False,
        "next_action": None,
        "history_length": len(messages) - 1,  # only the last message is "new" this turn
    }


@pytest.mark.asyncio
async def test_classify_intent_forces_venue_inquiry_for_unknown_first_message(agent, monkeypatch):
    monkeypatch.setattr(
        supabase_client_module.supabase_client, "is_band_member", lambda email: _async_false()
    )
    monkeypatch.setattr(
        llm_service_module.llm_service, "generate", lambda **kwargs: _async(make_llm_response("general_question"))
    )

    state = base_state(sender_email="venue@example.com", sender_type="venue")
    result = await agent.classify_intent(state)

    assert result["intent"] == "venue_inquiry"
    assert result["sender_type"] == "venue"


@pytest.mark.asyncio
async def test_classify_intent_does_not_force_venue_inquiry_for_band_member(agent, monkeypatch):
    monkeypatch.setattr(
        supabase_client_module.supabase_client, "is_band_member", lambda email: _async_true()
    )
    monkeypatch.setattr(
        llm_service_module.llm_service, "generate", lambda **kwargs: _async(make_llm_response("general_question"))
    )

    state = base_state(sender_email="alex@sickdaywithferris.band", sender_type="venue")  # caller mislabeled it
    result = await agent.classify_intent(state)

    # Not forced to venue_inquiry just because it's the first message - and the
    # mislabeled sender_type the caller passed in gets corrected.
    assert result["intent"] != "venue_inquiry"
    assert result["sender_type"] == "band_member"


@pytest.mark.asyncio
async def test_save_to_database_only_persists_new_messages(agent, monkeypatch):
    created_messages = []

    async def fake_create_message(**kwargs):
        created_messages.append(kwargs)
        return {"id": "msg-new", **kwargs}

    async def fake_get_contact_by_email(email):
        return {"id": "contact-1", "first_name": "Test", "last_name": "Sender"}

    monkeypatch.setattr(supabase_client_module.supabase_client, "create_message", fake_create_message)
    monkeypatch.setattr(supabase_client_module.supabase_client, "get_contact_by_email", fake_get_contact_by_email)

    prior_messages = [
        HumanMessage(content="old human message"),
        AIMessage(content="old ai reply"),
    ]
    new_messages = prior_messages + [
        HumanMessage(content="new human message"),
        AIMessage(content="new ai reply"),
    ]
    state = base_state(messages=new_messages)
    state["history_length"] = len(prior_messages)

    await agent.save_to_database(state)

    saved_contents = [m["content"] for m in created_messages]
    assert saved_contents == ["new human message", "new ai reply"]


@pytest.mark.asyncio
async def test_save_to_database_tags_pending_approval_replies(agent, monkeypatch):
    created_messages = []

    async def fake_create_message(**kwargs):
        created_messages.append(kwargs)
        return {"id": "msg-new", **kwargs}

    monkeypatch.setattr(supabase_client_module.supabase_client, "create_message", fake_create_message)

    state = base_state(messages=[AIMessage(content="draft reply awaiting approval")])
    state["history_length"] = 0
    state["requires_human_approval"] = True
    state["original_message_id"] = "orig-msg-id"
    state["original_subject"] = "Booking Inquiry"

    await agent.save_to_database(state)

    assert len(created_messages) == 1
    metadata = created_messages[0]["metadata"]
    assert metadata["status"] == "pending_approval"
    assert metadata["to_email"] == state["sender_email"]
    assert metadata["in_reply_to"] == "orig-msg-id"


async def _async(value):
    return value


async def _async_true():
    return True


async def _async_false():
    return False
