"""Database bootstrap + models. Multi-tenant: every row carries college_id.

SQLite for dev; Postgres (Neon/Vercel) in production — DATABASE_URL handles
both (postgres:// → postgresql+psycopg:// normalization). On Vercel the
bundle filesystem is read-only → SQLite falls back to /tmp (ephemeral)."""
import datetime as dt
import os

import os as _os

from sqlalchemy import (Boolean, Column, DateTime, Float, ForeignKey, Integer,
                        JSON, String, Text, create_engine)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

from .config import SETTINGS, DATA_DIR

url = SETTINGS.database_url
if url.startswith("sqlite:///data") and _os.getenv("VERCEL"):
    url = "sqlite:////tmp/seatsetu.db"  # read-only FS safety on Vercel
if url.startswith("postgres://"):
    url = "postgresql+psycopg://" + url[len("postgres://"):]
elif url.startswith("postgresql://"):
    url = "postgresql+psycopg://" + url[len("postgresql://"):]
if url.startswith("sqlite:////tmp"):
    pass
elif url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
    db_name = url.replace("sqlite:///", "")
    url = f"sqlite:///{DATA_DIR / db_name}" if "/" not in db_name else url
if os.environ.get("VERCEL") and url.startswith("sqlite:///"):
    url = "sqlite:////tmp/cgos.db"

engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


# ── College + Knowledge Pack (structured — exact numbers come from tables) ──
class College(Base):
    __tablename__ = "colleges"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    short = Column(String(40), default="")
    city = Column(String(80), default="")
    district = Column(String(80), default="")
    eapcet_code = Column(String(20), default="")
    website = Column(String(200), default="")
    phone = Column(String(30), default="")            # WhatsApp number shown to parents
    about = Column(Text, default="")
    location_note = Column(Text, default="")          # address + landmarks + distances
    admission_process = Column(Text, default="")      # steps + documents + token/booking rules
    brand_color = Column(String(20), default="#0d9488")
    ad_spend = Column(JSON, default=dict)   # {source: rupees spent this season}
    kill_switch = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)
    courses = relationship("Course", back_populates="college")


class Course(Base):
    __tablename__ = "courses"
    id = Column(Integer, primary_key=True)
    college_id = Column(Integer, ForeignKey("colleges.id"), index=True)
    name = Column(String(120))                        # "CSE — Computer Science & Engg"
    code = Column(String(30))                         # EAPCET branch code
    intake = Column(Integer, default=0)
    convener_fee = Column(Integer, default=0)         # ₹/year (AFRC Category A/B)
    mgmt_fee = Column(Integer, default=0)             # ₹/year (management quota)
    mgmt_note = Column(String(200), default="")       # "limited seats, token ₹10,000"
    cutoff_note = Column(String(200), default="")     # "2025 closing rank ≈ 58,000"
    highlights = Column(Text, default="")
    college = relationship("College", back_populates="courses")


class Hostel(Base):
    __tablename__ = "hostels"
    id = Column(Integer, primary_key=True)
    college_id = Column(Integer, ForeignKey("colleges.id"), index=True)
    for_whom = Column(String(20))                     # boys | girls
    ac = Column(Boolean, default=False)
    fee_per_year = Column(Integer, default=0)
    facilities = Column(Text, default="")


class TransportRoute(Base):
    __tablename__ = "transport_routes"
    id = Column(Integer, primary_key=True)
    college_id = Column(Integer, ForeignKey("colleges.id"), index=True)
    from_place = Column(String(80))
    distance_km = Column(Float, default=0)
    fee_per_year = Column(Integer, default=0)


class PlacementStat(Base):
    """Approved numbers ONLY — the guardrail layer cites this table."""
    __tablename__ = "placement_stats"
    id = Column(Integer, primary_key=True)
    college_id = Column(Integer, ForeignKey("colleges.id"), index=True)
    year = Column(String(20))
    placed_pct = Column(Float)                        # % of eligible students
    offers = Column(Integer, default=0)
    companies = Column(Integer, default=0)
    top_lpa = Column(Float, default=0)
    avg_lpa = Column(Float, default=0)
    note = Column(Text, default="")


class KeyDate(Base):
    __tablename__ = "key_dates"
    id = Column(Integer, primary_key=True)
    college_id = Column(Integer, ForeignKey("colleges.id"), index=True)
    label = Column(String(200))
    when_note = Column(String(200))


# ── Staff / Leads / Conversations ────────────────────────────────────────────
class Staff(Base):
    __tablename__ = "staff"
    id = Column(Integer, primary_key=True)
    college_id = Column(Integer, ForeignKey("colleges.id"), index=True)
    name = Column(String(120))
    role = Column(String(30), default="counselor")    # principal | counselor | iqac | admin
    phone = Column(String(20), default="")
    active = Column(Boolean, default=True)


class Lead(Base):
    __tablename__ = "leads"
    id = Column(Integer, primary_key=True)
    college_id = Column(Integer, ForeignKey("colleges.id"), index=True)
    name = Column(String(120), default="")
    phone = Column(String(20), default="")
    town = Column(String(80), default="")
    source = Column(String(30), default="website_chat")   # meta_ad|website_chat|walk_in|qr|missed_call|referral|import
    campaign = Column(String(120), default="")
    stage = Column(String(30), default="new")         # new|ai_engaged|contacted|interested|visit_booked|visited|applied|seat_booked|joined|lost
    lost_reason = Column(String(200), default="")
    branch_interest = Column(String(60), default="")
    rank_or_marks = Column(String(40), default="")
    reimbursement_category = Column(String(40), default="")   # optional, for JVD guidance
    score = Column(Integer, default=0)
    consent = Column(Boolean, default=False)          # DPDP: required before any outbound
    consent_at = Column(DateTime, nullable=True)
    assigned_to = Column(Integer, ForeignKey("staff.id"), nullable=True)
    ref_username = Column(String(60), default="")     # staff who brought this reference (commission basis)
    commission_amt = Column(Integer, default=0)       # ₹ agreed per joined admission
    commission_paid = Column(Boolean, default=False)  # settled flag
    commission_paid_at = Column(DateTime, nullable=True)
    seq_step = Column(Integer, default=0)             # follow-up sequence position
    next_followup_at = Column(DateTime, nullable=True)
    last_inbound_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)


class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True)
    college_id = Column(Integer, ForeignKey("colleges.id"), index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    channel = Column(String(20), default="web")       # web | whatsapp
    language = Column(String(10), default="en")       # en | te
    status = Column(String(20), default="open")       # open | handed_off
    created_at = Column(DateTime, default=utcnow)


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), index=True)
    role = Column(String(12))                         # parent | ai | staff
    text = Column(Text)
    citations = Column(JSON, default=list)
    flagged = Column(Boolean, default=False)          # trap-question handled
    created_at = Column(DateTime, default=utcnow)


class CounselorTask(Base):
    __tablename__ = "counselor_tasks"
    id = Column(Integer, primary_key=True)
    college_id = Column(Integer, ForeignKey("colleges.id"), index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    staff_id = Column(Integer, ForeignKey("staff.id"), nullable=True)
    kind = Column(String(30), default="call")         # call | whatsapp | verify | handoff | visit
    note = Column(Text, default="")
    due_at = Column(DateTime, default=utcnow)
    done = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)


class FollowUpLog(Base):
    __tablename__ = "followup_logs"
    id = Column(Integer, primary_key=True)
    college_id = Column(Integer, ForeignKey("colleges.id"), index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), index=True)
    template = Column(String(40))
    channel = Column(String(20), default="whatsapp")
    text = Column(Text)
    mode = Column(String(10), default="mock")         # mock | live
    sent_at = Column(DateTime, default=utcnow)


class KbChunk(Base):
    """RAG chunk. scope: global (counseling doctrine) | tenant (college CKP prose)."""
    __tablename__ = "kb_chunks"
    id = Column(Integer, primary_key=True)
    scope = Column(String(10), default="global", index=True)
    college_id = Column(Integer, ForeignKey("colleges.id"), nullable=True, index=True)
    title = Column(String(200))
    section = Column(String(200), default="")
    version = Column(String(20), default="2026-09")
    content = Column(Text)
    vec = Column(JSON)
    created_at = Column(DateTime, default=utcnow)


# ── SeatSetu Accred (Module B): NAAC / AQAR / OBE ────────────────────────────
class EvidenceItem(Base):
    """Accreditation evidence vault — one row per required proof."""
    __tablename__ = "evidence_items"
    id = Column(Integer, primary_key=True)
    college_id = Column(Integer, ForeignKey("colleges.id"), index=True)
    criterion = Column(String(20), default="1.1.1")   # NAAC metric number
    title = Column(String(300))
    owner = Column(String(120), default="")
    status = Column(String(20), default="pending")    # pending | collected | na
    file_note = Column(String(300), default="")       # filename or drive link
    created_at = Column(DateTime, default=utcnow)


class CourseReg(Base):
    """A course registration with its CO definitions + CO→PO mapping."""
    __tablename__ = "course_regs"
    id = Column(Integer, primary_key=True)
    college_id = Column(Integer, ForeignKey("colleges.id"), index=True)
    course_name = Column(String(200))
    code = Column(String(40), default="")
    semester = Column(String(30), default="")
    academic_year = Column(String(30), default="2025-26")
    cos = Column(JSON)            # [{no:1, desc:"...", bloom:2, pos:[1,2]}]
    co_po_map = Column(JSON)      # {"1": {"1":2,"2":3}, ...} CO→PO strength 1-3
    target = Column(Float, default=2.0)
    created_at = Column(DateTime, default=utcnow)


class AttainmentRun(Base):
    """Result of an OBE attainment computation for an uploaded marks sheet."""
    __tablename__ = "attainment_runs"
    id = Column(Integer, primary_key=True)
    college_id = Column(Integer, ForeignKey("colleges.id"), index=True)
    reg_id = Column(Integer, ForeignKey("course_regs.id"), index=True)
    filename = Column(String(300), default="")
    students = Column(Integer, default=0)
    result = Column(JSON)
    created_at = Column(DateTime, default=utcnow)


class SurveyResult(Base):
    """Indirect attainment (exit/stakeholder survey) per PO, avg on 0-3."""
    __tablename__ = "survey_results"
    id = Column(Integer, primary_key=True)
    college_id = Column(Integer, ForeignKey("colleges.id"), index=True)
    academic_year = Column(String(30), default="2025-26")
    respondents = Column(Integer, default=0)
    po_indirect = Column(JSON)    # {"1": 2.4, ...}
    created_at = Column(DateTime, default=utcnow)


class QPaper(Base):
    """Generated Bloom/CO-mapped question paper."""
    __tablename__ = "q_papers"
    id = Column(Integer, primary_key=True)
    college_id = Column(Integer, ForeignKey("colleges.id"), index=True)
    reg_id = Column(Integer, ForeignKey("course_regs.id"), index=True)
    title = Column(String(300))
    total_marks = Column(Integer, default=0)
    paper = Column(JSON)
    created_at = Column(DateTime, default=utcnow)


# ── SeatSetu Careers (Module C): Placement Copilot ───────────────────────────
class MockInterview(Base):
    __tablename__ = "mock_interviews"
    id = Column(Integer, primary_key=True)
    college_id = Column(Integer, ForeignKey("colleges.id"), index=True)
    student_name = Column(String(120))
    roll = Column(String(40), default="")
    branch = Column(String(40), default="")
    role = Column(String(60), default="")
    questions = Column(JSON)          # [{no,type,q,answer,score,tips,keywords}]
    overall = Column(Float, default=0)
    status = Column(String(12), default="open")   # open | done
    self_practice = Column(Integer, default=0)    # 1 = student self-practice via Practice Pass
    pass_id = Column(Integer, nullable=True)      # owning PracticePass
    created_at = Column(DateTime, default=utcnow)


class Feedback(Base):
    """Parent's 👍/👎 on AI answers — the AI-quality metric colleges can show NAAC."""
    __tablename__ = "feedback"
    id = Column(Integer, primary_key=True)
    college_id = Column(Integer, ForeignKey("colleges.id"), index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=True)
    helpful = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)


class StaffUser(Base):
    __tablename__ = "staff_users"
    id = Column(Integer, primary_key=True)
    college_id = Column(Integer, ForeignKey("colleges.id"), index=True, nullable=True)
    username = Column(String(60), unique=True, index=True)
    pw_hash = Column(String(200))
    role = Column(String(20), default="counselor")  # admin|principal|director|manager|office|counselor|placement|iqac
    name = Column(String(120), default="")
    phone = Column(String(20), default="")          # for WhatsApp welcome / recovery
    tabs_json = Column(Text, nullable=True)         # Owner's per-person allocation (null = role preset)
    last_login = Column(DateTime, nullable=True)    # last successful login
    must_change = Column(Boolean, default=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)


class PracticePass(Base):
    """Office-issued practice code: student self-practices voice mocks on any phone.
    No dashboard access — only their own attempts."""
    __tablename__ = "practice_passes"
    id = Column(Integer, primary_key=True)
    college_id = Column(Integer, ForeignKey("colleges.id"), index=True)
    student_name = Column(String(120))
    roll = Column(String(40), default="")
    branch = Column(String(40), default="CSE")
    code = Column(String(20), unique=True, index=True)
    active = Column(Boolean, default=True)
    last_used = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)


class Competitor(Base):
    """Owner-curated comparison pack: nearby colleges with PUBLIC data only.
    The AI compares using exactly these numbers + source note — never invented."""
    __tablename__ = "competitors"
    id = Column(Integer, primary_key=True)
    college_id = Column(Integer, ForeignKey("colleges.id"), index=True)
    name = Column(String(140))
    town = Column(String(80), default="")
    distance_km = Column(String(20), default="")
    annual_fee = Column(String(30), default="")
    placements_pct = Column(String(20), default="")
    closing_rank_note = Column(String(120), default="")
    their_strength = Column(String(200), default="")
    our_edge = Column(String(200), default="")
    source_note = Column(String(200), default="AICTE approvals / public disclosures")
    created_at = Column(DateTime, default=utcnow)


class AuditLog(Base):
    """Immutable trail: every AI answer, send, guardrail hit, human action."""
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    college_id = Column(Integer, ForeignKey("colleges.id"), index=True)
    actor = Column(String(20), default="ai")          # ai | staff | system
    action = Column(String(80))
    detail = Column(JSON)
    created_at = Column(DateTime, default=utcnow)


def init_db():
    Base.metadata.create_all(engine)


_ready = False


def ensure_ready():
    """Serverless-safe lazy bootstrap (idempotent per warm instance)."""
    global _ready
    if not _ready:
        from .seed import seed_if_empty
        seed_if_empty()
        try:  # v0.8.2: fictional Demo College (SSDC) for management demos — idempotent
            from .demo_college import seed_if_missing
            seed_if_missing()
        except Exception:
            pass
        try:  # lightweight migrations for DBs created before v0.5
            from sqlalchemy import text as _tx
            with engine.begin() as c:
                c.execute(_tx("ALTER TABLE colleges ADD COLUMN ad_spend JSON"))
        except Exception:
            pass
        try:  # v0.6 staff columns
            from sqlalchemy import text as _tx
            with engine.begin() as c:
                c.execute(_tx("ALTER TABLE staff_users ADD COLUMN phone VARCHAR(20) DEFAULT ''"))
                c.execute(_tx("ALTER TABLE staff_users ADD COLUMN tabs_json TEXT"))
                c.execute(_tx("ALTER TABLE staff_users ADD COLUMN last_login DATETIME"))
        except Exception:
            pass
        try:  # v0.7.2 self-practice columns
            from sqlalchemy import text as _tx
            with engine.begin() as c:
                c.execute(_tx("ALTER TABLE mock_interviews ADD COLUMN self_practice INTEGER DEFAULT 0"))
                c.execute(_tx("ALTER TABLE leads ADD COLUMN ref_username VARCHAR(60) DEFAULT ''"))
                c.execute(_tx("ALTER TABLE leads ADD COLUMN commission_amt INTEGER DEFAULT 0"))
                c.execute(_tx("ALTER TABLE leads ADD COLUMN commission_paid INTEGER DEFAULT 0"))
                c.execute(_tx("ALTER TABLE leads ADD COLUMN commission_paid_at DATETIME"))
                c.execute(_tx("ALTER TABLE mock_interviews ADD COLUMN pass_id INTEGER"))
        except Exception:
            pass
        try:  # hot-path indexes (idempotent, helps existing DBs too)
            from sqlalchemy import text as _tx
            with engine.begin() as c:
                for ix in ("CREATE INDEX IF NOT EXISTS idx_leads_col_stage ON leads(college_id, stage)",
                           "CREATE INDEX IF NOT EXISTS idx_leads_col_src ON leads(college_id, source)",
                           "CREATE INDEX IF NOT EXISTS idx_conv_col ON conversations(college_id, created_at)",
                           "CREATE INDEX IF NOT EXISTS idx_tasks_col_done ON counselor_tasks(college_id, done)",
                           "CREATE INDEX IF NOT EXISTS idx_fu_col_sent ON followup_logs(college_id, sent_at)",
                           "CREATE INDEX IF NOT EXISTS idx_mi_col ON mock_interviews(college_id, created_at)",
                           "CREATE INDEX IF NOT EXISTS idx_audit_col ON audit_logs(college_id, created_at)"):
                    c.execute(_tx(ix))
        except Exception:
            pass
        try:  # default staff logins for every college (principal/counselor/placement/iqac)
            from .authz import ensure_users_all
            with SessionLocal() as _db:
                ensure_users_all(_db)
        except Exception:
            pass
        _ready = True


def get_db():
    ensure_ready()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
