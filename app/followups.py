"""Follow-up sequence engine — the 'never forget a lead' machine.

Sequence (all bilingual, consent-gated, rate-capped, fully logged):
  step 0: instant greeting        (fired at capture, same day)
  step 1: day-2 doubts nudge      (run_due)
  step 2: day-7 campus-visit invite
  step 3: day-12 admissions-open reminder → sequence complete
Stops immediately on: joined, lost, consent withdrawn.
"""
from datetime import timedelta

from . import connectors, guardrails
from .db import College, FollowUpLog, Lead, utcnow

TEMPLATES = {
    "greeting": {
        "en": ("Hi {name}! 👋 Thanks for your interest in {college}. I'm the college's AI counselor — "
               "ask me anything about courses, fees, hostel or placements here, anytime. "
               "Our counselor can also call you — just reply CALL."),
        "te": ("నమస్తే {name} 🙏 {college} పట్ల మీ ఆసక్తికి ధన్యవాదాలు. నేను కాలేజీ AI కౌన్సిలర్‌ని — "
               "కోర్సులు, ఫీజులు, హాస్టల్, ప్లేస్‌మెంట్ల గురించి ఎప్పుడైనా అడగండి. మా కౌన్సిలర్ కాల్ కావాలంటే CALL అని రాయండి."),
    },
    "nudge": {
        "en": ("Hi {name}, any doubts about {branch} fees, hostel or bus routes? Reply here — "
               "I answer instantly, day or night."),
        "te": ("హాయ్ {name}, {branch} ఫీజులు, హాస్టల్ లేదా బస్సు రూట్ల గురించి సందేహాలా? "
               "ఇక్కడే రాయండి — పగలూ రాత్రూ వెంటనే సమాధానం ఇస్తాను."),
    },
    "visit": {
        "en": ("{name}, would you like a campus visit this week? You can see the labs, hostel & mess, "
               "and meet the placement team. Reply VISIT with your preferred day."),
        "te": ("{name}, ఈ వారం క్యాంపస్ విజిట్ చేయాలా? ల్యాబ్‌లు, హాస్టల్, మెస్ చూడవచ్చు, ప్లేస్‌మెంట్ టీమ్‌ని కలవవచ్చు. "
               "మీకు అనుకూలమైన రోజుతో VISIT అని రాయండి."),
    },
    "deadline": {
        "en": ("{name}, management-quota admissions for 2026-27 at {college} are open and filling. "
               "Reply BOOK and our counselor will guide you through seat booking (token at the college office)."),
        "te": ("{name}, {college}లో 2026-27 మేనేజ్‌మెంట్ కోటా అడ్మిషన్లు ఓపెన్‌గా ఉన్నాయి, సీట్లు త్వరితగతిన నిండుతున్నాయి. "
               "BOOK అని రాయండి — మా కౌన్సిలర్ సీటు బుకింగ్‌కు గైడ్ చేస్తారు (కాలేజీ ఆఫీస్‌లో టోకెన్)."),
    },
}
SEQ_ORDER = ["nudge", "visit", "deadline"]   # steps 1, 2, 3 (greeting = step 0)
GAP_DAYS = {1: 2, 2: 5, 3: 5}


def _render(template_key: str, lang: str, col: College, lead: Lead) -> str:
    tmpl = TEMPLATES[template_key].get(lang) or TEMPLATES[template_key]["en"]
    return tmpl.format(
        name=lead.name or "there" if lang == "en" else lead.name or "",
        college=col.short or col.name,
        branch=(lead.branch_interest or "your").upper() if lang == "en" else (lead.branch_interest or "మీ").upper(),
    )


def _send(db, col, lead, template_key) -> bool:
    lang = "te" if lead.town else "en"   # simple default; real inbound language wins in chat
    text = _render(template_key, lang, col, lead)
    try:
        guardrails.consent_firewall(col.id, lead, db)
        guardrails.rate_cap(col.id, "followup", db)
    except guardrails.GuardrailViolation as e:
        guardrails.log(col.id, "system", "followup.blocked",
                       {"lead_id": lead.id, "reason": e.reason}, db)
        return False
    result = connectors.whatsapp_send(col.id, lead.phone, text)
    db.add(FollowUpLog(college_id=col.id, lead_id=lead.id, template=template_key,
                       channel="whatsapp", text=text, mode=result["mode"], sent_at=utcnow()))
    guardrails.log(col.id, "ai", f"exec.followup_{template_key}",
                   {"lead_id": lead.id, "mode": result["mode"]}, db)
    return True


def fire_greeting(db, col, lead):
    _send(db, col, lead, "greeting")


def run_due(db, college_id: int) -> dict:
    """Cron body (Vercel Cron / local scheduler): fire every due follow-up."""
    from datetime import datetime, timezone
    col = db.query(College).get(college_id)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    due = (db.query(Lead)
             .filter(Lead.college_id == college_id,
                     Lead.consent == True,                      # noqa: E712
                     Lead.next_followup_at <= now,
                     Lead.seq_step >= 1, Lead.seq_step <= 3,
                     Lead.stage.notin_(["joined", "lost"]))
             .all())
    sent, blocked = [], []
    for lead in due:
        step = lead.seq_step
        template_key = SEQ_ORDER[step - 1]
        if _send(db, col, lead, template_key):
            sent.append({"lead": lead.name or lead.phone, "step": step, "template": template_key})
            lead.seq_step = step + 1
            lead.next_followup_at = (utcnow() + timedelta(days=GAP_DAYS[step])) if step < 3 else None
        else:
            blocked.append(lead.name or lead.phone)
    db.commit()
    return dict(sent=sent, blocked=blocked, checked=len(due))
