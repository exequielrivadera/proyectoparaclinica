# Arquitectura multi-clínica — decisión y próximos pasos

## Decisión
Usar PostgreSQL administrado y un backend central alojado en un servicio cloud persistente. La aplicación web de pacientes y administración se publica como frontend; el backend, la base de datos y las tareas de notificaciones corren en la nube. El cliente no necesita mantener una PC encendida.

## Cómo venderlo a varias clínicas
- Una instancia de aplicación compartida para todas las clínicas.
- Cada clínica tiene `clinic_id` y sus propios usuarios, pacientes, profesionales, agenda, registros, estudios y configuración de notificaciones.
- Todas las consultas de datos clínicos deben estar autorizadas por la membresía del usuario y filtradas por clínica. PostgreSQL Row-Level Security es una segunda barrera, no un reemplazo de la autorización del backend.
- Los secretos SMTP de cada clínica se guardan en un gestor de secretos o cifrados; nunca en el frontend, repositorio ni texto plano de la base de datos.
- Archivos médicos en almacenamiento de objetos privado, nunca en GitHub Pages ni dentro de un directorio público. Descarga solo con URL temporal y autorización.
- Tareas de correo en un worker separado/cola durable, con idempotencia, reintentos y registro de entregas.

## Archivos incluidos
- `schema_postgresql.sql`: diseño inicial de tablas para clínicas, usuarios, pacientes, profesionales, agenda, turnos, historias clínicas, estudios, notificaciones y auditoría.
- `app.py`: backend demo previo para seguir probando la agenda actual. **Todavía utiliza SQLite y no está conectado a este esquema PostgreSQL.**
- `.env.example`: variables de configuración de la demo.
- `README.md`: guía para correr la demo y preparar la migración.

## Migración recomendada
1. Revisar el modelo con los flujos reales de la clínica y asesoría legal/de privacidad.
2. Crear una base PostgreSQL de desarrollo y gestionar el esquema mediante migraciones versionadas (Alembic).
3. Migrar la capa de acceso a datos a SQLAlchemy/psycopg y agregar tenant context validado por el backend.
4. Construir autenticación segura, recuperación de cuenta, MFA para personal clínico/admin, roles y permisos granulares.
5. Implementar turnos y bloqueos de agenda transaccionales; en producción, usar una cola durable para emails.
6. Añadir pacientes, historia clínica, estudios privados, control de publicación y auditoría de lectura/cambios.
7. Pruebas de aislamiento entre dos clínicas distintas, restauración de backups, seguridad, rendimiento y envío de correos.
8. Desplegar en staging con datos ficticios y realizar pruebas de aceptación antes de producción.

## Nota de seguridad
El SQL es una base de diseño y requiere migraciones y pruebas. Las políticas RLS dependen de que el backend establezca `app.current_clinic_id` en cada transacción después de validar al usuario. No usar datos reales hasta completar autenticación, autorización, revisión de políticas RLS, gestión de claves, backups, HTTPS, auditoría, respuesta a incidentes y revisión legal aplicable en Argentina.
