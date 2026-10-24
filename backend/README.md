# Backend inicial (no productivo)

Este directorio contiene una base de referencia en Flask/SQLite para orientar el desarrollo. No está conectado a la interfaz pública y no debe usarse con pacientes reales.

## Preparación local en PowerShell

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Editar `.env` y colocar una `SECRET_KEY` aleatoria larga. Luego:

```powershell
py app.py
```

Probar `http://127.0.0.1:5000/api/health`.

## Pendiente antes de producción

- Alta segura del primer administrador y control de acceso.
- Activación de cuentas por código temporal verificado, expiración y uso único.
- Limitación de intentos, protección CSRF, cookies seguras, HTTPS y gestión de sesiones.
- Verificación de correo/celular y consentimiento versionado.
- Agenda configurable, transacciones y prevención de doble reserva.
- Servicio SMTP, reintentos, cola de mensajes, plantillas y registro de entrega.
- Políticas de autorización clínica, gestión de relaciones médico-paciente y permisos de publicación.
- Escaneo de archivos, validación de MIME/tamaño, cifrado, retención, backups probados y monitoreo.
- Auditoría protegida, pruebas, revisión de seguridad y cumplimiento legal.
- Cambiar SQLite por PostgreSQL para una instalación multiusuario real y definir infraestructura de archivos privada.

Las rutas de reservas y activación responden deliberadamente `501` para no simular una operación real insegura.
