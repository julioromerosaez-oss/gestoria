import shutil
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.extraccion import a_decimal, analizar, buscar_nifs, extraer, nif_valido

DOCS = Path(__file__).parent / "docs"
ocr = pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract no instalado")


def test_nif_cif_nie():
    assert nif_valido("44556677L") and not nif_valido("44556677H")
    assert nif_valido("B87654323") and not nif_valido("B87654324")
    assert nif_valido("A28476505")
    assert nif_valido("X1234567L")
    # el OCR mete guiones, espacios o el prefijo ES
    assert [n for n, _ in buscar_nifs("CIF: B-87.654.323\nNIF ES 44556677-L")] == ["B87654323", "44556677L"]


def test_importes_formato_espanol():
    assert a_decimal("1.234,56") == Decimal("1234.56")
    assert a_decimal("1234.56") == Decimal("1234.56")
    assert a_decimal("1.300") == Decimal("1300.00")
    assert a_decimal("37,8") == Decimal("37.80")


def test_factura_profesional_con_irpf():
    texto = """Laura Gómez Arquitectura
    NIF: 12345678Z
    Factura n.º 2026-031     Fecha: 05-10-26
    Cliente: Carlos Martín Ruiz · 44556677L
    Honorarios proyecto reforma
    Base imponible 1.000,00
    IVA 21% 210,00
    Retención IRPF 15% -150,00
    Total 1.060,00 €"""
    r = analizar(texto, "44556677L")
    assert r["tercero_nif"] == "12345678Z"
    assert r["numero"] == "2026-031"
    assert r["fecha"] == date(2026, 10, 5)
    assert (r["base_imponible"], r["tipo_iva"], r["tipo_irpf"], r["total"]) == (
        Decimal("1000.00"), Decimal(21), Decimal(15), Decimal("1060.00"))
    assert r["confianza"] == "alta"


def test_factura_emitida_por_el_cliente_es_venta():
    texto = """Carlos Martín Ruiz - Fontanería   NIF 44556677L
    FACTURA F2026-0042   Fecha 20/10/2026
    Cliente: Hostelería Plaza SL  CIF B87654323
    Base imponible 500,00  IVA 21% 105,00  TOTAL 605,00"""
    r = analizar(texto, "44556677L")
    assert r["emisor_es_cliente"] is True
    assert r["tercero_nif"] == "B87654323"   # el destinatario
    assert r["total"] == Decimal("605.00")


def test_deduce_tipo_iva_si_no_aparece_el_porcentaje():
    r = analizar("FACTURA 7/2026\nFecha 01/10/2026\nB87654323\nBase imponible 100,00\nTotal 110,00", None)
    assert r["tipo_iva"] == Decimal(10)


def test_importes_que_no_cuadran_dan_aviso():
    r = analizar("FACTURA 9\nFecha 01/10/2026\nB87654323\nBase imponible 100,00\nIVA 21% 21,00\nTotal 150,00", None)
    assert r["confianza"] != "alta"
    assert any("no cuadran" in a for a in r["avisos"])


@ocr
def test_foto_factura():
    r = extraer((DOCS / "factura_foto.jpg").read_bytes(), "jpg", "44556677L")
    assert r["metodo"] == "ocr" and r["tipo_documento"] == "factura"
    assert r["tercero_nif"] == "B87654323" and "LEVANTE" in r["tercero_nombre"].upper()
    assert r["numero"] == "FV-2026/0457" and r["fecha"] == date(2026, 10, 14)
    assert (r["base_imponible"], r["tipo_iva"], r["total"]) == (Decimal("180.00"), Decimal(21), Decimal("217.80"))
    assert r["confianza"] == "alta"


@ocr
def test_foto_albaran_torcida_sin_iva():
    r = extraer((DOCS / "albaran_foto.jpg").read_bytes(), "jpg", "44556677L")
    assert r["tipo_documento"] == "albaran"
    assert r["tercero_nif"] == "A28476505" and r["numero"] == "A-10233"
    assert r["fecha"] == date(2026, 10, 3) and r["base_imponible"] == Decimal("1300.00")
    assert r["confianza"] == "alta"


def test_pdf_con_texto():
    r = extraer((DOCS / "factura_texto.pdf").read_bytes(), "pdf", "44556677L")
    assert r["metodo"] == "pdf_texto" and r["numero"] == "2026-F-118"
    assert (r["base_imponible"], r["total"]) == (Decimal("2450.00"), Decimal("2964.50"))


def test_documento_ilegible_no_rompe():
    r = extraer(b"\xff\xd8\xff\xe0basura", "jpg")
    assert r["confianza"] == "error" and r["avisos"]
