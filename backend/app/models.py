"""Modelo de datos de la gestoría.

Tablas:
  usuarios            -> gestores y usuarios cliente (login)
  clientes            -> empresas / autónomos a los que lleva la gestoría
  facturas_compra     -> servicio de facturación de compra (gastos, IVA soportado)
  facturas_venta      -> servicio de facturación de venta (ingresos, IVA repercutido)
  movimientos_banco   -> extractos bancarios para el servicio de conciliación
  asientos / apuntes  -> servicio de apunte contable (libro diario, PGC)
El servicio de IVA y el margen se calculan sobre facturas_compra / facturas_venta.
"""
import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (Boolean, Date, DateTime, Enum, ForeignKey, Integer, Numeric,
                        String, Text, UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

Dinero = Numeric(14, 2)
Porcentaje = Numeric(5, 2)


class Rol(str, enum.Enum):
    gestor = "gestor"                    # personal de la gestoría
    cliente_admin = "cliente_admin"      # administración del cliente: ve todo su mes, reclama, cierra
    cliente_compras = "cliente_compras"  # sube albaranes y facturas de proveedor
    cliente_ventas = "cliente_ventas"    # sube los cierres Z del TPV (y facturas de venta)


ROLES_CLIENTE = (Rol.cliente_admin, Rol.cliente_compras, Rol.cliente_ventas)


class TipoCliente(str, enum.Enum):
    autonomo = "autonomo"
    sociedad = "sociedad"


class EstadoFactura(str, enum.Enum):
    pendiente = "pendiente"          # subida desde el móvil, falta revisar datos
    validada = "validada"            # datos revisados por la gestoría
    contabilizada = "contabilizada"  # asiento generado
    rechazada = "rechazada"          # foto ilegible / duplicada / no deducible


class OrigenFactura(str, enum.Enum):
    movil = "movil"
    gestoria = "gestoria"


class Usuario(Base):
    __tablename__ = "usuarios"
    id: Mapped[int] = mapped_column(primary_key=True)
    # UUID del usuario en Supabase Auth (auth.users.id). Nulo en modo local.
    auth_uid: Mapped[str | None] = mapped_column(String(36), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(160))
    # Solo en modo local; con Supabase la contraseña la guarda Supabase Auth
    password_hash: Mapped[str | None] = mapped_column(String(255))
    fallos_login: Mapped[int] = mapped_column(Integer, default=0)
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(DateTime)
    rol: Mapped[Rol] = mapped_column(Enum(Rol, name="rol_usuario"))
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    cliente: Mapped["Cliente | None"] = relationship(back_populates="usuarios")


class Cliente(Base):
    __tablename__ = "clientes"
    id: Mapped[int] = mapped_column(primary_key=True)
    nif: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    razon_social: Mapped[str] = mapped_column(String(200))
    tipo: Mapped[TipoCliente] = mapped_column(Enum(TipoCliente, name="tipo_cliente"), default=TipoCliente.autonomo)
    email: Mapped[str | None] = mapped_column(String(160))
    telefono: Mapped[str | None] = mapped_column(String(30))
    direccion: Mapped[str | None] = mapped_column(String(255))
    iban: Mapped[str | None] = mapped_column(String(34))
    regimen_iva: Mapped[str] = mapped_column(String(40), default="general")
    serie_venta: Mapped[str] = mapped_column(String(10), default="A")
    periodo_iva: Mapped[str] = mapped_column(String(12), default="trimestral")  # trimestral | mensual
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    notas: Mapped[str | None] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    usuarios: Mapped[list[Usuario]] = relationship(back_populates="cliente")


class _FacturaBase:
    id: Mapped[int] = mapped_column(primary_key=True)
    numero: Mapped[str | None] = mapped_column(String(40))
    fecha: Mapped[date | None] = mapped_column(Date, index=True)
    base_imponible: Mapped[Decimal] = mapped_column(Dinero, default=0)
    tipo_iva: Mapped[Decimal] = mapped_column(Porcentaje, default=21)
    cuota_iva: Mapped[Decimal] = mapped_column(Dinero, default=0)
    tipo_irpf: Mapped[Decimal] = mapped_column(Porcentaje, default=0)
    cuota_irpf: Mapped[Decimal] = mapped_column(Dinero, default=0)
    total: Mapped[Decimal] = mapped_column(Dinero, default=0)
    estado: Mapped[EstadoFactura] = mapped_column(Enum(EstadoFactura, name="estado_factura"),
                                                  default=EstadoFactura.pendiente, index=True)
    origen: Mapped[OrigenFactura] = mapped_column(Enum(OrigenFactura, name="origen_factura"),
                                                  default=OrigenFactura.gestoria)
    imagen_path: Mapped[str | None] = mapped_column(String(255))
    concepto: Mapped[str | None] = mapped_column(String(255))
    notas: Mapped[str | None] = mapped_column(Text)
    motivo_rechazo: Mapped[str | None] = mapped_column(String(255))
    conciliada: Mapped[bool] = mapped_column(Boolean, default=False)
    # Lectura automática del documento (OCR local): alta | media | baja | error
    extraccion_confianza: Mapped[str | None] = mapped_column(String(10))
    extraccion_avisos: Mapped[str | None] = mapped_column(Text)  # JSON: lista de avisos
    subido_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    @property
    def tiene_imagen(self) -> bool:
        return bool(self.imagen_path)


class FacturaCompra(_FacturaBase, Base):
    __tablename__ = "facturas_compra"
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"), index=True)
    proveedor_nif: Mapped[str | None] = mapped_column(String(20))
    proveedor_nombre: Mapped[str | None] = mapped_column(String(200))
    cuenta_gasto: Mapped[str] = mapped_column(String(10), default="629")  # PGC grupo 6
    asiento_id: Mapped[int | None] = mapped_column(ForeignKey("asientos.id", ondelete="SET NULL"))

    cliente: Mapped[Cliente] = relationship()


class FacturaVenta(_FacturaBase, Base):
    __tablename__ = "facturas_venta"
    __table_args__ = (UniqueConstraint("cliente_id", "numero", name="uq_venta_numero"),)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"), index=True)
    destinatario_nif: Mapped[str | None] = mapped_column(String(20))
    destinatario_nombre: Mapped[str | None] = mapped_column(String(200))
    cuenta_ingreso: Mapped[str] = mapped_column(String(10), default="705")  # PGC grupo 7
    asiento_id: Mapped[int | None] = mapped_column(ForeignKey("asientos.id", ondelete="SET NULL"))

    cliente: Mapped[Cliente] = relationship()


class EstadoAlbaran(str, enum.Enum):
    pendiente = "pendiente"    # subido, falta revisar los datos leídos
    revisado = "revisado"      # datos comprobados, a la espera de la factura del proveedor
    facturado = "facturado"    # incluido en una factura mensual del proveedor
    rechazado = "rechazado"


class Albaran(Base):
    """Albarán de PROVEEDOR. No es un documento fiscal: no genera IVA ni asiento.
    Varios albaranes del mes se agrupan en la factura mensual del proveedor, que es la
    que se contabiliza; aquí solo se comprueba que la factura cuadra con sus albaranes."""
    __tablename__ = "albaranes"
    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"), index=True)
    proveedor_nif: Mapped[str | None] = mapped_column(String(20), index=True)
    proveedor_nombre: Mapped[str | None] = mapped_column(String(200))
    numero: Mapped[str | None] = mapped_column(String(40))
    fecha: Mapped[date | None] = mapped_column(Date, index=True)
    base_imponible: Mapped[Decimal] = mapped_column(Dinero, default=0)
    tipo_iva: Mapped[Decimal | None] = mapped_column(Porcentaje)      # muchos albaranes no lo desglosan
    total: Mapped[Decimal | None] = mapped_column(Dinero)
    estado: Mapped[EstadoAlbaran] = mapped_column(Enum(EstadoAlbaran, name="estado_albaran"),
                                                  default=EstadoAlbaran.pendiente, index=True)
    origen: Mapped[OrigenFactura] = mapped_column(Enum(OrigenFactura, name="origen_factura"),
                                                  default=OrigenFactura.movil)
    imagen_path: Mapped[str | None] = mapped_column(String(255))
    notas: Mapped[str | None] = mapped_column(Text)
    motivo_rechazo: Mapped[str | None] = mapped_column(String(255))
    factura_compra_id: Mapped[int | None] = mapped_column(ForeignKey("facturas_compra.id", ondelete="SET NULL"),
                                                          index=True)
    extraccion_confianza: Mapped[str | None] = mapped_column(String(10))
    extraccion_avisos: Mapped[str | None] = mapped_column(Text)
    subido_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    cliente: Mapped[Cliente] = relationship()

    @property
    def tiene_imagen(self) -> bool:
        return bool(self.imagen_path)


class VentaTPV(Base):
    """Cierre de caja diario (informe Z) del TPV: ventas con ticket (facturas simplificadas).
    Cuenta para el IVA repercutido y los ingresos, igual que una factura de venta."""
    __tablename__ = "ventas_tpv"
    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"), index=True)
    fecha: Mapped[date | None] = mapped_column(Date, index=True)
    numero_z: Mapped[str | None] = mapped_column(String(30))
    num_tickets: Mapped[int | None] = mapped_column(Integer)
    base_imponible: Mapped[Decimal] = mapped_column(Dinero, default=0)   # suma de bases
    cuota_iva: Mapped[Decimal] = mapped_column(Dinero, default=0)        # suma de cuotas
    total: Mapped[Decimal] = mapped_column(Dinero, default=0)
    cobro_efectivo: Mapped[Decimal] = mapped_column(Dinero, default=0)
    cobro_tarjeta: Mapped[Decimal] = mapped_column(Dinero, default=0)
    cuenta_ingreso: Mapped[str] = mapped_column(String(10), default="700")
    estado: Mapped[EstadoFactura] = mapped_column(Enum(EstadoFactura, name="estado_factura"),
                                                  default=EstadoFactura.pendiente, index=True)
    imagen_path: Mapped[str | None] = mapped_column(String(255))
    notas: Mapped[str | None] = mapped_column(Text)
    motivo_rechazo: Mapped[str | None] = mapped_column(String(255))
    asiento_id: Mapped[int | None] = mapped_column(ForeignKey("asientos.id", ondelete="SET NULL"))
    extraccion_confianza: Mapped[str | None] = mapped_column(String(10))
    extraccion_avisos: Mapped[str | None] = mapped_column(Text)
    subido_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    cliente: Mapped[Cliente] = relationship()
    desglose: Mapped[list["VentaTPVIva"]] = relationship(cascade="all, delete-orphan", order_by="VentaTPVIva.tipo_iva.desc()")

    @property
    def tiene_imagen(self) -> bool:
        return bool(self.imagen_path)


class VentaTPVIva(Base):
    """Desglose del cierre Z por tipo de IVA (en hostelería, 10 % comida y 21 % alcohol...)."""
    __tablename__ = "ventas_tpv_iva"
    id: Mapped[int] = mapped_column(primary_key=True)
    venta_id: Mapped[int] = mapped_column(ForeignKey("ventas_tpv.id", ondelete="CASCADE"), index=True)
    tipo_iva: Mapped[Decimal] = mapped_column(Porcentaje)
    base: Mapped[Decimal] = mapped_column(Dinero)
    cuota: Mapped[Decimal] = mapped_column(Dinero)


class EstadoCierre(str, enum.Enum):
    abierto = "abierto"
    cerrado = "cerrado"        # cerrado por el cliente: no admite más documentos de ese mes
    liquidado = "liquidado"    # la gestoría ha contabilizado y emitido el informe


class CierreMes(Base):
    __tablename__ = "cierres_mes"
    __table_args__ = (UniqueConstraint("cliente_id", "anio", "mes", name="uq_cierre_mes"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"), index=True)
    anio: Mapped[int] = mapped_column(Integer)
    mes: Mapped[int] = mapped_column(Integer)
    estado: Mapped[EstadoCierre] = mapped_column(Enum(EstadoCierre, name="estado_cierre"), default=EstadoCierre.abierto)
    cerrado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    cerrado_en: Mapped[datetime | None] = mapped_column(DateTime)
    liquidado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"))
    liquidado_en: Mapped[datetime | None] = mapped_column(DateTime)
    resumen: Mapped[str | None] = mapped_column(Text)   # JSON congelado al cerrar / liquidar
    notas: Mapped[str | None] = mapped_column(Text)


class MovimientoBanco(Base):
    __tablename__ = "movimientos_banco"
    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"), index=True)
    fecha: Mapped[date] = mapped_column(Date, index=True)
    concepto: Mapped[str] = mapped_column(String(255))
    importe: Mapped[Decimal] = mapped_column(Dinero)  # >0 cobro, <0 pago
    conciliado: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    factura_compra_id: Mapped[int | None] = mapped_column(ForeignKey("facturas_compra.id", ondelete="SET NULL"))
    factura_venta_id: Mapped[int | None] = mapped_column(ForeignKey("facturas_venta.id", ondelete="SET NULL"))
    asiento_id: Mapped[int | None] = mapped_column(ForeignKey("asientos.id", ondelete="SET NULL"))
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Asiento(Base):
    __tablename__ = "asientos"
    __table_args__ = (UniqueConstraint("cliente_id", "ejercicio", "numero", name="uq_asiento_numero"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"), index=True)
    ejercicio: Mapped[int] = mapped_column(Integer)
    numero: Mapped[int] = mapped_column(Integer)
    fecha: Mapped[date] = mapped_column(Date, index=True)
    concepto: Mapped[str] = mapped_column(String(255))
    origen: Mapped[str] = mapped_column(String(20))  # compra | venta | pago | cobro | manual
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    apuntes: Mapped[list["Apunte"]] = relationship(back_populates="asiento", cascade="all, delete-orphan",
                                                   order_by="Apunte.id")


class Auditoria(Base):
    """Registro de acciones sensibles (quién, qué, cuándo, desde dónde)."""
    __tablename__ = "auditoria"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", ondelete="SET NULL"), index=True)
    accion: Mapped[str] = mapped_column(String(60))
    entidad: Mapped[str | None] = mapped_column(String(40))
    entidad_id: Mapped[int | None] = mapped_column(Integer)
    detalle: Mapped[str | None] = mapped_column(String(255))
    ip: Mapped[str | None] = mapped_column(String(64))
    fecha: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class Apunte(Base):
    __tablename__ = "apuntes"
    id: Mapped[int] = mapped_column(primary_key=True)
    asiento_id: Mapped[int] = mapped_column(ForeignKey("asientos.id", ondelete="CASCADE"), index=True)
    cuenta: Mapped[str] = mapped_column(String(12), index=True)
    descripcion: Mapped[str] = mapped_column(String(255))
    debe: Mapped[Decimal] = mapped_column(Dinero, default=0)
    haber: Mapped[Decimal] = mapped_column(Dinero, default=0)

    asiento: Mapped[Asiento] = relationship(back_populates="apuntes")
