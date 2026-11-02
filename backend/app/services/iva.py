"""Servicio de IVA (liquidación trimestral tipo modelo 303) y margen.

Solo cuentan las facturas revisadas (validadas o contabilizadas). Las pendientes de
revisar se informan aparte para que el cliente sepa que el dato puede cambiar.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import EstadoFactura, FacturaCompra, FacturaVenta, VentaTPV, VentaTPVIva
from .contabilidad import redondear

REVISADAS = (EstadoFactura.validada, EstadoFactura.contabilizada)
PLAZOS_303 = {1: "1–20 de abril", 2: "1–20 de julio", 3: "1–20 de octubre", 4: "1–30 de enero"}


def rango_trimestre(anio: int, trimestre: int) -> tuple[date, date]:
    if trimestre not in (1, 2, 3, 4):
        raise ValueError("Trimestre 1-4")
    inicio = date(anio, 3 * trimestre - 2, 1)
    fin = date(anio + 1, 1, 1) if trimestre == 4 else date(anio, 3 * trimestre + 1, 1)
    return inicio, fin


def _por_tipo(db: Session, modelo, cliente_id: int, ini: date, fin: date) -> list[dict]:
    filas = db.execute(
        select(modelo.tipo_iva, func.sum(modelo.base_imponible), func.sum(modelo.cuota_iva),
               func.count(modelo.id))
        .where(modelo.cliente_id == cliente_id, modelo.estado.in_(REVISADAS),
               modelo.fecha >= ini, modelo.fecha < fin)
        .group_by(modelo.tipo_iva).order_by(modelo.tipo_iva.desc())
    ).all()
    return [{"tipo": float(t), "base": float(redondear(b or 0)), "cuota": float(redondear(c or 0)),
             "facturas": n} for t, b, c, n in filas]


def _tpv_por_tipo(db: Session, cliente_id: int, ini: date, fin: date) -> list[dict]:
    """Cierres de caja (tickets): IVA repercutido por tipo."""
    filas = db.execute(
        select(VentaTPVIva.tipo_iva, func.sum(VentaTPVIva.base), func.sum(VentaTPVIva.cuota), func.count(VentaTPV.id.distinct()))
        .join(VentaTPV, VentaTPV.id == VentaTPVIva.venta_id)
        .where(VentaTPV.cliente_id == cliente_id, VentaTPV.estado.in_(REVISADAS),
               VentaTPV.fecha >= ini, VentaTPV.fecha < fin)
        .group_by(VentaTPVIva.tipo_iva)
    ).all()
    return [{"tipo": float(t), "base": float(redondear(b or 0)), "cuota": float(redondear(c or 0)),
             "facturas": n} for t, b, c, n in filas]


def _fusionar(*listas) -> list[dict]:
    acc: dict[float, dict] = {}
    for lista in listas:
        for r in lista:
            a = acc.setdefault(r["tipo"], {"tipo": r["tipo"], "base": 0.0, "cuota": 0.0, "facturas": 0})
            a["base"] = round(a["base"] + r["base"], 2)
            a["cuota"] = round(a["cuota"] + r["cuota"], 2)
            a["facturas"] += r["facturas"]
    return sorted(acc.values(), key=lambda r: -r["tipo"])


def liquidacion_iva_rango(db: Session, cliente_id: int, ini: date, fin: date) -> dict:
    repercutido = _fusionar(_por_tipo(db, FacturaVenta, cliente_id, ini, fin), _tpv_por_tipo(db, cliente_id, ini, fin))
    soportado = _por_tipo(db, FacturaCompra, cliente_id, ini, fin)
    total_rep = sum(Decimal(str(r["cuota"])) for r in repercutido)
    total_sop = sum(Decimal(str(r["cuota"])) for r in soportado)
    resultado = redondear(total_rep - total_sop)
    return {"repercutido": repercutido, "soportado": soportado,
            "total_repercutido": float(redondear(total_rep)), "total_soportado": float(redondear(total_sop)),
            "resultado": float(resultado),
            "situacion": "a ingresar" if resultado > 0 else ("a compensar" if resultado < 0 else "sin actividad")}


def _pendientes(db: Session, cliente_id: int, ini: date | None = None, fin: date | None = None) -> int:
    total = 0
    for modelo in (FacturaCompra, FacturaVenta):
        q = select(func.count(modelo.id)).where(modelo.cliente_id == cliente_id,
                                                modelo.estado == EstadoFactura.pendiente)
        if ini:
            # una factura pendiente sin fecha también puede ser de este trimestre
            q = q.where((modelo.fecha.is_(None)) | ((modelo.fecha >= ini) & (modelo.fecha < fin)))
        total += db.scalar(q) or 0
    return total


def liquidacion_iva(db: Session, cliente_id: int, anio: int, trimestre: int) -> dict:
    ini, fin = rango_trimestre(anio, trimestre)
    return {
        "cliente_id": cliente_id, "anio": anio, "trimestre": trimestre,
        "periodo": f"{trimestre}T {anio}", "desde": ini.isoformat(), "hasta": fin.isoformat(),
        **liquidacion_iva_rango(db, cliente_id, ini, fin),
        "plazo_presentacion": PLAZOS_303[trimestre],
        "facturas_pendientes_revision": _pendientes(db, cliente_id, ini, fin),
    }


def margen(db: Session, cliente_id: int, anio: int) -> dict:
    ini, fin = date(anio, 1, 1), date(anio + 1, 1, 1)
    meses = defaultdict(lambda: {"ingresos": Decimal(0), "gastos": Decimal(0)})
    for modelo, clave in ((FacturaVenta, "ingresos"), (VentaTPV, "ingresos"), (FacturaCompra, "gastos")):
        filas = db.execute(
            select(modelo.fecha, modelo.base_imponible)
            .where(modelo.cliente_id == cliente_id, modelo.estado.in_(REVISADAS),
                   modelo.fecha >= ini, modelo.fecha < fin)
        ).all()
        for fecha, base in filas:
            meses[fecha.month][clave] += Decimal(str(base))
    detalle = []
    tot_i = tot_g = Decimal(0)
    for m in range(1, 13):
        i, g = redondear(meses[m]["ingresos"]), redondear(meses[m]["gastos"])
        tot_i += i
        tot_g += g
        detalle.append({"mes": m, "ingresos": float(i), "gastos": float(g), "margen": float(i - g)})
    beneficio = tot_i - tot_g
    return {
        "cliente_id": cliente_id, "anio": anio, "meses": detalle,
        "ingresos": float(tot_i), "gastos": float(tot_g), "margen": float(beneficio),
        "margen_pct": float(redondear(beneficio / tot_i * 100)) if tot_i else 0.0,
        "facturas_pendientes_revision": _pendientes(db, cliente_id),
    }
