"""SeatSetu v0.4 — AI that ACTS: visit booking, brochure capture, next-best-actions, reply coach."""
import re
from datetime import datetime, timedelta

from . import counselor, guardrails
from .db import (CounselorTask, Conversation, EvidenceItem, FollowUpLog, Lead,
                 Message, MockInterview, CourseReg)

PHONE10 = re.compile(r"^[6-9]\d{9}$")


def _bad(msg):
    return {"ok": False, "error": msg}


def book_visit(db, col, name: str, phone: str, date: str, branch: str = "",
               town: str = "", consent: bool = False):
    """Parent books a campus visit from the widget → lead + counselor task."""
    if not name or len(name.strip()) < 2:
        return _bad("Please share your full name")
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if not PHONE10.match(digits):
        return _bad("Please enter a valid 10-digit mobile number")
    try:
        visit_date = datetime.strptime(date, "%Y-%m-%d").date()
    except Exception:
        return _bad("Please choose a visit date")
    if visit_date < datetime.utcnow().date():
        return _bad("Visit date cannot be in the past")

    lead = counselor.find_or_create_lead(db, col, digits, "website_chat", name.strip(), town.strip(), branch)
    lead.stage = "visit_booked"
    if branch:
        lead.branch_interest = branch
    if consent:
        lead.consent = True
        lead.consent_at = datetime.utcnow()
    counselor.rescore(lead)
    task = CounselorTask(college_id=col.id, lead_id=lead.id, kind="visit",
                         note=f"Campus visit booked via website for {visit_date.strftime('%d %b %Y')} "
                              f"({branch or 'branch NA'}) — confirm by phone & arrange POA/Faculty meet",
                         due_at=datetime.combine(visit_date, datetime.min.time()))
    db.add(task)
    guardrails.log(col.id, "system", "widget.visit_booked",
                   {"lead": lead.id, "date": str(visit_date), "branch": branch}, db)
    db.commit()
    friendly = visit_date.strftime("%A, %d %B")
    return {"ok": True, "lead_id": lead.id,
            "message": f"Visit booked for {friendly} ✅ Our admissions officer will call {digits[-5:].rjust(10, '•')} to confirm. "
                       f"Please bring: EAPCET hall ticket & rank card, SSC/Intermediate memos, Aadhaar."}


def brochure_lead(db, col, name: str, phone: str):
    """Brochure download gate → captures the lead, returns the PDF URL."""
    if not name or len(name.strip()) < 2:
        return _bad("Please share your full name")
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if not PHONE10.match(digits):
        return _bad("Please enter a valid 10-digit mobile number")
    lead = counselor.find_or_create_lead(db, col, digits, "website_chat", name.strip(), "", "")
    lead.consent = True
    lead.consent_at = datetime.utcnow()
    counselor.rescore(lead)
    db.add(CounselorTask(college_id=col.id, lead_id=lead.id, kind="call",
                         note="Parent requested the college brochure on the website — call today",
                         due_at=datetime.utcnow()))
    guardrails.log(col.id, "system", "widget.brochure_lead", {"lead": lead.id}, db)
    db.commit()
    return {"ok": True, "lead_id": lead.id, "url": f"/brochure/{col.id}.pdf"}


def next_actions(db, col):
    """Prescriptive 'what should staff do today' — computed from live data."""
    out, today = [], datetime.utcnow()
    due = (db.query(Lead).filter(Lead.college_id == col.id,
                                 Lead.next_followup_at != None,  # noqa: E711
                                 Lead.next_followup_at <= today,
                                 Lead.stage.notin_(["joined", "lost"])).count())
    if due:
        out.append({"icon": "⏰", "sev": "red", "tab": "followups",
                    "text": f"{due} follow-up(s) DUE right now — parents are cooling off. Run the sequence."})
    open_tasks = (db.query(CounselorTask)
                  .filter(CounselorTask.college_id == col.id, CounselorTask.done == False).all())  # noqa: E712
    handoffs = [t for t in open_tasks if t.kind == "handoff"]
    if handoffs:
        out.append({"icon": "🙋", "sev": "red", "tab": "tasks",
                    "text": f"{len(handoffs)} parent(s) asked for a human — AI handed them off. Call before they try another college."})
    visits = [t for t in open_tasks if t.kind == "visit"
              and t.due_at and t.due_at.date() <= today.date() + timedelta(days=2)]
    if visits:
        out.append({"icon": "📅", "sev": "amber", "tab": "tasks",
                    "text": f"{len(visits)} campus visit(s) in the next 48h — confirm by phone today (no-shows kill conversions)."})
    idle_hot = (db.query(Lead)
                .filter(Lead.college_id == col.id, Lead.score >= 50,
                        Lead.stage.in_(["ai_engaged", "contacted", "interested"]),
                        (Lead.last_inbound_at == None) | (Lead.last_inbound_at < today - timedelta(hours=48)))  # noqa: E711
                .order_by(Lead.score.desc()).limit(3).all())
    if idle_hot:
        names = ", ".join(f"{l.name or 'Parent ' + str(l.id)} ({l.phone})" for l in idle_hot)
        out.append({"icon": "🔥", "sev": "amber", "tab": "leads",
                    "text": f"Hot leads going cold (no contact in 48h): {names}. Personal call beats any template."})
    dec31 = datetime(datetime.utcnow().year + (1 if today.month == 12 and today.day > 31 else 0), 12, 31)
    days_left = (dec31 - today).days
    ev_pending = (db.query(EvidenceItem)
                  .filter(EvidenceItem.college_id == col.id, EvidenceItem.status == "pending").count())
    if ev_pending and days_left < 120:
        out.append({"icon": "🎯", "sev": "amber" if days_left < 60 else "teal", "tab": "accred",
                    "text": f"AQAR due Dec 31 — {days_left} days left, {ev_pending} evidence items pending. Collect weekly."})
    week_ago = today - timedelta(days=7)
    weekly_mi = (db.query(MockInterview)
                 .filter(MockInterview.college_id == col.id, MockInterview.created_at >= week_ago).count())
    if weekly_mi == 0:
        out.append({"icon": "💼", "sev": "teal", "tab": "careers",
                    "text": "No mock interviews this week — schedule the first batch (NAAC 5.1.2 evidence builds from these)."})
    if not out:
        out.append({"icon": "✅", "sev": "teal", "tab": "overview",
                    "text": "Everything on track — no overdue actions. Call one hot lead anyway; momentum is everything."})
    return out


TOPIC_SUGGEST = {
    "fees": "Share the exact convener & management fee for their branch, mention the token amount, and offer the campus visit — parents who ask fees are comparing, so end with 'what branch are you looking at?'",
    "hostel": "Confirm hostel availability + fee, then reassure on safety (warden, mess, study hours) and offer to send hostel photos on WhatsApp.",
    "placement": "Give last year's real numbers only. Never promise. Then offer: 'Meet our placement officer this Saturday?'",
    "cutoff": "Compare their rank with last year's closing ranks honestly (✅/🟡/🔴), and stress it's decided in convener counseling — invite them for a counselor meeting.",
    "transport": "List the routes near their town with the fee; offer the transport officer's callback for door-route confirmation.",
    "process": "Walk them through certificate verification → web options → seat allotment, and offer help with documents list on WhatsApp.",
}


def coach_reply(db, col, conversation_id: int | None = None, text: str = "",
                stage: str = "new", lang: str = "en"):
    """Reply Coach: suggests the next human reply (LLM if configured, else playbook templates)."""
    from .llm import complete, llm_available  # lazy import
    last_parent, topic = text or "", ""
    if conversation_id:
        row = (db.query(Message)
               .filter(Message.conversation_id == conversation_id,
                       Message.role == "parent")
               .order_by(Message.id.desc()).first())
        if row:
            last_parent = row.text
    t = (last_parent or "").lower()
    for key in ("fees", "hostel", "placement", "cutoff", "transport", "process"):
        import re as _re
        if _re.search(counselor.TOPICS.get(key, r"(?!)"), t):
            topic = key
            break
    stage_line = {"new": "Parent just started chatting — be warm, answer exactly, then ask their name/town.",
                  "ai_engaged": "Parent is engaging — give one fact + one question to keep momentum.",
                  "contacted": "You've called once — reference the call, don't restart the pitch.",
                  "interested": "Parent is warm — push for a DATE: campus visit or counselor meeting this week.",
                  "visit_booked": "Visit booked — confirm by call, share directions & document list.",
                  "visited": "They visited! Follow up same day: feel, doubts, token amount next step.",
                  "applied": "Application stage — nudge gently on documents pending / token payment deadline."}.get(stage, "")
    if llm_available():
        sys = (f"You are the reply coach for {col.name}'s admissions counselor. Draft ONE short WhatsApp reply "
               f"(max 40 words) a counselor can send to a parent. Stage: {stage}. {stage_line} "
               f"Only use facts the counselor already knows; never invent fees/placements/scholarships; "
               f"end with a soft next step. Match the parent's language (Telugu/Tenglish/English).")
        sug = complete(sys, f"Parent said: {last_parent or '(no message yet)'}")
        if sug:
            return {"suggestion": sug.strip(), "brain": "llm", "topic": topic or "general"}
    if topic and topic in TOPIC_SUGGEST:
        return {"suggestion": "Playbook: " + TOPIC_SUGGEST[topic], "brain": "playbook", "topic": topic}
    return {"suggestion": ("Playbook: answer their exact question with the approved number, then advance with ONE question — "
                           + (stage_line or "ask for name, town and branch to score the lead.")),
            "brain": "playbook", "topic": topic or "general"}
