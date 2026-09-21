"""AI-generated college brochure (PDF) built live from the College Knowledge Pack."""
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

TEAL = colors.HexColor("#0D9488")
DEEP = colors.HexColor("#0F766E")
INK = colors.HexColor("#0B1F1C")
AMBER = colors.HexColor("#F59E0B")
LINE = colors.HexColor("#DCE9E6")
MUT = colors.HexColor("#5B7470")


def _styles():
    ss = getSampleStyleSheet()
    base = "Helvetica"
    return {
        "h1": ParagraphStyle("h1", parent=ss["Title"], fontName=base + "-Bold", fontSize=22,
                             textColor=colors.white, leading=26),
        "kick": ParagraphStyle("kick", fontName=base + "-Bold", fontSize=9, textColor=colors.HexColor("#FDE68A"),
                               leading=12, alignment=1),
        "h2": ParagraphStyle("h2", fontName=base + "-Bold", fontSize=13, textColor=DEEP,
                             spaceBefore=10, spaceAfter=4),
        "p": ParagraphStyle("p", fontName=base, fontSize=9.5, textColor=INK, leading=13.5),
        "mut": ParagraphStyle("mut", fontName=base, fontSize=8, textColor=MUT, leading=11),
        "th": ParagraphStyle("th", fontName=base + "-Bold", fontSize=8.5, textColor=colors.white, leading=11),
        "td": ParagraphStyle("td", fontName=base, fontSize=9, textColor=INK, leading=12),
    }


def generate(col, db) -> bytes:
    st = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=0, leftMargin=14 * mm,
                            rightMargin=14 * mm, bottomMargin=12 * mm,
                            title=f"{col.name} — Brochure", author="SeatSetu / Pooja Soft Solutions")
    E = []
    # ── colour header band ──
    hdr = Table([[Paragraph("ADMISSIONS " + "·" , st["kick"])],
                 [Paragraph(col.name or "College", st["h1"])],
                 [Paragraph(f"{col.city or ''}{', ' if col.city else ''}{col.district or ''} · "
                            f"EAPCET code: {col.eapcet_code or '—'} · AI Counselor: scan & ask",
                            ParagraphStyle("sub", fontName="Helvetica", fontSize=9.5,
                                           textColor=colors.HexColor("#ECFDF5"), alignment=1))]],
                colWidths=[182 * mm])
    hdr.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), TEAL),
        ("TOPPADDING", (0, 0), (-1, 0), 18), ("TOPPADDING", (0, 1), (-1, -1), 2),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 16),
        ("LEFTPADDING", (0, 0), (-1, -1), 14), ("RIGHTPADDING", (0, 0), (-1, -1), 14)]))
    E += [hdr, Spacer(1, 6 * mm)]

    if col.about:
        E += [Paragraph("About the college", st["h2"]), Paragraph(col.about, st["p"]), Spacer(1, 2 * mm)]
    if col.admission_process:
        E += [Paragraph("Admission process", st["h2"]), Paragraph(col.admission_process, st["p"]), Spacer(1, 2 * mm)]

    # ── courses & fees ──
    E.append(Paragraph("Courses, intake & fees (per year)", st["h2"]))
    rows = [[Paragraph("Course", st["th"]), Paragraph("Code", st["th"]), Paragraph("Intake", st["th"]),
             Paragraph("Convener quota", st["th"]), Paragraph("Management quota", st["th"])]]
    for c in col.courses:
        rows.append([Paragraph(c.name, st["td"]), Paragraph(c.code or "—", st["td"]),
                     Paragraph(str(c.intake or "—"), st["td"]),
                     Paragraph(f"₹{c.convener_fee:,}/yr" if c.convener_fee else "—", st["td"]),
                     Paragraph(f"₹{c.mgmt_fee:,}/yr" if c.mgmt_fee else "—", st["td"])])
    t = Table(rows, colWidths=[62 * mm, 22 * mm, 18 * mm, 40 * mm, 40 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DEEP),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAF9")]),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    E += [t, Paragraph("Fees as per the approved fee structure; convener-quota seats through EAPCET counseling. "
                       "JVD/reimbursement eligibility depends on government norms.", st["mut"]), Spacer(1, 3 * mm)]

    # ── facilities two-col ──
    from .db import Hostel, TransportRoute, PlacementStat, KeyDate
    hs = db.query(Hostel).filter_by(college_id=col.id).all()
    if hs:
        E.append(Paragraph("Hostel & mess", st["h2"]))
        for h in hs:
            E.append(Paragraph(f"• <b>{(h.for_whom or 'Hostel').title()}{' (AC)' if h.ac else ''}</b> — "
                               f"₹{h.fee_per_year:,}/yr · {h.facilities or ''}", st["p"]))
        E.append(Spacer(1, 2 * mm))
    routes = db.query(TransportRoute).filter_by(college_id=col.id).all()
    if routes:
        E.append(Paragraph("Bus transport", st["h2"]))
        E.append(Paragraph(" • ".join(f"{r.from_place or 'Route'} ({r.distance_km or 0:.0f} km) — ₹{r.fee_per_year or 0:,}/yr"
                                      for r in routes if r.from_place), st["p"]))
        E.append(Spacer(1, 2 * mm))
    ps = db.query(PlacementStat).filter_by(college_id=col.id).all()
    if ps:
        E.append(Paragraph("Placements", st["h2"]))
        prow = [[Paragraph("Year", st["th"]), Paragraph("Placed %", st["th"]),
                 Paragraph("Offers", st["th"]), Paragraph("Companies", st["th"]),
                 Paragraph("Avg package", st["th"]), Paragraph("Highest package", st["th"])]]
        for p in sorted(ps, key=lambda x: str(x.year), reverse=True)[:3]:
            prow.append([Paragraph(str(p.year), st["td"]),
                         Paragraph(f"{p.placed_pct:.0f}%" if p.placed_pct else "—", st["td"]),
                         Paragraph(str(p.offers or "—"), st["td"]),
                         Paragraph(str(p.companies or "—"), st["td"]),
                         Paragraph(f"₹{p.avg_lpa:g} LPA" if p.avg_lpa else "—", st["td"]),
                         Paragraph(f"₹{p.top_lpa:g} LPA" if p.top_lpa else "—", st["td"])])
        pt = Table(prow, colWidths=[22 * mm, 24 * mm, 22 * mm, 28 * mm, 40 * mm, 46 * mm])
        pt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), DEEP),
                                ("GRID", (0, 0), (-1, -1), 0.5, LINE),
                                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAF9")]),
                                ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        E += [pt, Spacer(1, 2 * mm)]
    kd = db.query(KeyDate).filter_by(college_id=col.id).all()
    if kd:
        E.append(Paragraph("Key dates", st["h2"]))
        E.append(Paragraph(" • ".join(f"{d.label}: {d.when_note}" for d in kd), st["p"]))

    # ── CTA + footer ──
    E += [Spacer(1, 5 * mm),
          Paragraph(f"<b>Talk to our AI counselor now — 60-second answers in Telugu or English:</b><br/>"
                    f"Ask on the college website chat, or call {col.phone or 'the office'}. "
                    f"Campus visits welcome Mon–Sat.", st["p"]),
          Spacer(1, 4 * mm)]
    foot = Table([[Paragraph("<b>SeatSetu</b> — Admissions · Accred · Careers &nbsp;|&nbsp; "
                             "A product by <b>Pooja Soft Solutions</b>, Ongole, AP · poojasoftsolutions.com · "
                             "📞 92471 05525 · 💬 75691 92211",
                             ParagraphStyle("f", fontName="Helvetica", fontSize=8, textColor=MUT, alignment=1,
                                            leading=11))]], colWidths=[182 * mm])
    foot.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 2, AMBER),
                              ("TOPPADDING", (0, 0), (-1, -1), 8)]))
    E.append(foot)
    doc.build(E)
    return buf.getvalue()
