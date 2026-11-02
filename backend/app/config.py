import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

ENTORNO = os.getenv("ENTORNO", "desarrollo")  # desarrollo | produccion
PRODUCCION = ENTORNO == "produccion"

# --- Base de datos: en producción, la cadena de conexión de Supabase (pooler, puerto 6543/5432)
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'gestoria.db'}")

# --- Autenticación: "supabase" (producción) o "local" (desarrollo / tests)
AUTH_MODO = os.getenv("AUTH_MODO", "local")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
# Clave service_role: SOLO en el backend, nunca en el frontend
# Clave secreta del backend. Recomendada: una clave nueva "sb_secret_..." solo para la gestoría
# (Supabase > Settings > API Keys), revocable sin afectar a otras apps del proyecto.
# Se acepta la antigua service_role (JWT) por compatibilidad: deja de funcionar a finales de 2026.
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = SUPABASE_SECRET_KEY  # nombre antiguo, por compatibilidad
# Proyectos con JWT secret heredado (HS256). Si está vacío se valida con JWKS (claves asimétricas).
# Clave pública (anon/publishable): la usa SOLO el backend para el login. No va al navegador.
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "gestoria-facturas")

# --- Almacenamiento de fotos: "supabase" o "local"
STORAGE_MODO = os.getenv("STORAGE_MODO", AUTH_MODO)

# --- JWT propio (solo AUTH_MODO=local)
SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    if PRODUCCION and AUTH_MODO == "local":
        raise RuntimeError("SECRET_KEY es obligatoria en producción con AUTH_MODO=local")
    SECRET_KEY = "solo-desarrollo-no-usar-en-produccion-0123456789abcdef"
TOKEN_MINUTOS = int(os.getenv("TOKEN_MINUTOS", "480"))

if "supabase" in (AUTH_MODO, STORAGE_MODO) and not SUPABASE_URL:
    raise RuntimeError("Supabase requiere SUPABASE_URL")
if "supabase" in (AUTH_MODO, STORAGE_MODO) and not SUPABASE_SERVICE_ROLE_KEY:
    raise RuntimeError("Supabase requiere SUPABASE_SECRET_KEY en el backend")
if PRODUCCION and AUTH_MODO == "local" and len(SECRET_KEY) < 32:
    raise RuntimeError("SECRET_KEY debe tener al menos 32 caracteres aleatorios")

# Esquema PostgreSQL donde viven las tablas (en Supabase: "gestoria", no expuesto a la API pública)
DB_SCHEMA = os.getenv("DB_SCHEMA", "")

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", BASE_DIR / "uploads"))
FRONTEND_DIST = Path(os.getenv("FRONTEND_DIST", BASE_DIR.parent / "frontend" / "dist"))
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "10"))

CORS_ORIGINS = [o for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o]
ALLOWED_HOSTS = [h for h in os.getenv("ALLOWED_HOSTS", "*").split(",") if h]

LOGIN_MAX_FALLOS = int(os.getenv("LOGIN_MAX_FALLOS", "5"))
LOGIN_BLOQUEO_MIN = int(os.getenv("LOGIN_BLOQUEO_MIN", "15"))

# En desarrollo FastAPI sirve el build del frontend; en producción lo hace Nginx
SERVIR_FRONTEND = os.getenv("SERVIR_FRONTEND", "0" if PRODUCCION else "1") == "1"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def cabeceras_supabase(clave: str | None = None) -> dict:
    """Cabeceras para llamar a Supabase desde el backend.

    Las claves nuevas (sb_secret_ / sb_publishable_) NO son JWT: van solo en `apikey`
    (si se mandan también como `Authorization: Bearer`, Supabase puede rechazarlas).
    Las antiguas (JWT) van en las dos cabeceras."""
    clave = clave or SUPABASE_SECRET_KEY
    if clave.startswith("sb_"):
        return {"apikey": clave}
    return {"apikey": clave, "Authorization": f"Bearer {clave}"}
