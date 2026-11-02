"""Almacenamiento de fotos/PDF de facturas.

STORAGE_MODO=supabase -> bucket PRIVADO de Supabase Storage, accedido solo con la
                         service_role key desde el backend. El cliente nunca obtiene
                         acceso directo: la API comprueba permisos y sirve el fichero.
STORAGE_MODO=local    -> disco (UPLOAD_DIR), para desarrollo.

Seguridad de subida: el tipo se detecta por los "magic bytes" (no por la extensión ni el
Content-Type que manda el navegador), el nombre lo genera el servidor (uuid) y hay límite
de tamaño.
"""
import uuid
from pathlib import Path

import httpx
from fastapi import HTTPException, status

from .. import config

_TIPOS = {
    "jpg": "image/jpeg", "png": "image/png", "webp": "image/webp",
    "heic": "image/heic", "pdf": "application/pdf",
}


def detectar_tipo(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[4:8] == b"ftyp" and data[8:12] in (b"heic", b"heix", b"mif1", b"msf1", b"hevc"):
        return "heic"
    if data[:5] == b"%PDF-":
        return "pdf"
    return None


def validar(data: bytes) -> str:
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Fichero vacío")
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            f"Máximo {config.MAX_UPLOAD_MB} MB")
    ext = detectar_tipo(data)
    if not ext:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            "Formato no admitido (JPG, PNG, WEBP, HEIC o PDF)")
    return ext


def _headers() -> dict:
    return {"apikey": config.SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {config.SUPABASE_SERVICE_ROLE_KEY}"}


def guardar(cliente_id: int, data: bytes) -> str:
    ext = validar(data)
    ruta = f"{cliente_id}/{uuid.uuid4().hex}.{ext}"
    if config.STORAGE_MODO == "supabase":
        r = httpx.post(f"{config.SUPABASE_URL}/storage/v1/object/{config.SUPABASE_BUCKET}/{ruta}",
                       headers={**_headers(), "Content-Type": _TIPOS[ext], "x-upsert": "false"},
                       content=data, timeout=60)
        if r.status_code >= 400:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "No se pudo guardar el fichero")
    else:
        destino = config.UPLOAD_DIR / ruta
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(data)
    return ruta


def leer(ruta: str) -> tuple[bytes, str]:
    ext = ruta.rsplit(".", 1)[-1]
    if config.STORAGE_MODO == "supabase":
        r = httpx.get(f"{config.SUPABASE_URL}/storage/v1/object/{config.SUPABASE_BUCKET}/{ruta}",
                      headers=_headers(), timeout=60)
        if r.status_code >= 400:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Fichero no encontrado")
        return r.content, _TIPOS.get(ext, "application/octet-stream")
    base = config.UPLOAD_DIR.resolve()
    fichero = (base / ruta).resolve()
    if base not in fichero.parents or not fichero.is_file():  # evita path traversal
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fichero no encontrado")
    return fichero.read_bytes(), _TIPOS.get(ext, "application/octet-stream")
