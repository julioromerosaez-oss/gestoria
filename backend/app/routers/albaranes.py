"""Albaranes de proveedor (pantallas de la gestoría)."""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import auditar, solo_gestor
from ..db import get_db
from ..models import Albaran, Cliente, EstadoAlbaran, OrigenFactura, Usuario
from ..schemas import AlbaranIn, AlbaranOut, AlbaranUpdate, RechazoIn, VincularIn
from ..services import albaranes as srv
from ..services import almacen, documentos
from ..services.cierres import comprobar_editable

router = APIRouter(prefix="/api/albaranes", tags=["albaranes"], dependencies=[Depends(solo_gestor)])


def _obtener(db: Session, aid: int) -> Albaran:
    a = db.get(Albaran, aid)
    if not a:
        raise HTTPException(404, "Albarán no encontrado")
    return a


@router.get("", response_model=list[AlbaranOut])
def listar(cliente_id: int | None = None, anio: int | None = None, mes: int | None = None,
           estado: EstadoAlbaran | None = None, proveedor: str | None = None, factura_id: int | None = None,
           db: Session = Depends(get_db)):
    q = select(Albaran).order_by(Albaran.fecha.desc().nulls_first(), Albaran.id.desc())
    if cliente_id:
        q = q.where(Albaran.cliente_id == cliente_id)
    if anio and mes:
        ini, fin = srv.rango_mes(anio, mes)
        q = q.where(Albaran.fecha >= ini, Albaran.fecha < fin)
    if estado:
        q = q.where(Albaran.estado == estado)
    if factura_id:
        q = q.where(Albaran.factura_compra_id == factura_id)
    filas = db.scalars(q.limit(2000)).all()
    if proveedor:
        filas = [a for a in filas if srv.clave_proveedor(a.proveedor_nif, a.proveedor_nombre) == proveedor]
    return filas


@router.get("/resumen")
def resumen(cliente_id: int, anio: int, mes: int, db: Session = Depends(get_db)):
    """Albaranes del mes agrupados por proveedor y su situación frente a la factura mensual."""
    if not 1 <= mes <= 12:
        raise HTTPException(422, "Mes 1-12")
    return srv.resumen_mes(db, cliente_id, anio, mes)


@router.get("/candidatas")
def candidatas(cliente_id: int, anio: int, mes: int, proveedor_nif: str | None = None,
               proveedor_nombre: str | None = None, suma_base: Decimal = Decimal(0), db: Session = Depends(get_db)):
    return srv.candidatas(db, cliente_id, anio, mes, proveedor_nif, proveedor_nombre, suma_base)


@router.post("/vincular")
def vincular(datos: VincularIn, request: Request, db: Session = Depends(get_db),
             gestor: Usuario = Depends(solo_gestor)):
    r = srv.vincular(db, datos.factura_id, datos.albaran_ids, datos.forzar)
    auditar(db, request, gestor, "vincular_albaranes", "compras", datos.factura_id,
            f"{len(datos.albaran_ids)} albaranes, diferencia {r['diferencia']}" + (" (forzado)" if datos.forzar else ""))
    db.commit()
    return r


@router.post("", response_model=AlbaranOut, status_code=201)
def crear(datos: AlbaranIn, request: Request, db: Session = Depends(get_db), gestor: Usuario = Depends(solo_gestor)):
    if not db.get(Cliente, datos.cliente_id):
        raise HTTPException(404, "Cliente no encontrado")
    comprobar_editable(db, datos.cliente_id, datos.fecha, gestor)
    a = Albaran(**datos.model_dump(), estado=EstadoAlbaran.revisado, origen=OrigenFactura.gestoria)
    db.add(a)
    db.flush()
    auditar(db, request, gestor, "crear", "albaran", a.id)
    db.commit()
    return a


@router.get("/{aid}", response_model=AlbaranOut)
def detalle(aid: int, db: Session = Depends(get_db)):
    return _obtener(db, aid)


@router.put("/{aid}", response_model=AlbaranOut)
def actualizar(aid: int, datos: AlbaranUpdate, request: Request, db: Session = Depends(get_db),
               gestor: Usuario = Depends(solo_gestor)):
    a = _obtener(db, aid)
    if a.estado == EstadoAlbaran.facturado:
        raise HTTPException(409, "Está incluido en una factura: desvincúlalo antes de modificarlo")
    comprobar_editable(db, a.cliente_id, a.fecha, gestor)
    comprobar_editable(db, a.cliente_id, datos.fecha, gestor)
    for k, v in datos.model_dump().items():
        setattr(a, k, v)
    auditar(db, request, gestor, "editar", "albaran", a.id)
    db.commit()
    return a


@router.post("/{aid}/validar", response_model=AlbaranOut)
def validar(aid: int, request: Request, db: Session = Depends(get_db), gestor: Usuario = Depends(solo_gestor)):
    a = _obtener(db, aid)
    if a.estado == EstadoAlbaran.facturado:
        raise HTTPException(409, "Ya está facturado")
    if not a.fecha or not a.base_imponible:
        raise HTTPException(422, "Completa fecha e importe antes de marcarlo revisado")
    if not (a.proveedor_nif or a.proveedor_nombre):
        raise HTTPException(422, "Falta el proveedor")
    a.estado, a.motivo_rechazo = EstadoAlbaran.revisado, None
    auditar(db, request, gestor, "validar", "albaran", a.id)
    db.commit()
    return a


@router.post("/{aid}/rechazar", response_model=AlbaranOut)
def rechazar(aid: int, datos: RechazoIn, request: Request, db: Session = Depends(get_db),
             gestor: Usuario = Depends(solo_gestor)):
    a = _obtener(db, aid)
    if a.estado == EstadoAlbaran.facturado:
        raise HTTPException(409, "Está incluido en una factura")
    a.estado, a.motivo_rechazo = EstadoAlbaran.rechazado, datos.motivo[:255]
    auditar(db, request, gestor, "rechazar", "albaran", a.id, datos.motivo)
    db.commit()
    return a


@router.post("/{aid}/desvincular", response_model=AlbaranOut)
def desvincular(aid: int, request: Request, db: Session = Depends(get_db), gestor: Usuario = Depends(solo_gestor)):
    a = _obtener(db, aid)
    fid = a.factura_compra_id
    srv.desvincular(db, a)
    auditar(db, request, gestor, "desvincular_albaran", "albaran", a.id, f"factura {fid}")
    db.commit()
    return a


@router.post("/{aid}/extraer", response_model=AlbaranOut)
def extraer(aid: int, request: Request, sobrescribir: bool = False, db: Session = Depends(get_db),
            gestor: Usuario = Depends(solo_gestor)):
    a = _obtener(db, aid)
    if not a.imagen_path:
        raise HTTPException(404, "Sin imagen")
    if a.estado == EstadoAlbaran.facturado:
        raise HTTPException(409, "Ya está facturado")
    documentos.releer(a, sobrescribir)
    auditar(db, request, gestor, "releer", "albaran", a.id)
    db.commit()
    return a


@router.delete("/{aid}", status_code=204)
def borrar(aid: int, request: Request, db: Session = Depends(get_db), gestor: Usuario = Depends(solo_gestor)):
    a = _obtener(db, aid)
    if a.estado == EstadoAlbaran.facturado:
        raise HTTPException(409, "Está incluido en una factura")
    auditar(db, request, gestor, "borrar", "albaran", a.id)
    db.delete(a)
    db.commit()


@router.get("/{aid}/imagen")
def imagen(aid: int, db: Session = Depends(get_db)):
    a = _obtener(db, aid)
    if not a.imagen_path:
        raise HTTPException(404, "Sin imagen")
    data, mime = almacen.leer(a.imagen_path)
    return Response(data, media_type=mime, headers={"Cache-Control": "private, no-store"})
