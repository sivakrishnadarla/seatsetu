"""Guardrails — hard-coded safety layer (not prompt suggestions):
kill switch · consent firewall · trap-question refusals · rate caps ·
immutable audit log. This is what makes an AI safe to face parents."""
import re
from datetime import datetime, timedelta, timezone

from .db import AuditLog, College, Lead, SessionLocal, utcnow

DAILY_CAPS = {"whatsapp_send": 400, "followup": 300}

# ── Trap-question patterns (the 5 classes the AI must never invent on) ──────
TRAPS = {
    "job_guarantee": r"(100%\s*(placement|job)|job\s*guarantee|placement\s*guarantee|guaranteed?\s*(job|placement)|ఉద్యోగ హామీ|పూర్తి ప్లేస్\S* హామీ)",
    "salary_promise": r"(guarantee\w*\s*\S*\s*(salary|package|job|placement|lpa)|(salary|package|placement|job|lpa)\s*\S*\s*(guarantee|promise|fix)|package\s*(guarantee|promise|fix)|minimum\s*salary|జాబ్.*హామీ|ప్యాకేజీ.*హామీ)",
    "scholarship_certain": r"(scholarship.*(confirm|sure|definite|guarantee)|(confirm|sure|definite).*(reimbursement|scholarship)|స్కాలర్\S* ఖచ్చితంగా|ఫీజు రీఇంపర్స్\S* ఖచ్చితంగా)",
    "refund_ruling": r"(refund|money back|cancel.*(seat|booking).*(back|return)|డబ్బు వప్పించడం|రీఫండ్)",
    "rank_predict": r"(predict.*(rank|cutoff)|what rank.*(get|need).*(cse|ece|seat)|will i get.*seat|నా ర్యాంక్\S* సీటు|సీటు వస్తుందా)",
}
HUMAN_REQUEST = r"(talk to (someone|human|counselor|principal|staff)|call me|speak to|మీకు మాట్లాడే|కాల్ చేయండి|ఫోన్ చేయండి)"
COMPLAINT = r"(complaint|worst|cheat|fraud|scam|harass|ఫిర్యాదు|మోసం)"


class GuardrailViolation(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def check_kill_switch(college_id: int, db):
    c = db.query(College).get(college_id)
    if c and c.kill_switch:
        log(college_id, "system", "guardrail.kill_switch_blocked", {}, db)
        raise GuardrailViolation("Kill switch ON — AI counselor paused for this college.")


def consent_firewall(college_id: int, lead: Lead | None, db):
    """No outbound message to a lead without a consent record (DPDP)."""
    if lead is None:
        raise GuardrailViolation("No lead — nothing to send.")
    if not lead.consent:
        log(college_id, "ai", "guardrail.consent_blocked",
            {"lead_id": lead.id, "rule": "DPDP opt-in required"}, db)
        raise GuardrailViolation(f"Consent missing for {lead.name or lead.phone} — send blocked.")


def rate_cap(college_id: int, kind: str, db):
    day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).replace(tzinfo=None)
    n = db.query(AuditLog).filter(
        AuditLog.college_id == college_id,
        AuditLog.action == f"exec.{kind}",
        AuditLog.created_at >= day_start).count()
    cap = DAILY_CAPS.get(kind)
    if cap is not None and n >= cap:
        raise GuardrailViolation(f"Daily cap reached for '{kind}' ({cap}/day).")


def detect_trap(text: str) -> str | None:
    t = text.lower()
    for trap, pattern in TRAPS.items():
        if re.search(pattern, t):
            return trap
    return None


def is_human_request(text: str) -> bool:
    return bool(re.search(HUMAN_REQUEST, text.lower()))


def is_complaint(text: str) -> bool:
    return bool(re.search(COMPLAINT, text.lower()))


TENGLISH = r"\b(enta|entha|unda|undhi|undi|kavali|kavala|cheyyandi|cheppandi|cheppu|ela|ekkada|nunchi|peru|istara|pettandi|chudali|telidu|telusu|sir|garu|anna|akka|em|baagundi|chalu|kaadu|ledu|vachchu|randi)\b"


def detect_language(text: str) -> str:
    """Telugu script (U+0C00–U+0C7F) OR romanized Telugu ('Tenglish': enta/unda/
    kavali…) → 'te'. Most parents type Tenglish on WhatsApp keyboards."""
    telugu_chars = len(re.findall(r"[\u0C00-\u0C7F]", text))
    if telugu_chars >= 2:
        return "te"
    tenglish_hits = len(re.findall(TENGLISH, text.lower()))
    return "te" if tenglish_hits >= 2 else "en"


def log(college_id: int, actor: str, action: str, detail: dict, db):
    db.add(AuditLog(college_id=college_id, actor=actor, action=action,
                    detail=detail, created_at=utcnow()))
    db.commit()
