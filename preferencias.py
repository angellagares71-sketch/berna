# -*- coding: utf-8 -*-
"""Permisos persistentes del dueño para tareas rutinarias de Sobri.

Se guardan solo en config.json, que nunca se publica ni viaja en una actualización.
La ausencia de un permiso equivale a no tenerlo.
"""

import json
import os

from persistencia import actualizar_json_atomico

CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
DESCARGAS = "descargas_sin_confirmacion"
PROGRAMAS = "abrir_programas_sin_confirmacion"
_CLAVES = {DESCARGAS, PROGRAMAS}


def activada(clave):
    if clave not in _CLAVES:
        return False
    try:
        with open(CONFIG, "r", encoding="utf-8") as f:
            return json.load(f).get(clave) is True
    except (OSError, ValueError, AttributeError):
        return False


def permisos_automaticos():
    """Cuenta solo estas preferencias, sin mostrar otras claves del config."""
    return ("Descargas de Internet sin preguntar: %s. "
            "Abrir aplicaciones instaladas sin preguntar: %s. "
            "Instalar programas y ejecutar ordenes siguen necesitando permiso."
            % ("si" if activada(DESCARGAS) else "no",
               "si" if activada(PROGRAMAS) else "no"))


def configurar_permisos_automaticos(descargas=None, programas=None, permiso=None):
    """Cambia las dos autorizaciones, conservando todos los demas ajustes."""
    cambios = {}
    for clave, valor in ((DESCARGAS, descargas), (PROGRAMAS, programas)):
        if valor is None:
            continue
        if not isinstance(valor, bool):
            return "No he cambiado nada: los permisos deben ser si o no."
        cambios[clave] = valor
    if not cambios:
        return permisos_automaticos()
    resumen = "; ".join("%s: %s" %
                        ("descargas" if clave == DESCARGAS else "abrir aplicaciones",
                         "permitir sin preguntar" if valor else "volver a preguntar")
                        for clave, valor in cambios.items())
    aviso = ("Sobri va a guardar estos permisos en este ordenador: %s. "
             "No cambia los permisos de otros usuarios. Le dejas?" % resumen)
    if permiso is None or not permiso(aviso):
        return "No me han dado permiso; no he cambiado los ajustes."
    try:
        actualizar_json_atomico(CONFIG, cambios, crear=True)
    except Exception as e:
        return "No he podido guardar los permisos: %s" % str(e)[:180]
    return "Permisos guardados. " + permisos_automaticos()
