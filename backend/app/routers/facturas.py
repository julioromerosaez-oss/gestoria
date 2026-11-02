"""Servicios de facturación de compra y de venta (pantallas de la gestoría)."""
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import auditar, solo_gestor
from ..db import get_db
from ..models import Cliente, EstadoFactura, FacturaCompra, FacturaVenta, OrigenFactura, Usuario
from ..schemas import (AsientoOut, FacturaCompraIn, FacturaCompraOut, FacturaCompraUpdate,
                       FacturaVentaIn, FacturaVentaOut, FacturaVentaUpdate, RechazoIn)
from ..services import almacen, documentos
from ..services.cierres import comprobar_editable
from ..services.contabilidad import calcular_importes, contabilizar_compra, contabilizar_venta


def siguiente_numero_venta(db: Session, cliente: Cliente, fecha: date) -> str:
    prefijo = f"{cliente.serie_venta}{fecha.year}-"
    n = db.scalar(select(func.count(FacturaVenta.id)).where(
        FacturaVenta.cliente_id == cliente.id, FacturaVenta.numero.like(f"{prefijo}%"))) or 0
    while True:
        n += 1
        numero = f"{prefijo}{n:04d}"
        if not db.scalar(select(FacturaVenta.id).where(FacturaVenta.cliente_id == cliente.id,
                                                       FacturaVenta.numero == numero)):
            return numero


def _crear_router(tipo: str, Modelo, In, Update, Out, contabilizar) -> APIRouter:
    r = APIRouter(prefix=f"/api/{tipo}", tags=[tipo], dependencies=[Depends(solo_gestor)])

    def obtener(db: Session, fid: int):
        f = db.get(Modelo, fid)
        if not f:
            raise HTTPException(404, "Factura no encontrada")
        return f

    @r.get("", response_model=list[Out])
    def listar(cliente_id: int | None = None, estado: EstadoFactura | None = None,
               desde: date | None = None, hasta: date | None = None, limite: int = 500,
               db: Session = Depends(get_db)):
        q = select(Modelo).order_by(Modelo.fecha.desc().nulls_first(), Modelo.id.desc())
        if cliente_id:
            q = q.where(Modelo.cliente_id == cliente_id)
        if estado:
            q = q.where(Modelo.estado == estado)
        if desde:
            q = q.where(Modelo.fecha >= desde)
        if hasta:
            q = q.where(Modelo.fecha <= hasta)
        return db.scalars(q.limit(min(limite, 2000))).all()

    @r.post("", response_model=Out, status_code=201)
    def crear(datos: In, request: Request, db: Session = Depends(get_db),
              gestor: Usuario = Depends(solo_gestor)):
        cliente = db.get(Cliente, datos.cliente_id)
        if not cliente:
            raise HTTPException(404, "Cliente no encontrado")
        comprobar_editable(db, datos.cliente_id, datos.fecha, gestor)
        f = Modelo(**datos.model_dump(), origen=OrigenFactura.gestoria, estado=EstadoFactura.validada)
        if tipo == "ventas" and not f.numero:
            f.numero = siguiente_numero_venta(db, cliente, f.fecha or date.today())
        calcular_importes(f)
        db.add(f)
        db.flush()
        auditar(db, request, gestor, "crear", tipo, f.id)
        db.commit()
        return f

    @r.get("/{fid}", response_model=Out)
    def detalle(fid: int, db: Session = Depends(get_db)):
        return obtener(db, fid)

    @r.put("/{fid}", response_model=Out)
    def actualizar(fid: int, datos: Update, request: Request, db: Session = Depends(get_db),
                   gestor: Usuario = Depends(solo_gestor)):
        f = obtener(db, fid)
        if f.estado == EstadoFactura.contabilizada:
            raise HTTPException(409, "Factura contabilizada: no se puede modificar")
        comprobar_editable(db, f.cliente_id, f.fecha, gestor)
        comprobar_editable(db, f.cliente_id, datos.fecha, gestor)
        for k, v in datos.model_dump().items():
            setattr(f, k, v)
        calcular_importes(f)
        auditar(db, request, gestor, "editar", tipo, f.id)
        db.commit()
        return f

    @r.post("/{fid}/validar", response_model=Out)
    def validar(fid: int, request: Request, db: Session = Depends(get_db),
                gestor: Usuario = Depends(solo_gestor)):
        f = obtener(db, fid)
        if f.estado == EstadoFactura.contabilizada:
            raise HTTPException(409, "Ya contabilizada")
        comprobar_editable(db, f.cliente_id, f.fecha, gestor)
        if not f.fecha or not f.base_imponible:
            raise HTTPException(422, "Completa fecha y base imponible antes de validar")
        calcular_importes(f)
        f.estado = EstadoFactura.validada
        f.motivo_rechazo = None
        auditar(db, request, gestor, "validar", tipo, f.id)
        db.commit()
        return f

    @r.post("/{fid}/rechazar", response_model=Out)
    def rechazar(fid: int, datos: RechazoIn, request: Request, db: Session = Depends(get_db),
                 gestor: Usuario = Depends(solo_gestor)):
        f = obtener(db, fid)
        if f.estado == EstadoFactura.contabilizada:
            raise HTTPException(409, "Ya contabilizada")
        f.estado = EstadoFactura.rechazada
        f.motivo_rechazo = datos.motivo[:255]
        auditar(db, request, gestor, "rechazar", tipo, f.id, datos.motivo)
        db.commit()
        return f

    @r.post("/{fid}/contabilizar", response_model=AsientoOut)
    def contabilizar_ep(fid: int, request: Request, db: Session = Depends(get_db),
                        gestor: Usuario = Depends(solo_gestor)):
        f = obtener(db, fid)
        comprobar_editable(db, f.cliente_id, f.fecha, gestor)
        asiento = contabilizar(db, f)
        auditar(db, request, gestor, "contabilizar", tipo, f.id)
        db.commit()
        return asiento

    @r.delete("/{fid}", status_code=204)
    def borrar(fid: int, request: Request, db: Session = Depends(get_db),
               gestor: Usuario = Depends(solo_gestor)):
        f = obtener(db, fid)
        if f.estado == EstadoFactura.contabilizada:
            raise HTTPException(409, "Factura contabilizada: no se puede borrar")
        comprobar_editable(db, f.cliente_id, f.fecha, gestor)
        auditar(db, request, gestor, "borrar", tipo, f.id)
        db.delete(f)
        db.commit()

    @r.get("/{fid}/imagen")
    def imagen(fid: int, db: Session = Depends(get_db)):
        f = obtener(db, fid)
        if not f.imagen_path:
            raise HTTPException(404, "Sin imagen")
        data, mime = almacen.leer(f.imagen_path)
        return Response(data, media_type=mime, headers={"Cache-Control": "private, no-store"})

    @r.post("/{fid}/extraer", response_model=Out)
    def extraer(fid: int, request: Request, sobrescribir: bool = False, db: Session = Depends(get_db),
                gestor: Usuario = Depends(solo_gestor)):
        """Lee la foto con OCR local y rellena los campos vacíos (o todos si sobrescribir)."""
        f = obtener(db, fid)
        if not f.imagen_path:
            raise HTTPException(404, "Sin imagen")
        if f.estado == EstadoFactura.contabilizada:
            raise HTTPException(409, "Factura contabilizada: no se puede modificar")
        documentos.releer(f, sobrescribir)
        auditar(db, request, gestor, "releer", tipo, f.id)
        db.commit()
        return f

    @r.post("/{fid}/imagen", response_model=Out)
    async def subir_imagen(fid: int, request: Request, archivo: UploadFile = File(...),
                           db: Session = Depends(get_db), gestor: Usuario = Depends(solo_gestor)):
        f = obtener(db, fid)
        f.imagen_path = almacen.guardar(f.cliente_id, await archivo.read())
        auditar(db, request, gestor, "subir_imagen", tipo, f.id)
        db.commit()
        return f

    return r


compras = _crear_router("compras", FacturaCompra, FacturaCompraIn, FacturaCompraUpdate,
                        FacturaCompraOut, contabilizar_compra)
ventas = _crear_router("ventas", FacturaVenta, FacturaVentaIn, FacturaVentaUpdate,
                       FacturaVentaOut, contabilizar_venta)
