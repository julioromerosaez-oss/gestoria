"""Cierre mensual, resumen del mes, "qué falta", vista por proveedor y liquidación mensual.

Ciclo de un mes:  abierto  --(cliente-administración cierra)-->  cerrado
                  cerrado  --(gestoría liquida: contabiliza + informe)-->  liquidado
                  cerrado/liquidado --(gestoría reabre)--> abierto
- cerrado:   el cliente ya no puede subir documentos con fecha de ese mes; la gestoría sí puede revisar.
- liquidado: nadie modifica documentos de ese mes hasta que la gestoría lo reabra.
"""
import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (Albaran, CierreMes, Cliente, EstadoAlbaran, EstadoCierre, EstadoFactura,
                      FacturaCompra, FacturaVenta, MovimientoBanco, Rol, Usuario, VentaTPV)
from . import albaranes as srv_alb
from . import contabilidad, iva, tpv
from .contabilidad import redondear

REVISADAS = (EstadoFactura.validada, EstadoFactura.contabilizada)
NOMBRES_MES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
               "octubre", "noviembre", "diciembre"]


def _ahora():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def rango(anio: int, mes: int) -> tuple[date, date]:
    return srv_alb.rango_mes(anio, mes)


def cierre(db: Session, cliente_id: int, anio: int, mes: int, crear: bool = False) -> CierreMes | None:
    c = db.scalar(select(CierreMes).where(CierreMes.cliente_id == cliente_id, CierreMes.anio == anio,
                                          CierreMes.mes == mes))
    if not c and crear:
        c = CierreMes(cliente_id=cliente_id, anio=anio, mes=mes, estado=EstadoCierre.abierto)
        db.add(c)
        db.flush()
    return c


def estado_mes(db: Session, cliente_id: int, anio: int, mes: int) -> EstadoCierre:
    c = cierre(db, cliente_id, anio, mes)
    return c.estado if c else EstadoCierre.abierto


def comprobar_editable(db: Session, cliente_id: int, fecha: date | None, usuario: Usuario) -> None:
    """Lanza 409 si el documento cae en un mes que este usuario ya no puede tocar."""
    if not fecha:
        return
    est = estado_mes(db, cliente_id, fecha.year, fecha.month)
    nombre = f"{NOMBRES_MES[fecha.month - 1]} de {fecha.year}"
    if est == EstadoCierre.liquidado:
        raise HTTPException(409, f"El mes de {nombre} está liquidado. La gestoría tiene que reabrirlo.")
    if est == EstadoCierre.cerrado and usuario.rol != Rol.gestor:
        raise HTTPException(409, f"El mes de {nombre} ya está cerrado: habla con tu gestoría para incluir "
                                 f"este documento.")


# ---------------------------------------------------------------- resumen del mes
def _sumar(filas, campos=("base_imponible", "cuota_iva", "total")) -> dict:
    out = {"n": 0, "base": Decimal(0), "iva": Decimal(0), "total": Decimal(0), "irpf": Decimal(0)}
    for f in filas:
        out["n"] += 1
        out["base"] += f.base_imponible or 0
        out["iva"] += f.cuota_iva or 0
        out["total"] += f.total or 0
        out["irpf"] += getattr(f, "cuota_irpf", 0) or 0
    return out


def _f(d: dict) -> dict:
    return {k: (float(redondear(v)) if isinstance(v, Decimal) else v) for k, v in d.items()}


def resumen(db: Session, cliente_id: int, anio: int, mes: int) -> dict:
    ini, fin = rango(anio, mes)

    def del_mes(Modelo, estados):
        return db.scalars(select(Modelo).where(Modelo.cliente_id == cliente_id, Modelo.estado.in_(estados),
                                               Modelo.fecha >= ini, Modelo.fecha < fin)).all()

    compras = _sumar(del_mes(FacturaCompra, REVISADAS))
    ventas = _sumar(del_mes(FacturaVenta, REVISADAS))
    caja = _sumar(del_mes(VentaTPV, REVISADAS))
    ingresos = {k: ventas[k] + caja[k] for k in ("base", "iva", "total")}
    albs = db.scalars(select(Albaran).where(Albaran.cliente_id == cliente_id, Albaran.fecha >= ini,
                                            Albaran.fecha < fin, Albaran.estado != EstadoAlbaran.rechazado)).all()
    pendientes = 0
    for Modelo, est in ((FacturaCompra, EstadoFactura.pendiente), (FacturaVenta, EstadoFactura.pendiente),
                        (VentaTPV, EstadoFactura.pendiente), (Albaran, EstadoAlbaran.pendiente)):
        pendientes += len(db.scalars(select(Modelo.id).where(
            Modelo.cliente_id == cliente_id, Modelo.estado == est,
            (Modelo.fecha.is_(None)) | ((Modelo.fecha >= ini) & (Modelo.fecha < fin)))).all())
    cliente = db.get(Cliente, cliente_id)
    trimestre = (mes - 1) // 3 + 1
    iva_mes = iva.liquidacion_iva_rango(db, cliente_id, ini, fin)
    iva_trim = iva.liquidacion_iva_rango(db, cliente_id, date(anio, 3 * trimestre - 2, 1), fin)
    c = cierre(db, cliente_id, anio, mes)
    return {
        "cliente_id": cliente_id, "anio": anio, "mes": mes, "nombre_mes": f"{NOMBRES_MES[mes - 1]} {anio}",
        "estado": (c.estado if c else EstadoCierre.abierto).value,
        "cerrado_en": c.cerrado_en if c else None, "liquidado_en": c.liquidado_en if c else None,
        "gastos": _f(compras),
        "ingresos": {"facturas": _f(ventas), "tpv": _f(caja), **_f(ingresos)},
        "resultado_sin_iva": float(redondear(ingresos["base"] - compras["base"])),
        "resultado_con_iva": float(redondear(ingresos["total"] - compras["total"])),
        "iva_mes": iva_mes,
        "iva_trimestre": {**iva_trim, "trimestre": trimestre, "hasta_mes": mes,
                          "plazo_presentacion": iva.PLAZOS_303[trimestre]},
        "periodo_iva": cliente.periodo_iva,
        "albaranes": {"n": len(albs), "base": float(redondear(sum((a.base_imponible or 0 for a in albs), Decimal(0)))),
                      "sin_factura": sum(1 for a in albs if not a.factura_compra_id)},
        "pendientes_revision": pendientes,
    }


# ---------------------------------------------------------------- qué falta
def pendientes(db: Session, cliente_id: int, anio: int, mes: int, para_cliente: bool = False) -> list[dict]:
    """Lista accionable de lo que falta para cerrar el mes. quien = gestoria | cliente | proveedor."""
    ini, fin = rango(anio, mes)
    hoy = date.today()
    out: list[dict] = []

    def item(quien, gravedad, titulo, detalle="", importe=None, ref=None):
        out.append({"quien": quien, "gravedad": gravedad, "titulo": titulo, "detalle": detalle,
                    "importe": float(importe) if importe is not None else None, "ref": ref})

    # 1) documentos sin revisar
    for Modelo, nombre, ruta, est in ((FacturaCompra, "facturas de compra", "compras", EstadoFactura.pendiente),
                                      (FacturaVenta, "facturas de venta", "ventas", EstadoFactura.pendiente),
                                      (VentaTPV, "cierres de caja", "ventas-tpv", EstadoFactura.pendiente),
                                      (Albaran, "albaranes", "albaranes", EstadoAlbaran.pendiente)):
        ids = db.scalars(select(Modelo.id).where(
            Modelo.cliente_id == cliente_id, Modelo.estado == est,
            (Modelo.fecha.is_(None)) | ((Modelo.fecha >= ini) & (Modelo.fecha < fin)))).all()
        if ids:
            item("gestoria", "bloquea", f"{len(ids)} {nombre} " + ("en revisión por la gestoría" if para_cliente
                                                                     else "pendientes de revisar"),
                 ref={"tipo": ruta, "ids": list(ids)})
    # 2) documentos rechazados: hay que volver a subirlos
    for Modelo, nombre, est in ((FacturaCompra, "Factura", EstadoFactura.rechazada),
                                (FacturaVenta, "Factura de venta", EstadoFactura.rechazada),
                                (VentaTPV, "Cierre de caja", EstadoFactura.rechazada),
                                (Albaran, "Albarán", EstadoAlbaran.rechazado)):
        for d in db.scalars(select(Modelo).where(
                Modelo.cliente_id == cliente_id, Modelo.estado == est,
                (Modelo.fecha.is_(None)) | ((Modelo.fecha >= ini) & (Modelo.fecha < fin)))):
            tercero = getattr(d, "proveedor_nombre", None) or getattr(d, "destinatario_nombre", None) or ""
            item("cliente", "reclamar", f"{nombre} rechazado: volver a subir",
                 f"{tercero} {getattr(d, 'numero', '') or getattr(d, 'numero_z', '') or ''} · {d.motivo_rechazo or ''}".strip(" ·"))
    # 3) albaranes sin factura del proveedor y descuadres
    for g in srv_alb.resumen_mes(db, cliente_id, anio, mes):
        prov = g["proveedor_nombre"] or g["proveedor_nif"] or "proveedor sin identificar"
        if g["situacion"] == "por_cuadrar":
            fr = g["factura_recibida"]
            if abs(fr["diferencia"]) <= 0.05:
                item("gestoria", "bloquea", f"Cuadrar la factura de {prov} con sus albaranes",
                     f"Factura {fr['numero'] or ''} recibida: coincide con la suma de albaranes", g["suma_base"],
                     ref={"tipo": "proveedor", "clave": g["clave"]})
            else:
                item("proveedor", "reclamar", f"La factura de {prov} no cuadra con sus albaranes",
                     f"Factura {fr['numero'] or ''}: diferencia de {fr['diferencia']:+.2f} € en base. "
                     "Pedir rectificativa o el albarán que falta", fr["diferencia"],
                     ref={"tipo": "proveedor", "clave": g["clave"]})
        elif g["situacion"] in ("sin_factura", "parcial"):
            item("proveedor", "reclamar", f"Reclamar la factura de {prov}",
                 f"{g['sin_factura']} albarán(es) de {NOMBRES_MES[mes - 1]} sin factura", g["suma_base"],
                 ref={"tipo": "proveedor", "clave": g["clave"]})
        elif g["situacion"] == "descuadre":
            item("proveedor", "reclamar", f"La factura de {prov} no cuadra con sus albaranes",
                 f"Diferencia de {g['diferencia']:+.2f} € en base: pedir factura rectificativa o el albarán que falta",
                 g["diferencia"], ref={"tipo": "proveedor", "clave": g["clave"]})
    # 4) proveedores habituales que este mes no han enviado nada
    prev_ini = date(anio - (mes <= 3), (mes - 4) % 12 + 1, 1)
    meses_prov: dict[str, set] = defaultdict(set)
    nombres: dict[str, str] = {}
    for f in db.scalars(select(FacturaCompra).where(FacturaCompra.cliente_id == cliente_id,
                                                    FacturaCompra.estado != EstadoFactura.rechazada,
                                                    FacturaCompra.fecha >= prev_ini, FacturaCompra.fecha < ini)):
        k = srv_alb.clave_proveedor(f.proveedor_nif, f.proveedor_nombre)
        meses_prov[k].add((f.fecha.year, f.fecha.month))
        nombres[k] = f.proveedor_nombre or f.proveedor_nif
    este_mes = {srv_alb.clave_proveedor(x.proveedor_nif, x.proveedor_nombre)
                for M in (FacturaCompra, Albaran)
                for x in db.scalars(select(M).where(M.cliente_id == cliente_id, M.fecha >= ini, M.fecha < fin))}
    if fin <= hoy + timedelta(days=31):  # no avisar de meses futuros
        for k, ms in meses_prov.items():
            if len(ms) >= 2 and k not in este_mes:
                item("proveedor", "aviso", f"¿Falta la factura de {nombres[k]}?",
                     f"Ha facturado {len(ms)} de los 3 meses anteriores y en {NOMBRES_MES[mes - 1]} no hay nada",
                     ref={"tipo": "proveedor", "clave": k})
    # 5) movimientos de banco sin justificar
    from .conciliacion import sugerencias
    por_conciliar = 0
    for m in db.scalars(select(MovimientoBanco).where(MovimientoBanco.cliente_id == cliente_id,
                                                      MovimientoBanco.conciliado.is_(False),
                                                      MovimientoBanco.fecha >= ini, MovimientoBanco.fecha < fin)):
        if sugerencias(db, m, limite=1):   # la factura existe: solo falta conciliarlo
            por_conciliar += 1
        elif m.importe < 0:
            item("cliente", "reclamar", "Pago sin factura", f"{m.fecha:%d/%m} · {m.concepto}", m.importe)
        else:
            item("cliente", "aviso", "Cobro sin factura", f"{m.fecha:%d/%m} · {m.concepto}", m.importe)
    if por_conciliar and not para_cliente:
        item("gestoria", "aviso", f"{por_conciliar} movimiento(s) de banco por conciliar",
             "Tienen factura con el mismo importe: concilia en Conciliación bancaria")
    # 6) días sin cierre de caja (solo si el cliente usa TPV)
    usa_tpv = db.scalar(select(VentaTPV.id).where(VentaTPV.cliente_id == cliente_id,
                                                  VentaTPV.fecha >= ini - timedelta(days=90)).limit(1))
    if usa_tpv:
        con_z = {v for v in db.scalars(select(VentaTPV.fecha).where(
            VentaTPV.cliente_id == cliente_id, VentaTPV.fecha >= ini, VentaTPV.fecha < fin,
            VentaTPV.estado != EstadoFactura.rechazada))}
        # días de la semana que el negocio no abre (sin ningún Z en las 8 semanas anteriores): no se reclaman
        historico = db.scalars(select(VentaTPV.fecha).where(
            VentaTPV.cliente_id == cliente_id, VentaTPV.fecha >= ini - timedelta(days=56), VentaTPV.fecha < ini)).all()
        abre = {f.weekday() for f in historico} or set(range(7))
        dias = [ini + timedelta(days=i) for i in range((min(fin, hoy) - ini).days)]
        faltan = [d for d in dias if d not in con_z and d.weekday() in abre]
        if faltan:
            item("cliente", "aviso", f"{len(faltan)} día(s) sin cierre de caja",
                 "Días: " + ", ".join(str(d.day) for d in faltan[:31]) + ". Si el local cerró esos días, ignóralo.")
    orden = {"bloquea": 0, "reclamar": 1, "aviso": 2}
    return sorted(out, key=lambda x: orden[x["gravedad"]])


# ---------------------------------------------------------------- por proveedor
def proveedores(db: Session, cliente_id: int, anio: int) -> list[dict]:
    ini, fin = date(anio, 1, 1), date(anio + 1, 1, 1)
    g: dict[str, dict] = {}

    def fila(k, nif, nombre):
        return g.setdefault(k, {"clave": k, "proveedor_nif": nif, "proveedor_nombre": nombre,
                                "facturas": 0, "base": Decimal(0), "iva": Decimal(0), "total": Decimal(0),
                                "albaranes": 0, "albaranes_base": Decimal(0), "albaranes_sin_factura": 0,
                                "pendientes": 0, "ultima_factura": None, "meses": set()})
    for f in db.scalars(select(FacturaCompra).where(FacturaCompra.cliente_id == cliente_id,
                                                    FacturaCompra.fecha >= ini, FacturaCompra.fecha < fin)):
        r = fila(srv_alb.clave_proveedor(f.proveedor_nif, f.proveedor_nombre), f.proveedor_nif, f.proveedor_nombre)
        r["proveedor_nombre"] = r["proveedor_nombre"] or f.proveedor_nombre
        if f.estado == EstadoFactura.pendiente:
            r["pendientes"] += 1
        if f.estado in REVISADAS:
            r["facturas"] += 1
            r["base"] += f.base_imponible
            r["iva"] += f.cuota_iva
            r["total"] += f.total
            r["meses"].add(f.fecha.month)
            r["ultima_factura"] = max(filter(None, [r["ultima_factura"], f.fecha]))
    for a in db.scalars(select(Albaran).where(Albaran.cliente_id == cliente_id, Albaran.fecha >= ini,
                                              Albaran.fecha < fin, Albaran.estado != EstadoAlbaran.rechazado)):
        r = fila(srv_alb.clave_proveedor(a.proveedor_nif, a.proveedor_nombre), a.proveedor_nif, a.proveedor_nombre)
        r["proveedor_nombre"] = r["proveedor_nombre"] or a.proveedor_nombre
        r["albaranes"] += 1
        r["albaranes_base"] += a.base_imponible or 0
        r["albaranes_sin_factura"] += 0 if a.factura_compra_id else 1
        if a.estado == EstadoAlbaran.pendiente:
            r["pendientes"] += 1
    out = []
    for r in g.values():
        out.append({**_f(r), "meses": sorted(r["meses"])})
    return sorted(out, key=lambda x: -x["total"])


def documentos_proveedor(db: Session, cliente_id: int, clave: str, anio: int) -> dict:
    ini, fin = date(anio, 1, 1), date(anio + 1, 1, 1)
    facturas = [f for f in db.scalars(select(FacturaCompra).where(
        FacturaCompra.cliente_id == cliente_id, FacturaCompra.fecha >= ini, FacturaCompra.fecha < fin)
        .order_by(FacturaCompra.fecha)) if srv_alb.clave_proveedor(f.proveedor_nif, f.proveedor_nombre) == clave]
    albs = [a for a in db.scalars(select(Albaran).where(
        Albaran.cliente_id == cliente_id, Albaran.fecha >= ini, Albaran.fecha < fin).order_by(Albaran.fecha))
        if srv_alb.clave_proveedor(a.proveedor_nif, a.proveedor_nombre) == clave]
    return {"facturas": facturas, "albaranes": albs}


# ---------------------------------------------------------------- cierre y liquidación
def cerrar(db: Session, cliente_id: int, anio: int, mes: int, usuario: Usuario) -> CierreMes:
    if date(anio, mes, 1) > date.today():
        raise HTTPException(422, "No se puede cerrar un mes que aún no ha empezado")
    c = cierre(db, cliente_id, anio, mes, crear=True)
    if c.estado != EstadoCierre.abierto:
        raise HTTPException(409, f"El mes ya está {c.estado.value}")
    c.estado, c.cerrado_por_id, c.cerrado_en = EstadoCierre.cerrado, usuario.id, _ahora()
    c.resumen = json.dumps(resumen(db, cliente_id, anio, mes), default=str, ensure_ascii=False)
    return c


def reabrir(db: Session, cliente_id: int, anio: int, mes: int) -> CierreMes:
    c = cierre(db, cliente_id, anio, mes, crear=True)
    c.estado = EstadoCierre.abierto
    c.liquidado_en = c.liquidado_por_id = None
    return c


def liquidar(db: Session, cliente_id: int, anio: int, mes: int, gestor: Usuario, forzar: bool = False) -> dict:
    """Cierre contable del mes: contabiliza todo lo revisado y congela el informe."""
    c = cierre(db, cliente_id, anio, mes, crear=True)
    if c.estado == EstadoCierre.liquidado:
        raise HTTPException(409, "El mes ya está liquidado")
    falta = pendientes(db, cliente_id, anio, mes)
    bloqueantes = [p for p in falta if p["gravedad"] == "bloquea"]
    if bloqueantes and not forzar:
        raise HTTPException(409, "Antes de liquidar: " + "; ".join(p["titulo"] for p in bloqueantes))
    ini, fin = rango(anio, mes)
    asientos = 0
    for Modelo, fn in ((FacturaCompra, contabilidad.contabilizar_compra),
                       (FacturaVenta, contabilidad.contabilizar_venta), (VentaTPV, tpv.contabilizar)):
        for d in db.scalars(select(Modelo).where(Modelo.cliente_id == cliente_id,
                                                 Modelo.estado == EstadoFactura.validada,
                                                 Modelo.fecha >= ini, Modelo.fecha < fin)):
            fn(db, d)
            asientos += 1
    db.flush()
    informe = resumen(db, cliente_id, anio, mes)
    informe.update(asientos_generados=asientos, pendientes_al_liquidar=falta, liquidado_por=gestor.nombre)
    c.estado, c.liquidado_por_id, c.liquidado_en = EstadoCierre.liquidado, gestor.id, _ahora()
    if not c.cerrado_en:
        c.cerrado_en = c.liquidado_en
    informe["estado"], informe["liquidado_en"] = "liquidado", c.liquidado_en
    c.resumen = json.dumps(informe, default=str, ensure_ascii=False)
    return informe


def meses_del_anio(db: Session, cliente_id: int, anio: int) -> list[dict]:
    est = {c.mes: c.estado.value for c in db.scalars(select(CierreMes).where(
        CierreMes.cliente_id == cliente_id, CierreMes.anio == anio))}
    hoy = date.today()
    return [{"mes": m, "nombre": NOMBRES_MES[m - 1], "estado": est.get(m, "abierto"),
             "futuro": date(anio, m, 1) > hoy} for m in range(1, 13)]


def contadores(db: Session, cliente_id: int, anio: int, mes: int) -> dict:
    ini, fin = rango(anio, mes)

    def n(Modelo, *cond):
        return len(db.scalars(select(Modelo.id).where(Modelo.cliente_id == cliente_id, *cond)).all())

    del_mes = lambda M: (M.fecha.is_(None)) | ((M.fecha >= ini) & (M.fecha < fin))  # noqa: E731
    falta = pendientes(db, cliente_id, anio, mes)
    return {
        "compras": n(FacturaCompra, FacturaCompra.estado == EstadoFactura.pendiente, del_mes(FacturaCompra)),
        "ventas": n(FacturaVenta, FacturaVenta.estado == EstadoFactura.pendiente, del_mes(FacturaVenta)),
        "albaranes": n(Albaran, Albaran.estado == EstadoAlbaran.pendiente, del_mes(Albaran))
        + sum(1 for g in srv_alb.resumen_mes(db, cliente_id, anio, mes) if g["situacion"] != "cuadra"),
        "tpv": n(VentaTPV, VentaTPV.estado == EstadoFactura.pendiente, del_mes(VentaTPV)),
        "banco": n(MovimientoBanco, MovimientoBanco.conciliado.is_(False)),
        "falta": len(falta),
        "bloquean": sum(1 for p in falta if p["gravedad"] == "bloquea"),
    }
