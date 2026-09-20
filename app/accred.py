"""SeatSetu Accred — the NAAC/AQAR/OBE engine.

Powers:
  • Excel/CSV marks parsing with CO-column auto-detection
  • CO attainment (per-student % → 0-3 levels → class average)
  • CO→PO mapped PO/PSO attainment + gap analysis with action suggestions
  • AQAR (DCF-2025-era) evidence checklist across the 7 NAAC criteria
  • Bloom-mapped question-paper generator (structure + stems + CO tags)

All math is deterministic and explainable — every number in the report can be
traced back to the marks sheet (no LLM involvement where accuracy matters).
"""
import csv
import io
import re

# ── OBE configuration ────────────────────────────────────────────────────────
LEVEL_THRESHOLDS = [(60, 3), (50, 2), (40, 1)]   # % → level; below 40 → 0
TARGET_DEFAULT = 2.0

BLOOM_VERBS = {
    1: ["Define", "List", "State", "Recall", "Identify"],
    2: ["Explain", "Describe", "Summarize", "Illustrate", "Discuss"],
    3: ["Apply", "Solve", "Compute", "Demonstrate", "Use"],
    4: ["Analyze", "Compare", "Differentiate", "Examine", "Classify"],
    5: ["Evaluate", "Justify", "Critique", "Assess", "Rate"],
    6: ["Design", "Construct", "Propose", "Formulate", "Create"],
}

# AQAR/SSR checklist (7 criteria, DCF-2025-era key metrics as practical items)
AQAR_ITEMS = [
    ("1.1.1", "Curriculum adheres to CCFUGP/FYUP — evidence of multidisciplinary courses"),
    ("1.2.1", "Certificate/value-added courses offered & students enrolled"),
    ("1.3.2", "Experiential learning: internships/projects records"),
    ("2.1.1", "Enrollment percentage data (ADR) with admission receipts"),
    ("2.3.1", "Student-centric methods: ICT-enabled teaching evidence"),
    ("2.6.3", "CO-PO attainment & pass percentage (OBE documentation)"),
    ("3.1.2", "Funded research projects/grants (or seed-money minutes)"),
    ("3.3.2", "Papers published per teacher (Scopus/WoS list)"),
    ("3.4.2", "MoUs with industry/institutions — signed copies"),
    ("4.1.3", "Lab/infrastructure augmentation: purchase bills + photos"),
    ("4.3.1", "ICT facilities: Wi-Fi/LMS usage registers"),
    ("5.1.2", "Skill development: placement/training records, offers"),
    ("5.3.1", "Sports/cultural achievements of students"),
    ("6.2.2", "Institutional strategy/ decentralization: organogram + minutes"),
    ("6.3.2", "Faculty welfare & FDP attendance certificates"),
    ("6.5.2", "IQAC minutes, AQAR of previous year, action-taken reports"),
    ("7.1.1", "Green campus initiatives: energy audit, plantation photos"),
    ("7.2.1", "Best practices: two documented institutional best practices"),
]


# ── Marks parsing ────────────────────────────────────────────────────────────
def _headers_of(rows):
    for i, r in enumerate(rows[:10]):
        cells = [str(c).strip() if c is not None else "" for c in r]
        if sum(1 for c in cells if c) >= 3:
            return i, cells
    return 0, []


def _co_columns(headers):
    r"""Returns {col_index: co_no} using /CO\s*[-_ ]?(\d+)/ patterns (case-insens)."""
    out = {}
    for idx, h in enumerate(headers):
        m = re.search(r"co\s*[-_ .]?(\d+)", str(h).lower())
        if m:
            out[idx] = int(m.group(1))
    return out


def parse_marks(filename: str, content: bytes):
    """Parses a marks file → {students:[{roll, name, cos:{co: pct}}], notes:[]}.
    Expects a header row containing Roll/Regd + one column per CO (CO1..COn).
    Values per CO column are marks obtained; a parallel 'MAX' row (optional)
    or per-CO max in header ('CO1/20') sets the denominator."""
    rows = []
    notes = []
    if filename.lower().endswith(".csv"):
        text = content.decode("utf-8-sig", errors="replace")
        rows = [r for r in csv.reader(io.StringIO(text)) if any(x.strip() for x in r)]
    elif filename.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(content), data_only=True, read_only=True)
        ws = wb.active
        rows = [[c for c in row] for row in ws.iter_rows(values_only=True)]
    else:
        raise ValueError("Unsupported file (use .xlsx or .csv)")

    hdr_i, headers = _headers_of(rows)
    co_cols = _co_columns(headers)
    if not co_cols:
        raise ValueError("No CO columns found. Header must contain CO1, CO2, … columns.")

    # per-CO max: from header like "CO1 (20)" or "CO1/20", else 10 default, or MAX row
    co_max = {}
    for idx, co in co_cols.items():
        m = re.search(r"[/(]\s*(\d+)", str(headers[idx]))
        co_max[co] = int(m.group(1)) if m else None
    roll_col = name_col = None
    for idx, h in enumerate(headers):
        hl = str(h).lower()
        if roll_col is None and re.search(r"roll|regd|reg\.|admission|pin", hl):
            roll_col = idx
        if name_col is None and re.search(r"name|student", hl) and not re.search(r"co\d", hl):
            name_col = idx
    # MAX row detection (first data row containing 'max')
    start = hdr_i + 1
    first = [str(c).strip().lower() if c is not None else "" for c in rows[start]] if start < len(rows) else []
    if any("max" in c for c in first):
        for idx, co in co_cols.items():
            try:
                co_max[co] = int(float(rows[start][idx]))
            except (TypeError, ValueError, IndexError):
                pass
        start += 1

    students = []
    for r in rows[start:]:
        vals = list(r) + [None] * (len(headers) - len(r))
        roll = str(vals[roll_col]).strip() if roll_col is not None and vals[roll_col] is not None else ""
        if not roll or not re.search(r"\d", roll):
            continue
        name = str(vals[name_col]).strip() if name_col is not None and vals[name_col] is not None else ""
        cos = {}
        for idx, co in co_cols.items():
            try:
                got = float(vals[idx])
            except (TypeError, ValueError):
                continue
            mx = co_max[co] or 10
            if mx <= 0:
                continue
            cos[co] = round(100.0 * min(got, mx) / mx, 1)
        if cos:
            students.append(dict(roll=roll, name=name, cos=cos))
    notes.append(f"Parsed {len(students)} students · CO columns: "
                 f"{sorted(co_cols.values())} · max marks: {co_max}")
    return students, notes


# ── Attainment math ──────────────────────────────────────────────────────────
def _level(pct: float) -> int:
    for floor, lvl in LEVEL_THRESHOLDS:
        if pct >= floor:
            return lvl
    return 0


def compute_attainment(reg, students) -> dict:
    cos = reg.cos or []
    co_ids = sorted({c["no"] for c in cos} | {k for s in students for k in s["cos"]})
    co_attain = {}
    for co in co_ids:
        pcts = [s["cos"][co] for s in students if co in s["cos"]]
        if not pcts:
            co_attain[str(co)] = dict(avg_pct=None, level=0, students=0, above_60=0)
            continue
        avg = sum(pcts) / len(pcts)
        levels = [_level(p) for p in pcts]
        co_attain[str(co)] = dict(
            avg_pct=round(avg, 1), level=round(sum(levels) / len(levels), 2),
            students=len(pcts), above_60=sum(1 for p in pcts if p >= 60),
        )
    # CO→PO mapping → direct PO attainment (weighted by mapping strength)
    mapping = reg.co_po_map or {}
    po_scores, po_weights = {}, {}
    for c in cos:
        co = str(c["no"])
        att = co_attain.get(co, {}).get("level", 0) or 0
        for po, strength in (mapping.get(co) or {}).items():
            po_scores[po] = po_scores.get(po, 0.0) + att * strength
            po_weights[po] = po_weights.get(po, 0.0) + strength
    po_direct = {po: round(po_scores[po] / po_weights[po], 2)
                 for po in po_scores if po_weights[po]}
    target = reg.target or TARGET_DEFAULT
    gaps = []
    for po in sorted(po_direct, key=lambda x: int(re.sub(r"\D", "", x) or 99)):
        val = po_direct[po]
        if val < target:
            gap = round(target - val, 2)
            gaps.append(dict(po=po, attained=val, gap=gap, action=_action_for(gap)))
    return dict(course=reg.course_name, code=reg.code, academic_year=reg.academic_year,
                students=len(students), target=target, co_attain=co_attain,
                po_direct=po_direct, gaps=gaps)


def _action_for(gap: float) -> str:
    if gap >= 1.0:
        return ("Urgent: remedial classes + re-test of internal marks; mentor weak students "
                "individually; review question paper difficulty with Bloom mix.")
    if gap >= 0.5:
        return "Add tutorial hours, assignments targeting weak COs, and one revision test before end-sem."
    return "Minor: bridge the gap with extra problem-solving sessions and assignments."


def blend_indirect(report: dict, po_indirect: dict, weight_direct: float = 0.8) -> dict:
    """Final PO attainment = direct (mapped) + indirect (survey) weighted blend."""
    final = {}
    for po, direct in report["po_direct"].items():
        ind = po_indirect.get(po)
        final[po] = round(direct * weight_direct + ind * (1 - weight_direct), 2) if ind is not None else direct
    out = dict(report)
    out["po_final"] = final
    out["blend"] = f"{round(weight_direct*100)}% direct + {round((1-weight_direct)*100)}% indirect"
    return out


# ── Question-paper generator ─────────────────────────────────────────────────
def generate_qpaper(reg, sections) -> dict:
    """sections: [{name:'A', count:10, marks:2, blooms:[1,2]}, …]
    Produces Bloom+CO tagged question stems (college fills discipline content)."""
    cos = sorted(reg.cos or [], key=lambda c: c["no"])
    if not cos:
        raise ValueError("Course has no CO definitions")
    paper, total, ci = [], 0, 0
    for sec in sections:
        qs = []
        for i in range(sec["count"]):
            co = cos[ci % len(cos)]
            ci += 1
            bloom = sec["blooms"][i % len(sec["blooms"])]
            verb = BLOOM_VERBS[bloom][i % len(BLOOM_VERBS[bloom])]
            unit = f"U{min(1 + (i * len(cos) + ci) % 5, 5)}"
            qs.append(dict(no=i + 1, co=co["no"], bloom=bloom, unit=unit,
                           stem=f"{verb} {co['desc'][:70]}" + (
                               " with an example." if bloom in (2, 3) else ".")))
        total += sec["count"] * sec["marks"]
        paper.append(dict(section=sec["name"], marks_each=sec["marks"],
                          count=sec["count"], blooms=sec["blooms"], questions=qs))
    header = (f"{reg.course_name} ({reg.code}) · {reg.semester} · {reg.academic_year}\n"
              f"Time: 3 hours · Max marks: {total} · Bloom-mapped & CO-tagged")
    return dict(header=header, total_marks=total, sections=paper)


# ── AQAR helpers ─────────────────────────────────────────────────────────────
def aqar_status(evidence_rows) -> dict:
    by_criterion = {}
    for e in evidence_rows:
        by_criterion.setdefault(e.criterion, []).append(e)
    items = []
    for crit, desc in AQAR_ITEMS:
        rows = by_criterion.get(crit, [])
        collected = sum(1 for r in rows if r.status == "collected")
        items.append(dict(criterion=crit, desc=desc, collected=collected,
                          pending=sum(1 for r in rows if r.status == "pending"),
                          status="collected" if rows and all(r.status != "pending" for r in rows)
                          else ("partial" if collected else "pending")))
    covered = sum(1 for i in items if i["status"] == "collected")
    return dict(items=items, readiness=round(100 * covered / len(items)),
                total_items=len(items))
