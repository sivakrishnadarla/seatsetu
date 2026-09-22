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

## What's new in v0.8.4 — Accred Vault & AQAR Dossier

| Feature | Where | What it does |
|---|---|---|
| 📎 **Real document uploads** | SeatSetu Accred → evidence list | Upload the actual scan/photo/PDF (max 8 MB) on any AQAR item — it auto-marks the item **done**. Files download anytime with one tap. |
| ⬇ **AQAR Dossier ZIP** | SeatSetu Accred → green button | ONE click → NAAC-ready pack: `00_SUMMARY.csv` (every criterion, owner, status, links), `attainment/` (CO/PO reports from your marks Excel, TXT + CSV), `question_papers/`, `evidence/<criterion>/` (your uploaded documents). The IQAC downloads this and submits on the NAAC portal. |
| ➕ **Seed standard 18** | SeatSetu Accred | One tap creates the checklist rows for all standard AQAR criteria. |

> Honest note: SeatSetu PREPARES the dossier — it never submits to NAAC (no such integration exists). The college's IQAC submits under its own signature.

## What's new in v0.8.3 — Demo College (show the dashboard, not just the chat)

| Feature | Where | What it does |
|---|---|---|
| 🏫 **SeatSetu Demo College (SSDC)** | Auto-seeded on every fresh deployment | A fully-worked FICTIONAL tenant (EAPCET code `SSDC1`): 20 leads across **all 7 sources** and every funnel stage with real scores, 8 follow-ups DUE NOW, 2 bilingual chat transcripts (incl. the honest trap-question refusal), 3 staff tasks, competitor comparison pack, AQAR evidence, practice pass `DEMO2026`, and per-person staff logins. Switch to **SSDC** in the college selector and the Command Center is instantly demo-ready for a Principal/Director — numbers, funnel, ROI and to-dos all populated. |
| 👤 **Demo staff logins** | Login page | `ssdc.director / director-2026` (Director — sees everything, edits nothing) · `ssdc.lakshmi / lakshmi-2026` (Counselor) · `ssdc.ravi / ravi-2026` (Office) · `ssdc.iqac / iqac-2026` (IQAC). Hand these out during demos so management logs in as THEMSELVES with role-wise tabs. |

Demo data is clearly fictional ("SeatSetu Demo College of Engineering, Vijayawada") and never mixes with real colleges: leads, transcripts and knowledge chunks are tenant-scoped to SSDC only.

## What's new in v0.8.2 — Referrals & Imports

| Feature | Where | What it does |
|---|---|---|
| 💸 **Referral commissions** | Lead drawer + Reports | Attribute a lead to a staff member with an agreed ₹ per joined admission. DUE auto-computes when the lead reaches **joined**; settle with an audited **Mark paid**. Money roles only — counselors never see amounts. |
| ⬆ **Leads CSV import** | Leads tab | Columns: name, phone, town, branch, source, campaign, rank. Duplicates skipped; imported parents get **no consent** (never auto-messaged — DPDP safe). |
| ⬇/⬆ **Knowledge Pack import** | Knowledge tab | Restore `knowledge_pack.json` from any backup ZIP (Owner/Principal). Your college data moves with you. |
| 📦 **Backup ZIP +** | Settings | Now includes `mock_interviews.csv` (student practice evidence) alongside leads/careers/conversations/CKP. |

QA: **128/128**. All 15 dashboard tabs render-tested error-free; widget + `/practice` re-verified.

## What's new in v0.8 — Reach

| Feature | Where | What it does |
|---|---|---|
| 📣 **Broadcast** | Follow-ups tab | One message → every **consented** parent still in the pipeline (Owner/Principal/Management/Office). Audience counter, confirm dialog, fully logged (audit + per-lead FollowUpLog). Honest-text policy enforced in the UI copy. |
| 🧪 **WhatsApp test-send** | Settings | Send a test to your own mobile. Mock mode says "logged, not sent" honestly; with `WHATSAPP_TOKEN` + `WHATSAPP_PHONE_ID` env vars it goes **live** — no code change. |
| 🪑 **Honest seat answers** | Widget/chat | "Seats available aa?" → approved intake table (cited), joined-so-far, counselling reality ("nobody outside the office can promise a seat") → campus-visit CTA. Rank questions still route to the rank advisor. |

QA: **116/116**.

## What's new in v0.7.2 — Student Practice Pass

**Mock interviews now run two ways:**
1. **Office-led** (staff + student in the lab): speaking interviewer, voice answers, panel probes, strict mode.
2. **Student self-practice**: the office issues an **8-character Practice Pass** (Careers → 🎟️ Practice Passes card) → student opens **/practice** on ANY phone → unlimited voice mocks. Students see only their own history; every attempt appears in Careers (tagged self-practice) and files NAAC 5.1.2 evidence. Codes deactivate in one tap.

QA: **110/110**.

## What's new in v0.7 — Growth Edition

| Feature | Where | What it does |
|---|---|---|
| 🎙️ **Realistic AI interviews** | Careers | Interviewer **speaks questions aloud** (en-IN), student answers by **voice**, weak answers trigger **adaptive panel follow-up probes** ("walk me through it step by step"), strict-panel mode (−0.5 scoring) — zero third-party APIs, works offline |
| 🏫 **Comparison Pack** | Knowledge Pack | Owner curates nearby colleges' PUBLIC numbers (fee, placements %, closing ranks + source). When a parent asks "RIT vs X?", the AI compares honestly, credits their strengths, states your edge — then books a campus visit. Unlisted colleges → honest refusal, never invented |
| 📢 **/sell sales website** | `/sell` (public) | Full premium landing page: live AI demo embedded, competitor comparison table (Meritto/LeadSquared/Classe365), pricing cards with WhatsApp CTAs, FAQ — point colleges here |

QA: **100/100**.

## What's new in v0.6 — Staff & Roles ("Many Hands")

**One Admin Key is no longer a bottleneck — every person gets their own login:**

| Role | What they get |
|---|---|
| 🟢 Owner (Admin Key) | Everything + the only one who creates staff logins |
| 🟣 Principal | Full view + Monday digest + approvals — **no** staff admin |
| 🟠 Director | All numbers & ₹ ROI — sees everything, enters nothing |
| 🔵 Management | Pipeline + ad spend + widget |
| 🩵 Admin Office | Daily work: leads, calls, visits, consent |
| ⚪ Counselor | Own leads, AI chats, to-do — nothing else |
| 🩷 Placement Officer | Careers, mocks, NAAC evidence |
| 🟢 IQAC | Accreditation & marks |

- **🎚️ Allocate:** Owner ticks exactly which screens each person sees (per-person override of role presets) — applies on their very next click
- **🔑 Credentials flow:** create → temp password shown once → one-tap **send on WhatsApp**
- **Last-login tracking** + deactivate (instant lockout) + owner-only password resets
- **Login page rebuilt:** staff path vs Owner/Admin-Key path, in plain words + Telugu
- **❓ Help tab:** "What is SeatSetu", your-day-in-3-steps **per role**, glossary (Lead, Consent, CPL/CPJ, AQAR…), self-service password change
- **Role landing:** counselors land on To-Do, placement on Careers, IQAC on Accred — everyone lands where they work

QA: **92/92**. Settings (₹, digest, backup) now open to Director/Management too — read/edit money, never staff.

## What's new in v0.5 — Enterprise Edition

**Premium layer on top of v0.4's "AI that ACTS":**

| Feature | Where | What it does |
|---|---|---|
| 🎯 Lead-360° drawer | Leads → click any lead | Full story: every message (parent/AI), follow-up, task — color-coded timeline + assign to counselor |
| 💰 ₹ ROI analytics | Overview | Cost-per-lead, cost-per-JOINED-student vs ₹3.4L seat lifetime value, 7-day trend, conversion % |
| 🎤 Parent voice input | Widget | Telugu (te-IN) speech-to-text in Chrome/Edge — parents speak, AI answers |
| 👍👎 Answer ratings | Widget | Parents rate every 4th AI answer; quality loop |
| 📮 Monday digest | Settings | One-tap plain-language WhatsApp briefing for the principal |
| ⚙️ Settings console | Settings | Ad-spend per source (feeds ROI), system status, backup |
| 📦 One-click backup | Settings | ZIP: leads/careers/conversations CSVs + Knowledge Pack JSON |
| 🛡️ Chat rate-limiting | API | 40 msgs/60s per IP → 429; blocks flooding |
| 📲 PWA install | Widget | Manifest + service worker — parents install the college on their phone |

Settings tab is admin/principal-only. All v0.4 features unchanged. QA: **80/80**.

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


## v0.4 — The AI that ACTS
- **📅 Book campus visit** inside the parent chat: name + phone + date + branch → lead (`visit_booked`) + dated counselor task + document checklist reply. Invalid phones/dates rejected.
- **📄 Brochure lead-gate**: parent's name+phone → auto-generated college PDF brochure (built live from the Knowledge Pack: courses/fees, hostels, buses, placements, key dates) + call task for the counselor.
- **🎯 "What to do today"** — prescriptive next-best-actions on the dashboard: due follow-ups, human handoffs waiting, visits to confirm, hot leads going cold, AQAR countdown, careers nudge. Each with a Go→ button.
- **✨ Reply Coach** — one-click suggested next reply per conversation (LLM if a key is set, else topic playbook), stage-aware, guardrail-safe.
- QA matrix: **71/71**. Brochure endpoint is public; all staff endpoints remain gated.
