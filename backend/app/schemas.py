from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

import json

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, field_validator

from .models import EstadoAlbaran, EstadoFactura, OrigenFactura, Rol, TipoCliente

Euros = Annotated[Decimal, PlainSerializer(lambda v: float(v), return_type=float, when_used="json")]


def _lista_json(v):
    if v is None or isinstance(v, list):
        return v or []
    try:
        return json.loads(v)
    except ValueError:
        return [str(v)]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Auth ----------
class LoginIn(BaseModel):
    email: str
    password: str


class UsuarioOut(ORM):
    id: int
    email: str
    nombre: str
    rol: Rol
    cliente_id: int | None


class TokenOut(BaseModel):
    token: str
    refresh_token: str | None = None
    expira_en: int
    usuario: UsuarioOut


# ---------- Clientes ----------
class ClienteIn(BaseModel):
    nif: str = Field(min_length=8, max_length=20)
    razon_social: str = Field(min_length=2)
    tipo: TipoCliente = TipoCliente.autonomo
    email: str | None = None
    telefono: str | None = None
    direccion: str | None = None
    iban: str | None = None
    regimen_iva: str = "general"
    serie_venta: str = "A"
    periodo_iva: str = Field("trimestral", pattern="^(trimestral|mensual)$")
    activo: bool = True
    notas: str | None = None


class ClienteOut(ClienteIn, ORM):
    id: int
    creado_en: datetime | None = None
    pendientes: int = 0


class AccesoMovilIn(BaseModel):
    email: str
    nombre: str
    password: str = Field(min_length=8)
    rol: Rol = Rol.cliente_admin


# ---------- Facturas ----------
class FacturaBaseIn(BaseModel):
    numero: str | None = None
    fecha: date | None = None
    base_imponible: Decimal = Decimal("0")
    tipo_iva: Decimal = Decimal("21")
    tipo_irpf: Decimal = Decimal("0")
    concepto: str | None = None
    notas: str | None = None


class FacturaCompraIn(FacturaBaseIn):
    cliente_id: int
    proveedor_nif: str | None = None
    proveedor_nombre: str | None = None
    cuenta_gasto: str = "629"


class FacturaCompraUpdate(FacturaBaseIn):
    proveedor_nif: str | None = None
    proveedor_nombre: str | None = None
    cuenta_gasto: str = "629"


class FacturaVentaIn(FacturaBaseIn):
    cliente_id: int
    destinatario_nif: str | None = None
    destinatario_nombre: str | None = None
    cuenta_ingreso: str = "705"


class FacturaVentaUpdate(FacturaBaseIn):
    destinatario_nif: str | None = None
    destinatario_nombre: str | None = None
    cuenta_ingreso: str = "705"


class _FacturaOut(ORM):
    id: int
    cliente_id: int
    numero: str | None
    fecha: date | None
    base_imponible: Euros
    tipo_iva: Euros
    cuota_iva: Euros
    tipo_irpf: Euros
    cuota_irpf: Euros
    total: Euros
    estado: EstadoFactura
    origen: OrigenFactura
    tiene_imagen: bool = False
    concepto: str | None
    notas: str | None
    motivo_rechazo: str | None
    conciliada: bool
    asiento_id: int | None
    extraccion_confianza: str | None = None
    extraccion_avisos: list[str] = []
    creado_en: datetime | None = None

    _avisos = field_validator("extraccion_avisos", mode="before")(_lista_json)


class FacturaCompraOut(_FacturaOut):
    proveedor_nif: str | None
    proveedor_nombre: str | None
    cuenta_gasto: str


class FacturaVentaOut(_FacturaOut):
    destinatario_nif: str | None
    destinatario_nombre: str | None
    cuenta_ingreso: str


# ---------- Albaranes de proveedor ----------
class AlbaranUpdate(BaseModel):
    proveedor_nif: str | None = None
    proveedor_nombre: str | None = None
    numero: str | None = None
    fecha: date | None = None
    base_imponible: Decimal = Decimal("0")
    tipo_iva: Decimal | None = None
    total: Decimal | None = None
    notas: str | None = None


class AlbaranIn(AlbaranUpdate):
    cliente_id: int


class AlbaranOut(ORM):
    id: int
    cliente_id: int
    proveedor_nif: str | None
    proveedor_nombre: str | None
    numero: str | None
    fecha: date | None
    base_imponible: Euros
    tipo_iva: Euros | None
    total: Euros | None
    estado: EstadoAlbaran
    origen: OrigenFactura
    tiene_imagen: bool = False
    notas: str | None
    motivo_rechazo: str | None
    factura_compra_id: int | None
    extraccion_confianza: str | None = None
    extraccion_avisos: list[str] = []
    creado_en: datetime | None = None

    _avisos = field_validator("extraccion_avisos", mode="before")(_lista_json)


class VincularIn(BaseModel):
    factura_id: int
    albaran_ids: list[int] = Field(min_length=1)
    forzar: bool = False   # vincular aunque la suma no cuadre (queda auditado)


class RechazoIn(BaseModel):
    motivo: str


# ---------- Banco / conciliación ----------
class MovimientoIn(BaseModel):
    cliente_id: int
    fecha: date
    concepto: str
    importe: Decimal


class MovimientoOut(ORM):
    id: int
    cliente_id: int
    fecha: date
    concepto: str
    importe: Euros
    conciliado: bool
    factura_compra_id: int | None
    factura_venta_id: int | None
    asiento_id: int | None


class Sugerencia(BaseModel):
    tipo: str  # compra | venta
    factura_id: int
    numero: str | None
    fecha: date | None
    tercero: str | None
    total: Euros
    puntuacion: int


class ConciliarIn(BaseModel):
    tipo: str  # compra | venta
    factura_id: int


# ---------- Contabilidad ----------
class ApunteIn(BaseModel):
    cuenta: str
    descripcion: str
    debe: Decimal = Decimal("0")
    haber: Decimal = Decimal("0")


class AsientoIn(BaseModel):
    cliente_id: int
    fecha: date
    concepto: str
    apuntes: list[ApunteIn]


class ApunteOut(ORM):
    id: int
    cuenta: str
    descripcion: str
    debe: Euros
    haber: Euros


class AsientoOut(ORM):
    id: int
    cliente_id: int
    ejercicio: int
    numero: int
    fecha: date
    concepto: str
    origen: str
    apuntes: list[ApunteOut]
