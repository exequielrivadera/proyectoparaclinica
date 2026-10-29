"""
Backend de turnos para Clínica Demo.
Demo por defecto. Antes de usar pacientes reales, configurar SMTP, SECRET_KEY,
API_BASE_URL/CORS y completar verificación de identidad, rate limiting y despliegue HTTPS.
"""
import os, re, sqlite3, smtplib, logging
from email.message import EmailMessage
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, abort
from flask_cors import CORS
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
load_dotenv(ROOT / ".env")
TZ = ZoneInfo(os.getenv("TIMEZONE", "America/Argentina/Buenos_Aires"))
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"
DB_PATH = Path(os.getenv("DATABASE_PATH", str(ROOT / "instance" / "clinica.sqlite3")))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

# Servir frontend y API desde el mismo proceso evita el error "Failed to fetch"
# por URLs de API equivocadas o CORS en la demo. No exponer backend, base de datos ni archivos privados.
@app.get("/")
def public_home():
    return send_from_directory(PROJECT_ROOT, "index.html")

@app.get("/<path:filename>")
def public_assets(filename):
    normalized = filename.replace("\\", "/")
    first = normalized.split("/", 1)[0].lower()
    if first in {"api", "backend", "instance", "uploads_private", ".git", ".venv"} or normalized.startswith("."):
        abort(404)
    target = (PROJECT_ROOT / normalized).resolve()
    if PROJECT_ROOT.resolve() not in target.parents or not target.is_file():
        abort(404)
    return send_from_directory(PROJECT_ROOT, normalized)
allowed_origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "https://exequielrivadera.github.io,http://127.0.0.1:5500,http://localhost:5500,http://127.0.0.1:8000,http://localhost:8000").split(",") if x.strip()]
CORS(app, resources={r"/api/*": {"origins": allowed_origins}})
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("clinica")

SLOTS = ["08:30","09:00","09:30","10:00","10:30","11:00","11:30","12:00"]
DOCTORS = {
    "Cardiología": ["Dra. Ana López"],
    "Clínica Médica": ["Dr. Martín Pérez"],
    "Pediatría": ["Dra. Sofía Gómez"],
    "Dermatología": ["Profesional a incorporar"],
    "Ginecología": ["Profesional a incorporar"],
    "Traumatología": ["Profesional a incorporar"],
}
DEMO_APPOINTMENTS = [{
    "dni":"30123456", "first_names":"Paciente", "last_names":"Demostración",
    "email":"", "phone":"", "specialty":"Cardiología", "doctor":"Dra. Ana López",
    "starts_at":"2026-10-28T10:30:00-03:00", "status":"booked"
}]

def connect():
    con=sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory=sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=10000")
    return con

def now_local():
    return datetime.now(TZ).replace(microsecond=0)

def init_db():
    with connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS appointments(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          first_names TEXT NOT NULL, last_names TEXT NOT NULL,
          dni TEXT NOT NULL, email TEXT NOT NULL, phone TEXT NOT NULL DEFAULT '',
          specialty TEXT NOT NULL, doctor TEXT NOT NULL,
          starts_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'booked',
          appointment_type TEXT NOT NULL DEFAULT 'turno',
          created_at TEXT NOT NULL, confirmation_sent_at TEXT,
          reminder_24h_sent_at TEXT, reminder_3h_sent_at TEXT,
          patient_id INTEGER, doctor_id INTEGER,
          UNIQUE(doctor, starts_at)
        );
        CREATE INDEX IF NOT EXISTS idx_appointments_dni ON appointments(dni, starts_at);
        CREATE TABLE IF NOT EXISTS specialties (
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS doctors (
          id INTEGER PRIMARY KEY AUTOINCREMENT, full_name TEXT NOT NULL, license_number TEXT NOT NULL DEFAULT '',
          email TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '', room TEXT NOT NULL DEFAULT 'Consultorio 1',
          active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS doctor_specialties (
          doctor_id INTEGER NOT NULL REFERENCES doctors(id), specialty_id INTEGER NOT NULL REFERENCES specialties(id),
          PRIMARY KEY (doctor_id, specialty_id)
        );
        CREATE INDEX IF NOT EXISTS idx_appointments_reminders ON appointments(status, starts_at);
        CREATE TABLE IF NOT EXISTS patients (
          id INTEGER PRIMARY KEY AUTOINCREMENT, dni TEXT NOT NULL UNIQUE,
          first_names TEXT NOT NULL, last_names TEXT NOT NULL, email TEXT NOT NULL DEFAULT '',
          phone TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS clinical_notes (
          id INTEGER PRIMARY KEY AUTOINCREMENT, dni TEXT NOT NULL, doctor TEXT NOT NULL,
          appointment_id INTEGER, note TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS studies (
          id INTEGER PRIMARY KEY AUTOINCREMENT, dni TEXT NOT NULL, title TEXT NOT NULL,
          study_type TEXT NOT NULL, professional TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'processing',
          filename TEXT, original_name TEXT, published INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL, published_at TEXT, delivered_at TEXT
        );
        CREATE TABLE IF NOT EXISTS call_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, appointment_id INTEGER NOT NULL,
          patient_name TEXT NOT NULL, room TEXT NOT NULL, called_at TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'called'
        );
        CREATE INDEX IF NOT EXISTS idx_studies_dni ON studies(dni, created_at);
        CREATE INDEX IF NOT EXISTS idx_calls_called ON call_events(called_at);
        CREATE TABLE IF NOT EXISTS doctor_status (
          doctor TEXT PRIMARY KEY, room TEXT NOT NULL DEFAULT 'Consultorio 1',
          is_free INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL
        );
        """)
        # Migración compatible con bases SQLite ya creadas antes de incorporar sobreturnos.
        appointment_columns = {row["name"] for row in con.execute("PRAGMA table_info(appointments)").fetchall()}
        if "appointment_type" not in appointment_columns:
            con.execute("ALTER TABLE appointments ADD COLUMN appointment_type TEXT NOT NULL DEFAULT 'turno'")
        if "patient_id" not in appointment_columns:
            con.execute("ALTER TABLE appointments ADD COLUMN patient_id INTEGER REFERENCES patients(id)")
        if "doctor_id" not in appointment_columns:
            con.execute("ALTER TABLE appointments ADD COLUMN doctor_id INTEGER REFERENCES doctors(id)")
        # Catálogo editable de médicos y especialidades. Los IDs son autoincrementales y no se reutilizan.
        for specialty_name in ["Clínica Médica", "Cardiología", "Pediatría", "Dermatología", "Ginecología", "Traumatología"]:
            con.execute("INSERT OR IGNORE INTO specialties(name) VALUES(?)", (specialty_name,))
        seeds = [("Dra. Ana López", "Cardiología"), ("Dr. Martín Pérez", "Clínica Médica"), ("Dra. Sofía Gómez", "Pediatría")]
        for full_name, specialty_name in seeds:
            doc = con.execute("SELECT id FROM doctors WHERE full_name=?", (full_name,)).fetchone()
            if not doc:
                cur = con.execute("INSERT INTO doctors(full_name,created_at) VALUES(?,?)", (full_name, now_local().isoformat()))
                doc_id = cur.lastrowid
            else: doc_id = doc["id"]
            sp = con.execute("SELECT id FROM specialties WHERE name=?", (specialty_name,)).fetchone()
            con.execute("INSERT OR IGNORE INTO doctor_specialties(doctor_id,specialty_id) VALUES(?,?)", (doc_id, sp["id"]))
        # Vincular registros existentes a sus IDs sin alterar los IDs históricos de turnos/pacientes.
        for pat in con.execute("SELECT id,dni FROM patients").fetchall():
            con.execute("UPDATE appointments SET patient_id=? WHERE dni=? AND patient_id IS NULL", (pat["id"], pat["dni"]))
        for doc in con.execute("SELECT id,full_name FROM doctors").fetchall():
            con.execute("UPDATE appointments SET doctor_id=? WHERE doctor=? AND doctor_id IS NULL", (doc["id"], doc["full_name"]))
        # Demo patient data only. These records are fictional and safe for a walkthrough.
        con.execute("INSERT OR IGNORE INTO patients(dni,first_names,last_names,email,phone,created_at) VALUES(?,?,?,?,?,?)",
                    ("30123456","Juan","Pérez","juan.demo@example.com","3804000000",now_local().isoformat()))
        con.execute("INSERT OR IGNORE INTO patients(dni,first_names,last_names,email,phone,created_at) VALUES(?,?,?,?,?,?)",
                    ("28987654","María","Gómez","maria.demo@example.com","3804111111",now_local().isoformat()))
        con.execute("INSERT OR IGNORE INTO studies(dni,title,study_type,professional,status,published,created_at,published_at) VALUES(?,?,?,?,?,?,?,?)",
                    ("30123456","Análisis clínico de demostración","Laboratorio","Dra. Ana López","available",1,now_local().isoformat(),now_local().isoformat()))
        # Vincular también los turnos anteriores a pacientes demo insertados en esta misma inicialización.
        con.execute("UPDATE appointments SET patient_id=(SELECT id FROM patients WHERE patients.dni=appointments.dni) WHERE patient_id IS NULL")
        con.execute("UPDATE appointments SET doctor_id=(SELECT id FROM doctors WHERE doctors.full_name=appointments.doctor) WHERE doctor_id IS NULL")

def get_doctors(include_inactive=False):
    """Devuelve el catálogo activo agrupado por especialidad, manteniendo un ID único por médico."""
    with connect() as con:
        sql = """SELECT d.id, d.full_name, d.license_number, d.email, d.phone, d.room, d.active, s.name AS specialty
                 FROM doctors d JOIN doctor_specialties ds ON ds.doctor_id=d.id
                 JOIN specialties s ON s.id=ds.specialty_id WHERE s.active=1"""
        if not include_inactive: sql += " AND d.active=1"
        sql += " ORDER BY d.full_name, s.name"
        rows = con.execute(sql).fetchall()
    grouped = {}
    for row in rows: grouped.setdefault(row["specialty"], []).append(dict(row))
    return grouped

def doctor_name_to_id(name):
    with connect() as con:
        row = con.execute("SELECT id FROM doctors WHERE full_name=? AND active=1", (name,)).fetchone()
    return row["id"] if row else None

def smtp_ready():
    return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM") and os.getenv("SMTP_USER") and os.getenv("SMTP_PASSWORD"))

def send_email(to_addr, subject, body):
    if not smtp_ready():
        log.warning("SMTP no configurado: no se envió correo a %s (asunto: %s)", to_addr, subject)
        return False
    msg=EmailMessage()
    msg["Subject"]=subject
    msg["From"]=os.getenv("SMTP_FROM")
    msg["To"]=to_addr
    msg.set_content(body)
    host=os.getenv("SMTP_HOST")
    port=int(os.getenv("SMTP_PORT","587"))
    try:
        if os.getenv("SMTP_USE_SSL","false").lower()=="true":
            with smtplib.SMTP_SSL(host, port, timeout=20) as server:
                server.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD"))
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=20) as server:
                server.starttls()
                server.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD"))
                server.send_message(msg)
        return True
    except Exception:
        log.exception("Falló envío SMTP")
        return False

def appointment_text(row):
    starts=datetime.fromisoformat(row["starts_at"]).astimezone(TZ)
    return (f"Hola {row['first_names']},\n\n"
            f"Tu turno en Clínica Demo está registrado.\n"
            f"Especialidad: {row['specialty']}\nProfesional: {row['doctor']}\n"
            f"Fecha: {starts.strftime('%d/%m/%Y')}\nHora: {starts.strftime('%H:%M')}\n\n"
            "Si tu horario ya pasó y todavía no fuiste atendido, consultá en Administración el estado de tu turno.\n"
            "Si necesitás cancelar o cambiar el turno, contactá a la clínica.\n"
            "Este mensaje es informativo; conservá este correo.")

def send_confirmation(appointment_id):
    with connect() as con:
        row=con.execute("SELECT * FROM appointments WHERE id=?", (appointment_id,)).fetchone()
    if not row: return False
    ok=send_email(row["email"], "Confirmación de turno - Clínica Demo", appointment_text(row))
    if ok:
        with connect() as con: con.execute("UPDATE appointments SET confirmation_sent_at=? WHERE id=?", (now_local().isoformat(), appointment_id))
    return ok

def process_reminders():
    """Polling programado: recordatorio 24h y 3h antes; solo una vez por turno."""
    current=now_local()
    windows=[("reminder_24h_sent_at", current+timedelta(hours=24), "Recordatorio de turno para mañana"),
             ("reminder_3h_sent_at", current+timedelta(hours=3), "Recordatorio: tu turno es hoy")]
    with connect() as con:
        rows=con.execute("SELECT * FROM appointments WHERE status='booked'").fetchall()
    for row in rows:
        start=datetime.fromisoformat(row["starts_at"]).astimezone(TZ)
        if start <= current: continue
        for field,target,subject in windows:
            # tolerancia de 10 minutos para el trabajo del scheduler.
            if row[field] is None and abs((start-target).total_seconds()) <= 300:
                body=(f"Hola {row['first_names']},\n\n"
                      + ("Te recordamos que mañana tenés un turno en Clínica Demo.\n" if field=="reminder_24h_sent_at" else "Te recordamos que hoy tenés un turno en Clínica Demo.\n")
                      + f"Especialidad: {row['specialty']}\nProfesional: {row['doctor']}\n"
                      + f"Fecha: {start.strftime('%d/%m/%Y')}\nHora: {start.strftime('%H:%M')}\n\n"
                      "Si tu horario ya pasó y todavía no fuiste atendido, consultá en Administración el estado de tu turno.\n"
                      "Si necesitás cambiarlo o cancelarlo, contactá a la clínica.")
                if send_email(row["email"], subject, body):
                    with connect() as con:
                        # Atomic mark avoids a duplicate if scheduler overlaps.
                        con.execute(f"UPDATE appointments SET {field}=? WHERE id=? AND {field} IS NULL",
                                    (now_local().isoformat(), row["id"]))

@app.get("/api/health")
def health():
    return jsonify(status="ok", mode="demo" if DEMO_MODE else "configured", smtp_configured=smtp_ready())

@app.get("/api/specialties")
def specialties():
    grouped = get_doctors()
    with connect() as con:
        names = con.execute("SELECT name FROM specialties WHERE active=1 ORDER BY name").fetchall()
    return jsonify(specialties=[{"name":r["name"],"doctors":[d["full_name"] for d in grouped.get(r["name"], [])],
                                "professionals":grouped.get(r["name"], [])} for r in names])

@app.get("/api/availability")
def availability():
    specialty=request.args.get("specialty","").strip()
    day=request.args.get("date","").strip()
    doctor=request.args.get("doctor","").strip()
    catalog = get_doctors()
    if specialty not in catalog or not day: return jsonify(error="Especialidad o fecha inválida"),400
    try: target=date.fromisoformat(day)
    except ValueError: return jsonify(error="Fecha inválida"),400
    if target < now_local().date(): return jsonify(date=day,slots=[])
    if target.weekday()==6: return jsonify(date=day,slots=[],message="La clínica no agenda los domingos.")
    available_names = [d["full_name"] for d in catalog[specialty]]
    if not available_names: return jsonify(date=day, slots=[], message="Todavía no hay profesionales habilitados para esta especialidad.")
    chosen_doctor=doctor or available_names[0]
    if chosen_doctor not in available_names: return jsonify(error="El profesional no corresponde a la especialidad"),400
    booked=set()
    with connect() as con:
        rows=con.execute("SELECT starts_at FROM appointments WHERE status IN ('booked','arrived','called','in_consultation') AND doctor=?",
                         (chosen_doctor,)).fetchall()
    for row in rows:
        try:
            dt=datetime.fromisoformat(row["starts_at"]).astimezone(TZ)
            if dt.date()==target: booked.add(dt.strftime("%H:%M"))
        except ValueError: pass
    # En modo demo, crear una agenda visible; bloqueos ficticios para ilustrar disponibilidad.
    blocked_demo={"2026-10-26":["09:00","10:30"],"2026-10-27":["08:30","09:30","11:00"],"2026-10-28":["10:00"]}
    if DEMO_MODE: booked.update(blocked_demo.get(day, []))
    return jsonify(date=day, specialty=specialty, doctor=chosen_doctor,
                   slots=[slot for slot in SLOTS if slot not in booked],
                   demo=DEMO_MODE, message="Agenda de demostración" if DEMO_MODE else "Disponibilidad actual")

@app.post("/api/appointments")
def create_appointment():
    data=request.get_json(silent=True) or {}
    required=["first_names","last_names","dni","email","phone","specialty","doctor","date","time"]
    if any(not str(data.get(k,"")).strip() for k in required):
        return jsonify(error="Completá todos los campos obligatorios."),400
    dni=re.sub(r"\D","",str(data["dni"]))
    if not re.fullmatch(r"\d{7,9}",dni): return jsonify(error="DNI inválido."),400
    email=str(data["email"]).strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+",email): return jsonify(error="Correo electrónico inválido."),400
    first_names=str(data["first_names"]).strip()
    last_names=str(data["last_names"]).strip()
    phone=str(data["phone"]).strip()
    if not re.fullmatch(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ' -]{2,100}", first_names, re.UNICODE) or not re.fullmatch(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ' -]{2,100}", last_names, re.UNICODE):
        return jsonify(error="Ingresá nombres y apellidos válidos."),400
    if not re.fullmatch(r"\+?[0-9][0-9 ()-]{5,24}", phone): return jsonify(error="Teléfono inválido. Usá números y, si corresponde, un + inicial."),400
    specialty=str(data["specialty"]).strip()
    doctor=str(data["doctor"]).strip()
    catalog = get_doctors()
    if specialty not in catalog or doctor not in [d["full_name"] for d in catalog[specialty]]: return jsonify(error="Profesional y especialidad no coinciden."),400
    day=str(data["date"]); time=str(data["time"])
    if time not in SLOTS: return jsonify(error="Horario inválido."),400
    try: starts=datetime.fromisoformat(f"{day}T{time}:00").replace(tzinfo=TZ)
    except ValueError: return jsonify(error="Fecha u horario inválido."),400
    if starts <= now_local(): return jsonify(error="Elegí una fecha y hora futuras."),400
    if starts.weekday()==6: return jsonify(error="La clínica no agenda los domingos."),400
    if DEMO_MODE:
        # Demo persists fictional test reservations, clearly identified as non-production.
        pass
    doctor_id = doctor_name_to_id(doctor)
    if not doctor_id: return jsonify(error="El profesional ya no está habilitado."),409
    with connect() as con:
        patient = con.execute("SELECT * FROM patients WHERE dni=?", (dni,)).fetchone()
        if patient:
            patient_id = patient["id"]
            con.execute("UPDATE patients SET first_names=?,last_names=?,email=?,phone=? WHERE id=?",
                        (first_names,last_names,email,phone,patient_id))
        else:
            curp = con.execute("INSERT INTO patients(dni,first_names,last_names,email,phone,created_at) VALUES(?,?,?,?,?,?)",
                               (dni,first_names,last_names,email,phone,now_local().isoformat()))
            patient_id = curp.lastrowid
        existing=con.execute("SELECT id FROM appointments WHERE doctor=? AND starts_at=? AND status IN ('booked','arrived','called','in_consultation')",
                             (doctor,starts.isoformat())).fetchone()
        if existing: return jsonify(error="Ese horario acaba de ocuparse. Elegí otro."),409
        try:
            cur=con.execute("""INSERT INTO appointments(first_names,last_names,dni,email,phone,specialty,doctor,starts_at,status,created_at,patient_id,doctor_id)
                VALUES(?,?,?,?,?,?,?,?, 'booked',?,?,?)""",
                (first_names,last_names,dni,email,phone,specialty,doctor,starts.isoformat(),now_local().isoformat(),patient_id,doctor_id))
            aid=cur.lastrowid
        except sqlite3.IntegrityError:
            return jsonify(error="Ese horario ya no está disponible. Elegí otro."),409
    email_sent=send_confirmation(aid)
    with connect() as con:
        patient_row=con.execute("SELECT id,first_names,last_names,dni,email,phone FROM patients WHERE id=?",(patient_id,)).fetchone()
    return jsonify(ok=True, id=aid, patient_id=patient_id, patient=dict(patient_row), appointment={"specialty":specialty,"doctor":doctor,
        "date":starts.strftime("%Y-%m-%d"),"time":starts.strftime("%H:%M")},
        email_sent=email_sent, demo=DEMO_MODE,
        message="Turno de demostración guardado." if DEMO_MODE else "Turno registrado."),201

@app.get("/api/patients/lookup")
def patient_lookup():
    dni = re.sub(r"\D", "", request.args.get("dni", ""))
    if not re.fullmatch(r"\d{7,9}", dni): return jsonify(error="Ingresá un DNI válido de 7 a 9 números."),400
    with connect() as con: row=con.execute("SELECT id,first_names,last_names,dni,email,phone FROM patients WHERE dni=?",(dni,)).fetchone()
    return jsonify(found=bool(row), patient=dict(row) if row else None)

@app.get("/api/admin/doctors")
def admin_list_doctors():
    with connect() as con:
        rows=con.execute("""SELECT d.id,d.full_name,d.license_number,d.email,d.phone,d.room,d.active,d.created_at,
          GROUP_CONCAT(s.name, '||') AS specialties FROM doctors d
          LEFT JOIN doctor_specialties ds ON ds.doctor_id=d.id LEFT JOIN specialties s ON s.id=ds.specialty_id
          GROUP BY d.id ORDER BY d.id""").fetchall()
        specialties_rows=con.execute("SELECT id,name FROM specialties WHERE active=1 ORDER BY name").fetchall()
    items=[]
    for r in rows:
        item=dict(r); item["specialties"]=[x for x in (item.get("specialties") or "").split("||") if x]; items.append(item)
    return jsonify(doctors=items,specialties=[dict(x) for x in specialties_rows])

@app.post("/api/admin/doctors")
def admin_create_doctor():
    d=request.get_json(silent=True) or {}
    name=str(d.get("full_name","")).strip(); license_number=str(d.get("license_number","")).strip()
    email=str(d.get("email","")).strip().lower(); phone=str(d.get("phone","")).strip()
    room=str(d.get("room","Consultorio 1")).strip() or "Consultorio 1"
    specialty_ids=d.get("specialty_ids",[])
    if not re.fullmatch(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ.' -]{3,120}",name): return jsonify(error="Ingresá un nombre profesional válido."),400
    if not isinstance(specialty_ids,list) or not specialty_ids: return jsonify(error="Seleccioná al menos una especialidad."),400
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+",email): return jsonify(error="Correo inválido."),400
    with connect() as con:
        for sid in specialty_ids:
            if not con.execute("SELECT 1 FROM specialties WHERE id=? AND active=1",(sid,)).fetchone(): return jsonify(error="Una especialidad seleccionada no existe."),400
        if con.execute("SELECT 1 FROM doctors WHERE lower(full_name)=lower(?)",(name,)).fetchone(): return jsonify(error="Ya existe un médico con ese nombre. Editá el registro existente para agregar especialidades."),409
        cur=con.execute("INSERT INTO doctors(full_name,license_number,email,phone,room,active,created_at) VALUES(?,?,?,?,?,1,?)",(name,license_number,email,phone,room,now_local().isoformat()))
        doctor_id=cur.lastrowid
        for sid in specialty_ids: con.execute("INSERT INTO doctor_specialties(doctor_id,specialty_id) VALUES(?,?)",(doctor_id,sid))
        con.execute("INSERT OR IGNORE INTO doctor_status(doctor,room,is_free,updated_at) VALUES(?,?,0,?)",(name,room,now_local().isoformat()))
    return jsonify(ok=True,id=doctor_id,message=f"Médico dado de alta con ID {doctor_id}."),201

@app.put("/api/admin/doctors/<int:doctor_id>")
def admin_update_doctor(doctor_id):
    d=request.get_json(silent=True) or {}; name=str(d.get("full_name","")).strip(); license_number=str(d.get("license_number","")).strip()
    email=str(d.get("email","")).strip().lower(); phone=str(d.get("phone","")).strip(); room=str(d.get("room","Consultorio 1")).strip() or "Consultorio 1"
    specialty_ids=d.get("specialty_ids",[])
    if not name or not isinstance(specialty_ids,list) or not specialty_ids: return jsonify(error="Nombre y al menos una especialidad son obligatorios."),400
    with connect() as con:
        old=con.execute("SELECT * FROM doctors WHERE id=?",(doctor_id,)).fetchone()
        if not old: return jsonify(error="Médico no encontrado."),404
        if con.execute("SELECT 1 FROM doctors WHERE lower(full_name)=lower(?) AND id<>?",(name,doctor_id)).fetchone(): return jsonify(error="Ya existe otro médico con ese nombre."),409
        if any(not con.execute("SELECT 1 FROM specialties WHERE id=? AND active=1",(sid,)).fetchone() for sid in specialty_ids): return jsonify(error="Especialidad inválida."),400
        old_name=old["full_name"]
        con.execute("UPDATE doctors SET full_name=?,license_number=?,email=?,phone=?,room=? WHERE id=?",(name,license_number,email,phone,room,doctor_id))
        con.execute("UPDATE appointments SET doctor=? WHERE doctor_id=?",(name,doctor_id))
        con.execute("UPDATE doctor_status SET doctor=?,room=? WHERE doctor=?",(name,room,old_name))
        con.execute("DELETE FROM doctor_specialties WHERE doctor_id=?",(doctor_id,))
        for sid in specialty_ids: con.execute("INSERT INTO doctor_specialties(doctor_id,specialty_id) VALUES(?,?)",(doctor_id,sid))
    return jsonify(ok=True,message="Datos del médico actualizados; se conservó su ID.")

@app.post("/api/admin/doctors/<int:doctor_id>/status")
def admin_doctor_status_set(doctor_id):
    d=request.get_json(silent=True) or {}; active=1 if d.get("active") is True else 0
    with connect() as con:
        row=con.execute("SELECT * FROM doctors WHERE id=?",(doctor_id,)).fetchone()
        if not row: return jsonify(error="Médico no encontrado."),404
        con.execute("UPDATE doctors SET active=? WHERE id=?",(active,doctor_id))
    return jsonify(ok=True,message="Médico activado." if active else "Médico dado de baja lógica. Su ID e historial se conservan.")

@app.post("/api/bot/appointment-lookup")
def bot_appointment_lookup():
    data=request.get_json(silent=True) or {}
    dni=re.sub(r"\D","",str(data.get("dni","")))
    if not re.fullmatch(r"\d{7,9}",dni): return jsonify(error="Ingresá un DNI válido."),400
    # Demo lookup uses a fixed sample. Real mode refuses disclosure until OTP verification exists.
    if DEMO_MODE:
        matching=[a for a in DEMO_APPOINTMENTS if a["dni"]==dni and datetime.fromisoformat(a["starts_at"])>now_local()]
        return jsonify(found=bool(matching), appointments=[{
            "specialty":a["specialty"],"doctor":a["doctor"],
            "date":datetime.fromisoformat(a["starts_at"]).astimezone(TZ).strftime("%d/%m/%Y"),
            "time":datetime.fromisoformat(a["starts_at"]).astimezone(TZ).strftime("%H:%M"),
            "demo":True} for a in matching], demo=True)
    return jsonify(error="Para proteger tus datos, primero debemos verificar tu identidad con un código enviado a tu correo o teléfono registrado."),403

@app.post("/api/appointments/<int:appointment_id>/cancel")
def cancel_appointment(appointment_id):
    # Cancelación pública no habilitada sin verificación del titular.
    return jsonify(error="Para cancelar el turno, contactá a secretaría. La cancelación en línea requiere verificar tu identidad."),403

# --- Paneles institucionales (demo con datos ficticios) ---
# IMPORTANTE: estas rutas son para demostración. No publicar con datos reales hasta implementar
# autenticación robusta, autorización por rol, sesiones seguras, CSRF/rate-limit y auditoría reforzada.
from werkzeug.utils import secure_filename
from flask import send_from_directory
import uuid

@app.get("/api/admin/appointments")
def admin_appointments():
    day=request.args.get("date", "").strip()
    query="SELECT * FROM appointments"
    params=[]
    if day:
        query += " WHERE substr(starts_at,1,10)=?"
        params.append(day)
    query += " ORDER BY starts_at DESC LIMIT 300"
    with connect() as con:
        rows=con.execute(query,params).fetchall()
    return jsonify(appointments=[dict(r) for r in rows], demo=DEMO_MODE)

@app.get("/api/admin/patients")
def admin_patients():
    q=request.args.get("q","").strip()
    with connect() as con:
        if q:
            like=f"%{q}%"
            rows=con.execute("SELECT * FROM patients WHERE dni LIKE ? OR first_names LIKE ? OR last_names LIKE ? ORDER BY last_names LIMIT 100",(like,like,like)).fetchall()
        else:
            rows=con.execute("SELECT * FROM patients ORDER BY last_names LIMIT 100").fetchall()
    return jsonify(patients=[dict(r) for r in rows], demo=DEMO_MODE)

@app.post("/api/admin/patients")
def admin_create_patient():
    d=request.get_json(silent=True) or {}
    first=str(d.get("first_names","")).strip(); last=str(d.get("last_names","")).strip()
    dni=re.sub(r"\D","",str(d.get("dni","")))
    if not first or not last or not re.fullmatch(r"\d{7,9}",dni): return jsonify(error="Completá nombres, apellidos y un DNI válido."),400
    with connect() as con:
        existing=con.execute("SELECT id FROM patients WHERE dni=?",(dni,)).fetchone()
        if existing:
            con.execute("UPDATE patients SET first_names=?,last_names=?,email=?,phone=? WHERE id=?",(first,last,str(d.get("email","")),str(d.get("phone","")),existing["id"]))
            patient_id=existing["id"]
            return jsonify(ok=True,id=patient_id,message=f"Paciente actualizado. ID de paciente: {patient_id}."),200
        cur=con.execute("INSERT INTO patients(dni,first_names,last_names,email,phone,created_at) VALUES(?,?,?,?,?,?)",(dni,first,last,str(d.get("email","")),str(d.get("phone","")),now_local().isoformat()))
        patient_id=cur.lastrowid
    return jsonify(ok=True,id=patient_id,message=f"Paciente de prueba registrado con ID {patient_id}."),201

@app.post("/api/admin/overbooking")
def admin_create_overbooking():
    """Registra el paciente por DNI y crea un sobreturno vinculado a su ID permanente."""
    d = request.get_json(silent=True) or {}
    first = str(d.get("first_names", "")).strip()
    last = str(d.get("last_names", "")).strip()
    dni = re.sub(r"\D", "", str(d.get("dni", "")))
    email = str(d.get("email", "")).strip().lower()
    phone = str(d.get("phone", "")).strip()
    doctor = str(d.get("doctor", "")).strip()

    catalog = get_doctors()
    known = {doc["full_name"] for docs in catalog.values() for doc in docs}
    if not first or not last or not re.fullmatch(r"\d{7,9}", dni):
        return jsonify(error="Completá nombres, apellidos y un DNI válido."), 400
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return jsonify(error="El correo electrónico no tiene un formato válido."), 400
    if doctor not in known:
        return jsonify(error="Seleccioná un médico válido para el sobreturno."), 400

    specialty = next((specialty for specialty, docs in catalog.items()
                      if any(doc["full_name"] == doctor for doc in docs)), "Atención presencial")
    doctor_id = doctor_name_to_id(doctor)
    arrived_at = now_local().isoformat(timespec="microseconds")
    patient_created = False

    # El registro de paciente y el sobreturno se guardan juntos. El ID del paciente
    # solo se genera si el DNI no existía; los pacientes existentes conservan su ID.
    with connect() as con:
        patient = con.execute("SELECT id,email,phone FROM patients WHERE dni=?", (dni,)).fetchone()
        if patient:
            patient_id = patient["id"]
            con.execute("""UPDATE patients SET first_names=?, last_names=?,
                email=CASE WHEN ? <> '' THEN ? ELSE email END,
                phone=CASE WHEN ? <> '' THEN ? ELSE phone END
                WHERE id=?""", (first, last, email, email, phone, phone, patient_id))
            saved = con.execute("SELECT email,phone FROM patients WHERE id=?", (patient_id,)).fetchone()
            saved_email = saved["email"]
            saved_phone = saved["phone"]
        else:
            cur_patient = con.execute(
                "INSERT INTO patients(dni,first_names,last_names,email,phone,created_at) VALUES(?,?,?,?,?,?)",
                (dni, first, last, email, phone, arrived_at))
            patient_id = cur_patient.lastrowid
            patient_created = True
            saved_email, saved_phone = email, phone

        try:
            cur = con.execute("""INSERT INTO appointments
                (first_names,last_names,dni,email,phone,specialty,doctor,starts_at,status,
                 appointment_type,created_at,patient_id,doctor_id)
                VALUES(?,?,?,?,?,?,?,?, 'arrived','sobreturno',?,?,?)""",
                (first, last, dni, saved_email, saved_phone, specialty, doctor,
                 arrived_at, arrived_at, patient_id, doctor_id))
        except sqlite3.IntegrityError:
            return jsonify(error="No se pudo registrar el sobreturno. Actualizá la agenda e intentá nuevamente."), 409
        appointment_id = cur.lastrowid

    patient_message = "Se creó el registro del paciente" if patient_created else "Se reutilizó el registro existente del paciente"
    return jsonify(ok=True, id=appointment_id, patient_id=patient_id,
                   patient_created=patient_created, doctor_id=doctor_id, doctor=doctor,
                   specialty=specialty, appointment_type="sobreturno", status="arrived",
                   message=f"Sobreturno registrado. {patient_message}: ID de paciente {patient_id}. Ya figura como llegado y puede llamarse desde Administración."), 201


@app.post("/api/admin/appointments/<int:aid>/status")
def admin_appointment_status(aid):
    d=request.get_json(silent=True) or {}; status=str(d.get("status",""))
    allowed={"booked","arrived","called","in_consultation","attended","cancelled","rescheduled"}
    if status not in allowed: return jsonify(error="Estado inválido."),400
    with connect() as con:
        cur=con.execute("UPDATE appointments SET status=? WHERE id=?",(status,aid))
        if cur.rowcount==0: return jsonify(error="No se encontró el turno."),404
    return jsonify(ok=True,status=status)

@app.post("/api/admin/appointments/<int:aid>/reschedule")
def admin_reschedule(aid):
    d=request.get_json(silent=True) or {}; day=str(d.get("date","")); tm=str(d.get("time",""))
    if tm not in SLOTS: return jsonify(error="Horario inválido."),400
    try: starts=datetime.fromisoformat(f"{day}T{tm}:00").replace(tzinfo=TZ)
    except ValueError: return jsonify(error="Fecha inválida."),400
    if starts<=now_local() or starts.weekday()==6: return jsonify(error="Elegí una fecha futura habilitada."),400
    with connect() as con:
        row=con.execute("SELECT * FROM appointments WHERE id=?",(aid,)).fetchone()
        if not row: return jsonify(error="No se encontró el turno."),404
        busy=con.execute("SELECT id FROM appointments WHERE doctor=? AND starts_at=? AND status IN ('booked','arrived','called','in_consultation') AND id<>?",(row['doctor'],starts.isoformat(),aid)).fetchone()
        if busy: return jsonify(error="Ese horario ya está ocupado."),409
        con.execute("UPDATE appointments SET starts_at=?,status='booked',reminder_24h_sent_at=NULL,reminder_3h_sent_at=NULL,confirmation_sent_at=NULL WHERE id=?",(starts.isoformat(),aid))
    # El correo se envía de nuevo con el horario actualizado; si SMTP no está configurado, se informa.
    sent=send_confirmation(aid)
    return jsonify(ok=True,email_sent=sent,message="Turno reprogramado."+(" Correo enviado." if sent else " Configurá el correo para enviar la notificación."))

@app.get("/api/doctor/status")
def doctor_status_get():
    doctor=request.args.get("doctor", "").strip()
    if not doctor: return jsonify(error="Seleccioná un profesional."),400
    with connect() as con:
        known=con.execute("SELECT id,room FROM doctors WHERE full_name=? AND active=1",(doctor,)).fetchone()
        if not known: return jsonify(error="El profesional no está activo."),404
        row=con.execute("SELECT * FROM doctor_status WHERE doctor=?",(doctor,)).fetchone()
    return jsonify(doctor=doctor, status=dict(row) if row else {"doctor":doctor,"room":known["room"],"is_free":0,"updated_at":None}, demo=DEMO_MODE)

@app.post("/api/doctor/status")
def doctor_status_set():
    d=request.get_json(silent=True) or {}
    doctor=str(d.get("doctor"," ")).strip()
    room=str(d.get("room","Consultorio 1")).strip()[:80]
    is_free=1 if d.get("is_free") is True else 0
    if not doctor or not room: return jsonify(error="Seleccioná un profesional y un consultorio."),400
    now=now_local().isoformat(); called=None
    with connect() as con:
        known=con.execute("SELECT id FROM doctors WHERE full_name=? AND active=1",(doctor,)).fetchone()
        if not known: return jsonify(error="Seleccioná un profesional activo."),400
        previous=con.execute("SELECT * FROM doctor_status WHERE doctor=?",(doctor,)).fetchone()
        if is_free and previous and not previous["is_free"]:
            current=con.execute("SELECT id FROM appointments WHERE doctor=? AND status IN ('called','in_consultation') ORDER BY id DESC LIMIT 1",(doctor,)).fetchone()
            if current: con.execute("UPDATE appointments SET status='attended' WHERE id=?",(current["id"],))
        if not is_free:
            con.execute("UPDATE appointments SET status='in_consultation' WHERE doctor=? AND status='called'",(doctor,))
        con.execute("INSERT INTO doctor_status(doctor,room,is_free,updated_at) VALUES(?,?,?,?) ON CONFLICT(doctor) DO UPDATE SET room=excluded.room,is_free=excluded.is_free,updated_at=excluded.updated_at",(doctor,room,is_free,now))
        if is_free:
            # Al liberar el consultorio, el backend llama automáticamente al siguiente paciente ya registrado como llegado.
            day=now_local().date().isoformat()
            row=con.execute("SELECT * FROM appointments WHERE doctor=? AND status='arrived' AND substr(starts_at,1,10)=? ORDER BY starts_at ASC,id ASC LIMIT 1",(doctor,day)).fetchone()
            if row:
                patient_name=(row["first_names"]+" "+row["last_names"]).strip()
                con.execute("INSERT INTO call_events(appointment_id,patient_name,room,called_at,status) VALUES(?,?,?,?,'called')",(row["id"],patient_name,room,now))
                con.execute("UPDATE appointments SET status='called' WHERE id=?",(row["id"],))
                con.execute("UPDATE doctor_status SET is_free=0,updated_at=? WHERE doctor=?",(now,doctor))
                called={"appointment_id":row["id"],"patient_name":patient_name,"room":room}
    if called:
        return jsonify(ok=True,doctor=doctor,room=room,is_free=False,called=called,message=f"Llamado automático: {called['patient_name']} — {room}. El consultorio pasó a ocupado.")
    if is_free:
        return jsonify(ok=True,doctor=doctor,room=room,is_free=True,message="Consultorio libre. No hay pacientes marcados como llegados para llamar.")
    return jsonify(ok=True,doctor=doctor,room=room,is_free=False,message="Consultorio ocupado. No se llamará a otro paciente hasta liberarlo.")

@app.get("/api/admin/doctor-status")
def admin_doctor_status():
    with connect() as con:
        rows=con.execute("SELECT * FROM doctor_status ORDER BY doctor").fetchall()
        statuses={r["doctor"]:dict(r) for r in rows}
        doctors=[]
        active_doctors=con.execute("SELECT full_name,room,id FROM doctors WHERE active=1 ORDER BY full_name").fetchall()
        for doctor_record in active_doctors:
                name=doctor_record["full_name"]
                item=statuses.get(name,{"doctor":name,"room":doctor_record["room"] or "Consultorio 1","is_free":0,"updated_at":None,"doctor_id":doctor_record["id"]})
                last=con.execute("""SELECT c.id,c.appointment_id,c.patient_name,c.room,c.called_at,a.status,a.starts_at
                    FROM call_events c JOIN appointments a ON a.id=c.appointment_id
                    WHERE a.doctor=? ORDER BY c.id DESC LIMIT 1""",(name,)).fetchone()
                if last:
                    count=con.execute("SELECT COUNT(*) AS n FROM call_events WHERE appointment_id=?",(last["appointment_id"],)).fetchone()["n"]
                    item.update({"last_call":dict(last),"call_count":count})
                else:
                    item.update({"last_call":None,"call_count":0})
                doctors.append(item)
    return jsonify(doctors=doctors,demo=DEMO_MODE)

@app.post("/api/admin/doctor/<path:doctor>/call-next")
def admin_call_next(doctor):
    doctor=doctor.strip()
    d=request.get_json(silent=True) or {}
    room=str(d.get("room","")).strip()[:80]
    day=str(d.get("date",now_local().date().isoformat())).strip()
    try: date.fromisoformat(day)
    except ValueError: return jsonify(error="Fecha inválida para buscar el siguiente paciente."),400
    with connect() as con:
        status=con.execute("SELECT * FROM doctor_status WHERE doctor=?",(doctor,)).fetchone()
        if not status or not status["is_free"]:
            return jsonify(error="El profesional todavía no marcó su consultorio como libre."),409
        if not room: room=status["room"] or "Consultorio 1"
        # Cada paciente debe ser anunciado al menos dos veces antes de habilitar el siguiente llamado.
        last=con.execute("""SELECT c.appointment_id,a.status FROM call_events c
            JOIN appointments a ON a.id=c.appointment_id
            WHERE a.doctor=? AND substr(a.starts_at,1,10)=? ORDER BY c.id DESC LIMIT 1""",(doctor,day)).fetchone()
        if last and last["status"] == "called":
            count=con.execute("SELECT COUNT(*) AS n FROM call_events WHERE appointment_id=?",(last["appointment_id"],)).fetchone()["n"]
            if count < 2:
                return jsonify(error="Antes de llamar al siguiente paciente, repetí el llamado actual al menos una segunda vez."),409
        # Solo llamar pacientes que recepción ya marcó como llegados; evitar llamar a alguien que aún no está.
        row=con.execute("SELECT * FROM appointments WHERE doctor=? AND status='arrived' AND substr(starts_at,1,10)=? ORDER BY starts_at ASC,id ASC LIMIT 1",(doctor,day)).fetchone()
        if not row:
            return jsonify(error="No hay pacientes marcados como llegados para este profesional hoy."),404
        name=(row["first_names"]+" "+row["last_names"]).strip()
        con.execute("INSERT INTO call_events(appointment_id,patient_name,room,called_at,status) VALUES(?,?,?,?,?)",(row["id"],name,room,now_local().isoformat(),"called"))
        con.execute("UPDATE appointments SET status='called' WHERE id=?",(row["id"],))
        con.execute("UPDATE doctor_status SET is_free=0,updated_at=? WHERE doctor=?",(now_local().isoformat(),doctor))
    return jsonify(ok=True,appointment_id=row["id"],patient_name=name,room=room,message=f"Llamado publicado: {name} — {room}. El consultorio pasó a ocupado."),201

@app.post("/api/admin/doctor/<path:doctor>/repeat-call")
def admin_repeat_call(doctor):
    doctor=doctor.strip()
    d=request.get_json(silent=True) or {}
    day=str(d.get("date",now_local().date().isoformat())).strip()
    try: date.fromisoformat(day)
    except ValueError: return jsonify(error="Fecha inválida para repetir el llamado."),400
    with connect() as con:
        row=con.execute("""SELECT c.appointment_id,c.patient_name,c.room,a.status
            FROM call_events c JOIN appointments a ON a.id=c.appointment_id
            WHERE a.doctor=? AND substr(a.starts_at,1,10)=? ORDER BY c.id DESC LIMIT 1""",(doctor,day)).fetchone()
        if not row or row["status"] != "called":
            return jsonify(error="No hay un paciente con llamado activo para repetir."),404
        count=con.execute("SELECT COUNT(*) AS n FROM call_events WHERE appointment_id=?",(row["appointment_id"],)).fetchone()["n"]
        if count >= 2:
            return jsonify(error="Este paciente ya recibió dos llamados. Podés continuar cuando el consultorio esté libre."),409
        called_at=now_local().isoformat()
        con.execute("INSERT INTO call_events(appointment_id,patient_name,room,called_at,status) VALUES(?,?,?,?,?)",
                    (row["appointment_id"],row["patient_name"],row["room"],called_at,"called"))
        new_count=count+1
    return jsonify(ok=True,appointment_id=row["appointment_id"],patient_name=row["patient_name"],room=row["room"],call_count=new_count,message=f"Llamado {new_count}/2 publicado para {row['patient_name']} en {row['room']}.")

@app.get("/api/doctor/appointments")
def doctor_appointments():
    doctor=request.args.get("doctor", "").strip()
    if not doctor: return jsonify(appointments=[],doctor="",demo=DEMO_MODE)
    with connect() as con: rows=con.execute("SELECT * FROM appointments WHERE doctor=? ORDER BY starts_at DESC LIMIT 200",(doctor,)).fetchall()
    return jsonify(appointments=[dict(r) for r in rows],doctor=doctor,demo=DEMO_MODE)

@app.get("/api/doctor/patient/<dni>")
def doctor_patient(dni):
    dni=re.sub(r"\D","",dni)
    with connect() as con:
        patient=con.execute("SELECT * FROM patients WHERE dni=?",(dni,)).fetchone()
        notes=con.execute("SELECT * FROM clinical_notes WHERE dni=? ORDER BY created_at DESC",(dni,)).fetchall()
        studies=con.execute("SELECT id,dni,title,study_type,professional,status,published,created_at,published_at,delivered_at FROM studies WHERE dni=? ORDER BY created_at DESC",(dni,)).fetchall()
    return jsonify(patient=dict(patient) if patient else None,notes=[dict(r) for r in notes],studies=[dict(r) for r in studies],demo=DEMO_MODE)

@app.post("/api/doctor/notes")
def doctor_add_note():
    d=request.get_json(silent=True) or {}; dni=re.sub(r"\D","",str(d.get("dni",""))); note=str(d.get("note","")).strip(); doctor=str(d.get("doctor","Profesional de demo"))
    if not re.fullmatch(r"\d{7,9}",dni) or not note: return jsonify(error="DNI y nota son obligatorios."),400
    with connect() as con:
        if not con.execute("SELECT 1 FROM patients WHERE dni=?",(dni,)).fetchone(): return jsonify(error="Paciente no encontrado en la demo."),404
        con.execute("INSERT INTO clinical_notes(dni,doctor,note,created_at) VALUES(?,?,?,?)",(dni,doctor,note,now_local().isoformat()))
    return jsonify(ok=True,message="Nota de demostración guardada."),201

@app.post("/api/doctor/studies")
def doctor_add_study():
    d=request.get_json(silent=True) or {}; dni=re.sub(r"\D","",str(d.get("dni",""))); title=str(d.get("title","")).strip(); typ=str(d.get("study_type","Laboratorio")).strip(); prof=str(d.get("professional","Profesional de demo")).strip(); status=str(d.get("status","processing"))
    if not re.fullmatch(r"\d{7,9}",dni) or not title: return jsonify(error="DNI y nombre del estudio son obligatorios."),400
    if status not in {"processing","available","delivered"}: status="processing"
    with connect() as con:
        if not con.execute("SELECT 1 FROM patients WHERE dni=?",(dni,)).fetchone(): return jsonify(error="Paciente no encontrado. Primero registralo desde Administración."),404
        cur=con.execute("INSERT INTO studies(dni,title,study_type,professional,status,published,created_at,published_at,delivered_at) VALUES(?,?,?,?,?,?,?,?,?)",(dni,title,typ,prof,status,1 if status=="available" else 0,now_local().isoformat(),now_local().isoformat() if status=="available" else None,now_local().isoformat() if status=="delivered" else None))
        sid=cur.lastrowid
    return jsonify(ok=True,id=sid,message="Estudio de demostración guardado."),201

@app.get("/api/patient/studies")
def patient_studies():
    # Solo para datos ficticios de la demo; sustituir por sesión verificada antes de producción.
    dni=re.sub(r"\D","",request.args.get("dni",""))
    if not re.fullmatch(r"\d{7,9}",dni): return jsonify(error="Ingresá un DNI válido."),400
    with connect() as con:
        patient=con.execute("SELECT first_names,last_names,dni FROM patients WHERE dni=?",(dni,)).fetchone()
        rows=con.execute("SELECT id,title,study_type,professional,status,published,created_at,published_at,delivered_at FROM studies WHERE dni=? AND published=1 ORDER BY created_at DESC",(dni,)).fetchall()
    if not patient: return jsonify(error="No encontramos ese paciente en la demo. Probá con el DNI 30123456."),404
    return jsonify(patient=dict(patient),studies=[dict(r) for r in rows],demo=True)

@app.get("/api/display/calls")
def display_calls():
    with connect() as con: rows=con.execute("SELECT * FROM call_events ORDER BY id DESC LIMIT 5").fetchall()
    return jsonify(calls=[dict(r) for r in rows],demo=DEMO_MODE)

@app.post("/api/admin/appointments/<int:aid>/call")
def call_patient(aid):
    d=request.get_json(silent=True) or {}; room=str(d.get("room","Consultorio 1")).strip()[:80]
    with connect() as con:
        row=con.execute("SELECT * FROM appointments WHERE id=?",(aid,)).fetchone()
        if not row: return jsonify(error="No se encontró el turno."),404
        name=(row['first_names']+" "+row['last_names']).strip()
        con.execute("INSERT INTO call_events(appointment_id,patient_name,room,called_at,status) VALUES(?,?,?,?,?)",(aid,name,room,now_local().isoformat(),"called"))
        con.execute("UPDATE appointments SET status='called' WHERE id=?",(aid,))
        con.execute("INSERT INTO doctor_status(doctor,room,is_free,updated_at) VALUES(?,?,0,?) ON CONFLICT(doctor) DO UPDATE SET room=excluded.room,is_free=0,updated_at=excluded.updated_at",(row["doctor"],room,now_local().isoformat()))
    return jsonify(ok=True,patient_name=name,room=room,message="Llamado publicado en la pantalla."),201

@app.post("/api/admin/studies/<int:sid>/status")
def admin_study_status(sid):
    d=request.get_json(silent=True) or {}; status=str(d.get("status",""))
    if status not in {"processing","available","delivered"}: return jsonify(error="Estado de estudio inválido."),400
    now=now_local().isoformat()
    with connect() as con:
        row=con.execute("SELECT id FROM studies WHERE id=?",(sid,)).fetchone()
        if not row: return jsonify(error="Estudio no encontrado."),404
        con.execute("UPDATE studies SET status=?,published=?,published_at=?,delivered_at=? WHERE id=?",(status,1 if status in {"available","delivered"} else 0,now if status in {"available","delivered"} else None,now if status=="delivered" else None,sid))
    return jsonify(ok=True,message="Estado del estudio actualizado.")


def start_scheduler():
    scheduler=BackgroundScheduler(timezone=TZ)
    scheduler.add_job(process_reminders,"interval",minutes=5,id="appointment_reminders",replace_existing=True,
                      max_instances=1,coalesce=True)
    scheduler.start()
    return scheduler

init_db()
scheduler=None
# En despliegues WSGI, mantener RUN_SCHEDULER=false y ejecutar el scheduler en un proceso único separado.
if os.getenv("RUN_SCHEDULER","false").lower()=="true" and __name__ != "__main__":
    try: scheduler=start_scheduler()
    except Exception: log.exception("No se pudo iniciar scheduler")

if __name__=="__main__":
    scheduler=start_scheduler()
    log.info("Clínica backend activo en modo %s", "DEMO" if DEMO_MODE else "PRODUCCIÓN")
    app.run(host=os.getenv("HOST","127.0.0.1"),port=int(os.getenv("PORT","5000")),debug=False)
