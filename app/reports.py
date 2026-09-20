"""Report generators: admissions, careers, compliance, AQAR — JSON, CSV and printable HTML."""
import html as _html
from datetime import datetime, timedelta

from .db import (AuditLog, AttainmentRun, College, Conversation, CounselorTask, CourseReg,
                 EvidenceItem, FollowUpLog, Lead, MockInterview, QPaper)

STAGES = ["new", "ai_engaged", "contacted", "interested", "visit_booked", "visited",
          "applied", "seat_booked", "joined", "lost"]


def _since(days):
    return datetime.utcnow() - timedelta(days=days) if days else None


def admissions(db, col: College, days=None):
    q = db.query(Lead).filter(Lead.college_id == col.id)
    if _since(days):
        q = q.filter(Lead.created_at >= _since(days))
    leads = q.all()
    funnel = {st: 0 for st in STAGES}
    branches, sources = {}, {}
    for l in leads:
        funnel[l.stage if l.stage in STAGES else "new"] += 1
        branches[l.branch_interest or "—"] = branches.get(l.branch_interest or "—", 0) + 1
        sr = sources.setdefault(l.source or "website_chat", {"leads": 0, "visits": 0, "joined": 0})
        sr["leads"] += 1
        if l.stage in ("visit_booked", "visited", "applied", "seat_booked", "joined"):
            sr["visits"] += 1
        if l.stage == "joined":
            sr["joined"] += 1
    tasks_open = (db.query(CounselorTask)
                  .filter(CounselorTask.college_id == col.id, CounselorTask.done == False).count())
    due = (db.query(Lead).filter(Lead.college_id == col.id,
                                 Lead.next_followup_at != None,  # noqa: E711
                                 Lead.next_followup_at <= datetime.utcnow()).count())
    fu_sent = db.query(FollowUpLog).filter(FollowUpLog.college_id == col.id).count()
    fu_live = db.query(FollowUpLog).filter(FollowUpLog.college_id == col.id,
                                           FollowUpLog.mode == "live").count()
    return {"total_leads": len(leads), "funnel": funnel, "branches": branches,
            "sources": sources, "tasks_open": tasks_open, "followups_due": due,
            "followups_sent": fu_sent, "followups_live": fu_live,
            "period_days": days or "all"}


def careers_rep(db, col: College, days=None):
    q = db.query(MockInterview).filter(MockInterview.college_id == col.id)
    if _since(days):
        q = q.filter(MockInterview.created_at >= _since(days))
    rows = q.order_by(MockInterview.id.desc()).all()
    by_branch, weak = {}, []
    scores = [m.overall for m in rows if m.overall]
    for m in rows:
        b = m.branch or "—"
        a = by_branch.setdefault(b, {"n": 0, "sum": 0.0})
        a["n"] += 1
        a["sum"] += m.overall or 0
        if (m.overall or 0) < 2.5:
            weak.append({"student": m.student, "branch": b, "score": m.overall, "at": str(m.created_at)[:16]})
    for b in by_branch:
        by_branch[b] = {"n": by_branch[b]["n"], "avg": round(by_branch[b]["sum"] / by_branch[b]["n"], 2)}
    return {"interviews": len(rows), "avg": round(sum(scores) / len(scores), 2) if scores else 0,
            "by_branch": by_branch, "below_2_5": weak[:15]}


def compliance(db, col: College):
    leads = db.query(Lead).filter(Lead.college_id == col.id).all()
    granted = sum(1 for l in leads if l.consent)
    audits = db.query(AuditLog).filter(AuditLog.college_id == col.id).count()
    last = (db.query(AuditLog).filter(AuditLog.college_id == col.id)
              .order_by(AuditLog.id.desc()).first())
    return {"consents_total": len(leads), "consents_granted": granted,
            "kill_switch": bool(col.kill_switch), "audit_events": audits,
            "last_audit_at": str(last.created_at)[:16] if last else None}


def accred_summary(db, col: College):
    ev = db.query(EvidenceItem).filter(EvidenceItem.college_id == col.id).all()
    done = sum(1 for e in ev if e.status == "collected")
    regs = db.query(CourseReg).filter(CourseReg.college_id == col.id).count()
    runs = (db.query(AttainmentRun).join(CourseReg, AttainmentRun.reg_id == CourseReg.id)
              .filter(CourseReg.college_id == col.id).count())
    papers = db.query(QPaper).filter(QPaper.college_id == col.id).count()
    pct = round(100 * done / len(ev)) if ev else 0
    return {"evidence_total": len(ev), "evidence_collected": done, "readiness_pct": pct,
            "course_regs": regs, "attainment_runs": runs, "question_papers": papers}


def management(db, col: College, days=None):
    return {"college": {"id": col.id, "name": col.name, "short": col.short, "city": col.city},
            "generated_at": datetime.utcnow().strftime("%d %b %Y %H:%M"),
            "admissions": admissions(db, col, days), "careers": careers_rep(db, col, days),
            "compliance": compliance(db, col), "accred": accred_summary(db, col)}


def _e(x):
    return _html.escape(str(x if x is not None else "—"))


def leads_csv(db, col: College) -> str:
    rows = db.query(Lead).filter(Lead.college_id == col.id).order_by(Lead.id).all()
    out = ["id,name,phone,town,source,campaign,stage,branch,rank_or_marks,consent,score,next_followup_at,created_at"]
    for l in rows:
        out.append(",".join([str(l.id), f'"{_e(l.name)}"', f'"{_e(l.phone)}"', f'"{_e(l.town)}"',
                             l.source or "", f'"{_e(l.campaign)}"', l.stage or "",
                             f'"{_e(l.branch_interest)}"', f'"{_e(l.rank_or_marks)}"',
                             "yes" if l.consent else "no", str(l.score or 0),
                             str(l.next_followup_at or ""), str(l.created_at or "")[:16]]))
    return "\n".join(out)


def careers_csv(db, col: College) -> str:
    rows = (db.query(MockInterview).filter(MockInterview.college_id == col.id)
              .order_by(MockInterview.id).all())
    out = ["id,student,branch,overall,strengths,gaps,at"]
    for m in rows:
        out.append(",".join([str(m.id), f'"{_e(m.student)}"', f'"{_e(m.branch)}"',
                             str(m.overall or 0), f'"{_e(m.strengths)}"', f'"{_e(m.gaps)}"',
                             str(m.created_at or "")[:16]]))
    return "\n".join(out)


def render_html(db, col: College, days=None) -> str:
    d = management(db, col, days)
    a, c, cp, ac = d["admissions"], d["careers"], d["compliance"], d["accred"]
    mx = max(a["funnel"].values() or [0]) or 1
    conv = round(100 * a["funnel"].get("joined", 0) / a["total_leads"], 1) if a["total_leads"] else 0
    bars = "".join(f'<div class="fr"><span>{_e(s)}</span><div class="fb" style="width:{max(3, v / mx * 92)}%">'
                   f'{v}</div></div>' for s, v in a["funnel"].items())
    srcs = "".join(f"<tr><td>{_e(k)}</td><td>{v['leads']}</td><td>{v['visits']}</td><td><b>{v['joined']}</b></td></tr>"
                   for k, v in sorted(a["sources"].items(), key=lambda x: -x[1]["leads"]))
    brs = " · ".join(f"{_e(k)} ({v})" for k, v in sorted(a["branches"].items(), key=lambda x: -x[1])[:8])
    cbb = "".join(f"<tr><td>{_e(k)}</td><td>{v['n']}</td><td><b>{v['avg']}</b>/5</td></tr>"
                  for k, v in c["by_branch"].items())
    weak = ("<ul>" + "".join(f"<li>{_e(w['student'])} ({_e(w['branch'])}) — {_e(w['score'])}/5</li>"
                             for w in c["below_2_5"]) + "</ul>") if c["below_2_5"] else "<p>None 🎉</p>"
    kpis = [("Total leads", a["total_leads"]), ("Joined", a["funnel"].get("joined", 0)),
            ("Conversion %", f"{conv}%"), ("Follow-ups due", a["followups_due"]),
            ("Interviews", c["interviews"]), ("Avg score", f"{c['avg']}/5"),
            ("AQAR readiness", f"{ac['readiness_pct']}%"), ("AI status", "PAUSED" if cp["kill_switch"] else "Running")]
    kh = "".join(f'<div class="k"><b>{_e(v)}</b><span>{_e(k)}</span></div>' for k, v in kpis)
    period = f"last {days} days" if days else "full season"
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<title>Management Report — {_e(col.name)}</title><style>
body{{font-family:system-ui,sans-serif;color:#12332E;background:#F7FAF9;margin:0;padding:26px}}
.wrap{{max-width:900px;margin:0 auto}}
.hd{{background:linear-gradient(135deg,#0D9488,#0F766E 60%,#134E4A);color:#fff;border-radius:14px;padding:22px 26px}}
.hd img{{height:40px;background:#fff;padding:4px 8px;border-radius:7px}}
.hd h1{{font-size:21px;margin:12px 0 2px}}.hd p{{margin:0;color:#ECFDF5;font-size:13.5px}}
.krow{{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}}
.k{{background:#fff;border:1px solid #DCE9E6;border-radius:11px;padding:12px 16px;flex:1;min-width:150px;text-align:center}}
.k b{{font-size:22px;color:#0F766E;display:block}}.k span{{font-size:11.5px;color:#5B7470}}
h2{{font-size:15.5px;color:#0B1F1C;border-left:4px solid #F59E0B;padding-left:10px;margin:22px 0 8px}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:9px;overflow:hidden}}
th{{background:#134E4A;color:#fff;text-align:left;padding:8px 12px;font-size:12px}}
td{{padding:7px 12px;border-top:1px solid #DCE9E6;font-size:13px}}
.fr{{display:flex;align-items:center;gap:10px;margin:5px 0}}
.fr span{{width:110px;font-size:12.5px;color:#5B7470}}
.fb{{background:linear-gradient(90deg,#0D9488,#2DD4BF);border-radius:5px;color:#fff;font-size:12px;
padding:3px 8px;min-width:30px;text-align:right}}
.box{{background:#fff;border:1px solid #DCE9E6;border-radius:11px;padding:14px 18px}}
.two{{display:flex;gap:14px;flex-wrap:wrap}}.two>div{{flex:1;min-width:280px}}
.foot{{margin-top:20px;border-top:3px solid #F59E0B;padding-top:10px;text-align:center;color:#5B7470;font-size:12px}}
button{{background:#0D9488;color:#fff;border:0;border-radius:9px;padding:10px 18px;font-size:14px;
font-weight:600;cursor:pointer;margin-bottom:14px}}
@media print{{body{{background:#fff;padding:0}}button{{display:none}}.wrap{{max-width:none}}}}
</style></head><body><div class="wrap">
<button onclick="window.print()">🖨️ Print / Save as PDF</button>
<div class="hd"><img src="/static/logo.png" alt="SeatSetu">
<h1>{_e(col.name)} — Management Report</h1><p>Period: {period} · Generated {_e(d['generated_at'])} · Powered by Pooja Soft Solutions</p></div>
<div class="krow">{kh}</div>
<h2>Admissions funnel</h2><div class="box">{bars}</div>
<h2>Source performance</h2><table><tr><th>Source</th><th>Leads</th><th>Visit+</th><th>Joined</th></tr>{srcs}</table>
<div class="two"><div><h2>Branch interest</h2><div class="box">{brs}</div></div>
<div><h2>Placement training</h2><table><tr><th>Branch</th><th>Interviews</th><th>Avg</th></tr>{cbb}</table>
<p style="font-size:12.5px;color:#5B7470">Below 2.5 (needs coaching):</p>{weak}</div></div>
<h2>Compliance & AQAR</h2><div class="box">Consent: <b>{cp['consents_granted']}/{cp['consents_total']}</b> granted ·
Audit events: <b>{cp['audit_events']}</b> (last {_e(cp['last_audit_at'])}) · AI kill switch: <b>{'ON — paused' if cp['kill_switch'] else 'off'}</b><br>
AQAR evidence: <b>{ac['evidence_collected']}/{ac['evidence_total']}</b> collected (readiness {ac['readiness_pct']}%) ·
Attainment runs: <b>{ac['attainment_runs']}</b> · Question papers: <b>{ac['question_papers']}</b> ·
WhatsApp follow-ups sent: <b>{a['followups_sent']}</b> ({a['followups_live']} live)</div>
<div class="foot"><b>SeatSetu</b> — Admissions · Accred · Careers · A product by <b>Pooja Soft Solutions</b>, Ongole · AP<br>
📞 92471 05525 · 💬 WhatsApp 75691 92211 · info@poojasoftsolutions.com</div></div></body></html>"""
