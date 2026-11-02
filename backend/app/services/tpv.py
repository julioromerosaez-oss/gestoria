"""Ventas del TPV: cierres de caja diarios (informe Z)."""
import json
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import Cliente, EstadoFactura, VentaTPV, VentaTPVIva
from . import almacen
from .contabilidad import crear_asiento, redondear
from .extraccion import extraer_z


def recalcular(v: VentaTPV) -> None:
    v.base_imponible = redondear(sum((d.base for d in v.desglose), Decimal(0)))
    v.cuota_iva = redondear(sum((d.cuota for d in v.desglose), Decimal(0)))
    v.total = v.base_imponible + v.cuota_iva


def poner_desglose(v: VentaTPV, filas: list[dict]) -> None:
    v.desglose = [VentaTPVIva(tipo_iva=Decimal(str(f["tipo_iva"])), base=redondear(f["base"]),
                              cuota=redondear(f.get("cuota") if f.get("cuota") is not None
                                              else Decimal(str(f["base"])) * Decimal(str(f["tipo_iva"])) / 100))
                  for f in filas if Decimal(str(f.get("base") or 0))]
    recalcular(v)


def aplicar(v: VentaTPV, r: dict) -> None:
    if r.get("fecha"):
        v.fecha = r["fecha"]
    v.numero_z = r.get("numero_z") or v.numero_z
    v.num_tickets = r.get("num_tickets") or v.num_tickets
    if r.get("desglose"):
        poner_desglose(v, r["desglose"])
    elif r.get("total"):
        v.total = r["total"]
    v.cobro_efectivo = r.get("efectivo") or Decimal(0)
    v.cobro_tarjeta = r.get("tarjeta") or Decimal(0)
    v.extraccion_confianza = r.get("confianza")
    v.extraccion_avisos = json.dumps(r.get("avisos", []), ensure_ascii=False)


def contabilizar(db: Session, v: VentaTPV):
    """Ventas con ticket: 570 Caja (efectivo) y 572 Bancos (tarjeta) contra 7xx y 477 por tipo."""
    if v.estado == EstadoFactura.contabilizada:
        raise HTTPException(409, "Ya contabilizada")
    if v.estado != EstadoFactura.validada:
        raise HTTPException(409, "Revisa el cierre antes de contabilizarlo")
    if not v.fecha or not v.desglose:
        raise HTTPException(422, "Falta la fecha o el desglose por IVA")
    recalcular(v)
    tarjeta = min(redondear(v.cobro_tarjeta or 0), v.total)
    efectivo = v.total - tarjeta
    concepto = f"Ventas TPV {v.fecha:%d/%m/%Y}" + (f" (Z {v.numero_z})" if v.numero_z else "")
    lineas = [("570", "Cobros en efectivo", efectivo, 0), ("572", "Cobros con tarjeta", tarjeta, 0)]
    for d in v.desglose:
        lineas.append((v.cuenta_ingreso, f"Ventas {d.tipo_iva}%", 0, d.base))
        lineas.append(("477", f"IVA repercutido {d.tipo_iva}%", 0, d.cuota))
    asiento = crear_asiento(db, v.cliente_id, v.fecha, concepto, "venta_tpv", lineas)
    v.asiento_id = asiento.id
    v.estado = EstadoFactura.contabilizada
    return asiento


def leer_y_crear(db: Session, cliente: Cliente, data: bytes, usuario_id: int | None, notas: str | None):
    ext = almacen.validar(data)
    r = extraer_z(data, ext)
    v = VentaTPV(cliente_id=cliente.id, estado=EstadoFactura.pendiente, subido_por_id=usuario_id,
                 notas=(notas or "")[:1000] or None, base_imponible=0, cuota_iva=0, total=0,
                 cobro_efectivo=0, cobro_tarjeta=0)
    aplicar(v, r)
    return v, r, ext
