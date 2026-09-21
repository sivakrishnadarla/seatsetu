"""College Growth OS API — FastAPI app + dashboard. All routes college-scoped;
every AI action passes guardrails and lands in the audit log."""
from datetime import datetime, timedelta

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from . import accred, actions, authz, brochure, careers, connectors, counselor, guardrails, reports
from .config import BASE_DIR, DATA_DIR, SETTINGS
from .db import (AuditLog, AttainmentRun, College, Competitor, Conversation, CounselorTask, PracticePass, FollowUpLog,
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
PUBLIC_PREFIX = ("/static/", "/widget/", "/api/chat/", "/api/widget/", "/api/webhooks/", "/brochure/", "/manifest.json", "/sw.js", "/sell", "/practice", "/api/practice/")


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


# ── simple per-IP rate limit for parent-facing chat (premium hardening) ──
CHAT_RATE: dict = {}
CHAT_LIMIT, CHAT_WINDOW = 40, 60  # 40 msgs / 60s per IP


@app.middleware("http")
async def chat_rate_limit(request: Request, call_next):
    if request.url.path.startswith("/api/chat/") and request.method == "POST":
        import time as _t
        ip = (request.client.host if request.client else "?")
        now = _t.time()
        hits = [t for t in CHAT_RATE.get(ip, []) if now - t < CHAT_WINDOW]
        if len(hits) >= CHAT_LIMIT:
            return JSONResponse({"detail": "Too many messages — please slow down."}, status_code=429)
        hits.append(now)
        CHAT_RATE[ip] = hits
    return await call_next(request)


_LOGIN_HTML = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>SeatSetu — Staff Login</title>
<link rel="icon" href="/static/favicon-32.png"><link rel="apple-touch-icon" href="/static/apple-touch-icon.png">
<link rel="manifest" href="/manifest.json"><meta name="theme-color" content="#0F766E">
<style>body{margin:0;font-family:system-ui,sans-serif;background:#F7FAF9;display:flex;align-items:center;
justify-content:center;min-height:100vh}.box{background:#fff;border:1px solid #DCE9E6;border-radius:18px;
padding:38px 34px;width:min(400px,92vw);box-shadow:0 14px 40px #0b1f1c14}
h1{font-size:21px;color:#0B1F1C;margin:12px 0 4px}p{color:#5B7470;font-size:13.5px;margin:0 0 18px}
label{font-size:12.5px;color:#0F766E;font-weight:700;display:block;margin:0 0 6px}
input{width:100%;padding:12px 14px;border:1px solid #DCE9E6;border-radius:10px;font-size:15px;margin-bottom:14px;box-sizing:border-box}
button{width:100%;padding:12px;border:0;border-radius:10px;background:linear-gradient(135deg,#0D9488,#0F766E);
color:#fff;font-size:15px;font-weight:600;cursor:pointer}.err{color:#B91C1C;font-size:13px;margin-bottom:12px}
.divider{display:flex;align-items:center;gap:10px;color:#8AA6A0;font-size:11.5px;margin:16px 0 12px}
.divider::before,.divider::after{content:"";height:1px;background:#DCE9E6;flex:1}
.note{background:#F0FDFA;border:1px solid #CCFBF1;border-radius:10px;padding:10px 12px;font-size:12.5px;color:#134E4A;margin-bottom:16px}
.te{font-size:12px;color:#62807A;margin-top:10px}
.ft{margin-top:20px;font-size:11.5px;color:#62807a;text-align:center}.ft a{color:#0F766E;font-weight:600;text-decoration:none}</style></head>
<body><div class="box" style="text-align:center"><img src="/static/logo.png" alt="SeatSetu" style="max-width:200px">
<h1>Sign in</h1><p>Admissions · Accreditation · Careers — one login per person</p>
<!--ERR-->
<form method="post" action="/login">
<label>👤 Your username (given by your Owner)</label>
<input type="text" name="username" placeholder="e.g. counselor, lakshmi, director…" autocomplete="username" style="margin-bottom:10px">
<label>🔑 Your password</label>
<input type="password" name="password" placeholder="Your password" required autofocus>
<button>Login to dashboard</button>
</form>
<div class="divider">OWNER / ADMIN?</div>
<div class="note"><b>Owner with the Admin Key:</b> leave the username <b>empty</b> and enter your Admin Key as the password.<br>
<span style="color:#0F766E">మీరు ఓనర్ నయితే — యూజర్‌నేమ్ ఖాళీగా వదిలేసి, అడ్మిన్ కీ టైప్ చేయండి.</span></div>
<div class="te">యూజర్‌నేమ్ / పాస్‌వర్డ్ మర్చిపోయారా? మీ ఓనర్‌ను సంప్రదించండి — వారు కొత్తది ఇవ్వగలరు.</div>
<div class="ft">A product by <a href="https://poojasoftsolutions.com">Pooja Soft Solutions</a> · Ongole, AP<br>📞 92471 05525 · 💬 WhatsApp 75691 92211</div></div></body></html>"""


# ── Report generators (auth via admin_gate) ──
@app.get("/api/leads/{lead_id}/timeline")
def lead_timeline(lead_id: int, db: Session = Depends(get_db)):
    l = db.query(Lead).get(lead_id)
    if not l:
        raise HTTPException(404, "Lead not found")
    msgs = []
    for cv in db.query(Conversation).filter_by(lead_id=l.id).all():
        for m in (db.query(Message).filter_by(conversation_id=cv.id)
                   .order_by(Message.id).limit(60).all()):
            msgs.append({"at": str(m.created_at)[:16], "who": m.role, "text": m.text})
    fus = [{"at": str(f.sent_at)[:16], "who": "followup", "text": f"{f.template} via {f.channel} ({f.mode})"}
           for f in db.query(FollowUpLog).filter_by(lead_id=l.id).all()]
    tasks = [{"at": str(t.created_at)[:16], "who": "task", "text": f"[{t.kind}] {t.note} "
              + ("✓ done" if t.done else "• open")}
             for t in db.query(CounselorTask).filter_by(lead_id=l.id).all()]
    timeline = sorted(msgs + fus + tasks, key=lambda x: x["at"])
    return {"lead": dict(id=l.id, name=l.name, phone=l.phone, town=l.town, stage=l.stage,
                         source=l.source, branch=l.branch_interest, rank=l.rank_or_marks,
                         score=l.score, consent=l.consent, assigned_to=l.assigned_to,
                         created=str(l.created_at)[:16]),
            "timeline": timeline,
            "ref": dict(username=l.ref_username or "", amt=l.commission_amt or 0,
                        paid=bool(l.commission_paid))}


@app.post("/api/leads/{lead_id}/assign")
def assign_lead(lead_id: int, body: dict, db: Session = Depends(get_db)):
    su = db.query(StaffUser).filter_by(username=str(body.get("username", "")).lower(), active=True).first()
    if not su:
        raise HTTPException(404, "Staff user not found")
    l = db.query(Lead).get(lead_id)
    if not l:
        raise HTTPException(404, "Lead not found")
    l.assigned_to = su.id
    guardrails.log(l.college_id, "staff", "lead.assigned", {"lead": l.id, "to": su.username}, db)
    db.commit()
    return dict(ok=True, assigned=su.username)


@app.post("/api/widget/{college_id}/feedback")
def widget_feedback(college_id: int, body: dict, db: Session = Depends(get_db)):
    C(college_id, db)
    from .db import Feedback
    db.add(Feedback(college_id=college_id, conversation_id=body.get("conversation_id"),
                    helpful=bool(body.get("helpful", True))))
    db.commit()
    return dict(ok=True)


@app.get("/api/colleges/{college_id}/analytics")
def analytics(college_id: int, db: Session = Depends(get_db)):
    from datetime import timedelta
    col = C(college_id, db)
    rep = reports.admissions(db, col)
    spend = sum((col.ad_spend or {}).values()) if isinstance(col.ad_spend, dict) else 0
    joined = rep["funnel"].get("joined", 0)
    leads = rep["total_leads"]
    trend = []
    today = datetime.utcnow().date()
    for i in range(6, -1, -1):
        d0 = today - timedelta(days=i)
        n = (db.query(Lead).filter(Lead.college_id == col.id,
                                   Lead.created_at >= datetime.combine(d0, datetime.min.time()),
                                   Lead.created_at < datetime.combine(d0 + timedelta(days=1), datetime.min.time()))
               .count())
        trend.append({"day": d0.strftime("%a"), "n": n})
    return {"spend": spend, "leads": leads, "joined": joined,
            "cpl": round(spend / leads) if leads and spend else None,
            "cpj": round(spend / joined) if joined and spend else None,
            "conversion_pct": round(100 * joined / leads, 1) if leads else 0,
            "trend": trend, "per_source_spend": col.ad_spend or {}}


@app.get("/api/colleges/{college_id}/digest")
def digest(college_id: int, db: Session = Depends(get_db)):
    col = C(college_id, db)
    return reports.weekly_digest(db, col)


@app.get("/api/colleges/{college_id}/settings")
def get_settings(college_id: int, request: Request, db: Session = Depends(get_db)):
    a = authz.actor(request, db)
    if not a or a["role"] not in authz.SETTINGS_ROLES:
        raise HTTPException(403, "Principal or admin role required")
    col = C(college_id, db)
    return dict(name=col.name, short=col.short, city=col.city, phone=col.phone,
                ad_spend=col.ad_spend or {},
                env=dict(whatsapp_live=bool(SETTINGS.whatsapp_token and SETTINGS.whatsapp_phone_id),
                         llm_brain=bool(SETTINGS.gemini_api_key or SETTINGS.github_token
                                        or SETTINGS.openai_api_key or SETTINGS.anthropic_api_key),
                         meta_signature=bool(SETTINGS.meta_app_secret)))


@app.put("/api/colleges/{college_id}/settings")
def put_settings(college_id: int, body: dict, request: Request, db: Session = Depends(get_db)):
    a = authz.actor(request, db)
    if not a or a["role"] not in authz.SETTINGS_ROLES:
        raise HTTPException(403, "Principal or admin role required")
    col = C(college_id, db)
    if isinstance(body.get("ad_spend"), dict):
        clean = {}
        for k, v in body["ad_spend"].items():
            try:
                if float(v) >= 0:
                    clean[str(k)[:30]] = int(float(v))
            except Exception:
                pass
        col.ad_spend = clean
        flag_modified(col, "ad_spend")
        guardrails.log(col.id, "staff", "settings.ad_spend", clean, db)
        db.commit()
    return dict(ok=True)


@app.get("/api/colleges/{college_id}/backup.zip")
def backup_zip(college_id: int, request: Request, db: Session = Depends(get_db)):
    a = authz.actor(request, db)
    if not a or a["role"] not in authz.SETTINGS_ROLES:
        raise HTTPException(403, "Principal or admin role required")
    import csv as _csv
    import io as _io
    import zipfile as _zf
    col = C(college_id, db)
    buf = _io.BytesIO()
    with _zf.ZipFile(buf, "w", _zf.ZIP_DEFLATED) as z:
        z.writestr("leads.csv", reports.leads_csv(db, col))
        z.writestr("careers.csv", reports.careers_csv(db, col))
        rows = [["id", "conversation", "role", "text", "at"]]
        for cv in db.query(Conversation).filter_by(college_id=col.id).all():
            for m in db.query(Message).filter_by(conversation_id=cv.id).all():
                rows.append([m.id, cv.id, m.role, (m.text or "")[:500], str(m.created_at)[:16]])
        out = _io.StringIO(); _csv.writer(out).writerows(rows)
        z.writestr("conversations.csv", out.getvalue())
        from .db import Hostel, KeyDate, PlacementStat, TransportRoute
        ck = {"college": {"name": col.name, "about": col.about, "admission_process": col.admission_process},
              "courses": [{"name": c.name, "code": c.code, "intake": c.intake,
                           "convener_fee": c.convener_fee, "mgmt_fee": c.mgmt_fee,
                           "cutoff_note": c.cutoff_note} for c in col.courses],
              "hostels": [{"for_whom": h.for_whom, "ac": h.ac, "fee": h.fee_per_year}
                          for h in db.query(Hostel).filter_by(college_id=col.id).all()],
              "buses": [{"from": r.from_place, "fee": r.fee_per_year}
                        for r in db.query(TransportRoute).filter_by(college_id=col.id).all()],
              "placements": [{"year": p.year, "placed_pct": p.placed_pct, "top_lpa": p.top_lpa}
                             for p in db.query(PlacementStat).filter_by(college_id=col.id).all()],
              "dates": [{"label": d.label, "when": d.when_note}
                        for d in db.query(KeyDate).filter_by(college_id=col.id).all()]}
        irows = [["id", "student", "roll", "branch", "role", "score", "mode", "at"]]
        for m in (db.query(MockInterview).filter_by(college_id=col.id)
                   .order_by(MockInterview.id.desc()).limit(2000).all()):
            irows.append([m.id, m.student_name, m.roll, m.branch, m.role,
                          m.overall, "self-practice" if m.self_practice else "office",
                          str(m.created_at)[:16]])
        out = _io.StringIO(); _csv.writer(out).writerows(irows)
        z.writestr("mock_interviews.csv", out.getvalue())
        import json as _json
        z.writestr("knowledge_pack.json", _json.dumps(ck, indent=1))
        z.writestr("README.txt", "SeatSetu data backup — your data is yours.\n"
                                 "Generated by SeatSetu (Pooja Soft Solutions).\n")
    buf.seek(0)
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f"attachment; filename=seatsetu_backup_col{college_id}.zip"})


@app.get("/api/colleges/{college_id}/next-actions")
def next_actions(college_id: int, db: Session = Depends(get_db)):
    col = C(college_id, db)
    return actions.next_actions(db, col)


@app.post("/api/colleges/{college_id}/coach")
def reply_coach(college_id: int, body: dict, db: Session = Depends(get_db)):
    col = C(college_id, db)
    return actions.coach_reply(db, col, body.get("conversation_id"),
                               str(body.get("text", "") or ""), str(body.get("stage", "new") or "new"))


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
            su.last_login = utcnow()
            db.commit()
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
def require_owner(request: Request, db: Session = Depends(get_db)) -> dict:
    """Staff accounts are allocated by the Owner (Admin Key) only."""
    a = authz.actor(request, db)
    if not a or a["role"] != "admin":
        raise HTTPException(403, "Only the Admin Key owner can manage staff accounts")
    return a


class StaffUserIn(BaseModel):
    username: str
    password: str
    role: str = "counselor"
    name: str = ""
    phone: str = ""
    tabs: list[str] | None = None
    college_id: int | None = None


def _su_dict(u: StaffUser) -> dict:
    import json as _json
    try:
        tabs = _json.loads(u.tabs_json) if u.tabs_json else None
    except Exception:
        tabs = None
    return dict(id=u.id, username=u.username, role=u.role, name=u.name,
                phone=u.phone or "", tabs=tabs, active=u.active,
                must_change=u.must_change, college_id=u.college_id,
                last_login=str(u.last_login)[:16] if u.last_login else None)


@app.get("/api/staff-users")
def staff_users(request: Request, db: Session = Depends(get_db)):
    if not authz.actor(request, db):
        raise HTTPException(401, "Not signed in")
    return [_su_dict(u) for u in db.query(StaffUser).order_by(StaffUser.id).all()]


@app.post("/api/staff-users")
def add_staff_user(body: StaffUserIn, request: Request, db: Session = Depends(get_db)):
    a_hint = require_owner(request, db)
    if body.role not in authz.ROLES:
        raise HTTPException(422, "Unknown role")
    if len(body.password) < 8:
        raise HTTPException(422, "Password must be at least 8 characters")
    if db.query(StaffUser).filter_by(username=body.username.lower()).first():
        raise HTTPException(422, "Username already exists")
    import json as _json
    tabs_json = None
    if body.tabs is not None:
        clean = [t for t in body.tabs if t in authz.ALL_TABS]
        tabs_json = _json.dumps(clean) if clean else None
    su = StaffUser(username=body.username.lower(), pw_hash=authz.hash_pw(body.password),
                   role=body.role, name=body.name, phone=body.phone[:20],
                   tabs_json=tabs_json,
                   college_id=body.college_id or a_hint["college_id"])
    db.add(su)
    guardrails.log(0, "staff", "staff_user.created", {"username": su.username, "role": su.role}, db)
    db.commit()
    return dict(ok=True, id=su.id)


@app.put("/api/staff-users/{uid}")
def update_staff_user(uid: int, body: dict, request: Request, db: Session = Depends(get_db)):
    require_owner(request, db)
    su = db.query(StaffUser).get(uid)
    if not su:
        raise HTTPException(404, "User not found")
    import json as _json
    if "role" in body:
        if body["role"] not in authz.ROLES:
            raise HTTPException(422, "Unknown role")
        su.role = body["role"]
    if "name" in body:
        su.name = str(body["name"])[:120]
    if "phone" in body:
        su.phone = str(body["phone"])[:20]
    if "active" in body:
        su.active = bool(body["active"])
    if "tabs" in body:
        if body["tabs"] is None:
            su.tabs_json = None  # back to role preset
        else:
            clean = [t for t in body["tabs"] if t in authz.ALL_TABS]
            su.tabs_json = _json.dumps(clean) if clean else None
    guardrails.log(su.college_id or 0, "staff", "staff_user.updated",
                   {"username": su.username, "active": su.active,
                    "role": su.role, "tabs": su.tabs_json}, db)
    db.commit()
    return dict(ok=True)


@app.post("/api/staff-users/{uid}/password")
def change_password(uid: int, body: dict, request: Request, db: Session = Depends(get_db)):
    a = authz.actor(request, db)
    if not a:
        raise HTTPException(401, "Not signed in")
    if a["role"] != "admin" and a.get("id") != uid:
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
    ref_username: str | None = None
    commission_amt: int | None = None


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
def onboard(body: CollegeIn, db: Session = Depends(get_db), _mgr: dict = Depends(require_owner)):
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
    return dict(name=c.name, short=c.short, color=c.brand_color, phone=c.phone,
                courses=[dict(code=x.code, name=x.name) for x in c.courses])


@app.post("/api/widget/{college_id}/book_visit")
def widget_book_visit(college_id: int, body: dict, db: Session = Depends(get_db)):
    col = C(college_id, db)
    return actions.book_visit(db, col, str(body.get("name", "")), str(body.get("phone", "")),
                              str(body.get("date", "")), str(body.get("branch", "") or ""),
                              str(body.get("town", "") or ""), bool(body.get("consent")))


@app.post("/api/widget/{college_id}/brochure_lead")
def widget_brochure_lead(college_id: int, body: dict, db: Session = Depends(get_db)):
    col = C(college_id, db)
    return actions.brochure_lead(db, col, str(body.get("name", "")), str(body.get("phone", "")))


@app.get("/brochure/{college_id}.pdf")
def college_brochure(college_id: int, db: Session = Depends(get_db)):
    col = C(college_id, db)
    pdf = brochure.generate(col, db)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f"inline; filename={col.short or 'college'}_brochure.pdf"})


def _pass_actor(request: Request, db: Session):
    """Office-ish roles can issue practice codes."""
    a = authz.actor(request, db)
    if not a or a["role"] not in ("admin", "principal", "director", "manager", "office", "placement"):
        raise HTTPException(403, "Staff role required to manage practice passes")
    return a


@app.get("/api/colleges/{college_id}/practice-passes")
def practice_list(college_id: int, request: Request, db: Session = Depends(get_db)):
    _pass_actor(request, db)
    C(college_id, db)
    rows = (db.query(PracticePass).filter_by(college_id=college_id)
              .order_by(PracticePass.id.desc()).all())
    return [dict(id=r.id, student_name=r.student_name, roll=r.roll, branch=r.branch,
                 code=r.code, active=r.active,
                 last_used=str(r.last_used)[:16] if r.last_used else None) for r in rows]


@app.post("/api/colleges/{college_id}/practice-passes")
def practice_create(college_id: int, body: dict, request: Request, db: Session = Depends(get_db)):
    a = _pass_actor(request, db)
    col = C(college_id, db)
    name = str(body.get("student_name") or "").strip()[:120]
    if not name:
        raise HTTPException(422, "Student name required")
    import secrets as _sc
    code = "".join(_sc.choice("ABCDEFGHJKMNPQRSTUVWXYZ23456789") for _ in range(8))
    r = PracticePass(college_id=col.id, student_name=name,
                     roll=str(body.get("roll") or "")[:40],
                     branch=str(body.get("branch") or "CSE")[:40], code=code)
    db.add(r)
    guardrails.log(col.id, "staff", "practice.pass_created", {"student": name}, db)
    db.commit()
    return dict(ok=True, id=r.id, code=code)


@app.put("/api/colleges/{college_id}/practice-passes/{pid}")
def practice_toggle(college_id: int, pid: int, request: Request, db: Session = Depends(get_db)):
    _pass_actor(request, db)
    r = db.query(PracticePass).get(pid)
    if r and r.college_id == college_id:
        r.active = not r.active
        db.commit()
    return dict(ok=True)


# ── student self-practice (code-gated, public) ──
def _prac_actor(request: Request, db: Session):
    import base64 as _b64
    tok = request.cookies.get("ss_prac", "")
    if not tok:
        raise HTTPException(401, "Enter your practice code first")
    import hmac as _hm2
    try:
        b64, sig = tok.split(".", 1)
        payload = _b64.urlsafe_b64decode(b64.encode()).decode()
        if not _hm2.compare_digest(sig, authz._sig(payload)):
            raise HTTPException(401, "Session expired — enter your code again")
        kind, pid, cid = payload.split("|")
        assert kind == "practice"
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(401, "Session expired — enter your code again")
    r = db.query(PracticePass).get(int(pid))
    if not r or not r.active or r.college_id != int(cid):
        raise HTTPException(401, "This practice code was deactivated — ask the office")
    return r


@app.post("/api/practice/login")
def practice_login(body: dict, db: Session = Depends(get_db)):
    code = str(body.get("code") or "").strip().upper().replace(" ", "")
    r = db.query(PracticePass).filter_by(code=code, active=True).first()
    if not r:
        raise HTTPException(403, "Wrong or expired code — ask the office for your Practice Pass")
    import base64 as _b64, hmac as _hmac
    payload = f"practice|{r.id}|{r.college_id}"
    tok = _b64.urlsafe_b64encode(payload.encode()).decode() + "." + authz._sig(payload)
    r.last_used = utcnow()
    db.commit()
    resp = JSONResponse(dict(ok=True, name=r.student_name, college=r.college_id))
    resp.set_cookie("ss_prac", tok, httponly=True, samesite="lax", max_age=90 * 24 * 3600)
    return resp


@app.get("/api/practice/me")
def practice_me(request: Request, db: Session = Depends(get_db)):
    r = _prac_actor(request, db)
    return dict(name=r.student_name, roll=r.roll, branch=r.branch)


@app.get("/api/practice/history")
def practice_history(request: Request, db: Session = Depends(get_db)):
    r = _prac_actor(request, db)
    rows = (db.query(MockInterview).filter_by(pass_id=r.id)
              .order_by(MockInterview.id.desc()).limit(20).all())
    return [dict(id=m.id, at=str(m.created_at)[:16], branch=m.branch,
                 overall=m.overall, strict=bool(getattr(m, "self_practice", 0))) for m in rows]


@app.post("/api/practice/start")
def practice_start(body: dict, request: Request, db: Session = Depends(get_db)):
    r = _prac_actor(request, db)
    qs = careers.build_interview(str(body.get("branch") or r.branch), str(body.get("role") or "Software / IT"))
    strict = bool(body.get("strict"))
    for q in qs:
        q["strict"] = strict
    m = MockInterview(college_id=r.college_id, student_name=r.student_name,
                      roll=r.roll, branch=str(body.get("branch") or r.branch),
                      role=str(body.get("role") or "Software / IT"),
                      questions=qs, created_at=utcnow(),
                      self_practice=1, pass_id=r.id)
    db.add(m)
    guardrails.log(r.college_id, "ai", "practice.started", {"student": r.student_name}, db)
    db.commit()
    return dict(id=m.id, questions=[{k: q[k] for k in ("no", "type", "q")} for q in qs])


@app.post("/api/practice/{mid}/answer")
def practice_answer(mid: int, body: dict, request: Request, db: Session = Depends(get_db)):
    r = _prac_actor(request, db)
    m = db.query(MockInterview).get(mid)
    if not m or m.pass_id != r.id:
        raise HTTPException(404, "Interview not found")
    no_raw = str(body.get("no", "1"))
    text = (body.get("text") or "").strip()
    score, tips, qitem = None, "", None
    for q in m.questions:
        if str(q["no"]) == no_raw:
            score, tips = careers.score_answer(text, q)
            q["answer"], q["score"], q["tips"] = text[:2000], score, tips
            qitem = q
            break
    followup = None
    if qitem is not None and score is not None and score < 3.0 and not no_raw.endswith("b") \
            and not any(str(x["no"]) == f"{no_raw}b" for x in m.questions):
        followup = careers.make_probe(int(no_raw) if no_raw.isdigit() else 1, text, score, qitem)
        m.questions.append(dict(followup))
    flag_modified(m, "questions")
    db.commit()
    if followup:
        followup = {k: followup[k] for k in ("no", "type", "q", "tip")}
    return dict(score=score, tips=tips, followup=followup)


@app.post("/api/practice/{mid}/finish")
def practice_finish(mid: int, request: Request, db: Session = Depends(get_db)):
    r = _prac_actor(request, db)
    m = db.query(MockInterview).get(mid)
    if not m or m.pass_id != r.id:
        raise HTTPException(404, "Interview not found")
    done = [q["score"] for q in m.questions if q.get("score") is not None]
    m.overall = round(sum(done) / len(done), 1) if done else 0
    m.status = "done"
    guardrails.log(m.college_id, "ai", "practice.finished",
                   {"student": r.student_name, "overall": m.overall}, db)
    db.commit()
    return dict(ok=True, overall=m.overall)


@app.get("/api/practice/{mid}/report")
def practice_report(mid: int, request: Request, db: Session = Depends(get_db)):
    r = _prac_actor(request, db)
    m = db.query(MockInterview).get(mid)
    if not m or m.pass_id != r.id:
        raise HTTPException(404, "Interview not found")
    return dict(id=m.id, student=m.student_name, branch=m.branch, overall=m.overall,
                at=str(m.created_at)[:16],
                questions=[dict(no=q["no"], type=q["type"], q=q["q"], score=q.get("score"),
                                tips=q.get("tips")) for q in m.questions])


@app.get("/practice")
def practice_page():
    return FileResponse(BASE_DIR / "app" / "static" / "practice.html")


MONEY_ROLES = ("admin", "principal", "manager", "office")


@app.get("/api/colleges/{college_id}/commissions")
def commissions(college_id: int, request: Request, db: Session = Depends(get_db)):
    a = authz.actor(request, db)
    if not a:
        raise HTTPException(401, "Sign in required")
    C(college_id, db)
    leads = (db.query(Lead).filter(Lead.college_id == college_id,
                                   Lead.ref_username != "").all())
    rows, summ = [], {}
    for l in leads:
        due = (l.commission_amt or 0) if (l.stage == "joined" and not l.commission_paid) else 0
        paid = (l.commission_amt or 0) if l.commission_paid else 0
        u = l.ref_username
        t = summ.setdefault(u, dict(refs=0, joined=0, due=0, paid=0))
        t["refs"] += 1
        t["joined"] += 1 if l.stage == "joined" else 0
        t["due"] += due
        t["paid"] += paid
        rows.append(dict(id=l.id, name=l.name or l.phone, stage=l.stage, username=u,
                         amt=l.commission_amt or 0, paid=bool(l.commission_paid)))
    order = sorted(summ.items(), key=lambda kv: -(kv[1]["due"] + kv[1]["paid"]))
    return dict(summaries=[dict(username=k, **v) for k, v in order], rows=rows)


@app.post("/api/colleges/{college_id}/commissions/mark-paid")
def commissions_mark_paid(college_id: int, body: dict, request: Request,
                          db: Session = Depends(get_db)):
    a = authz.actor(request, db)
    if not a or a["role"] not in MONEY_ROLES:
        raise HTTPException(403, "Owner/Principal/Management/Admin Office only")
    col = C(college_id, db)
    username = str(body.get("username") or "").strip()
    targets = (db.query(Lead).filter(Lead.college_id == college_id,
                                     Lead.ref_username == username,
                                     Lead.stage == "joined",
                                     Lead.commission_paid == False).all())   # noqa: E712
    if not targets:
        raise HTTPException(404, "Nothing pending for " + username)
    for l in targets:
        l.commission_paid = True
        l.commission_paid_at = utcnow()
    guardrails.log(col.id, "staff", "commissions.mark_paid",
                   {"by": a["username"], "username": username, "count": len(targets)}, db)
    db.commit()
    return dict(ok=True, cleared=len(targets))


@app.post("/api/colleges/{college_id}/leads/import")
def leads_import(college_id: int, body: dict, request: Request, db: Session = Depends(get_db)):
    """CSV paste/upload import. Header row required. Consent=False (DPDP): imported
    parents are NEVER auto-messaged until they consent. Duplicates (same phone) skipped."""
    a = authz.actor(request, db)
    if not a:
        raise HTTPException(401, "Sign in required")
    col = C(college_id, db)
    import csv as _csv, io as _io
    raw = str(body.get("csv") or "").strip()
    if not raw:
        raise HTTPException(422, "Paste CSV text or choose a file")
    reader = _csv.reader(_io.StringIO(raw))
    rows = [r for r in reader if any((c or "").strip() for c in r)]
    if len(rows) < 2:
        raise HTTPException(422, "Need a header row + at least one data row")
    hdr = [(h or "").strip().lower() for h in rows[0]]
    alias = {"name": "name", "parent": "name", "parent name": "name", "student": "name",
             "phone": "phone", "mobile": "phone", "phone number": "phone", "whatsapp": "phone",
             "town": "town", "city": "town", "village": "town",
             "branch": "branch", "course": "branch", "branch interest": "branch",
             "source": "source", "campaign": "campaign", "note": "campaign",
             "rank": "rank", "marks": "rank", "rank/marks": "rank"}
    cols = {}
    for i, h in enumerate(hdr):
        key = alias.get(h)
        if key and key not in cols:
            cols[key] = i
    if "phone" not in cols and "name" not in cols:
        raise HTTPException(422, "Header must include at least a name or phone column "
                                 "(use: name, phone, town, branch, source, campaign, rank)")
    existing = {l.phone for l in db.query(Lead).filter_by(college_id=col.id).all() if l.phone}
    imported, skipped = 0, 0
    for r in rows[1:]:
        get = lambda k: (r[cols[k]].strip() if cols.get(k) is not None and len(r) > cols[k] else "")  # noqa: E731
        phone = "".join(ch for ch in get("phone") if ch.isdigit())[-10:]
        name = get("name")
        if not name and not phone:
            continue
        if phone and phone in existing:
            skipped += 1
            continue
        lead = Lead(college_id=col.id, name=name, phone=phone, town=get("town"),
                    branch_interest=get("branch")[:60],
                    source="import", campaign=(get("campaign") or "CSV import")[:120],
                    rank_or_marks=get("rank")[:40], consent=False)
        counselor.rescore(lead)
        db.add(lead)
        existing.add(phone)
        imported += 1
    guardrails.log(col.id, "staff", "leads.imported",
                   {"by": a["username"], "imported": imported, "skipped": skipped}, db)
    db.commit()
    return dict(ok=True, imported=imported, skipped=skipped,
                note="Imported leads have NO consent yet (DPDP) — they are never auto-messaged until the parent opts in.")


@app.post("/api/colleges/{college_id}/ckp/import")
def ckp_import(college_id: int, body: dict, request: Request, db: Session = Depends(get_db)):
    """Restore a Knowledge Pack from backup-shaped JSON (knowledge_pack.json)."""
    a = authz.actor(request, db)
    if not a or a["role"] not in ("admin", "principal"):
        raise HTTPException(403, "Owner or Principal only")
    col = C(college_id, db)
    from .db import Hostel, KeyDate, PlacementStat, TransportRoute
    pack = body.get("pack") or {}
    if not isinstance(pack, dict) or not (pack.get("courses") or pack.get("placements")):
        raise HTTPException(422, "This does not look like a knowledge_pack.json (need courses or placements)")
    meta = pack.get("college") or {}
    if meta.get("about"):
        col.about = str(meta["about"])[:4000]
    if meta.get("admission_process"):
        col.admission_process = str(meta["admission_process"])[:4000]
    for model, key, fields in (
        (Hostel, "hostels", ("for_whom", "ac", "fee_per_year")),
        (TransportRoute, "buses", ("from_place", "fee_per_year")),
        (PlacementStat, "placements", ("year", "placed_pct", "top_lpa")),
        (KeyDate, "dates", ("label", "when_note")),
    ):
        db.query(model).filter_by(college_id=col.id).delete()
        for item in pack.get(key, []):
            db.add(model(college_id=col.id, **{f: item.get(f) for f in fields}))
    db.query(Course).filter_by(college_id=col.id).delete()
    for c in pack.get("courses", []):
        db.add(Course(college_id=col.id, name=str(c.get("name") or "")[:120],
                      code=str(c.get("code") or "")[:20], intake=int(c.get("intake") or 0),
                      convener_fee=int(c.get("convener_fee") or 0),
                      mgmt_fee=int(c.get("mgmt_fee") or 0),
                      cutoff_note=str(c.get("cutoff_note") or "")[:300]))
    guardrails.log(col.id, "staff", "ckp.imported", {"by": a["username"]}, db)
    db.commit()
    n = db.query(Course).filter_by(college_id=col.id).count()
    return dict(ok=True, courses=n,
                note="Knowledge Pack replaced. Review it in the Knowledge tab.")


BROADCAST_ROLES = ("admin", "principal", "manager", "office")


def _broadcast_actor(request: Request, db: Session):
    a = authz.actor(request, db)
    if not a or a["role"] not in BROADCAST_ROLES:
        raise HTTPException(403, "Owner/Principal/Management/Admin Office only")
    return a


@app.get("/api/colleges/{college_id}/broadcast/audience")
def broadcast_audience(college_id: int, request: Request, db: Session = Depends(get_db)):
    _broadcast_actor(request, db)
    C(college_id, db)
    n = (db.query(Lead)
           .filter(Lead.college_id == college_id, Lead.consent == True,      # noqa: E712
                   Lead.stage.notin_(["joined", "lost"]), Lead.phone != "")
           .count())
    return dict(count=n)


@app.post("/api/colleges/{college_id}/broadcast")
def broadcast(college_id: int, body: dict, request: Request, db: Session = Depends(get_db)):
    a = _broadcast_actor(request, db)
    col = C(college_id, db)
    text = str(body.get("text") or "").strip()
    if len(text) < 10:
        raise HTTPException(422, "Write a real message (10+ characters)")
    if len(text) > 600:
        raise HTTPException(422, "Keep broadcasts under 600 characters")
    targets = (db.query(Lead)
                 .filter(Lead.college_id == col.id, Lead.consent == True,   # noqa: E712
                         Lead.stage.notin_(["joined", "lost"]), Lead.phone != "")
                 .all())
    sent, mode = 0, "mock"
    for lead in targets:
        try:
            guardrails.consent_firewall(col.id, lead, db)
        except guardrails.GuardrailViolation:
            continue
        res = connectors.whatsapp_send(col.id, lead.phone, text)
        mode = res["mode"]
        if res.get("sent") or res["mode"] == "mock":
            sent += 1
            db.add(FollowUpLog(college_id=col.id, lead_id=lead.id, template="broadcast",
                               channel="whatsapp", text=text, mode=mode, sent_at=utcnow()))
    guardrails.log(col.id, "staff", "broadcast.sent",
                   {"by": a["username"], "count": sent, "mode": mode}, db)
    db.commit()
    return dict(ok=True, sent=sent, mode=mode,
                note=("Sent via WhatsApp Cloud API" if mode == "live"
                      else "MOCK mode — logged, not sent. Add WHATSAPP_TOKEN + WHATSAPP_PHONE_ID "
                           "in Vercel env (or ask Pooja Soft Solutions) to go live."))


@app.post("/api/settings/test-whatsapp")
def test_whatsapp(body: dict, request: Request, db: Session = Depends(get_db)):
    a = authz.actor(request, db)
    if not a or a["role"] not in authz.SETTINGS_ROLES:
        raise HTTPException(403, "Owner/Principal/Director/Management only")
    phone = str(body.get("phone") or "").strip()
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) < 10:
        raise HTTPException(422, "Enter a valid mobile number")
    text = str(body.get("text") or "Hello from SeatSetu — WhatsApp test message ✅")
    res = connectors.whatsapp_send(0, digits[-10:], text[:600])
    guardrails.log(0, "staff", "settings.whatsapp_test", {"mode": res["mode"], "sent": res.get("sent")}, db)
    db.commit()
    return res


@app.get("/api/colleges/{college_id}/competitors")
def competitors_list(college_id: int, db: Session = Depends(get_db)):
    C(college_id, db)
    rows = db.query(Competitor).filter_by(college_id=college_id).order_by(Competitor.id).all()
    return [dict(id=r.id, name=r.name, town=r.town, distance_km=r.distance_km,
                 annual_fee=r.annual_fee, placements_pct=r.placements_pct,
                 closing_rank_note=r.closing_rank_note, their_strength=r.their_strength,
                 our_edge=r.our_edge, source_note=r.source_note) for r in rows]


@app.post("/api/colleges/{college_id}/competitors")
def competitors_add(college_id: int, body: dict, request: Request, db: Session = Depends(get_db)):
    a = authz.actor(request, db)
    if not a or a["role"] not in authz.SETTINGS_ROLES:
        raise HTTPException(403, "Owner/Principal/Director/Management only")
    col = C(college_id, db)
    name = str(body.get("name") or "").strip()[:140]
    if not name:
        raise HTTPException(422, "Name required")
    r = Competitor(college_id=col.id, name=name,
                   town=str(body.get("town") or "")[:80],
                   distance_km=str(body.get("distance_km") or "")[:20],
                   annual_fee=str(body.get("annual_fee") or "")[:30],
                   placements_pct=str(body.get("placements_pct") or "")[:20],
                   closing_rank_note=str(body.get("closing_rank_note") or "")[:120],
                   their_strength=str(body.get("their_strength") or "")[:200],
                   our_edge=str(body.get("our_edge") or "")[:200],
                   source_note=str(body.get("source_note") or "AICTE approvals / public disclosures")[:200])
    db.add(r)
    guardrails.log(col.id, "staff", "comparison.added", {"name": name}, db)
    db.commit()
    return dict(ok=True, id=r.id)


@app.delete("/api/colleges/{college_id}/competitors/{rid}")
def competitors_del(college_id: int, rid: int, request: Request, db: Session = Depends(get_db)):
    a = authz.actor(request, db)
    if not a or a["role"] not in authz.SETTINGS_ROLES:
        raise HTTPException(403, "Owner/Principal/Director/Management only")
    r = db.query(Competitor).get(rid)
    if r and r.college_id == college_id:
        db.delete(r)
        guardrails.log(college_id, "staff", "comparison.removed", {"id": rid}, db)
        db.commit()
    return dict(ok=True)


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
    if body.ref_username is not None:
        l.ref_username = body.ref_username.strip()[:60]
    if body.commission_amt is not None:
        l.commission_amt = max(0, int(body.commission_amt))
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
def killswitch(college_id: int, state: str, db: Session = Depends(get_db), _mgr: dict = Depends(require_owner)):
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
    strict: bool = False


@app.post("/api/colleges/{college_id}/careers/start")
def careers_start(college_id: int, body: InterviewIn, db: Session = Depends(get_db)):
    C(college_id, db)
    qs = careers.build_interview(body.branch, body.role)
    for q in qs:
        q["strict"] = bool(body.strict)
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
    no_raw = str(body.get("no", "1"))
    text = (body.get("text") or "").strip()
    score, tips = None, ""
    qitem = None
    for q in m.questions:
        if str(q["no"]) == no_raw:
            score, tips = careers.score_answer(text, q)
            q["answer"], q["score"], q["tips"] = text[:2000], score, tips
            qitem = q
            break
    followup = None
    if qitem is not None and score is not None and score < 3.0 and not no_raw.endswith("b") \
            and not any(str(x["no"]) == f"{no_raw}b" for x in m.questions):
        followup = careers.make_probe(int(no_raw) if no_raw.isdigit() else 1, text, score, qitem)
        m.questions.append(dict(followup))
    flag_modified(m, "questions")     # force JSON mutation to persist
    guardrails.log(m.college_id, "ai", "careers.answer_scored",
                   {"interview": m.id, "q": no_raw, "score": score,
                    "probe": bool(followup)}, db)
    db.commit()
    if followup:
        followup = {k: followup[k] for k in ("no", "type", "q", "tip")}
    return dict(score=score, tips=tips, followup=followup)


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
    return FileResponse(BASE_DIR / "docs" / "SeatSetu_User_Manual.pdf", media_type="application/pdf",
                        headers={"Content-Disposition": "inline; filename=SeatSetu_User_Manual.pdf"})


@app.get("/guide.pdf")
def guide_pdf():
    return FileResponse(BASE_DIR / "docs" / "SeatSetu_User_Manual.pdf",
                        media_type="application/pdf",
                        headers={"Content-Disposition": "inline; filename=SeatSetu_User_Manual.pdf"})


@app.get("/presentation")
def presentation_partner():
    return FileResponse(BASE_DIR / "docs" / "SeatSetu_Sales_Deck.pdf", media_type="application/pdf",
                        headers={"Content-Disposition": "inline; filename=SeatSetu_Sales_Deck.pdf"})


@app.get("/presentation.pdf")
def presentation_partner_pdf():
    return FileResponse(BASE_DIR / "docs" / "SeatSetu_Sales_Deck.pdf",
                        media_type="application/pdf",
                        headers={"Content-Disposition": "inline; filename=SeatSetu_Sales_Deck.pdf"})


@app.get("/presentation-college")
def presentation_college():
    return FileResponse(BASE_DIR / "docs" / "SeatSetu_Sales_Deck.pdf", media_type="application/pdf",
                        headers={"Content-Disposition": "inline; filename=SeatSetu_Sales_Deck.pdf"})


@app.get("/presentation-college.pdf")
def presentation_college_pdf():
    return FileResponse(BASE_DIR / "docs" / "SeatSetu_Sales_Deck.pdf",
                        media_type="application/pdf",
                        headers={"Content-Disposition": "inline; filename=SeatSetu_Sales_Deck.pdf"})


@app.get("/favicon.ico")
def favicon():
    return FileResponse(BASE_DIR / "app" / "static" / "favicon.png")


@app.get("/widget/{college_id}")
def widget(college_id: int):
    return FileResponse(BASE_DIR / "app" / "static" / "widget.html")


@app.get("/sell")
def sell_page():
    return FileResponse(BASE_DIR / "app" / "static" / "sell.html")


@app.get("/manifest.json")
def pwa_manifest():
    return FileResponse(BASE_DIR / "app" / "static" / "manifest.json", media_type="application/manifest+json")


@app.get("/sw.js")
def pwa_sw():
    return FileResponse(BASE_DIR / "app" / "static" / "sw.js", media_type="application/javascript")


app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")
