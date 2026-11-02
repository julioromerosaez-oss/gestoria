# Gestoría — panel de gestión + web app móvil para clientes

Aplicación para una gestoría y sus clientes, con cuatro roles:

| Rol | Dónde | Qué hace |
|---|---|---|
| **Gestoría** | Panel web (`/`) | Lista de clientes → **ficha del cliente por mes o por proveedor**: facturas de compra y venta, albaranes y su cuadre con la factura mensual, caja (TPV), IVA, **qué falta** del cliente y de sus proveedores, conciliación bancaria y **liquidación mensual** (cierre contable + informe). |
| **Cliente · administración** | App (`/movil`, también en escritorio) | Por mes: ingresos y gastos **con y sin IVA**, IVA del mes y del trimestre, **qué reclamar a proveedores** y qué falta, sus proveedores, y el **cierre mensual** (bloquea el mes). |
| **Cliente · compras** | App móvil | Sube **albaranes y facturas de proveedor** (foto o PDF). Ve solo lo que ha subido. |
| **Cliente · ventas** | App móvil | Sube la **foto del cierre Z del TPV** cada día (restaurante, tienda). Ve solo sus cierres. |

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

Stack: **FastAPI + SQLAlchemy** · **React + Vite** · **Supabase** (PostgreSQL y Storage, en el proyecto *Genia*) · **Nginx** como capa de entrada · **Tesseract** para el OCR local.

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
 │ Supabase/Genia│
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
- **Roles**: el rol (`gestor`, `cliente_admin`, `cliente_compras`, `cliente_ventas`) sale de la tabla `usuarios` en cada petición, no del token. Compras no puede ver IVA, resumen ni cierres de caja; ventas no puede subir facturas de proveedor; ninguno de los dos ve lo que han subido otros usuarios.
- **Aislamiento entre clientes**: en `/api/movil/*` el `cliente_id` siempre sale del usuario autenticado. Si alguien pide un ID de otro cliente recibe 404.
- **Subidas**: el tipo se detecta por los *magic bytes* (JPG, PNG, WEBP, HEIC, PDF), el nombre lo pone el servidor, hay límite de tamaño y se protege contra *path traversal*.
- **Fotos**: van a un bucket **privado**. El navegador nunca recibe una URL pública: la API comprueba permisos y entrega el fichero.
- `TrustedHostMiddleware`, CORS cerrado, documentación desactivada en producción, errores 500 sin detalles internos y contenedor sin root, de solo lectura y sin capabilities.
- **Auditoría**: tabla `auditoria` con quién, qué, cuándo y desde qué IP. La API no puede modificarla ni borrarla.

### Capa base de datos (Supabase, proyecto Genia)

La gestoría comparte proyecto con otra aplicación (Genia), así que está **aislada de ella**:

- Todas las tablas viven en el esquema propio **`gestoria`**, que no está expuesto en la API REST pública de Supabase y en el que `anon`, `authenticated` y `public` **no tienen ni permiso de uso**. Las tablas de Genia (`public`) no se tocan.
- La API conecta con el rol dedicado **`gestoria_api`** (solo DML sobre `gestoria`, sin DDL, sin acceso a las tablas de Genia) y su `search_path` apunta a `gestoria`.
- **RLS activado y forzado** en las 12 tablas como segunda barrera. La auditoría no se puede modificar ni borrar.
- **No se usa Supabase Auth**: los usuarios de la gestoría no aparecen en `auth.users`, no disparan el trigger de alta de Genia y no tienen acceso a Genia (ni los de Genia a la gestoría).
- Fotos en el bucket **privado `gestoria-facturas`** (máx. 10 MB, solo JPG/PNG/WEBP/HEIC/PDF), sin políticas de Storage: solo el backend, con la clave `service_role`, puede leerlo o escribirlo.
- El frontend no habla con Supabase: datos y fotos pasan siempre por la API.

---

## Puesta en marcha en producción

Las tres migraciones de `supabase/migrations/` **ya están aplicadas** en el proyecto Genia (esquema, tablas, permisos, RLS, rol `gestoria_api` todavía sin login, bucket, albaranes, roles, caja TPV y cierres de mes).

1. **Activa el rol de la API** con una contraseña larga, en *SQL Editor* de Supabase:
   ```sql
   alter role gestoria_api with login password 'UNA_CONTRASEÑA_LARGA_Y_ALEATORIA';
   ```
2. **SSL de la base de datos**: en *Database → Settings → SSL Configuration* descarga el certificado a `certs/supabase-ca.crt`. La API ya exige TLS verificado por su lado; activar además **Enforce SSL** es recomendable, pero afecta a todo el proyecto: comprueba antes que Genia también conecta con SSL.
3. `cp .env.example .env` y rellena `SECRET_KEY`, `SUPABASE_SECRET_KEY` (una clave `sb_secret_` creada solo para la gestoría), el `DATABASE_URL` (host del *Session pooler*, puerto 5432) y tu `DOMINIO`.
4. **Certificado TLS** del dominio con Let's Encrypt (`certbot certonly --webroot -w ./certbot-www -d tu-dominio`), copiado a `certs/fullchain.pem` y `certs/privkey.pem`.
5. `docker compose up -d --build`
6. **Primer gestor** (la contraseña se pide por teclado):
   ```bash
   docker compose exec api python -m app.crear_gestor tu@gestoria.es "Tu Nombre"
   ```
   Desde ahí, los usuarios de cada cliente (administración, compras, ventas) se crean en **Clientes → Usuarios**.

## Desarrollo local (sin Supabase)

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
| Gestoría | gestor@gestoria.local | Gestor.2026 |
| Administración (restaurante) | admin@cliente.local | Cliente.2026 |
| Compras (restaurante) | compras@cliente.local | Cliente.2026 |
| Ventas / caja (restaurante) | ventas@cliente.local | Cliente.2026 |

Tests: `cd backend && pytest` (21 tests). Cubren seguridad (401/403, token manipulado, fuerza bruta, cabeceras, ficheros falsos, aislamiento entre clientes y entre usuarios, permisos por rol), la lectura de fotos reales generadas (factura, albarán torcido, PDF, cierre Z), el cuadre de albaranes con la factura mensual, el cierre y bloqueo del mes, la liquidación con sus asientos y el flujo contable completo.

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
