"""Genera documentos de prueba realistas (fotos y PDF) para los tests de extracción."""
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

D = Path(__file__).parent / "docs"
D.mkdir(exist_ok=True)
F = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def foto(lineas, nombre, girar=0.0, ruido=True):
    img = Image.new("RGB", (1240, 1754), (250, 249, 245))
    d = ImageDraw.Draw(img)
    y = 90
    for texto, tam, negrita in lineas:
        d.text((90, y), texto, fill=(25, 25, 25), font=ImageFont.truetype(FB if negrita else F, tam))
        y += int(tam * 1.7)
    if girar:
        img = img.rotate(girar, expand=True, fillcolor=(90, 90, 90))
    if ruido:
        img = img.filter(ImageFilter.GaussianBlur(0.8))
    img.save(D / nombre, "JPEG", quality=70)


def generar():
    foto([
        ("SUMINISTROS ELÉCTRICOS LEVANTE S.L.", 40, True),
        ("C/ Colón 22, 46004 Valencia  ·  CIF: B87654323", 26, False),
        ("", 20, False),
        ("FACTURA Nº: FV-2026/0457", 34, True),
        ("Fecha factura: 14/10/2026", 26, False),
        ("Cliente: Carlos Martín Ruiz  NIF 44556677L", 26, False),
        ("", 20, False),
        ("Concepto                      Cant.    Precio     Importe", 24, False),
        ("Cable 2,5mm (rollo 100m)        3      45,00      135,00", 24, False),
        ("Diferencial 40A                 2      22,50       45,00", 24, False),
        ("", 20, False),
        ("Base imponible                                    180,00 €", 26, False),
        ("IVA 21%                                            37,80 €", 26, False),
        ("TOTAL FACTURA                                     217,80 €", 30, True),
    ], "factura_foto.jpg", girar=1.5)

    foto([
        ("ALMACENES DÍAZ, S.A.", 40, True),
        ("CIF A28476505 - Polígono Norte, nave 7", 26, False),
        ("ALBARÁN DE ENTREGA", 34, True),
        ("Nº Albarán: A-10233", 28, False),
        ("Fecha: 3 de octubre de 2026", 26, False),
        ("Entregado a: Carlos Martín Ruiz (44556677L)", 26, False),
        ("Ref.     Descripción              Uds.   Importe", 24, False),
        ("T-120    Tubo cobre 15mm            20    1.240,00", 24, False),
        ("C-050    Codos 90º                  40       60,00", 24, False),
        ("Total neto                                1.300,00", 26, False),
        ("Recibí conforme: ____________", 24, False),
    ], "albaran_foto.jpg", girar=-2.0)

    # ticket de cierre Z (estrecho, como sale de la impresora térmica)
    z = Image.new("RGB", (620, 1500), (252, 252, 250))
    d = ImageDraw.Draw(z)
    fm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 24)
    for i, t in enumerate(["   BAR RESTAURANTE LA PLAZA", "   CIF B65432106", "", "    INFORME Z  Nº 0347",
                           "Fecha: 18/10/2026   23:41", "--------------------------------",
                           "Nº tickets:            86", "--------------------------------",
                           "IVA 10%  Base      1.245,45", "         Cuota       124,55",
                           "IVA 21%  Base        312,40", "         Cuota        65,60",
                           "--------------------------------", "TOTAL VENTAS        1.748,00",
                           "Efectivo              612,30", "Tarjeta             1.135,70",
                           "--------------------------------", "      Gracias por su visita"]):
        d.text((20, 40 + i * 44), t, fill=(30, 30, 30), font=fm)
    z.rotate(-2.5, expand=True, fillcolor=(80, 80, 80)).filter(ImageFilter.GaussianBlur(0.7)).save(
        D / "cierre_z_foto.jpg", "JPEG", quality=70)

    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(D / "factura_texto.pdf"), pagesize=A4)
    y = 800
    for t in ["ALMACENES DÍAZ, S.A.", "CIF: A28476505", "Factura nº 2026-F-118", "Fecha: 31/10/2026",
              "Cliente: Carlos Martín Ruiz - NIF: 44556677L",
              "Resumen albaranes octubre: A-10233, A-10240, A-10251",
              "Base Imponible: 2.450,00", "I.V.A. 21%: 514,50", "Total a pagar: 2.964,50 EUR"]:
        c.drawString(60, y, t)
        y -= 26
    c.save()


if __name__ == "__main__":
    generar()
    print("ok", sorted(p.name for p in D.iterdir()))
