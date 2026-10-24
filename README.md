# Clínica

Demo responsive de una web de clínica/consultorio desarrollada por Pulso Digital. Incluye portada pública, especialidades, perfiles ficticios, prototipo de agenda, formulario de turnos, portal de pacientes desactivado y crédito discreto de Pulso Digital en el pie.

## Importante: qué funciona y qué es demostración

- La web pública y sus interacciones de interfaz funcionan localmente.
- La disponibilidad mostrada es ficticia y se usa únicamente para probar la interfaz.
- El formulario NO crea una reserva real y NO envía emails.
- El portal de pacientes NO autentica usuarios ni expone estudios.
- El panel médico/backend se entrega como un esqueleto inicial separado; requiere configuración y revisión antes de cualquier uso real.
- No se deben cargar datos reales de pacientes ni estudios en esta demo.
- Los nombres, perfiles, dirección y contacto son ficticios. El WhatsApp y correo institucional deben configurarse con los datos autorizados de la clínica.

## Abrir la demo

1. Extraer el ZIP.
2. Abrir una terminal dentro de la carpeta `Clinica`.
3. Ejecutar `py -m http.server 8000`.
4. Abrir `http://localhost:8000`.

También puede publicarse como web estática en GitHub Pages para mostrar el diseño. GitHub Pages no ejecuta el backend Python y no sirve para alojar documentación clínica privada.

## Publicar en GitHub Pages

Subir el contenido de esta carpeta al repositorio `proyectoclinica`, luego ir a **Settings → Pages → Deploy from a branch → main → /(root)**. La dirección esperada, si el repositorio y Pages están configurados, sería `https://exequielrivadera.github.io/proyectoclinica/`. La publicación debe verificarse en GitHub.

## Backend inicial (opcional, no productivo)

Hay un ejemplo separado en `backend/` con Flask y SQLite para orientar la siguiente etapa. Requiere Python 3.11+, instalar dependencias y configurar variables de entorno. No está integrado a la web estática y no debe exponerse públicamente sin completar autenticación, autorización, CSRF, límites de intentos, HTTPS, auditoría, backups y revisión de seguridad.

### Recomendaciones de seguridad y privacidad

- DNI puede ser identificador de usuario, pero no debe ser contraseña permanente.
- Activar cuentas con un código temporal de un solo uso por un canal verificado; exigir que el paciente cree una contraseña.
- Estudios y documentos clínicos deben almacenarse fuera de carpetas públicas, con autorización por paciente/rol y enlaces protegidos.
- La notificación por email debe evitar diagnósticos, resultados y otros datos clínicos sensibles.
- En producción se requiere consentimiento y tratamiento conforme a la normativa argentina aplicable a datos personales y sensibles.
- Antes de uso real, revisar requisitos legales, seguridad, permisos y operación clínica con profesionales competentes.

## Marca

El pie muestra “Diseñada por”, el texto “Pulso Digital” y el logotipo oficial negro proporcionado, guardado como `assets/pulsodigital-logo.png`.


## Navegación interactiva y WhatsApp

- Especialidades, Profesionales y La clínica abren vistas internas sin salir de la página.
- Profesionales está organizado por rubro y cada perfil permite abrir el formulario de turno con médico/especialidad preseleccionados.
- El botón flotante de WhatsApp permanece visible. El globo “¿Te asesoramos?” aparece al cargar y se desvanece cuando la persona empieza a desplazarse; al tocar el icono abre un globo de chat.
- Para activar la salida real a WhatsApp, editar `WHATSAPP_NUMBER` en `js/app.js` con el número institucional en formato internacional y solo dígitos. Mientras no se configure, no se abre un número inventado.
- Se quitaron las flechas decorativas de las tarjetas y la elevación/animación de las tarjetas de especialidades.
