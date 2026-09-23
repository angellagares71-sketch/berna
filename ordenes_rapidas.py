# -*- coding: utf-8 -*-
"""Ordenes inequívocas que se resuelven localmente sin esperar a un modelo."""

import re
import unicodedata


def _normalizar(texto):
    t = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").strip(" .?¿!¡")


def responder(texto):
    t = _normalizar(str(texto or ""))
    if t in {"que hora es", "dime la hora", "que dia es hoy", "dime la fecha",
             "que fecha es hoy"}:
        import herramientas
        return herramientas.hora_y_fecha()
    if re.fullmatch(r"(?:quita|borra|retira) (?:la )?marca(?: de la pantalla)?", t):
        import marcas
        return marcas.quitar_marca()
    m = re.fullmatch(r"(?:marca|senala)\s+(.+)", t)
    if m:
        import marcas
        objetivo = m.group(1).strip()
        color = "rojo"
        cm = re.search(r"\s+en\s+(rojo|verde|azul|amarillo|naranja)$", objetivo)
        if cm:
            color = cm.group(1)
            objetivo = objetivo[:cm.start()].strip()
        if objetivo in {"aqui", "ahi", "donde esta el raton", "el raton"}:
            objetivo = ""
        return marcas.marcar_en_pantalla(objetivo, color=color)
    m = re.fullmatch(r"(?:calcula|cuanto es|dime cuanto es)\s+(.+)", t)
    if m:
        expresion = m.group(1)
        for palabra, signo in (("multiplicado por", "*"), ("dividido entre", "/"),
                               ("por", "*"), ("entre", "/"), ("mas", "+"),
                               ("menos", "-")):
            expresion = re.sub(r"\b" + palabra + r"\b", signo, expresion)
        if re.fullmatch(r"[\d\s.,()+*/%\-]+", expresion) and len(expresion) < 80:
            import herramientas
            return herramientas.calcular(expresion.replace(",", "."))
    return None
