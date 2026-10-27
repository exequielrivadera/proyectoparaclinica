# Clínica Demo — Sindicato de Camioneros de La Rioja

Demo institucional con web pública, turnos, panel de Administración, panel Médico, portal Paciente y pantalla de llamados. Usa SQLite local para datos ficticios.

## Inicio en Windows (una sola terminal para el backend)
1. Extraé todo el ZIP.
2. Abrí PowerShell dentro de `clinica_demo_sindicato/backend`.
3. Ejecutá:
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   Copy-Item .env.example .env
   py app.py
   ```
4. Dejá esa terminal abierta y entrá a **http://127.0.0.1:5000**.
5. Los paneles están en **http://127.0.0.1:5000/paneles.html**. Administración: `/admin.html`; médicos: `/medicos.html`; pacientes: `/pacientes.html`; llamados: `/llamados.html`.
6. Para comprobar que el backend responde, abrí **http://127.0.0.1:5000/api/health**; debe aparecer `status: ok`.

**Importante:** ya no abras `index.html` haciendo doble clic ni inicies `py -m http.server 5500`. La web y la API ahora se sirven desde el mismo backend para evitar `Failed to fetch`.

## Pruebas de demostración
- Usá únicamente los pacientes ficticios ya incluidos, por ejemplo DNI `30123456` (Juan Pérez) o `28987654` (María Gómez). No uses DNI real.
- Administración: registrar paciente ficticio, buscarlo, consultar turnos, marcar llegada, llamar, reprogramar y cambiar estados de estudios.
- Médicos: buscar el DNI ficticio `30123456`, guardar una nota no sensible de demostración y registrar un estudio ficticio.
- Pacientes: consultar estudios publicados con DNI ficticio `30123456`. La descarga actual es un comprobante de texto ilustrativo, no un archivo médico real.
- Llamados: abrir `/llamados.html`, activar sonido y generar un llamado desde Administración.

## Correo
Las confirmaciones y recordatorios requieren configurar SMTP en `backend/.env`. Sin esos datos, el turno se guarda, pero no se envía correo.

## Publicación en la nube
`render.yaml` ahora define un único servicio web para servir frontend y API en el mismo dominio. Importá el repositorio en Render y revisá el plan y disco persistente antes de desplegar. Las variables SMTP son opcionales para iniciar la demo; configurarlas para probar correos. La configuración usa SQLite persistente solo para demo, no es la arquitectura final.

## Limitaciones y seguridad
Es un prototipo: los paneles no tienen autenticación real y el portal por DNI es solo simulación. No publicar con datos reales ni cargar información de afiliados. Antes de uso institucional se requieren autenticación y permisos por rol, verificación de identidad, archivos privados, auditoría, límites de solicitudes, HTTPS, backups y restauración. El esquema PostgreSQL incluido es una propuesta, pero el backend aún usa SQLite.

## Flujo de disponibilidad y llamado al siguiente paciente

1. En Administración, filtrá la agenda por la fecha del turno. Cuando llega una persona, pulsá **Llegó** en su fila.
2. En el panel Médico, seleccioná el profesional, indicá el consultorio y pulsá **Consultorio libre** cuando el médico haya terminado y esté listo para recibir a otra persona. Si vuelve a atender o necesita tiempo, pulsá **Estoy atendiendo**.
3. En Administración aparecerá el estado del profesional. Pulsá **Llamar siguiente paciente** en la tarjeta de ese médico. El sistema elige el turno más temprano de esa fecha que esté marcado como **Llegó**, publica el llamado para la pantalla de sala de espera y cambia el consultorio a ocupado.
4. La pantalla `llamados.html` debe permanecer abierta en un monitor/TV. Pulsá **Activar sonido** una vez para permitir el audio del navegador.

El estado de consultorio se comparte entre los paneles mediante la base SQLite de la demo. La lista de profesionales de esta versión es fija y de demostración; antes de uso institucional deben implementarse registro/autenticación de usuarios y gestión real de profesionales.
