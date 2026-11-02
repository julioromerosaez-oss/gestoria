"""Roles del cliente, cierres Z del TPV, qué falta, cierre mensual y liquidación de la gestoría."""
import shutil
from pathlib import Path

import pytest

from conftest import tok

DOCS = Path(__file__).parent / "docs"
pytestmark = pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract no instalado")


def subir(c, h, fichero, ruta="/api/movil/facturas", tipo=None, mime="image/jpeg"):
    data = {"tipo": tipo} if tipo else {}
    return c.post(ruta, headers=h, data=data, files={"foto": (fichero, (DOCS / fichero).read_bytes(), mime)})


def test_permisos_por_rol(c):
    compras, ventas, admin = (tok(c, e, "cli123") for e in ("compras@x.es", "ventas@x.es", "u1@x.es"))
    # compras sube albaranes y facturas de proveedor, pero no ve IVA, margen ni el mes
    assert subir(c, compras, "albaran_foto.jpg").json()["tipo"] == "albaran"
    for ruta in ("/api/movil/iva", "/api/movil/margen", "/api/movil/meses/2026/10", "/api/movil/proveedores?anio=2026"):
        assert c.get(ruta, headers=compras).status_code == 403
    assert subir(c, compras, "cierre_z_foto.jpg", ruta="/api/movil/cierres-z").status_code == 403
    # ventas sube cierres Z, no facturas de proveedor
    assert subir(c, ventas, "factura_foto.jpg", tipo="compra").status_code == 403
    r = subir(c, ventas, "cierre_z_foto.jpg", ruta="/api/movil/cierres-z")
    assert r.status_code == 201, r.text
    z = r.json()["leido"]
    assert (z["numero_z"], z["fecha"], z["total"], z["tarjeta"], z["confianza"]) == ("0347", "2026-10-18", 1748.0, 1135.7, "alta")
    assert {d["tipo_iva"] for d in z["desglose"]} == {10.0, 21.0}
    # el mismo Z no se puede subir dos veces
    assert subir(c, ventas, "cierre_z_foto.jpg", ruta="/api/movil/cierres-z").status_code == 409
    # cada uno ve solo lo suyo; administración ve todo
    assert {d["tipo"] for d in c.get("/api/movil/facturas", headers=compras).json()} == {"albaran"}
    assert {d["tipo"] for d in c.get("/api/movil/facturas", headers=ventas).json()} == {"tpv"}
    assert {d["tipo"] for d in c.get("/api/movil/facturas", headers=admin).json()} == {"albaran", "tpv"}
    # compras no puede ver la foto del cierre de caja
    tid = r.json()["id"]
    assert c.get(f"/api/movil/facturas/tpv/{tid}/imagen", headers=compras).status_code == 404
    assert c.get(f"/api/movil/facturas/tpv/{tid}/imagen", headers=admin).status_code == 200


def test_mes_completo_cierre_y_liquidacion(c):
    g = tok(c, "g@x.es", "gestor123")
    admin, compras, ventas = (tok(c, e, "cli123") for e in ("u1@x.es", "compras@x.es", "ventas@x.es"))

    alb = subir(c, compras, "albaran_foto.jpg").json()["id"]                              # 3/10 Almacenes Díaz 1.300
    fra = subir(c, compras, "factura_foto.jpg").json()["id"]                              # 14/10 Levante 180 + IVA
    z = subir(c, ventas, "cierre_z_foto.jpg", ruta="/api/movil/cierres-z").json()["id"]   # 18/10 caja 1.748
    c.post("/api/banco/movimientos", headers=g, json={"cliente_id": 1, "fecha": "2026-10-25",
                                                     "concepto": "RECIBO TELEFONICA", "importe": "-60.50"})

    # qué falta, visto por administración del cliente
    falta = c.get("/api/movil/meses/2026/10", headers=admin).json()["pendientes"]
    titulos = " | ".join(p["titulo"] for p in falta)
    assert "en revisión por la gestoría" in titulos
    assert "Pago sin factura" in titulos
    assert "sin cierre de caja" in titulos

    # la gestoría revisa todo
    for ruta, i in (("albaranes", alb), ("compras", fra), ("ventas-tpv", z)):
        assert c.post(f"/api/{ruta}/{i}/validar", headers=g).status_code == 200, ruta
    falta = c.get("/api/clientes/1/meses/2026/10", headers=g).json()["pendientes"]
    reclamar = [p for p in falta if p["quien"] == "proveedor"]
    assert reclamar and "Almacenes" in reclamar[0]["titulo"] or "ALMACENES" in reclamar[0]["titulo"]

    # resumen del mes con y sin IVA
    res = c.get("/api/movil/meses/2026/10", headers=admin).json()["resumen"]
    assert res["gastos"]["base"] == 180.0 and res["gastos"]["total"] == 217.8
    assert res["ingresos"]["tpv"]["total"] == 1748.0 and res["ingresos"]["base"] == 1557.85
    assert res["resultado_sin_iva"] == 1377.85
    assert res["iva_mes"]["total_repercutido"] == 190.15 and res["iva_mes"]["resultado"] == 152.35
    assert res["albaranes"] == {"n": 1, "base": 1300.0, "sin_factura": 1}

    # administración cierra el mes -> ya no se suben documentos de octubre
    assert c.post("/api/movil/meses/2026/10/cerrar", headers=admin).status_code == 200
    r = subir(c, compras, "factura_foto.jpg")
    assert r.status_code == 409 and "cerrado" in r.json()["detail"]
    # la gestoría sí puede seguir revisando un mes cerrado
    assert c.put(f"/api/albaranes/{alb}", headers=g, json={"proveedor_nif": "A28476505", "proveedor_nombre": "Almacenes Díaz",
                 "numero": "A-10233", "fecha": "2026-10-03", "base_imponible": "1300"}).status_code == 200

    # liquidación: contabiliza todo lo revisado y congela el informe
    inf = c.post("/api/clientes/1/meses/2026/10/liquidar", headers=g, json={}).json()
    assert inf["asientos_generados"] == 2 and inf["estado"] == "liquidado"
    diario = c.get("/api/contabilidad/asientos?cliente_id=1&ejercicio=2026", headers=g).json()
    caja = next(a for a in diario if a["origen"] == "venta_tpv")
    cuentas = {(p["cuenta"], p["debe"], p["haber"]) for p in caja["apuntes"]}
    assert ("570", 612.3, 0) in cuentas and ("572", 1135.7, 0) in cuentas and ("477", 0, 124.55) in cuentas
    # liquidado: ni la gestoría lo toca hasta reabrir
    assert c.put(f"/api/albaranes/{alb}", headers=g, json={"base_imponible": "1"}).status_code == 409
    assert c.get("/api/clientes/1/meses/2026/10/informe", headers=g).json()["resultado_sin_iva"] == 1377.85
    assert c.post("/api/clientes/1/meses/2026/10/reabrir", headers=g).status_code == 200
    estados = {m["mes"]: m["estado"] for m in c.get("/api/clientes/1/meses?anio=2026", headers=g).json()}
    assert estados[10] == "abierto"

    # vista por proveedor
    provs = {p["proveedor_nif"]: p for p in c.get("/api/clientes/1/proveedores?anio=2026", headers=g).json()}
    assert provs["A28476505"]["albaranes_sin_factura"] == 1 and provs["B87654323"]["total"] == 217.8


def test_area_web_de_administracion(c):
    """La administración del cliente ve sus albaranes por proveedor y sus proveedores; compras no, y nadie ve otras empresas."""
    admin, compras, otro = (tok(c, e, "cli123") for e in ("u1@x.es", "compras@x.es", "u2@x.es"))
    subir(c, compras, "albaran_foto.jpg")
    g = c.get("/api/movil/albaranes/resumen?anio=2026&mes=10", headers=admin).json()
    assert len(g) == 1 and g[0]["proveedor_nif"] == "A28476505" and len(g[0]["filas"]) == 1
    d = c.get(f"/api/movil/proveedores/documentos?anio=2026&clave={g[0]['clave']}", headers=admin).json()
    assert len(d["albaranes"]) == 1
    assert c.get("/api/movil/albaranes/resumen?anio=2026&mes=10", headers=compras).status_code == 403
    assert c.get("/api/movil/albaranes/resumen?anio=2026&mes=10", headers=otro).json() == []   # otra empresa: nada
    assert c.get("/api/clientes", headers=admin).status_code == 403                           # no ve la lista de empresas
