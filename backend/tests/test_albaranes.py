"""Flujo completo: el cliente sube albaranes y la factura mensual desde el móvil, el sistema
los lee y los archiva donde toca, y la gestoría cuadra la factura con la suma de albaranes."""
import shutil
from pathlib import Path

import pytest

from conftest import tok

DOCS = Path(__file__).parent / "docs"
pytestmark = pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract no instalado")


def subir(c, h, fichero, tipo="auto", mime="image/jpeg"):
    r = c.post("/api/movil/facturas", headers=h, data={"tipo": tipo},
               files={"foto": (fichero, (DOCS / fichero).read_bytes(), mime)})
    assert r.status_code == 201, r.text
    return r.json()


def test_albaranes_y_factura_mensual(c):
    g = tok(c, "g@x.es", "gestor123")
    u1 = tok(c, "u1@x.es", "cli123")
    u2 = tok(c, "u2@x.es", "cli123")

    # 1) el cliente sube un albarán SIN decir qué es: el sistema lo detecta y lo lee
    r = subir(c, u1, "albaran_foto.jpg")
    assert r["tipo"] == "albaran" and r["leido"]["nif"] == "A28476505" and r["leido"]["confianza"] == "alta"
    alb1 = r["id"]
    # una factura de proveedor -> compras
    r = subir(c, u1, "factura_texto.pdf", mime="application/pdf")
    assert r["tipo"] == "compra" and r["leido"]["numero"] == "2026-F-118"
    fra = r["id"]

    # el cliente lo ve en su lista; otro cliente no ve ni la lista ni la foto
    tipos = {(d["tipo"], d["id"]) for d in c.get("/api/movil/facturas", headers=u1).json()}
    assert ("albaran", alb1) in tipos and ("compra", fra) in tipos
    assert c.get("/api/movil/facturas", headers=u2).json() == []
    assert c.get(f"/api/movil/facturas/albaran/{alb1}/imagen", headers=u2).status_code == 404

    # 2) la gestoría ve los datos ya rellenados y los da por buenos
    a = c.get(f"/api/albaranes/{alb1}", headers=g).json()
    assert (a["proveedor_nif"], a["numero"], a["fecha"], a["base_imponible"]) == ("A28476505", "A-10233", "2026-10-03", 1300.0)
    assert a["estado"] == "pendiente" and a["extraccion_confianza"] == "alta"
    assert c.post(f"/api/albaranes/{alb1}/validar", headers=g).status_code == 200
    # otros dos albaranes del mismo proveedor en octubre (metidos a mano)
    ids = [alb1]
    for num, base in (("A-10240", "800"), ("A-10251", "300")):
        r = c.post("/api/albaranes", headers=g, json={"cliente_id": 1, "proveedor_nif": "A28476505",
                   "proveedor_nombre": "Almacenes Díaz SA", "numero": num, "fecha": "2026-10-20", "base_imponible": base})
        ids.append(r.json()["id"])

    # 3) resumen del mes: 3 albaranes, suma 2.400 €; la factura ya llegó pero falta cuadrarla (dif. 50 €)
    res = c.get("/api/albaranes/resumen?cliente_id=1&anio=2026&mes=10", headers=g).json()
    assert len(res) == 1 and res[0]["n_albaranes"] == 3 and res[0]["suma_base"] == 2400.0
    assert res[0]["situacion"] == "por_cuadrar" and res[0]["diferencia"] == 50.0

    # la factura del proveedor aparece como candidata (base 2.450 -> diferencia 50 €)
    c.post(f"/api/compras/{fra}/validar", headers=g)
    cands = c.get("/api/albaranes/candidatas?cliente_id=1&anio=2026&mes=10&proveedor_nif=A28476505&suma_base=2400",
                  headers=g).json()
    assert cands[0]["id"] == fra and cands[0]["diferencia"] == 50.0

    # 4) no cuadra -> se rechaza salvo que se fuerce
    r = c.post("/api/albaranes/vincular", headers=g, json={"factura_id": fra, "albaran_ids": ids})
    assert r.status_code == 409 and "No cuadra" in r.json()["detail"]
    # faltaba un albarán de 50 €: se sube y entonces cuadra
    r = c.post("/api/albaranes", headers=g, json={"cliente_id": 1, "proveedor_nif": "A28476505",
               "numero": "A-10262", "fecha": "2026-10-28", "base_imponible": "50"})
    ids.append(r.json()["id"])
    r = c.post("/api/albaranes/vincular", headers=g, json={"factura_id": fra, "albaran_ids": ids})
    assert r.status_code == 200 and r.json()["cuadra"] is True
    res = c.get("/api/albaranes/resumen?cliente_id=1&anio=2026&mes=10", headers=g).json()
    assert res[0]["situacion"] == "cuadra" and res[0]["facturas"][0]["id"] == fra

    # un albarán facturado no se puede tocar sin desvincularlo
    assert c.put(f"/api/albaranes/{ids[1]}", headers=g, json={"base_imponible": "1"}).status_code == 409
    # el cliente ve su albarán como facturado y vinculado a la factura
    mio = next(d for d in c.get("/api/movil/facturas", headers=u1).json() if d["tipo"] == "albaran")
    assert mio["estado"] == "facturado" and mio["factura_id"] == fra

    # 5) los albaranes NO cuentan para el IVA: solo la factura (2.450 x 21 % = 514,50)
    liq = c.get("/api/movil/iva?anio=2026&trimestre=4", headers=u1).json()
    assert liq["total_soportado"] == 514.5


def test_venta_detectada_por_emisor(c):
    """Factura emitida por el propio cliente -> se archiva como venta."""
    from PIL import Image, ImageDraw, ImageFont
    import io
    img = Image.new("RGB", (1240, 900), "white")
    d = ImageDraw.Draw(img)
    from generar_docs import fuente
    f = fuente("normal", 30)
    for i, t in enumerate(["Carlos Martín Ruiz - Fontanería", "NIF: 44556677L", "FACTURA Nº F2026-0042",
                           "Fecha: 20/10/2026", "Cliente: Hostelería Plaza SL  CIF B87654323",
                           "Base imponible 500,00", "IVA 21% 105,00", "TOTAL 605,00 €"]):
        d.text((80, 60 + i * 80), t, fill="black", font=f)
    b = io.BytesIO()
    img.save(b, "JPEG")
    u1 = tok(c, "u1@x.es", "cli123")
    r = c.post("/api/movil/facturas", headers=u1, files={"foto": ("v.jpg", b.getvalue(), "image/jpeg")})
    assert r.json()["tipo"] == "venta"
    g = tok(c, "g@x.es", "gestor123")
    v = c.get(f"/api/ventas/{r.json()['id']}", headers=g).json()
    assert v["destinatario_nif"] == "B87654323" and v["total"] == 605.0
