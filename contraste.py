# -*- coding: utf-8 -*-
"""Segundo parecer local, solo para preguntas que merecen contraste."""

import re


def conviene(texto):
    import cerebro
    t = str(texto or "").lower()
    if cerebro.pide_accion(t):
        return False
    return (len(t) > 180 or bool(re.search(
        r"\b(compara|analiza|investiga|explica|recomienda|conviene|"
        r"verifica|contrasta|diferencia|por que)\b", t)))


def cabe_en_memoria():
    try:
        import psutil
        return psutil.virtual_memory().available >= 4 * 1024 ** 3
    except Exception:
        return False


def segundo_parecer(pregunta):
    """Sin herramientas ni servicios externos; devuelve vacio si tarda/falla."""
    import requests
    try:
        r = requests.post("http://127.0.0.1:11434/api/chat", json={
            "model": "qwen3.5:2b", "stream": False, "think": False,
            "keep_alive": 0, "options": {"num_ctx": 2048, "num_predict": 300},
            "messages": [
                {"role": "system", "content": "Da un segundo parecer independiente y "
                 "breve en espanol. Señala incertidumbre y no inventes fuentes."},
                {"role": "user", "content": str(pregunta)[:1000]}]},
            timeout=(3, 55))
        if r.status_code == 200:
            return str((r.json().get("message") or {}).get("content") or "")[:1200]
    except Exception:
        pass
    return ""
