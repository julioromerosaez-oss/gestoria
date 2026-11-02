"""Servicio de apunte contable (Plan General Contable).

Compra:  (6xx) Gasto        D base
         (472) HP IVA soportado  D cuota IVA
         (4751) HP acreedora retenciones  H cuota IRPF
         (400) Proveedores    H total
Venta:   (430) Clientes     D total
         (473) HP retenciones a cuenta  D cuota IRPF
         (7xx) Ingreso      H base
         (477) HP IVA repercutido  H cuota IVA
Pago:    (400) D / (572) H        Cobro: (572) D / (430) H
"""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (Apunte, Asiento, EstadoFactura, FacturaCompra, FacturaVenta,
                      MovimientoBanco)

CENT = Decimal("0.01")

CUENTAS = {
    "400": "Proveedores", "430": "Clientes", "472": "H.P. IVA soportado",
    "473": "H.P. retenciones y pagos a cuenta", "4751": "H.P. acreedora por retenciones",
    "477": "H.P. IVA repercutido", "572": "Bancos", "600": "Compras de mercaderías",
    "621": "Arrendamientos", "622": "Reparaciones y conservación",
    "623": "Servicios profesionales", "624": "Transportes", "625": "Primas de seguros",
    "626": "Servicios bancarios", "627": "Publicidad", "628": "Suministros",
    "629": "Otros servicios", "700": "Ventas de mercaderías", "705": "Prestaciones de servicios",
}


def redondear(v) -> Decimal:
    return Decimal(str(v)).quantize(CENT, rounding=ROUND_HALF_UP)


def calcular_importes(f) -> None:
    """Recalcula cuota IVA, cuota IRPF y total a partir de base y tipos."""
    base = redondear(f.base_imponible or 0)
    f.base_imponible = base
    f.cuota_iva = redondear(base * Decimal(str(f.tipo_iva or 0)) / 100)
    f.cuota_irpf = redondear(base * Decimal(str(f.tipo_irpf or 0)) / 100)
    f.total = base + f.cuota_iva - f.cuota_irpf


def _siguiente_numero(db: Session, cliente_id: int, ejercicio: int) -> int:
    actual = db.scalar(select(func.max(Asiento.numero))
                       .where(Asiento.cliente_id == cliente_id, Asiento.ejercicio == ejercicio))
    return (actual or 0) + 1


def crear_asiento(db: Session, cliente_id: int, fecha: date, concepto: str, origen: str,
                  lineas: list[tuple[str, str, Decimal, Decimal]]) -> Asiento:
    lineas = [(c, d, redondear(de), redondear(ha)) for c, d, de, ha in lineas
              if redondear(de) or redondear(ha)]
    total_debe = sum(l[2] for l in lineas)
    total_haber = sum(l[3] for l in lineas)
    if not lineas or total_debe != total_haber:
        raise HTTPException(422, f"Asiento descuadrado: debe {total_debe} ≠ haber {total_haber}")
    asiento = Asiento(cliente_id=cliente_id, ejercicio=fecha.year,
                      numero=_siguiente_numero(db, cliente_id, fecha.year),
                      fecha=fecha, concepto=concepto[:255], origen=origen)
    asiento.apuntes = [Apunte(cuenta=c, descripcion=d[:255], debe=de, haber=ha)
                       for c, d, de, ha in lineas]
    db.add(asiento)
    db.flush()
    return asiento


def _comprobar_contabilizable(f) -> None:
    if f.estado == EstadoFactura.contabilizada:
        raise HTTPException(409, "La factura ya está contabilizada")
    if f.estado in (EstadoFactura.pendiente, EstadoFactura.rechazada):
        raise HTTPException(409, "Valida la factura antes de contabilizarla")
    if not f.fecha or not f.base_imponible:
        raise HTTPException(422, "Faltan fecha o base imponible")


def contabilizar_compra(db: Session, f: FacturaCompra) -> Asiento:
    _comprobar_contabilizable(f)
    calcular_importes(f)
    prov = f.proveedor_nombre or "proveedor"
    concepto = f"Fra. {f.numero or 's/n'} {prov}"
    asiento = crear_asiento(db, f.cliente_id, f.fecha, concepto, "compra", [
        (f.cuenta_gasto, concepto, f.base_imponible, 0),
        ("472", f"IVA soportado {f.tipo_iva}%", f.cuota_iva, 0),
        ("4751", f"Retención IRPF {f.tipo_irpf}%", 0, f.cuota_irpf),
        ("400", prov, 0, f.total),
    ])
    f.asiento_id = asiento.id
    f.estado = EstadoFactura.contabilizada
    return asiento


def contabilizar_venta(db: Session, f: FacturaVenta) -> Asiento:
    _comprobar_contabilizable(f)
    calcular_importes(f)
    dest = f.destinatario_nombre or "cliente"
    concepto = f"Fra. {f.numero or 's/n'} {dest}"
    asiento = crear_asiento(db, f.cliente_id, f.fecha, concepto, "venta", [
        ("430", dest, f.total, 0),
        ("473", f"Retención IRPF {f.tipo_irpf}%", f.cuota_irpf, 0),
        (f.cuenta_ingreso, concepto, 0, f.base_imponible),
        ("477", f"IVA repercutido {f.tipo_iva}%", 0, f.cuota_iva),
    ])
    f.asiento_id = asiento.id
    f.estado = EstadoFactura.contabilizada
    return asiento


def contabilizar_movimiento(db: Session, mov: MovimientoBanco, factura) -> Asiento:
    importe = abs(redondear(mov.importe))
    if isinstance(factura, FacturaCompra):
        lineas = [("400", factura.proveedor_nombre or "proveedor", importe, 0),
                  ("572", mov.concepto, 0, importe)]
        origen = "pago"
    else:
        lineas = [("572", mov.concepto, importe, 0),
                  ("430", factura.destinatario_nombre or "cliente", 0, importe)]
        origen = "cobro"
    return crear_asiento(db, mov.cliente_id, mov.fecha,
                         f"{origen.capitalize()} fra. {factura.numero or 's/n'}", origen, lineas)


def sumas_y_saldos(db: Session, cliente_id: int, ejercicio: int) -> list[dict]:
    filas = db.execute(
        select(Apunte.cuenta, func.sum(Apunte.debe), func.sum(Apunte.haber))
        .join(Asiento).where(Asiento.cliente_id == cliente_id, Asiento.ejercicio == ejercicio)
        .group_by(Apunte.cuenta).order_by(Apunte.cuenta)
    ).all()
    out = []
    for cuenta, debe, haber in filas:
        debe, haber = redondear(debe or 0), redondear(haber or 0)
        out.append({"cuenta": cuenta, "nombre": CUENTAS.get(cuenta, ""), "debe": float(debe),
                    "haber": float(haber), "saldo": float(debe - haber)})
    return out
