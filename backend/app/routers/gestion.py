"""Conciliación bancaria, contabilidad (libro diario / sumas y saldos), IVA y panel."""
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..auth import auditar, solo_gestor
from ..db import get_db
from ..models import (Albaran, VentaTPV, Asiento, Auditoria, Cliente, EstadoAlbaran, EstadoFactura, FacturaCompra, FacturaVenta,
                      MovimientoBanco, Usuario)
from ..schemas import (AsientoIn, AsientoOut, ConciliarIn, MovimientoIn, MovimientoOut,
                       Sugerencia)
from ..services import conciliacion, contabilidad, iva

router = APIRouter(prefix="/api", dependencies=[Depends(solo_gestor)])


def _cliente(db: Session, cliente_id: int) -> Cliente:
    c = db.get(Cliente, cliente_id)
    if not c:
        raise HTTPException(404, "Cliente no encontrado")
    return c


# ---------------- Conciliación ----------------
@router.get("/banco/movimientos", response_model=list[MovimientoOut], tags=["conciliacion"])
def movimientos(cliente_id: int, conciliado: bool | None = None, db: Session = Depends(get_db)):
    q = select(MovimientoBanco).where(MovimientoBanco.cliente_id == cliente_id)
    if conciliado is not None:
        q = q.where(MovimientoBanco.conciliado.is_(conciliado))
    return db.scalars(q.order_by(MovimientoBanco.fecha.desc(), MovimientoBanco.id.desc())).all()


@router.post("/banco/movimientos", response_model=MovimientoOut, status_code=201, tags=["conciliacion"])
def crear_movimiento(datos: MovimientoIn, request: Request, db: Session = Depends(get_db),
                     gestor: Usuario = Depends(solo_gestor)):
    _cliente(db, datos.cliente_id)
    mov = MovimientoBanco(**datos.model_dump())
    db.add(mov)
    db.flush()
    auditar(db, request, gestor, "crear", "movimiento", mov.id)
    db.commit()
    return mov


@router.post("/banco/importar", tags=["conciliacion"])
async def importar(request: Request, cliente_id: int = Form(...), archivo: UploadFile = File(...),
                   db: Session = Depends(get_db), gestor: Usuario = Depends(solo_gestor)):
    _cliente(db, cliente_id)
    crudo = await archivo.read()
    if len(crudo) > 5 * 1024 * 1024:
        raise HTTPException(413, "CSV demasiado grande (máx. 5 MB)")
    try:
        texto = crudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = crudo.decode("latin-1")
    resultado = conciliacion.importar_csv(db, cliente_id, texto)
    auditar(db, request, gestor, "importar_extracto", "cliente", cliente_id,
            f"{resultado['importados']} movimientos")
    db.commit()
    return resultado


@router.get("/banco/movimientos/{mid}/sugerencias", response_model=list[Sugerencia], tags=["conciliacion"])
def sugerencias(mid: int, db: Session = Depends(get_db)):
    mov = db.get(MovimientoBanco, mid)
    if not mov:
        raise HTTPException(404, "Movimiento no encontrado")
    return conciliacion.sugerencias(db, mov)


@router.post("/banco/movimientos/{mid}/conciliar", response_model=MovimientoOut, tags=["conciliacion"])
def conciliar(mid: int, datos: ConciliarIn, request: Request, db: Session = Depends(get_db),
              gestor: Usuario = Depends(solo_gestor)):
    mov = db.get(MovimientoBanco, mid)
    if not mov:
        raise HTTPException(404, "Movimiento no encontrado")
    conciliacion.conciliar(db, mov, datos.tipo, datos.factura_id)
    auditar(db, request, gestor, "conciliar", "movimiento", mov.id, f"{datos.tipo} {datos.factura_id}")
    db.commit()
    return mov


# ---------------- Contabilidad ----------------
@router.get("/contabilidad/asientos", response_model=list[AsientoOut], tags=["contabilidad"])
def asientos(cliente_id: int, ejercicio: int | None = None, db: Session = Depends(get_db)):
    ejercicio = ejercicio or date.today().year
    return db.scalars(select(Asiento).options(selectinload(Asiento.apuntes))
                      .where(Asiento.cliente_id == cliente_id, Asiento.ejercicio == ejercicio)
                      .order_by(Asiento.numero.desc())).all()


@router.post("/contabilidad/asientos", response_model=AsientoOut, status_code=201, tags=["contabilidad"])
def asiento_manual(datos: AsientoIn, request: Request, db: Session = Depends(get_db),
                   gestor: Usuario = Depends(solo_gestor)):
    _cliente(db, datos.cliente_id)
    asiento = contabilidad.crear_asiento(
        db, datos.cliente_id, datos.fecha, datos.concepto, "manual",
        [(a.cuenta, a.descripcion, a.debe, a.haber) for a in datos.apuntes])
    auditar(db, request, gestor, "asiento_manual", "asiento", asiento.id)
    db.commit()
    return asiento


@router.get("/contabilidad/sumas-saldos", tags=["contabilidad"])
def sumas_saldos(cliente_id: int, ejercicio: int | None = None, db: Session = Depends(get_db)):
    return contabilidad.sumas_y_saldos(db, cliente_id, ejercicio or date.today().year)


@router.get("/contabilidad/cuentas", tags=["contabilidad"])
def cuentas():
    return [{"cuenta": k, "nombre": v} for k, v in contabilidad.CUENTAS.items()]


# ---------------- IVA ----------------
@router.get("/iva/liquidacion", tags=["iva"])
def liquidacion(cliente_id: int, anio: int, trimestre: int, db: Session = Depends(get_db)):
    _cliente(db, cliente_id)
    if trimestre not in (1, 2, 3, 4):
        raise HTTPException(422, "Trimestre 1-4")
    return iva.liquidacion_iva(db, cliente_id, anio, trimestre)


@router.get("/iva/resumen", tags=["iva"])
def resumen_todos(anio: int, trimestre: int, db: Session = Depends(get_db)):
    """Liquidación del trimestre para todos los clientes activos (vista de campaña)."""
    return [iva.liquidacion_iva(db, c.id, anio, trimestre) | {"razon_social": c.razon_social, "nif": c.nif}
            for c in db.scalars(select(Cliente).where(Cliente.activo.is_(True)).order_by(Cliente.razon_social))]


@router.get("/margen", tags=["iva"])
def margen(cliente_id: int, anio: int, db: Session = Depends(get_db)):
    _cliente(db, cliente_id)
    return iva.margen(db, cliente_id, anio)


# ---------------- Panel ----------------
@router.get("/panel", tags=["panel"])
def panel(db: Session = Depends(get_db)):
    def contar(modelo, *cond):
        return db.scalar(select(func.count(modelo.id)).where(*cond)) or 0
    return {
        "clientes": contar(Cliente, Cliente.activo.is_(True)),
        "compras_pendientes": contar(FacturaCompra, FacturaCompra.estado == EstadoFactura.pendiente),
        "ventas_pendientes": contar(FacturaVenta, FacturaVenta.estado == EstadoFactura.pendiente),
        "por_contabilizar": contar(FacturaCompra, FacturaCompra.estado == EstadoFactura.validada)
        + contar(FacturaVenta, FacturaVenta.estado == EstadoFactura.validada),
        "albaranes_pendientes": contar(Albaran, Albaran.estado == EstadoAlbaran.pendiente),
        "tpv_pendientes": contar(VentaTPV, VentaTPV.estado == EstadoFactura.pendiente),
        "albaranes_sin_factura": contar(Albaran, Albaran.estado == EstadoAlbaran.revisado),
        "movimientos_sin_conciliar": contar(MovimientoBanco, MovimientoBanco.conciliado.is_(False)),
        "ultimas_subidas_movil": _ultimas_pendientes(db),
    }


def _ultimas_pendientes(db: Session, n: int = 10) -> list[dict]:
    filas = []
    for Modelo, tipo, ruta, pendiente in ((FacturaCompra, "compra", "compras", EstadoFactura.pendiente),
                                          (FacturaVenta, "venta", "ventas", EstadoFactura.pendiente),
                                          (Albaran, "albaran", "albaranes", EstadoAlbaran.pendiente),
                                          (VentaTPV, "tpv", "ventas-tpv", EstadoFactura.pendiente)):
        for f in db.scalars(select(Modelo).where(Modelo.estado == pendiente).order_by(Modelo.id.desc()).limit(n)):
            filas.append({"id": f.id, "tipo": tipo, "ruta": ruta, "cliente_id": f.cliente_id,
                          "cliente": f.cliente.razon_social, "creado_en": f.creado_en, "notas": f.notas,
                          "tercero": getattr(f, "proveedor_nombre", None) or getattr(f, "destinatario_nombre", None)
                          or (f"Cierre Z {f.numero_z or ''}" if tipo == "tpv" else None),
                          "confianza": f.extraccion_confianza})
    return sorted(filas, key=lambda x: x["creado_en"] or 0, reverse=True)[:n]


@router.get("/auditoria", tags=["panel"])
def auditoria(limite: int = 100, db: Session = Depends(get_db)):
    filas = db.scalars(select(Auditoria).order_by(Auditoria.id.desc()).limit(min(limite, 500)))
    return [{"fecha": a.fecha, "usuario_id": a.usuario_id, "accion": a.accion, "entidad": a.entidad,
             "entidad_id": a.entidad_id, "detalle": a.detalle, "ip": a.ip} for a in filas]
