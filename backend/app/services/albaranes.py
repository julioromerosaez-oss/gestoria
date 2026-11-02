"""Cuadre de albaranes de proveedor con su factura mensual.

Regla: la factura mensual del proveedor debe coincidir con la SUMA de las bases imponibles
de los albaranes que incluye (los albaranes suelen ir sin IVA; el IVA va en la factura).
Los albaranes no cuentan para IVA, margen ni contabilidad: solo la factura.
"""
import re
import unicodedata
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Albaran, EstadoAlbaran, EstadoFactura, FacturaCompra
from .contabilidad import redondear

TOLERANCIA = Decimal("0.05")


def _norm(t: str | None) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().upper()
    t = re.sub(r"\b(S\.?\s?L\.?U?|S\.?\s?A\.?U?|SLU|SAU|S\.?COOP|C\.?B\.?)\b", " ", t)
    return re.sub(r"[^A-Z0-9]+", " ", t).strip()


def clave_proveedor(nif: str | None, nombre: str | None) -> str:
    return (nif or "").upper() or _norm(nombre) or "SIN PROVEEDOR"


def rango_mes(anio: int, mes: int) -> tuple[date, date]:
    return date(anio, mes, 1), date(anio + (mes == 12), mes % 12 + 1, 1)


def resumen_mes(db: Session, cliente_id: int, anio: int, mes: int) -> list[dict]:
    ini, fin = rango_mes(anio, mes)
    albs = db.scalars(select(Albaran).where(
        Albaran.cliente_id == cliente_id, Albaran.estado != EstadoAlbaran.rechazado,
        Albaran.fecha >= ini, Albaran.fecha < fin).order_by(Albaran.fecha, Albaran.id)).all()
    grupos: dict[str, dict] = {}
    for a in albs:
        g = grupos.setdefault(clave_proveedor(a.proveedor_nif, a.proveedor_nombre), {
            "clave": clave_proveedor(a.proveedor_nif, a.proveedor_nombre), "proveedor_nif": a.proveedor_nif,
            "proveedor_nombre": a.proveedor_nombre, "albaranes": [], "suma_base": Decimal(0),
            "pendientes_revision": 0, "facturas": set()})
        g["albaranes"].append(a.id)
        g["suma_base"] += a.base_imponible or 0
        g["proveedor_nombre"] = g["proveedor_nombre"] or a.proveedor_nombre
        if a.estado == EstadoAlbaran.pendiente:
            g["pendientes_revision"] += 1
        if a.factura_compra_id:
            g["facturas"].add(a.factura_compra_id)
    out = []
    for g in grupos.values():
        facturas = [db.get(FacturaCompra, fid) for fid in sorted(g["facturas"])]
        sin_factura = sum(1 for aid in g["albaranes"] if not db.get(Albaran, aid).factura_compra_id)
        base_facturas = sum((f.base_imponible for f in facturas), Decimal(0))
        recibida = None
        if not facturas:
            # ¿ha llegado ya la factura del proveedor aunque nadie la haya cuadrado todavía?
            cands = [c for c in candidatas(db, cliente_id, anio, mes, g["proveedor_nif"], g["proveedor_nombre"],
                                           g["suma_base"]) if not c["albaranes_vinculados"]]
            recibida = cands[0] if cands else None
        if not facturas and recibida:
            situacion = "por_cuadrar"
        elif not facturas:
            situacion = "sin_factura"
        elif sin_factura:
            situacion = "parcial"
        elif abs(base_facturas - g["suma_base"]) <= TOLERANCIA:
            situacion = "cuadra"
        else:
            situacion = "descuadre"
        out.append({**g, "suma_base": float(redondear(g["suma_base"])), "n_albaranes": len(g["albaranes"]),
                    "sin_factura": sin_factura, "situacion": situacion,
                    "facturas": [{"id": f.id, "numero": f.numero, "fecha": f.fecha, "base": float(f.base_imponible),
                                  "total": float(f.total), "estado": f.estado} for f in facturas],
                    "factura_recibida": recibida,
                    "diferencia": float(redondear(base_facturas - g["suma_base"])) if facturas
                    else (recibida["diferencia"] if recibida else None)})
    return sorted(out, key=lambda x: (x["situacion"] == "cuadra", (x["proveedor_nombre"] or "")))


def candidatas(db: Session, cliente_id: int, anio: int, mes: int, nif: str | None, nombre: str | None,
               suma_base: Decimal) -> list[dict]:
    """Facturas de compra del mismo proveedor emitidas en el mes o los dos siguientes."""
    ini, _ = rango_mes(anio, mes)
    fin = date(anio + (mes >= 10), (mes + 2) % 12 + 1, 1)
    q = select(FacturaCompra).where(FacturaCompra.cliente_id == cliente_id,
                                    FacturaCompra.estado != EstadoFactura.rechazada)
    out = []
    for f in db.scalars(q):
        mismo = (nif and f.proveedor_nif and f.proveedor_nif.upper() == nif.upper()) or (
            not nif and nombre and _norm(f.proveedor_nombre) == _norm(nombre))
        if not mismo or (f.fecha and not (ini <= f.fecha < fin)):
            continue
        ya = db.scalars(select(Albaran.id).where(Albaran.factura_compra_id == f.id)).all()
        out.append({"id": f.id, "numero": f.numero, "fecha": f.fecha, "base": float(f.base_imponible),
                    "total": float(f.total), "estado": f.estado, "albaranes_vinculados": len(ya),
                    "diferencia": float(redondear(f.base_imponible - suma_base))})
    return sorted(out, key=lambda c: abs(c["diferencia"]))


def vincular(db: Session, factura_id: int, albaran_ids: list[int], forzar: bool) -> dict:
    factura = db.get(FacturaCompra, factura_id)
    if not factura:
        raise HTTPException(404, "Factura no encontrada")
    if factura.estado in (EstadoFactura.pendiente, EstadoFactura.rechazada):
        raise HTTPException(409, "Revisa primero la factura del proveedor")
    albs = [db.get(Albaran, i) for i in albaran_ids]
    if any(a is None or a.cliente_id != factura.cliente_id for a in albs):
        raise HTTPException(404, "Algún albarán no existe o es de otro cliente")
    for a in albs:
        if a.estado == EstadoAlbaran.pendiente:
            raise HTTPException(409, f"El albarán {a.numero or a.id} está pendiente de revisar")
        if a.estado == EstadoAlbaran.rechazado:
            raise HTTPException(409, f"El albarán {a.numero or a.id} está rechazado")
        if a.factura_compra_id and a.factura_compra_id != factura.id:
            raise HTTPException(409, f"El albarán {a.numero or a.id} ya está en otra factura")
    ya = db.scalars(select(Albaran).where(Albaran.factura_compra_id == factura.id)).all()
    todos = {a.id: a for a in [*ya, *albs]}
    suma = redondear(sum((a.base_imponible or 0) for a in todos.values()))
    diferencia = redondear(factura.base_imponible - suma)
    if abs(diferencia) > TOLERANCIA and not forzar:
        raise HTTPException(409, f"No cuadra: base de la factura {factura.base_imponible} € y suma de "
                                 f"albaranes {suma} € (diferencia {diferencia} €)")
    for a in albs:
        a.factura_compra_id = factura.id
        a.estado = EstadoAlbaran.facturado
    return {"factura_id": factura.id, "albaranes": len(todos), "suma_base": float(suma),
            "base_factura": float(factura.base_imponible), "diferencia": float(diferencia),
            "cuadra": abs(diferencia) <= TOLERANCIA}


def desvincular(db: Session, albaran: Albaran) -> None:
    albaran.factura_compra_id = None
    albaran.estado = EstadoAlbaran.revisado
