"""Crea (o reactiva) un usuario gestor. Uso:

    docker compose exec api python -m app.crear_gestor tu@gestoria.es "Tu Nombre"

La contraseña se pide por teclado (no queda en el historial de la shell).
"""
import getpass
import sys

from sqlalchemy import select

from . import config
from .auth import hash_password
from .db import SessionLocal
from .models import Rol, Usuario


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    if config.AUTH_MODO != "local":
        raise SystemExit("Con AUTH_MODO=supabase el usuario se crea en Supabase Auth")
    email, nombre = sys.argv[1].strip().lower(), sys.argv[2].strip()
    pw = getpass.getpass("Contraseña (mín. 12 caracteres): ")
    if len(pw) < 12 or pw != getpass.getpass("Repite la contraseña: "):
        raise SystemExit("Contraseña demasiado corta o no coincide")
    db = SessionLocal()
    u = db.scalar(select(Usuario).where(Usuario.email == email))
    if u and u.rol != Rol.gestor:
        raise SystemExit("Ese email pertenece a un usuario cliente")
    if not u:
        u = Usuario(email=email, rol=Rol.gestor, nombre=nombre)
        db.add(u)
    u.nombre, u.password_hash, u.activo, u.fallos_login, u.bloqueado_hasta = nombre, hash_password(pw), True, 0, None
    db.commit()
    print(f"Gestor {email} listo.")


if __name__ == "__main__":
    main()
