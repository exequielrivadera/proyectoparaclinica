"""
Backend inicial de referencia para Clínica.
No es un sistema clínico listo para producción. Completar hardening y auditoría antes de exponerlo.
"""
import os, re, sqlite3, secrets
from datetime import datetime, date
from functools import wraps
from pathlib import Path
from flask import Flask, request, jsonify, session, abort, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "DEV-ONLY-change-this-before-running")
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024
DB_PATH = Path(os.getenv("DATABASE_PATH", str(ROOT / "instance" / "clinica.sqlite3")))
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(ROOT.parent / "uploads_private"))).resolve()
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con

def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users(
          id INTEGER PRIMARY KEY, dni TEXT UNIQUE NOT NULL, full_name TEXT NOT NULL,
          email TEXT NOT NULL, phone TEXT NOT NULL, sex TEXT NOT NULL DEFAULT '',
          role TEXT NOT NULL CHECK(role IN ('admin','doctor','patient')),
          password_hash TEXT, enabled INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS appointments(
          id INTEGER PRIMARY KEY, patient_id INTEGER NOT NULL REFERENCES users(id),
          specialty TEXT NOT NULL, doctor_id INTEGER REFERENCES users(id),
          starts_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'booked',
          created_at TEXT NOT NULL, UNIQUE(doctor_id, starts_at)
        );
        CREATE TABLE IF NOT EXISTS studies(
          id INTEGER PRIMARY KEY, patient_id INTEGER NOT NULL REFERENCES users(id),
          doctor_id INTEGER REFERENCES users(id), title TEXT NOT NULL, study_date TEXT NOT NULL,
          comments TEXT NOT NULL DEFAULT '', stored_name TEXT NOT NULL,
          published INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit_log(
          id INTEGER PRIMARY KEY, actor_id INTEGER, action TEXT NOT NULL,
          target_type TEXT NOT NULL, target_id INTEGER, created_at TEXT NOT NULL
        );
        """)

def now():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def current_user():
    uid = session.get("uid")
    if not uid: return None
    with db() as con:
        return con.execute("SELECT * FROM users WHERE id=? AND enabled=1", (uid,)).fetchone()

def login_required(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            u = current_user()
            if not u: return jsonify(error="Autenticación requerida"), 401
            if roles and u["role"] not in roles: return jsonify(error="Permiso insuficiente"), 403
            return fn(*args, **kwargs)
        return wrapped
    return deco

def audit(actor, action, target_type, target_id=None):
    with db() as con:
        con.execute("INSERT INTO audit_log(actor_id,action,target_type,target_id,created_at) VALUES(?,?,?,?,?)",
                    (actor, action, target_type, target_id, now()))

@app.get("/api/health")
def health():
    return jsonify(status="ok", mode="starter-not-production")

@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    dni = re.sub(r"\D", "", str(data.get("dni", "")))
    password = str(data.get("password", ""))
    if not dni or not password: return jsonify(error="Ingresá DNI y contraseña"), 400
    with db() as con:
        u = con.execute("SELECT * FROM users WHERE dni=? AND enabled=1", (dni,)).fetchone()
    if not u or not u["password_hash"] or not check_password_hash(u["password_hash"], password):
        # Production must add rate limits, progressive delays and security monitoring.
        return jsonify(error="Credenciales inválidas"), 401
    session.clear()
    session["uid"] = u["id"]
    audit(u["id"], "login", "user", u["id"])
    return jsonify(user={"id":u["id"],"name":u["full_name"],"role":u["role"]})

@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)

@app.get("/api/me")
@login_required()
def me():
    u = current_user()
    return jsonify(id=u["id"], dni=u["dni"], full_name=u["full_name"], role=u["role"])

@app.post("/api/admin/patients")
@login_required("admin")
def create_patient():
    data = request.get_json(silent=True) or {}
    required = ["dni", "full_name", "email", "phone"]
    if any(not str(data.get(k, "")).strip() for k in required):
        return jsonify(error="Faltan datos obligatorios"), 400
    dni = re.sub(r"\D", "", str(data["dni"]))
    if not re.fullmatch(r"\d{7,9}", dni): return jsonify(error="DNI inválido"), 400
    # New accounts are disabled until a verified activation flow is implemented.
    try:
        with db() as con:
            cur = con.execute("""INSERT INTO users(dni,full_name,email,phone,sex,role,password_hash,enabled,created_at)
            VALUES(?,?,?,?,?,'patient',NULL,0,?)""",
            (dni, data["full_name"].strip(), data["email"].strip(), data["phone"].strip(),
             data.get("sex",""), now()))
            uid = cur.lastrowid
        audit(current_user()["id"], "create_patient_pending_activation", "user", uid)
        return jsonify(id=uid, status="pending_secure_activation"), 201
    except sqlite3.IntegrityError:
        return jsonify(error="Ya existe un registro con ese DNI"), 409

@app.post("/api/admin/patients/<int:patient_id>/activation")
@login_required("admin")
def create_activation(patient_id):
    # Scaffold intentionally does not issue/send codes. Implement verified single-use tokens,
    # expiry, rate limiting and delivery to a verified channel before enabling this endpoint.
    return jsonify(error="Flujo de activación segura pendiente de implementar; no se habilitó la cuenta."), 501

@app.get("/api/availability")
def availability():
    specialty = request.args.get("specialty", "").strip()
    day = request.args.get("date", "").strip()
    if not specialty or not day: return jsonify(error="Indicar specialty y date"), 400
    try: date.fromisoformat(day)
    except ValueError: return jsonify(error="Fecha inválida"), 400
    # This endpoint deliberately does not invent availability. It only returns slots configured
    # by the real scheduling module, which must be implemented for the selected clinic.
    return jsonify(date=day, specialty=specialty, slots=[], message="Agenda real pendiente de configuración")

@app.post("/api/appointments")
def create_appointment():
    # Public booking must be completed with server-side validation, email verification,
    # consent tracking, idempotency and a transaction-based slot lock before production.
    return jsonify(error="Reservas reales pendientes de implementar; no se guardó ningún turno."), 501

@app.get("/api/patient/studies")
@login_required("patient")
def patient_studies():
    u = current_user()
    with db() as con:
        rows = con.execute("""SELECT id,title,study_date,comments,created_at FROM studies
            WHERE patient_id=? AND published=1 ORDER BY study_date DESC""", (u["id"],)).fetchall()
    audit(u["id"], "list_own_published_studies", "user", u["id"])
    return jsonify(studies=[dict(r) for r in rows])

@app.post("/api/doctor/studies")
@login_required("doctor")
def upload_study():
    u = current_user()
    patient_dni = re.sub(r"\D", "", request.form.get("patient_dni", ""))
    title = request.form.get("title", "").strip()
    study_date = request.form.get("study_date", "").strip()
    comments = request.form.get("comments", "").strip()
    file = request.files.get("file")
    if not patient_dni or not title or not study_date or not file:
        return jsonify(error="Paciente, título, fecha y archivo son obligatorios"), 400
    try: date.fromisoformat(study_date)
    except ValueError: return jsonify(error="Fecha inválida"), 400
    ext = Path(secure_filename(file.filename or "")).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS: return jsonify(error="Formato no permitido"), 400
    # Random storage name, outside public static files. Production must also scan files and validate MIME.
    stored = secrets.token_hex(24) + ext
    path = UPLOAD_DIR / stored
    with db() as con:
        patient = con.execute("SELECT * FROM users WHERE dni=? AND role='patient' AND enabled=1", (patient_dni,)).fetchone()
        if not patient: return jsonify(error="Paciente habilitado no encontrado"), 404
        file.save(path)
        cur = con.execute("""INSERT INTO studies(patient_id,doctor_id,title,study_date,comments,stored_name,published,created_at)
          VALUES(?,?,?,?,?,?,0,?)""", (patient["id"],u["id"],title,study_date,comments,stored,now()))
        sid = cur.lastrowid
    audit(u["id"], "upload_study_draft", "study", sid)
    return jsonify(id=sid, status="draft_not_published"), 201

@app.post("/api/doctor/studies/<int:study_id>/publish")
@login_required("doctor", "admin")
def publish_study(study_id):
    u = current_user()
    with db() as con:
        row = con.execute("SELECT * FROM studies WHERE id=?", (study_id,)).fetchone()
        if not row: return jsonify(error="Estudio no encontrado"), 404
        if u["role"] == "doctor" and row["doctor_id"] != u["id"]:
            return jsonify(error="No tenés permiso para publicar este estudio"), 403
        con.execute("UPDATE studies SET published=1 WHERE id=?", (study_id,))
    audit(u["id"], "publish_study", "study", study_id)
    # Email notification intentionally not sent until SMTP and a privacy-safe template are configured.
    return jsonify(ok=True, status="published_email_integration_pending")

@app.get("/api/patient/studies/<int:study_id>/download")
@login_required("patient")
def download_study(study_id):
    u = current_user()
    with db() as con:
        row = con.execute("SELECT * FROM studies WHERE id=? AND patient_id=? AND published=1", (study_id,u["id"])).fetchone()
    if not row: abort(404)
    path = UPLOAD_DIR / row["stored_name"]
    if not path.is_file(): abort(404)
    audit(u["id"], "download_own_study", "study", study_id)
    return send_file(path, as_attachment=True, download_name=f"estudio-{study_id}{path.suffix}")

if __name__ == "__main__":
    init_db()
    if app.config["SECRET_KEY"].startswith("DEV-ONLY"):
        print("ADVERTENCIA: SECRET_KEY de desarrollo. No usar públicamente.")
    app.run(host="127.0.0.1", port=5000, debug=True)
