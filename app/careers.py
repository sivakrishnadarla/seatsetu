"""SeatSetu Careers — the Placement Copilot.

AI mock interviews for tier-3 students (Telugu-English answers welcome):
HR + branch-technical + scenario questions, heuristic scoring with STAR
feedback that upgrades to LLM scoring when an API key exists. Every finished
interview is a dated pre-placement training record → NAAC 5.1.2 evidence CSV.
"""
import csv
import io

# ── Question bank ────────────────────────────────────────────────────────────
HR = [
    dict(type="HR", q="Tell me about yourself (Telugu-English ok).",
         keywords=["college", "branch", "year", "studying", "project", "interest", "goal", "built", "learning", "skills"],
         tip="Structure: name → branch/college → one strength with example → career goal. Keep it 60-90 seconds."),
    dict(type="HR", q="What are your strengths? Give one real example.",
         keywords=["strength", "team", "hard work", "example", "project", "leadership", "time"],
         tip="One strength + one concrete example (project/event) beats five adjectives."),
    dict(type="HR", q="Why should we hire you?",
         keywords=["skills", "learn", "project", "company", "fit", "training", "certified"],
         tip="Connect YOUR skills to the ROLE: 'I built X, your role needs Y'."),
    dict(type="HR", q="Where do you see yourself in 5 years?",
         keywords=["grow", "learn", "senior", "team", "company", "expert", "role"],
         tip="Show ambition anchored to the company: learn → contribute → lead."),
    dict(type="HR", q="Are you willing to relocate? How do you handle pressure?",
         keywords=["yes", "relocate", "pressure", "deadline", "plan", "calm", "prioritize"],
         tip="Direct answer + one example of handling exam/project pressure."),
]

TECH = {
    "CSE": [
        dict(type="Technical", q="Explain the difference between a list/array and a linked list. When would you use which?",
             keywords=["memory", "index", "insert", "pointer", "node", "dynamic", "o(1)"],
             tip="Mention memory layout, insertion cost, and one use-case each."),
        dict(type="Technical", q="What is normalization in DBMS? Why do we need it?",
             keywords=["redundancy", "1nf", "2nf", "3nf", "duplicate", "consistency", "keys"],
             tip="Define it, name 1NF/2NF/3NF, and give the redundancy/anomaly reason."),
        dict(type="Technical", q="Walk me through a project you built. What was hardest?",
             keywords=["project", "built", "team", "problem", "solved", "learned", "database", "code"],
             tip="STAR format: Situation → Task → Action → Result (with numbers if possible)."),
        dict(type="Technical", q="What happens when you type a URL and press Enter?",
             keywords=["dns", "server", "request", "browser", "http", "response", "ip"],
             tip="DNS → request → server → response → render. Even a short ordered answer works."),
    ],
    "ECE": [
        dict(type="Technical", q="What is the difference between microprocessor and microcontroller?",
             keywords=["memory", "embedded", "cpu", "ram", "rom", "system", "peripheral"],
             tip="Microcontroller = CPU+memory+peripherals on one chip; give one application."),
        dict(type="Technical", q="Explain Ohm's law and where you used it in a lab.",
             keywords=["voltage", "current", "resistance", "circuit", "experiment", "verification"],
             tip="State the law (V=IR) + a real lab usage with values."),
        dict(type="Technical", q="What is a multiplexer? Give one real use.",
             keywords=["inputs", "select", "channel", "data", "lines", "switch"],
             tip="n select lines → 2^n inputs; use: data routing/sharing one line."),
        dict(type="Technical", q="Explain your favorite lab experiment end-to-end.",
             keywords=["aim", "apparatus", "procedure", "result", "graph", "learned"],
             tip="Aim → apparatus → procedure → result. Speaking in order shows rigor."),
    ],
    "MECH": [
        dict(type="Technical", q="What is the difference between 2-stroke and 4-stroke engines?",
             keywords=["cycle", "power", "fuel", "stroke", "efficiency", "piston"],
             tip="Power-stroke frequency + efficiency + one application each."),
        dict(type="Technical", q="Explain Newton's three laws with a workshop example.",
             keywords=["inertia", "force", "reaction", "motion", "machine", "mass"],
             tip="One crisp example per law (lathe, hammering, jet)."),
        dict(type="Technical", q="What is CAD? Which tools did you practice?",
             keywords=["design", "software", "autocad", "solidworks", "modeling", "drawing"],
             tip="Name the tools you actually touched + what you modeled."),
        dict(type="Technical", q="Why did you choose mechanical engineering?",
             keywords=["interest", "machines", "core", "industry", "childhood", "curious"],
             tip="A genuine story + where you want to take it."),
    ],
    "CIVIL": [
        dict(type="Technical", q="What is the water-cement ratio and why does it matter?",
             keywords=["strength", "concrete", "mix", "workability", "curing"],
             tip="More water = weaker concrete; mention workability vs strength trade-off."),
        dict(type="Technical", q="Explain types of foundations and where each is used.",
             keywords=["shallow", "deep", "pile", "footing", "soil", "load"],
             tip="Shallow vs deep + soil/load decides; one structure example each."),
        dict(type="Technical", q="What is a survey? Which instruments did you use in field work?",
             keywords=["theodolite", "level", "chain", "map", "measurement", "total station"],
             tip="Name instruments you actually handled + one survey camp story."),
        dict(type="Technical", q="How does your branch help infrastructure growth in Andhra Pradesh?",
             keywords=["roads", "ports", "capital", "construction", "projects", "state"],
             tip="Tie local development (ports/highways/capital city) to your career."),
    ],
}
TECH["CSE-AIML"] = TECH["CSE"]

SCENARIO = dict(type="Scenario", q="Your teammate is not completing their part before the deadline. What do you do?",
                keywords=["talk", "help", "split", "deadline", "team", "inform", "support", "plan"],
                tip="Communicate first, offer help, redistribute, escalate only if needed — show maturity.")


def build_interview(branch: str, role: str) -> list[dict]:
    branch = (branch or "CSE").upper()
    bank = TECH.get(branch, TECH["CSE"])
    tech = bank[:3] if role.lower().startswith("software") or branch in TECH else bank[:3]
    if role.lower().startswith("core"):
        tech = bank[:3]
    qs = [HR[0], HR[2]] + tech[:2] + [dict(SCENARIO)]
    if len(tech) >= 3:
        qs = [HR[0], HR[2]] + tech[:3] + [dict(SCENARIO)]
    out = []
    for i, q in enumerate(qs, 1):
        d = dict(q)
        d["no"], d["answer"], d["score"], d["tips"] = i, "", None, None
        out.append(d)
    return out


# ── Scoring ──────────────────────────────────────────────────────────────────
STAR_WORDS = {"situation", "task", "action", "result", "project", "team", "example",
              "implemented", "built", "led", "achieved", "learned"}
FILLER = {"nothing", "dont know", "no idea", "dunno", "telidu", "teliyadu"}


def score_answer(ans: str, item: dict) -> tuple[float, str]:
    a = ans.strip().lower()
    if len(a) < 4 or any(f in a for f in FILLER):
        return 1.0, ("Answer too short — even 3 honest sentences score. "
                     + item["tip"])
    import re as _re
    words = set(_re.findall(r"[a-z]+", a))   # punctuation-free tokens
    kws = item.get("keywords", [])
    hit = sum(1 for k in kws if k in a)          # substring match on full text
    kw_score = hit / max(1, len(kws))
    n_words = len(a.split())
    length_score = min(1.0, n_words / 35)
    star = len(STAR_WORDS & words) > 0
    numbers = any(ch.isdigit() for ch in a)
    # Substance-first calibration: a full, structured answer with partial keyword
    # coverage should land ~3.5; keywords add precision, not gatekeep.
    score = (1.0 + 1.4 * kw_score + 1.3 * length_score
             + (0.5 if star else 0) + (0.4 if numbers else 0)
             + (0.3 if n_words >= 60 else 0))
    score = round(min(5.0, score), 1)
    tips = []
    if kw_score < 0.25:
        tips.append("Cover the core concepts: " + ", ".join(kws[:4]) + ".")
    if len(a.split()) < 30:
        tips.append("Add a concrete example (STAR: situation→action→result).")
    if not numbers:
        tips.append("Quantify something — team size, marks, time saved, users.")
    if star and kw_score >= 0.25:
        tips.append("Good structure! Practice saying it in 60 seconds.")
    return score, " ".join(tips) or "Solid answer."


def overall_score(questions: list[dict]) -> float:
    scores = [q["score"] for q in questions if q.get("score")]
    return round(sum(scores) / len(scores), 1) if scores else 0.0


# ── NAAC evidence export ─────────────────────────────────────────────────────
def evidence_csv(rows) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["# SeatSetu Careers — Pre-placement training evidence (NAAC Criterion 5.1.2)"])
    w.writerow(["Date", "Student", "Roll", "Branch", "Role", "Overall /5",
                "Q scores", "Improvement notes"])
    for m in rows:
        qsc = " | ".join(f"Q{q['no']}:{q.get('score') or '-'}" for q in m.questions)
        notes = " ;; ".join(f"Q{q['no']}: {q.get('tips')}" for q in m.questions if q.get("tips"))[:300]
        w.writerow([m.created_at.strftime("%Y-%m-%d"), m.student_name, m.roll, m.branch,
                    m.role, m.overall, qsc, notes])
    return buf.getvalue().encode("utf-8-sig")
