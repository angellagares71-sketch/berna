# -*- coding: utf-8 -*-
"""Encuentra texto visible con OCR local cuando Windows no publica controles."""

import csv
import io
import os
import re
import subprocess
import unicodedata

BASE = os.path.dirname(os.path.abspath(__file__))
TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
DATOS = os.path.join(BASE, "modelos", "tessdata")


def _limpio(texto):
    t = unicodedata.normalize("NFD", str(texto or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return " ".join(re.findall(r"[a-z0-9]+", t))


def localizar_texto(objetivo, imagen=None, origen=None):
    """(x,y,descripcion) o (None,None,motivo). No guarda ni envia capturas."""
    if not os.path.exists(TESSERACT) or not os.path.exists(os.path.join(DATOS, "spa.traineddata")):
        return None, None, "OCR local no instalado"
    palabras = [p for p in _limpio(objetivo).split()
                if p not in {"boton", "el", "la", "de", "del", "un", "una",
                             "enlace", "icono", "texto", "que", "dice"}]
    buscado = " ".join(palabras)
    if len(buscado) < 3:
        return None, None, "nombre demasiado corto para OCR"
    if imagen is None:
        from PIL import ImageGrab
        import manos
        imagen = ImageGrab.grab(all_screens=True)
        vx, vy, _, _ = manos._pantalla_fisica()
        origen = (vx, vy)
    origen = origen or (0, 0)
    buf = io.BytesIO()
    imagen.save(buf, format="PNG")
    try:
        r = subprocess.run(
            [TESSERACT, "stdin", "stdout", "--tessdata-dir", DATOS,
             "-l", "spa+eng", "--psm", "11",
             "-c", "tessedit_create_tsv=1"],
            input=buf.getvalue(), capture_output=True, timeout=12,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, None, "OCR local no ha respondido: %s" % str(e)[:80]
    if r.returncode:
        return None, None, "OCR local no pudo leer la pantalla"
    grupos = {}
    for fila in csv.DictReader(io.StringIO(r.stdout.decode("utf-8", "replace")),
                               delimiter="\t"):
        palabra = (fila.get("text") or "").strip()
        if not palabra:
            continue
        try:
            conf = float(fila.get("conf", "-1"))
            if conf < 45:
                continue
            clave = tuple(fila[k] for k in ("block_num", "par_num", "line_num"))
            grupos.setdefault(clave, []).append((palabra, int(fila["left"]),
                int(fila["top"]), int(fila["width"]), int(fila["height"])))
        except (ValueError, KeyError):
            continue
    candidatas = []
    for palabras_linea in grupos.values():
        contenido = _limpio(" ".join(p[0] for p in palabras_linea))
        if buscado not in contenido:
            continue
        izquierda = min(p[1] for p in palabras_linea)
        arriba = min(p[2] for p in palabras_linea)
        derecha = max(p[1] + p[3] for p in palabras_linea)
        abajo = max(p[2] + p[4] for p in palabras_linea)
        candidatas.append((origen[0] + (izquierda + derecha) // 2,
                           origen[1] + (arriba + abajo) // 2, contenido))
    if len(candidatas) == 1:
        x, y, texto = candidatas[0]
        return x, y, "texto '%s' (OCR local)" % texto[:70]
    if len(candidatas) > 1:
        return None, None, "hay varios textos que coinciden; concreta cual"
    return None, None, "no se ha encontrado ese texto con OCR local"
