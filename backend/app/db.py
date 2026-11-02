"""Conexión a base de datos.

Con PostgreSQL (Supabase) la conexión va SIEMPRE cifrada con TLS:
  - DB_SSLMODE (por defecto "verify-full" en producción, "require" en desarrollo)
  - DB_SSLROOTCERT: ruta al certificado CA de Supabase (Dashboard > Database > SSL)
    necesario para verify-full, que además de cifrar comprueba que el servidor es Supabase.
En producción se rechaza arrancar sin TLS verificado.
"""
import os

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from . import config


def _connect_args() -> dict:
    url = make_url(config.DATABASE_URL)
    if url.get_backend_name() == "sqlite":
        return {"check_same_thread": False}
    sslmode = url.query.get("sslmode") or os.getenv(
        "DB_SSLMODE", "verify-full" if config.PRODUCCION else "require")
    if sslmode in ("disable", "allow", "prefer"):
        raise RuntimeError(f"sslmode={sslmode} no permitido: la conexión a la BBDD debe ir cifrada")
    if config.PRODUCCION and sslmode != "verify-full":
        raise RuntimeError("En producción la BBDD debe usar sslmode=verify-full")
    args = {"sslmode": sslmode, "application_name": "gestoria-api"}
    rootcert = url.query.get("sslrootcert") or os.getenv("DB_SSLROOTCERT")
    if sslmode in ("verify-ca", "verify-full"):
        if not rootcert or not os.path.isfile(rootcert):
            raise RuntimeError("sslmode verify-full requiere DB_SSLROOTCERT con el certificado de Supabase")
        args["sslrootcert"] = rootcert
    return args


engine = create_engine(config.DATABASE_URL, connect_args=_connect_args(), pool_pre_ping=True,
                       future=True)

if config.DB_SCHEMA and engine.url.get_backend_name() == "postgresql":
    if not config.DB_SCHEMA.isidentifier():
        raise RuntimeError("DB_SCHEMA no válido")

    @event.listens_for(engine, "connect")
    def _fijar_esquema(dbapi_conn, _record):
        # Las tablas viven en un esquema propio, aislado del resto de aplicaciones del proyecto
        # autocommit para que el SET no se pierda con el rollback de la primera transacción
        dbapi_conn.autocommit = True
        with dbapi_conn.cursor() as cur:
            cur.execute(f'set search_path to "{config.DB_SCHEMA}"')
        dbapi_conn.autocommit = False
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
