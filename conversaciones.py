# -*- coding: utf-8 -*-
"""Archivo local de conversaciones e intentos. SQLite permite buscar sin
mandar el historial completo al proveedor del modelo."""

import datetime as dt
import json
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager

BASE = os.path.dirname(os.path.abspath(__file__))
RUTA = os.path.join(BASE, "conversaciones.sqlite3")
VACIAS = {"angel", "sobri", "quiero", "puedes", "hacer", "ahora", "esto",
          "esta", "para", "como", "donde", "cuando", "tengo", "dime", "hace"}


def nueva_sesion():
    return uuid.uuid4().hex


@contextmanager
def _abrir():
    con = sqlite3.connect(RUTA, timeout=10)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=10000")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS mensajes (
            id INTEGER PRIMARY KEY, sesion TEXT NOT NULL, fecha TEXT NOT NULL,
            papel TEXT NOT NULL, contenido TEXT NOT NULL);
        CREATE VIRTUAL TABLE IF NOT EXISTS mensajes_busca USING fts5(
            contenido, content='mensajes', content_rowid='id', tokenize='unicode61');
        CREATE TRIGGER IF NOT EXISTS mensajes_ai AFTER INSERT ON mensajes BEGIN
            INSERT INTO mensajes_busca(rowid, contenido) VALUES (new.id, new.contenido);
        END;
        CREATE TRIGGER IF NOT EXISTS mensajes_ad AFTER DELETE ON mensajes BEGIN
            INSERT INTO mensajes_busca(mensajes_busca, rowid, contenido)
            VALUES ('delete', old.id, old.contenido);
        END;
        CREATE TABLE IF NOT EXISTS episodios (
            id INTEGER PRIMARY KEY, sesion TEXT NOT NULL, fecha TEXT NOT NULL,
            objetivo TEXT NOT NULL, contexto TEXT NOT NULL DEFAULT '',
            estado TEXT NOT NULL DEFAULT 'en_curso',
            resultado TEXT NOT NULL DEFAULT '', verificado INTEGER NOT NULL DEFAULT 0);
        CREATE VIRTUAL TABLE IF NOT EXISTS episodios_busca USING fts5(
            objetivo, resultado, content='episodios', content_rowid='id', tokenize='unicode61');
        CREATE TRIGGER IF NOT EXISTS episodios_ai AFTER INSERT ON episodios BEGIN
            INSERT INTO episodios_busca(rowid, objetivo, resultado)
            VALUES (new.id, new.objetivo, new.resultado);
        END;
        CREATE TRIGGER IF NOT EXISTS episodios_au AFTER UPDATE ON episodios BEGIN
            INSERT INTO episodios_busca(episodios_busca, rowid, objetivo, resultado)
            VALUES ('delete', old.id, old.objetivo, old.resultado);
            INSERT INTO episodios_busca(rowid, objetivo, resultado)
            VALUES (new.id, new.objetivo, new.resultado);
        END;
        CREATE TRIGGER IF NOT EXISTS episodios_ad AFTER DELETE ON episodios BEGIN
            INSERT INTO episodios_busca(episodios_busca, rowid, objetivo, resultado)
            VALUES ('delete', old.id, old.objetivo, old.resultado);
        END;
        CREATE TABLE IF NOT EXISTS pasos (
            id INTEGER PRIMARY KEY, episodio_id INTEGER NOT NULL, orden INTEGER NOT NULL,
            herramienta TEXT NOT NULL, argumentos TEXT NOT NULL,
            resultado TEXT NOT NULL, estado TEXT NOT NULL,
            FOREIGN KEY(episodio_id) REFERENCES episodios(id) ON DELETE CASCADE);
    """)
    con.execute("PRAGMA foreign_keys=ON")
    try:
        with con:
            yield con
    finally:
        con.close()


def _fecha():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def registrar_mensaje(sesion, papel, contenido):
    if papel not in ("user", "assistant"):
        return
    with _abrir() as con:
        con.execute("INSERT INTO mensajes(sesion,fecha,papel,contenido) VALUES (?,?,?,?)",
                    (sesion, _fecha(), papel, str(contenido)))


def iniciar_episodio(sesion, objetivo, contexto=""):
    with _abrir() as con:
        cur = con.execute("INSERT INTO episodios(sesion,fecha,objetivo,contexto) "
                          "VALUES (?,?,?,?)", (sesion, _fecha(), str(objetivo), str(contexto)))
        return cur.lastrowid


def registrar_paso(episodio_id, herramienta, argumentos, resultado):
    if episodio_id is None:
        return
    salida = str(resultado)
    fallo = bool(re.search(r"(?:^|\n)(?:ERROR|Error|No he podido|La herramienta .* ha fallado)",
                           salida[:800]))
    with _abrir() as con:
        orden = con.execute("SELECT COUNT(*) FROM pasos WHERE episodio_id=?",
                            (episodio_id,)).fetchone()[0] + 1
        con.execute("INSERT INTO pasos(episodio_id,orden,herramienta,argumentos,resultado,estado) "
                    "VALUES (?,?,?,?,?,?)",
                    (episodio_id, orden, herramienta,
                     json.dumps(argumentos, ensure_ascii=False)[:3000], salida[:4000],
                     "fallo" if fallo else "informado"))


def terminar_episodio(episodio_id, estado, resultado, verificado=False):
    if episodio_id is None:
        return
    with _abrir() as con:
        con.execute("UPDATE episodios SET estado=?,resultado=?,verificado=? WHERE id=?",
                    (estado, str(resultado)[:4000], int(verificado), episodio_id))


def _consulta(texto):
    palabras = [p for p in re.findall(r"\w+", str(texto).lower())
                if len(p) >= 4 and p not in VACIAS]
    return " OR ".join('"%s"' % p for p in list(dict.fromkeys(palabras))[:8])


def buscar_mensajes(texto, limite=6, excluir_sesion=None):
    q = _consulta(texto)
    if not q:
        return []
    with _abrir() as con:
        return con.execute("""SELECT m.fecha,m.papel,m.contenido FROM mensajes_busca b
            JOIN mensajes m ON m.id=b.rowid
            WHERE mensajes_busca MATCH ? AND (? IS NULL OR m.sesion<>?)
            ORDER BY bm25(mensajes_busca),m.id DESC LIMIT ?""",
            (q, excluir_sesion, excluir_sesion, limite)).fetchall()


def mensajes_recientes(limite=4, excluir_sesion=None):
    with _abrir() as con:
        return con.execute("""SELECT fecha,papel,contenido FROM mensajes
            WHERE (? IS NULL OR sesion<>?) ORDER BY id DESC LIMIT ?""",
            (excluir_sesion, excluir_sesion, limite)).fetchall()[::-1]


def buscar_episodios(texto, limite=4, excluir_sesion=None):
    q = _consulta(texto)
    if not q:
        return []
    with _abrir() as con:
        filas = con.execute("""SELECT e.id,e.fecha,e.objetivo,e.contexto,e.estado,
            e.resultado,e.verificado FROM episodios_busca b
            JOIN episodios e ON e.id=b.rowid WHERE episodios_busca MATCH ?
            AND (? IS NULL OR e.sesion<>?)
            ORDER BY bm25(episodios_busca),e.id DESC LIMIT ?""",
            (q, excluir_sesion, excluir_sesion, limite)).fetchall()
        resultado = []
        for fila in filas:
            pasos = con.execute("SELECT herramienta,argumentos,resultado,estado FROM pasos "
                                "WHERE episodio_id=? ORDER BY orden LIMIT 8", (fila[0],)).fetchall()
            resultado.append((fila, pasos))
        return resultado


def contexto_relevante(peticion, sesion, limite=2600):
    lineas = []
    vistos = set()
    referencial = bool(re.search(r"\b(eso|aquello|anterior|seguimos|continua|retoma)\b",
                                str(peticion).lower()))
    recientes = mensajes_recientes(4, sesion) if referencial else []
    for fecha, papel, contenido in buscar_mensajes(peticion, 4, sesion) + recientes:
        clave = (fecha, papel, contenido)
        if clave in vistos:
            continue
        vistos.add(clave)
        lineas.append("%s %s: %s" % (fecha[:10], papel, contenido.replace("\n", " ")[:300]))
    episodios = []
    for e, pasos in buscar_episodios(peticion, 3, excluir_sesion=sesion):
        _, fecha, objetivo, contexto, estado, resultado, verificado = e
        detalle = "; ".join("%s: %s" % (p[0], p[2].replace("\n", " ")[:120])
                            for p in pasos[:4])
        episodios.append("%s Objetivo: %s. Condiciones: %s. Estado: %s%s. "
                         "Pasos: %s. Resultado: %s" %
                         (fecha[:10], objetivo[:170], contexto[:120], estado,
                          " (verificado)" if verificado else " (sin verificacion independiente)",
                          detalle, resultado[:220]))
    if not lineas and not episodios:
        return ""
    bloque = "Recuerdos LOCALES relevantes; comprueba si siguen siendo validos. "
    bloque += "Un intento fallido se puede repetir si cambio su causa o contexto.\n"
    if lineas:
        bloque += "Conversaciones anteriores:\n" + "\n".join(lineas) + "\n"
    if episodios:
        bloque += "Experiencias anteriores:\n" + "\n".join(episodios)
    return bloque[:limite]


def texto_para_revisar(busqueda="", limite=100):
    filas = buscar_mensajes(busqueda, limite) if busqueda else mensajes_recientes(limite)
    return "\n\n".join("%s  %s\n%s" % (f, "Angel" if p == "user" else "Sobri", c)
                       for f, p, c in filas) or "Todavia no hay conversaciones guardadas."


def borrar_historial():
    with _abrir() as con:
        con.execute("DELETE FROM pasos")
        con.execute("DELETE FROM episodios")
        con.execute("DELETE FROM mensajes")
        con.execute("INSERT INTO mensajes_busca(mensajes_busca) VALUES ('rebuild')")
        con.execute("INSERT INTO episodios_busca(episodios_busca) VALUES ('rebuild')")
    # Compacta el archivo y trunca el diario WAL para que el texto borrado no
    # quede en paginas antiguas de SQLite por una eliminacion logica.
    con = sqlite3.connect(RUTA, timeout=10)
    try:
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con.execute("VACUUM")
    finally:
        con.close()
