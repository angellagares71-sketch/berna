# -*- coding: utf-8 -*-
"""Documentos, hojas de calculo, PDF, ZIP y archivos para Berna.

Las operaciones que escriben o mueven datos reciben ``permiso`` desde la
ventana principal. Las lecturas son libres. Nada escribe en carpetas del
sistema y las extracciones ZIP comprueban cada ruta antes de tocar el disco.
"""

import csv
import datetime
import difflib
import hashlib
import io
import json
import os
import re
import shutil
import textwrap
import zipfile


BASE_USUARIO = os.path.expanduser("~")
DOCUMENTOS = os.path.join(BASE_USUARIO, "Documents", "Documentos de Berna")
SISTEMA = tuple(os.path.abspath(p).lower() for p in (
    os.environ.get("WINDIR", r"C:\Windows"),
    os.environ.get("ProgramFiles", r"C:\Program Files"),
    os.environ.get("ProgramData", r"C:\ProgramData"),
) if p)


def _ruta(ruta):
    return os.path.abspath(os.path.expandvars(os.path.expanduser(str(ruta or ""))))


def _es_destino_seguro(ruta):
    r = _ruta(ruta).lower()
    return bool(r) and not any(r == p or r.startswith(p + os.sep) for p in SISTEMA)


def _nombre_seguro(nombre, defecto):
    nombre = re.sub(r'[<>:"/\\|?*]', "", str(nombre or "")).strip()
    return (nombre or defecto)[:90]


def _salida(salida, nombre, extension):
    if salida:
        ruta = _ruta(salida)
        if os.path.isdir(ruta):
            ruta = os.path.join(ruta, nombre + extension)
    else:
        ruta = os.path.join(DOCUMENTOS, nombre + extension)
    if not ruta.lower().endswith(extension):
        ruta += extension
    return ruta


def _permitido(permiso, mensaje):
    return permiso is not None and bool(permiso(mensaje))


def _preparar_salida(ruta):
    if not _es_destino_seguro(ruta):
        raise ValueError("esa es una carpeta del sistema y no voy a escribir ahi")
    os.makedirs(os.path.dirname(ruta), exist_ok=True)


def _copia_si_existe(ruta):
    if not os.path.isfile(ruta):
        return ""
    base, ext = os.path.splitext(ruta)
    copia = "%s.copia-%s%s" % (base, datetime.datetime.now().strftime("%Y%m%d-%H%M%S"), ext)
    shutil.copy2(ruta, copia)
    return copia


def _si(texto):
    return str(texto or "").strip().lower() in ("si", "s", "true", "1", "yes")


def _filas(datos):
    """Convierte JSON o texto con separadores en una tabla rectangular."""
    if isinstance(datos, (list, tuple)):
        bruto = datos
    else:
        texto = str(datos or "").strip()
        if not texto:
            return []
        try:
            bruto = json.loads(texto)
        except Exception:
            muestra = texto[:4096]
            candidatos = ["\t", "|", ";", ","]
            separador = max(candidatos, key=lambda s: muestra.count(s))
            bruto = list(csv.reader(io.StringIO(texto), delimiter=separador))

    if isinstance(bruto, dict):
        cabeceras = list(bruto)
        columnas = [v if isinstance(v, list) else [v] for v in bruto.values()]
        largo = max((len(v) for v in columnas), default=0)
        bruto = [cabeceras] + [[columnas[j][i] if i < len(columnas[j]) else ""
                               for j in range(len(columnas))]
                              for i in range(largo)]
    elif bruto and all(isinstance(x, dict) for x in bruto):
        cabeceras = []
        for fila in bruto:
            for clave in fila:
                if clave not in cabeceras:
                    cabeceras.append(clave)
        bruto = [cabeceras] + [[fila.get(c, "") for c in cabeceras] for fila in bruto]

    salida = []
    for fila in bruto:
        salida.append(list(fila) if isinstance(fila, (list, tuple)) else [fila])
    ancho = max((len(f) for f in salida), default=0)
    return [f + [""] * (ancho - len(f)) for f in salida]


def crear_documento_word(titulo, contenido, salida="", permiso=None):
    """Crea un DOCX cuidado a partir de texto sencillo o Markdown basico."""
    nombre = _nombre_seguro(titulo, "Documento")
    ruta = _salida(salida, nombre, ".docx")
    aviso = ("Berna quiere crear%s este documento Word:\n\n%s\n\nLe dejas?" %
             (" o reemplazar" if os.path.exists(ruta) else "", ruta))
    if not _permitido(permiso, aviso):
        return "No me has dado permiso, no he creado el documento."
    try:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Cm, Pt

        _preparar_salida(ruta)
        copia = _copia_si_existe(ruta)
        doc = Document()
        sec = doc.sections[0]
        sec.top_margin = sec.bottom_margin = Cm(2.2)
        sec.left_margin = sec.right_margin = Cm(2.4)
        normal = doc.styles["Normal"]
        normal.font.name = "Aptos"
        normal.font.size = Pt(11)
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(str(titulo).strip())
        run.bold = True
        run.font.size = Pt(20)

        for linea in str(contenido or "").splitlines():
            t = linea.strip()
            if not t:
                doc.add_paragraph()
            elif t.startswith("### "):
                doc.add_heading(t[4:], level=3)
            elif t.startswith("## "):
                doc.add_heading(t[3:], level=2)
            elif t.startswith("# "):
                doc.add_heading(t[2:], level=1)
            elif re.match(r"^[-*]\s+", t):
                doc.add_paragraph(re.sub(r"^[-*]\s+", "", t), style="List Bullet")
            elif re.match(r"^\d+[.)]\s+", t):
                doc.add_paragraph(re.sub(r"^\d+[.)]\s+", "", t), style="List Number")
            else:
                doc.add_paragraph(linea)
        doc.core_properties.title = str(titulo)
        doc.core_properties.author = "Berna"
        doc.save(ruta)
        return "Documento Word creado: %s%s" % (ruta, "\nCopia anterior: " + copia if copia else "")
    except Exception as e:
        return "No he podido crear el Word: %s" % e


def crear_hoja_excel(nombre, datos, salida="", hoja="Datos",
                     permitir_formulas="no", permiso=None):
    """Crea un XLSX con cabecera, filtro, panel fijo y columnas ajustadas."""
    filas = _filas(datos)
    if not filas:
        return "No me has dado ningun dato para la hoja."
    nombre_limpio = _nombre_seguro(nombre, "Hoja de calculo")
    ruta = _salida(salida, nombre_limpio, ".xlsx")
    if not _permitido(permiso, "Berna quiere crear una hoja de calculo con %d filas:\n\n%s\n\nLe dejas?" % (len(filas), ruta)):
        return "No me has dado permiso, no he creado la hoja."
    try:
        import openpyxl
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter

        _preparar_salida(ruta)
        copia = _copia_si_existe(ruta)
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = _nombre_seguro(hoja, "Datos")[:31]
        formulas = _si(permitir_formulas)
        for fila in filas:
            limpia = []
            for valor in fila:
                if isinstance(valor, str) and valor.startswith(("=", "+", "-", "@")) and not formulas:
                    valor = "'" + valor
                limpia.append(valor)
            ws.append(limpia)
        for celda in ws[1]:
            celda.font = Font(bold=True, color="FFFFFF")
            celda.fill = PatternFill("solid", fgColor="4F46E5")
            celda.alignment = Alignment(horizontal="center")
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for columna in range(1, ws.max_column + 1):
            ancho = max(len(str(ws.cell(f, columna).value or ""))
                        for f in range(1, min(ws.max_row, 300) + 1))
            ws.column_dimensions[get_column_letter(columna)].width = min(55, max(10, ancho + 2))
        wb.save(ruta)
        return "Hoja de calculo creada: %s (%d filas, %d columnas)%s" % (
            ruta, ws.max_row, ws.max_column, "\nCopia anterior: " + copia if copia else "")
    except Exception as e:
        return "No he podido crear la hoja: %s" % e


def actualizar_celda_excel(ruta, celda, valor, hoja="", permiso=None):
    ruta = _ruta(ruta)
    if not os.path.isfile(ruta):
        return "No existe la hoja %s" % ruta
    if not re.match(r"^[A-Za-z]{1,3}[1-9][0-9]{0,6}$", str(celda or "").strip()):
        return "La celda no es valida. Dime algo como A1, B7 o AA20."
    aviso = "Berna quiere cambiar %s%s en:\n\n%s\n\nGuardara una copia anterior. Le dejas?" % (
        celda.upper(), " de la hoja " + hoja if hoja else "", ruta)
    if not _permitido(permiso, aviso):
        return "No me has dado permiso, no he cambiado la hoja."
    try:
        import openpyxl
        copia = _copia_si_existe(ruta)
        wb = openpyxl.load_workbook(ruta)
        ws = wb[hoja] if hoja and hoja in wb.sheetnames else wb[wb.sheetnames[0]]
        anterior = ws[celda.upper()].value
        ws[celda.upper()] = valor
        wb.save(ruta)
        return "Actualizado %s!%s: %r -> %r\nCopia anterior: %s" % (
            ws.title, celda.upper(), anterior, valor, copia)
    except Exception as e:
        return "No he podido actualizar la hoja: %s" % e


def crear_pdf_texto(titulo, contenido, salida="", permiso=None):
    nombre = _nombre_seguro(titulo, "Documento")
    ruta = _salida(salida, nombre, ".pdf")
    if not _permitido(permiso, "Berna quiere crear este PDF:\n\n%s\n\nLe dejas?" % ruta):
        return "No me has dado permiso, no he creado el PDF."
    try:
        import pymupdf as fitz
        _preparar_salida(ruta)
        copia = _copia_si_existe(ruta)
        doc = fitz.open()
        lineas = []
        for parrafo in str(contenido or "").splitlines():
            lineas.extend(textwrap.wrap(parrafo, width=92, replace_whitespace=False) or [""])
        pendientes = lineas or [""]
        primera = True
        while pendientes:
            pagina = doc.new_page(width=595, height=842)
            y = 62
            if primera:
                pagina.insert_text((55, y), str(titulo)[:120], fontsize=18, fontname="helv")
                y += 36
                primera = False
            caben = max(1, int((790 - y) / 15))
            bloque, pendientes = pendientes[:caben], pendientes[caben:]
            pagina.insert_textbox(fitz.Rect(55, y, 540, 790), "\n".join(bloque),
                                  fontsize=10.5, fontname="helv", lineheight=1.35)
        doc.set_metadata({"title": str(titulo), "author": "Berna"})
        doc.save(ruta)
        paginas = doc.page_count
        doc.close()
        return "PDF creado: %s (%d paginas)%s" % (ruta, paginas, "\nCopia anterior: " + copia if copia else "")
    except Exception as e:
        return "No he podido crear el PDF: %s" % e


def _numeros_paginas(texto, total):
    numeros = []
    for parte in re.split(r"[,;\s]+", str(texto or "").strip()):
        if not parte:
            continue
        if "-" in parte:
            a, b = parte.split("-", 1)
            a, b = int(a), int(b)
            numeros.extend(range(min(a, b), max(a, b) + 1))
        else:
            numeros.append(int(parte))
    numeros = list(dict.fromkeys(numeros))
    if not numeros or any(n < 1 or n > total for n in numeros):
        raise ValueError("las paginas deben estar entre 1 y %d" % total)
    return numeros


def extraer_paginas_pdf(ruta, paginas, salida="", permiso=None):
    ruta = _ruta(ruta)
    if not os.path.isfile(ruta):
        return "No existe el PDF %s" % ruta
    try:
        from pypdf import PdfReader, PdfWriter
        lector = PdfReader(ruta)
        numeros = _numeros_paginas(paginas, len(lector.pages))
        nombre = _nombre_seguro(os.path.splitext(os.path.basename(ruta))[0] + " paginas", "Paginas")
        destino = _salida(salida, nombre, ".pdf")
        if not _permitido(permiso, "Berna quiere sacar las paginas %s de:\n%s\n\ny guardarlas en:\n%s\n\nLe dejas?" % (", ".join(map(str, numeros)), ruta, destino)):
            return "No me has dado permiso, no he extraido paginas."
        _preparar_salida(destino)
        copia = _copia_si_existe(destino)
        escritor = PdfWriter()
        for n in numeros:
            escritor.add_page(lector.pages[n - 1])
        with open(destino, "wb") as f:
            escritor.write(f)
        return "PDF creado con %d paginas: %s%s" % (
            len(numeros), destino, "\nCopia anterior: " + copia if copia else "")
    except Exception as e:
        return "No he podido extraer las paginas: %s" % e


def dividir_pdf(ruta, destino="", permiso=None):
    ruta = _ruta(ruta)
    if not os.path.isfile(ruta):
        return "No existe el PDF %s" % ruta
    try:
        from pypdf import PdfReader, PdfWriter
        lector = PdfReader(ruta)
        carpeta = _ruta(destino) if destino else os.path.join(
            os.path.dirname(ruta), os.path.splitext(os.path.basename(ruta))[0] + " - paginas")
        if not _es_destino_seguro(carpeta):
            return "No voy a escribir en una carpeta del sistema."
        if not _permitido(permiso, "Berna quiere dividir este PDF en %d archivos:\n\n%s\n\nDestino: %s\n\nLe dejas?" % (len(lector.pages), ruta, carpeta)):
            return "No me has dado permiso, no he dividido nada."
        os.makedirs(carpeta, exist_ok=True)
        base = _nombre_seguro(os.path.splitext(os.path.basename(ruta))[0], "pagina")
        for i, pagina in enumerate(lector.pages, 1):
            escritor = PdfWriter()
            escritor.add_page(pagina)
            with open(os.path.join(carpeta, "%s - %03d.pdf" % (base, i)), "wb") as f:
                escritor.write(f)
        return "PDF dividido en %d archivos dentro de %s" % (len(lector.pages), carpeta)
    except Exception as e:
        return "No he podido dividir el PDF: %s" % e


def _lista_rutas(rutas):
    if isinstance(rutas, (list, tuple)):
        partes = rutas
    else:
        texto = str(rutas or "").strip()
        try:
            partes = json.loads(texto)
            if not isinstance(partes, list):
                partes = [texto]
        except Exception:
            partes = re.split(r"[\r\n;]+", texto)
    return [_ruta(p) for p in partes if str(p).strip()]


def crear_zip(rutas, salida="", permiso=None):
    entradas = _lista_rutas(rutas)
    inexistentes = [p for p in entradas if not os.path.exists(p)]
    if not entradas or inexistentes:
        return "No encuentro: %s" % (", ".join(inexistentes) if inexistentes else "ningun archivo")
    nombre = _nombre_seguro(os.path.basename(entradas[0]), "Archivos")
    destino = _salida(salida, nombre, ".zip")
    archivos = []
    for entrada in entradas:
        if os.path.isfile(entrada):
            archivos.append((entrada, os.path.basename(entrada)))
        else:
            padre = os.path.dirname(entrada)
            for raiz, dirs, ficheros in os.walk(entrada):
                dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(raiz, d))]
                for fichero in ficheros:
                    p = os.path.join(raiz, fichero)
                    if not os.path.islink(p):
                        archivos.append((p, os.path.relpath(p, padre)))
                if len(archivos) > 20000:
                    return "Hay mas de 20.000 archivos. Divide la copia en varias partes."
    tamano = sum(os.path.getsize(p) for p, _ in archivos)
    if not _permitido(permiso, "Berna quiere comprimir %d archivos (%.1f MB) en:\n\n%s\n\nLe dejas?" % (len(archivos), tamano / 1048576, destino)):
        return "No me has dado permiso, no he creado el ZIP."
    try:
        _preparar_salida(destino)
        copia = _copia_si_existe(destino)
        with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for origen, dentro in archivos:
                z.write(origen, dentro)
        return "ZIP creado: %s (%d archivos, %.1f MB)%s" % (
            destino, len(archivos), os.path.getsize(destino) / 1048576,
            "\nCopia anterior: " + copia if copia else "")
    except Exception as e:
        return "No he podido crear el ZIP: %s" % e


def extraer_zip(ruta, destino="", permiso=None):
    ruta = _ruta(ruta)
    if not zipfile.is_zipfile(ruta):
        return "No es un ZIP valido: %s" % ruta
    carpeta = _ruta(destino) if destino else os.path.splitext(ruta)[0]
    if not _es_destino_seguro(carpeta):
        return "No voy a extraer nada dentro de una carpeta del sistema."
    try:
        with zipfile.ZipFile(ruta) as z:
            infos = z.infolist()
            if len(infos) > 20000:
                return "El ZIP tiene mas de 20.000 elementos y no lo abro de golpe."
            total = sum(i.file_size for i in infos)
            if total > 5 * 1024**3:
                return "El ZIP ocuparia mas de 5 GB al abrirse. No lo extraigo de golpe."
            base = os.path.normcase(os.path.abspath(carpeta)) + os.sep
            for info in infos:
                nombre = info.filename.replace("/", os.sep)
                objetivo = os.path.normcase(os.path.abspath(os.path.join(carpeta, nombre)))
                modo = (info.external_attr >> 16) & 0o170000
                if (not objetivo.startswith(base) or ":" in nombre or modo == 0o120000):
                    return "El ZIP contiene una ruta peligrosa y no lo voy a extraer: %s" % info.filename
            if not _permitido(permiso, "Berna quiere extraer %d elementos (%.1f MB) de:\n%s\n\nen:\n%s\n\nLe dejas?" % (len(infos), total / 1048576, ruta, carpeta)):
                return "No me has dado permiso, no he extraido el ZIP."
            os.makedirs(carpeta, exist_ok=True)
            for info in infos:
                objetivo = os.path.abspath(os.path.join(carpeta, info.filename.replace("/", os.sep)))
                if info.is_dir():
                    os.makedirs(objetivo, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(objetivo), exist_ok=True)
                    with z.open(info) as origen, open(objetivo, "wb") as salida:
                        shutil.copyfileobj(origen, salida, 1024 * 1024)
        return "ZIP extraido: %d elementos en %s" % (len(infos), carpeta)
    except Exception as e:
        return "No he podido extraer el ZIP: %s" % e


def copiar_archivo_o_carpeta(origen, destino, permiso=None):
    origen, destino = _ruta(origen), _ruta(destino)
    if not os.path.exists(origen):
        return "No existe %s" % origen
    if os.path.isdir(destino):
        destino = os.path.join(destino, os.path.basename(origen))
    if not _es_destino_seguro(destino):
        return "No voy a copiar dentro de una carpeta del sistema."
    if os.path.isdir(origen) and os.path.exists(destino):
        return "La carpeta de destino ya existe. Dime otro nombre para no mezclar datos."
    if not _permitido(permiso, "Berna quiere copiar:\n%s\n\na:\n%s\n\nLe dejas?" % (origen, destino)):
        return "No me has dado permiso, no he copiado nada."
    try:
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        if os.path.isdir(origen):
            shutil.copytree(origen, destino)
        else:
            copia = _copia_si_existe(destino)
            shutil.copy2(origen, destino)
            if copia:
                return "Copiado en %s\nCopia anterior: %s" % (destino, copia)
        return "Copiado correctamente en %s" % destino
    except Exception as e:
        return "No he podido copiar: %s" % e


def mover_archivo_o_carpeta(origen, destino, permiso=None):
    origen, destino = _ruta(origen), _ruta(destino)
    if not os.path.exists(origen):
        return "No existe %s" % origen
    if os.path.isdir(destino):
        destino = os.path.join(destino, os.path.basename(origen))
    if os.path.exists(destino):
        return "El destino ya existe. No voy a sobrescribirlo al mover."
    if not _es_destino_seguro(destino):
        return "No voy a mover nada dentro de una carpeta del sistema."
    if not _permitido(permiso, "Berna quiere MOVER:\n%s\n\na:\n%s\n\nEl original cambiara de sitio. Le dejas?" % (origen, destino)):
        return "No me has dado permiso, no he movido nada."
    try:
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        shutil.move(origen, destino)
        return "Movido correctamente a %s" % destino
    except Exception as e:
        return "No he podido moverlo: %s" % e


def crear_carpeta(ruta, permiso=None):
    ruta = _ruta(ruta)
    if os.path.isdir(ruta):
        return "La carpeta ya existe: %s" % ruta
    if not _es_destino_seguro(ruta):
        return "No voy a crear carpetas dentro del sistema."
    if not _permitido(permiso, "Berna quiere crear esta carpeta:\n\n%s\n\nLe dejas?" % ruta):
        return "No me has dado permiso, no he creado la carpeta."
    try:
        os.makedirs(ruta)
        return "Carpeta creada: %s" % ruta
    except Exception as e:
        return "No he podido crear la carpeta: %s" % e


def _hash(ruta):
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()


def informacion_archivo(ruta):
    ruta = _ruta(ruta)
    if not os.path.exists(ruta):
        return "No existe %s" % ruta
    try:
        if os.path.isfile(ruta):
            st = os.stat(ruta)
            return ("Archivo: %s\nTamano: %.2f MB (%d bytes)\nModificado: %s\nSHA-256: %s" %
                    (ruta, st.st_size / 1048576, st.st_size,
                     datetime.datetime.fromtimestamp(st.st_mtime).strftime("%d/%m/%Y %H:%M:%S"),
                     _hash(ruta)))
        cantidad = 0
        tamano = 0
        for raiz, dirs, files in os.walk(ruta):
            dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(raiz, d))]
            for nombre in files:
                p = os.path.join(raiz, nombre)
                try:
                    cantidad += 1
                    tamano += os.path.getsize(p)
                except OSError:
                    pass
        return "Carpeta: %s\nArchivos: %d\nTamano total: %.2f MB" % (ruta, cantidad, tamano / 1048576)
    except Exception as e:
        return "No he podido revisar la ruta: %s" % e


def buscar_duplicados(carpeta, max_archivos=5000):
    carpeta = _ruta(carpeta)
    if not os.path.isdir(carpeta):
        return "No existe la carpeta %s" % carpeta
    try:
        limite = max(100, min(20000, int(max_archivos)))
    except Exception:
        limite = 5000
    por_tamano = {}
    vistos = 0
    for raiz, dirs, files in os.walk(carpeta):
        dirs[:] = [d for d in dirs if d not in ("venv", "node_modules", ".git", "__pycache__")]
        for nombre in files:
            p = os.path.join(raiz, nombre)
            try:
                por_tamano.setdefault(os.path.getsize(p), []).append(p)
                vistos += 1
            except OSError:
                pass
            if vistos >= limite:
                break
        if vistos >= limite:
            break
    grupos = []
    for tamano, candidatos in por_tamano.items():
        if len(candidatos) < 2 or tamano == 0:
            continue
        hashes = {}
        for p in candidatos:
            try:
                hashes.setdefault(_hash(p), []).append(p)
            except OSError:
                pass
        grupos.extend((tamano, rutas) for rutas in hashes.values() if len(rutas) > 1)
    if not grupos:
        return "No he encontrado archivos duplicados entre los %d revisados." % vistos
    grupos.sort(key=lambda x: x[0] * (len(x[1]) - 1), reverse=True)
    lineas = ["Duplicados exactos encontrados (no he borrado nada):"]
    recuperable = 0
    for i, (tamano, rutas) in enumerate(grupos[:30], 1):
        recuperable += tamano * (len(rutas) - 1)
        lineas.append("\n%d. %.2f MB, %d copias\n   %s" %
                      (i, tamano / 1048576, len(rutas), "\n   ".join(rutas)))
    lineas.append("\nEspacio repetido mostrado: %.2f MB." % (recuperable / 1048576))
    return "\n".join(lineas)


def comparar_archivos(primero, segundo, max_lineas=120):
    a, b = _ruta(primero), _ruta(segundo)
    if not os.path.isfile(a) or not os.path.isfile(b):
        return "Necesito dos archivos que existan."
    ha, hb = _hash(a), _hash(b)
    if ha == hb:
        return "Los dos archivos son exactamente iguales (SHA-256 %s)." % ha
    extensiones = (".txt", ".md", ".csv", ".json", ".xml", ".ini", ".py", ".bat", ".ps1")
    if os.path.splitext(a)[1].lower() not in extensiones or os.path.splitext(b)[1].lower() not in extensiones:
        return "Los archivos son distintos.\n%s: %s\n%s: %s" % (a, ha, b, hb)
    try:
        with open(a, encoding="utf-8", errors="replace") as f:
            la = f.readlines()
        with open(b, encoding="utf-8", errors="replace") as f:
            lb = f.readlines()
        limite = max(20, min(500, int(max_lineas)))
        diff = list(difflib.unified_diff(la, lb, fromfile=a, tofile=b, n=3))
        corte = "".join(diff[:limite])
        if len(diff) > limite:
            corte += "\n[...diferencias recortadas...]"
        return "Los archivos son distintos:\n\n%s" % corte
    except Exception as e:
        return "Los archivos son distintos, pero no he podido comparar el texto: %s" % e
