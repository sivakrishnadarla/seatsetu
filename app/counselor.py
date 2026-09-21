"""The AI Admissions Counselor brain.

Pipeline per parent message:
  language detect → kill switch → human/complaint handoff → trap refusal →
  structured CKP-table answer (exact numbers) → RAG fallback (tenant-first) →
  honest escape hatch → lead capture state machine → follow-up scheduling →
  full audit logging with citations.

Bilingual: Telugu-first (code-mixed, the way parents type) + English.
Works with ZERO API keys (deterministic brain); upgrades to grounded LLM
generation when GEMINI_API_KEY/GITHUB_TOKEN is set.
"""
import re
from datetime import timedelta

from . import connectors, guardrails
from .config import SETTINGS
from .db import (College, Conversation, CounselorTask, Course, Hostel, KbChunk, KeyDate,
                 Lead, Message, PlacementStat, Staff, TransportRoute, utcnow)
from .llm import complete, llm_available
from .rag import ingest, retrieve

# ── bilingual keyword maps ───────────────────────────────────────────────────
TOPICS = {
    "fees": r"(fee|fees|tuition|cost|ఫీజు|ఫీజులు|ఎంత ఖర్చు)",
    "hostel": r"(hostel|room|mess|stay|హాస్టల్|వసతి|భోజనం)",
    "transport": r"(bus|transport|route|బస్సు|రవాణా)",
    "placements": r"(placement|placed|package|recruit|ప్లేస్\S*|ప్యాకేజీ|ఉద్యోగాలు)",
    "courses": r"(course|branch|branches|stream|కోర్సు|బ్రాంచ్|కోర్సులు)",
    "cutoff": r"(cutoff|closing rank|last rank|\brank\b|కటాఫ్|ర్యాంక్)",
    "dates": r"(date|deadline|last date|when.*(start|open|join)|తేదీ|ఎప్పుడు|గడువు)",
    "location": r"(where|location|address|distance|reach|ఎక్కడ|చిరునామా|దూరం)",
    "process": r"(admission|join|apply|process|how to|document|certificate|చేరడానికి|ప్రక్రియ|డాక్యుమెంట్|అడ్మిషన్)",
    "greeting": r"^(hi|hii+|hello|hey|namaste|నమస్తే|హాయ్)\b",
}
PHONE_RE = r"\d[\d ]{8,16}\d"   # raw digit-run scan (spaces allowed inside)
CONSENT_YES = r"^(yes|yeah|yep|ok|okay|sure|haan|avunu|avvamu|అవును|సరే|హాఅన్)"
BRANCH_HINTS = {
    "cse": r"\b(cse|computer science|cs)\b|సీఎస్|కంప్యూటర",
    "ai": r"\b(ai|ml|artificial|machine learning|data science)\b|ఏఐ|ఆర్టిఫిషియల్",
    "ece": r"\b(ece|electronics|ec)\b|ఈసీఈ|ఎలక్ట్రానిక్స్",
    "mech": r"\b(mech|mechanical)\b|మెక్|మెకానికల్",
    "civil": r"\b(civil)\b|సివిల్",
}


def _detect_topic(text: str, exclude: str | None = None) -> str | None:
    t = text.lower()
    for topic, pat in TOPICS.items():
        if topic == exclude:
            continue
        if re.search(pat, t):
            return topic
    return None


def _detect_branch(text: str, courses) -> Course | None:
    t = text.lower()
    for c in courses:
        code = (c.code or "").lower()
        key = code.split("-")[0].lower() if code else ""
        for hint_key, pat in BRANCH_HINTS.items():
            if re.search(pat, t):
                if hint_key in code or hint_key in (c.name or "").lower():
                    return c
    for c in courses:  # direct code mention
        if code and re.search(rf"\b{re.escape(code.lower())}\b", t):
            return c
    return None


def _rupees(n: int) -> str:
    return f"₹{n:,}" if n else "—"


# ── structured answer builders (exact numbers from CKP tables) ───────────────
def _answer_fees(col, branch, lang) -> tuple[str, list]:
    courses = branch and [branch] or col.courses
    lines, cites = [], [dict(n=1, title="College Knowledge Pack — fee table", source="CKP: courses")]
    n = 2
    for c in courses[:4]:
        if lang == "te":
            lines.append(f"▸ {c.name} (కోడ్ {c.code}): కన్వీనర్ కోటా {_rupees(c.convener_fee)}/సం|| మేనేజ్‌మెంట్ కోటా {_rupees(c.mgmt_fee)}/సం")
        else:
            lines.append(f"▸ {c.name} (code {c.code}): Convener quota {_rupees(c.convener_fee)}/yr · Management quota {_rupees(c.mgmt_fee)}/yr")
        if c.mgmt_note:
            lines.append(f"   ({c.mgmt_note})")
    scholarship = ("JVD ఫీజు రీఇంపర్స్‌మెంట్ అర్హత ఉండవచ్చు (AP నివాసి, ఆదాయ పరిమితి, కన్వీనర్ కోటా) — ప్రస్తుత సంవత్సర అర్హత మా ఆఫీస్ ధృవీకరిస్తుంది."
                   if lang == "te" else
                   "JVD fee reimbursement may apply for eligible convener-quota students (AP domicile, income ceiling) — our office verifies current-year eligibility before confirming.")
    lines.append(scholarship)
    cites.append(dict(n=n, title="JVD fee reimbursement guidance", source="doctrine: scholarship basics"))
    return "\n".join(lines), cites


def _answer_hostel(col, lang):
    hs = db_hostels(col)
    lines, cites = [], [dict(n=1, title="College Knowledge Pack — hostel", source="CKP: hostels")]
    for h in hs:
        kind = "Boys" if h.for_whom == "boys" else "Girls"
        ac = "AC" if h.ac else "non-AC"
        if lang == "te":
            lines.append(f"▸ {kind} హాస్టల్ ({ac}): {_rupees(h.fee_per_year)}/సం — {h.facilities}")
        else:
            lines.append(f"▸ {kind} hostel ({ac}): {_rupees(h.fee_per_year)}/yr — {h.facilities}")
    invite = ("మీరు హాస్టల్, మెస్ చూడటానికి ఎప్పుడైనా వచ్చేయవచ్చు — ముందస్తు సమాచారం అవసరం లేదు. ఫోటోలు కావాలా?"
              if lang == "te" else
              "You're welcome to visit the hostel and mess anytime — no appointment needed. Shall I send photos?")
    lines.append(invite)
    return "\n".join(lines), cites


def _answer_transport(col, lang):
    routes = db_routes(col)
    lines, cites = [], [dict(n=1, title="College Knowledge Pack — transport", source="CKP: transport")]
    for r in routes:
        if lang == "te":
            lines.append(f"▸ {r.from_place} ({r.distance_km:g} కి.మీ): {_rupees(r.fee_per_year)}/సం")
        else:
            lines.append(f"▸ {r.from_place} ({r.distance_km:g} km): {_rupees(r.fee_per_year)}/yr")
    more = ("మీ ఊరి పేరు చెబితే రూట్ ఉందో చెబుతాను." if lang == "te"
            else "Tell me your town and I'll check the route for you.")
    lines.append(more)
    return "\n".join(lines), cites


def _answer_placements(col, lang):
    ps = db_latest_placements(col)
    cites = [dict(n=1, title=f"Approved placement data {ps.year if ps else '2025-26'}", source="CKP: placement stats")]
    if not ps:
        return ("Placement details కోసం మా కాలేజీ ఆఫీస్‌ని సంప్రదించండి." if lang == "te"
                else "Please contact the college office for placement details."), cites
    if lang == "te":
        text = (f"{ps.year} సంవత్సరం: అర్హత ఉన్న విద్యార్థులలో {ps.placed_pct:g}% ప్లేస్‌మెంట్ పొందారు — "
                f"{ps.offers}+ ఆఫర్లు, {ps.companies} కంపెనీలు. టాప్ ప్యాకేజీ ₹{ps.top_lpa:g} LPA, సగటు ₹{ps.avg_lpa:g} LPA.\n"
                "ప్లేస్‌మెంట్ మీ కృషి మీద ఆధారపడి ఉంటుంది — హామీ ఎవరూ ఇవ్వలేరు, కానీ మా రికార్డ్ చూడండి. "
                "ప్లేస్‌మెంట్ ఆఫీసర్‌ని కలవడానికి క్యాంపస్ విజిట్ చేయండి.")
    else:
        text = (f"In {ps.year}: {ps.placed_pct:g}% of eligible students were placed — {ps.offers}+ offers "
                f"from {ps.companies} companies. Top package ₹{ps.top_lpa:g} LPA, average ₹{ps.avg_lpa:g} LPA.\n"
                "Placements depend on your effort too — no honest college guarantees jobs, but this record is our evidence. "
                "Visit the campus and meet the placement team.")
    return text, cites


def _answer_courses(col, lang):
    lines, cites = [], [dict(n=1, title="College Knowledge Pack — courses", source="CKP: courses")]
    for c in col.courses:
        if lang == "te":
            lines.append(f"▸ {c.name} — ఇన్టేక్ {c.intake} (EAPCET కోడ్: {c.code})")
        else:
            lines.append(f"▸ {c.name} — intake {c.intake} (EAPCET code: {c.code})")
    ask = ("మీకు ఏ బ్రాంచ్ ఆసక్తి? ఫీజులు, హాస్టల్, ప్లేస్‌మెంట్స్ వివరాలు చెబుతాను." if lang == "te"
           else "Which branch interests you? I'll share fees, hostel and placement details.")
    lines.append(ask)
    return "\n".join(lines), cites


RANK_IN_TEXT = re.compile(
    r"rank\D{0,12}(\d{1,3}(?:[,\d]{0,8})?)|((?<![\d,.])\d{2,3}(?:[,\d]{0,8})?\s*rank)", re.I)
CLOSING_IN_NOTE = re.compile(r"(?:closing|last)\s*rank\D{0,10}(\d{1,3}(?:[,\d]{0,8})?)", re.I)


def _num(txt):
    try:
        return int((txt or "").replace(",", ""))
    except Exception:
        return None


def _parse_rank(text):
    """Extract an EAPCET rank a parent mentioned, e.g. 'rank 45000', '45,000 rank', 'ర్యాంక్ 92000'."""
    text = (text or "").replace("ర్యాంకు", "rank").replace("ర్యాంక్", "rank")
    m = RANK_IN_TEXT.search(text)
    if not m:
        return None
    n = _num(m.group(1) or (m.group(2) or "").replace("rank", ""))
    return n if n and 1 <= n <= 999999 else None


def _closing_rank(note):
    """Pull the approved closing-rank number from a CKP cutoff note."""
    m = CLOSING_IN_NOTE.search(note or "")
    return _num(m.group(1)) if m else None


def _answer_cutoff(col, branch, lang, text=""):
    cites = [dict(n=1, title="College Knowledge Pack — cutoff notes", source="CKP: courses")]
    rank = _parse_rank(text)
    rows = [(c, _closing_rank(c.cutoff_note)) for c in col.courses]
    rows = [(c, cr) for c, cr in rows if cr]
    if rank and rows:
        def verdict(r, cr):
            if r <= cr * 0.90:
                return "✅", "strong chance", "మంచి అవకాశం ఉంది"
            if r <= cr:
                return "🟡", "borderline — possible in later rounds", "బోర్డర్‌లైన్ — తర్వాతి రౌండ్లలో అవకాశం"
            return "🔴", "tough — management quota or other branches", "కష్టం — మేనేజ్‌మెంట్ కోటా / ఇతర బ్రాంచ్‌లు చూడండి"
        order = {"✅": 0, "🟡": 1, "🔴": 2}
        head = (f"మీ ర్యాంక్ {rank:,} — గత ఏడాది క్లోజింగ్ ర్యాంక్‌లతో పోల్చితే:" if lang == "te"
                else f"Your rank {rank:,} — compared to last year's closing ranks:")
        scored = []
        for c, cr in rows:
            mark, en, te = verdict(rank, cr)
            scored.append((order[mark], f"{mark} {c.code}: closed at {cr:,} → {te if lang == 'te' else en}"))
        scored.sort()
        tail = ("తుది సీటు కన్వీనర్ కౌన్సెలింగ్‌లో మాత్రమే ఖరారవుతుంది — ఖచ్చితమైన సలహా కోసం క్యాంపస్‌కు వచ్చి కౌన్సెలర్‌ని కలవండి."
                if lang == "te" else
                "Final seat allotment is decided only in convener counseling — visit the campus and meet our counselor for exact guidance.")
        lines = [head] + [t for _, t in scored] + [tail]
        cites.append(dict(n=2, title="Last-year closing ranks (approved CKP)", source="CKP: courses"))
        return "\n".join(lines), cites
    if branch:
        note = branch.cutoff_note or "No approved cutoff note for this branch yet."
        name = branch.name
    else:
        name = col.name
        note = " · ".join(f"{c.code}: {c.cutoff_note}" for c in col.courses if c.cutoff_note) or \
               "No approved cutoff notes yet."
    honest = ("ఈ సంవత్సరం ర్యాంక్‌లను ముందుగా చెప్పడం సాధ్యం కాదు — గత సంవత్సరం డేటా మాత్రమే చెబుతాను." if lang == "te"
              else "I can't predict this year's cutoffs — here's last year's data only.")
    return f"{honest}\n{name}: {note}", cites


def _answer_dates(col, lang):
    lines, cites = [], [dict(n=1, title="College Knowledge Pack — key dates", source="CKP: dates")]
    for d in db_dates(col):
        lines.append(f"▸ {d.label}: {d.when_note}")
    return "\n".join(lines), cites


def _answer_location(col, lang):
    cites = [dict(n=1, title="College Knowledge Pack — location", source="CKP: about")]
    return col.location_note or (f"{col.name}, {col.city}." if lang == "te" else f"{col.name}, {col.city}."), cites


def _answer_process(col, lang):
    cites = [dict(n=1, title="Admission process & documents", source="CKP: process"),
             dict(n=2, title="Admission document checklist", source="doctrine: documents")]
    body = col.admission_process or "Contact the college office."
    checklist = ("డాక్యుమెంట్స్: EAPCET హాల్ టికెట్/ర్యాంక్ కార్డ్, SSC+ఇంటర్ మెమోలు, TC, స్టడీ సర్టిఫికేట్లు, కుల+ఆదాయ ధృవీకరణ పత్రాలు, ఆధార్, ఫోటోలు."
                 if lang == "te" else
                 "Documents: EAPCET hall ticket/rank card, SSC + Intermediate memos, TC, study certificates, caste & income certificates (for JVD), Aadhaar, photos.")
    return f"{body}\n{checklist}", cites


def _greet(col, lang):
    return ("నమస్తే! 🙏 నేను " + (col.short or col.name) + " AI కౌన్సిలర్‌ని. కోర్సులు, ఫీజులు, హాస్టల్, బస్సు రూట్లు, ప్లేస్‌మెంట్లు — ఏదైనా అడగండి."
            if lang == "te" else
            f"Hello! 👋 I'm the {col.short or col.name} AI counselor. Ask me anything — courses, fees, hostel, bus routes, placements.")


def _ask_details(col, lang, lead) -> str:
    if lead:
        return ""
    if lang == "te":
        return ("\n\nమీ పేరు, ఊరు, ఫోన్ నంబర్ పంపండి — మా కౌన్సిలర్ కాల్ చేసి, క్యాంపస్ విజిట్ ఏర్పాటు చేస్తారు. "
                "(ఉదా: రవి, ప్రొద్దుటూరు, 9876543210)")
    return ("\n\nShare your NAME, TOWN and PHONE and our counselor will call you and arrange a campus visit. "
            "(e.g. Ravi, Proddatur, 9876543210)")


def _trap_reply(trap: str, col, lang) -> tuple[str, list]:
    ps = db_latest_placements(col)
    cites = [dict(n=1, title=f"Approved placement data {ps.year if ps else ''}".strip(),
                  source="CKP: placement stats")] if ps else []
    if trap == "job_guarantee":
        en = ("No genuine college can guarantee jobs — and we won't make false promises to you. "
              + (f"Our approved record ({ps.year}): {ps.placed_pct:g}% of eligible students placed, "
                 f"{ps.offers}+ offers, top ₹{ps.top_lpa:g} LPA. " if ps else "")
              + "Placements depend on student effort + training — visit us and meet the placement team.")
        te = ("ఎటువంటి నిజాయితీ కాలేజీ ఉద్యోగ హామీ ఇవ్వదు — మేమూ తప్పుడు హామీలు ఇవ్వము. "
              + (f"మా ధృవీకరించిన రికార్డ్ ({ps.year}): అర్హుల్లో {ps.placed_pct:g}% ప్లేస్‌మెంట్, {ps.offers}+ ఆఫర్లు, టాప్ ₹{ps.top_lpa:g} LPA. " if ps else "")
              + "ప్లేస్‌మెంట్ మీ కృషి + శిక్షణపై ఆధారపడి ఉంటుంది — వచ్చి ప్లేస్‌మెంట్ టీమ్‌ని కలవండి.")
        return (te if lang == "te" else en), cites
    if trap == "salary_promise":
        en = ("We can't promise a specific salary — no honest college can. "
              + (f"Approved {ps.year} data: top ₹{ps.top_lpa:g} LPA, average ₹{ps.avg_lpa:g} LPA. " if ps else "")
              + "Your skills decide the offer; our training and record support you.")
        te = ("నిర్దిష్ట జీతం హామీ ఇవ్వలేము — ఎటువంటి నిజాయితీ కాలేజీ ఇవ్వదు. "
              + (f"ధృవీకరించిన {ps.year} డేటా: టాప్ ₹{ps.top_lpa:g} LPA, సగటు ₹{ps.avg_lpa:g} LPA. " if ps else "")
              + "మీ నైపుణ్యమే ఆఫర్‌ని నిర్ణయిస్తుంది; మా శిక్షణ మీకు తోడ్పడుతుంది.")
        return (te if lang == "te" else en), cites
    if trap == "scholarship_certain":
        en = ("I can't confirm scholarship/reimbursement eligibility in chat — it depends on current-year government rules, "
              "income ceiling, caste certificate and convener-quota admission. Our office will verify your documents and confirm. "
              "Shall I book a counselor call?")
        te = ("స్కాలర్‌షిప్/రీఇంపర్స్‌మెంట్ అర్హతను ఇక్కడ ఖచ్చితంగా చెప్పలేను — అది ప్రభుత్వ నియమాలు, ఆదాయ పరిమితి, కుల ధృవీకరణ పత్రాలు, "
              "కన్వీనర్ కోటా ప్రవేశంపై ఆధారపడి ఉంటుంది. మా ఆఫీస్ మీ పత్రాలు సరిచూసి ధృవీకరిస్తుంది. కౌన్సిలర్ కాల్ కావాలా?")
        return (te if lang == "te" else en), []
    if trap == "refund_ruling":
        en = ("Refund rules are institutional and must be confirmed by the college office — I don't want to "
              "misinform you. I've marked this for our counselor to explain the exact policy in writing.")
        te = ("రీఫండ్ నియమాలు కాలేజీ ఆఫీస్ మాత్రమే ధృవీకరించాలి — తప్పు సమాచారం ఇవ్వకూడదు. "
              "ఖచ్చితమైన విధానాన్ని మా కౌన్సిలర్ రాతపూర్వకంగా వివరిస్తారు.")
        return (te if lang == "te" else en), []
    if trap == "rank_predict":
        en = ("I can't predict seats or future cutoffs. I can share last year's closing ranks for each branch — "
              "which branch are you asking about?")
        te = ("సీట్లు లేదా భవిష్య కటాఫ్‌లను అంచనా వేయలేను. గత సంవత్సరం క్లోజింగ్ ర్యాంక్‌లు చెబుతాను — ఏ బ్రాంచ్ గురించి?")
        return (te if lang == "te" else en), []
    return "", []


def _handoff_reply(lang, col) -> str:
    return (f"ఖచ్చితంగా — మా కౌన్సిలర్ మిమ్మల్ని కలుస్తారు. మీ ఫోన్ నంబర్ చెబితే వెంటనే కాల్ చేస్తార్లు 📞 (కాలేజీ: {col.phone})"
            if lang == "te" else
            f"Of course — our counselor will speak with you personally. Share your phone number and they'll call you shortly 📞 (college: {col.phone})")


def _escape_reply(lang) -> str:
    return ("ఇది ఖచ్చితంగా చెప్పడానికి నా దగ్గర ధృవీకరించిన సమాచారం లేదు — ఊహించి చెప్పను. "
            "మా కౌన్సిలర్ కచ్చితమైన సమాధానం ఇస్తారు; మీ నంబర్ ఇస్తే కాల్ చేస్తార్లు."
            if lang == "te" else
            "I don't have verified information for that and I won't guess. "
            "Our counselor will give you the exact answer — share your number and they'll call you.")


# ── DB helpers ───────────────────────────────────────────────────────────────
def db_hostels(col): return db_obj("Hostel", col)
def db_routes(col): return db_obj("TransportRoute", col)
def db_dates(col): return db_obj("KeyDate", col)


def db_obj(model_name, col):
    from .db import SessionLocal
    model = {"Hostel": Hostel, "TransportRoute": TransportRoute, "KeyDate": KeyDate}[model_name]
    db = SessionLocal()
    try:
        return db.query(model).filter(model.college_id == col.id).all()
    finally:
        db.close()


def db_latest_placements(col):
    from .db import SessionLocal
    db = SessionLocal()
    try:
        return (db.query(PlacementStat).filter(PlacementStat.college_id == col.id)
                  .order_by(PlacementStat.year.desc()).first())
    finally:
        db.close()


# ── Lead capture & scoring ───────────────────────────────────────────────────
SOURCE_SCORES = {"meta_ad": 30, "referral": 25, "walk_in": 25, "qr": 15,
                 "website_chat": 10, "missed_call": 10, "import": 5}


def extract_phone(text: str) -> str | None:
    """Finds a 10-digit Indian mobile in messy text ('my number is 98765 00011.')."""
    for m in re.finditer(PHONE_RE, text):
        p = re.sub(r"\D", "", m.group(0))
        if len(p) == 12 and p.startswith("91"):
            p = p[2:]
        if len(p) == 11 and p.startswith("0"):
            p = p[1:]
        if len(p) == 10 and p[0] in "6789":
            return p
    return None


def parse_details(text: str) -> tuple[str, str]:
    """Extracts (name, town) from free text in common formats:
    'I am Ravi from Proddatur...' · 'Ravi, Proddatur, 9876500011' · 'na peru X, nunchi Y'."""
    t = text.strip()
    name = town = ""
    parts = [x.strip() for x in t.split(",")]
    if len(parts) >= 3 and re.search(r"\d", parts[0]):
        # "9876500011, Ravi Kumar, Proddatur" → number-first format
        name = parts[1] if not re.search(r"\d", parts[1]) else ""
        town = re.sub(r"[^A-Za-z\u0C00-\u0C7F ]", "", parts[2]).strip() if len(parts) > 2 else ""
        return name[:60], town[:60]
    if len(parts) >= 2 and not re.search(r"\d", parts[0]) and 1 <= len(parts[0].split()) <= 5:
        name = parts[0]
        if parts[1] and not re.search(r"\d", parts[1]):
            town = re.sub(r"[^A-Za-z\u0C00-\u0C7F ]", "", parts[1]).strip()
        # strip self-intro prefixes from name
        name = re.sub(r"^(?:i am|i'm|my name is|this is|na peru|nenu)\s+", "", name, flags=re.I).strip()
        name = re.split(r"\bfrom\b|\bnunchi\b|నుంచి", name, flags=re.I)[0].strip()
        town = re.sub(r"^(?:\bmy\b|\band\b|\bfrom\b|\bnunchi\b|నుంచి)\s*", "", town, flags=re.I).strip()
        return name[:60], town[:60]
    m = re.search(r"(?:i am|i'm|my name is|this is|na peru|nenu)\s+([A-Za-z\u0C00-\u0C7F. ]{2,30})", t, re.I)
    if m:
        name = re.split(r"\bfrom\b|\bnunchi\b|,", m.group(1), flags=re.I)[0].strip()
    m2 = re.search(r"(?:\bfrom\b|nunchi|నుంచి|నుండి)\s+([A-Za-z\u0C00-\u0C7F. ]{2,30})", t, re.I)
    if m2:
        town = re.split(r",|\bmy\b|\band\b", m2.group(1), flags=re.I)[0].strip()
    return name[:60], town[:60]


def find_or_create_lead(db, col, phone: str, channel: str, name: str = "",
                        town: str = "", branch_interest: str = "") -> Lead:
    lead = db.query(Lead).filter_by(college_id=col.id, phone=phone).first()
    if not lead:
        lead = Lead(college_id=col.id, phone=phone, name=name, town=town,
                    source="whatsapp" if channel == "whatsapp" else "website_chat",
                    created_at=utcnow())
        db.add(lead)
        db.flush()
        guardrails.log(col.id, "ai", "lead.captured",
                       {"lead_id": lead.id, "source": lead.source, "phone": phone}, db)
    if name and not lead.name:
        lead.name = name
    if town and not lead.town:
        lead.town = town
    if branch_interest and not lead.branch_interest:
        lead.branch_interest = branch_interest
    return lead


def assign_counselor(db, col) -> Staff | None:
    return (db.query(Staff).filter_by(college_id=col.id, role="counselor", active=True)
              .order_by(Staff.id).first())


def rescore(lead: Lead):
    s = SOURCE_SCORES.get(lead.source, 5)
    if lead.rank_or_marks:
        s += 10
    if lead.branch_interest:
        s += 10
    if lead.town:
        s += 5
    if lead.consent:
        s += 10
    lead.score = min(100, s)


def capture_details_if_present(db, col, conv, text, consent_given: bool) -> Lead | None:
    """Extract name/town/phone from free text; create/attach lead + consent."""
    phone = extract_phone(text)
    if not phone:
        return None
    name, town = parse_details(text)
    branch = ""
    t = text.lower()
    for hint_key, pat in BRANCH_HINTS.items():
        if re.search(pat, t):
            branch = hint_key
            break
    lead = find_or_create_lead(db, col, phone, conv.channel, name, town, branch)
    if conv.channel == "whatsapp" or consent_given or re.search(CONSENT_YES, t.strip()):
        if not lead.consent:
            lead.consent = True
            lead.consent_at = utcnow()
            guardrails.log(col.id, "ai", "consent.recorded",
                           {"lead_id": lead.id, "channel": conv.channel}, db)
    if lead.rank_or_marks == "" :
        mr = re.search(r"\b(\d{1,6})\s*(rank|ర్యాంక్)|(\d{1,3}(\.\d)?)\s*(cgpa|marks|మార్క్స్)", t)
        if mr:
            lead.rank_or_marks = mr.group(0)[:40]
    conv.lead_id = lead.id
    if lead.stage == "new":
        lead.stage = "ai_engaged"
    lead.last_inbound_at = utcnow()
    rescore(lead)
    schedule_sequence(db, col, lead)
    return lead


def schedule_sequence(db, col, lead: Lead):
    """Instant greeting (if consent) + day-2 nudge scheduled."""
    from .followups import fire_greeting
    if lead.consent and lead.seq_step == 0:
        fire_greeting(db, col, lead)
        lead.seq_step = 1                       # now inside the sequence (day-2 nudge next)
        lead.next_followup_at = utcnow() + timedelta(days=2)


def make_task(db, col, lead, kind, note):
    staff = assign_counselor(db, col)
    db.add(CounselorTask(college_id=col.id, lead_id=lead.id if lead else None,
                         staff_id=staff.id if staff else None, kind=kind, note=note,
                         due_at=utcnow()))
    guardrails.log(col.id, "ai", f"task.{kind}",
                   {"lead_id": lead.id if lead else None, "note": note[:80]}, db)


# ── main entry ───────────────────────────────────────────────────────────────
def _seats_pack(db, col, text) -> bool:
    """Seat AVAILABILITY questions. Rank-word messages belong to the rank advisor,
    so 'rank is 45000 — can I get a seat?' never lands here."""
    import re as _re
    t = " " + _re.sub(r"[^a-z0-9 ]", " ", (text or "").lower()) + " "
    if " rank " in t or "ranku" in t or "ర్యాంక్" in text:
        return False
    return any(w in t for w in ("seat", "seats", "సీట్", "kottha seat", "khaali seat"))


def _seats_reply(db, col, lang):
    """Honest seat-status answer: intake (approved) + joined-so-far (our own pipeline)
    + counselling reality + visit CTA. NEVER promises a seat."""
    from .db import Course, Lead
    courses = db.query(Course).filter_by(college_id=col.id).all()
    joined = (db.query(Lead).filter(Lead.college_id == col.id, Lead.stage == "joined").count())
    lines = []
    if courses:
        lines.append("Seat structure (approved intake, 2026-27):")
        lines += [f"• {c.name.split('—')[0].strip()} ({c.code}): intake {c.intake}/yr" for c in courses]
    lines.append(f"This season {joined} student(s) have already joined us — the rest fill through "
                 "EAPCET counselling (rank-based) and the management quota (token at the college office).")
    lines.append("Honest truth: seats move every day in counselling season — nobody outside the "
                 "admission office can promise you one. What I CAN do: book your campus visit now, "
                 "and our admission officer will confirm live status on the spot + guide the token process.")
    if lang == "te":
        lines.append("సీట్లు రోజూ మారుతూ ఉంటాయి — ప్రమోసం చేయను. వచ్చి క్యాంపస్ చూడండి, లైవ్ స్టేటస్ చెబుతారు.")
    guardrails.log(col.id, "ai", "seats.answered", {"joined": joined}, db)
    return "\n".join(lines), [{"title": "Approved intake table (CKP: courses)"}]


def _comparison_pack(db, col, text) -> bool:
    """Parent comparing colleges? (named a competitor OR generic compare words)"""
    import re as _re
    from .db import Competitor as _C
    t = " " + _re.sub(r"[^a-z0-9 ]", " ", (text or "").lower()) + " "
    for r in db.query(_C).filter_by(college_id=col.id).all():
        if r.name and (" " + r.name.lower() + " ") in t:
            return True
    return any(w in t for w in (" vs ", "vs ", "compare", "comparison", "better college",
                                "which college", "which is best", "best college",
                                "difference between", "పోల్చ", "మంచి కాలేజీ", "ఏ కాలేజీ"))


def _comparison_reply(db, col, text, lang):
    """Honest comparison: public numbers from the Owner-curated pack, never invented,
    credit where due, then pivot to a campus visit. If not in pack → honest refusal."""
    import re as _re
    from .db import Competitor as _C, PlacementStat as _P, Course as _Co
    t = " " + _re.sub(r"[^a-z0-9 ]", " ", (text or "").lower()) + " "
    rows = db.query(_C).filter_by(college_id=col.id).all()
    hits = [r for r in rows if r.name and (" " + r.name.lower() + " ") in t]
    our = col.short or col.name
    ps = db.query(_P).filter_by(college_id=col.id).all()
    our_plc = ""
    if ps:
        placed = [p.placed_pct or 0 for p in ps]
        top = max((p.top_lpa or 0) for p in ps)
        avg = max((p.avg_lpa or 0) for p in ps)
        our_plc = (f"placements ~{round(sum(placed) / len(placed))}% avg across branches, "
                   f"packages up to ₹{top} LPA (avg {avg} LPA)")
    fees = [c.convener_fee for c in db.query(_Co).filter_by(college_id=col.id).all() if c.convener_fee]
    our_fee = f"convener-quota fee from ₹{min(fees):,}/yr" if fees else \
        "transparent EAPCET-counselling fees (no donations)"
    if hits:
        m = hits[0]
        lines = [f"Honest comparison — public numbers only ({m.source_note}):",
                 f"• {m.name}" + (f" ({m.town}, {m.distance_km} km away)" if (m.town or m.distance_km) else "")
                 + f": fee {m.annual_fee or '—'}/yr · placements {m.placements_pct or '—'}"
                 + (f" · {m.closing_rank_note}" if m.closing_rank_note else ""),
                 f"• {our}: {our_plc or 'verified placement record in our brochure'} · {our_fee}."]
        if m.their_strength:
            lines.append(f"Credit where due — {m.name} is known for: {m.their_strength}.")
        if m.our_edge:
            lines.append(f"Families choose {our} for: {m.our_edge}.")
        lines.append("Rank maths and fee maths depend on YOUR EAMCET rank and budget — "
                     "the real test is a campus visit: hostels, labs, food, you verify everything yourself. "
                     "Shall I book a free visit? Or share your rank + town and I'll tell you honestly where you stand.")
        if lang == "te":
            lines.append("మీ ర్యాంక్ చెబితే నిజాయితీగా చెబుతాను — ఒకసారి క్యాంపస్ చూడండి, తర్వాత నిర్ణయం.")
        guardrails.log(col.id, "ai", "comparison.answered", {"about": m.name}, db)
        return "\n".join(lines), [{"title": f"Comparison Pack — {m.name} ({m.source_note})"}]
    lines = [f"I keep only verified, approved numbers for {our} — I will not guess another college's "
             "fees or placements, because wrong information can spoil a family's decision.",
             "For other colleges please rely on official sources (AICTE approvals list, your EAPCET rank card).",
             f"What I CAN say with proof about {our}: {our_plc or 'a verified placement record'} · {our_fee}.",
             "Seeing is believing — shall I book a free campus visit for you and your parents?"]
    if lang == "te":
        lines.append("వేరే కాలేజీ గురించి తప్పు సమాచారం చెప్పను — మా కాలేజీ గురించి మాత్రమే ధృవీకరించిన సమాచారం చెబుతాను.")
    guardrails.log(col.id, "ai", "comparison.honest_refusal", {}, db)
    return "\n".join(lines), [{"title": "Honest-answer policy — approved data only"}]


def handle_parent_message(db, college_id: int, text: str, channel: str = "web",
                          conversation_id: int | None = None,
                          consent_given: bool = False) -> dict:
    guardrails.check_kill_switch(college_id, db)
    col = db.query(College).get(college_id)
    lang = guardrails.detect_language(text)

    if conversation_id:
        conv = db.query(Conversation).get(conversation_id)
    else:
        conv = Conversation(college_id=college_id, channel=channel, language=lang)
        db.add(conv)
        db.flush()

    db.add(Message(conversation_id=conv.id, role="parent", text=text, created_at=utcnow()))
    lead = db.query(Lead).get(conv.lead_id) if conv.lead_id else None

    # 1. lead capture from free text (phone number etc.)
    captured = capture_details_if_present(db, col, conv, text, consent_given)
    if captured:
        lead = captured

    reply, citations, flagged, escalated, topic = "", [], False, False, _detect_topic(text)

    # 2. human request / complaint → handoff
    if guardrails.is_complaint(text):
        reply, escalated = _handoff_reply(lang, col), True
        make_task(db, col, lead, "handoff", "COMPLAINT in chat — call parent ASAP: " + text[:100])
        conv.status = "handed_off"
    elif guardrails.is_human_request(text):
        reply, escalated = _handoff_reply(lang, col), True
        make_task(db, col, lead, "call", "Parent asked for a human counselor: " + text[:100])

    # 2a. seat availability → approved intake + honesty + visit CTA (never promises)
    elif _seats_pack(db, col, text):
        reply, citations = _seats_reply(db, col, lang)
        topic = "seats"

    # 2b. college comparison → honest, sourced, visit-pivoting answer (never invent)
    elif _comparison_pack(db, col, text):
        reply, citations = _comparison_reply(db, col, text, lang)
        topic = "comparison"

    # 3. trap classes → honest refusal (never invent)
    else:
        trap = guardrails.detect_trap(text)
        if trap:
            reply, citations = _trap_reply(trap, col, lang)
            flagged = True
            make_task(db, col, lead, "call", f"Trap question ({trap}) — counselor follow-up advised")
        elif topic == "greeting" and not lead and len(text) < 30:
            reply = _greet(col, lang)
        elif topic and topic != "greeting":
            branch = _detect_branch(text, col.courses)
            builders = {
                "fees": lambda: _answer_fees(col, branch, lang),
                "hostel": lambda: _answer_hostel(col, lang),
                "transport": lambda: _answer_transport(col, lang),
                "placements": lambda: _answer_placements(col, lang),
                "courses": lambda: _answer_courses(col, lang),
                "cutoff": lambda: _answer_cutoff(col, branch, lang, text),
                "dates": lambda: _answer_dates(col, lang),
                "location": lambda: _answer_location(col, lang),
                "process": lambda: _answer_process(col, lang),
            }
            reply, citations = builders[topic]()
            if branch and lead and not lead.branch_interest:
                lead.branch_interest = branch.code
                rescore(lead)

        # 4. RAG fallback (tenant-first), grounded LLM if available
        else:
            if topic == "greeting" and (lead or captured):
                reply = (_greet(col, lang) + "\n" +
                         ("మీ నంబర్ సేవ్ అయ్యింది — మా కౌన్సిలర్ త్వరలో కాల్ చేస్తారు 📞"
                          if lang == "te" else
                          "Your number is saved — our counselor will call you shortly 📞"))
            elif topic == "greeting":
                reply = _greet(col, lang) + _ask_details(col, lang, lead)
            else:
                hits = retrieve(text, col.id, k=5, db=db, scope="tenant_first")
                if hits and (hits[0][2] >= 0.16 or hits[0][3] >= 0.22):
                    context_blocks, citations = [], []
                    for i, (c, fused, vec, lex) in enumerate(hits[:4], 1):
                        context_blocks.append(f"[{i}] {c.title} — {c.section}\n{c.content}")
                        if not any(x["title"] == c.title for x in citations):
                            citations.append(dict(n=len(citations) + 1, title=c.title,
                                                  source=f"KB: {c.section}"))
                    if llm_available():
                        system = (
                            "You are the admissions AI counselor for " + col.name + ". Answer ONLY from the "
                            "context. NEVER promise jobs, salaries, scholarships or predict ranks/cutoffs. "
                            "Refund questions: say the office will confirm. If context is insufficient, say you'll "
                            "have the counselor confirm. Reply in the SAME language as the question "
                            "(Telugu or English), max 90 words, warm and clear."
                        )
                        user = "Context:\n\n" + "\n\n".join(context_blocks) + f"\n\nQuestion: {text}"
                        reply = complete(system, user) or _extractive(text, hits)
                    else:
                        reply = _extractive(text, hits)
                else:
                    reply, escalated = _escape_reply(lang), True
                    make_task(db, col, lead, "verify", "AI couldn't ground an answer: " + text[:100])

    # 5. gentle lead-capture ask
    if not lead and not escalated and topic not in ("greeting",):
        reply += _ask_details(col, lang, lead)

    if lead:
        lead.last_inbound_at = utcnow()
        if lead.stage == "new":
            lead.stage = "ai_engaged"

    db.add(Message(conversation_id=conv.id, role="ai", text=reply,
                   citations=citations, flagged=flagged, created_at=utcnow()))
    guardrails.log(college_id, "ai", "chat.answered",
                   {"conversation_id": conv.id, "topic": topic, "trap": flagged,
                    "escalated": escalated, "lang": lang,
                    "lead_captured": bool(lead and lead.phone)}, db)
    db.commit()
    return dict(conversation_id=conv.id, reply=reply, language=lang,
                citations=citations, flagged=flagged, escalated=escalated,
                lead_captured=bool(lead and lead.phone))


def _extractive(query: str, hits) -> str:
    import re as _re
    from .rag import _tokens
    q_terms = set(_tokens(query))
    parts = []
    for rank, (c, fused, vec, lex) in enumerate(hits[:2], 1):
        sents = _re.split(r"(?<=[.!?]) ", c.content.strip())
        sents.sort(key=lambda s: len(q_terms & set(_tokens(s))), reverse=True)
        parts.append("• " + " ".join(sents[:2]) + f" [{rank}]")
    return "\n".join(parts)
