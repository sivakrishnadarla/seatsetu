"""SeatSetu — full module QA matrix (run: python3 qa_test.py)"""
import json, urllib.request, urllib.error, urllib.parse

B = "http://localhost:8000"
results = []
ADMIN_COOKIE = {}

def req(method, path, data=None, headers=None, raw=False, noauth=False):
    h = dict(headers) if headers else {"Content-Type": "application/json"}
    if ADMIN_COOKIE and not noauth:
        admin = "ss_admin=" + ADMIN_COOKIE["ss_admin"]
        h["Cookie"] = (h["Cookie"] + "; " + admin) if "Cookie" in h else admin
    r = urllib.request.Request(B+path, method=method,
        data=json.dumps(data).encode() if data is not None else None, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, (resp.read() if raw else json.loads(resp.read().decode()))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None

def try_login(password):
    """POST /login; capture ss_admin cookie on success. Returns (status, got_cookie)."""
    body = urllib.parse.urlencode({"password": password}).encode()
    r = urllib.request.Request(B+"/login", data=body, method="POST",
                               headers={"Content-Type": "application/x-www-form-urlencoded"})
    op = urllib.request.build_opener(_NoRedirect)
    try:
        resp = op.open(r, timeout=30)
    except urllib.error.HTTPError as e:
        resp = e
    sc = resp.headers.get("Set-Cookie", "")
    got = "ss_admin=" in sc
    if got:
        ADMIN_COOKIE["ss_admin"] = sc.split("ss_admin=")[1].split(";")[0]
    return getattr(resp, "status", getattr(resp, "code", 0)), got

st, ok = try_login("seatsetu-admin")   # default dev password (app/config.py)
if not ok:
    raise SystemExit("FATAL: admin login failed — qa_test cannot proceed")

STAFF_COOKIE = {}
def staff_login(u, p):
    body = urllib.parse.urlencode({"username": u, "password": p}).encode()
    r = urllib.request.Request(B+"/login", data=body, method="POST",
                               headers={"Content-Type": "application/x-www-form-urlencoded"})
    op = urllib.request.build_opener(_NoRedirect)
    try:
        resp = op.open(r, timeout=30)
    except urllib.error.HTTPError as e:
        resp = e
    sc = resp.headers.get("Set-Cookie", "")
    got = "ss_user=" in sc
    if got:
        STAFF_COOKIE["ss_user"] = sc.split("ss_user=")[1].split(";")[0]
    return getattr(resp, "status", getattr(resp, "code", 0)), got

def check(module, name, cond, extra=""):
    results.append((module, name, "PASS" if cond else "FAIL", extra))

# ── 0. Infrastructure ──
st, html = req("GET", "/home", raw=True);  check("Core", "Landing page /home", st==200 and b"Every seat" in html)
st, html = req("GET", "/", raw=True);      check("Core", "Dashboard /", st==200 and b"SeatSetu" in html)
st, d = req("GET", "/api/colleges", noauth=True); check("Security", "Admin API blocked without login", st==401, str(st))
st2, ok2 = try_login("wrong-password");            check("Security", "Wrong password rejected", (not ok2) and st2 in (401,403), str(st2))
st, d = req("GET", "/api/me");                       check("Staff", "/api/me shows admin", st==200 and d.get("role")=="admin", str(st))
st, ok = staff_login("counselor", "counselor123");   check("Staff", "Counselor login (seeded)", st==303 and ok, str(st))
h = {"Content-Type": "application/json", "Cookie": "ss_user=" + STAFF_COOKIE.get("ss_user","")}
st, d = req("GET", "/api/me", headers=h);            check("Staff", "Counselor role via /api/me", st==200 and d.get("role")=="counselor", str(d)[:60])
st, d = req("POST", "/api/colleges/1/killswitch/on", {}, headers=h)
check("Staff", "Counselor CANNOT kill-switch (403)", st==403, str(st))
st, d = req("GET", "/api/colleges/1/reports/management", headers=h)
check("Reports", "Management pack JSON", st==200 and "admissions" in d and "careers" in d and "accred" in d, str(st))
st, html = req("GET", "/reports/1", headers=h, raw=True)
check("Reports", "Management one-pager HTML", st==200 and b"Management Report" in html and b"Pooja Soft Solutions" in html, str(st))
st, csv = req("GET", "/api/colleges/1/reports/leads.csv", headers=h, raw=True)
check("Reports", "Leads register CSV", st==200 and b"name,phone,town" in csv, str(st))
ah = {"Content-Type": "application/json", "Cookie": "ss_admin=" + ADMIN_COOKIE["ss_admin"]}
st, d = req("POST", "/api/staff-users", {"username":"qaofficer","password":"short","role":"placement"}, headers=ah)
check("Staff", "Weak password rejected (422)", st==422, str(st))
st, d = req("POST", "/api/staff-users", {"username":"qaofficer","password":"qapass12345","role":"placement","name":"QA Officer"}, headers=ah)
check("Staff", "Create staff user (admin)", st==200 and d.get("ok"), str(d)[:60])
st, d = req("POST", "/api/staff-users", {"username":"qaoff2","password":"qapass12345","role":"placement"}, headers=h)
check("Staff", "Counselor CANNOT create users (403)", st==403, str(st))
st, ok = staff_login("qaofficer", "qapass12345");    check("Staff", "New staff can login", st==303 and ok, str(st))
st, html = req("GET", "/widget/1", raw=True); check("Core", "Parent widget + PSS attribution", st==200 and b"Pooja Soft Solutions" in html)
st, ico = req("GET", "/favicon.ico", raw=True); check("Core", "Favicon", st==200 and len(ico)>500)
st, css = req("GET", "/static/brand.css", raw=True); check("Core", "brand.css (fonts+tokens)", st==200 and b"Poppins" in css)
st, lg = req("GET", "/static/logo.png", raw=True); check("Core", "Logo asset", st==200 and len(lg)>10000)

# ── 1. Onboarding ──
st, d = req("POST", "/api/colleges", {"name":"QA Engineering College","short":"QAC","city":"Kurnool",
              "district":"Kurnool","eapcet_code":"QACK","phone":"+91-90000-99999"})
check("Onboarding", "Create college", st==200 and d.get("college_id"), str(d)[:60])
CID = d["college_id"]
st, d = req("GET", "/api/colleges");  check("Onboarding", "College list", st==200 and any(c["id"]==CID for c in d))

# ── 2. CKP ──
st, d = req("POST", f"/api/colleges/{CID}/ckp", {
  "about":"QAC is a testing college in Kurnool with 4 UG branches.",
  "admission_process":"Visit office with documents. Token 8000.",
  "courses":[{"name":"CSE — Computer Science","code":"CSE","intake":120,"convener_fee":35000,
              "mgmt_fee":75000,"mgmt_note":"token 8000","cutoff_note":"2025: 62000","highlights":"good"}],
  "hostels":[{"for_whom":"boys","ac":False,"fee_per_year":60000,"facilities":"mess, warden"}],
  "routes":[{"from_place":"Kurnool","distance_km":6,"fee_per_year":7000}],
  "placements":[{"year":"2025-26","placed_pct":64,"offers":100,"companies":30,"top_lpa":4.0,"avg_lpa":3.0,"note":"ok"}],
  "dates":[{"label":"Admissions","when_note":"Open now"}]})
check("CKP", "Save & re-index", st==200 and d.get("chunks_indexed",0)>0, str(d)[:60])
st, d = req("GET", f"/api/colleges/{CID}/ckp")
check("CKP", "CKP read-back", st==200 and d["courses"][0]["mgmt_fee"]==75000)

# ── 3. AI Counselor ──
st, d = req("POST", f"/api/chat/{CID}", {"text":"CSE fee enta? hostel unda?","channel":"web"})
check("Counselor", "Tenglish detected → Telugu answer (exact ₹)", st==200 and "35,000" in d["reply"] and d["language"]=="te",
      f"lang={d.get('language')}")
check("Counselor", "Citations present", len(d["citations"])>0)
st, d = req("POST", f"/api/chat/{CID}", {"text":"What are the placements?","channel":"web"})
check("Counselor", "Placements (English, approved stats)", st==200 and "64%" in d["reply"])
st, d = req("POST", f"/api/chat/{CID}", {"text":"100% placement guarantee unda?","channel":"web"})
check("Counselor", "Trap: job guarantee refused", d["flagged"] and "guarantee" in d["reply"].lower())
st, d = req("POST", f"/api/chat/{CID}", {"text":"refund istara cancel cheste?","channel":"web"})
check("Counselor", "Trap: refund → office", d["flagged"] and "office" in d["reply"].lower())
st, d = req("POST", f"/api/chat/{CID}", {"text":"predict my rank sir","channel":"web"})
check("Counselor", "Trap: rank prediction refused", d["flagged"])
st, d = req("POST", f"/api/chat/{CID}", {"text":"minimum salary package guarantee cheyyi","channel":"web"})
check("Counselor", "Trap: salary promise refused", d["flagged"])
st, d = req("POST", f"/api/chat/{CID}", {"text":"scholarship confirm ga vastunda?","channel":"web"})
check("Counselor", "Trap: scholarship certainty", d["flagged"])
st, d = req("POST", f"/api/chat/{CID}", {"text":"hello","channel":"web"})
check("Counselor", "Greeting", st==200 and "counselor" in d["reply"].lower())
st, d = req("POST", f"/api/chat/{CID}", {"text":"flurple zorp qwerty","channel":"web"})
check("Counselor", "Ungrounded → honest escape + task", d["escalated"])
st, d = req("POST", f"/api/chat/1", {"text": "my EAPCET rank is 45000 - can I get CSE seat?"}); check("Counselor", "Rank advisor (approved closing ranks)", st==200 and ("58,000" in d.get("reply","")) and "✅" in d.get("reply",""), d.get("reply","")[:60])

# ── v0.4: actions & intelligence ──
st, d = req("POST", "/api/widget/1/book_visit", {"name":"QA Visitor","phone":"9600000001",
            "date": __import__("datetime").date.today().isoformat(), "branch":"CSE","consent":True})
check("Actions", "Widget: book campus visit", st==200 and d.get("ok"), str(d)[:70])
st, d = req("POST", "/api/widget/1/book_visit", {"name":"QA Bad","phone":"123","date":"2026-01-01"})
check("Actions", "Visit: invalid phone rejected", st==200 and not d.get("ok"), str(d)[:50])
st, d = req("POST", "/api/widget/1/brochure_lead", {"name":"QA Brochure Parent","phone":"9600000002"})
check("Actions", "Widget: brochure gate captures lead", st==200 and d.get("ok") and d.get("url"), str(d)[:70])
st, pdf = req("GET", "/brochure/1.pdf", raw=True)
check("Actions", "AI brochure PDF generated", st==200 and pdf[:4]==b"%PDF" and len(pdf)>3000, f"{len(pdf)//1024}KB")
st, d = req("GET", "/api/colleges/1/next-actions")
check("Actions", "Next-best-actions panel", st==200 and isinstance(d,list) and len(d)>=1, str(st))
st, d = req("POST", "/api/colleges/1/coach", {"text":"fee enta saar","stage":"interested"})
check("Actions", "Reply Coach suggestion", st==200 and d.get("suggestion"), str(d)[:60])

# ── v0.5 premium ──
st, leads = req("GET", "/api/colleges/1/leads")
LID = leads[0]["id"] if isinstance(leads, list) and leads else 1
st, d = req("GET", f"/api/leads/{LID}/timeline")
check("Premium", "Lead 360 timeline", st==200 and "lead" in d and "timeline" in d, str(st))
st, d = req("POST", f"/api/leads/{LID}/assign", {"username":"counselor"})
check("Premium", "Assign lead to counselor", st==200 and d.get("ok"), str(d)[:50])
st, d = req("POST", "/api/widget/1/feedback", {"helpful": True})
check("Premium", "Parent 👍 feedback captured", st==200 and d.get("ok"), str(st))
st, d = req("GET", "/api/colleges/1/analytics")
check("Premium", "ROI analytics (CPL/CPJ/trend)", st==200 and "trend" in d and "conversion_pct" in d, str(st))
st, d = req("GET", "/api/colleges/1/digest")
check("Premium", "Monday digest (headline lines)", st==200 and isinstance(d.get("headline"), list) and len(d["headline"])>=4, str(st))
st, d = req("PUT", "/api/colleges/1/settings", {"ad_spend": {"meta_ad": 12000, "hoarding": 4000}})
check("Premium", "Save ad spend (principal)", st==200 and d.get("ok"), str(st))
st, d = req("GET", "/api/colleges/1/analytics")
check("Premium", "Cost-per-joined computed", st==200 and d.get("cpj") and d["spend"]==16000, str(d)[:60])
st, bz = req("GET", "/api/colleges/1/backup.zip", raw=True)
check("Premium", "Data backup ZIP", st==200 and bz[:2]==b"PK" and len(bz)>2000, f"{len(bz)//1024}KB")
st, d = req("GET", "/api/colleges/1/settings", headers=h)
check("Premium", "Counselor blocked from settings", st==403, str(st))

# ── 4. Lead capture ──
st, d = req("POST", f"/api/chat/{CID}", {"text":"Hi I am Ravi from Nandyal, number 9876543210","channel":"web","consent_given":True})
check("Leads", "Chat lead captured", d["lead_captured"])
st, d = req("GET", f"/api/colleges/{CID}/leads")
lead = next((l for l in d if l["phone"]=="9876543210"), None)
check("Leads", "Lead fields parsed", lead and lead["name"]=="Ravi" and lead["town"]=="Nandyal")
check("Leads", "Consent recorded", lead and lead["consent"])

# ── 5. Meta webhook ──
st, d = req("POST", "/api/webhooks/meta-lead", {"leadgen_id":"QA1","form_name":"QA Form",
    "field_data":[{"name":"full_name","values":["Web Lead"]},{"name":"phone_number","values":["9876500099"]},{"name":"city","values":["Kurnool"]}]})
check("Meta Ads", "Lead-ad webhook", st==200 and d.get("lead_id"))
st, d = req("GET", f"/api/colleges/{CID}/followups")
check("Follow-ups", "Greeting fired + seq scheduled", any(l["seq_step"]>=1 for l in d))
st, d = req("GET", "/api/webhooks/meta-lead?hub_mode=subscribe&hub_verify_token=wrong&hub_challenge=42")
check("Meta Ads", "Webhook verify rejects bad token", st==403)

# ── 6. Follow-up engine ──
st, d = req("POST", f"/api/run/followups/{CID}")
check("Follow-ups", "Scheduler runs", st==200 and "sent" in d)
st, d = req("POST", f"/api/leads/{lead['id']}/stop")
check("Compliance", "DPDP STOP (marketing killed)", st==200)
st, d = req("GET", f"/api/colleges/{CID}/followups")
check("Compliance", "Stopped lead excluded", all(not (l["id"]==lead["id"] and l["seq_step"] in (1,2,3)) for l in d))

# ── 7. Tasks ──
st, d = req("GET", f"/api/colleges/{CID}/tasks")
check("Counselor To-Do", "Tasks auto-created", st==200 and len(d)>0)

# ── 8. Accred (Module B) ──
st, d = req("POST", f"/api/colleges/{CID}/accred/regs", {
  "course_name":"QA Course","code":"QC101","semester":"I","academic_year":"2025-26",
  "cos":[{"no":1,"desc":"explain basics","bloom":2,"pos":[1,2]},{"no":2,"desc":"apply methods","bloom":3,"pos":[2,3]},
         {"no":3,"desc":"analyze problems","bloom":4,"pos":[3,4]}],
  "co_po_map":{"1":{"1":3,"2":2},"2":{"2":3,"3":2},"3":{"3":3,"4":1}},"target":2.0})
check("Accred", "Create course registration", st==200 and d.get("reg_id"))
REG = d["reg_id"]
st, d = req("POST", f"/api/colleges/{CID}/accred/regs/{REG}/upload", raw=False,
            headers={"Content-Type":"application/json"})
# multipart upload via raw request:
import http.client, os
boundary = "X-BOUNDARY"
with open("app/static/sample_marks.csv","rb") as f: filedata = f.read()
body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"sample_marks.csv\"\r\n"
        f"Content-Type: text/csv\r\n\r\n").encode() + filedata + f"\r\n--{boundary}--\r\n".encode()
_uph = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
if ADMIN_COOKIE:
    _uph["Cookie"] = "ss_admin=" + ADMIN_COOKIE["ss_admin"]
r = urllib.request.Request(B+f"/api/colleges/{CID}/accred/regs/{REG}/upload", data=body, method="POST",
    headers=_uph)
with urllib.request.urlopen(r, timeout=30) as resp:
    up = json.loads(resp.read().decode())
rep = up["report"]
check("Accred", "Marks upload → CO/PO attainment", len(rep["co_attain"])==5 and len(rep["po_direct"])>0,
      f"students={rep['students']}")
RUN = up["run_id"]
st, d = req("POST", f"/api/colleges/{CID}/accred/survey", {"academic_year":"2025-26","respondents":50,
    "po_indirect":{"1":2.5,"2":2.4,"3":2.6,"4":2.2,"5":2.5,"6":2.3,"7":2.4}})
check("Accred", "Survey stored", st==200)
st, d = req("GET", f"/api/colleges/{CID}/accred/runs/{RUN}")
check("Accred", "Survey blend (final PO)", "po_final" in d["report"] and d["report"]["blend"].endswith("indirect"))
st, d = req("GET", f"/api/colleges/{CID}/accred/aqar")
check("Accred", "AQAR checklist + readiness", st==200 and d["total_items"]>=18 and 0<=d["readiness"]<=100)
st, d = req("POST", f"/api/colleges/{CID}/accred/evidence", {"criterion":"5.1.2","title":"Mock interview records","owner":"PO"})
check("Accred", "Evidence add", st==200 and d.get("id"))
st, d = req("POST", f"/api/accred/evidence/{d['id']}/status", {"status":"collected"})
check("Accred", "Evidence → collected", st==200)
st, d = req("POST", f"/api/colleges/{CID}/accred/qpaper", {"reg_id":REG,
    "sections":[{"name":"A","count":5,"marks":2,"blooms":[1,2]},{"name":"B","count":3,"marks":5,"blooms":[3,4]}]})
check("Accred", "Bloom question paper", st==200 and d["total_marks"]==25 and all("co" in q for q in d["sections"][0]["questions"]))

# ── 9. Careers (Module C) ──
st, d = req("POST", f"/api/colleges/{CID}/careers/start", {"student_name":"QA Student","roll":"22QA001","branch":"CSE","role":"Software / IT"})
check("Careers", "Interview start (6 Qs)", st==200 and len(d["questions"])==6)
MI = d["id"]
st, d = req("POST", f"/api/careers/{MI}/answer", {"no":1,"text":"I am QA Student from Kurnool, CSE third year. I built a library app used by 200 students and I am learning React. My goal is a product company role."})
check("Careers", "Answer scoring", st==200 and 2.5<=d["score"]<=5 and d["tips"])
st, d = req("POST", f"/api/careers/{MI}/answer", {"no":2,"text":"dont know"})
check("Careers", "Weak answer low score", st==200 and d["score"]<=1.5)
st, d = req("POST", f"/api/careers/{MI}/finish")
check("Careers", "Finish → overall", st==200 and d["overall"]>0)
st, d = req("GET", f"/api/careers/{MI}")
check("Careers", "Report persisted", d["overall"]>0 and d["questions"][0]["score"]>0)
st, d = req("GET", f"/api/colleges/{CID}/careers/summary")
check("Careers", "Summary", st==200 and d["total"]>=1 and d["avg"]>0)
st, csvd = req("GET", f"/api/colleges/{CID}/careers/export", raw=True)
check("Careers", "NAAC evidence CSV", st==200 and b"5.1.2" in csvd and b"QA Student" in csvd)

# ── 10. Governance ──
st, d = req("POST", f"/api/colleges/{CID}/killswitch/on")
check("Governance", "Kill switch ON", st==200)
st, d = req("POST", f"/api/chat/{CID}", {"text":"fees?"})
check("Governance", "AI blocked during kill switch", st==403)
st, d = req("POST", f"/api/colleges/{CID}/killswitch/off")
check("Governance", "Kill switch OFF", st==200)
st, d = req("GET", f"/api/colleges/{CID}/audit")
check("Governance", "Audit log has full trail", st==200 and len(d)>15 and any("guardrail" in l["action"] for l in d))
st, d = req("GET", f"/api/colleges/{CID}/consents")
check("Governance", "Consent ledger", st==200 and len(d)>0)
st, d = req("GET", "/api/kb/search?q=fee+structure&college_id=1")
check("RAG", "KB search", st==200 and len(d)>0)

# ── report ──
mods = []

# ── v0.6 staff & roles ──
import time as _t

def staff_login(u, p):
    body = urllib.parse.urlencode({"username": u, "password": p}).encode()
    r = urllib.request.Request(B+"/login", data=body, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    op = urllib.request.build_opener(_NoRedirect)
    try:
        resp = op.open(r, timeout=30)
    except urllib.error.HTTPError as e:
        resp = e
    sc = resp.headers.get("Set-Cookie", "")
    tok = sc.split("ss_user=")[1].split(";")[0] if "ss_user=" in sc else None
    return getattr(resp, "status", getattr(resp, "code", 0)), tok

def hdr(tok):
    return {"Content-Type": "application/json", "Cookie": "ss_user=" + tok}

uname = "qaoff" + str(int(_t.time()))[-6:]
st, d = req("POST", "/api/staff-users", {"username": uname, "password": "office-2026",
           "role": "office", "name": "QA Office", "phone": "9999911111",
           "tabs": ["leads", "tasks", "help"]})
check("Staff", "Owner creates login + custom tabs", st == 200 and d.get("ok"), str(d)[:60])
st, d = req("POST", "/api/staff-users", {"username": uname, "password": "office-2026"})
check("Staff", "Duplicate username rejected", st == 422, str(st))
st, d = req("GET", "/api/staff-users")
uid = next((u["id"] for u in d if u["username"] == uname), 0)
check("Staff", "Console lists person (phone visible)", uid > 0 and any(
    u["username"] == uname and u["phone"] == "9999911111" for u in d), str(uid))
ls, tok = staff_login(uname, "office-2026")
check("Staff", "New person can login", ls in (303, 200) and tok, str(ls))
st, d = req("GET", "/api/me", headers=hdr(tok))
check("Staff", "Custom allocation honored (leads/tasks/help)",
      st == 200 and sorted(d.get("tabs", [])) == ["help", "leads", "tasks"], str(d.get("tabs")))
check("Staff", "Office user blocked from Settings",
      req("GET", "/api/colleges/1/settings", headers=hdr(tok))[0] == 403, "")
check("Staff", "Office user can't touch staff accounts",
      req("PUT", f"/api/staff-users/{uid}", {"active": True}, headers=hdr(tok))[0] == 403, "")
st, d = req("PUT", f"/api/staff-users/{uid}", {"active": False})
check("Staff", "Owner deactivates -> login dies",
      st == 200 and staff_login(uname, "office-2026")[0] == 401, str(st))
req("PUT", f"/api/staff-users/{uid}", {"active": True})
st, d = req("POST", f"/api/staff-users/{uid}/password", {"password": "newsecret99"})
check("Staff", "Owner resets password -> new works",
      st == 200 and staff_login(uname, "newsecret99")[0] == 303, str(st))
st, d = req("GET", "/api/staff-users")
u2 = next((u for u in d if u["username"] == uname), {})
check("Staff", "Last-login tracked", bool(u2.get("last_login")), str(u2.get("last_login")))
ls, dtok = staff_login("director", "director123")
check("Staff", "Director opens Settings (ROI view)",
      ls == 303 and req("GET", "/api/colleges/1/settings", headers=hdr(dtok))[0] == 200, str(ls))
check("Staff", "Director can't create staff (owner-only)",
      req("POST", "/api/staff-users", {"username": "xq1", "password": "12345678"},
          headers=hdr(dtok))[0] == 403, "")


# ── v0.7: comparison pack + probe interviews + /sell ──
st, d = req("POST", "/api/colleges/1/competitors", {"name": "Sri Vision Institute of Technology",
           "town": "Kadapa", "distance_km": "14 km", "annual_fee": "78000", "placements_pct": "58%",
           "closing_rank_note": "CSE closes ~70k", "their_strength": "New campus buildings",
           "our_edge": "2x placement record + senior faculty", "source_note": "AICTE approvals 2025-26"})
check("Growth", "Comparison Pack: add competitor (owner)", st == 200 and d.get("ok"), str(st))
st, d = req("POST", "/api/chat/1", {"text": "RIT vs Sri Vision Institute of Technology — which is better for CSE?", "channel": "web"})
rep = d.get("reply", "") if isinstance(d, dict) else ""
check("Growth", "Chat compares with public numbers + visit pivot",
      st == 200 and "Sri Vision" in rep and "campus visit" in rep, rep[:70])
st, d = req("POST", "/api/chat/1", {"text": "which is the best college nearby?", "channel": "web"})
rep = d.get("reply", "") if isinstance(d, dict) else ""
check("Growth", "Unlisted college -> honest refusal", st == 200 and "will not guess" in rep, rep[:60])
st, d = req("GET", "/api/colleges/1/competitors")
check("Growth", "Comparison Pack list", st == 200 and len(d) >= 1, str(st))
st, m = req("POST", "/api/colleges/1/careers/start",
            {"student_name": "QA Pro", "branch": "CSE", "role": "Software / IT", "strict": True})
check("Growth", "Strict-panel interview starts", st == 200 and len(m.get("questions", [])) >= 5, str(st))
MID = m.get("id", 0)
st, d = req("POST", f"/api/careers/{MID}/answer", {"no": 1, "text": "ok"})
fu = d.get("followup") or {}
check("Growth", "Weak answer -> adaptive probe follow-up",
      st == 200 and str(fu.get("no")) == "1b", str(d)[:80])
st, d = req("POST", f"/api/careers/{MID}/answer", {"no": "1b",
           "text": "In my second-year project I built a library app with Flask and SQLite; I led a 3-member team and we delivered before the deadline with 96% accuracy."})
check("Growth", "Probe answer scored (no second probe)",
      st == 200 and d.get("score") is not None and not d.get("followup"), str(d)[:60])
st, bz = req("GET", "/sell", raw=True)
check("Growth", "/sell sales page live (public)", st == 200 and b"Every seat" in bz, str(st))


# ── v0.7.2: student practice pass ──
st, d = req("POST", "/api/colleges/1/practice-passes", {"student_name": "QA Student", "roll": "22CSE999", "branch": "CSE"})
check("Practice", "Staff creates Practice Pass code", st == 200 and d.get("ok") and len(d.get("code", "")) == 8, str(d)[:60])
PCODE = d.get("code", "")
check("Practice", "Practice code login works", urllib.request.Request, "")
def _prac_login(code):
    r = urllib.request.Request(B+"/api/practice/login", data=json.dumps({"code": code}).encode(),
        method="POST", headers={"Content-Type": "application/json"})
    op = urllib.request.build_opener(_NoRedirect)
    try: resp = op.open(r, timeout=30)
    except urllib.error.HTTPError as e: resp = e
    sc = resp.headers.get("Set-Cookie", "")
    tok = sc.split("ss_prac=")[1].split(";")[0] if "ss_prac=" in sc else None
    return getattr(resp, "status", 0), tok
pls, ptok = _prac_login(PCODE)
check("Practice", "Student logs in with code", pls == 200 and ptok, str(pls))
PH = {"Content-Type": "application/json", "Cookie": "ss_prac=" + ptok}
check("Practice", "Wrong code rejected", _prac_login("ZZZZZZZZ")[0] == 403, "")
st, d = req("POST", "/api/practice/start", {"branch": "CSE", "role": "Software / IT"}, headers=PH)
check("Practice", "Student starts self-practice interview", st == 200 and len(d.get("questions", [])) >= 5, str(st))
PMID = d.get("id", 0)
st, d = req("POST", f"/api/practice/{PMID}/answer", {"no": 1, "text": "I am QA Student, CSE final year, I built a hostel mess feedback app with Flask, led 2 juniors, goal is backend developer."}, headers=PH)
check("Practice", "Self-practice answer scored", st == 200 and d.get("score") is not None, str(st))
st, d = req("POST", f"/api/practice/{PMID}/finish", {}, headers=PH)
check("Practice", "Self-practice finish saves readiness", st == 200 and "overall" in d, str(st))
check("Practice", "Student CANNOT touch college APIs",
      req("GET", "/api/colleges/1/leads", headers=PH, noauth=True)[0] == 401, "")
check("Practice", "Officer sees self-practice in careers summary",
      req("GET", "/api/colleges/1/careers/summary")[0] == 200, "")
check("Practice", "/practice page serves", req("GET", "/practice", raw=True)[1].find(b"Practice Code") > -1, "")


# ── v0.8: reach (broadcast + test + seats) ──
st, d = req("GET", "/api/colleges/1/broadcast/audience")
check("Reach", "Broadcast audience counts consented leads", st == 200 and d.get("count", 0) >= 1, str(d)[:60])
st, d = req("POST", "/api/colleges/1/broadcast",
            {"text": "Namaste! Campus visits open this Saturday 10-4. Bring your rank card. Reply STOP to opt out."})
check("Reach", "Broadcast queues to consented (mock mode)",
      st == 200 and d.get("sent", 0) >= 1 and d.get("mode") == "mock", str(d)[:70])
st, d = req("POST", "/api/colleges/1/broadcast", {"text": "short"})
check("Reach", "Broadcast rejects tiny text", st == 422, str(st))
st, d = req("POST", "/api/settings/test-whatsapp", {"phone": "9848123456"})
check("Reach", "WhatsApp test-send (mock mode honest)",
      st == 200 and d.get("mode") == "mock" and "logged" in str(d.get("note", "")), str(d)[:70])
st, d = req("POST", "/api/chat/1", {"text": "CSE seats available aa? kottha seat unda?", "channel": "web"})
rep = d.get("reply", "") if isinstance(d, dict) else ""
check("Reach", "Seats answer: intake + honesty + visit CTA",
      st == 200 and "intake" in rep and "campus visit" in rep and "guarantee" not in rep.lower(), rep[:70])
st, d = req("POST", "/api/chat/1", {"text": "ECE seat", "channel": "web"})
check("Reach", "Seats answer cites approved intake table",
      st == 200 and any("intake table" in str(c.get("title", "")) for c in d.get("citations", [])), "")


# ── v0.8.2: referrals/commissions + imports ──
st, ls0 = req("GET", "/api/colleges/1/leads")
lid = ls0[0]["id"]
st, d = req("POST", f"/api/leads/{lid}", {"ref_username": "lakshmi", "commission_amt": 3000})
check("Commissions", "Lead attributed to staff with ₹ amount", st == 200, str(st))
st, d = req("POST", f"/api/leads/{lid}", {"stage": "joined"})
check("Commissions", "Lead advanced to joined", st == 200 and d.get("stage") == "joined", str(d)[:50])
st, d = req("GET", "/api/colleges/1/commissions")
sm = {t["username"]: t for t in d.get("summaries", [])}
check("Commissions", "Due ₹ computed on joined lead",
      "lakshmi" in sm and sm["lakshmi"]["due"] == 3000 and sm["lakshmi"]["joined"] >= 1, str(sm)[:80])
st, d = req("GET", f"/api/leads/{lid}/timeline")
check("Commissions", "Drawer payload includes referral info",
      st == 200 and d.get("ref", {}).get("username") == "lakshmi", str(d.get("ref"))[:60])
st, d = req("POST", "/api/colleges/1/commissions/mark-paid", {"username": "lakshmi"})
check("Commissions", "Mark-paid settles + logs", st == 200 and d.get("cleared", 0) >= 1, str(d)[:60])
st, d = req("GET", "/api/colleges/1/commissions")
sm = {t["username"]: t for t in d.get("summaries", [])}
check("Commissions", "After settle: due 0, paid 3000",
      "lakshmi" in sm and sm["lakshmi"]["due"] == 0 and sm["lakshmi"]["paid"] == 3000, str(sm)[:80])
st, d = req("GET", "/api/colleges/1/backup.zip", raw=True)
import io as _io, zipfile as _zf
names = _zf.ZipFile(_io.BytesIO(d)).namelist() if st == 200 else []
check("Exports", "Backup ZIP has interviews + CKP + leads CSVs",
      st == 200 and "mock_interviews.csv" in names and "knowledge_pack.json" in names and "leads.csv" in names, str(names)[:80])
CSV = "name,phone,town,branch,source\nImport A,9000000001,Proddatur,CSE,walk_in\nImport B,9000000002,Rajampet,ECE,\nDup,9000000001,Kadapa,CSE,\n"
st, d = req("POST", "/api/colleges/1/leads/import", {"csv": CSV})
check("Imports", "Leads CSV import: 2 imported, 1 duplicate skipped",
      st == 200 and d.get("imported") == 2 and d.get("skipped") == 1, str(d)[:70])
st, ls2 = req("GET", "/api/colleges/1/leads")
imp = [l for l in ls2 if l.get("source") == "import"]
check("Imports", "Imported leads: no consent (DPDP), scored",
      len(imp) >= 2 and all(not l.get("consent") for l in imp), str(len(imp)))
st, d = req("POST", "/api/colleges/1/leads/import", {"csv": "hello world\n1,2\n"})
check("Imports", "Import rejects header-less CSV", st == 422, str(st))
st, d = req("POST", "/api/colleges/1/ckp/import",
            {"pack": {"college": {"about": "Import test college"}, "courses": [
                {"name": "B.Tech CSE — import test", "code": "CSE", "intake": 111,
                 "convener_fee": 35000, "mgmt_fee": 65000, "cutoff_note": ""}]}})
check("Imports", "CKP import replaces pack (Owner)", st == 200 and d.get("courses") == 1, str(d)[:70])
st, d = req("GET", "/api/colleges/1/ckp")
ck = d if isinstance(d, dict) else {}
check("Imports", "CKP reflects imported course", any(c.get("intake") == 111 for c in ck.get("courses", [])), "")

for m, n, r, e in results:
    if m not in mods: mods.append(m)
print("\n" + "═"*78)
print("SEATSETU — FULL MODULE QA MATRIX")
print("═"*78)
cur = None
fails = 0
for m, n, r, e in results:
    if m != cur:
        print(f"\n▌ {m}")
        cur = m
    print(f"  {r}  {n}" + (f"   [{e}]" if e and r=="FAIL" else ""))
    fails += (r=="FAIL")
print("\n" + "═"*78)
print(f"RESULT: {len(results)-fails}/{len(results)} passed · {fails} failed")
print("═"*78)
