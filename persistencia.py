# -*- coding: utf-8 -*-
"""Escrituras resistentes para los datos que Berna no puede perder.

Los JSON de configuracion, memoria y recordatorios se escribian directamente
o mediante un unico ``.tmp`` compartido. Si dos partes de Berna guardaban a la
vez, o Windows cortaba el proceso a mitad, se podia perder el fichero bueno.

Este modulo escribe primero un temporal unico en la misma carpeta, fuerza los
bytes al disco y solo entonces sustituye el destino. El cambio es atomico: se
ve el archivo anterior entero o el nuevo entero, nunca medio JSON.
"""

import json
import os
import tempfile
import threading
import time
from contextlib import contextmanager


_CANDADO_HILO = threading.RLock()


@contextmanager
def _candado_archivo(ruta, espera=5.0):
    """Exclusion mutua entre la ventana y el servidor movil."""
    bloqueo = os.path.abspath(ruta) + ".lock"
    os.makedirs(os.path.dirname(bloqueo) or ".", exist_ok=True)
    with _CANDADO_HILO:
        with open(bloqueo, "a+b") as f:
            f.seek(0, os.SEEK_END)
            if f.tell() == 0:
                f.write(b"0")
                f.flush()
            f.seek(0)
            if os.name == "nt":
                import msvcrt
                limite = time.monotonic() + espera
                while True:
                    try:
                        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        if time.monotonic() >= limite:
                            raise TimeoutError("otro proceso sigue guardando " + ruta)
                        time.sleep(0.05)
                try:
                    yield
                finally:
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def escribir_bytes_atomico(ruta, datos):
    """Sustituye ``ruta`` de una sola vez y conserva sus permisos."""
    ruta = os.path.abspath(ruta)
    carpeta = os.path.dirname(ruta) or "."
    os.makedirs(carpeta, exist_ok=True)
    temporal = None
    permisos = None
    try:
        if os.path.exists(ruta):
            permisos = os.stat(ruta).st_mode
        with tempfile.NamedTemporaryFile(
                mode="wb", prefix=".%s." % os.path.basename(ruta),
                suffix=".tmp", dir=carpeta, delete=False) as f:
            temporal = f.name
            f.write(datos)
            f.flush()
            os.fsync(f.fileno())
        if permisos is not None:
            os.chmod(temporal, permisos)
        os.replace(temporal, ruta)
        temporal = None
    finally:
        if temporal and os.path.exists(temporal):
            try:
                os.remove(temporal)
            except OSError:
                pass


def escribir_texto_atomico(ruta, texto, encoding="utf-8"):
    escribir_bytes_atomico(ruta, str(texto).encode(encoding))


def _guardar_json_sin_bloqueo(ruta, datos, indent=2):
    texto = json.dumps(datos, indent=indent, ensure_ascii=False) + "\n"
    escribir_texto_atomico(ruta, texto)


def guardar_json_atomico(ruta, datos, indent=2):
    with _candado_archivo(str(ruta)):
        _guardar_json_sin_bloqueo(ruta, datos, indent)


def actualizar_json_atomico(ruta, cambios, indent=2, crear=False):
    """Mezcla solo los campos indicados con el JSON mas reciente del disco."""
    with _candado_archivo(str(ruta)):
        if os.path.exists(ruta):
            with open(ruta, "r", encoding="utf-8") as f:
                datos = json.load(f)
            if not isinstance(datos, dict):
                raise ValueError("el JSON existente no es un objeto")
        elif crear:
            datos = {}
        else:
            raise FileNotFoundError(ruta)
        datos.update(dict(cambios))
        _guardar_json_sin_bloqueo(ruta, datos, indent)
        return datos
