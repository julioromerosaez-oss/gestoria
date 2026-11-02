"""Subida de documentos (facturas y albaranes) con lectura automática local.

El cliente sube una foto o PDF desde el móvil. El sistema:
  1. valida y guarda el fichero (bucket privado),
  2. lo lee con OCR local + reglas (services/extraccion.py, sin IA),
  3. decide dónde va si el cliente eligió "automático":
       - pone "albarán"                      -> albaranes (de proveedor)
       - factura cuyo emisor es el cliente   -> facturas de venta
       - cualquier otra factura              -> facturas de compra
  4. crea el registro con los datos leídos en estado "pendiente" para que la gestoría lo revise.
"""
import json

from sqlalchemy.orm import Session

from ..models import (Albaran, Cliente, EstadoAlbaran, EstadoFactura, FacturaCompra, FacturaVenta,
                      OrigenFactura)
from . import almacen
from .contabilidad import calcular_importes
from .extraccion import extraer

TIPOS = ("auto", "compra", "venta", "albaran")


def _vacio(v) -> bool:
    return v is None or v == "" or (not isinstance(v, str) and v == 0)


def aplicar(obj, r: dict, sobrescribir: bool = False) -> None:
    """Rellena el registro con lo leído. Por defecto solo los campos vacíos (no pisa lo revisado)."""
    def poner(campo, valor):
        if valor is not None and (sobrescribir or _vacio(getattr(obj, campo, None))):
            setattr(obj, campo, valor)

    if isinstance(obj, FacturaVenta):
        poner("destinatario_nif", r.get("tercero_nif"))
        poner("destinatario_nombre", r.get("tercero_nombre"))
    else:
        poner("proveedor_nif", r.get("tercero_nif"))
        poner("proveedor_nombre", r.get("tercero_nombre"))
    poner("numero", r.get("numero"))
    poner("fecha", r.get("fecha"))
    poner("base_imponible", r.get("base_imponible"))
    if isinstance(obj, Albaran):
        poner("tipo_iva", r.get("tipo_iva"))
        poner("total", r.get("total"))
    else:
        if r.get("tipo_iva") is not None and (sobrescribir or obj.estado == EstadoFactura.pendiente):
            obj.tipo_iva = r["tipo_iva"]
        if r.get("tipo_irpf") and (sobrescribir or _vacio(obj.tipo_irpf)):
            obj.tipo_irpf = r["tipo_irpf"]
        calcular_importes(obj)
    obj.extraccion_confianza = r.get("confianza")
    obj.extraccion_avisos = json.dumps(r.get("avisos", []), ensure_ascii=False)


def decidir_destino(tipo: str, r: dict) -> str:
    if tipo != "auto":
        return tipo
    if r.get("tipo_documento") == "albaran":
        return "albaran"
    return "venta" if r.get("emisor_es_cliente") else "compra"


def subir(db: Session, cliente: Cliente, data: bytes, tipo: str = "auto", notas: str | None = None,
          origen: OrigenFactura = OrigenFactura.movil, usuario=None, permitidos: set | None = None):
    ext = almacen.validar(data)                     # tipo real y tamaño, antes de nada
    r = extraer(data, ext, cliente.nif)
    destino = decidir_destino(tipo, r)
    if permitidos is not None and destino not in permitidos:
        from fastapi import HTTPException
        raise HTTPException(403, "Este documento parece una factura de venta: lo debe subir administración o ventas")
    if usuario is not None:                         # mes cerrado: no se admite (se avisa al usuario)
        from .cierres import comprobar_editable
        comprobar_editable(db, cliente.id, r.get("fecha"), usuario)
    ruta = almacen.guardar(cliente.id, data)
    comunes = dict(cliente_id=cliente.id, imagen_path=ruta, origen=origen, notas=(notas or "")[:1000] or None,
                   subido_por_id=getattr(usuario, "id", None))
    if destino == "albaran":
        obj = Albaran(**comunes, estado=EstadoAlbaran.pendiente, base_imponible=0)
    elif destino == "venta":
        obj = FacturaVenta(**comunes, estado=EstadoFactura.pendiente, base_imponible=0, tipo_iva=21, tipo_irpf=0)
    else:
        obj = FacturaCompra(**comunes, estado=EstadoFactura.pendiente, base_imponible=0, tipo_iva=21, tipo_irpf=0)
    aplicar(obj, r)
    db.add(obj)
    db.flush()
    return obj, destino, r


def releer(obj, sobrescribir: bool = False) -> dict:
    """Vuelve a leer la imagen ya guardada (botón 'Leer datos de la foto' de la gestoría)."""
    data, _ = almacen.leer(obj.imagen_path)
    db_cliente = obj.cliente if hasattr(obj, "cliente") else None
    r = extraer(data, obj.imagen_path.rsplit(".", 1)[-1], db_cliente.nif if db_cliente else None)
    aplicar(obj, r, sobrescribir=sobrescribir)
    return r
