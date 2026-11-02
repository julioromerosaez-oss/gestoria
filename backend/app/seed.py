"""Datos de demostración (solo SQLite de desarrollo).  python -m app.seed

Crea una gestoría con tres clientes. El principal es un restaurante con los cuatro roles:
  - cierres Z diarios (cerrado los lunes),
  - proveedores con albaranes semanales y factura mensual (uno con descuadre, otro sin facturar),
  - suministros y alquiler (con retención) sin albaranes,
  - meses ya liquidados, septiembre cerrado por el cliente y octubre abierto con cosas pendientes.
"""
import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from . import config
from .auth import hash_password
from .db import Base, SessionLocal, engine
from .models import (Albaran, Cliente, EstadoAlbaran, EstadoFactura, FacturaCompra, FacturaVenta,
                     MovimientoBanco, OrigenFactura, Rol, TipoCliente, Usuario, VentaTPV)
from .services import cierres, documentos, tpv
from .services.contabilidad import calcular_importes, contabilizar_compra, contabilizar_venta
from .services.conciliacion import conciliar

D = Decimal
DOCS = Path(__file__).resolve().parent.parent / "tests" / "docs"

# proveedor: (nif, nombre, cuenta, iva, irpf, modo)  modo: albaranes semanales | factura mensual fija
PROVEEDORES_REST = [
    ("A08017006", "Makro Autoservicio Mayorista SA", "600", 10, 0, "albaranes"),
    ("B24680134", "Distribuciones Bebidas Turia SL", "600", 21, 0, "albaranes"),
    ("B33557794", "Pescados y Mariscos La Lonja SL", "600", 10, 0, "albaranes"),
    ("A28007656", "Iberdrola Clientes SAU", "628", 21, 0, "fija"),
    ("B46123451", "Inmuebles Centro Valencia SL", "621", 21, 19, "fija"),
    ("B11122231", "Asesoría y Gestoría Levante SL", "623", 21, 0, "fija"),
]


def _mes_siguiente(d: date) -> date:
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def main():
    if config.AUTH_MODO != "local" or not config.DATABASE_URL.startswith("sqlite") or config.PRODUCCION:
        raise SystemExit("El seed solo se ejecuta contra la base SQLite de desarrollo")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    random.seed(11)
    db = SessionLocal()
    hoy = date.today()

    gestor = Usuario(email="roberto@complutumasesores.com", nombre="Roberto", rol=Rol.gestor,
                     password_hash=hash_password("Rober2026"))
    db.add(gestor)
    rest = Cliente(nif="B65432106", razon_social="Bar Restaurante La Plaza SL", tipo=TipoCliente.sociedad,
                   email="admin@laplaza.es", telefono="963000111", serie_venta="R")
    fonta = Cliente(nif="44556677L", razon_social="Carlos Martín Ruiz (Fontanería)", tipo=TipoCliente.autonomo,
                    email="carlos@ejemplo.es", telefono="600111222", serie_venta="F")
    fisio = Cliente(nif="53421987W", razon_social="Laura Sánchez Pérez (Fisioterapia)", tipo=TipoCliente.autonomo,
                    email="laura@fisio.es", serie_venta="L")
    db.add_all([rest, fonta, fisio])
    db.flush()
    usuarios = {}
    for email, nombre, rol, cli, clave in (
            ("patrilucre1953@gmail.com", "Patri", Rol.cliente_admin, rest, "Patri2026"),
            ("joselucre1953@gmail.com", "José", Rol.cliente_compras_ventas, rest, "Javi2026"),
            ("carlos@cliente.local", "Carlos Martín", Rol.cliente_admin, fonta, "Cliente.2026")):
        usuarios[email] = Usuario(email=email, nombre=nombre, rol=rol, cliente_id=cli.id,
                                  password_hash=hash_password(clave))
        db.add(usuarios[email])
    db.flush()
    # Compras y ventas las sube la misma persona
    admin_u = usuarios["patrilucre1953@gmail.com"]
    compras_u = ventas_u = usuarios["joselucre1953@gmail.com"]

    # ---------------- restaurante: enero .. octubre ----------------
    ultimo_mes = date(hoy.year, hoy.month, 1) - timedelta(days=1)       # mes anterior completo
    mes = date(hoy.year, 1, 1)
    while mes <= ultimo_mes:
        fin = _mes_siguiente(mes)
        es_ultimo = fin > ultimo_mes
        # cierres Z diarios (lunes cerrado)
        d, nz = mes, 0
        while d < fin:
            if d.weekday() != 0 and not (es_ultimo and d.day in (12, 13)):   # faltan 2 Z en el último mes
                nz += 1
                comida = D(random.randint(700, 1900)) + D(random.randint(0, 99)) / 100
                bebida = D(random.randint(150, 600)) + D(random.randint(0, 99)) / 100
                v = VentaTPV(cliente_id=rest.id, fecha=d, numero_z=f"{d.month:02d}{nz:02d}", num_tickets=random.randint(40, 140),
                             estado=EstadoFactura.validada, subido_por_id=ventas_u.id, cuenta_ingreso="700",
                             base_imponible=0, cuota_iva=0, total=0, cobro_efectivo=0, cobro_tarjeta=0)
                tpv.poner_desglose(v, [{"tipo_iva": 10, "base": comida}, {"tipo_iva": 21, "base": bebida}])
                v.cobro_tarjeta = (v.total * D("0.68")).quantize(D("0.01"))
                v.cobro_efectivo = v.total - v.cobro_tarjeta
                if es_ultimo and d.day > 26:
                    v.estado = EstadoFactura.pendiente
                    v.extraccion_confianza = "alta"
                db.add(v)
            d += timedelta(days=1)
        # proveedores
        for nif, nombre, cuenta, iva, irpf, modo in PROVEEDORES_REST:
            if modo == "albaranes":
                albs = []
                for semana in range(4):
                    fa = mes + timedelta(days=2 + semana * 7)
                    base = D(random.randint(180, 900)) + D(random.randint(0, 99)) / 100
                    a = Albaran(cliente_id=rest.id, proveedor_nif=nif, proveedor_nombre=nombre, numero=f"AL-{fa:%m%d}-{random.randint(10, 99)}",
                                fecha=fa, base_imponible=base, estado=EstadoAlbaran.revisado, subido_por_id=compras_u.id,
                                origen=OrigenFactura.movil, extraccion_confianza="alta")
                    db.add(a)
                    albs.append(a)
                db.flush()
                if es_ultimo and "Lonja" in nombre:
                    continue                                  # la Lonja aún no ha mandado la factura de octubre
                if es_ultimo and semana == 3 and "Makro" in nombre:
                    albs[-1].estado = EstadoAlbaran.pendiente  # uno sin revisar
                suma = sum(a.base_imponible for a in albs)
                if es_ultimo and "Bebidas" in nombre:
                    suma += D("24.60")                        # factura que no cuadra con sus albaranes
                f = FacturaCompra(cliente_id=rest.id, numero=f"F{mes:%y%m}-{random.randint(100, 999)}", fecha=fin - timedelta(days=1),
                                  proveedor_nif=nif, proveedor_nombre=nombre, cuenta_gasto=cuenta, tipo_iva=D(iva), tipo_irpf=D(irpf),
                                  base_imponible=suma, estado=EstadoFactura.validada, subido_por_id=compras_u.id,
                                  origen=OrigenFactura.movil, concepto=f"Suministros {mes:%m/%Y}")
                calcular_importes(f)
                db.add(f)
                db.flush()
                if es_ultimo:
                    continue                                  # octubre: las facturas han llegado, falta cuadrarlas
                for a in albs:
                    if a.estado == EstadoAlbaran.revisado:
                        a.factura_compra_id, a.estado = f.id, EstadoAlbaran.facturado
            else:
                base = {"628": D(random.randint(480, 760)), "621": D("1800.00"), "623": D("150.00")}[cuenta]
                f = FacturaCompra(cliente_id=rest.id, numero=f"{nif[-4:]}/{mes:%y%m}", fecha=mes + timedelta(days=4),
                                  proveedor_nif=nif, proveedor_nombre=nombre, cuenta_gasto=cuenta, tipo_iva=D(iva), tipo_irpf=D(irpf),
                                  base_imponible=base, estado=EstadoFactura.validada, origen=OrigenFactura.gestoria,
                                  concepto={"628": "Electricidad", "621": "Alquiler local", "623": "Asesoría"}[cuenta])
                calcular_importes(f)
                db.add(f)
                # pago por banco
                db.add(MovimientoBanco(cliente_id=rest.id, fecha=mes + timedelta(days=6),
                                       concepto=f"RECIBO {nombre.upper()[:30]}", importe=-f.total))
        db.flush()
        # meses anteriores: liquidados; penúltimo: cerrado por el cliente; último: abierto
        if mes < date(ultimo_mes.year, ultimo_mes.month, 1) - timedelta(days=31):
            cierres.cerrar(db, rest.id, mes.year, mes.month, admin_u)
            cierres.liquidar(db, rest.id, mes.year, mes.month, gestor, forzar=True)
            from .services.conciliacion import sugerencias
            for mov in db.query(MovimientoBanco).filter(MovimientoBanco.cliente_id == rest.id, MovimientoBanco.conciliado.is_(False),
                                                       MovimientoBanco.fecha >= mes, MovimientoBanco.fecha < fin):
                if s := sugerencias(db, mov, limite=1):
                    conciliar(db, mov, s[0]["tipo"], s[0]["factura_id"])
        elif not es_ultimo:
            cierres.cerrar(db, rest.id, mes.year, mes.month, admin_u)
        mes = fin

    # octubre: un pago sin factura y documentos recién subidos desde el móvil (con lectura real)
    db.add(MovimientoBanco(cliente_id=rest.id, fecha=ultimo_mes - timedelta(days=3), concepto="TPV AMAZON EU SARL",
                           importe=D("-86.90")))
    if DOCS.joinpath("albaran_foto.jpg").exists():
        for fichero in ("albaran_foto.jpg", "factura_foto.jpg"):
            obj, _, _ = documentos.subir(db, rest, DOCS.joinpath(fichero).read_bytes(), "auto",
                                         "Subido desde el almacén", usuario=None)
            obj.subido_por_id = compras_u.id
            obj.fecha = obj.fecha and ultimo_mes.replace(day=min(obj.fecha.day, 28))

    # ---------------- fontanero y fisio: facturación sencilla ----------------
    for c in (fonta, fisio):
        mes = date(hoy.year, 1, 1)
        n = 0
        while mes <= ultimo_mes:
            for _ in range(random.randint(2, 4)):
                n += 1
                f = FacturaVenta(cliente_id=c.id, numero=f"{c.serie_venta}{mes.year}-{n:04d}", fecha=mes + timedelta(days=random.randint(0, 25)),
                                 destinatario_nif="B24680134", destinatario_nombre="Comunidad de Propietarios Turia",
                                 tipo_iva=D(21), tipo_irpf=D(15) if c.tipo == TipoCliente.autonomo else D(0),
                                 base_imponible=D(random.randint(300, 1800)), estado=EstadoFactura.validada, concepto="Servicios")
                calcular_importes(f)
                db.add(f)
            g = FacturaCompra(cliente_id=c.id, numero=f"G{mes:%m}-{random.randint(1, 99)}", fecha=mes + timedelta(days=10),
                              proveedor_nif="A28007656", proveedor_nombre="Iberdrola Clientes SAU", cuenta_gasto="628",
                              tipo_iva=D(21), base_imponible=D(random.randint(40, 120)), estado=EstadoFactura.validada)
            calcular_importes(g)
            db.add(g)
            mes = _mes_siguiente(mes)
        db.flush()
        for Modelo, fn in ((FacturaVenta, contabilizar_venta), (FacturaCompra, contabilizar_compra)):
            for f in db.query(Modelo).filter(Modelo.cliente_id == c.id, Modelo.fecha < ultimo_mes.replace(day=1)):
                fn(db, f)
    db.commit()
    print("Datos de demo creados.\n"
          "  Gestoría:                 roberto@complutumasesores.com / Rober2026   (http://localhost:8000)\n"
          "  Administración (web):     patrilucre1953@gmail.com / Patri2026         (http://localhost:8000)\n"
          "  Compras y ventas (móvil): joselucre1953@gmail.com / Javi2026          (http://localhost:8000/movil)\n"
          "  Fontanero (app):     carlos@cliente.local / Cliente.2026")


if __name__ == "__main__":
    main()
