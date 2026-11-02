"""API de la gestoría.

En producción NO se expone directamente: corre en la red interna de Docker y solo es
accesible a través de Nginx (TLS, rate limiting, cabeceras, límites). Aun así aplica su
propia defensa en profundidad: hosts permitidos, CORS cerrado, cabeceras de seguridad,
documentación OpenAPI desactivada y errores sin detalles internos.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .db import Base, engine
from .routers import albaranes, auth, clientes, facturas, gestion, meses, movil, tpv

log = logging.getLogger("gestoria")

@asynccontextmanager
async def lifespan(_app):
    # En Supabase las tablas se crean con supabase/migrations/*.sql; esto cubre SQLite/desarrollo
    if engine.url.get_backend_name() == "sqlite":
        Base.metadata.create_all(engine)
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Gestoría API",
    version="1.0.0",
    docs_url=None if config.PRODUCCION else "/api/docs",
    redoc_url=None,
    openapi_url=None if config.PRODUCCION else "/api/openapi.json",
)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=config.ALLOWED_HOSTS)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_credentials=False,
                   allow_methods=["GET", "POST", "PUT", "DELETE"],
                   allow_headers=["Authorization", "Content-Type"])


@app.middleware("http")
async def cabeceras_seguridad(request: Request, call_next):
    respuesta = await call_next(request)
    h = respuesta.headers
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Referrer-Policy", "no-referrer")
    h.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=(self)")
    if request.url.path.startswith("/api/"):
        h.setdefault("Cache-Control", "no-store")
    return respuesta


@app.exception_handler(Exception)
async def error_no_controlado(request: Request, exc: Exception):
    log.exception("Error no controlado en %s", request.url.path)
    return JSONResponse({"detail": "Error interno"}, status_code=500)


@app.get("/api/salud", tags=["salud"])
def salud():
    return {"ok": True}


for r in (auth.router, meses.router, clientes.router, facturas.compras, facturas.ventas, albaranes.router,
          tpv.router, gestion.router, movil.router):
    app.include_router(r)



# ---- Frontend (solo desarrollo; en producción lo sirve Nginx) ----
if config.SERVIR_FRONTEND and config.FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=config.FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{ruta:path}", include_in_schema=False)
    def spa(ruta: str):
        fichero = (config.FRONTEND_DIST / ruta).resolve()
        if ruta and fichero.is_file() and config.FRONTEND_DIST.resolve() in fichero.parents:
            return FileResponse(fichero)
        return FileResponse(config.FRONTEND_DIST / "index.html")
