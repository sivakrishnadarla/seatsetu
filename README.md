# 🎓 SeatSetu — Admissions · Accreditation · Careers OS (v0.3)
### *Every seat. Filled.*
### *Every seat. Filled.*

**SeatSetu** = the bridge between empty seats and eager students. Module A (**SeatSetu Admissions**): parents chat in
**Telugu or English** on the college website (and WhatsApp), the AI answers
**only from the college's approved facts** (fees, hostel, transport,
placements, dates — never invents, never promises jobs or scholarships),
captures every lead, runs bilingual WhatsApp follow-up sequences, and gives
the management a live funnel with **cost-per-joined-student** attribution —
all behind DPDP consent records, a kill switch and an immutable audit log.

**Runs at ₹0/month** (Vercel Hobby + Neon free Postgres + Gemini/GitHub free
LLM tier). Works with **zero API keys** in demo mode — WhatsApp sends are
logged, not sent; a deterministic bilingual brain answers everything.

---

## Quickstart

```bash
cd SeatSetu
pip install -r requirements.txt
cp .env.example .env            # optional: keys later
uvicorn app.main:app --host 0.0.0.0 --port 8000
# open http://localhost:8000  (dashboard)  ·  /widget/1 (the parent chat)
```

A fully-seeded demo college (**RIT Kadapa** — fictional) ships with 5 courses,
fees, hostels, bus routes, approved placement stats, 8 leads across the
pipeline, tasks, and a sample Telugu conversation.

## The 3-minute demo (principal or investor)

1. **Dashboard → Website Widget** → open the live widget.
2. Chat as a parent: `CSE fee enta? hostel unda?` → instant Telugu answer with
   **exact fees from the Knowledge Pack**, JVD guidance with the
   "office will verify" safety suffix, and citations under the bubble.
3. Ask `100% placement guarantee unda?` → honest refusal + approved 2025-26
   stats only (the trust moment — this is what telecallers get wrong daily).
4. Share a number (`9876500011, Ravi, Proddatur`) → lead captured, consented,
   scored, greeting WhatsApp fired (mock), day-2 nudge scheduled.
5. **Follow-ups → Run scheduler now** → due bilingual sequences send.
6. **Overview** → funnel, source attribution, joined count, branch demand.
7. **Compliance** → DPDP consent ledger + full audit log + kill switch.

## Guardrails (hard-coded, not prompt-hoped)

| Guardrail | Behavior |
|---|---|
| Approved-facts-only | Structured answers come from CKP tables (fees/hostels/routes/placements/dates); prose from the RAG pack with citations; unknown → "counselor will confirm" + task |
| 5 trap refusals | job guarantees, salary promises, scholarship certainty, refund rulings, rank predictions → honest refusal + approved data + counselor follow-up |
| DPDP consent firewall | No outbound without a consent record; one-click STOP per lead; WhatsApp opt-in recorded with timestamps |
| Kill switch | Pauses the AI for the whole college instantly |
| Immutable audit log | Every AI answer, trap hit, send, handoff, human action |
| Rate caps | Daily WhatsApp/follow-up caps per college |

## Repo map

```
SeatSetu/
├── api/index.py + vercel.json    Vercel serverless entrypoint + config
├── app/
│   ├── main.py        FastAPI routes (chat, leads, CKP, followups, webhook…)
│   ├── db.py          Models: College, Course, Hostel, TransportRoute,
│   │                  PlacementStat, KeyDate, Staff, Lead, Conversation,
│   │                  Message, CounselorTask, FollowUpLog, KbChunk, AuditLog
│   ├── counselor.py   THE BRAIN: bilingual topic router → CKP-table answers →
│   │                  RAG fallback → trap refusals → lead capture → scheduling
│   ├── followups.py   Greeting → day-2 nudge → day-7 visit → day-12 reminder
│   ├── guardrails.py  Kill switch · consent firewall · trap patterns · audit
│   ├── corpus.py      Counseling doctrine (JVD rules, EAPCET process,
│   │                  objection playbook, trap doctrine, DPDP script)
│   ├── rag.py         Hybrid retrieval (vectors + keywords, RRF) + confidence
│   ├── llm.py         Free-tier LLM gateway (Gemini / GitHub Models / …)
│   ├── connectors.py  WhatsApp Cloud API (mock→live) + Meta lead-ads parsing
│   ├── seed.py        Demo college (RIT Kadapa) + doctrine corpus
│   └── static/        Dashboard (index.html) + parent widget (widget.html)
└── requirements.txt
```

## Deploy to Vercel (₹0)

1. `git init && git add . && git commit -m "SeatSetu v0.3.2"` → push to GitHub
   (the `SeatSetu/` folder is the repo root).
2. Vercel → Add New → Project → import the repo (auto-detects `vercel.json`).
3. Storage → create **Postgres** (Hobby free) or use [neon.tech](https://neon.tech)
   → add env var `DATABASE_URL = postgresql://…`.
4. Optional (better chat quality, still free): `GEMINI_API_KEY`
   ([aistudio.google.com/apikey](https://aistudio.google.com/apikey)) or
   `GITHUB_TOKEN` (PAT with `models:read` → GitHub Models).
5. Deploy → open the app → Settings → set `META_VERIFY_TOKEN` to any random
   string (needed later for the real Meta webhook).

**WhatsApp live mode** (when ready): Meta app + WABA + phone number → put
`WHATSAPP_TOKEN` + `WHATSAPP_PHONE_ID` in env; point the Meta lead-ads webhook
to `POST /api/webhooks/meta-lead` (verify via `GET` with the same token).
Sending costs ≈ ₹0.13–0.17/message (pass-through, billed by Meta).

## What's mock vs real today

| Capability | State | To activate |
|---|---|---|
| Website AI counselor (Telugu+English, cited) | ✅ **Real** now | — |
| Traps, consent firewall, audit log, kill switch | ✅ **Real** | — |
| Lead CRM, scoring, tasks, funnel, attribution | ✅ **Real** | — |
| Follow-up engine | ✅ **Real** (mock sends) | Add WhatsApp keys → live sends |
| Meta lead-ads intake | ✅ **Real** endpoint | Point the real webhook at it |
| LLM-grounded free-text answers | Template/extractive brain | Add a free LLM key |
| WhatsApp Cloud API | Mock (logged) | `WHATSAPP_TOKEN` + `WHATSAPP_PHONE_ID` |

## Module B — **SeatSetu Accred** (NAAC/AQAR/OBE Autopilot) — ✅ BUILT

Dashboard → **SeatSetu Accred** tab:

- **OBE attainment from Excel**: upload the college's existing marks sheet
  (.xlsx/.csv with `Roll, Name, CO1/20, CO2/20…` columns + optional MAX row) →
  deterministic computation of per-CO attainment (0-3 levels), CO→PO-mapped
  **direct PO attainment**, target gaps with auto-drafted "action taken" text,
  and an 80/20 direct+indirect blend once an exit-survey is added
  (`POST /api/.../accred/survey`). Zero LLM involvement where accuracy matters —
  every number traces back to the sheet.
- **AQAR evidence vault**: 18-item checklist across the 7 NAAC criteria with
  readiness %, Dec-31 deadline countdown, per-item status (pending/partial/
  collected) — the same structure a ₹5L consultant walks in with, in software.
- **Bloom-mapped question papers**: pick a course registration → generate a
  model paper with sections distributed across Bloom levels, every question
  tagged `[CO · L# · Unit]` — kills the accreditation formatting grind.

**Acceptance test passed**: 24-student sample sheet → 5 CO levels, 7 PO direct
scores, survey blend, gap analysis, generated paper (see `app/static/sample_marks.csv`
as the shareable "expected format" template for IQACs).

API: `/api/colleges/{id}/accred/regs · .../upload · .../runs · .../aqar ·
.../evidence · .../survey · .../qpaper`

*Business plan: `../CollegeGrowthOS_Business_Plan.md` · Product spec:
`../CollegeGrowthOS_Product_Spec.md`*


## Security (v0.3.1)
Dashboard + staff APIs are behind an admin login (`ADMIN_PASSWORD` env; default `seatsetu-admin` for dev — **change in production**).
Parent surfaces (widget, chat, landing, guides) stay public. See `SECURITY.md` for the full model.

## Website integration (any existing college website)
One line before `</body>` adds a branded AI-chat bubble to any site (WordPress/Joomla/custom PHP):
`<script src="https://YOUR-SEATSETU-HOST/embed.js" data-college="1"></script>`
Also available: direct `/widget/1` link, iframe page, and QR codes for hoardings. Field kit: `docs/Onboarding_Kit.html`.

### Rank advisor (v0.3.1)
Parent shares an EAPCET rank (English, Tenglish or Telugu script) → the counselor compares it against the college's approved last-year closing ranks and answers per branch: ✅ strong chance / 🟡 borderline / 🔴 tough — always with the honest "decided only in convener counseling" line and a campus-visit CTA. No prediction, no promises — approved CKP data only.
