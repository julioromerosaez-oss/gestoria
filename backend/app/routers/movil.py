"""API de la app de los clientes, con permisos por rol.

  cliente_admin    ve todo su negocio por mes: resumen con y sin IVA, qué falta, reclamaciones,
                   proveedores, y hace el cierre mensual. También puede subir documentos.
  cliente_compras  sube albaranes y facturas de proveedor; ve solo lo que ha subido él.
  cliente_ventas   sube los cierres Z del TPV (y facturas de venta); ve solo lo suyo.

Aislamiento: el cliente_id SIEMPRE sale del usuario autenticado, nunca de la petición.
"""
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import auditar, requiere, solo_cliente
from ..db import get_db
from ..models import Albaran, Cliente, FacturaCompra, FacturaVenta, Rol, Usuario, VentaTPV
from ..services import almacen, cierres, documentos, iva, tpv

router = APIRouter(prefix="/api/movil", tags=["app cliente"])
ADMIN = requiere(Rol.cliente_admin)
# qué tipos de documento puede subir cada rol
TIPOS_POR_ROL = {Rol.cliente_admin: {"auto", "compra", "venta", "albaran"},
                 Rol.cliente_compras: {"auto", "compra", "albaran"},
                 Rol.cliente_ventas: {"venta"}}


def _trimestre_actual() -> tuple[int, int]:
    hoy = date.today()
    return hoy.year, (hoy.month - 1) // 3 + 1


@router.get("/perfil")
def perfil(usuario: Usuario = Depends(solo_cliente), db: Session = Depends(get_db)):
    c = db.get(Cliente, usuario.cliente_id)
    return {"nombre": usuario.nombre, "email": usuario.email, "rol": usuario.rol,
            "razon_social": c.razon_social, "nif": c.nif, "periodo_iva": c.periodo_iva}


# ------------------------------------------------------------------ subir documentos
@router.post("/facturas", status_code=201)
def subir_documento(request: Request, foto: UploadFile = File(...), tipo: str = Form("auto"),
                    notas: str | None = Form(None), usuario: Usuario = Depends(solo_cliente),
                    db: Session = Depends(get_db)):
    """Factura o albarán. Se lee en el servidor (OCR local, sin IA) y se archiva donde toque.
    tipo: auto (el sistema decide) | compra | venta | albaran"""
    if tipo not in TIPOS_POR_ROL[usuario.rol]:
        raise HTTPException(403, "Tu usuario no puede subir este tipo de documento")
    cliente = db.get(Cliente, usuario.cliente_id)
    obj, destino, r = documentos.subir(db, cliente, foto.file.read(), tipo, notas, usuario=usuario,
                                       permitidos=TIPOS_POR_ROL[usuario.rol])
    auditar(db, request, usuario, "subida_movil", destino, obj.id, f"lectura {r.get('confianza')}")
    db.commit()
    return {"id": obj.id, "tipo": destino, "estado": obj.estado,
            "leido": {"tercero": r.get("tercero_nombre"), "nif": r.get("tercero_nif"), "numero": r.get("numero"),
                      "fecha": r.get("fecha"), "base": r.get("base_imponible"),
                      "total": r.get("total") or getattr(obj, "total", None), "confianza": r.get("confianza"),
                      "avisos": r.get("avisos", [])}}


@router.post("/cierres-z", status_code=201)
def subir_cierre_z(request: Request, foto: UploadFile = File(...), notas: str | None = Form(None),
                   usuario: Usuario = Depends(requiere(Rol.cliente_ventas, Rol.cliente_admin)),
                   db: Session = Depends(get_db)):
    """Foto del informe Z del TPV (cierre de caja diario)."""
    cliente = db.get(Cliente, usuario.cliente_id)
    data = foto.file.read()
    v, r, _ = tpv.leer_y_crear(db, cliente, data, usuario.id, notas)
    cierres.comprobar_editable(db, cliente.id, v.fecha, usuario)
    if v.fecha and db.scalar(select(VentaTPV.id).where(VentaTPV.cliente_id == cliente.id, VentaTPV.fecha == v.fecha,
                                                       VentaTPV.numero_z == v.numero_z)) and v.numero_z:
        raise HTTPException(409, f"El cierre Z {v.numero_z} del {v.fecha:%d/%m/%Y} ya está subido")
    v.imagen_path = almacen.guardar(cliente.id, data)
    db.add(v)
    db.flush()
    auditar(db, request, usuario, "subida_movil", "venta_tpv", v.id, f"lectura {r.get('confianza')}")
    db.commit()
    return {"id": v.id, "tipo": "tpv", "estado": v.estado,
            "leido": {"fecha": v.fecha, "numero_z": v.numero_z, "num_tickets": v.num_tickets,
                      "total": float(v.total), "efectivo": float(v.cobro_efectivo), "tarjeta": float(v.cobro_tarjeta),
                      "desglose": [{"tipo_iva": float(d.tipo_iva), "base": float(d.base), "cuota": float(d.cuota)}
                                   for d in v.desglose],
                      "confianza": r.get("confianza"), "avisos": r.get("avisos", [])}}


# ------------------------------------------------------------------ documentos
def _fila(f, tipo: str) -> dict:
    tercero = getattr(f, "proveedor_nombre", None) or getattr(f, "destinatario_nombre", None)
    if tipo == "tpv":
        tercero = f"Cierre de caja{' Z ' + f.numero_z if f.numero_z else ''}"
    return {"id": f.id, "tipo": tipo, "numero": getattr(f, "numero", None) or getattr(f, "numero_z", None),
            "fecha": f.fecha, "tercero": tercero, "base": float(f.base_imponible or 0),
            "iva": float(getattr(f, "cuota_iva", 0) or 0), "total": float(f.total or f.base_imponible or 0),
            "factura_id": getattr(f, "factura_compra_id", None), "estado": f.estado,
            "motivo_rechazo": f.motivo_rechazo, "tiene_imagen": f.tiene_imagen, "subida": f.creado_en,
            "notas": f.notas, "confianza": f.extraccion_confianza}


@router.get("/facturas")
def mis_documentos(anio: int | None = None, mes: int | None = None, usuario: Usuario = Depends(solo_cliente),
                   db: Session = Depends(get_db)):
    """Administración ve todo el negocio; compras y ventas, solo lo que ha subido cada uno."""
    out = []
    modelos = {Rol.cliente_admin: (("compra", FacturaCompra), ("venta", FacturaVenta), ("albaran", Albaran), ("tpv", VentaTPV)),
               Rol.cliente_compras: (("compra", FacturaCompra), ("albaran", Albaran)),
               Rol.cliente_ventas: (("venta", FacturaVenta), ("tpv", VentaTPV))}[usuario.rol]
    for tipo, Modelo in modelos:
        q = select(Modelo).where(Modelo.cliente_id == usuario.cliente_id)
        if usuario.rol != Rol.cliente_admin:
            q = q.where(Modelo.subido_por_id == usuario.id)
        if anio and mes:
            ini, fin = cierres.rango(anio, mes)
            q = q.where(((Modelo.fecha >= ini) & (Modelo.fecha < fin)) | Modelo.fecha.is_(None))
        out += [_fila(f, tipo) for f in db.scalars(q.order_by(Modelo.id.desc()).limit(300))]
    return sorted(out, key=lambda x: (x["subida"] is not None, x["subida"] or 0), reverse=True)


@router.get("/facturas/{tipo}/{fid}/imagen")
def imagen(tipo: str, fid: int, usuario: Usuario = Depends(solo_cliente), db: Session = Depends(get_db)):
    Modelo = {"compra": FacturaCompra, "venta": FacturaVenta, "albaran": Albaran, "tpv": VentaTPV}.get(tipo)
    f = db.get(Modelo, fid) if Modelo else None
    propio = f and f.cliente_id == usuario.cliente_id and (
        usuario.rol == Rol.cliente_admin or f.subido_por_id == usuario.id)
    if not propio or not f.imagen_path:
        raise HTTPException(404, "No encontrada")  # 404 también si es de otro cliente o de otro usuario
    data, mime = almacen.leer(f.imagen_path)
    return Response(data, media_type=mime, headers={"Cache-Control": "private, no-store"})


# ------------------------------------------------------------------ administración: mes, IVA, margen
@router.get("/meses")
def meses(anio: int, usuario: Usuario = Depends(ADMIN), db: Session = Depends(get_db)):
    return cierres.meses_del_anio(db, usuario.cliente_id, anio)


@router.get("/meses/{anio}/{mes}")
def mes(anio: int, mes: int, usuario: Usuario = Depends(ADMIN), db: Session = Depends(get_db)):
    if not 1 <= mes <= 12:
        raise HTTPException(422, "Mes 1-12")
    return {"resumen": cierres.resumen(db, usuario.cliente_id, anio, mes),
            "pendientes": cierres.pendientes(db, usuario.cliente_id, anio, mes, para_cliente=True)}


@router.post("/meses/{anio}/{mes}/cerrar")
def cerrar_mes(anio: int, mes: int, request: Request, usuario: Usuario = Depends(ADMIN),
               db: Session = Depends(get_db)):
    if not 1 <= mes <= 12:
        raise HTTPException(422, "Mes 1-12")
    c = cierres.cerrar(db, usuario.cliente_id, anio, mes, usuario)
    auditar(db, request, usuario, "cerrar_mes", "cliente", usuario.cliente_id, f"{mes:02d}/{anio}")
    db.commit()
    return {"estado": c.estado, "cerrado_en": c.cerrado_en}


@router.get("/proveedores")
def proveedores(anio: int, usuario: Usuario = Depends(ADMIN), db: Session = Depends(get_db)):
    return cierres.proveedores(db, usuario.cliente_id, anio)


@router.get("/iva")
def mi_iva(anio: int | None = None, trimestre: int | None = None,
           usuario: Usuario = Depends(ADMIN), db: Session = Depends(get_db)):
    a, t = _trimestre_actual()
    trimestre = trimestre or t
    if trimestre not in (1, 2, 3, 4):
        raise HTTPException(422, "Trimestre 1-4")
    return iva.liquidacion_iva(db, usuario.cliente_id, anio or a, trimestre)


@router.get("/margen")
def mi_margen(anio: int | None = None, usuario: Usuario = Depends(ADMIN), db: Session = Depends(get_db)):
    return iva.margen(db, usuario.cliente_id, anio or date.today().year)
