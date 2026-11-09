# Gestoría — panel de gestión + web app móvil para clientes

Aplicación para una gestoría y sus clientes, con cuatro roles:

| Rol | Dónde | Qué hace |
|---|---|---|
| **Gestoría** | Web (`/`) | Menú principal: **Panel** (clientes que necesitan atención, documentos por revisar, campaña de IVA) y **Clientes**. Al abrir un cliente aparece su menú: resumen y qué falta, facturas de compra y venta, albaranes (cuadre con la factura mensual), caja (TPV), proveedores, conciliación bancaria, apuntes contables, IVA y margen, datos y usuarios. El mes de trabajo se elige en la cabecera del cliente y se mantiene al cambiar de sección o de cliente; desde ahí se **liquida** o reabre el mes. |
| **Cliente · administración** | Web en el ordenador (`/`) | Ve **solo su empresa** (su nombre en la cabecera): resumen del mes con y sin IVA, **qué reclamar a proveedores**, qué falta, sus facturas, albaranes, caja y proveedores (solo lectura, con la foto de cada documento), IVA y margen, y el **cierre mensual** (bloquea el mes). No usa la versión móvil. |
| **Cliente · compras** | App móvil (`/movil`) | Operativa diaria: sube **albaranes y facturas de proveedor** (foto o PDF). Ve solo lo que ha subido. |
| **Cliente · ventas** | App móvil (`/movil`) | Operativa diaria: sube la **foto del cierre Z del TPV** cada día y las **facturas de venta**. Ve solo lo que ha subido. |

### Lectura automática de documentos (OCR local, sin IA)

Al subir una foto o PDF, el servidor la lee con **Tesseract** (OCR, en español) y **reglas** propias, sin IA ni servicios externos:

- **Facturas y albaranes**: tipo de documento (si el cliente elige "Automático", el sistema lo archiva como albarán, factura de compra o de venta según quién sea el emisor), NIF/CIF/NIE con dígito de control, proveedor, número, fecha, base, tipo de IVA, IRPF y total, comprobando que **base + IVA − IRPF = total**.
- **Cierres Z**: nº de Z, fecha, nº de tickets, **desglose por tipo de IVA** (10 % / 21 %…), total y cobros en efectivo/tarjeta. Si una línea es ambigua ("IVA 10 % 1.100,00"), se decide con el total del ticket.
- Endereza fotos torcidas o giradas y hace una segunda pasada con otra segmentación si la primera no es fiable.
- Cada documento queda **pendiente de revisar** con su nivel de confianza (alta / media / baja) y avisos; la gestoría lo valida o pulsa "Leer datos de la foto" para repetir la lectura.

### Albaranes de proveedor

Los albaranes **no cuentan** para el IVA ni la contabilidad: solo la factura mensual del proveedor. La aplicación agrupa los albaranes del mes por proveedor y comprueba que la factura **cuadra con la suma de sus bases** (tolerancia 5 céntimos). Si no cuadra, no se vincula salvo que la gestoría lo fuerce (queda auditado), y aparece en "qué falta" como reclamación al proveedor.

### Mes: abierto → cerrado → liquidado

- **Cerrado** por administración del cliente: congela el resumen y ya no se pueden subir documentos con fecha de ese mes (la gestoría sí puede seguir revisando).
- **Liquidado** por la gestoría: contabiliza todo lo revisado del mes (facturas y cierres de caja), guarda el informe y nadie puede modificar documentos de ese mes hasta que la gestoría lo **reabra**.
- **Qué falta**: documentos sin revisar o rechazados, albaranes sin factura, facturas que no cuadran, facturas recibidas sin cuadrar, proveedores habituales que este mes no han facturado, pagos y cobros del banco sin factura, y días sin cierre de caja (aprende qué días cierra el negocio).

Stack: **FastAPI + SQLAlchemy** · **React + Vite** · **Supabase** (PostgreSQL y Storage, en su propio proyecto *gestoria*) · **Nginx** como capa de entrada · **Tesseract** para el OCR local.

---

## Arquitectura y seguridad

```
 Móvil / navegador
        │  HTTPS (TLS 1.2/1.3, HSTS, CSP)
        ▼
 ┌──────────────┐   único servicio expuesto (80→301, 443)
 │    Nginx     │   rate limiting · límites de tamaño · cabeceras · sirve el frontend
 └──────┬───────┘
        │  red interna Docker (la API no publica puertos)
        ▼
 ┌──────────────┐   login propio (JWT) · roles · aislamiento por cliente
 │   FastAPI    │   validación de ficheros · auditoría · lógica contable
 └──────┬───────┘
        │  TLS verify-full (PostgreSQL) · HTTPS (Storage)
        ▼
 ┌──────────────┐   esquema `gestoria` aislado · RLS forzado · bucket privado
 │ Supabase      │
 └──────────────┘
```

### Sin URLs externas ni IA

- El navegador **solo habla con tu propio dominio** (`/api/...`). No hay SDKs de terceros, CDNs, fuentes web, analítica ni scripts externos. La CSP lo impone (`connect-src 'self'`, `script-src 'self'`) y se ha comprobado en un navegador real: cero peticiones a otros dominios.
- **El login lo hace la propia API** (no Supabase Auth): el frontend no conoce la URL de Supabase ni ninguna clave.
- **No se usa ninguna IA** ni servicio de IA en el código. El único servicio externo es Supabase (base de datos y almacenamiento), y solo se llega a él desde el servidor.

### Tráfico cifrado en todos los tramos

| Tramo | Protección |
|---|---|
| Navegador → Nginx | HTTPS obligatorio, HTTP redirige a HTTPS, TLS 1.2/1.3, HSTS 2 años |
| Nginx → API | Red interna de Docker. La API no tiene `ports:` y no es alcanzable desde fuera |
| API → base de datos | `sslmode=verify-full` con el certificado CA de Supabase. **En producción la API no arranca** si la conexión no es verify-full, y `disable`/`prefer` se rechazan siempre |
| API → Supabase Storage | HTTPS |

### Capa Nginx

- Rate limiting: login 5/min por IP, subidas (POST) 20/min, API 15 req/s.
- `client_max_body_size 12m` y timeouts cortos.
- Cabeceras: HSTS, CSP (solo `self`: ningún dominio externo), `X-Frame-Options DENY`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`.
- `/api/docs`, `/api/openapi.json` y los ficheros ocultos (`.env`, `.git`) devuelven 404. No se muestra la versión del servidor.

### Capa API (defensa en profundidad)

- **Autenticación propia**: contraseñas con PBKDF2-SHA256 (310.000 iteraciones), JWT HS256 firmado con `SECRET_KEY` (≥ 32 caracteres, obligatoria en producción) con emisor, audiencia y caducidad (8 h). Bloqueo de la cuenta 15 minutos tras 5 fallos y el mismo mensaje exista o no el email. *(El código conserva un modo `AUTH_MODO=supabase` por si en el futuro la gestoría tiene su propio proyecto.)*
- **Roles**: el rol (`gestor`, `cliente_admin`, `cliente_compras`, `cliente_ventas`, `cliente_compras_ventas`) sale de la tabla `usuarios` en cada petición, no del token. Compras no puede ver IVA, resumen ni cierres de caja; ventas no puede subir facturas de proveedor; ninguno de los dos ve lo que han subido otros usuarios.
- **Aislamiento entre clientes**: en `/api/movil/*` el `cliente_id` siempre sale del usuario autenticado. Si alguien pide un ID de otro cliente recibe 404.
- **Subidas**: el tipo se detecta por los *magic bytes* (JPG, PNG, WEBP, HEIC, PDF), el nombre lo pone el servidor, hay límite de tamaño y se protege contra *path traversal*.
- **Fotos**: van a un bucket **privado**. El navegador nunca recibe una URL pública: la API comprueba permisos y entrega el fichero.
- `TrustedHostMiddleware`, CORS cerrado, documentación desactivada en producción, errores 500 sin detalles internos y contenedor sin root, de solo lectura y sin capabilities.
- **Auditoría**: tabla `auditoria` con quién, qué, cuándo y desde qué IP. La API no puede modificarla ni borrarla.

### Capa base de datos (Supabase, proyecto gestoria)

La gestoría tiene **su propio proyecto de Supabase** (`gestoria`, ref `fgjoafbpejgrbnjsufvi`, Irlanda), sin ninguna otra aplicación dentro. Además:

- Todas las tablas viven en el esquema propio **`gestoria`**, que no está expuesto en la API REST pública de Supabase y en el que `anon`, `authenticated` y `public` **no tienen ni permiso de uso**.
- La API conecta con el rol dedicado **`gestoria_api`** (solo DML sobre `gestoria`, sin DDL) y su `search_path` apunta a `gestoria`.
- **RLS activado y forzado** en las 12 tablas como segunda barrera. La auditoría no se puede modificar ni borrar.
- **No se usa Supabase Auth**: los usuarios de la gestoría no aparecen en `auth.users`; el login lo gestiona la propia API.
- Fotos en el bucket **privado `gestoria-facturas`** (máx. 10 MB, solo JPG/PNG/WEBP/HEIC/PDF), sin políticas de Storage: solo el backend, con la clave `service_role`, puede leerlo o escribirlo.
- El frontend no habla con Supabase: datos y fotos pasan siempre por la API.

---

## Puesta en marcha en producción

Las cuatro migraciones de `supabase/migrations/` **ya están aplicadas** en el proyecto `gestoria` (esquema, tablas, permisos, RLS, rol `gestoria_api` todavía sin login, bucket, albaranes, roles, caja TPV y cierres de mes).

**Antes de empezar (en Supabase y en tu proveedor de dominio):**

1. **Activa el rol de la API** en *SQL Editor* con una contraseña larga (≥ 16 caracteres, guárdala en tu gestor de contraseñas):
   ```sql
   alter role gestoria_api with login password 'UNA_CONTRASEÑA_LARGA_Y_ALEATORIA';
   ```
2. **Clave secreta solo para la gestoría**: *Settings → API Keys → Publishable and secret API keys* → nueva clave secreta `gestoria_backend` (empieza por `sb_secret_`).
3. **Host del pooler**: *Connect → Session pooler*, copia el host (`aws-…pooler.supabase.com`, puerto 5432).
4. **Certificado SSL de la base de datos**: *Database → Settings → SSL Configuration → Download certificate*.
5. **DNS**: registro tipo **A** de tu dominio (p. ej. `gestoria.tudominio.es`) hacia la IP del servidor.

**En el servidor (Ubuntu 22.04/24.04):**

> **Oracle Cloud (Always Free, ARM):** la app funciona igual en ARM (Ampere A1). Crea la instancia con *Ubuntu 24.04* y forma *VM.Standard.A1.Flex* (2 OCPU, 12 GB) y, en la *Security List* de la red (VCN), añade reglas de entrada TCP para los puertos **80** y **443** desde `0.0.0.0/0`. El script detecta Oracle y abre esos puertos en su cortafuegos `iptables` (no usa ufw, que choca con él).

```bash
git clone https://github.com/julioromerosaez-oss/gestoria.git && cd gestoria
mkdir -p certs && nano certs/supabase-ca.crt        # pega el certificado descargado en el paso 4 (o súbelo con scp)
sudo bash scripts/instalar-servidor.sh
```

El script instala Docker y certbot, deja el cortafuegos solo con 22/80/443, te pide los datos de Supabase sin mostrarlos y crea el `.env` (permisos 600), saca el certificado HTTPS con renovación automática, construye y arranca la aplicación y crea tu primer usuario de gestor. Al terminar:

- Gestoría y administración de los clientes: `https://tu-dominio`
- App móvil de compras y ventas: `https://tu-dominio/movil`
- Logs: `docker compose logs -f` · Actualizar: `git pull && docker compose up -d --build`

Después, en la aplicación: **Clientes → Nuevo cliente** y, en el cliente, **Datos y usuarios → Añadir usuario** (administración, compras, ventas).

## Desarrollo local (sin Supabase)

Requisitos: **Python 3.12+**, **Node 22+** (Vite 8 necesita Node 20.19+ o 22.12+) y **Tesseract** con el idioma español.

```bash
# backend
cd backend && pip install -r requirements.txt
python -m app.seed                      # SQLite + datos de demo
uvicorn app.main:app --reload --port 8000
# frontend (otra terminal)
cd frontend && npm install && npm run dev   # http://localhost:5173  (proxy /api → 8000)
```

Para el OCR en local hace falta Tesseract: `sudo apt install tesseract-ocr tesseract-ocr-spa` (en macOS, `brew install tesseract tesseract-lang`). En Docker ya va incluido.

Usuarios de demo (restaurante con meses liquidados, septiembre cerrado y octubre con cosas pendientes):

| Rol | Usuario | Contraseña |
|---|---|---|
| Gestoría (http://localhost:8000) | roberto@complutumasesores.com | Rober2026 |
| Administración del restaurante (web, http://localhost:8000) | patrilucre1953@gmail.com | Patri2026 |
| Compras y ventas del restaurante (móvil, http://localhost:8000/movil) | joselucre1953@gmail.com | Javi2026 |

Estas claves son solo para la base de demo local. En el servidor los usuarios se crean desde la pantalla del cliente con contraseñas distintas.

Tests: `cd backend && pytest` (22 tests). Cubren seguridad (401/403, token manipulado, fuerza bruta, cabeceras, ficheros falsos, aislamiento entre clientes y entre usuarios, permisos por rol), la lectura de fotos reales generadas (factura, albarán torcido, PDF, cierre Z), el cuadre de albaranes con la factura mensual, el cierre y bloqueo del mes, la liquidación con sus asientos y el flujo contable completo.

## Contabilidad que genera

| Operación | Asiento |
|---|---|
| Factura de compra | 6xx gasto (D) · 472 IVA soportado (D) · 4751 retenciones (H) · 400 proveedores (H) |
| Factura de venta | 430 clientes (D) · 473 retenciones (D) · 7xx ingreso (H) · 477 IVA repercutido (H) |
| Pago conciliado | 400 (D) · 572 bancos (H) |
| Cobro conciliado | 572 (D) · 430 (H) |
| Cierre de caja (TPV) | 570 caja por el efectivo (D) · 572 bancos por la tarjeta (D) · 700 ventas por tipo (H) · 477 IVA por tipo (H) |

Una factura contabilizada ya no se puede editar ni borrar: se corrige con un asiento manual de rectificación. Los asientos descuadrados se rechazan.

## Limitaciones conocidas / siguientes pasos

- **Un tipo de IVA por factura.** Las facturas con varios tipos se meten hoy como dos facturas. El siguiente paso es añadir líneas de factura.
- **La lectura automática no es infalible**: con fotos muy borrosas, muy torcidas o de lado se queda en confianza baja y hay que completar los datos a mano. Formatos de factura muy distintos pueden necesitar ajustar las reglas.
- Los albaranes se cuadran con la factura por base imponible; no se comparan línea a línea.
- El resumen de IVA sigue la lógica del modelo 303 (repercutido − soportado por tipo), pero **no genera el fichero de presentación** de la AEAT ni contempla prorrata, recargo de equivalencia, operaciones intracomunitarias ni el régimen simplificado.
- Conciliación por CSV. Los formatos Norma 43 o la conexión PSD2 con el banco quedan para más adelante.
