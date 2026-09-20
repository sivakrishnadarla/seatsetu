"""Seeds one fully-worked demo college (fictional) + global counseling doctrine
so every feature works the moment the server starts."""
from .corpus import CORPUS
from .db import (College, Conversation, Course, CounselorTask, CourseReg, EvidenceItem,
                 Hostel, KbChunk, KeyDate, Lead, Message, PlacementStat, SessionLocal,
                 Staff, SurveyResult, TransportRoute, init_db, utcnow)
from .rag import embed, ingest
from . import careers
from .db import MockInterview

ABOUT = ("Rayalaseema Institute of Technology (RIT) is an AICTE-approved engineering college on the "
         "Kadapa–Proddatur highway (5 km from Kadapa railway station, 15 min from the bus stand). "
         "Established 2009. Campus: 12 acres, 42 labs, central library, boys & girls hostels, "
         "Wi-Fi campus, indoor games, ATM. Affiliated to JNTUA, Anantapur.")

PROCESS = ("How to join RIT:\n"
           "1. EAPCET route: attend certificate verification, enter RIT (code RITK) in web options.\n"
           "2. Management quota: visit the college admission cell with documents; book a branch seat with a "
           "token (adjustable in tuition) — refund policy is explained in writing by the office.\n"
           "3. Documents: EAPCET hall ticket/rank card, SSC & Intermediate memos, TC, study certificates "
           "6th-12th, caste & income certificates (for JVD), Aadhaar, photos.\n"
           "Office hours: Mon-Sat 9:30am-5pm. Admission cell: +91-90000-12345.")

CKP_PROSE = [
    ("About & location", ABOUT),
    ("Admission process & documents", PROCESS),
    ("Placement training support", ("RIT runs a dedicated Placement & Training Cell: daily aptitude hour from "
        "2nd year, communication skills lab, mock interviews every semester, and paid internship tie-ups with "
        "local industries. These programs support the placement statistics reported in the approved data — "
        "outcomes depend on individual student effort.")),
    ("Scholarship guidance note", ("RIT's admission office helps families with JVD fee-reimbursement paperwork "
        "(AP convener-quota students). Eligibility depends on current-year government rules: AP domicile, "
        "income ceiling, certificates. The office verifies and confirms — the college never promises "
        "reimbursement in advance.")),
]


def seed_if_empty():
    init_db()
    db = SessionLocal()
    try:
        if db.query(KbChunk).filter(KbChunk.scope == "global").count() == 0:
            for entry in CORPUS:
                ingest(content=entry["content"], title=entry["title"],
                       section=entry["section"], scope="global", db=db)

        if db.query(College).count() == 0:
            col = College(name="Rayalaseema Institute of Technology", short="RIT Kadapa",
                          city="Kadapa", district="YSR Kadapa", eapcet_code="RITK",
                          website="ritkadapa.example.edu", phone="+91-90000-12345",
                          about=ABOUT, location_note=ABOUT.split(".")[1].strip() + ".",
                          admission_process=PROCESS, created_at=utcnow())
            db.add(col)
            db.flush()

            courses = [
                ("CSE — Computer Science & Engineering", "CSE", 240, 35000, 85000,
                 "Few seats left · token ₹10,000", "2025 closing rank ≈ 58,000",
                 "Highest placements; AI/ML electives, coding bootcamps"),
                ("CSE (AI & ML)", "CSE-AIML", 60, 35000, 80000,
                 "Few seats left · token ₹10,000", "2025 closing rank ≈ 52,000",
                 "AI/ML specialization with GPU lab"),
                ("ECE — Electronics & Communication", "ECE", 120, 35000, 70000,
                 "Seats available", "2025 closing rank ≈ 71,000",
                 "Embedded/IoT lab, VLSI electives"),
                ("MECH — Mechanical Engineering", "MECH", 60, 35000, 65000,
                 "Seats available", "2025 closing rank ≈ 96,000",
                 "CAD/CAM lab, industry visits"),
                ("CIVIL — Civil Engineering", "CIVIL", 60, 35000, 65000,
                 "Seats available", "2025 closing rank ≈ 1,05,000",
                 "Surveying camp, govt-job coaching support"),
            ]
            for name, code, intake, cf, mf, note, cutoff, hl in courses:
                db.add(Course(college_id=col.id, name=name, code=code, intake=intake,
                              convener_fee=cf, mgmt_fee=mf, mgmt_note=note,
                              cutoff_note=cutoff, highlights=hl))

            db.add(Hostel(college_id=col.id, for_whom="boys", ac=False, fee_per_year=72000,
                          facilities="3/day mess, warden, study hall 6-10pm, hot water, solar backup"))
            db.add(Hostel(college_id=col.id, for_whom="boys", ac=True, fee_per_year=95000,
                          facilities="AC rooms (2/share), laundry, gym access"))
            db.add(Hostel(college_id=col.id, for_whom="girls", ac=False, fee_per_year=68000,
                          facilities="Female wardens, CCTV, biometric entry, 3/day mess, study hall"))

            for row in [("Kadapa town", 8, 8000), ("Proddatur", 48, 14000),
                        ("Pulivendula", 38, 12000), ("Jammalamadugu", 55, 16000)]:
                db.add(TransportRoute(college_id=col.id, from_place=row[0],
                                      distance_km=row[1], fee_per_year=row[2]))

            db.add(PlacementStat(college_id=col.id, year="2025-26", placed_pct=68, offers=220,
                                 companies=45, top_lpa=4.5, avg_lpa=3.2,
                                 note="Approved by Placement Cell. % of eligible final-year students."))
            db.add(PlacementStat(college_id=col.id, year="2024-25", placed_pct=61, offers=185,
                                 companies=38, top_lpa=4.2, avg_lpa=3.0,
                                 note="Approved by Placement Cell."))

            for label, when in [
                ("Management quota admissions 2026-27", "Open now — booking token at admission cell"),
                ("EAPCET 2026 counselling (web options)", "Aug-Sep 2026 — enter code RITK"),
                ("Semester start (B.Tech 1st year)", "First week of September 2026"),
                ("Spot admissions round (if seats remain)", "Oct 2026 — watch this space"),
            ]:
                db.add(KeyDate(college_id=col.id, label=label, when_note=when))

            staff = [("Dr. K. Ramesh", "principal", "+91-90000-11111"),
                     ("Lakshmi Devi", "counselor", "+91-90000-22222"),
                     ("Suresh Babu", "counselor", "+91-90000-33333")]
            for n, r, p in staff:
                db.add(Staff(college_id=col.id, name=n, role=r, phone=p))

            db.flush()
            # sample leads across the funnel
            leads = [
                ("Praveen Reddy", "9876543210", "Proddatur", "meta_ad", "Monsoon Lead Form",
                 "interested", "CSE", "rank 61,200", True, 2),
                ("Sravani", "9812345678", "Kadapa", "website_chat", "",
                 "visit_booked", "CSE-AIML", "952 marks", True, 1),
                ("Mohan", "9700112233", "Pulivendula", "qr", "Hoarding QR — Ring Road",
                 "contacted", "ECE", "", True, 1),
                ("Yamuna", "9966778899", "Jammalamadugu", "walk_in", "",
                 "joined", "CSE", "rank 49,500", True, 0),
                ("Kiran", "9553344556", "Kadapa", "missed_call", "",
                 "ai_engaged", "", "", False, 0),
                ("Basha", "9848586878", "Proddatur", "referral", "Yamuna referral",
                 "interested", "MECH", "", True, 2),
                ("Divya", "9701122334", "Kadapa", "meta_ad", "Monsoon Lead Form",
                 "new", "", "", False, 0),
                ("Ravi Teja", "9871231234", "Vempalli", "website_chat", "",
                 "lost", "CIVIL", "", True, 0),
            ]
            for name, phone, town, source, campaign, stage, branch, rank, consent, staff_idx in leads:
                assigned = None
                if staff_idx:
                    assigned = db.query(Staff).filter_by(college_id=col.id, role="counselor")\
                                  .order_by(Staff.id).offset(staff_idx - 1).first()
                    assigned = assigned.id if assigned else None
                import datetime as _dt
                due = None
                if consent and stage in ("contacted", "interested", "visited"):
                    due = utcnow().replace(tzinfo=None) - _dt.timedelta(hours=6)  # DUE NOW
                    seq = 2 if stage == "interested" else 1
                db.add(Lead(college_id=col.id, name=name, phone=phone, town=town,
                            source=source, campaign=campaign, stage=stage,
                            branch_interest=branch, rank_or_marks=rank, consent=consent,
                            consent_at=utcnow() if consent else None,
                            assigned_to=assigned, created_at=utcnow(),
                            seq_step=seq if consent and stage in ("contacted", "interested", "visited") else 0,
                            next_followup_at=due))
            db.flush()

            # sample conversation (Praveen)
            praveen = db.query(Lead).filter_by(phone="9876543210").first()
            conv = Conversation(college_id=col.id, lead_id=praveen.id, channel="whatsapp",
                                language="te")
            db.add(conv)
            db.flush()
            db.add(Message(conversation_id=conv.id, role="parent",
                           text="సర్ CSE ఫీజు ఎంత? హాస్టల్ ఉందా?", created_at=utcnow()))
            db.add(Message(conversation_id=conv.id, role="ai", flagged=False,
                           text="ప్రవీణ్ గారూ, CSE: కన్వీనర్ కోటా ₹35,000/సం|| మేనేజ్‌మెంట్ కోటా ₹85,000/సం. "
                                "బాయ్స్ హాస్టల్ ₹72,000/సం (3 పూట భోజనం, వార్డెన్). JVD అర్హత ఆఫీస్ ధృవీకరిస్తుంది.",
                           citations=[dict(n=1, title="CKP: fee table", source="CKP: courses")],
                           created_at=utcnow()))
            db.add(CounselorTask(college_id=col.id, lead_id=praveen.id,
                                 staff_id=db.query(Staff).filter_by(role="counselor").first().id,
                                 kind="call", note="Praveen asked fees+hostel on WhatsApp — call today",
                                 due_at=utcnow(), created_at=utcnow()))

            # ── SeatSetu Accred seed: course regs, evidence, survey ──
            co_po = {str(c): {str(p): ((c + p) % 3) + 1 for p in range(1, 8) if (c + p) % 2 == 1}
                     for c in range(1, 6)}
            cos_demo = [
                {"no": 1, "desc": "explain core data structures and their applications", "bloom": 2, "pos": [1, 2]},
                {"no": 2, "desc": "apply searching & sorting algorithms to problems", "bloom": 3, "pos": [2, 3]},
                {"no": 3, "desc": "analyze algorithm complexity for given scenarios", "bloom": 4, "pos": [3, 4]},
                {"no": 4, "desc": "design database schemas using normalization", "bloom": 5, "pos": [4, 5]},
                {"no": 5, "desc": "build a mini-project integrating course concepts", "bloom": 6, "pos": [5, 6]},
            ]
            db.add(CourseReg(college_id=col.id, course_name="Data Structures (CSM-III)",
                             code="CS303PC", semester="II-II", academic_year="2025-26",
                             cos=cos_demo, co_po_map=co_po, target=2.0))
            db.add(CourseReg(college_id=col.id, course_name="Digital Electronics (ECE-II)",
                             code="EC204PC", semester="I-II", academic_year="2025-26",
                             cos=[{"no": c, "desc": f"demonstrate course outcome {c} of digital electronics",
                                   "bloom": min(1 + c, 6), "pos": [1, 2, 3]} for c in range(1, 5)],
                             co_po_map={str(c): {"1": 2, "2": 3} for c in range(1, 5)}, target=2.0))
            for crit in ["2.6.3", "5.1.2", "6.5.2", "4.1.3"]:
                db.add(EvidenceItem(college_id=col.id, criterion=crit,
                                    title=f"{crit} — sample pending item (photos/bills/minutes)",
                                    owner="IQAC", status="pending"))
            db.add(EvidenceItem(college_id=col.id, criterion="7.2.1",
                                title="Best practice #1: 'Every seat. Filled.' admission digital drive",
                                owner="IQAC", status="collected", file_note="best_practice_1.pdf"))
            db.add(EvidenceItem(college_id=col.id, criterion="2.6.3",
                                title="CO-PO attainment reports 2025-26 (SeatSetu computed)",
                                owner="IQAC", status="collected", file_note="attainment_runs.pdf"))
            db.add(SurveyResult(college_id=col.id, academic_year="2025-26", respondents=86,
                                po_indirect={str(p): round(2.1 + (p % 3) * 0.25, 2) for p in range(1, 8)}))
            qs_demo = careers.build_interview("CSE", "Software / IT")
            for q, ans, sc, tip in zip(qs_demo,
                ["I am Yamuna from Kadapa, CSE third year. I built a library management project with MySQL and I am learning Python.",
                 "My strength is consistency. Example: I completed 100 DSA problems in the last semester while maintaining 9.1 CGPA.",
                 "I built 2 mini projects in Python and MySQL, I learn fast, and your company works on web apps which matches my training.",
                 "DNS converts the name to IP, browser sends HTTP request, server responds and browser renders the page.",
                 "I will first talk to them, offer help, and split the work. In our project I did this and we submitted 2 days early."],
                [4.0, 4.5, 3.5, 3.5, 4.0],
                ["Good structure, add one more skill.", "Strong — quantify team size too.", "Good; add a result metric.",
                 "Correct order — mention rendering briefly.", "Excellent STAR answer."]):
                q.update(answer=ans, score=sc, tips=tip)
            db.add(MockInterview(college_id=col.id, student_name="Yamuna", roll="21B81A0504",
                                 branch="CSE", role="Software / IT", questions=qs_demo,
                                 overall=careers.overall_score(qs_demo), status="done",
                                 created_at=utcnow()))
            db.flush()

            # tenant CKP prose → tenant chunks
            for title, content in CKP_PROSE:
                ingest(content=content, title="RIT Kadapa — " + title, section=title,
                       scope="tenant", college_id=col.id, db=db)

            guard_log_init(db, col.id)
        db.commit()
    finally:
        db.close()


def guard_log_init(db, college_id):
    from .db import AuditLog
    db.add(AuditLog(college_id=college_id, actor="system", action="college.onboarded",
                    detail={"note": "demo seed", "tenant": "RIT Kadapa"}, created_at=utcnow()))
