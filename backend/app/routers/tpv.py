"""Ventas del TPV (cierres Z) — pantallas de la gestoría."""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..auth import auditar, solo_gestor
from ..db import get_db
from ..models import EstadoFactura, Usuario, VentaTPV
from ..schemas import AsientoOut, RechazoIn
from ..services import almacen, tpv
from ..services.cierres import comprobar_editable
from ..services.extraccion import extraer_z

router = APIRouter(prefix="/api/ventas-tpv", tags=["ventas TPV"], dependencies=[Depends(solo_gestor)])


class DesgloseIn(BaseModel):
    tipo_iva: Decimal
    base: Decimal
    cuota: Decimal | None = None


class VentaTPVUpdate(BaseModel):
    fecha: date | None = None
    numero_z: str | None = None
    num_tickets: int | None = None
    cobro_efectivo: Decimal = Decimal(0)
    cobro_tarjeta: Decimal = Decimal(0)
    cuenta_ingreso: str = "700"
    notas: str | None = None
    desglose: list[DesgloseIn] = []


def _out(v: VentaTPV) -> dict:
    import json
    return {"id": v.id, "cliente_id": v.cliente_id, "fecha": v.fecha, "numero_z": v.numero_z,
            "num_tickets": v.num_tickets, "base_imponible": float(v.base_imponible), "cuota_iva": float(v.cuota_iva),
            "total": float(v.total), "cobro_efectivo": float(v.cobro_efectivo), "cobro_tarjeta": float(v.cobro_tarjeta),
            "cuenta_ingreso": v.cuenta_ingreso, "estado": v.estado, "tiene_imagen": v.tiene_imagen, "notas": v.notas,
            "motivo_rechazo": v.motivo_rechazo, "asiento_id": v.asiento_id,
            "extraccion_confianza": v.extraccion_confianza,
            "extraccion_avisos": json.loads(v.extraccion_avisos) if v.extraccion_avisos else [],
            "desglose": [{"tipo_iva": float(d.tipo_iva), "base": float(d.base), "cuota": float(d.cuota)} for d in v.desglose],
            "creado_en": v.creado_en}


def _obtener(db: Session, vid: int) -> VentaTPV:
    v = db.get(VentaTPV, vid)
    if not v:
        raise HTTPException(404, "Cierre no encontrado")
    return v


@router.get("")
def listar(cliente_id: int | None = None, desde: date | None = None, hasta: date | None = None,
           estado: EstadoFactura | None = None, db: Session = Depends(get_db)):
    q = select(VentaTPV).options(selectinload(VentaTPV.desglose)).order_by(VentaTPV.fecha.desc().nulls_first())
    if cliente_id:
        q = q.where(VentaTPV.cliente_id == cliente_id)
    if desde:
        q = q.where(VentaTPV.fecha >= desde)
    if hasta:
        q = q.where(VentaTPV.fecha <= hasta)
    if estado:
        q = q.where(VentaTPV.estado == estado)
    return [_out(v) for v in db.scalars(q.limit(1000))]


@router.get("/{vid}")
def detalle(vid: int, db: Session = Depends(get_db)):
    return _out(_obtener(db, vid))


@router.put("/{vid}")
def actualizar(vid: int, datos: VentaTPVUpdate, request: Request, db: Session = Depends(get_db),
               gestor: Usuario = Depends(solo_gestor)):
    v = _obtener(db, vid)
    if v.estado == EstadoFactura.contabilizada:
        raise HTTPException(409, "Cierre contabilizado: no se puede modificar")
    comprobar_editable(db, v.cliente_id, v.fecha, gestor)
    comprobar_editable(db, v.cliente_id, datos.fecha, gestor)
    for k in ("fecha", "numero_z", "num_tickets", "cobro_efectivo", "cobro_tarjeta", "cuenta_ingreso", "notas"):
        setattr(v, k, getattr(datos, k))
    tpv.poner_desglose(v, [d.model_dump() for d in datos.desglose])
    auditar(db, request, gestor, "editar", "venta_tpv", v.id)
    db.commit()
    return _out(v)


@router.post("/{vid}/validar")
def validar(vid: int, request: Request, db: Session = Depends(get_db), gestor: Usuario = Depends(solo_gestor)):
    v = _obtener(db, vid)
    if v.estado == EstadoFactura.contabilizada:
        raise HTTPException(409, "Ya contabilizado")
    comprobar_editable(db, v.cliente_id, v.fecha, gestor)
    if not v.fecha or not v.desglose:
        raise HTTPException(422, "Completa la fecha y el desglose por IVA")
    v.estado, v.motivo_rechazo = EstadoFactura.validada, None
    auditar(db, request, gestor, "validar", "venta_tpv", v.id)
    db.commit()
    return _out(v)


@router.post("/{vid}/rechazar")
def rechazar(vid: int, datos: RechazoIn, request: Request, db: Session = Depends(get_db),
             gestor: Usuario = Depends(solo_gestor)):
    v = _obtener(db, vid)
    if v.estado == EstadoFactura.contabilizada:
        raise HTTPException(409, "Ya contabilizado")
    v.estado, v.motivo_rechazo = EstadoFactura.rechazada, datos.motivo[:255]
    auditar(db, request, gestor, "rechazar", "venta_tpv", v.id, datos.motivo)
    db.commit()
    return _out(v)


@router.post("/{vid}/contabilizar", response_model=AsientoOut)
def contabilizar(vid: int, request: Request, db: Session = Depends(get_db), gestor: Usuario = Depends(solo_gestor)):
    v = _obtener(db, vid)
    comprobar_editable(db, v.cliente_id, v.fecha, gestor)
    asiento = tpv.contabilizar(db, v)
    auditar(db, request, gestor, "contabilizar", "venta_tpv", v.id)
    db.commit()
    return asiento


@router.post("/{vid}/extraer")
def releer(vid: int, request: Request, db: Session = Depends(get_db), gestor: Usuario = Depends(solo_gestor)):
    v = _obtener(db, vid)
    if not v.imagen_path or v.estado == EstadoFactura.contabilizada:
        raise HTTPException(409, "Sin imagen o ya contabilizado")
    data, _ = almacen.leer(v.imagen_path)
    tpv.aplicar(v, extraer_z(data, v.imagen_path.rsplit(".", 1)[-1]))
    auditar(db, request, gestor, "releer", "venta_tpv", v.id)
    db.commit()
    return _out(v)


@router.delete("/{vid}", status_code=204)
def borrar(vid: int, request: Request, db: Session = Depends(get_db), gestor: Usuario = Depends(solo_gestor)):
    v = _obtener(db, vid)
    if v.estado == EstadoFactura.contabilizada:
        raise HTTPException(409, "Cierre contabilizado: no se puede borrar")
    comprobar_editable(db, v.cliente_id, v.fecha, gestor)
    auditar(db, request, gestor, "borrar", "venta_tpv", v.id)
    db.delete(v)
    db.commit()


@router.get("/{vid}/imagen")
def imagen(vid: int, db: Session = Depends(get_db)):
    v = _obtener(db, vid)
    if not v.imagen_path:
        raise HTTPException(404, "Sin imagen")
    data, mime = almacen.leer(v.imagen_path)
    return Response(data, media_type=mime, headers={"Cache-Control": "private, no-store"})
