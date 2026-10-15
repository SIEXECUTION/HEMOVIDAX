# 🩸 HemoVida - Sistema de Gestión para Banco de Sangre

> Plataforma modular integral para la gestión de donantes, hemocomponentes, auditoría forense y trazabilidad transfusional.
> Desarrollado con **Python 3.12**, **Django 5**, **Django REST Framework (DRF)**, **PostgreSQL (Supabase)** y **React 19 + Vite + Tailwind CSS**.

---

## 🏛️ Arquitectura del Sistema

```text
HemoVida-Banco-De-Sangre/
├── backend/                  # API REST modular en Django 5 + DRF
│   ├── apps/
│   │   ├── seguridad/        # Autenticación JWT, Roles RBAC y Auditoría Forense
│   │   ├── donantes/         # Donantes, Carnet Digital y Cálculo Biológico de Intervalos
│   │   └── inventario/       # Parámetros de Stock, Hemocomponentes, Categoría Etaria y FEFO
│   ├── hemovida_project/     # Configuración central (Settings, URLs, WSGI)
│   ├── build.sh              # Script de compilación para Render
│   ├── Procfile              # Comando de inicio Gunicorn para Render
│   ├── manage.py
│   ├── requirements.txt
│   └── .env.example
├── frontend/                 # Aplicación Web React 19 + Vite + Tailwind CSS
│   ├── src/                  # Componentes, vistas por rol, servicios y tipos
│   ├── package.json
│   └── vite.config.ts        # Configurado con Proxy hacia el backend
├── render.yaml               # Manifiesto de despliegue para Render (Backend)
├── iniciar_backend.bat       # Lanzador rápido en 1 clic para desarrollo local
├── iniciar_frontend.bat      # Lanzador rápido en 1 clic para desarrollo local
└── README.md
```

---

## 📋 Módulos Principales de la Plataforma

### 1. Seguridad, Control de Acceso y RBAC
- **Autenticación Segura:** Endpoint `POST /api/auth/login/` con emisión de tokens JWT (`access` y `refresh`) y validación de contraseñas robustas (soporte Argon2id y PBKDF2).
- **Gestión de Personal y Cuentas:** Registro y administración de personal de salud con asignación de roles institucionales (Administrador, Médico de Triaje, Bioquímico de Laboratorio, Personal de Recepción/Colecta, Técnico de Logística/Despacho).
- **Protección contra Fuerza Bruta:** Bloqueo automático de cuentas tras intentos fallidos repetidos con trazabilidad de bloqueos recibidos.

### 2. Auditoría Forense y Trazabilidad Transfusional
- **Bitácora Forense:** Registro inmutable de eventos clínicos, de inventario y de acceso con captura de IP origen, usuario actor, rol activo (`X-Active-Role`), tabla afectada y timestamp de precisión.
- **Filtros Avanzados:** Búsqueda por rango de fechas, usuario actor, entidad y detección de operaciones fuera de horario laboral habitual.

### 3. Donantes y Carnet Digital Biológico
- **Evaluación y Carnet Digital:** Endpoint `GET /api/donantes/{ci}/carnet/` con cálculo de intervalo biológico reglamentario:
  - Donantes Varones: Intervalo biológico de 90 días entre donaciones efectivas.
  - Donantes Mujeres: Intervalo biológico de 120 días entre donaciones efectivas.
- **Historial y Trazabilidad:** Cálculo en tiempo real de días restantes de espera, volumen acumulado y condición de aptitud.

### 4. Control de Inventario y Hemocomponentes (FEFO)
- **Hemocomponentes Oficiales:** Gestión normalizada de `Concentrado de Globulos Rojos`, `Plasma Fresco Congelado`, `Concentrado Plaquetario` y `Crioprecipitado`.
- **Categorización Etaria:** Segmentación clínica obligatoria en `Adulto`, `Adolescente` y `Pediátrico`.
- **Despacho FEFO (First-Expired, First-Out):** Priorización algorítmica de unidades con fecha de caducidad más próxima para minimizar mermas.
- **Umbrales y Alertas Críticas:** Parámetros configurables de stock mínimo de seguridad y alerta crítica con cálculo dinámico de déficit.

### 5. Donación Autóloga y Gestión Transfusional
- **Protocolo de Donación Autóloga:** Registro, flebotomía y custodia exclusiva en frío de unidades destinadas a procedimientos quirúrgicos electivos programados.
- **Bloqueo a Terceros:** Marcado `esExclusivoAutologo = TRUE` para prevenir despachos cruzados y protocolo de descarte biológico controlado ante cancelación quirúrgica.

---

## 🚀 Despliegue en Producción

### Backend en Render
1. Conecta el repositorio de GitHub en el panel de **Render**.
2. Selecciona **Web Service** y especifica:
   - **Root Directory:** `backend`
   - **Build Command:** `bash build.sh`
   - **Start Command:** `gunicorn hemovida_project.wsgi:application --bind 0.0.0.0:$PORT --workers 2`
3. Configura las variables de entorno en Render:
   - `DATABASE_URL`: URI de conexión PostgreSQL provista por **Supabase** (modo Transaction / Session Pooler con SSL).
   - `DEBUG`: `False`
   - `ALLOWED_HOSTS`: `*` (o tu dominio asignado en Render)
   - `SECRET_KEY`: Cadena aleatoria segura para producción.
   - `CORS_ALLOW_ALL_ORIGINS`: `True`

### Frontend en Cloudflare Pages
1. Conecta el repositorio de GitHub en **Cloudflare Pages**.
2. Selecciona **Create application** > **Pages** > **Connect to Git**.
3. Configura los parámetros de compilación:
   - **Root directory:** `frontend`
   - **Framework preset:** `Vite`
   - **Build command:** `npm run build`
   - **Build output directory:** `dist`
4. Configura la variable de entorno para conectar con el backend de Render:
   - `VITE_API_URL`: `https://tu-servicio-render.onrender.com`

---

## 💻 Ejecución en Desarrollo Local

### 1. Iniciar Backend
```bash
cd backend
pip install -r requirements.txt
python manage.py runserver 8000
```
API activa en: **`http://127.0.0.1:8000`**

### 2. Iniciar Frontend
```bash
cd frontend
npm install
npm run dev
```
Aplicación web activa en: **`http://localhost:3000`**

---

## 🧪 Pruebas Automatizadas

El proyecto cuenta con una suite completa de pruebas unitarias y de integración que validan validadores, endpoints y lógica transaccional:
```bash
cd backend
python manage.py test apps
```
**Resultado:** Todas las pruebas superadas exitosamente (`OK`).
