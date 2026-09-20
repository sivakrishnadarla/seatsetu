# SeatSetu — Security Model (v0.3.1)

## What's enforced in code
| **Staff roles** | 4 seeded logins per college (principal/counselor/placement/iqac) with role-scoped tabs + signed `ss_user` cookie (pbkdf2 passwords). Counselors cannot kill-switch or create users (403, QA-tested). Password change enforced via UI; default passwords flagged until changed. |
| Control | Mechanism |
|---|---|
| **Admin gate** | All staff APIs + dashboard require the `ss_admin` HttpOnly cookie (`/login`, password = `ADMIN_PASSWORD`, HMAC-derived token). Parents' surfaces stay public: widget, chat API, landing, guides. |
| **XSS defense** | Every parent/college-supplied string rendered in the dashboard passes `esc()` (HTML-entity encoded) before touching `innerHTML`. Widget uses no `innerHTML`. |
| **AI factual safety** | Counselor answers **only** from the college's approved Knowledge Pack (hybrid RAG, tenant-scoped). Ungrounded → polite hand-off. Guarantee/salary/scholarship traps refused (Consumer Protection Act 2019 guard). |
| **Kill switch** | Principal can pause all AI instantly (`/api/colleges/{id}/killswitch/on` → 403 on chat). Every block is audit-logged. |
| **Consent ledger (DPDP)** | Opt-in recorded per parent with timestamp; STOP excludes a lead from all outreach. |
| **Audit log** | Staff + guardrail + kill-switch events persisted with actor + timestamp. |
| **Meta webhook** | `verify_token` on GET; **HMAC X-Hub-Signature-256 verification on POST when `META_APP_SECRET` is set.** |
| **Uploads** | Marks file uploads capped at 5 MB; parsed via openpyxl/csv (no eval). |
| **SQL** | 100% SQLAlchemy ORM — parameterized, no string SQL. |
| **Secrets** | Never in code — `.env` / platform env vars (`ADMIN_PASSWORD`, `META_APP_SECRET`, LLM keys, WhatsApp token). |

## Deployment checklist (production)
1. `ADMIN_PASSWORD` — set a strong value on the server/Vercel env (default `seatsetu-admin` is dev-only).
2. `META_APP_SECRET` — set when the Meta lead webhook goes live (signature enforcement switches on automatically).
3. Serve behind HTTPS (Vercel gives this); then set `secure=True` on the login cookie in `app/main.py`.
4. Restrict DB (Neon/Postgres) to the app's connection string; enable provider backups.
5. Rate-limit `/api/chat/*` at the edge (Vercel firewall or Cloudflare free tier) if a widget gets abused.

## Known scope notes (honest)
- Single shared admin password per deployment (not per-staff accounts) — right-sized for a 3–10 member college office; per-user accounts + 2FA are on the v0.4 roadmap.
- Webhook routing picks the first college (single-tenant-per-deployment model); multi-tenant webhook routing is documented for the Vercel multi-college phase.
