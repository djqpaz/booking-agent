"""Admin endpoints (protected)"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import structlog

from app.services.email_service import email_service
from app.services.supabase_client import supabase_client

logger = structlog.get_logger()
router = APIRouter()


# TODO: Implement authentication middleware
async def verify_admin(token: str = None):
    """Verify admin authentication"""
    # TODO: Verify JWT token from Supabase
    pass


class BookingApproval(BaseModel):
    """Booking approval request"""
    approved_by: str
    notes: Optional[str] = None


@router.get("/bookings")
async def list_bookings(
    status: Optional[str] = None,
    limit: int = 20,
    # admin = Depends(verify_admin)
):
    """
    List all bookings with optional status filter
    """
    logger.info("list_bookings", status=status, limit=limit)
    
    # TODO: Query bookings from database
    return {
        "bookings": [],
        "total": 0
    }


@router.get("/bookings/{booking_id}")
async def get_booking(
    booking_id: str,
    # admin = Depends(verify_admin)
):
    """
    Get detailed booking information
    """
    # TODO: Fetch booking with conversations and contract
    return {
        "booking": {},
        "conversations": [],
        "contract": None
    }


@router.post("/bookings/{booking_id}/approve")
async def approve_booking(
    booking_id: str,
    approval: BookingApproval,
    # admin = Depends(verify_admin)
):
    """
    Approve a booking and send confirmation
    """
    logger.info(
        "booking_approved",
        booking_id=booking_id,
        approved_by=approval.approved_by
    )
    
    # TODO: Update booking status
    # TODO: Send confirmation email
    # TODO: Log approval in audit_log
    
    return {
        "status": "confirmed",
        "email_sent": True
    }


@router.post("/contracts/{contract_id}/approve")
async def approve_contract(
    contract_id: str,
    approval: BookingApproval,
    # admin = Depends(verify_admin)
):
    """
    Approve contract and send to venue
    """
    logger.info(
        "contract_approved",
        contract_id=contract_id,
        approved_by=approval.approved_by
    )
    
    # TODO: Update contract status
    # TODO: Send contract to venue
    # TODO: Log in audit_log

    return {
        "status": "sent",
        "sent_at": None
    }


class ReplyDecision(BaseModel):
    """Human review decision on a held agent reply"""
    reviewed_by: str
    reason: Optional[str] = None


@router.get("/replies/pending")
async def list_pending_replies(
    limit: int = 50,
    # admin = Depends(verify_admin)
):
    """List agent-drafted replies awaiting human approval before sending"""
    messages = await supabase_client.list_messages_by_status("pending_approval", limit=limit)
    return {"replies": messages, "total": len(messages)}


@router.post("/replies/{message_id}/approve")
async def approve_reply(
    message_id: str,
    decision: ReplyDecision,
    # admin = Depends(verify_admin)
):
    """Approve a held agent reply - this is the only path that actually sends it"""
    message = await supabase_client.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    metadata = message.get("metadata") or {}
    if metadata.get("status") != "pending_approval":
        raise HTTPException(status_code=400, detail=f"Reply is not pending approval (status: {metadata.get('status')})")

    to_email = metadata.get("to_email")
    if not to_email:
        raise HTTPException(status_code=400, detail="No recipient email on file for this reply")

    subject = f"Re: {metadata.get('subject') or 'Your Inquiry'}"
    in_reply_to = metadata.get("in_reply_to")

    try:
        send_result = await email_service.send_email(
            to=[to_email],
            subject=subject,
            html=message["content"],
            text=message["content"],
            metadata={"conversation_id": message.get("conversation_id", "")},
            in_reply_to=in_reply_to,
            references=in_reply_to,
        )
    except Exception as e:
        logger.error("reply_approval_send_failed", message_id=message_id, error=str(e))
        raise HTTPException(status_code=502, detail=f"Failed to send approved reply: {e}")

    updated_metadata = {
        **metadata,
        "status": "sent",
        "approved_by": decision.reviewed_by,
        "email_id": send_result.get("email_id"),
    }
    await supabase_client.update_message(message_id, {"metadata": updated_metadata})

    logger.info("reply_approved_and_sent", message_id=message_id, to=to_email, approved_by=decision.reviewed_by)
    return {"status": "sent", "email_id": send_result.get("email_id")}


@router.post("/replies/{message_id}/reject")
async def reject_reply(
    message_id: str,
    decision: ReplyDecision,
    # admin = Depends(verify_admin)
):
    """Reject a held agent reply - nothing is sent"""
    message = await supabase_client.get_message(message_id)
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    metadata = message.get("metadata") or {}
    if metadata.get("status") != "pending_approval":
        raise HTTPException(status_code=400, detail=f"Reply is not pending approval (status: {metadata.get('status')})")

    updated_metadata = {
        **metadata,
        "status": "rejected",
        "rejected_by": decision.reviewed_by,
        "rejection_reason": decision.reason,
    }
    updated = await supabase_client.update_message(message_id, {"metadata": updated_metadata})

    logger.info("reply_rejected", message_id=message_id, rejected_by=decision.reviewed_by)
    return {"message": updated}
