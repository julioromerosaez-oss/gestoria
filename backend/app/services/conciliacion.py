"""Servicio de conciliación bancaria.

Importa extractos CSV y propone qué factura corresponde a cada movimiento:
  - cobros (importe > 0)  -> facturas de venta
  - pagos  (importe < 0)  -> facturas de compra
Puntuación: importe exacto (obligatorio) + cercanía de fecha + nombre/NIF/número en el concepto.
"""
import csv
import io
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import EstadoFactura, FacturaCompra, FacturaVenta, MovimientoBanco
from .contabilidad import contabilizar_movimiento, redondear

VENTANA_DIAS = 90


def _norm(txt: str | None) -> str:
    txt = unicodedata.normalize("NFKD", txt or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]", " ", txt)


def _importe(txt: str) -> Decimal:
    t = txt.strip().replace("€", "").replace(" ", "")
    if "," in t:  # formato español 1.234,56
        t = t.replace(".", "").replace(",", ".")
    try:
        return redondear(Decimal(t))
    except InvalidOperation:
        raise ValueError(f"Importe no válido: {txt}")


def _fecha(txt: str) -> date:
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(txt.strip(), fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Fecha no válida: {txt}")


def importar_csv(db: Session, cliente_id: int, contenido: str) -> dict:
    """CSV con columnas fecha;concepto;importe (separador ; o ,, con cabecera)."""
    muestra = contenido[:2048]
    dialecto = csv.Sniffer().sniff(muestra, delimiters=";,\t") if muestra.strip() else csv.excel
    lector = csv.DictReader(io.StringIO(contenido), dialect=dialecto)
    campos = {(_norm(c).strip()): c for c in (lector.fieldnames or [])}
    faltan = [c for c in ("fecha", "concepto", "importe") if c not in campos]
    if faltan:
        raise HTTPException(422, f"Faltan columnas en el CSV: {', '.join(faltan)}")
    creados, errores, duplicados = 0, [], 0
    for n, fila in enumerate(lector, start=2):
        try:
            f = _fecha(fila[campos["fecha"]])
            imp = _importe(fila[campos["importe"]])
            concepto = (fila[campos["concepto"]] or "").strip()[:255]
        except (ValueError, TypeError, AttributeError) as e:
            errores.append(f"Línea {n}: {e}")
            continue
        existe = db.scalar(select(MovimientoBanco.id).where(
            MovimientoBanco.cliente_id == cliente_id, MovimientoBanco.fecha == f,
            MovimientoBanco.importe == imp, MovimientoBanco.concepto == concepto))
        if existe:
            duplicados += 1
            continue
        db.add(MovimientoBanco(cliente_id=cliente_id, fecha=f, concepto=concepto, importe=imp))
        creados += 1
    return {"importados": creados, "duplicados": duplicados, "errores": errores[:20]}


def sugerencias(db: Session, mov: MovimientoBanco, limite: int = 5) -> list[dict]:
    if mov.conciliado:
        return []
    importe = abs(redondear(mov.importe))
    if mov.importe < 0:
        modelo, tipo, campo_nombre, campo_nif = FacturaCompra, "compra", "proveedor_nombre", "proveedor_nif"
    else:
        modelo, tipo, campo_nombre, campo_nif = FacturaVenta, "venta", "destinatario_nombre", "destinatario_nif"
    candidatas = db.scalars(select(modelo).where(
        modelo.cliente_id == mov.cliente_id, modelo.conciliada.is_(False),
        modelo.estado.in_((EstadoFactura.validada, EstadoFactura.contabilizada)),
        modelo.total == importe)).all()
    concepto = _norm(mov.concepto)
    resultado = []
    for f in candidatas:
        dias = abs((mov.fecha - f.fecha).days) if f.fecha else VENTANA_DIAS
        if dias > VENTANA_DIAS:
            continue
        puntos = 50 + max(0, 30 - dias // 3)
        nombre = _norm(getattr(f, campo_nombre))
        palabras = [p for p in nombre.split() if len(p) > 3]
        if palabras and any(p in concepto for p in palabras):
            puntos += 15
        nif = _norm(getattr(f, campo_nif)).replace(" ", "")
        if f.numero and _norm(f.numero).replace(" ", "") in concepto.replace(" ", ""):
            puntos += 15
        elif nif and nif in concepto.replace(" ", ""):
            puntos += 10
        resultado.append({"tipo": tipo, "factura_id": f.id, "numero": f.numero, "fecha": f.fecha,
                          "tercero": getattr(f, campo_nombre), "total": f.total,
                          "puntuacion": min(puntos, 100)})
    return sorted(resultado, key=lambda s: -s["puntuacion"])[:limite]


def conciliar(db: Session, mov: MovimientoBanco, tipo: str, factura_id: int) -> MovimientoBanco:
    if mov.conciliado:
        raise HTTPException(409, "El movimiento ya está conciliado")
    modelo = FacturaCompra if tipo == "compra" else FacturaVenta if tipo == "venta" else None
    if modelo is None:
        raise HTTPException(422, "tipo debe ser compra o venta")
    factura = db.get(modelo, factura_id)
    if not factura or factura.cliente_id != mov.cliente_id:
        raise HTTPException(404, "Factura no encontrada para este cliente")
    if factura.conciliada:
        raise HTTPException(409, "La factura ya está conciliada")
    if (tipo == "compra") != (mov.importe < 0):
        raise HTTPException(422, "Un pago se concilia con una compra y un cobro con una venta")
    if factura.estado != EstadoFactura.contabilizada:
        raise HTTPException(409, "Contabiliza la factura antes de conciliarla")
    if abs(redondear(mov.importe)) != redondear(factura.total):
        raise HTTPException(422, "El importe del movimiento no coincide con el total de la factura")
    asiento = contabilizar_movimiento(db, mov, factura)
    mov.conciliado = True
    mov.asiento_id = asiento.id
    if tipo == "compra":
        mov.factura_compra_id = factura.id
    else:
        mov.factura_venta_id = factura.id
    factura.conciliada = True
    return mov
