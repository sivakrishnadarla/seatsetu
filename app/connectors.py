"""Connectors — WhatsApp Cloud API (mock by default) + Meta lead-ads parsing.
Real mode activates with WHATSAPP_TOKEN/WHATSAPP_PHONE_ID in .env."""
from .config import SETTINGS
from .db import AuditLog, SessionLocal, utcnow


def whatsapp_send(college_id: int, to_phone: str, text: str) -> dict:
    """Parent-facing outbound. Mock mode = logged only, never sent."""
    if SETTINGS.whatsapp_token and SETTINGS.whatsapp_phone_id:
        import httpx
        r = httpx.post(
            f"https://graph.facebook.com/v20.0/{SETTINGS.whatsapp_phone_id}/messages",
            headers={"Authorization": f"Bearer {SETTINGS.whatsapp_token}"},
            json={"messaging_product": "whatsapp", "to": to_phone,
                  "type": "text", "text": {"body": text[:4000]}}, timeout=30)
        ok = r.status_code == 200
        return dict(mode="live", sent=ok)
    db = SessionLocal()
    db.add(AuditLog(college_id=college_id, actor="system", action="exec.whatsapp_send",
                    detail=dict(to=to_phone, text=text[:140], mode="mock"),
                    created_at=utcnow()))
    db.commit()
    db.close()
    return dict(mode="mock", sent=False,
                note="WhatsApp not configured — logged, not sent (₹0 demo mode).")


def parse_meta_lead(payload: dict) -> dict | None:
    """Real Meta lead-ads webhook payload shape:
    {"leadgen_id": "...", "form_name": "...", "created_time": "...",
     "field_data": [{"name": "full_name", "values": ["X"]}, ...]}"""
    try:
        fields = {}
        for f in payload.get("field_data", []):
            vals = f.get("values", [])
            fields[f.get("name", "")] = vals[0] if vals else ""
        return dict(
            name=fields.get("full_name") or fields.get("name") or "",
            phone=fields.get("phone_number") or fields.get("phone") or "",
            town=fields.get("city") or fields.get("town") or "",
            branch_interest=fields.get("branch") or fields.get("branch_interest") or "",
            campaign=payload.get("form_name", "meta_lead_form"),
            external_id=str(payload.get("leadgen_id", "")),
        )
    except Exception:
        return None
