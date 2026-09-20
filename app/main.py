"""College Growth OS API — FastAPI app + dashboard. All routes college-scoped;
every AI action passes guardrails and lands in the audit log."""
from datetime import timedelta

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from . import accred, authz, careers, connectors, counselor, guardrails, reports
from .config import BASE_DIR, DATA_DIR, SETTINGS
from .db import (AuditLog, AttainmentRun, College, Conversation, CounselorTask,
                 Course, CourseReg, EvidenceItem, Hostel, KeyDate, Lead, Message, MockInterview,
                 PlacementStat, QPaper, SessionLocal, Staff, StaffUser, SurveyResult,
                 TransportRoute, ensure_ready, get_db, init_db, utcnow)
from .followups import run_due
from .rag import ingest, retrieve

app = FastAPI(title="SeatSetu — Admissions & Accreditation OS", version="0.3.1")

# ── Admin gate: dashboard + staff APIs need the ss_admin cookie (parents' widget stays public) ──
import hashlib as _hl

PUBLIC_EXACT = {"/login", "/logout", "/home", "/guide", "/guide.pdf",
                "/presentation", "/presentation.pdf",
                "/presentation-college", "/presentation-college.pdf",
                "/favicon.ico"}
PUBLIC_PREFIX = ("/static/", "/widget/", "/api/chat/", "/api/widget/", "/api/webhooks/")


def _admin_token() -> str:
    return _hl.sha256(f"{SETTINGS.admin_password}|seatsetu-v1".encode()).hexdigest()


@app.middleware("http")
async def admin_gate(request: Request, call_next):
    path = request.url.path
    if path in PUBLIC_EXACT or path.startswith(PUBLIC_PREFIX):
        return await call_next(request)
    if request.cookies.get("ss_admin", "") == _admin_token():
        return await call_next(request)
    tok = request.cookies.get("ss_user", "")  # signed staff session
    if tok:
        d = authz.parse_token(tok)
        if d:
            return await call_next(request)
    if path.startswith("/api/"):
        return JSONResponse({"detail": "Admin login required"}, status_code=401)
    return RedirectResponse("/login", status_code=302)


_LOGIN_HTML = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>SeatSetu — Staff Login</title>
<style>body{margin:0;font-family:system-ui,sans-serif;background:#F7FAF9;display:flex;align-items:center;
justify-content:center;min-height:100vh}.box{background:#fff;border:1px solid #DCE9E6;border-radius:18px;
padding:40px 36px;width:min(380px,92vw);box-shadow:0 14px 40px #0b1f1c14;text-align:center}
h1{font-size:21px;color:#0B1F1C;margin:14px 0 4px}p{color:#5B7470;font-size:13.5px;margin:0 0 22px}
input{width:100%;padding:12px 14px;border:1px solid #DCE9E6;border-radius:10px;font-size:15px;margin-bottom:14px}
button{width:100%;padding:12px;border:0;border-radius:10px;background:linear-gradient(135deg,#0D9488,#0F766E);
color:#fff;font-size:15px;font-weight:600;cursor:pointer}.err{color:#B91C1C;font-size:13px;margin-bottom:12px}
.ft{margin-top:22px;font-size:11.5px;color:#62807a}.ft a{color:#0F766E;font-weight:600;text-decoration:none}</style></head>
<body><div class="box"><img src="/static/logo.png" alt="SeatSetu" style="max-width:210px">
<h1>Staff Login</h1><p>Admissions · Accreditation · Careers</p>
<!--ERR-->
<form method="post" action="/login"><input type="text" name="username" placeholder="Username (staff) — optional" autocomplete="username" style="margin-bottom:10px">
<input type="password" name="password" placeholder="Password" required autofocus>
<button>Login to dashboard</button></form>
<div class="ft">A product by <a href="https://poojasoftsolutions.com">Pooja Soft Solutions</a> · Ongole, AP<br>📞 92471 05525 · 💬 WhatsApp 75691 92211</div></div></body></html>"""


# ── Report generators (auth via admin_gate) ──
@app.get("/api/colleges/{college_id}/reports/management")
def report_management(college_id: int, days: int = 0, db: Session = Depends(get_db)):
    col = C(college_id, db)
    return reports.management(db, col, days or None)


@app.get("/api/colleges/{college_id}/reports/leads.csv")
def report_leads_csv(college_id: int, db: Session = Depends(get_db)):
    col = C(college_id, db)
    return Response(reports.leads_csv(db, col), media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=leads_col{college_id}.csv"})


@app.get("/api/colleges/{college_id}/reports/careers.csv")
def report_careers_csv(college_id: int, db: Session = Depends(get_db)):
    col = C(college_id, db)
    return Response(reports.careers_csv(db, col), media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=careers_col{college_id}.csv"})


@app.get("/reports/{college_id}")
def report_onepager(college_id: int, days: int = 0, db: Session = Depends(get_db)):
    col = C(college_id, db)
    return HTMLResponse(reports.render_html(db, col, days or None))


@app.get("/login")
def login_form():
    return HTMLResponse(_LOGIN_HTML)


@app.post("/login")
def login_submit(request: Request, password: str = Form(""), username: str = Form(""),
                 db: Session = Depends(get_db)):
    if username.strip():  # staff login
        su = (db.query(StaffUser)
                .filter_by(username=username.strip().lower(), active=True).first())
        if su and authz.verify(password, su.pw_hash):
            resp = RedirectResponse("/", status_code=303)
            resp.set_cookie("ss_user", authz.make_token(su.username, su.role, su.college_id),
                            httponly=True, samesite="lax", max_age=7 * 24 * 3600, secure=False)
            return resp
        return HTMLResponse(_LOGIN_HTML.replace("<!--ERR-->", '<div class="err">Wrong username or password</div>'),
                            status_code=401)
    if password and password == SETTINGS.admin_password:  # master admin
        resp = RedirectResponse("/", status_code=303)
        resp.set_cookie("ss_admin", _admin_token(), httponly=True, samesite="lax",
                        max_age=7 * 24 * 3600, secure=False)  # set secure=True behind HTTPS
        return resp
    return HTMLResponse(_LOGIN_HTML.replace("<!--ERR-->", '<div class="err">Wrong password — try again</div>'),
                        status_code=401)


@app.get("/api/me")
def me(request: Request, db: Session = Depends(get_db)):
    a = authz.actor(request, db)
    if not a:
        raise HTTPException(401, "Not signed in")
    return a


@app.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie("ss_admin")
    resp.delete_cookie("ss_user")
    return resp


# ── staff-user management (principal/admin) ──
def require_manager(request: Request, db: Session = Depends(get_db)) -> dict:
    a = authz.actor(request, db)
    if not a or a["role"] not in ("admin", "principal"):
        raise HTTPException(403, "Principal or admin role required")
    return a


class StaffUserIn(BaseModel):
    username: str
    password: str
    role: str = "counselor"
    name: str = ""


@app.get("/api/staff-users")
def staff_users(request: Request, db: Session = Depends(get_db)):
    if not authz.actor(request, db):
        raise HTTPException(401, "Not signed in")
    return [dict(id=u.id, username=u.username, role=u.role, name=u.name,
                 active=u.active, must_change=u.must_change) for u in
            db.query(StaffUser).filter_by(active=True).all()]


@app.post("/api/staff-users")
def add_staff_user(body: StaffUserIn, request: Request, db: Session = Depends(get_db)):
    require_manager(request, db)
    if body.role not in authz.ROLES:
        raise HTTPException(422, "Unknown role")
    if len(body.password) < 8:
        raise HTTPException(422, "Password must be at least 8 characters")
    if db.query(StaffUser).filter_by(username=body.username.lower()).first():
        raise HTTPException(422, "Username already exists")
    su = StaffUser(username=body.username.lower(), pw_hash=authz.hash_pw(body.password),
                         role=body.role, name=body.name)
    db.add(su)
    guardrails.log(0, "staff", "staff_user.created", {"username": su.username, "role": su.role}, db)
    db.commit()
    return dict(ok=True, id=su.id)


@app.post("/api/staff-users/{uid}/password")
def change_password(uid: int, body: dict, request: Request, db: Session = Depends(get_db)):
    a = authz.actor(request, db)
    if not a:
        raise HTTPException(401, "Not signed in")
    if a["role"] not in ("admin", "principal") and a["username"] !=             (db.query(StaffUser).get(uid).username if db.query(StaffUser).get(uid) else ""):
        raise HTTPException(403, "You can change only your own password")
    su = db.query(StaffUser).get(uid)
    if not su:
        raise HTTPException(404, "User not found")
    if not body.get("password") or len(body["password"]) < 8:
        raise HTTPException(422, "Password must be at least 8 characters")
    su.pw_hash = authz.hash_pw(body["password"])
    su.must_change = False
    guardrails.log(su.college_id or 0, "staff", "staff_user.password_changed",
                   {"username": su.username}, db)
    db.commit()
    return dict(ok=True)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])


@app.on_event("startup")
def startup():
    ensure_ready()


# ── Schemas ──────────────────────────────────────────────────────────────────
class ChatIn(BaseModel):
    text: str
    channel: str = "web"
    conversation_id: int | None = None
    consent_given: bool = False


class CollegeIn(BaseModel):
    name: str
    short: str = ""
    city: str = ""
    district: str = ""
    eapcet_code: str = ""
    website: str = ""
    phone: str = ""


class CKPIn(BaseModel):
    about: str = ""
    location_note: str = ""
    admission_process: str = ""
    courses: list[dict] = []
    hostels: list[dict] = []
    routes: list[dict] = []
    placements: list[dict] = []
    dates: list[dict] = []


class LeadUpdate(BaseModel):
    stage: str | None = None
    assigned_to: int | None = None
    note: str = ""


def C(college_id: int, db: Session) -> College:
    c = db.query(College).get(college_id)
    if not c:
        raise HTTPException(404, "College not found")
    return c


# ── Colleges / onboarding ────────────────────────────────────────────────────
@app.get("/api/colleges")
def list_colleges(db: Session = Depends(get_db)):
    return [dict(id=c.id, name=c.name, short=c.short, city=c.city,
                 eapcet_code=c.eapcet_code, kill_switch=c.kill_switch)
            for c in db.query(College).all()]


@app.post("/api/colleges")
def onboard(body: CollegeIn, db: Session = Depends(get_db), _mgr: dict = Depends(require_manager)):
    col = College(name=body.name, short=body.short or body.name.split()[0],
                  city=body.city, district=body.district,
                  eapcet_code=body.eapcet_code, website=body.website,
                  phone=body.phone, created_at=utcnow())
    db.add(col)
    db.flush()
    db.add(Staff(college_id=col.id, name="Principal", role="principal"))
    db.add(Staff(college_id=col.id, name="Counselor 1", role="counselor"))
    guardrails.log(col.id, "system", "college.onboarded", {"name": col.name}, db)
    db.commit()
    return dict(college_id=col.id, next_step="Fill the College Knowledge Pack in the dashboard CKP tab")


@app.get("/api/colleges/{college_id}")
def college_overview(college_id: int, db: Session = Depends(get_db)):
    c = C(college_id, db)
    stages = ["new", "ai_engaged", "contacted", "interested", "visit_booked",
              "visited", "applied", "seat_booked", "joined", "lost"]
    funnel = {s: db.query(Lead).filter_by(college_id=c.id, stage=s).count() for s in stages}
    sources = {}
    for (src,) in db.query(Lead.source).filter_by(college_id=c.id).distinct():
        ls = db.query(Lead).filter_by(college_id=c.id, source=src).all()
        sources[src] = dict(leads=len(ls),
                            joined=sum(1 for l in ls if l.stage == "joined"),
                            visits=sum(1 for l in ls if l.stage in ("visit_booked", "visited")))
    branches = {}
    for (b,) in db.query(Lead.branch_interest).filter_by(college_id=c.id).distinct():
        if b:
            branches[b] = db.query(Lead).filter_by(college_id=c.id, branch_interest=b).count()
    return dict(id=c.id, name=c.name, short=c.short, city=c.city,
                eapcet_code=c.eapcet_code, phone=c.phone, kill_switch=c.kill_switch,
                funnel=funnel, sources=sources, branches=branches,
                total_leads=sum(funnel.values()),
                due_followups=db.query(Lead).filter_by(college_id=c.id).filter(
                    Lead.next_followup_at <= utcnow().replace(tzinfo=None) + timedelta(days=7),
                    Lead.seq_step >= 1, Lead.stage.notin_(["joined", "lost"])).count(),
                open_tasks=db.query(CounselorTask).filter_by(college_id=c.id, done=False).count())


# ── Chat (the AI counselor) ──────────────────────────────────────────────────
@app.post("/api/chat/{college_id}")
def chat(college_id: int, body: ChatIn, db: Session = Depends(get_db)):
    try:
        return counselor.handle_parent_message(db, college_id, body.text, body.channel,
                                               body.conversation_id, body.consent_given)
    except guardrails.GuardrailViolation as e:
        raise HTTPException(403, e.reason)


@app.get("/api/widget/{college_id}/info")
def widget_info(college_id: int, db: Session = Depends(get_db)):
    c = C(college_id, db)
    return dict(name=c.name, short=c.short, color=c.brand_color, phone=c.phone)


@app.get("/api/colleges/{college_id}/conversations")
def conversations(college_id: int, db: Session = Depends(get_db)):
    convs = (db.query(Conversation).filter_by(college_id=college_id)
               .order_by(Conversation.id.desc()).limit(40).all())
    out = []
    for cv in convs:
        ms = db.query(Message).filter_by(conversation_id=cv.id).order_by(Message.id).all()
        lead = db.query(Lead).get(cv.lead_id) if cv.lead_id else None
        out.append(dict(id=cv.id, channel=cv.channel, language=cv.language,
                        status=cv.status, lead=(lead.name or lead.phone) if lead else "Anonymous",
                        messages=[dict(role=m.role, text=m.text, citations=m.citations,
                                       flagged=m.flagged) for m in ms]))
    return out


# ── CKP (College Knowledge Pack) ─────────────────────────────────────────────
@app.get("/api/colleges/{college_id}/ckp")
def get_ckp(college_id: int, db: Session = Depends(get_db)):
    c = C(college_id, db)
    def rows(q):
        return [{k: v for k, v in r.__dict__.items() if not k.startswith("_")} for r in q]
    return dict(about=c.about, location_note=c.location_note,
                admission_process=c.admission_process,
                courses=rows(db.query(Course).filter_by(college_id=c.id).all()),
                hostels=rows(db.query(Hostel).filter_by(college_id=c.id).all()),
                routes=rows(db.query(TransportRoute).filter_by(college_id=c.id).all()),
                placements=rows(db.query(PlacementStat).filter_by(college_id=c.id).all()),
                dates=rows(db.query(KeyDate).filter_by(college_id=c.id).all()))


@app.post("/api/colleges/{college_id}/ckp")
def save_ckp(college_id: int, body: CKPIn, db: Session = Depends(get_db)):
    c = C(college_id, db)
    c.about = body.about or c.about
    c.location_note = body.location_note or c.location_note
    c.admission_process = body.admission_process or c.admission_process

    def replace(model, rows, fields):
        db.query(model).filter_by(college_id=c.id).delete()
        for r in rows:
            db.add(model(college_id=c.id, **{f: r.get(f) for f in fields if r.get(f) is not None}))

    replace(Course, body.courses, ["name", "code", "intake", "convener_fee", "mgmt_fee",
                                   "mgmt_note", "cutoff_note", "highlights"])
    replace(Hostel, body.hostels, ["for_whom", "ac", "fee_per_year", "facilities"])
    replace(TransportRoute, body.routes, ["from_place", "distance_km", "fee_per_year"])
    replace(PlacementStat, body.placements, ["year", "placed_pct", "offers", "companies",
                                             "top_lpa", "avg_lpa", "note"])
    replace(KeyDate, body.dates, ["label", "when_note"])
    db.commit()

    # re-embed tenant prose (idempotent: clear tenant chunks first)
    from .db import KbChunk
    db.query(KbChunk).filter(KbChunk.college_id == c.id).delete()
    # Tenant-only prose: strictly THIS college's approved facts (never cross-tenant)
    prose = []
    if c.about:
        prose.append(dict(title=f"{c.short or c.name} — About & Location", section="about",
                          content=(c.about + " " + (c.location_note or "")).strip()))
    if c.admission_process:
        prose.append(dict(title=f"{c.short or c.name} — Admission Process & Documents",
                          section="process", content=c.admission_process))
    n = 0
    for p in prose:
        if p["content"]:
            n += ingest(content=p["content"], title=p["title"], section=p["section"],
                        scope="tenant", college_id=c.id, db=db)
    guardrails.log(c.id, "user", "ckp.updated", {"chunks": n}, db)
    db.commit()
    return dict(ok=True, chunks_indexed=n)


# ── Leads CRM ────────────────────────────────────────────────────────────────
@app.get("/api/colleges/{college_id}/leads")
def leads(college_id: int, db: Session = Depends(get_db)):
    ls = (db.query(Lead).filter_by(college_id=college_id)
            .order_by(Lead.score.desc()).all())
    staff = {s.id: s.name for s in db.query(Staff).filter_by(college_id=college_id).all()}
    return [dict(id=l.id, name=l.name, phone=l.phone, town=l.town, source=l.source,
                 campaign=l.campaign, stage=l.stage, score=l.score,
                 branch_interest=l.branch_interest, rank_or_marks=l.rank_or_marks,
                 consent=l.consent, assigned=staff.get(l.assigned_to, "—"),
                 seq_step=l.seq_step,
                 next_followup=str(l.next_followup_at)[:16] if l.next_followup_at else None)
            for l in ls]


@app.post("/api/leads/{lead_id}")
def update_lead(lead_id: int, body: LeadUpdate, db: Session = Depends(get_db)):
    l = db.query(Lead).get(lead_id)
    if not l:
        raise HTTPException(404, "Lead not found")
    if body.stage:
        l.stage = body.stage
        if body.stage == "visit_booked":
            col = db.query(College).get(l.college_id)
            counselor.make_task(db, col, l, "visit",
                                f"Campus visit booked for {l.name or l.phone} — prepare kit")
        if body.stage == "joined":
            l.next_followup_at = None
    if body.assigned_to:
        l.assigned_to = body.assigned_to
    counselor.rescore(l)
    guardrails.log(l.college_id, "staff", "lead.updated",
                   {"lead_id": l.id, "stage": l.stage, "note": body.note[:120]}, db)
    db.commit()
    return dict(ok=True, stage=l.stage, score=l.score)


@app.post("/api/leads/{lead_id}/stop")
def stop_marketing(lead_id: int, db: Session = Depends(get_db)):
    """DPDP withdrawal — stop all marketing immediately."""
    l = db.query(Lead).get(lead_id)
    if not l:
        raise HTTPException(404, "Lead not found")
    l.consent = False
    l.stage = "lost"
    l.lost_reason = "opted_out (DPDP withdrawal)"
    l.next_followup_at = None
    guardrails.log(l.college_id, "staff", "consent.withdrawn", {"lead_id": l.id}, db)
    db.commit()
    return dict(ok=True)


@app.get("/api/colleges/{college_id}/tasks")
def tasks(college_id: int, db: Session = Depends(get_db)):
    ts = (db.query(CounselorTask).filter_by(college_id=college_id, done=False)
            .order_by(CounselorTask.id.desc()).limit(50).all())
    out = []
    for t in ts:
        l = db.query(Lead).get(t.lead_id) if t.lead_id else None
        s = db.query(Staff).get(t.staff_id) if t.staff_id else None
        out.append(dict(id=t.id, kind=t.kind, note=t.note,
                        lead=(l.name or l.phone) if l else "—",
                        phone=l.phone if l else "",
                        assigned=s.name if s else "—"))
    return out


@app.post("/api/tasks/{task_id}/done")
def task_done(task_id: int, db: Session = Depends(get_db)):
    t = db.query(CounselorTask).get(task_id)
    if not t:
        raise HTTPException(404, "Task not found")
    t.done = True
    guardrails.log(t.college_id, "staff", "task.done", {"task_id": t.id, "kind": t.kind}, db)
    db.commit()
    return dict(ok=True)


# ── Follow-up engine ─────────────────────────────────────────────────────────
@app.get("/api/colleges/{college_id}/followups")
def followup_queue(college_id: int, db: Session = Depends(get_db)):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    due = (db.query(Lead).filter_by(college_id=college_id)
             .filter(Lead.consent == True,                     # noqa: E712
                     Lead.next_followup_at <= now + timedelta(days=30),
                     Lead.seq_step >= 1, Lead.seq_step <= 3,
                     Lead.stage.notin_(["joined", "lost"]))
             .order_by(Lead.next_followup_at).all())
    return [dict(id=l.id, name=l.name or l.phone, stage=l.stage, seq_step=l.seq_step,
                 next=str(l.next_followup_at)[:16] if l.next_followup_at else None,
                 due_now=bool(l.next_followup_at and l.next_followup_at <= now))
            for l in due]


@app.post("/api/run/followups/{college_id}")
def run_followups(college_id: int, db: Session = Depends(get_db)):
    try:
        guardrails.check_kill_switch(college_id, db)
        return run_due(db, college_id)
    except guardrails.GuardrailViolation as e:
        raise HTTPException(403, e.reason)


# ── Meta lead-ads webhook ────────────────────────────────────────────────────
@app.get("/api/webhooks/meta-lead")
def meta_verify(hub_mode: str = "", hub_verify_token: str = "", hub_challenge: str = ""):
    if hub_mode == "subscribe" and hub_verify_token == SETTINGS.meta_verify_token:
        return int(hub_challenge or 0)
    raise HTTPException(403, "verify token mismatch")


@app.post("/api/webhooks/meta-lead")
async def meta_lead(payload: dict, request: Request, db: Session = Depends(get_db)):
    if SETTINGS.meta_app_secret:  # verify X-Hub-Signature-256 when configured
        import hmac as _hm
        raw = await request.body()
        sig = request.headers.get("x-hub-signature-256", "")
        expected = "sha256=" + _hm.new(SETTINGS.meta_app_secret.encode(), raw, _hl.sha256).hexdigest()
        if not _hm.compare_digest(sig, expected):
            return JSONResponse({"detail": "bad signature"}, status_code=403)
    parsed = connectors.parse_meta_lead(payload)
    if not parsed or not parsed.get("phone"):
        return dict(ok=True, note="no phone in payload — ignored")  # 200 fast (Meta requires)
    col = db.query(College).first()  # single-tenant webhooks: route by form/page in production
    if not col:
        raise HTTPException(404, "No college configured")
    lead = counselor.find_or_create_lead(db, col, parsed["phone"], "whatsapp",
                                         parsed["name"], parsed["town"],
                                         parsed["branch_interest"])
    lead.source = "meta_ad"
    lead.campaign = parsed["campaign"]
    lead.consent = True                       # lead-ads form carries its own consent disclaimer
    lead.consent_at = utcnow()
    counselor.rescore(lead)
    counselor.schedule_sequence(db, col, lead)
    guardrails.log(col.id, "system", "lead.meta_ad",
                   {"lead_id": lead.id, "campaign": lead.campaign}, db)
    db.commit()
    return dict(ok=True, lead_id=lead.id)


# ── Compliance views ─────────────────────────────────────────────────────────
@app.get("/api/colleges/{college_id}/consents")
def consents(college_id: int, db: Session = Depends(get_db)):
    ls = db.query(Lead).filter_by(college_id=college_id).all()
    return [dict(id=l.id, name=l.name or "—", phone=l.phone, consent=l.consent,
                 at=str(l.consent_at)[:16] if l.consent_at else None) for l in ls]


@app.get("/api/colleges/{college_id}/audit")
def audit(college_id: int, db: Session = Depends(get_db)):
    ls = (db.query(AuditLog).filter_by(college_id=college_id)
            .order_by(AuditLog.id.desc()).limit(120).all())
    return [dict(id=l.id, actor=l.actor, action=l.action, detail=l.detail,
                 at=str(l.created_at)[:19]) for l in ls]


@app.post("/api/colleges/{college_id}/killswitch/{state}")
def killswitch(college_id: int, state: str, db: Session = Depends(get_db), _mgr: dict = Depends(require_manager)):
    c = C(college_id, db)
    c.kill_switch = state == "on"
    guardrails.log(college_id, "staff", f"killswitch.{state}", {}, db)
    db.commit()
    return dict(kill_switch=c.kill_switch)


@app.get("/api/kb/search")
def kb_search(q: str, college_id: int = 0, db: Session = Depends(get_db)):
    hits = retrieve(q, college_id or None, k=6, db=db)
    return [dict(title=c.title, section=c.section, score=round(s, 4),
                 snippet=c.content[:240] + "…") for c, s, v, l in hits]


# ── SeatSetu Accred (Module B) ───────────────────────────────────────────────
class RegIn(BaseModel):
    course_name: str
    code: str = ""
    semester: str = ""
    academic_year: str = "2025-26"
    cos: list[dict]                    # [{no, desc, bloom, pos:[…]}]
    co_po_map: dict = {}
    target: float = 2.0


@app.post("/api/colleges/{college_id}/accred/regs")
def create_reg(college_id: int, body: RegIn, db: Session = Depends(get_db)):
    C(college_id, db)
    reg = CourseReg(college_id=college_id, course_name=body.course_name, code=body.code,
                    semester=body.semester, academic_year=body.academic_year,
                    cos=body.cos, co_po_map=body.co_po_map, target=body.target)
    db.add(reg)
    guardrails.log(college_id, "staff", "accred.reg_created", {"course": body.course_name}, db)
    db.commit()
    return dict(reg_id=reg.id)


@app.get("/api/colleges/{college_id}/accred/regs")
def list_regs(college_id: int, db: Session = Depends(get_db)):
    C(college_id, db)
    regs = db.query(CourseReg).filter_by(college_id=college_id).all()
    out = []
    for r in regs:
        runs = (db.query(AttainmentRun).filter_by(reg_id=r.id)
                  .order_by(AttainmentRun.id.desc()).first())
        out.append(dict(id=r.id, course_name=r.course_name, code=r.code,
                        semester=r.semester, academic_year=r.academic_year,
                        cos=r.cos, co_po_map=r.co_po_map, target=r.target,
                        last_run=dict(students=runs.students,
                                      at=str(runs.created_at)[:16]) if runs else None))
    return out


@app.post("/api/colleges/{college_id}/accred/regs/{reg_id}/upload")
async def upload_marks(college_id: int, reg_id: int, file: bytes = File(...),
                       filename: str = Form("marks.csv"), db: Session = Depends(get_db)):
    if len(file) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large — max 5 MB")
    C(college_id, db)
    reg = db.query(CourseReg).get(reg_id)
    if not reg or reg.college_id != college_id:
        raise HTTPException(404, "Course registration not found")
    try:
        students, notes = accred.parse_marks(filename, file)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not students:
        raise HTTPException(400, "No student rows parsed — check the file format.")
    report = accred.compute_attainment(reg, students)
    run = AttainmentRun(college_id=college_id, reg_id=reg_id, filename=filename,
                        students=len(students), result=report)
    db.add(run)
    guardrails.log(college_id, "staff", "accred.attainment_run",
                   {"reg": reg.course_name, "students": len(students),
                    "po_direct": report["po_direct"]}, db)
    db.commit()
    return dict(run_id=run.id, notes=notes, report=report)


@app.get("/api/colleges/{college_id}/accred/runs")
def list_runs(college_id: int, db: Session = Depends(get_db)):
    runs = (db.query(AttainmentRun).filter_by(college_id=college_id)
              .order_by(AttainmentRun.id.desc()).limit(30).all())
    out = []
    for r in runs:
        reg = db.query(CourseReg).get(r.reg_id)
        out.append(dict(id=r.id, reg_id=r.reg_id, course=reg.course_name if reg else "?",
                        filename=r.filename, students=r.students, at=str(r.created_at)[:16]))
    return out


@app.get("/api/colleges/{college_id}/accred/runs/{run_id}")
def get_run(college_id: int, run_id: int, db: Session = Depends(get_db)):
    run = db.query(AttainmentRun).get(run_id)
    if not run or run.college_id != college_id:
        raise HTTPException(404, "Run not found")
    survey = (db.query(SurveyResult).filter_by(college_id=college_id)
                .order_by(SurveyResult.id.desc()).first())
    report = run.result
    if survey and survey.po_indirect:
        report = accred.blend_indirect(report, survey.po_indirect)
    return dict(run=dict(id=run.id, course=report.get("course"), students=run.students,
                         filename=run.filename, at=str(run.created_at)[:16]),
                report=report)


class EvidenceIn(BaseModel):
    criterion: str
    title: str
    owner: str = ""
    file_note: str = ""


@app.get("/api/colleges/{college_id}/accred/aqar")
def aqar(college_id: int, db: Session = Depends(get_db)):
    C(college_id, db)
    rows = db.query(EvidenceItem).filter_by(college_id=college_id).all()
    return accred.aqar_status(rows)


@app.post("/api/colleges/{college_id}/accred/evidence")
def add_evidence(college_id: int, body: EvidenceIn, db: Session = Depends(get_db)):
    C(college_id, db)
    e = EvidenceItem(college_id=college_id, criterion=body.criterion, title=body.title,
                     owner=body.owner, file_note=body.file_note)
    db.add(e)
    guardrails.log(college_id, "staff", "accred.evidence_added",
                   {"criterion": body.criterion, "title": body.title[:80]}, db)
    db.commit()
    return dict(id=e.id)


@app.post("/api/accred/evidence/{evidence_id}/status")
def evidence_status(evidence_id: int, body: dict, db: Session = Depends(get_db)):
    e = db.query(EvidenceItem).get(evidence_id)
    if not e:
        raise HTTPException(404, "Evidence not found")
    if body.get("status") in ("pending", "collected", "na"):
        e.status = body["status"]
    if body.get("file_note") is not None:
        e.file_note = body["file_note"]
    guardrails.log(e.college_id, "staff", "accred.evidence_update",
                   {"id": e.id, "status": e.status}, db)
    db.commit()
    return dict(ok=True)


@app.get("/api/colleges/{college_id}/accred/evidence")
def list_evidence(college_id: int, db: Session = Depends(get_db)):
    rows = (db.query(EvidenceItem).filter_by(college_id=college_id)
              .order_by(EvidenceItem.criterion).all())
    return [dict(id=e.id, criterion=e.criterion, title=e.title, owner=e.owner,
                 status=e.status, file_note=e.file_note) for e in rows]


class SurveyIn(BaseModel):
    academic_year: str = "2025-26"
    respondents: int = 0
    po_indirect: dict


@app.post("/api/colleges/{college_id}/accred/survey")
def add_survey(college_id: int, body: SurveyIn, db: Session = Depends(get_db)):
    C(college_id, db)
    db.add(SurveyResult(college_id=college_id, academic_year=body.academic_year,
                        respondents=body.respondents, po_indirect=body.po_indirect))
    guardrails.log(college_id, "staff", "accred.survey_added",
                   {"respondents": body.respondents}, db)
    db.commit()
    return dict(ok=True)


class QPaperIn(BaseModel):
    reg_id: int
    title: str = "Model Question Paper"
    sections: list[dict]                 # [{name, count, marks, blooms:[…]}]


@app.post("/api/colleges/{college_id}/accred/qpaper")
def make_qpaper(college_id: int, body: QPaperIn, db: Session = Depends(get_db)):
    C(college_id, db)
    reg = db.query(CourseReg).get(body.reg_id)
    if not reg or reg.college_id != college_id:
        raise HTTPException(404, "Course registration not found")
    try:
        paper = accred.generate_qpaper(reg, body.sections)
    except ValueError as e:
        raise HTTPException(400, str(e))
    qp = QPaper(college_id=college_id, reg_id=body.reg_id, title=body.title,
                total_marks=paper["total_marks"], paper=paper)
    db.add(qp)
    guardrails.log(college_id, "staff", "accred.qpaper_generated",
                   {"reg": reg.course_name, "total": paper["total_marks"]}, db)
    db.commit()
    return dict(id=qp.id, **paper)


# ── SeatSetu Careers (Module C) ──────────────────────────────────────────────
class InterviewIn(BaseModel):
    student_name: str
    roll: str = ""
    branch: str = "CSE"
    role: str = "Software / IT"


@app.post("/api/colleges/{college_id}/careers/start")
def careers_start(college_id: int, body: InterviewIn, db: Session = Depends(get_db)):
    C(college_id, db)
    qs = careers.build_interview(body.branch, body.role)
    m = MockInterview(college_id=college_id, student_name=body.student_name,
                      roll=body.roll, branch=body.branch, role=body.role,
                      questions=qs, created_at=utcnow())
    db.add(m)
    guardrails.log(college_id, "staff", "careers.interview_started",
                   {"student": body.student_name, "branch": body.branch}, db)
    db.commit()
    return dict(id=m.id, questions=[{k: q[k] for k in ("no", "type", "q")} for q in qs])


@app.post("/api/careers/{interview_id}/answer")
def careers_answer(interview_id: int, body: dict, db: Session = Depends(get_db)):
    m = db.query(MockInterview).get(interview_id)
    if not m:
        raise HTTPException(404, "Interview not found")
    no = int(body.get("no", 0))
    text = (body.get("text") or "").strip()
    score, tips = None, ""
    for q in m.questions:
        if q["no"] == no:
            score, tips = careers.score_answer(text, q)
            q["answer"], q["score"], q["tips"] = text[:2000], score, tips
            break
    flag_modified(m, "questions")     # force JSON mutation to persist
    guardrails.log(m.college_id, "ai", "careers.answer_scored",
                   {"interview": m.id, "q": no, "score": score}, db)
    db.commit()
    return dict(score=score, tips=tips)


@app.post("/api/careers/{interview_id}/finish")
def careers_finish(interview_id: int, db: Session = Depends(get_db)):
    m = db.query(MockInterview).get(interview_id)
    if not m:
        raise HTTPException(404, "Interview not found")
    m.overall = careers.overall_score(m.questions)
    m.status = "done"
    guardrails.log(m.college_id, "staff", "careers.interview_done",
                   {"student": m.student_name, "overall": m.overall}, db)
    db.commit()
    return dict(ok=True, overall=m.overall)


@app.get("/api/careers/{interview_id}")
def careers_report(interview_id: int, db: Session = Depends(get_db)):
    m = db.query(MockInterview).get(interview_id)
    if not m:
        raise HTTPException(404, "Interview not found")
    return dict(id=m.id, student=m.student_name, roll=m.roll, branch=m.branch,
                role=m.role, overall=m.overall, status=m.status,
                questions=[{k: q.get(k) for k in ("no", "type", "q", "answer", "score", "tips")}
                           for q in m.questions])


@app.get("/api/colleges/{college_id}/careers/summary")
def careers_summary(college_id: int, db: Session = Depends(get_db)):
    C(college_id, db)
    rows = (db.query(MockInterview).filter_by(college_id=college_id)
              .order_by(MockInterview.id.desc()).all())
    done = [r for r in rows if r.status == "done"]
    return dict(total=len(rows),
                avg=round(sum(r.overall for r in done) / len(done), 1) if done else None,
                recent=[dict(id=r.id, student=r.student_name, branch=r.branch,
                             overall=r.overall, at=str(r.created_at)[:10]) for r in rows[:12]])


@app.get("/api/colleges/{college_id}/careers/export")
def careers_export(college_id: int, db: Session = Depends(get_db)):
    C(college_id, db)
    rows = (db.query(MockInterview).filter_by(college_id=college_id, status="done")
              .order_by(MockInterview.created_at).all())
    data = careers.evidence_csv(rows)
    return Response(data, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=seatsetu_training_evidence.csv"})


# ── UI ───────────────────────────────────────────────────────────────────────
@app.get("/")
def index():
    return FileResponse(BASE_DIR / "app" / "static" / "index.html")


@app.get("/home")
def landing():
    return FileResponse(BASE_DIR / "app" / "static" / "landing.html")


@app.get("/guide")
def guide():
    return FileResponse(BASE_DIR / "docs" / "User_Guide.html", media_type="text/html")


@app.get("/guide.pdf")
def guide_pdf():
    return FileResponse(BASE_DIR / "docs" / "SeatSetu_User_Guide.pdf",
                        media_type="application/pdf",
                        headers={"Content-Disposition": "inline; filename=SeatSetu_User_Guide.pdf"})


@app.get("/presentation")
def presentation_partner():
    return FileResponse(BASE_DIR / "docs" / "Presentation_Partner.html", media_type="text/html")


@app.get("/presentation.pdf")
def presentation_partner_pdf():
    return FileResponse(BASE_DIR / "docs" / "SeatSetu_Partner_Deck.pdf",
                        media_type="application/pdf",
                        headers={"Content-Disposition": "inline; filename=SeatSetu_Partner_Deck.pdf"})


@app.get("/presentation-college")
def presentation_college():
    return FileResponse(BASE_DIR / "docs" / "Presentation_Colleges.html", media_type="text/html")


@app.get("/presentation-college.pdf")
def presentation_college_pdf():
    return FileResponse(BASE_DIR / "docs" / "SeatSetu_College_Deck.pdf",
                        media_type="application/pdf",
                        headers={"Content-Disposition": "inline; filename=SeatSetu_College_Deck.pdf"})


@app.get("/favicon.ico")
def favicon():
    return FileResponse(BASE_DIR / "app" / "static" / "favicon.png")


@app.get("/widget/{college_id}")
def widget(college_id: int):
    return FileResponse(BASE_DIR / "app" / "static" / "widget.html")


app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")
