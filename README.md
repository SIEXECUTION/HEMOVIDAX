# HemoVida - Banco de Sangre

Django REST Framework + React/Vite para una base PostgreSQL **existente en Supabase**, API en **Render** y frontend en **Cloudflare Pages**.

## Funcionalidad conectada

- JWT, selector de perfiles, bloqueo progresivo 15/30/60 minutos y administración de cuentas.
- Solicitudes de cargos con acreditación profesional, aprobación/rechazo y auditoría persistente.
- Carnet con QR, grupo ABO/Rh obtenido de un análisis, historial, reposiciones y descanso biológico 90/120 días.
- Prefiltro con el catálogo real y conservación de respuestas rechazadas; citas, asistencia y derivación médica.
- Triaje, diferimientos, extracción con consentimiento, bolsa madre en cuarentena y refrigerio.
- Inmunohematología, serología, liberación o descarte, fraccionamiento etario y capacidad de almacenamiento. Pediatría genera tres alícuotas de glóbulos rojos de 75 ml, plasma y plaquetas.
- Inventario por grupo/componente/categoría, umbrales, FEFO y baja de bolsas disponibles vencidas al consultar el monitor.
- Autodonación con fecha quirúrgica persistida, custodia exclusiva y descarte por suspensión definitiva.
- Auditoría por usuario, C.I., tabla, fechas y horario nocturno; indicadores de citas, serología, cámaras, reposición y demanda hospitalaria.

Las pantallas consultan la API. No se cargan registros simulados ni se guardan datos clínicos en localStorage. La sesión se conserva en sessionStorage. Cuando cambia un rol, vuelve a iniciar sesión para actualizar el selector.

## Schema existente: no importar ni migrar

Los 36 modelos de dominio mantienen `managed = False`. `backend/schema_contract.json` conserva solo la estructura entregada, sin datos ni credenciales. `usuariorol` utiliza su clave primaria compuesta real.

El build no ejecuta migraciones, importaciones, semillas ni procedimientos de creación. **No vuelvas a importar el schema sobre tu Supabase.** Los catálogos de roles, requisitos, grupos y ubicaciones deben existir en esa base; la aplicación no los sustituye por ejemplos.

Los timestamps sin zona se interpretan como UTC y los períodos operativos se calculan en `America/La_Paz`, la zona institucional del proyecto. Verifica esta convención si tu base histórica guardó horas locales sin zona. Los operadores de triaje, extracción, laboratorio y bajas deben tener una fila en `personalsalud`: el schema exige ese responsable.

Las solicitudes de cargos conservan la acreditación en `personalsalud` y la solicitud/resolución en `bitacoraauditoria`, porque el schema no incluye una tabla específica de solicitudes de roles.

## Render: API

Conecta el repositorio como Blueprint con `render.yaml` o configura un Web Service:

| Configuración | Valor |
|---|---|
| Root directory | `backend` |
| Build | `bash build.sh` |
| Start | `gunicorn hemovida_project.wsgi:application --bind 0.0.0.0:$PORT --workers 2` |
| Health check | `/api/health/` |

| Variable | Valor |
|---|---|
| `DATABASE_URL` | URI de tu Supabase existente, preferiblemente Session pooler, puerto 5432 y `sslmode=require` |
| `SECRET_KEY` | Generada por el Blueprint; mantener estable entre despliegues |
| `DEBUG` | `False` |
| `USE_SQLITE` | `False` |
| `CORS_ALLOWED_ORIGINS` | `https://TU-PROYECTO.pages.dev` y dominios propios, separados por comas |
| `ALLOWED_HOSTS` | Opcional para dominios propios; Render añade automáticamente su `RENDER_EXTERNAL_HOSTNAME` |

Copia la URI desde **Connect > Session pooler** en Supabase y codifica los caracteres especiales de la contraseña. Producción exige PostgreSQL y SSL. Una configuración ausente o inválida detiene el arranque, sin fallback a SQLite. Los cursores del servidor están desactivados para compatibilidad con pooling.

La salud ejecuta `SELECT 1`, devuelve 503 si falla y no revela detalles internos de la conexión.

Para recuperar contraseñas, configura un remitente real mediante las variables SMTP de `backend/.env.example`, o `BREVO_API_KEY` y `BREVO_SENDER_EMAIL`. El código completo se envía solo por correo, expira en 15 minutos y se invalida después de usarlo. La firma funciona entre workers sin caché compartida ni tablas adicionales. El alta de personal devuelve la cuenta creada y no envía contraseñas por correo automáticamente.

## Cloudflare Workers: frontend

Si el despliegue usa `workers/scripts/hemovidax/versions`, corresponde a Workers. Desde el directorio `frontend`, utiliza:

| Configuración | Valor |
|---|---|
| Root directory | `frontend` |
| Build command | `npm ci && npm run build` |
| Deploy command | `npx wrangler deploy` |
| Variable de compilación | `VITE_API_URL=https://TU-SERVICIO.onrender.com` |

`frontend/wrangler.jsonc` publica `dist` como assets del Worker `hemovidax` y configura el fallback SPA. No añadas `/* /index.html 200` a `_redirects`: Workers puede rechazar esa regla como un bucle. Configura también el origen real del frontend (`https://…workers.dev` o tu dominio) en `CORS_ALLOWED_ORIGINS` de Render.

Referencia: [Cloudflare Workers: routing para SPA](https://developers.cloudflare.com/workers/static-assets/routing/single-page-application/).

## Cloudflare Pages: alternativa de frontend

| Configuración | Valor |
|---|---|
| Root directory | `frontend` |
| Build command | `npm ci && npm run build` |
| Build output directory | `dist` |
| Variable de compilación | `VITE_API_URL=https://TU-SERVICIO.onrender.com` |
| Node | 22 o posterior compatible con Vite |

Define `VITE_API_URL` para producción y las vistas previas utilizadas. Admite URL con o sin `/api`. Al cambiarla, vuelve a compilar. El build falla si falta una URL HTTPS. Autoriza también los orígenes de vista previa necesarios en el CORS del backend.

Nunca coloques credenciales PostgreSQL, `SECRET_KEY` ni claves privadas de Supabase en variables `VITE_`: su contenido es público. El frontend llama a Django y Django conecta con PostgreSQL.

## Desarrollo y comprobaciones

Desde la raíz, en Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.lock.txt
Copy-Item backend/.env.example backend/.env
# Editar backend/.env con la conexión de desarrollo.
.\.venv\Scripts\python.exe backend/manage.py runserver 8000
```

En otra terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Sin `VITE_API_URL`, el desarrollo usa el proxy `/api` hacia `127.0.0.1:8000`. Para usar Render, copia `frontend/.env.example` a `frontend/.env.local` y configura la URL.

Pruebas aisladas sin conexión ni escrituras en Supabase:

```powershell
.\.venv\Scripts\python.exe backend/manage.py test apps --noinput
cd frontend
npm run lint
$env:VITE_API_URL='https://TU-SERVICIO.onrender.com'
npm run build
```

La suite cubre permisos, tokens, bloqueo, recuperación, clave compuesta, prefiltro, descanso, diferimiento, consentimiento, rollback, refrigerio, FEFO, capacidad, fraccionamiento, serología, autodonación e indicadores. Utiliza SQLite en pruebas; no reproduce los triggers ni los bloqueos concurrentes de PostgreSQL. El runner restablece `managed=False` al terminar.

Validación estructural sin modificar tablas:

```powershell
# Contrato local; requiere configuración de desarrollo o DATABASE_URL.
.\.venv\Scripts\python.exe backend/manage.py check_schema
# Estructura real de Supabase, mediante transacción READ ONLY.
.\.venv\Scripts\python.exe backend/manage.py check_schema --database
```

Antes de usar datos reales, ejecuta esa comprobación y una prueba de aceptación en PostgreSQL de ensayo. La verificación local no confirma conectividad, permisos, RLS ni los triggers de tu instancia.

## Referencias

- [Supabase: conexión a PostgreSQL](https://supabase.com/docs/guides/database/connecting-to-postgres)
- [Render: despliegue Django](https://render.com/docs/deploy-django)
- [Cloudflare Pages: configuración del build](https://developers.cloudflare.com/pages/configuration/build-configuration/)
