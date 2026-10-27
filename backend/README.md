# Backend Clínica Demo

Desde esta carpeta, en Windows: `py -m venv .venv`, activar `.venv`, `pip install -r requirements.txt`, copiar `.env.example` a `.env` y ejecutar `py app.py`.

Abrí http://127.0.0.1:5000. El mismo Flask sirve la web y la API. No iniciar un segundo servidor estático en el puerto 5500. La salud de API se revisa en `/api/health`.

Demo únicamente con datos ficticios. El acceso a paneles no es autenticación de producción y el portal por DNI no verifica identidad. No usar con pacientes reales.

### Flujo de consultorio y llamados (demo)
- El backend crea la tabla `doctor_status` automáticamente al iniciar, incluso en una base SQLite existente.
- El médico puede marcar el consultorio libre/ocupado.
- Administración llama al paciente que recepción marcó como `Llegó`.
- Administración puede repetir el llamado; el siguiente paciente no se habilita hasta que el llamado actual tenga dos anuncios registrados.
- Tras el llamado, el médico debe volver a marcar el consultorio libre para habilitar el siguiente llamado.
