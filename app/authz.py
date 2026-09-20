"""Role-based staff access: pbkdf2 passwords, signed cookies, role→tabs."""
import base64, hashlib, hmac, secrets

from .config import SETTINGS

ROLES = ("principal", "director", "counselor", "placement", "iqac", "admin")
ALL_TABS = ["overview", "leads", "chats", "tasks", "followups", "reports", "ckp", "widget",
            "playbook", "accred", "careers", "comply"]
ROLE_TABS = {
    "principal": ALL_TABS,
    "admin": ALL_TABS,
    "director": ["overview", "reports", "playbook", "accred", "careers", "comply"],  # read-first
    "counselor": ["overview", "leads", "chats", "tasks", "followups", "reports", "playbook"],
    "placement": ["overview", "reports", "careers", "playbook"],
    "iqac": ["overview", "reports", "accred", "playbook"],
}
DEFAULT_USERS = [  # (username, password, role, name) — must_change=True forces reset
    ("principal", "principal123", "principal", "Principal"),
    ("counselor", "counselor123", "counselor", "Front-desk Counselor"),
    ("placement", "placement123", "placement", "Placement Officer"),
    ("iqac", "iqac123", "iqac", "IQAC Coordinator"),
]


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


def actor(request, db) -> dict | None:
    """Current signed-in staff (or master admin) from cookies."""
    tok = request.cookies.get("ss_user", "")
    if tok:
        d = parse_token(tok)
        if d and db is not None:
            from .db import StaffUser
            su = db.query(StaffUser).filter_by(username=d["username"], active=True).first()
            if su:
                return {"username": su.username, "role": su.role, "name": su.name or su.username,
                        "college_id": su.college_id, "tabs": ROLE_TABS.get(su.role, []), "must_change": su.must_change}
    if request.cookies.get("ss_admin", ""):
        return {"username": "admin", "role": "admin", "name": "Master Admin",
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
