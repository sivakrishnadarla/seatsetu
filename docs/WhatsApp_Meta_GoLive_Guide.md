# WhatsApp + Meta Lead Ads — Go-Live Guide (SeatSetu)

This guide takes SeatSetu from demo mode to **real WhatsApp sending + real Meta lead-ads capture**.
One-time setup (~45 min). After this, the same env vars serve **every college** on your deployment.

---

## PART A — WhatsApp Cloud API (send real WhatsApp messages)

### A1. Create the Meta App (free)
1. Go to https://developers.facebook.com → **My Apps → Create App**
2. Type: **Business** → name it "SeatSetu WhatsApp" → create.
3. On the app dashboard, find **WhatsApp → Set up** (Meta walks you through creating a
   **Business Portfolio** + a test **WhatsApp Business Account**).
4. You get a **test number** with 5 recipient contacts — enough to test.
   For production: WhatsApp → **API Setup** → add a real phone number (a SIM that can
   receive an OTP; it must NOT be used in the WhatsApp app). **Never publish this number's token.**

### A2. Copy the two values
On **WhatsApp → API Setup**:
- **WHATSAPP_TOKEN** = the temporary access token (24h) — for permanent, generate a
  **System User token** in Business Settings → Users → System users (never expires).
- **WHATSAPP_PHONE_ID** = the Phone number ID (a long number, NOT the phone number itself).

### A3. Put them in Vercel
Vercel → your `setsetu` project → **Settings → Environment Variables** → add:
```
WHATSAPP_TOKEN      = EAAG...your-token
WHATSAPP_PHONE_ID   = 123456789012345
```
→ **Redeploy** (Deployments → latest → Redeploy) so they take effect.

### A4. Test (30 seconds)
Dashboard → **Settings → 🧪 Test WhatsApp sending** → enter your own mobile → Send.
- Live mode message arrives ✅ — done.
- Error? 90% of the time it's the token expired (make a System User token) or the
  recipient not added to the test number's allowed list.

### A5. Know the 24-hour rule (important, keep you legal)
Business-initiated messages outside the 24h customer-service window need an approved
**template**. Your follow-up/broadcast texts work great inside the window. For day-2/7/12
nudges, register message templates in the Meta Business Manager (Marketing category,
e.g. "Hi {name}, any doubts about {branch} fees...") and use them as the template texts —
start with the free-tier conversations every new number gets.

---

## PART B — Meta Lead Ads → SeatSetu (instant lead capture)

### B1. Note your three values
- **VERIFY_TOKEN**: any random string YOU invent, e.g. `ssu-verify-7Kd93jla` 
  (keep it consistent — same string in Meta AND in Vercel).
- **APP_SECRET**: Meta App → App Settings → Basic → App Secret → show/copy.

### B2. Vercel env vars (same place as Part A)
```
META_VERIFY_TOKEN = ssu-verify-7Kd93jla
META_APP_SECRET   = your-app-secret
```
→ Redeploy. SeatSetu now answers Meta's verification challenge at
`https://setsetu.vercel.app/api/webhooks/meta-lead` and verifies every payload's
X-Hub-Signature-256 signature.

### B3. Create the Lead Ad form
1. Meta Business Suite → **Ads Manager → Create campaign → Objective: Leads**.
2. Ad set → choose audience (your district + age 18-40 + parents interests).
3. **Instant Form**: ask Full name, **Phone number** (WhatsApp-preferred), City, Course interest.
4. Publish (even a ₹100/day boosted post works).

### B4. Connect the webhook (one time per Meta app)
1. developers.facebook.com → your app → **+ Add Product → Webhooks**.
2. Object: **Page** → **Subscribe**.
3. Callback URL: `https://setsetu.vercel.app/api/webhooks/meta-lead`
4. Verify token: the exact `META_VERIFY_TOKEN` string from B2 → Verify and save
   (SeatSetu returns the challenge automatically).
5. Subscribe to the **leadgen** field.
6. In your Lead form settings, connect the form to this Page.

### B5. Test end-to-end
Submit your own test lead to the ad form (Meta's "Preview form" → submit from your phone).
→ **Leads tab**: new lead appears within seconds, source `whatsapp`/meta, greeting follow-up fires.
✅ Live capture complete.

---

## PART C — Where the leads land + who can change what
- Every webhook lead lands in **Leads** with source attribution, scored, consent handled.
- Change/repoint env vars: Vercel → Settings → Environment Variables (Owner only — never share).
- Rotate tokens: Meta Business → System user → regenerate → update Vercel → Redeploy.
- If WhatsApp shows "mock mode" again, it means an env var is missing on the CURRENT
  deployment — check Vercel → Deployments → the deploy's env summary.

## Quick troubleshooting
| Symptom | Fix |
|---|---|
| Test-send says "mock mode" | Env vars missing on current deployment → add + **Redeploy** |
| `(#131030) recipient not in allowed list` | Test number: add recipient in API Setup |
| Token expired errors (#190) | Use a **System User** token (never expires) |
| Webhook verify fails | VERIFY_TOKEN strings don't match exactly (case-sensitive) |
| Leads not arriving | Webhook → leadgen not subscribed; or form not linked to the Page |
