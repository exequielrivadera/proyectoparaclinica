# Cambios de esta versión

## Sobreturnos
- Administración permite registrar un paciente presencial como sobreturno y seleccionar el médico.
- El backend guarda el sobreturno como una atención del día con estado `arrived`, por lo que aparece en la lista del médico y puede llamarse desde el flujo habitual de disponibilidad y llamados.
- Se añadió el campo `appointment_type` con migración automática compatible con las bases SQLite existentes.
- Administración y agenda médica distinguen visualmente `Sobreturno` de `Con turno`.

## Línea estética
- Se actualizó `css/panels.css` para compartir la paleta verde/mint, fondos claros, bordes, sombras suaves, tarjetas y botones redondeados de la pantalla principal.
- Se incrementó la versión del caché del service worker para que los cambios de estilos se descarguen al publicar.

## Publicación
1. Descomprimí el ZIP en una carpeta de trabajo o copiá estos archivos sobre tu proyecto actual, conservando cualquier archivo local que no esté en el ZIP.
2. Revisá `js/config.js`: debe apuntar a `https://proyectoparaclinica-api.onrender.com`.
3. Publicá los cambios en GitHub. Render volverá a desplegar el backend y GitHub Pages publicará el frontend.
4. Probá el ingreso de un sobreturno con datos ficticios, marcá el consultorio del médico como libre y llamá al siguiente paciente para verificar la pantalla `llamados.html`.

Este proyecto continúa siendo una PRUEBA. No usar con datos médicos reales sin autenticación, autorización, privacidad, respaldos y persistencia de producción.
