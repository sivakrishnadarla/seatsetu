"""Auto-seeds the 'SeatSetu Demo College of Engineering' (SSDC) — a fully-worked
FICTIONAL tenant whose dashboard a sales demo can show to Principals / Directors
/ Management: leads funnel across every source, ROI per source, due follow-ups,
per-person staff logins, WhatsApp transcripts, tasks, competitor comparison,
AQAR evidence vault and a placement practice pass.

Idempotent + serverless-safe: created only when no college with EAPCET code
SSDC1 exists. Called from db.ensure_ready() wrapped in try/except, so a seeding
bug can never break server startup.
"""
import datetime as _dt

from . import authz
from .db import (College, Competitor, Conversation, CounselorTask, Course, CourseReg,
                 EvidenceItem, Hostel, KeyDate, Lead, Message, PlacementStat,
                 PracticePass, SessionLocal, Staff, StaffUser, TransportRoute,
                 AuditLog, utcnow)

CODE = "SSDC1"

ABOUT = ("SSDC is a 12-year-old engineering college on NH-16 near Benz Circle, "
         "Vijayawada — AICTE approved, affiliated to JNTUK. 4,200 students, 148 "
         "faculty, 62-acre campus with separate hostels for boys and girls, 42 labs "
         "and a placement & training cell that runs daily aptitude hour from 2nd year.")

PROCESS = ("How to join SSDC:\n"
           "1. AP EAPCET route: attend certificate verification, enter code SSDC1 in web "
           "options (convener quota — JVD fee reimbursement paperwork is helped free at "
           "the college help desk; approval depends on current-year government rules and "
           "is never promised in advance).\n"
           "2. Management quota: visit the admission office with documents; seat booking "
           "token is adjustable in tuition and the refund policy is given in writing.\n"
           "3. Documents: EAPCET hall ticket & rank card, SSC + Intermediate memos, "
           "TC/study certificates, Aadhaar, income & caste certificates if applicable.")

# name, phone, town, source, campaign, stage, branch, rank, consent, seq, due_hours
LEADS = [
    ("Divya Sri",        "9701266666", "Vijayawada", "meta_ad",      "Monsoon Lead Form",   "new",          "CSE",  "",        False, 0, 0),
    ("Harish Yadav",     "9701277777", "Guntur",     "meta_ad",      "Monsoon Lead Form",   "interested",   "CSE",  "rank 61,200", True, 2, -20),
    ("Swapna",           "9701255555", "Tenali",     "meta_ad",      "Retargeting — hostels", "contacted",  "AIML", "",        True, 1, -26),
    ("Manikanta",        "9848011111", "Gudivada",   "website_chat", "",                    "ai_engaged",   "CSE",  "rank 45,000", True, 0, 0),
    ("Sravani",          "9848022222", "Tenali",     "website_chat", "",                    "visit_booked", "ECE",  "",        True, 1, 30),
    ("Venkatesh",        "9848033333", "Nuzvid",     "website_chat", "",                    "seat_booked",  "CSE",  "rank 57,800", True, 3, 0),
    ("Prasad",           "9848044444", "Vijayawada", "website_chat", "",                    "applied",      "MECH", "",        True, 0, 0),
    ("Anitha",           "9848055555", "Guntur",     "website_chat", "",                    "joined",       "ECE",  "",        True, 0, 0),
    ("Rao",              "9848066666", "Machilipatnam", "website_chat", "",                 "lost",         "AIML", "",        True, 0, 0),
    ("Kiran",            "9848077777", "Mylavaram",  "website_chat", "",                    "ai_engaged",   "CIVIL", "",       True, 0, 0),
    ("Yamuna",           "9848090905", "Tiruvuru",   "qr",           "Hoarding QR NH-16",   "contacted",    "AIML", "",        True, 1, -6),
    ("L. Ramesh",        "9848090908", "Nuzvid",     "qr",           "Auto sticker QR",     "new",          "CIVIL", "",       False, 0, 0),
    ("M. Praveen",       "9848090903", "Jaggayyapeta", "referral",   "Alumni — Suresh",     "visited",      "MECH", "",        True, 2, -18),
    ("T. Kavya",         "9848090904", "Nandigama",  "referral",     "Staff referral",      "seat_booked",  "CSE",  "rank 55,400", True, 3, 0),
    ("K. Srinivasa Rao", "9848090901", "Vijayawada", "walk_in",      "Campus visit",        "visited",      "CSE",  "",        True, 2, -40),
    ("Ch. Mahesh",       "9848090906", "Vuyyuru",    "walk_in",      "Roadshow",            "interested",   "ECE",  "",        True, 1, -8),
    ("B. Anusha",        "9848090902", "Vuyyuru",    "missed_call",  "BoardDirect",         "new",          "ECE",  "",        False, 0, 0),
    ("G. Bhavani",       "9848090907", "Gudivada",   "missed_call",  "BoardDirect",         "contacted",    "AIML", "",        True, 1, -30),
    ("P. Naveen Kumar",  "9866012345", "Hanuman Junction", "import", "CSV import — school fair", "contacted", "CSE", "",     False, 0, 0),
    ("Padmavathi",       "9701122334", "Vijayawada", "import",       "CSV import — exhibition", "interested", "CSE", "",      False, 0, 0),
]


def seed_if_missing():
    db = SessionLocal()
    try:
        if db.query(College).filter_by(eapcet_code=CODE).first():
            return
        c = College(name="SeatSetu Demo College of Engineering", short="SSDC",
                    city="Vijayawada", district="NTR", eapcet_code=CODE,
                    website="https://poojasoftsolutions.com", phone="9247105525",
                    about=ABOUT, location_note="Benz Circle, Vijayawada, NTR district, "
                    "Andhra Pradesh 520008 — 6 km from railway station.",
                    admission_process=PROCESS,
                    ad_spend={"meta_ad": 15000, "hoarding": 8000, "qr": 2000})
        db.add(c)
        db.flush()

        for co in [dict(name="Computer Science & Engineering", code="CSE", intake="240",
                        convener_fee="79000", mgmt_fee="95000",
                        mgmt_note="Donation never collected",
                        cutoff_note="Last round closed around rank 58,000 (2025)",
                        highlights="180+ placement drives, AI & Data Science electives from 2nd year"),
                   dict(name="AI & Machine Learning", code="AIML", intake="120",
                        convener_fee="79000", mgmt_fee="95000",
                        cutoff_note="Closed around rank 52,000 (2025)",
                        highlights="NVIDIA GPU lab, Hyderabad AI-company internship MoU"),
                   dict(name="Electronics & Communication", code="ECE", intake="180",
                        convener_fee="72000", mgmt_fee="88000",
                        cutoff_note="Closed around rank 71,000 (2025)",
                        highlights="Embedded + IoT lab, ISRO student chapter"),
                   dict(name="Mechanical Engineering", code="MECH", intake="120",
                        convener_fee="61000", mgmt_fee="75000",
                        cutoff_note="Closed around rank 96,000 (2025)",
                        highlights="CNC workshop, core-company drives every January"),
                   dict(name="Civil Engineering", code="CIVIL", intake="60",
                        convener_fee="61000", mgmt_fee="75000",
                        cutoff_note="Closed around rank 105,000 (2025)",
                        highlights="AutoCAD + survey camp, government-job exam preparation")]:
            db.add(Course(college_id=c.id, **co))

        for h in [dict(for_whom="Boys", ac=False, fee_per_year="48000",
                       facilities="2/3 sharing, veg+nonveg mess, study hall 6-10pm, warden on campus"),
                  dict(for_whom="Girls", ac=False, fee_per_year="52000",
                       facilities="2/3 sharing, biometric entry, lady wardens, CCTV, parents may visit Sundays"),
                  dict(for_whom="Boys/Girls", ac=True, fee_per_year="78000",
                       facilities="2 sharing, AC, laundry, high-speed wifi")]:
            db.add(Hostel(college_id=c.id, **h))

        for r in [("Guntur", "58", "15000"), ("Tenali", "33", "10000"),
                  ("Machilipatnam", "68", "16000"), ("Nuzvid", "52", "14000"),
                  ("Hanuman Junction", "41", "12000")]:
            db.add(TransportRoute(college_id=c.id, from_place=r[0], distance_km=r[1],
                                  fee_per_year=r[2]))

        for p in [dict(year="2025", placed_pct=62, offers=340, companies=48,
                       top_lpa=6.5, avg_lpa=3.8,
                       note="Verified offers only; internship stipends not counted"),
                  dict(year="2024", placed_pct=57, offers=295, companies=41,
                       top_lpa=6.0, avg_lpa=3.5, note="AICTE-approved disclosures")]:
            db.add(PlacementStat(college_id=c.id, **p))

        for d in [("EAPCET web options — special round", "Check the EAPCET website; the college help desk fills options free"),
                  ("Management quota closes", "When seats fill — usually 2-3 weeks after counselling ends"),
                  ("Classes begin", "August 1 (as per JNTUK calendar)")]:
            db.add(KeyDate(college_id=c.id, label=d[0], when_note=d[1]))

        # internal staff directory (assignment targets)
        db.add(Staff(college_id=c.id, name="Principal", role="principal"))
        db.flush()
        lakshmi = Staff(college_id=c.id, name="Lakshmi Devi", role="counselor",
                        phone="9848500111")
        ravi = Staff(college_id=c.id, name="Ravi Kumar", role="office",
                     phone="9848500222")
        db.add_all([lakshmi, ravi])
        db.flush()

        # per-person logins (no shared passwords) — ready to hand out in demos.
        # Usernames are globally unique: prefix with tenant code to avoid clashes.
        for u, pw, role, name, phone, tabs in [
                ("ssdc.director", "director-2026", "director",
                 "Dr. A. Rama Krishnan (Director)", "9848500001", None),
                ("ssdc.lakshmi", "lakshmi-2026", "counselor", "Lakshmi Devi", "9848500111", None),
                ("ssdc.ravi", "ravi-2026", "office", "Ravi Kumar", "9848500222",
                 '["tasks", "leads", "followups", "help"]'),
                ("ssdc.iqac", "iqac-2026", "iqac", "Prof. J. Sarala (IQAC)", "9848500333", None)]:
            if not db.query(StaffUser).filter_by(username=u).first():
                db.add(StaffUser(college_id=c.id, username=u,
                                 pw_hash=authz.hash_pw(pw), role=role, name=name,
                                 phone=phone, tabs_json=tabs, must_change=False))

        # leads across every source + stage, a few follow-ups DUE NOW
        from .counselor import rescore
        for (name, phone, town, src, camp, stage, br, rank, consent, seq, due_h) in LEADS:
            due = None
            if due_h:
                due = utcnow().replace(tzinfo=None) + _dt.timedelta(hours=due_h)
            assigned = lakshmi.id if consent and seq else None
            lead = Lead(college_id=c.id, name=name, phone=phone, town=town,
                        source=src, campaign=camp, stage=stage, branch_interest=br,
                        rank_or_marks=rank, consent=consent,
                        consent_at=utcnow().replace(tzinfo=None) if consent else None,
                        assigned_to=assigned,
                        created_at=utcnow().replace(tzinfo=None)
                        - _dt.timedelta(hours=(due_h and abs(due_h) + 24) or 6),
                        seq_step=seq, next_followup_at=due)
            rescore(lead)
            db.add(lead)
        db.flush()

        # WhatsApp transcript (Telugu) — the honest-referral story
        anitha = db.query(Lead).filter_by(college_id=c.id, phone="9848055555").first()
        conv = Conversation(college_id=c.id, lead_id=anitha.id, channel="whatsapp",
                            language="te", status="handed_off")
        db.add(conv)
        db.flush()
        for role, text, flagged in [
                ("parent", "అమ్మాయికి ECE సీటు వస్తుందా? గర్ల్స్ హాస్టల్ ఫీజు ఎంత?", False),
                ("ai", "అనీత గారూ, గత ఏడాది ECE క్లోజింగ్ ర్యాంక్ సుమారు 71,000 (2025). "
                       "గర్ల్స్ హాస్టల్ (నాన్-AC): ₹52,000/సం॥ — బయోమెట్రిక్ ఎంట్రీ, లేడీ వార్డెన్, CCTV. "
                       "ప్రతి నంబర్‌కి సోర్స్ ఉంటుంది.", False),
                ("parent", "100% జాబ్ గ్యారంటీ ఇస్తారా?", True),
                ("ai", "గ్యారంటీ మేము ఇవ్వము — అబద్ధం చెప్పము. 2025 లో ECE లో 62% విద్యార్థులకు ఆఫర్స్ "
                       "వచ్చాయి (48 కంపెనీలు, సోర్స్: కాలేజీ ప్లేస్‌మెంట్ సెల్). మీ కూతురి ఎఫర్ట్ మీద "
                       "ఫలితం ఉంటుంది. క్యాంపస్ విజిట్‌కి రండి — బుక్ చేసుకోవాలా?", False),
                ("parent", "శనివారం వస్తాను చూడ్డానికి", False)]:
            db.add(Message(conversation_id=conv.id, role=role, text=text, flagged=flagged))

        # English web transcript with the honest trap-question refusal
        kiran = db.query(Lead).filter_by(college_id=c.id, phone="9848077777").first()
        conv2 = Conversation(college_id=c.id, lead_id=kiran.id, channel="web", language="en")
        db.add(conv2)
        db.flush()
        for role, text, flagged in [
                ("parent", "what is the CSE cutoff and management quota fee?", False),
                ("ai", "CSE closing rank was about 58,000 last year (2025, convener quota). "
                       "Management quota is Rs 95,000/year — donation is never collected. Source: "
                       "admission office, 2025 records.", False),
                ("parent", "ok but guarantee seat in CSE if I pay today?", True),
                ("ai", "I can't guarantee a seat — that would be wrong. Seats depend on counselling "
                       "and availability confirmed by the office. May I book you a campus visit "
                       "so the admission office confirms today's status?", False)]:
            db.add(Message(conversation_id=conv2.id, role=role, text=text, flagged=flagged))

        # counselor to-do
        db.add(CounselorTask(college_id=c.id, lead_id=kiran.id, staff_id=lakshmi.id,
                             kind="call", note="Call Kiran — CIVIL doubt, offer bus-route info",
                             due_at=utcnow().replace(tzinfo=None)))
        db.add(CounselorTask(college_id=c.id, lead_id=anitha.id, staff_id=lakshmi.id,
                             kind="verify", note="Collect Anitha's certificates set — joined",
                             done=True, due_at=utcnow().replace(tzinfo=None)))
        db.add(CounselorTask(college_id=c.id, staff_id=ravi.id, kind="visit",
                             note="Prepare visit kit + hostel tour for Saturday visitors",
                             due_at=utcnow().replace(tzinfo=None)))

        # competitor comparison pack (public-data only)
        db.add(Competitor(college_id=c.id, name="Sri Vision Institute of Technology",
                          town="Guntur", distance_km="58 km", annual_fee="92000",
                          placements_pct="54%", closing_rank_note="CSE closes ~70k",
                          their_strength="New buildings",
                          our_edge="Higher placement % + senior faculty",
                          source_note="Public AICTE disclosures 2025-26"))
        db.add(Competitor(college_id=c.id, name="Coastal Institute of Engineering",
                          town="Machilipatnam", distance_km="68 km", annual_fee="85000",
                          placements_pct="49%", closing_rank_note="CSE closes ~82k",
                          their_strength="Lower fee",
                          our_edge="Better hostel + 180+ drives vs 90",
                          source_note="College websites, 2025"))

        # AQAR / accreditation evidence vault
        for e in [("Criterion 3", "Placement records 3 years (offers + salary slips)",
                   "Placement Cell", "Export from Careers module as CSV"),
                  ("Criterion 5", "Student support: counselling chat transcripts (consented)",
                   "IQAC", "Auto-collected by AI counselor with consent log"),
                  ("Criterion 6", "Admissions funnel + ROI reports (management)",
                   "Director's office", "Monday one-pager PDFs")]:
            db.add(EvidenceItem(college_id=c.id, criterion=e[0], title=e[1],
                                owner=e[2], file_note=e[3]))

        # placement practice pass (code shown on the /practice page)
        if not db.query(PracticePass).filter_by(code="DEMO2026").first():
            db.add(PracticePass(college_id=c.id, student_name="Keerthana", roll="22ECE012",
                                branch="ECE", code="DEMO2026"))

        db.add(AuditLog(college_id=c.id, actor="system", action="college.onboarded",
                        detail={"note": "demo seed", "tenant": "SSDC Vijayawada"},
                        created_at=utcnow()))
        db.commit()

        # tenant knowledge chunks for AI answers (never blocks startup)
        try:
            from .rag import ingest
            ingest(content=ABOUT, title="SSDC — About & Location", section="about",
                   scope="tenant", college_id=c.id, db=db)
            ingest(content=PROCESS, title="SSDC — Admission Process & Documents",
                   section="process", scope="tenant", college_id=c.id, db=db)
            db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()
