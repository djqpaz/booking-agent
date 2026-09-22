"""Tests for supabase_client.is_band_member - the single source of truth for
sender identity that webhooks.py and the orchestrator both rely on.
"""

import pytest

from app.services.supabase_client import supabase_client


@pytest.mark.asyncio
async def test_is_band_member_true_case_insensitive(monkeypatch):
    async def fake_get_band_members():
        return [{"email": "Alex@SickDayWithFerris.band", "name": "Alex"}]

    monkeypatch.setattr(supabase_client, "get_band_members", fake_get_band_members)

    assert await supabase_client.is_band_member("alex@sickdaywithferris.band") is True


@pytest.mark.asyncio
async def test_is_band_member_false_for_unknown_email(monkeypatch):
    async def fake_get_band_members():
        return [{"email": "alex@sickdaywithferris.band", "name": "Alex"}]

    monkeypatch.setattr(supabase_client, "get_band_members", fake_get_band_members)

    assert await supabase_client.is_band_member("venue@example.com") is False


@pytest.mark.asyncio
async def test_is_band_member_false_for_empty_email(monkeypatch):
    async def fake_get_band_members():
        raise AssertionError("should not query band members for an empty email")

    monkeypatch.setattr(supabase_client, "get_band_members", fake_get_band_members)

    assert await supabase_client.is_band_member("") is False
    assert await supabase_client.is_band_member(None) is False


@pytest.mark.asyncio
async def test_is_band_member_fails_closed_on_db_error(monkeypatch):
    async def fake_get_band_members():
        raise RuntimeError("supabase is down")

    monkeypatch.setattr(supabase_client, "get_band_members", fake_get_band_members)

    # A DB error must not be mistaken for "yes, this is a band member" -
    # failing closed here means an unknown sender is treated as a venue,
    # the more restrictive path.
    assert await supabase_client.is_band_member("alex@sickdaywithferris.band") is False
