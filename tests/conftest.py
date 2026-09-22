"""Shared pytest fixtures/setup.

Every app module that touches Supabase, OpenAI, or Resend builds its client at
*import time* (see the module-level singletons in app/services/*.py), so these
env vars must be set before any app module is first imported - not inside a
fixture. None of these are real credentials; nothing in this suite makes a
real network call.
"""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
# supabase-py only checks that the key is JWT-shaped at client-construction
# time - it never contacts the network for that check.
os.environ.setdefault(
    "SUPABASE_SERVICE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0In0.c2lnbmF0dXJl",
)
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("RESEND_API_KEY", "test-key")
os.environ.setdefault("WEBHOOK_SIGNING_SECRET", "whsec_MfKQ9r8GKYqrTwjUPD8ILPZIo2LaLaSw")
