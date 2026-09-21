"""Role-based staff access: pbkdf2 passwords, signed cookies, role→tabs.

v0.6 "Many Hands": 8 role types mirroring a real college hierarchy.
The Owner (Admin Key) allocates exactly what each person sees — per-person
tab overrides stored on the user, role presets as the starting point.
"""
import base64, hashlib, hmac, json, secrets

from .config import SETTINGS

ROLES = ("admin", "principal", "director", "manager", "office",
         "counselor", "placement", "iqac")

ALL_TABS = ["overview", "leads", "chats", "tasks", "followups", "reports",
            "settings", "staff", "help", "ckp", "widget", "playbook",
            "accred", "careers", "comply"]

# Who can open Settings (ad spend, digest, backup, system status)
SETTINGS_ROLES = ("admin", "principal", "director", "manager")

ROLE_TABS = {
    "admin":     ALL_TABS,  # Owner — everything, incl. staff accounts
    "principal": [t for t in ALL_TABS if t != "staff"],  # oversight + digest, no staff admin
    "director":  ["overview", "reports", "settings", "accred", "careers",
                  "comply", "playbook", "help"],               # see everything, enter nothing
    "manager":   ["overview", "leads", "chats", "tasks", "followups",
                  "reports", "settings", "widget", "careers", "help"],
    "office":    ["overview", "leads", "chats", "tasks", "followups",
                  "widget", "ckp", "accred", "careers", "comply", "help"],
    "counselor": ["overview", "leads", "chats", "tasks", "followups",
                  "playbook", "help"],
    "placement": ["overview", "reports", "careers", "playbook", "help"],
    "iqac":      ["overview", "reports", "accred", "ckp", "playbook", "help"],
}

ROLE_LABELS = {  # one plain line each — shown in the Staff console & Help
    "admin":     "Owner (Admin Key) — controls everything, creates staff accounts",
    "principal": "Principal — full view + Monday digest + approvals; no staff admin",
    "director":  "Director — sees every number & ₹ ROI; enters no data",
    "manager":   "Management — runs the admissions pipeline, ad spend & widget",
    "office":    "Admin Office — does the daily work: leads, calls, visits, consent",
    "counselor": "Counselor — their leads, AI chats, to-do list. Nothing else.",
    "placement": "Placement Officer — mock interviews, careers, NAAC evidence",
    "iqac":      "IQAC Coordinator — accreditation, marks, evidence vault",
}
ROLE_LANDING = {  # where each role lands after login
    "admin": "overview", "principal": "overview", "director": "overview",
    "manager": "leads", "office": "tasks", "counselor": "tasks",
    "placement": "careers", "iqac": "accred",
}


def hash_pw(pw: str) -> str:
    salt = secrets.token_hex(8)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 60000).hex()
    return f"{salt}${h}"


def verify(pw: str, stored: str) -> bool:
    try:
        salt, h = (stored or "").split("$", 1)
        return hmac.compare_digest(hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 60000).hex(), h)
    except Exception:
        return False


def gen_password(name: str = "") -> str:
    """Human-typeable temp password: ravi-4832 style (≥8 chars)."""
    base = "".join(ch for ch in (name or "staff").lower() if ch.isalpha())[:4] or "staff"
    return f"{base}-{secrets.randbelow(9000) + 1000}"


def _sig(payload: str) -> str:
    return hmac.new(SETTINGS.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()[:24]


def make_token(username: str, role: str, college_id) -> str:
    payload = f"{username}|{role}|{college_id or 0}"
    return base64.urlsafe_b64encode(payload.encode()).decode() + "." + _sig(payload)


def parse_token(token: str):
    try:
        b64, sig = token.split(".", 1)
        payload = base64.urlsafe_b64decode(b64.encode()).decode()
        if not hmac.compare_digest(sig, _sig(payload)):
            return None
        u, r, c = payload.split("|")
        return {"username": u, "role": r if r in ROLES else "counselor",
                "college_id": int(c) or None, "tabs": ROLE_TABS.get(r, [])}
    except Exception:
        return None


def _tabs_for(su) -> list:
    """Role preset, unless the Owner allocated a custom set for this person."""
    custom = None
    try:
        custom = json.loads(su.tabs_json) if getattr(su, "tabs_json", None) else None
    except Exception:
        custom = None
    if isinstance(custom, list) and custom:
        valid = [t for t in custom if t in ALL_TABS]
        if valid:
            return valid
    return list(ROLE_TABS.get(su.role, []))


def actor(request, db) -> dict | None:
    """Current signed-in staff (or master admin) from cookies."""
    tok = request.cookies.get("ss_user", "")
    if tok:
        d = parse_token(tok)
        if d and db is not None:
            from .db import StaffUser
            su = db.query(StaffUser).filter_by(username=d["username"], active=True).first()
            if su:
                return {"id": su.id, "username": su.username, "role": su.role,
                        "name": su.name or su.username, "college_id": su.college_id,
                        "tabs": _tabs_for(su), "must_change": su.must_change}
    if request.cookies.get("ss_admin", ""):
        return {"id": 0, "username": "admin", "role": "admin", "name": "Master Admin",
                "college_id": None, "tabs": ALL_TABS, "must_change": False}
    return None


def ensure_users(db, college_id: int):
    from .db import StaffUser
    for u, pw, r, n in DEFAULT_USERS:
        if not db.query(StaffUser).filter_by(username=u).first():
            db.add(StaffUser(college_id=college_id, username=u, pw_hash=hash_pw(pw), role=r, name=n))
    db.commit()


def ensure_users_all(db):
    from .db import College
    for c in db.query(College).all():
        ensure_users(db, c.id)


DEFAULT_USERS = [  # (username, password, role, name) — must_change=True forces reset
    ("principal", "principal123", "principal", "Principal"),
    ("director", "director123", "director", "Director"),
    ("manager", "manager123", "manager", "Management"),
    ("office", "office123", "office", "Admin Office"),
    ("counselor", "counselor123", "counselor", "Front-desk Counselor"),
    ("placement", "placement123", "placement", "Placement Officer"),
    ("iqac", "iqac123", "iqac", "IQAC Coordinator"),
]
