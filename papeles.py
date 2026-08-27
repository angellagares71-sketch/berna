# -*- coding: utf-8 -*-
r"""
Papeles: presupuestos en PDF y manejo de PDFs.

Angel se dedica al dron y para cobrar hay que pasar presupuestos. Escribir
uno a mano en el Word cada vez, cuadrar el IVA y guardarlo bonito es
justamente de lo que un asistente tiene que librarte.

QUE ES Y QUE NO ES
  Esto hace **PRESUPUESTOS**, que es una oferta y no obliga a nada. NO hace
  facturas: una factura tiene requisitos legales (numeracion correlativa sin
  huecos, NIF, retenciones segun el caso) y equivocarse ahi te mete en un lio
  con Hacienda. Si algun dia hace falta facturar, que lo haga con un programa
  de facturacion o con su gestor. Esta escrito aqui para que no se cruce esa
  raya por comodidad.

  El IVA se calcula al 21%, que es el general en Espana, y **se ve desglosado
  en el papel** para que Angel pueda comprobarlo de un vistazo. Si su caso es
  otro (recargo de equivalencia, exento, otro tipo), se le pasa el numero y
  ya esta: el programa no adivina la situacion fiscal de nadie.

COMO SE DIBUJA
  Con PyMuPDF, que ya estaba instalado para leer PDFs. Nada de plantillas ni
  librerias nuevas: A4, texto y unas lineas. Sencillo y que se lea bien
  impreso o en el movil.
"""
import os
import json
import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
PERFIL = os.path.join(BASE, "perfil.json")
SALIDA = os.path.join(os.path.expanduser("~"), "Documents", "Berna")

IVA = 21.0
A4 = (595, 842)
MARGEN = 56

TINTA = (0.10, 0.12, 0.16)
SUAVE = (0.45, 0.48, 0.55)
LINEA = (0.80, 0.83, 0.88)
AZUL = (0.16, 0.42, 0.72)


def _perfil():
    try:
        with open(PERFIL, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _carpeta():
    os.makedirs(SALIDA, exist_ok=True)
    return SALIDA


def _sin_pisar(ruta):
    if not os.path.exists(ruta):
        return ruta
    raiz, ext = os.path.splitext(ruta)
    i = 2
    while os.path.exists("%s-%d%s" % (raiz, i, ext)):
        i += 1
    return "%s-%d%s" % (raiz, i, ext)


def _euros(n):
    return ("%.2f" % n).replace(".", ",") + " EUR"


def _entender_conceptos(conceptos):
    """Acepta lo que mande el modelo: lista, o texto con una linea por concepto.

    Cada linea puede ser 'Grabacion con dron | 2 | 300' o 'Grabacion, 2, 300'
    o simplemente 'Grabacion 300'. Se es flexible a proposito, porque el
    modelo no siempre manda lo mismo y esto no puede fallar por una coma.
    """
    filas = []
    if isinstance(conceptos, (list, tuple)):
        crudas = conceptos
    else:
        crudas = [l for l in str(conceptos or "").splitlines() if l.strip()]
    for c in crudas:
        if isinstance(c, dict):
            desc = str(c.get("concepto") or c.get("descripcion") or "").strip()
            try:
                unidades = float(c.get("unidades") or c.get("cantidad") or 1)
            except Exception:
                unidades = 1
            try:
                precio = float(str(c.get("precio") or 0).replace(",", "."))
            except Exception:
                precio = 0.0
        else:
            texto = str(c).strip()
            # La barra y el punto y coma mandan; la coma solo se usa si no hay
            # ninguna de las dos, porque las descripciones LLEVAN comas
            # ("Grabacion aerea, media jornada") y partir por ahi se comia
            # media frase. Paso de verdad, se vio en el PDF impreso.
            sep = "|" if "|" in texto else (";" if ";" in texto else ",")
            trozos = [x.strip() for x in texto.split(sep)]
            trozos = [x for x in trozos if x]

            def _numero(x):
                x = x.replace("EUR", "").replace("eur", "").replace("\u20ac", "")
                x = x.replace(",", ".").strip()
                try:
                    return float(x)
                except Exception:
                    return None

            # la descripcion es todo lo de delante del primer numero suelto
            corte = len(trozos)
            for i, x in enumerate(trozos):
                if i and _numero(x) is not None:
                    corte = i
                    break
            desc = sep.join(trozos[:corte]).strip() or texto
            numeros = [n for n in (_numero(x) for x in trozos[corte:]) if n is not None]
            unidades, precio = 1.0, 0.0
            if len(numeros) >= 2:
                unidades, precio = numeros[0], numeros[1]
            elif numeros:
                precio = numeros[0]
        if desc:
            filas.append((desc[:80], unidades, precio))
    return filas


def hacer_presupuesto(cliente, conceptos, notas="", validez_dias=30, permiso=None):
    filas = _entender_conceptos(conceptos)
    if not filas:
        return ("No he entendido los conceptos. Pasamelos con una linea por "
                "cosa, asi: 'Grabacion con dron media jornada | 1 | 300'.")
    if not str(cliente or "").strip():
        return "Dime para quien es el presupuesto."
    try:
        import pymupdf as fitz          # 'fitz' esta deprecado y avisa por pantalla
    except Exception:
        try:
            import fitz
        except Exception as e:
            return "No tengo la libreria de PDF: %s" % e

    base = sum(u * p for _d, u, p in filas)
    iva = base * IVA / 100.0
    total = base + iva
    resumen = "\n".join("  %s x%g = %s" % (d, u, _euros(u * p)) for d, u, p in filas)
    aviso = ("Berna va a hacer un PRESUPUESTO en PDF:\n\nPara: %s\n\n%s\n\n"
             "Base: %s\nIVA (21%%): %s\nTOTAL: %s\n\n"
             "Es un presupuesto, NO una factura. Revisa los numeros. Le dejas?"
             % (cliente, resumen, _euros(base), _euros(iva), _euros(total)))
    if permiso is None or not permiso(aviso):
        return "No me has dado permiso, no he hecho el presupuesto."

    p = _perfil()
    quien = p.get("nombre") or "Angel"
    zona = p.get("zona") or ""
    hoy = datetime.datetime.now()
    numero = hoy.strftime("P-%Y%m%d-%H%M")

    doc = fitz.open()
    pag = doc.new_page(width=A4[0], height=A4[1])
    x, y = MARGEN, MARGEN

    pag.insert_text((x, y), "PRESUPUESTO", fontsize=24, fontname="hebo", color=TINTA)
    pag.insert_text((x, y + 20), "Nº %s" % numero, fontsize=9, color=SUAVE)
    pag.insert_text((A4[0] - MARGEN - 150, y), quien, fontsize=12,
                    fontname="hebo", color=TINTA)
    if zona:
        pag.insert_text((A4[0] - MARGEN - 150, y + 16), zona, fontsize=9, color=SUAVE)
    if p.get("habilidades"):
        hab = p["habilidades"]
        hab = ", ".join(hab) if isinstance(hab, list) else str(hab)
        pag.insert_text((A4[0] - MARGEN - 150, y + 29), hab[:44], fontsize=8, color=SUAVE)

    y += 56
    pag.draw_line(fitz.Point(x, y), fitz.Point(A4[0] - MARGEN, y), color=LINEA, width=1)
    y += 24
    pag.insert_text((x, y), "Para:", fontsize=9, color=SUAVE)
    pag.insert_text((x + 40, y), str(cliente)[:60], fontsize=11,
                    fontname="hebo", color=TINTA)
    pag.insert_text((A4[0] - MARGEN - 150, y), "Fecha: %s" % hoy.strftime("%d/%m/%Y"),
                    fontsize=9, color=SUAVE)

    y += 34
    pag.insert_text((x, y), "CONCEPTO", fontsize=9, fontname="hebo", color=SUAVE)
    pag.insert_text((x + 300, y), "UDS", fontsize=9, fontname="hebo", color=SUAVE)
    pag.insert_text((x + 350, y), "PRECIO", fontsize=9, fontname="hebo", color=SUAVE)
    pag.insert_text((x + 430, y), "IMPORTE", fontsize=9, fontname="hebo", color=SUAVE)
    y += 8
    pag.draw_line(fitz.Point(x, y), fitz.Point(A4[0] - MARGEN, y), color=LINEA, width=1)

    y += 20
    for desc, uds, precio in filas[:22]:
        pag.insert_text((x, y), desc[:52], fontsize=10, color=TINTA)
        pag.insert_text((x + 300, y), "%g" % uds, fontsize=10, color=TINTA)
        pag.insert_text((x + 350, y), _euros(precio), fontsize=10, color=TINTA)
        pag.insert_text((x + 430, y), _euros(uds * precio), fontsize=10, color=TINTA)
        y += 20

    y += 6
    pag.draw_line(fitz.Point(x + 300, y), fitz.Point(A4[0] - MARGEN, y),
                  color=LINEA, width=1)
    y += 20
    for etiqueta, valor, gordo in (("Base imponible", base, False),
                                   ("IVA (%g%%)" % IVA, iva, False),
                                   ("TOTAL", total, True)):
        pag.insert_text((x + 330, y), etiqueta, fontsize=11 if gordo else 10,
                        fontname="hebo" if gordo else "helv",
                        color=TINTA if gordo else SUAVE)
        pag.insert_text((x + 430, y), _euros(valor), fontsize=12 if gordo else 10,
                        fontname="hebo" if gordo else "helv",
                        color=AZUL if gordo else TINTA)
        y += 22

    y += 20
    if notas:
        pag.insert_textbox(fitz.Rect(x, y, A4[0] - MARGEN, y + 70), str(notas)[:600],
                           fontsize=9, color=TINTA)
        y += 76
    try:
        dias = max(1, min(365, int(float(validez_dias))))
    except Exception:
        dias = 30
    caduca = (hoy + datetime.timedelta(days=dias)).strftime("%d/%m/%Y")
    pag.insert_textbox(
        fitz.Rect(x, A4[1] - MARGEN - 46, A4[0] - MARGEN, A4[1] - MARGEN),
        "Presupuesto valido hasta el %s. Los precios incluyen el desplazamiento "
        "salvo que se indique lo contrario. Este documento es una oferta y no "
        "una factura." % caduca, fontsize=8, color=SUAVE)

    nombre = "presupuesto-%s-%s.pdf" % (
        "".join(c for c in str(cliente) if c.isalnum() or c in " -_")[:30].strip()
        .replace(" ", "-").lower(), hoy.strftime("%Y%m%d"))
    ruta = _sin_pisar(os.path.join(_carpeta(), nombre))
    doc.save(ruta)
    doc.close()
    try:
        import tareas
        tareas._apuntar("PAPELES PRESUPUESTO", "%s %s" % (cliente, _euros(total)), ruta)
    except Exception:
        pass
    return ("Presupuesto hecho: %s\n\nPara %s, total %s (base %s + IVA %s).\n\n"
            "Diselo en una frase con el total, y ofrecele abrirselo para "
            "repasarlo antes de mandarlo. Recuerdale que es un presupuesto, no "
            "una factura." % (ruta, cliente, _euros(total), _euros(base), _euros(iva)))


def unir_pdfs(rutas, salida="", permiso=None):
    if isinstance(rutas, str):
        trozos = [r.strip().strip('"') for r in rutas.replace(";", "\n").splitlines()]
    else:
        trozos = [str(r).strip() for r in (rutas or [])]
    trozos = [r for r in trozos if r]
    faltan = [r for r in trozos if not os.path.isfile(r)]
    if len(trozos) < 2:
        return "Dame al menos dos PDF para juntarlos."
    if faltan:
        return "No encuentro estos: %s" % ", ".join(faltan[:4])
    try:
        import pymupdf as fitz          # 'fitz' esta deprecado y avisa por pantalla
    except Exception:
        try:
            import fitz
        except Exception as e:
            return "No tengo la libreria de PDF: %s" % e
    salida = salida or os.path.join(_carpeta(), "unido-%s.pdf"
                                    % datetime.datetime.now().strftime("%Y%m%d-%H%M"))
    if permiso is None or not permiso(
            "Berna va a UNIR %d PDF en uno solo:\n\n%s\n\nSe guardara en:\n%s\n\n"
            "Los originales no se tocan. Le dejas?"
            % (len(trozos), "\n".join(os.path.basename(r) for r in trozos[:8]), salida)):
        return "No me has dado permiso, no he unido nada."
    try:
        doc = fitz.open()
        paginas = 0
        for r in trozos:
            with fitz.open(r) as otro:
                doc.insert_pdf(otro)
                paginas += otro.page_count
        ruta = _sin_pisar(salida)
        doc.save(ruta)
        doc.close()
        return "Unidos %d PDF (%d paginas) en:\n%s" % (len(trozos), paginas, ruta)
    except Exception as e:
        return "No he podido unirlos: %s" % e


def fotos_a_pdf(carpeta, salida="", ancho=1600, permiso=None):
    if not os.path.isdir(carpeta):
        return "No encuentro esa carpeta: %s" % carpeta
    try:
        import pymupdf as fitz
        from PIL import Image
    except Exception as e:
        return "Me falta una libreria: %s" % e
    fotos = [os.path.join(carpeta, f) for f in sorted(os.listdir(carpeta))
             if f.lower().endswith((".jpg", ".jpeg", ".png"))]
    if not fotos:
        return "En esa carpeta no hay fotos jpg ni png."
    salida = salida or os.path.join(_carpeta(), "%s.pdf"
                                    % os.path.basename(os.path.normpath(carpeta)))
    if permiso is None or not permiso(
            "Berna va a meter %d fotos en un PDF:\n\nDe: %s\nA:  %s\n\n"
            "Le dejas?" % (len(fotos), carpeta, salida)):
        return "No me has dado permiso, no he hecho nada."
    try:
        ancho = max(400, min(4000, int(float(ancho))))
    except Exception:
        ancho = 1600
    try:
        doc = fitz.open()
        metidas = 0
        for f in fotos[:200]:
            try:
                with Image.open(f) as img:
                    img = img.convert("RGB")
                    if img.width > ancho:
                        img = img.resize((ancho, int(img.height * ancho / img.width)),
                                         Image.LANCZOS)
                    import io as _io
                    buf = _io.BytesIO()
                    img.save(buf, "JPEG", quality=85)
                    ancho_pag = A4[0] if img.width < img.height else A4[1]
                    alto_pag = A4[1] if img.width < img.height else A4[0]
                    pag = doc.new_page(width=ancho_pag, height=alto_pag)
                    caja = fitz.Rect(20, 20, ancho_pag - 20, alto_pag - 20)
                    pag.insert_image(caja, stream=buf.getvalue(), keep_proportion=True)
                    metidas += 1
            except Exception:
                pass
        if not metidas:
            return "No he podido meter ninguna foto."
        ruta = _sin_pisar(salida)
        doc.save(ruta)
        doc.close()
        return ("Hecho el PDF con %d fotos:\n%s\n\nAsi se lo puedes mandar a un "
                "cliente de una vez." % (metidas, ruta))
    except Exception as e:
        return "No he podido hacer el PDF: %s" % e
