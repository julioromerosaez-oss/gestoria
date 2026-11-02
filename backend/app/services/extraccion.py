"""Extracción de datos de facturas y albaranes a partir de una foto o un PDF.

100 % local: sin IA y sin servicios externos.
  1. Texto:   PDF con texto -> pdfplumber.  Foto o PDF escaneado -> OCR con Tesseract (español).
  2. Reglas:  expresiones regulares + validación (dígito de control de NIF/CIF/NIE,
              coherencia base + IVA - IRPF = total, fechas plausibles).
El resultado siempre lo revisa la gestoría: aquí solo se rellena el borrador.
"""
from __future__ import annotations

import io
import re
import unicodedata
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

TIPOS_IVA = (21, 10, 5, 4, 0)
TIPOS_IRPF = (1, 2, 7, 15, 19)
CENT = Decimal("0.01")
MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7,
         "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}


# =====================================================================
# 1. Obtener el texto
# =====================================================================
def _angulo_inclinacion(img) -> float:
    """Ángulo (−12°..12°) que deja las líneas de texto más horizontales.

    Método de perfil de proyección: con el texto recto, la suma de píxeles oscuros por fila
    alterna mucho entre líneas y huecos (varianza máxima)."""
    import numpy as np

    peq = img.copy()
    peq.thumbnail((900, 900))
    arr = np.asarray(peq, dtype=np.uint8)
    tinta = (arr < np.percentile(arr, 35)).astype(np.uint8) * 255
    from PIL import Image
    tinta = Image.fromarray(tinta)

    def puntuacion(a):
        filas = np.asarray(tinta.rotate(a, expand=False, fillcolor=0), dtype=np.float32).sum(axis=1)
        return float(np.var(np.diff(filas)))

    mejor = max(np.arange(-12, 12.5, 1.0), key=puntuacion)
    fino = max(np.arange(mejor - 1, mejor + 1.01, 0.25), key=puntuacion)
    return float(fino)


def _ocr_imagen(img, psm: int = 3) -> str:
    import pytesseract
    from PIL import ImageOps

    img = ImageOps.exif_transpose(img).convert("L")
    if img.width < 1600:  # Tesseract funciona mejor con ~300 ppp
        escala = 1600 / img.width
        img = img.resize((int(img.width * escala), int(img.height * escala)))
    img = ImageOps.autocontrast(img, cutoff=1)
    # 1) fotos de lado o del revés (90°/180°)
    try:
        osd = pytesseract.image_to_osd(img, config="--psm 0", timeout=20)
        giro = int(re.search(r"Rotate: (\d+)", osd).group(1))
        if giro:
            img = img.rotate(-giro, expand=True, fillcolor=255)
    except Exception:
        pass  # poco texto para decidir: se deja como está
    # 2) inclinación pequeña típica de foto con el móvil
    try:
        angulo = _angulo_inclinacion(img)
        if abs(angulo) >= 0.5:
            img = img.rotate(angulo, expand=True, fillcolor=255, resample=3)
    except ImportError:
        pass
    return pytesseract.image_to_string(img, lang="spa", config=f"--psm {psm}", timeout=60)


def texto_de_documento(data: bytes, ext: str, psm: int = 3) -> tuple[str, str]:
    """Devuelve (texto, método)."""
    if ext == "pdf":
        import pdfplumber

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            paginas = pdf.pages[:5]
            texto = "\n".join((p.extract_text() or "") for p in paginas)
            if len(texto.strip()) >= 40:
                return texto, "pdf_texto"
            # PDF escaneado: rasteriza y pasa OCR
            return "\n".join(_ocr_imagen(p.to_image(resolution=300).original, psm) for p in paginas[:3]), "ocr_pdf"
    from PIL import Image

    if ext == "heic":
        from pillow_heif import register_heif_opener
        register_heif_opener()
    return _ocr_imagen(Image.open(io.BytesIO(data)), psm), "ocr"


# =====================================================================
# 2. Utilidades
# =====================================================================
def _sin_acentos(t: str) -> str:
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().upper()


_NUM = re.compile(r"(?<![\d,.])-?\d{1,3}(?:[.\s]\d{3})+(?:,\d{1,2})?(?![\d])|(?<![\d,.])-?\d{1,3}(?:,\d{3})+,\d{2}(?![\d])|(?<![\d,.])-?\d+(?:[.,]\d{1,2})?(?![\d.,]\d)")


def a_decimal(txt: str) -> Decimal | None:
    t = txt.replace(" ", "").replace("€", "")
    if t.count(",") > 1:  # 1,245,45 -> 1245,45
        ent, dec = t.rsplit(",", 1)
        t = ent.replace(",", "") + "," + dec
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        t = t.replace(",", ".")
    elif t.count(".") > 1 or (t.count(".") == 1 and len(t.split(".")[1]) == 3):
        t = t.replace(".", "")  # 1.234 = mil doscientos treinta y cuatro
    try:
        return Decimal(t).quantize(CENT, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None


def _importes(linea: str) -> list[Decimal]:
    sin_pct = re.sub(r"\d+(?:[.,]\d+)?\s*%", " ", linea)          # quita "21%"
    sin_fechas = re.sub(r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}", " ", sin_pct)
    out = []
    for m in _NUM.finditer(sin_fechas):
        v = a_decimal(m.group())
        if v is not None and ("," in m.group() or "." in m.group() or "€" in linea):
            out.append(v)
    return out


# ---------- NIF / CIF / NIE ----------
_LETRAS_DNI = "TRWAGMYFPDXBNJZSQVHLCKE"


def nif_valido(nif: str) -> bool:
    n = nif.upper()
    if re.fullmatch(r"\d{8}[A-Z]", n):
        return _LETRAS_DNI[int(n[:8]) % 23] == n[8]
    if re.fullmatch(r"[XYZ]\d{7}[A-Z]", n):
        return _LETRAS_DNI[int(str("XYZ".index(n[0])) + n[1:8]) % 23] == n[8]
    if re.fullmatch(r"[ABCDEFGHJNPQRSUVW]\d{7}[0-9A-J]", n):
        digitos = n[1:8]
        pares = sum(int(d) for d in digitos[1::2])
        impares = sum(sum(divmod(int(d) * 2, 10)) for d in digitos[0::2])
        control = (10 - (pares + impares) % 10) % 10
        return n[8] in (str(control), "JABCDEFGHI"[control])
    return False


# Se buscan por separado (si no, "NIF 44556677L" se leería como el CIF "F4455667...")
_INICIO = r"(?<![A-Z0-9])(?:ES[\s-]?)?"
_NIF_PATRONES = [
    re.compile(_INICIO + r"(\d{2}[\s.]?\d{3}[\s.]?\d{3}[\s.-]?[A-Z])(?![A-Z0-9])"),                 # DNI
    re.compile(_INICIO + r"([XYZ][\s.-]?\d{7}[\s.-]?[A-Z])(?![A-Z0-9])"),                            # NIE
    re.compile(_INICIO + r"([ABCDEFGHJNPQRSUVW][\s.-]?\d{2}[\s.]?\d{3}[\s.]?\d{2}[\s.-]?[0-9A-J])(?![A-Z0-9])"),  # CIF
]


def buscar_nifs(texto: str) -> list[tuple[str, int]]:
    """[(nif, nº de línea)] en orden de aparición, sin repetidos y con control válido."""
    vistos, out = set(), []
    for i, linea in enumerate(texto.upper().splitlines()):
        encontrados = sorted((m.start(1), re.sub(r"[\s.-]", "", m.group(1)))
                             for p in _NIF_PATRONES for m in p.finditer(linea))
        for _, nif in encontrados:
            if nif_valido(nif) and nif not in vistos:
                vistos.add(nif)
                out.append((nif, i))
    return out


# ---------- fechas ----------
def _fecha_ok(a: int, m: int, d: int) -> date | None:
    if a < 100:
        a += 2000
    try:
        f = date(a, m, d)
    except ValueError:
        return None
    hoy = date.today()
    return f if date(2000, 1, 1) <= f <= date(hoy.year + 1, 12, 31) else None


def _fechas(linea: str) -> list[date]:
    out = []
    for d, m, a in re.findall(r"\b(\d{1,2})\s?[/.-]\s?(\d{1,2})\s?[/.-]\s?(\d{4}|\d{2})\b", linea):
        if f := _fecha_ok(int(a), int(m), int(d)):
            out.append(f)
    for a, m, d in re.findall(r"\b(\d{4})-(\d{2})-(\d{2})\b", linea):
        if f := _fecha_ok(int(a), int(m), int(d)):
            out.append(f)
    for d, mes, a in re.findall(r"\b(\d{1,2})\s+de\s+([a-záé]+)\s+(?:de\s+)?(\d{4})", linea.lower()):
        if mes in MESES and (f := _fecha_ok(int(a), MESES[mes], int(d))):
            out.append(f)
    return out


# =====================================================================
# 3. Análisis del texto
# =====================================================================
_PALABRAS_NO_NUMERO = {"FECHA", "SIMPLIFICADA", "RECTIFICATIVA", "CLIENTE", "PROVEEDOR", "PAGINA", "DE", "NIF", "CIF"}


def _numero_documento(lineas_n: list[str]) -> str | None:
    # "Nº" sale del OCR como NO, N0, N°, N?, N*, N. ...
    marca = r"(?:N\.?\s?[O0º°?*]|N\.|NUM(?:ERO)?|NRO)"
    patrones = [
        marca + r"\.?\s*(?:DE\s+)?(?:FACTURA|ALBARAN|FRA|DOC(?:UMENTO)?)\.?\s*[:#]?\s*([A-Z0-9][A-Z0-9/\-.]{1,24})",
        r"(?:FACTURA|ALBARAN|FRA)\.?\s*" + marca + r"\.?\s*[:#]?\s*([A-Z0-9][A-Z0-9/\-.]{1,24})",
        r"(?:FACTURA|ALBARAN|FRA)\.?\s*[:#]\s*([A-Z0-9][A-Z0-9/\-.]{1,24})",
    ]
    for patron in patrones:
        for linea in lineas_n:
            if re.search(r"TOTAL|IMPORTE|BASE|I\.?V\.?A", linea):
                continue  # líneas de importes: ahí "FACTURA 217,80" no es un número de factura
            for m in re.finditer(patron, linea):
                if re.match(r"[,.]\d", linea[m.end():]):
                    continue  # es un importe (217,80)
                cand = m.group(1).strip(".-/")
                if any(c.isdigit() for c in cand) and cand not in _PALABRAS_NO_NUMERO and not _fechas(cand):
                    return cand
    return None


def _importe_etiquetado(lineas: list[str], lineas_n: list[str], etiquetas: list[str], excluir: list[str] = ()) -> Decimal | None:
    for etiqueta in etiquetas:
        for i, ln in enumerate(lineas_n):
            if re.search(etiqueta, ln) and not any(re.search(x, ln) for x in excluir):
                valores = _importes(lineas[i])
                if not valores and i + 1 < len(lineas):  # el importe en la línea de abajo
                    valores = _importes(lineas[i + 1])
                if valores:
                    return valores[-1]
    return None


def _tipo_en(lineas_n: list[str], clave: str, validos) -> Decimal | None:
    for ln in lineas_n:
        if re.search(clave, ln):
            for p in re.findall(r"(\d{1,2})(?:[.,]0{1,2})?\s*%", ln):
                if int(p) in validos:
                    return Decimal(p)
    return None


def _nombre_cerca(lineas: list[str], idx: int, nif: str) -> str | None:
    def limpiar(t: str) -> str:
        t = re.sub(r"(?i)\b(N\.?I\.?F|C\.?I\.?F|DNI|NIE)\b\.?\s*:?", " ", t)
        t = re.sub(re.escape(nif), " ", t, flags=re.I)
        t = re.sub(r"[^\w\s.,&'-]", " ", t)
        return re.sub(r"\s+", " ", t).strip(" .,-")
    candidatos = []
    for j in (idx, idx - 1, idx - 2, idx - 3):
        if 0 <= j < len(lineas):
            t = limpiar(lineas[j])
            if sum(c.isalpha() for c in t) >= 4 and not re.search(r"(?i)factura|albar|fecha|tel[eé]f|calle|c/|avda|@|www", t):
                candidatos.append(t)
    sociedad = [c for c in candidatos if re.search(r"(?i)\bS\.?\s?L\.?U?\b|\bS\.?\s?A\.?U?\b|S\.?COOP|\bC\.?B\.?\b|SLU|SAU", c)]
    return (sociedad or candidatos or [None])[0]


def analizar(texto: str, nif_cliente: str | None = None) -> dict:
    lineas = [l for l in texto.splitlines() if l.strip()]
    lineas_n = [_sin_acentos(l) for l in lineas]
    todo = "\n".join(lineas_n)
    avisos: list[str] = []

    # --- tipo de documento ---
    es_albaran = bool(re.search(r"ALBAR[AN]N|NOTA DE ENTREGA|DELIVERY NOTE", todo))
    es_factura = bool(re.search(r"\bFACTURA\b|\bFRA\b\.?|\bINVOICE\b", todo))
    tipo_documento = "albaran" if es_albaran and not re.search(r"FACTURA\s*(N|NUM|NRO|:)", todo) else (
        "factura" if es_factura else None)

    # --- NIFs: el emisor suele ser el primero; el del cliente de la gestoría se aparta ---
    nifs = buscar_nifs(texto)
    propio = (nif_cliente or "").upper().replace("-", "").replace(" ", "")
    ajenos = [(n, i) for n, i in nifs if n != propio]
    emisor_es_cliente = bool(nifs and nifs[0][0] == propio)
    tercero_nif, tercero_linea = (ajenos[0] if ajenos else (None, None))
    tercero_nombre = _nombre_cerca(lineas, tercero_linea, tercero_nif) if tercero_nif else None
    if not tercero_nombre and lineas:
        tercero_nombre = next((l.strip() for l in lineas[:4] if sum(c.isalpha() for c in l) >= 4
                               and not re.search(r"(?i)factura|albar", l)), None)

    # --- fecha ---
    fecha = None
    for ln in lineas_n:
        if "FECHA" in ln and (fs := _fechas(ln)):
            fecha = fs[0]
            break
    if not fecha:
        todas = [f for l in lineas for f in _fechas(l)]
        fecha = todas[0] if todas else None

    # --- importes ---
    total = _importe_etiquetado(lineas, lineas_n,
                                [r"TOTAL\s*(A\s*PAGAR|FACTURA|ALBARAN|IMPORTE|EUR|€)", r"IMPORTE\s*TOTAL", r"\bTOTAL\b"],
                                excluir=[r"SUBTOTAL", r"TOTAL\s*(BASE|BRUTO|NETO|IVA|LINEAS|UNIDADES|BULTOS|KG)"])
    base = _importe_etiquetado(lineas, lineas_n,
                               [r"BASE\s*IMPONIBLE|B\.\s*IMPONIBLE|BASE\s*IMP", r"SUBTOTAL|TOTAL\s*NETO|IMPORTE\s*NETO|TOTAL\s*BASE|\bNETO\b",
                                r"\bBASE\b"])
    tipo_iva = _tipo_en(lineas_n, r"I\.?V\.?A|IMPUESTO", TIPOS_IVA)
    tipo_irpf = _tipo_en(lineas_n, r"I\.?R\.?P\.?F|RETENCION", TIPOS_IRPF) or Decimal(0)

    # --- coherencia: base + IVA - IRPF = total ---
    def calc_total(b, iva, irpf):
        return (b + (b * iva / 100).quantize(CENT, ROUND_HALF_UP) - (b * irpf / 100).quantize(CENT, ROUND_HALF_UP))

    cuadra = False
    if base is not None and total is not None and tipo_iva is None and base > 0:
        # deduce el tipo de IVA
        for t in TIPOS_IVA:
            if abs(calc_total(base, Decimal(t), tipo_irpf) - total) <= Decimal("0.05"):
                tipo_iva = Decimal(t)
                break
    if base is None and total is not None and tipo_iva is not None:
        base = (total / (1 + (tipo_iva - tipo_irpf) / 100)).quantize(CENT, ROUND_HALF_UP)
        avisos.append("Base calculada a partir del total")
    if base is not None and tipo_iva is not None:
        esperado = calc_total(base, tipo_iva, tipo_irpf)
        if total is None:
            total = esperado
            avisos.append("Total calculado a partir de la base")
        cuadra = abs(esperado - total) <= Decimal("0.05")
        if not cuadra:
            avisos.append(f"Los importes no cuadran (base + IVA − IRPF = {esperado}, total leído {total})")
    if tipo_documento == "albaran" and tipo_iva is None and total is None and base is not None:
        # Lo normal en un albarán: importe neto sin desglose de IVA. Se cuadra por base.
        cuadra = True
        avisos.append("Albarán sin IVA desglosado: se cuadrará con la factura por base imponible")
    elif tipo_iva is None:
        avisos.append("No se ha podido determinar el tipo de IVA")
    if not tercero_nif:
        avisos.append("No se ha encontrado un NIF/CIF válido")
    if not fecha:
        avisos.append("No se ha encontrado la fecha")

    puntos = sum([bool(tercero_nif), bool(fecha), cuadra, bool(_numero_documento(lineas_n))])
    confianza = "alta" if puntos == 4 else "media" if puntos >= 2 and total is not None else "baja"

    return {
        "tipo_documento": tipo_documento,
        "emisor_es_cliente": emisor_es_cliente,
        "tercero_nif": tercero_nif,
        "tercero_nombre": (tercero_nombre or None) and tercero_nombre[:200],
        "numero": _numero_documento(lineas_n),
        "fecha": fecha,
        "base_imponible": base,
        "tipo_iva": tipo_iva,
        "tipo_irpf": tipo_irpf,
        "total": total,
        "confianza": confianza,
        "avisos": avisos,
    }


def extraer(data: bytes, ext: str, nif_cliente: str | None = None) -> dict:
    """Punto de entrada. Nunca lanza excepción: si algo falla devuelve confianza 'error'."""
    try:
        texto, metodo = texto_de_documento(data, ext)
    except Exception as e:  # tesseract no instalado, imagen corrupta, timeout...
        return {"confianza": "error", "avisos": [f"No se pudo leer el documento ({type(e).__name__})"],
                "metodo": None, "texto": ""}
    resultado = analizar(texto, nif_cliente)
    if resultado["confianza"] != "alta" and metodo.startswith("ocr"):
        # segunda pasada con otra segmentación (tickets y facturas a dos columnas)
        try:
            texto2, _ = texto_de_documento(data, ext, psm=4)
            r2 = analizar(texto2, nif_cliente)
            orden = {"alta": 3, "media": 2, "baja": 1}
            if orden.get(r2["confianza"], 0) > orden.get(resultado["confianza"], 0):
                resultado, texto = r2, texto2
        except Exception:
            pass
    resultado.update(metodo=metodo, texto=texto[:8000])
    return resultado


# =====================================================================
# 4. Cierre de caja (informe Z del TPV)
# =====================================================================
def _par_base_cuota(valores: list[Decimal], tipo: Decimal) -> tuple[Decimal, Decimal] | None:
    """De los importes de una línea "IVA 10%", deduce (base, cuota) por coherencia."""
    r = tipo / 100
    tol = lambda v: max(Decimal("0.06"), v * Decimal("0.005"))  # noqa: E731
    for b in valores:
        for c in valores:
            if b is not c and b > 0 and abs(c - (b * r).quantize(CENT, ROUND_HALF_UP)) <= tol(c):
                return b, c
    for b in valores:
        for t in valores:
            if b is not t and b > 0 and abs(t - (b * (1 + r)).quantize(CENT, ROUND_HALF_UP)) <= tol(t):
                return b, t - b
    return None


def analizar_z(texto: str) -> dict:
    lineas = [l for l in texto.splitlines() if l.strip()]
    lineas_n = [_sin_acentos(l) for l in lineas]
    avisos: list[str] = []

    # --- nº de Z y fecha ---
    numero_z = None
    for ln in lineas_n:
        m = re.search(r"(?:INFORME|CIERRE|ARQUEO)\s*(?:DE\s*CAJA\s*)?(?:\bZ\b)?|\bZ\b\s*(?:N|#|:|\d)", ln)
        if not m or "FECHA" in ln:
            continue
        resto = re.sub(r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{1,2}:\d{2}", " ", ln[m.end() - 1:])
        nums = re.findall(r"\d{1,8}", resto)
        if nums:  # el OCR mete basura ("N*2 0347"): el número más largo es el del Z
            numero_z = max(nums, key=len)
            break
    fecha = None
    for ln in lineas_n:
        if "FECHA" in ln and (fs := _fechas(ln)):
            fecha = fs[0]
            break
    if not fecha:
        todas = [f for l in lineas for f in _fechas(l)]
        fecha = todas[0] if todas else None

    # --- desglose por tipo de IVA ---
    porcion: dict[Decimal, dict] = {}
    for linea, ln in zip(lineas, lineas_n):
        tipos = [Decimal(p) for p in re.findall(r"(\d{1,2})(?:[.,]0{1,2})?\s*%", ln) if int(p) in TIPOS_IVA]
        if len(tipos) != 1 or tipos[0] == 0:
            continue
        t = tipos[0]
        valores = _importes(linea)
        d = porcion.setdefault(t, {})
        if len(valores) >= 2 and (par := _par_base_cuota(valores, t)):
            d["base"], d["cuota"] = par
        elif len(valores) == 1:
            v = valores[0]
            if re.search(r"\bBASE\b|\bB\.?\s?I\b|\bNETO\b", ln):
                d["base"] = v
            elif re.search(r"CUOTA|\bIVA\b|IMPUESTO", ln) and "TOTAL" not in ln:
                d.setdefault("cuota_suelta", v)
            else:
                d["total"] = v
    def construir(interpretacion: dict) -> list[dict]:
        out = []
        for t, d in sorted(porcion.items(), reverse=True):
            r = t / 100
            base, cuota = d.get("base"), d.get("cuota")
            suelto = d.get("cuota_suelta")
            if base is None and d.get("total") is not None:
                base = (d["total"] / (1 + r)).quantize(CENT, ROUND_HALF_UP)
            if base is None and suelto is not None:
                como = interpretacion.get(t, "cuota")       # "IVA 10% 124,55": ¿cuota, base o total?
                base = {"cuota": suelto / r, "base": suelto, "total": suelto / (1 + r)}[como].quantize(CENT, ROUND_HALF_UP)
                if como == "cuota":
                    cuota = suelto
            if base is None:
                continue
            if cuota is None:
                cuota = suelto if suelto is not None and abs(suelto - base * r) <= Decimal("0.10") \
                    else (base * r).quantize(CENT, ROUND_HALF_UP)
            out.append({"tipo_iva": t, "base": base, "cuota": cuota})
        return out

    desglose = construir({})
    ambiguos = [t for t, d in porcion.items() if d.get("base") is None and d.get("total") is None
                and d.get("cuota_suelta") is not None]
    # --- total y cobros ---
    total = _importe_etiquetado(lineas, lineas_n,
                                [r"TOTAL\s*(VENTAS|CAJA|Z|DIA|NETO\s*\+\s*IVA|GENERAL|COBRADO)", r"\bTOTAL\b"],
                                excluir=[r"\d{1,2}\s*%", r"TICKET", r"EFECTIVO|TARJETA|BASE|CUOTA|DESCUENTO|ANULAC"])
    efectivo = _importe_etiquetado(lineas, lineas_n, [r"EFECTIVO|METALICO|CONTADO|CASH"]) or Decimal(0)
    tarjeta = _importe_etiquetado(lineas, lineas_n, [r"TARJETA|VISA|DATAFONO|T\.?\s?CREDITO|BIZUM"]) or Decimal(0)
    num_tickets = None
    for ln in lineas_n:
        if m := re.search(r"(?:N\.?\s?[O0º°?*]?\.?\s*(?:DE\s*)?TICKETS|TICKETS|OPERACIONES|N\.?\s?CLIENTES)\D{0,6}(\d{1,5})\b", ln):
            num_tickets = int(m.group(1))
            break

    if ambiguos and total is not None:
        from itertools import product
        for combo in product(("cuota", "total", "base"), repeat=len(ambiguos)):
            prueba = construir(dict(zip(ambiguos, combo)))
            if abs(sum((d["base"] + d["cuota"] for d in prueba), Decimal(0)) - total) <= Decimal("0.10"):
                desglose = prueba
                break
    suma = sum((d["base"] + d["cuota"] for d in desglose), Decimal(0))
    if total is None and desglose:
        total = suma
        avisos.append("Total calculado a partir del desglose de IVA")
    if not desglose and total is not None:
        avisos.append("No se ha encontrado el desglose por IVA: indícalo a mano")
    cuadra = bool(desglose) and total is not None and abs(suma - total) <= Decimal("0.10")
    if desglose and total is not None and not cuadra:
        avisos.append(f"El desglose ({suma}) no coincide con el total ({total})")
    if total is not None and (efectivo or tarjeta) and abs(efectivo + tarjeta - total) > Decimal("0.10"):
        avisos.append(f"Efectivo + tarjeta ({efectivo + tarjeta}) no coincide con el total ({total})")
    if not fecha:
        avisos.append("No se ha encontrado la fecha")
    confianza = "alta" if cuadra and fecha else "media" if total is not None and fecha else "baja"
    return {"tipo_documento": "cierre_z", "numero_z": numero_z, "fecha": fecha, "num_tickets": num_tickets,
            "desglose": desglose, "total": total, "efectivo": efectivo, "tarjeta": tarjeta,
            "confianza": confianza, "avisos": avisos}


def extraer_z(data: bytes, ext: str) -> dict:
    try:
        texto, metodo = texto_de_documento(data, ext, psm=4)  # ticket: una columna, filas juntas
    except Exception as e:
        return {"confianza": "error", "avisos": [f"No se pudo leer el documento ({type(e).__name__})"],
                "desglose": [], "texto": ""}
    r = analizar_z(texto)
    r.update(metodo=metodo, texto=texto[:8000])
    return r
