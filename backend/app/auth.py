"""Autenticación y autorización.

AUTH_MODO=supabase -> el frontend hace login contra Supabase Auth y envía el access_token.
                      Aquí se valida la firma (JWKS o JWT secret heredado), la audiencia
                      y la caducidad, y se busca el perfil en `usuarios` por auth_uid.
                      El rol NUNCA se toma del token (user_metadata es editable por el
                      usuario): sale de nuestra tabla `usuarios`.
AUTH_MODO=local    -> login propio con contraseña PBKDF2 y JWT HS256 (desarrollo/tests).
"""
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .db import get_db
from .models import ROLES_CLIENTE, Auditoria, Rol, Usuario

_bearer = HTTPBearer(auto_error=False)
_ITER = 310_000


# ---------------- contraseñas (modo local) ----------------
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITER)
    return f"pbkdf2${_ITER}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        _, it, salt, dk = stored.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(it))
        return hmac.compare_digest(calc.hex(), dk)
    except ValueError:
        return False


def crear_token_local(usuario: Usuario) -> str:
    ahora = datetime.now(timezone.utc)
    payload = {"sub": str(usuario.id), "iss": "gestoria-local", "aud": "gestoria",
               "iat": ahora, "exp": ahora + timedelta(minutes=config.TOKEN_MINUTOS)}
    return jwt.encode(payload, config.SECRET_KEY, algorithm="HS256")


# ---------------- validación de tokens Supabase ----------------
@lru_cache(maxsize=1)
def _jwks_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{config.SUPABASE_URL}/auth/v1/.well-known/jwks.json", cache_keys=True)


def decodificar_token_supabase(token: str) -> dict:
    opciones = dict(audience="authenticated", issuer=f"{config.SUPABASE_URL}/auth/v1",
                    options={"require": ["exp", "sub", "aud"]})
    if config.SUPABASE_JWT_SECRET:
        return jwt.decode(token, config.SUPABASE_JWT_SECRET, algorithms=["HS256"], **opciones)
    clave = _jwks_client().get_signing_key_from_jwt(token)
    return jwt.decode(token, clave.key, algorithms=["ES256", "RS256"], **opciones)


def _buscar_usuario(token: str, db: Session) -> Usuario | None:
    if config.AUTH_MODO == "supabase":
        payload = decodificar_token_supabase(token)
        return db.scalar(select(Usuario).where(Usuario.auth_uid == payload["sub"]))
    payload = jwt.decode(token, config.SECRET_KEY, algorithms=["HS256"], audience="gestoria",
                         issuer="gestoria-local")
    return db.get(Usuario, int(payload["sub"]))


def usuario_actual(cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
                   db: Session = Depends(get_db)) -> Usuario:
    if cred is None or cred.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No autenticado",
                            headers={"WWW-Authenticate": "Bearer"})
    try:
        usuario = _buscar_usuario(cred.credentials, db)
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido o caducado",
                            headers={"WWW-Authenticate": "Bearer"})
    if not usuario or not usuario.activo:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Usuario sin acceso a la gestoría")
    return usuario


def solo_gestor(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
    if usuario.rol != Rol.gestor:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo personal de la gestoría")
    return usuario


def solo_cliente(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
    """Cualquier usuario de un cliente (administración, compras o ventas)."""
    if usuario.rol not in ROLES_CLIENTE or usuario.cliente_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo usuarios cliente")
    return usuario


def requiere(*roles: Rol):
    """Dependencia: el usuario cliente debe tener uno de estos roles."""
    def _dep(usuario: Usuario = Depends(solo_cliente)) -> Usuario:
        if usuario.rol not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Tu usuario no tiene permiso para esta función")
        return usuario
    return _dep


# ---------------- login contra Supabase Auth (desde el servidor) ----------------
# El navegador NUNCA habla con Supabase: envía email/contraseña a nuestra API y es el
# backend quien llama a Supabase Auth. Así el frontend no conoce ninguna URL externa.
def _auth_headers() -> dict:
    clave = config.SUPABASE_ANON_KEY or config.SUPABASE_SERVICE_ROLE_KEY
    return {"apikey": clave, "Content-Type": "application/json"}


def supabase_login_password(email: str, password: str) -> dict | None:
    """Devuelve {access_token, refresh_token, expires_in, user} o None si las credenciales fallan."""
    r = httpx.post(f"{config.SUPABASE_URL}/auth/v1/token?grant_type=password",
                   headers=_auth_headers(), json={"email": email, "password": password}, timeout=15)
    if r.status_code in (400, 401, 422):
        return None
    if r.status_code >= 400:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Servicio de autenticación no disponible")
    return r.json()


def supabase_refresh(refresh_token: str) -> dict | None:
    r = httpx.post(f"{config.SUPABASE_URL}/auth/v1/token?grant_type=refresh_token",
                   headers=_auth_headers(), json={"refresh_token": refresh_token}, timeout=15)
    return r.json() if r.status_code < 400 else None


def supabase_logout(access_token: str) -> None:
    try:
        httpx.post(f"{config.SUPABASE_URL}/auth/v1/logout",
                   headers=_auth_headers() | {"Authorization": f"Bearer {access_token}"}, timeout=10)
    except httpx.HTTPError:
        pass


# ---------------- alta de usuarios en Supabase Auth ----------------
def crear_usuario_supabase(email: str, password: str, nombre: str) -> str:
    """Crea el usuario en Supabase Auth (Admin API) y devuelve su UUID."""
    r = httpx.post(
        f"{config.SUPABASE_URL}/auth/v1/admin/users",
        headers={"apikey": config.SUPABASE_SERVICE_ROLE_KEY,
                 "Authorization": f"Bearer {config.SUPABASE_SERVICE_ROLE_KEY}"},
        json={"email": email, "password": password, "email_confirm": True,
              "user_metadata": {"nombre": nombre}},
        timeout=15,
    )
    if r.status_code >= 400:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Supabase Auth: {r.json().get('msg', r.text)}")
    return r.json()["id"]


# ---------------- auditoría ----------------
def ip_cliente(request: Request) -> str | None:
    # Nginx pone X-Real-IP; uvicorn con --proxy-headers ya resuelve request.client
    return request.headers.get("x-real-ip") or (request.client.host if request.client else None)


def auditar(db: Session, request: Request | None, usuario: Usuario | None, accion: str,
            entidad: str | None = None, entidad_id: int | None = None, detalle: str | None = None):
    db.add(Auditoria(usuario_id=usuario.id if usuario else None, accion=accion, entidad=entidad,
                     entidad_id=entidad_id, detalle=(detalle or "")[:255] or None,
                     ip=ip_cliente(request) if request else None))
