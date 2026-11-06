# Clínica — Sindicato de Camioneros de La Rioja

Aplicación institucional con web pública, solicitud de turnos, portal de pacientes, panel de Administración, panel Médico y pantalla de llamados. El backend Flask comparte una base SQLite para reflejar las acciones entre los paneles.

## Ejecutar localmente en Windows

1. Extraé el ZIP.
2. Abrí PowerShell dentro de la carpeta `backend`.
3. Ejecutá:
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   Copy-Item .env.example .env
   py app.py
   ```
4. Dejá esa terminal abierta y entrá a `http://127.0.0.1:5000`.
5. Comprobá el backend en `http://127.0.0.1:5000/api/health`; debe devolver JSON con `status: ok`.
6. Abrí `http://127.0.0.1:5000/paneles.html`. Desde ahí accedés a Administración, Médicos, Pacientes y Pantalla de llamados.

No abras `index.html` con doble clic ni uses Live Server para probar funciones dinámicas: la página y la API deben servirse desde Flask en el mismo puerto.

## Publicación en GitHub Pages y Render

GitHub Pages no ejecuta Python. Hay que desplegar el backend Flask por separado y conectar la web a su URL HTTPS. El archivo `render.yaml` prepara el servicio en Render.

### Paso A — Publicar el backend

1. Subí estos cambios al repositorio `proyectoparaclinica`.
2. Entrá en Render y elegí **New + → Blueprint** (o desplegá un servicio web desde el repositorio).
3. Seleccioná el repositorio `exequielrivadera/proyectoparaclinica` y aplicá la configuración de `render.yaml`.
4. Esperá a que el servicio termine el despliegue. Render asignará una URL HTTPS similar a `https://nombre-del-servicio.onrender.com`.
5. Abrí `https://TU-URL.onrender.com/api/health`. Debe devolver JSON con `status: ok`. Reemplazá `TU-URL` por el dominio real que te asignó Render.

El plan gratuito puede suspenderse por inactividad y el almacenamiento local puede perderse al reiniciar o volver a desplegar. No debe considerarse almacenamiento permanente.

### Paso B — Conectar GitHub Pages al backend

1. Abrí `js/config.js`.
2. Cambiá la línea `window.CLINICA_API_BASE = '';` por la URL HTTPS real de Render, sin barra al final. Ejemplo:
   ```js
   window.CLINICA_API_BASE = 'https://nombre-del-servicio.onrender.com';
   ```
3. Guardá y subí el cambio a GitHub:
   ```powershell
   git add js/config.js render.yaml README.md js/app.js js/panels.js service-worker.js
   git commit -m "Actualiza la aplicación Clínica"
   git push origin main
   ```
4. Esperá a que GitHub Pages publique el commit. Abrí la web y hacé `Ctrl + F5`.
5. Si el navegador bloquea la solicitud por CORS, revisá en Render que `CORS_ORIGINS` incluya `https://exequielrivadera.github.io` (solo el origen, sin `/proyectoparaclinica/`) y volvé a desplegar.

También podés presentar directamente la URL de Render: el backend sirve la página principal y los recursos estáticos en el mismo dominio, así que no requiere configurar una segunda URL de API. GitHub Pages seguirá disponible como frontend estático cuando completes el Paso B.

## Funcionalidades incluidas

- Solicitud de turnos y disponibilidad consultadas en el backend.
- Panel de Administración para agenda, pacientes, estados y llamados.
- Panel médico para disponibilidad del consultorio, notas y estudios.
- Portal del paciente para consultar estudios publicados.
- Pantalla de llamados para recepción y sala de espera.
- Envío de confirmaciones y recordatorios por correo, si se configuran credenciales SMTP en `backend/.env` o variables de entorno del servicio.

Los recordatorios por correo no se envían hasta que SMTP esté configurado. El servicio gratuito puede dormir cuando no se utiliza, por lo que el primer acceso puede demorar.

## Datos y seguridad

La base incluida contiene registros ficticios. No ingreses datos reales de pacientes ni subas estudios reales.

Los paneles y el acceso de pacientes **todavía no tienen autenticación real ni permisos adecuados para producción**; los datos y estudios pueden quedar expuestos públicamente. Antes de usarla con una clínica real hay que implementar autenticación por roles, autorización en cada endpoint, verificación de identidad, almacenamiento privado de estudios, auditoría, límites de solicitudes, copias de seguridad, recuperación y una base de datos administrada. No usar con información médica real.

## Pacientes, profesionales y llamados

- Cada paciente tiene un `id` entero autoincremental e independiente del DNI. Los turnos guardan referencias a `patient_id` y `doctor_id`.
- La solicitud de turno empieza verificando el DNI; si el paciente existe, recupera sus datos. Si no existe, registra el paciente al confirmar el turno.
- Se valida el formato de nombres, teléfono, DNI, correo, fecha y horario tanto en el frontend como en el backend.
- La confirmación del turno se muestra en una ventana aparte. El envío de correo y recordatorios depende de la configuración SMTP del backend.
- Administración permite dar de alta, editar, activar y desactivar médicos, con ID autoincremental y una o varias especialidades por médico.
- Al marcar un consultorio como libre, el backend finaliza la atención previa y llama automáticamente al siguiente paciente que Administración haya marcado como llegado.
- La pantalla de llamados muestra el nombre completo y consultorio; para los sobreturnos también anuncia por voz que se trata de un sobreturno.
- El panel médico admite adjuntar un PDF, PNG o JPG de hasta 12 MB. Los archivos se guardan en `backend/private_studies/`, fuera de los recursos públicos, y no deben incluirse en Git.

El portal actual utiliza una contraseña compartida y debe sustituirse por autenticación individual robusta, autorización, auditoría y almacenamiento privado persistente antes de producción. La sesión de descarga vence a los 30 minutos.
