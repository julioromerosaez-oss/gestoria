from conftest import JPEG, tok  # noqa: F401


def test_sin_token_401(c):
    assert c.get("/api/clientes").status_code == 401
    assert c.get("/api/movil/iva").status_code == 401


def test_token_manipulado(c):
    h = tok(c, "g@x.es", "gestor123")
    malo = {"Authorization": h["Authorization"][:-3] + "abc"}
    assert c.get("/api/clientes", headers=malo).status_code == 401


def test_cliente_no_accede_a_gestoria(c):
    h = tok(c, "u1@x.es", "cli123")
    assert c.get("/api/clientes", headers=h).status_code == 403
    assert c.get("/api/compras", headers=h).status_code == 403


def test_bloqueo_fuerza_bruta(c):
    for _ in range(5):
        assert c.post("/api/auth/login", json={"email": "g@x.es", "password": "mal"}).status_code == 401
    assert c.post("/api/auth/login", json={"email": "g@x.es", "password": "gestor123"}).status_code == 429


def test_cabeceras_seguridad(c):
    r = c.get("/api/salud")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"


def test_flujo_completo_y_aislamiento(c):
    g = tok(c, "g@x.es", "gestor123")
    u1 = tok(c, "u1@x.es", "cli123")
    u2 = tok(c, "u2@x.es", "cli123")

    # rechaza ficheros que no son imagen/PDF aunque digan serlo
    r = c.post("/api/movil/facturas", headers=u1, files={"foto": ("x.jpg", b"<script>", "image/jpeg")})
    assert r.status_code == 415

    # cliente 1 sube foto
    r = c.post("/api/movil/facturas", headers=u1, files={"foto": ("f.jpg", JPEG, "image/jpeg")},
               data={"notas": "gasoil"})
    assert r.status_code == 201
    fid = r.json()["id"]
    assert c.get(f"/api/movil/facturas/compra/{fid}/imagen", headers=u1).status_code == 200
    # cliente 2 no puede ver la foto de cliente 1
    assert c.get(f"/api/movil/facturas/compra/{fid}/imagen", headers=u2).status_code == 404
    assert c.get("/api/movil/facturas", headers=u2).json() == []

    # gestor completa, valida y contabiliza la compra
    r = c.put(f"/api/compras/{fid}", headers=g, json={
        "numero": "G-1", "fecha": "2026-08-10", "base_imponible": "100", "tipo_iva": "21",
        "tipo_irpf": "0", "proveedor_nombre": "Repsol", "cuenta_gasto": "628"})
    assert r.json()["total"] == 121.0
    assert c.post(f"/api/compras/{fid}/contabilizar", headers=g).status_code == 409  # sin validar
    assert c.post(f"/api/compras/{fid}/validar", headers=g).status_code == 200
    asiento = c.post(f"/api/compras/{fid}/contabilizar", headers=g).json()
    assert sum(a["debe"] for a in asiento["apuntes"]) == sum(a["haber"] for a in asiento["apuntes"]) == 121.0

    # venta con IRPF 15 %
    r = c.post("/api/ventas", headers=g, json={"cliente_id": 1, "fecha": "2026-08-20",
               "base_imponible": "1000", "tipo_iva": "21", "tipo_irpf": "15", "destinatario_nombre": "ACME SL"})
    v = r.json()
    assert v["total"] == 1060.0 and v["numero"].startswith("A2026-")
    c.post(f"/api/ventas/{v['id']}/contabilizar", headers=g)

    # IVA 3T: 210 repercutido - 21 soportado = 189 a ingresar
    liq = c.get("/api/movil/iva?anio=2026&trimestre=3", headers=u1).json()
    assert liq["resultado"] == 189.0 and liq["situacion"] == "a ingresar"
    m = c.get("/api/movil/margen?anio=2026", headers=u1).json()
    assert m["ingresos"] == 1000.0 and m["gastos"] == 100.0 and m["margen"] == 900.0

    # conciliación: importa extracto y concilia el cobro
    csv = "fecha;concepto;importe\n25/08/2026;TRANSF ACME SL;1.060,00\n12/08/2026;RECIBO REPSOL G-1;-121,00\n"
    r = c.post("/api/banco/importar", headers=g, data={"cliente_id": "1"},
               files={"archivo": ("e.csv", csv.encode(), "text/csv")})
    assert r.json()["importados"] == 2
    movs = c.get("/api/banco/movimientos?cliente_id=1", headers=g).json()
    for mv in movs:
        sug = c.get(f"/api/banco/movimientos/{mv['id']}/sugerencias", headers=g).json()
        assert sug, mv
        r = c.post(f"/api/banco/movimientos/{mv['id']}/conciliar", headers=g,
                   json={"tipo": sug[0]["tipo"], "factura_id": sug[0]["factura_id"]})
        assert r.status_code == 200 and r.json()["conciliado"]
    saldos = {s["cuenta"]: s["saldo"] for s in c.get("/api/contabilidad/sumas-saldos?cliente_id=1&ejercicio=2026", headers=g).json()}
    assert saldos["400"] == 0 and saldos["430"] == 0 and saldos["572"] == 939.0

    # asiento descuadrado rechazado
    r = c.post("/api/contabilidad/asientos", headers=g, json={"cliente_id": 1, "fecha": "2026-09-01",
               "concepto": "x", "apuntes": [{"cuenta": "572", "descripcion": "a", "debe": 10},
                                            {"cuenta": "430", "descripcion": "b", "haber": 9}]})
    assert r.status_code == 422
