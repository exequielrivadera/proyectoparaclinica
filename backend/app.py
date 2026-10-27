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
allowed_origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://127.0.0.1:5500,http://localhost:5500,http://127.0.0.1:8000,http://localhost:8000").split(",") if x.strip()]
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
          created_at TEXT NOT NULL, confirmation_sent_at TEXT,
          reminder_24h_sent_at TEXT, reminder_3h_sent_at TEXT,
          UNIQUE(doctor, starts_at)
        );
        CREATE INDEX IF NOT EXISTS idx_appointments_dni ON appointments(dni, starts_at);
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
        # Demo patient data only. These records are fictional and safe for a walkthrough.
        con.execute("INSERT OR IGNORE INTO patients(dni,first_names,last_names,email,phone,created_at) VALUES(?,?,?,?,?,?)",
                    ("30123456","Juan","Pérez","juan.demo@example.com","3804000000",now_local().isoformat()))
        con.execute("INSERT OR IGNORE INTO patients(dni,first_names,last_names,email,phone,created_at) VALUES(?,?,?,?,?,?)",
                    ("28987654","María","Gómez","maria.demo@example.com","3804111111",now_local().isoformat()))
        con.execute("INSERT OR IGNORE INTO studies(dni,title,study_type,professional,status,published,created_at,published_at) VALUES(?,?,?,?,?,?,?,?)",
                    ("30123456","Análisis clínico de demostración","Laboratorio","Dra. Ana López","available",1,now_local().isoformat(),now_local().isoformat()))

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
    return jsonify(specialties=[{"name":k,"doctors":v} for k,v in DOCTORS.items()])

@app.get("/api/availability")
def availability():
    specialty=request.args.get("specialty","").strip()
    day=request.args.get("date","").strip()
    doctor=request.args.get("doctor","").strip()
    if specialty not in DOCTORS or not day: return jsonify(error="Especialidad o fecha inválida"),400
    try: target=date.fromisoformat(day)
    except ValueError: return jsonify(error="Fecha inválida"),400
    if target < now_local().date(): return jsonify(date=day,slots=[])
    if target.weekday()==6: return jsonify(date=day,slots=[],message="La clínica no agenda los domingos.")
    chosen_doctor=doctor or DOCTORS[specialty][0]
    if chosen_doctor not in DOCTORS[specialty]: return jsonify(error="El profesional no corresponde a la especialidad"),400
    booked=set()
    with connect() as con:
        rows=con.execute("SELECT starts_at FROM appointments WHERE status='booked' AND doctor=?",
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
    specialty=str(data["specialty"]).strip()
    doctor=str(data["doctor"]).strip()
    if specialty not in DOCTORS or doctor not in DOCTORS[specialty]: return jsonify(error="Profesional y especialidad no coinciden."),400
    day=str(data["date"]); time=str(data["time"])
    if time not in SLOTS: return jsonify(error="Horario inválido."),400
    try: starts=datetime.fromisoformat(f"{day}T{time}:00").replace(tzinfo=TZ)
    except ValueError: return jsonify(error="Fecha u horario inválido."),400
    if starts <= now_local(): return jsonify(error="Elegí una fecha y hora futuras."),400
    if starts.weekday()==6: return jsonify(error="La clínica no agenda los domingos."),400
    if DEMO_MODE:
        # Demo persists fictional test reservations, clearly identified as non-production.
        pass
    with connect() as con:
        existing=con.execute("SELECT id FROM appointments WHERE doctor=? AND starts_at=? AND status='booked'",
                             (doctor,starts.isoformat())).fetchone()
        if existing: return jsonify(error="Ese horario acaba de ocuparse. Elegí otro."),409
        try:
            cur=con.execute("""INSERT INTO appointments(first_names,last_names,dni,email,phone,specialty,doctor,starts_at,status,created_at)
                VALUES(?,?,?,?,?,?,?,?, 'booked',?)""",
                (str(data["first_names"]).strip(),str(data["last_names"]).strip(),dni,email,str(data["phone"]).strip(),
                 specialty,doctor,starts.isoformat(),now_local().isoformat()))
            aid=cur.lastrowid
        except sqlite3.IntegrityError:
            return jsonify(error="Ese horario ya no está disponible. Elegí otro."),409
    with connect() as con:
        con.execute("INSERT OR IGNORE INTO patients(dni,first_names,last_names,email,phone,created_at) VALUES(?,?,?,?,?,?)",(dni,str(data["first_names"]).strip(),str(data["last_names"]).strip(),email,str(data["phone"]).strip(),now_local().isoformat()))
    email_sent=send_confirmation(aid)
    return jsonify(ok=True, id=aid, appointment={"specialty":specialty,"doctor":doctor,
        "date":starts.strftime("%Y-%m-%d"),"time":starts.strftime("%H:%M")},
        email_sent=email_sent, demo=DEMO_MODE,
        message="Turno de demostración guardado." if DEMO_MODE else "Turno registrado."),201

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
    try:
        with connect() as con:
            con.execute("INSERT INTO patients(dni,first_names,last_names,email,phone,created_at) VALUES(?,?,?,?,?,?)",(dni,first,last,str(d.get("email","")),str(d.get("phone","")),now_local().isoformat()))
    except sqlite3.IntegrityError: return jsonify(error="Ya existe un paciente con ese DNI."),409
    return jsonify(ok=True,message="Paciente de prueba registrado."),201

@app.post("/api/admin/appointments/<int:aid>/status")
def admin_appointment_status(aid):
    d=request.get_json(silent=True) or {}; status=str(d.get("status",""))
    allowed={"booked","arrived","called","attended","cancelled","rescheduled"}
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
        busy=con.execute("SELECT id FROM appointments WHERE doctor=? AND starts_at=? AND status IN ('booked','arrived','called') AND id<>?",(row['doctor'],starts.isoformat(),aid)).fetchone()
        if busy: return jsonify(error="Ese horario ya está ocupado."),409
        con.execute("UPDATE appointments SET starts_at=?,status='booked',reminder_24h_sent_at=NULL,reminder_3h_sent_at=NULL,confirmation_sent_at=NULL WHERE id=?",(starts.isoformat(),aid))
    # El correo se envía de nuevo con el horario actualizado; si SMTP no está configurado, se informa.
    sent=send_confirmation(aid)
    return jsonify(ok=True,email_sent=sent,message="Turno reprogramado."+(" Correo enviado." if sent else " Configurá el correo para enviar la notificación."))

@app.get("/api/doctor/status")
def doctor_status_get():
    doctor=request.args.get("doctor",DOCTORS["Cardiología"][0]).strip()
    with connect() as con:
        row=con.execute("SELECT * FROM doctor_status WHERE doctor=?",(doctor,)).fetchone()
    return jsonify(doctor=doctor, status=dict(row) if row else {"doctor":doctor,"room":"Consultorio 1","is_free":0,"updated_at":None}, demo=DEMO_MODE)

@app.post("/api/doctor/status")
def doctor_status_set():
    d=request.get_json(silent=True) or {}
    doctor=str(d.get("doctor","")).strip()
    room=str(d.get("room","Consultorio 1")).strip()[:80]
    is_free=1 if d.get("is_free") is True else 0
    known={name for names in DOCTORS.values() for name in names}
    if not doctor or doctor not in known:
        return jsonify(error="Seleccioná un profesional registrado en la demo."),400
    if not room:
        return jsonify(error="Indicá el consultorio."),400
    with connect() as con:
        con.execute("INSERT INTO doctor_status(doctor,room,is_free,updated_at) VALUES(?,?,?,?) ON CONFLICT(doctor) DO UPDATE SET room=excluded.room,is_free=excluded.is_free,updated_at=excluded.updated_at",(doctor,room,is_free,now_local().isoformat()))
    return jsonify(ok=True,doctor=doctor,room=room,is_free=bool(is_free),message=("Consultorio marcado como libre. Administración ya puede verlo." if is_free else "Estado actualizado: consultorio ocupado."))

@app.get("/api/admin/doctor-status")
def admin_doctor_status():
    with connect() as con:
        rows=con.execute("SELECT * FROM doctor_status ORDER BY doctor").fetchall()
        statuses={r["doctor"]:dict(r) for r in rows}
        doctors=[]
        for names in DOCTORS.values():
            for name in names:
                item=statuses.get(name,{"doctor":name,"room":"Consultorio 1","is_free":0,"updated_at":None})
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
    doctor=request.args.get("doctor",DOCTORS["Cardiología"][0])
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
