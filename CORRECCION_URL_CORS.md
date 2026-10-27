# Corrección de conexión API y CORS

- `js/config.js` apunta al backend confirmado: `https://proyectoparaclinica-api.onrender.com`.
- `backend/app.py` permite por defecto el origen `https://exequielrivadera.github.io` además de localhost.
- `render.yaml` declara `CORS_ORIGINS` para ese dominio.

## Importante
Cambiar los archivos localmente no modifica el backend que ya está desplegado. Después de subir estos cambios, verificá en Render que el servicio `proyectoparaclinica-api` use `CORS_ORIGINS` con `https://exequielrivadera.github.io` (sin barra final) y hacé un redeploy. Probá la web desde GitHub Pages, no abriendo `medicos.html` con `file://`, ya que ese caso genera `Origin: null`.

La API debe responder al preflight OPTIONS de `/api/*` con `Access-Control-Allow-Origin: https://exequielrivadera.github.io`. No habilitar `null` globalmente en producción.
