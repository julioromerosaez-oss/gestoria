"""Login, renovación y cierre de sesión.

El frontend solo habla con esta API. En AUTH_MODO=supabase es el backend quien llama a
Supabase Auth; el navegador no conoce ninguna URL externa.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..auth import (auditar, crear_token_local, supabase_login_password, supabase_logout,
                    supabase_refresh, usuario_actual, verify_password)
from ..db import get_db
from ..models import Usuario
from ..schemas import LoginIn, TokenOut, UsuarioOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RefreshIn(BaseModel):
    refresh_token: str


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _fallo(db: Session, request: Request, usuario: Usuario | None):
    if usuario:
        usuario.fallos_login += 1
        if usuario.fallos_login >= config.LOGIN_MAX_FALLOS:
            usuario.bloqueado_hasta = _ahora() + timedelta(minutes=config.LOGIN_BLOQUEO_MIN)
            usuario.fallos_login = 0
        auditar(db, request, usuario, "login_fallido")
        db.commit()
    # mismo mensaje exista o no el usuario (no revela emails válidos)
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email o contraseña incorrectos")


@router.post("/login", response_model=TokenOut)
def login(datos: LoginIn, request: Request, db: Session = Depends(get_db)):
    email = datos.email.strip().lower()
    usuario = db.scalar(select(Usuario).where(Usuario.email == email))
    if usuario and usuario.bloqueado_hasta and usuario.bloqueado_hasta > _ahora():
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Demasiados intentos. Prueba de nuevo más tarde.")

    refresh, expira = None, config.TOKEN_MINUTOS * 60
    if config.AUTH_MODO == "supabase":
        sesion = supabase_login_password(email, datos.password)
        if not sesion:
            _fallo(db, request, usuario)
        # el perfil debe existir, estar activo y corresponder a ese usuario de Supabase
        if not usuario or not usuario.activo or usuario.auth_uid != sesion["user"]["id"]:
            supabase_logout(sesion["access_token"])
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Usuario sin acceso a la gestoría")
        token, refresh, expira = sesion["access_token"], sesion["refresh_token"], sesion.get("expires_in", 3600)
    else:
        if not usuario or not usuario.activo or not verify_password(datos.password, usuario.password_hash):
            _fallo(db, request, usuario)
        token = crear_token_local(usuario)

    usuario.fallos_login = 0
    usuario.bloqueado_hasta = None
    auditar(db, request, usuario, "login")
    db.commit()
    return TokenOut(token=token, refresh_token=refresh, expira_en=expira,
                    usuario=UsuarioOut.model_validate(usuario))


@router.post("/refresh")
def refresh(datos: RefreshIn):
    if config.AUTH_MODO != "supabase":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No disponible en modo local")
    sesion = supabase_refresh(datos.refresh_token)
    if not sesion:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión caducada")
    return {"token": sesion["access_token"], "refresh_token": sesion["refresh_token"],
            "expira_en": sesion.get("expires_in", 3600)}


@router.post("/logout", status_code=204)
def logout(cred: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False))):
    if config.AUTH_MODO == "supabase" and cred:
        supabase_logout(cred.credentials)


@router.get("/yo", response_model=UsuarioOut)
def yo(usuario: Usuario = Depends(usuario_actual)):
    return usuario
