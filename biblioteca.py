# -*- coding: utf-8 -*-
"""Indice de la biblioteca de pistas y loops grabados.

Berna traia cinco loops de fabrica y renunciaba a ellos en cuanto le pedias
otra velocidad. Desde el 04/09/2026 hay 13.244 trozos grabados en
C:\\Users\\alaga\\Documents\\lmms\\samples\\Pistas, con la velocidad y muchas
veces el tono escritos en el propio nombre del fichero.

Este modulo los lee una vez, se apunta de cada uno su estilo, su papel, su
velocidad, su tono y cuantos compases dura, y guarda la lista en un json.
Asi Berna puede pedir "un break de 118 pulsaciones en La" y que se lo den.

La regla de oro sigue siendo la de siempre: UN TROZO GRABADO NO SE ESTIRA.
Si suena a otra velocidad se va de tiempo. Por eso aqui solo se devuelven
trozos cuya velocidad ya coincide con la de la cancion.
"""

import json
import os
import re
import unicodedata
import wave

from persistencia import guardar_json_atomico

BASE = os.path.dirname(os.path.abspath(__file__))
RAIZ = r"C:\Users\alaga\Documents\lmms\samples\Pistas"
CACHE = os.path.join(BASE, "biblioteca_pistas.json")
VERSION = 5

# ------------------------------------------------------------ leer el nombre

# "120bpm", "(140BPM)", "125 bpm"
_RE_BPM = re.compile(r'(?<!\d)(\d{2,3})\s*bpm', re.I)
# el tono suele ir pegado a la velocidad: 120G-01, 125_A-01, C120G
_RE_TONO1 = re.compile(r'(?<!\d)\d{2,3}\s*_?([A-G][#b]?)(?=[-_.]|\d|$)')
# o al final del todo: -G1, _Bb
_RE_TONO2 = re.compile(r'[-_]([A-G][#b]?)[0-9]?$')

# Que papel hace cada trozo dentro de la cancion. El orden importa: un
# "bass drum" es bateria y no bajo, por eso bateria va primero.
#
# OJO con la palabra "kit": NO esta en la lista a proposito. En estos packs
# una carpeta "Kit A 162bpm" o "LoopKit B 128bpm" no es de bateria, es un
# conjunto con TODOS los instrumentos de ese tema. Meterla marcaba como
# bateria hasta los bajos y las guitarras que hay dentro.
_PAPELES = (
    ("bateria", ("bass drum", "snare", "hi hat", "hihat", "tom", "cymbal",
                 "clap", "rimshot", "beat", "beats", "drum", "drums",
                 "break", "breaks", "perc", "percussion",
                 "conga", "congas", "cajon", "djembe", "maraca", "maracas",
                 "clave", "claves", "cowbell", "bongo", "bongos", "shaker",
                 "ride", "kick")),
    ("efecto",  ("sweep", "sweeps", "riser", "risers", "drop", "drops",
                 "impact", "impacts", "fx", "noise", "atmos", "texture",
                 "textures", "foley", "vinyl", "scratch", "stab", "stabs")),
    ("bajo",    ("bassline", "basslines", "bass", "bajo", "sub", "808")),
    ("melodia", ("lead", "leads", "mono", "arp", "arps", "brass", "horn",
                 "horns", "sax", "trumpet", "flute", "solo", "melody")),
    ("armonia", ("piano", "pianos", "organ", "organo", "clav", "clavinet",
                 "guitar", "guitars", "guitarra", "elka", "rhodes", "key",
                 "keys", "string", "strings", "pad", "pads", "synth",
                 "synths", "sinte", "chord", "chords")),
)

# Que carpeta de la biblioteca sirve para cada estilo de los que Berna conoce.
# Un estilo puede tirar de varias carpetas; se prueban en ese orden.
ESTILO_CARPETAS = {
    "reggaeton":   ("04_Dancehall_Regueton", "08_808_Graves", "07_Percusion"),
    "trap":        ("05_Trap", "08_808_Graves"),
    "hiphop":      ("02_HipHop", "18_LoFi", "08_808_Graves"),
    "house":       ("09_House", "23_Electro_House", "30_Nu_Disco"),
    "techno":      ("23_Electro_House", "26_IDM", "28_Industrial"),
    "dance":       ("23_Electro_House", "12_Rave", "09_House"),
    "drumandbass": ("01_BreakBeat", "03_BreakBeat_Roto", "25_Grime"),
    "breakbeat":   ("01_BreakBeat", "03_BreakBeat_Roto"),
    "pop":         ("31_Pop", "22_Anos_80"),
    "funk":        ("13_Funk", "30_Nu_Disco"),
    "disco":       ("30_Nu_Disco", "13_Funk"),
    "lofi":        ("18_LoFi", "21_Chillout"),
    "reggae":      ("04_Dancehall_Regueton", "07_Percusion"),
    "rock":        ("19_Guitarra_Acustica", "15_Bajo_Electrico"),
    "salsa":       ("07_Percusion", "06_Afrobeat", "17_Ska_Vientos"),
    "rumba":       ("07_Percusion", "19_Guitarra_Acustica"),
    "cumbia":      ("07_Percusion", "06_Afrobeat"),
    "balada":      ("21_Chillout", "16_Ambient"),
    "bolero":      ("21_Chillout", "19_Guitarra_Acustica"),
    "blues":       ("19_Guitarra_Acustica", "15_Bajo_Electrico"),
    "metal":       ("28_Industrial", "27_Impactos"),
    "punk":        ("28_Industrial",),
    "vals":        ("16_Ambient",),
}


def _sin_tildes(t):
    t = unicodedata.normalize("NFD", t)
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower()


_RE_CAMELLO = re.compile(r'(?<=[a-z])(?=[A-Z])')
_RE_PARTIR = re.compile(r'[^A-Za-z0-9]+|(?<=[A-Za-z])(?=[0-9])|(?<=[0-9])(?=[A-Za-z])')


def _palabras(texto):
    """Parte un nombre en palabras sueltas.

    Estos packs escriben todo pegado y en camello: "BassA162A", "ND_BeatMixA130",
    "ElkaPianoC120G". Si se busca el trozo "bass" tal cual dentro de la cadena
    hay falsos positivos ("kitty" contiene "kit", "custom" contiene "tom"), y si
    se exige palabra aislada no encuentra nada porque no hay separadores. La
    solucion es cortar donde cambia de minuscula a mayuscula y donde empiezan
    los numeros: "BassA162A" -> bass, a, 162, a.
    """
    t = _RE_CAMELLO.sub(" ", texto)
    return [p for p in _RE_PARTIR.split(_sin_tildes(t)) if p]


def _dice(palabras, clave):
    """Si entre las palabras esta la que se busca (o la pareja, si son dos)."""
    if " " in clave:
        return clave in " ".join(palabras)
    return clave in palabras


def _papel(carpeta_rel, nombre):
    """Que papel hace el trozo.

    Se mira PRIMERO el nombre del fichero y solo despues la carpeta, porque el
    nombre es lo concreto. Aun asi la carpeta hace falta: hay ficheros que se
    llaman solo "01" y viven dentro de "Drums".
    """
    for texto in (nombre, carpeta_rel.replace("\\", "/")):
        ps = _palabras(texto)
        for papel, claves in _PAPELES:
            for c in claves:
                if _dice(ps, c):
                    return papel
    return "otro"


def _velocidad(ruta_rel, nombre):
    m = _RE_BPM.search(ruta_rel) or _RE_BPM.search(nombre)
    return int(m.group(1)) if m else None


def _tono(nombre):
    m = _RE_TONO1.search(nombre) or _RE_TONO2.search(nombre)
    return m.group(1) if m else None


def _compases(ruta, bpm):
    """Cuantos compases de 4/4 dura, a la velocidad que dice su nombre."""
    if not bpm:
        return None
    try:
        w = wave.open(ruta, "rb")
        segundos = w.getnframes() / float(w.getframerate())
        w.close()
    except Exception:
        return None
    compases = segundos * bpm / 60.0 / 4.0
    entero = int(round(compases))
    # Solo vale si cae casi clavado en un numero entero de compases. Si no, no
    # es un loop que se pueda repetir: es un trozo suelto.
    if entero >= 1 and abs(compases - entero) < 0.05:
        return entero
    return None


# ------------------------------------------------------------ el indice

def indexar(forzar=False):
    """Devuelve la lista de trozos. La primera vez tarda; luego va del json."""
    if not forzar and os.path.exists(CACHE):
        try:
            with open(CACHE, "r", encoding="utf-8") as f:
                datos = json.load(f)
            if datos.get("version") == VERSION and datos.get("raiz") == RAIZ:
                return datos["trozos"]
        except Exception:
            pass

    trozos = []
    if not os.path.isdir(RAIZ):
        return trozos

    for carpeta, _, ficheros in os.walk(RAIZ):
        rel = os.path.relpath(carpeta, RAIZ)
        if rel == ".":
            continue
        partes = rel.split(os.sep)
        estilo = partes[0]
        # Para adivinar el papel se quita la carpeta de estilo: se llaman
        # "01_BreakBeat" u "08_808_Graves", y esas palabras marcarian como
        # bateria o bajo todo lo que hay dentro, sintetizadores incluidos.
        dentro = os.sep.join(partes[1:])
        for f in ficheros:
            if not f.lower().endswith(".wav"):
                continue
            ruta = os.path.join(carpeta, f)
            nombre = os.path.splitext(f)[0]
            rel_completo = os.path.join(rel, f)
            bpm = _velocidad(rel_completo, nombre)
            trozos.append({
                "ruta": ruta,
                "carpeta": estilo,
                "papel": _papel(dentro, nombre),
                "bpm": bpm,
                "tono": _tono(nombre),
                "compases": _compases(ruta, bpm),
            })

    try:
        guardar_json_atomico(
            CACHE, {"version": VERSION, "raiz": RAIZ, "trozos": trozos},
            indent=None)
    except Exception:
        pass
    return trozos


def hay_biblioteca():
    return os.path.isdir(RAIZ)


def buscar(papel=None, estilo=None, bpm=None, tono=None, con_compases=True):
    """Trozos que cumplen lo pedido. La velocidad tiene que ser EXACTA."""
    carpetas = ESTILO_CARPETAS.get(estilo) if estilo else None
    salida = []
    for t in indexar():
        if papel and t["papel"] != papel:
            continue
        if carpetas and t["carpeta"] not in carpetas:
            continue
        if bpm and t["bpm"] != bpm:
            continue
        if tono and t["tono"] != tono:
            continue
        if con_compases and not t["compases"]:
            continue
        salida.append(t)
    return salida


def _de_carpeta(carpeta, papel, bpm=None, tono=None):
    salida = []
    for t in indexar():
        if t["carpeta"] != carpeta or t["papel"] != papel or not t["compases"]:
            continue
        if bpm and t["bpm"] != bpm:
            continue
        if tono and t["tono"] != tono:
            continue
        salida.append(t)
    return salida


PAPELES_KIT = ("bateria", "bajo", "armonia", "melodia", "efecto")

# Golpes sueltos que suenan AGUDO. Se buscan por nombre porque es lo que hay.
AGUDOS = ("hat", "hihat", "shaker", "ride", "cymbal", "tamb", "cabasa",
          "maraca", "clave", "tick", "snap", "crash", "triangle")


def golpes_agudos(estilo, limite=8):
    """Golpes SUELTOS y agudos del estilo: charles, shakers, maracas...

    POR QUE HACE FALTA (04/09/2026): las canciones salian apagadas. Medido,
    tenian un 3% de energia entre 2 y 8 kHz cuando un disco tiene un 7%. El
    motivo es que al apilar bajo, armonia y melodia se amontona todo abajo y
    los agudos quedan diluidos. En un estudio eso se arregla poniendo ENCIMA
    una capa de charles y shakers.

    Se devuelven golpes SUELTOS (los que no son bucles, `compases` vacio) a
    proposito: un golpe suelto vale para cualquier velocidad, porque no hay
    nada que estirar. Es el unico material que se puede usar sin restricciones.
    """
    if not hay_biblioteca():
        return []
    salida = []
    for carpeta in ESTILO_CARPETAS.get(estilo, ()):
        for t in indexar():
            if t["carpeta"] != carpeta or t["compases"]:
                continue          # los bucles no, aqui se quieren golpes
            n = _sin_tildes(os.path.basename(t["ruta"]))
            if any(a in n for a in AGUDOS):
                salida.append(t)
        if salida:
            break
    salida.sort(key=lambda t: t["ruta"])
    return salida[:limite]


def kit_para(estilo, bpm=None, minimo=2):
    """Un CONJUNTO coherente de trozos grabados para montar una cancion entera.

    Devuelve {carpeta, bpm, tono, papeles: {papel: [trozos]}} o None.

    Esto es lo que separa una cancion de un amasijo. No vale coger la bateria
    de un sitio, el bajo de otro y la guitarra de un tercero: sonarian a tres
    canciones a la vez. Hay que exigir que todo venga de la MISMA carpeta, a la
    MISMA velocidad y en el MISMO tono. Los packs estan grabados asi a
    proposito: cada "Kit A 120bpm" son las pistas de un mismo tema.

    La bateria y los efectos no llevan tono, asi que a esos no se les exige.
    """
    if not hay_biblioteca():
        return None
    mejor = None
    for carpeta in ESTILO_CARPETAS.get(estilo, ()):
        # que velocidades tiene esta carpeta, la que mas material primero
        cuenta = {}
        for t in indexar():
            if t["carpeta"] == carpeta and t["compases"] and t["bpm"]:
                cuenta[t["bpm"]] = cuenta.get(t["bpm"], 0) + 1
        if not cuenta:
            continue
        candidatas = [bpm] if bpm else [v for v, _ in sorted(
            cuenta.items(), key=lambda x: (-x[1], x[0]))[:4]]
        for v in candidatas:
            if not v or v not in cuenta:
                continue
            # el tono con mas material melodico a esa velocidad
            tonos = {}
            for p in ("bajo", "armonia", "melodia"):
                for t in _de_carpeta(carpeta, p, v):
                    if t["tono"]:
                        tonos[t["tono"]] = tonos.get(t["tono"], 0) + 1
            tono = sorted(tonos.items(), key=lambda x: -x[1])[0][0] if tonos else None

            papeles = {}
            for p in PAPELES_KIT:
                if p in ("bateria", "efecto") or not tono:
                    trozos = _de_carpeta(carpeta, p, v)
                else:
                    trozos = (_de_carpeta(carpeta, p, v, tono)
                              or _de_carpeta(carpeta, p, v))
                if trozos:
                    papeles[p] = trozos
            if "bateria" not in papeles or len(papeles) < minimo:
                continue
            nota = (len(papeles), sum(len(x) for x in papeles.values()))
            if mejor is None or nota > mejor[0]:
                mejor = (nota, {"carpeta": carpeta, "bpm": v, "tono": tono,
                                "papeles": papeles})
        if mejor:
            break        # manda la primera carpeta del estilo que sirva
    return mejor[1] if mejor else None


def velocidades(estilo, papel="bateria"):
    """A que velocidades hay material de este estilo, de mas a menos trozos."""
    cuenta = {}
    for t in buscar(papel=papel, estilo=estilo):
        if t["bpm"]:
            cuenta[t["bpm"]] = cuenta.get(t["bpm"], 0) + 1
    return sorted(cuenta.items(), key=lambda x: (-x[1], x[0]))


def loop_para(estilo, bpm=None, tono=None, papel="bateria", az=None):
    """Un loop listo para Berna: (ruta, compases, bpm). None si no hay.

    Las carpetas de cada estilo se prueban EN ORDEN, y manda la primera que
    tenga algo. Es a proposito: para el reggaeton, la primera es la del
    dancehall, que es el ritmo del genero; si se buscara por todas a la vez
    ganarian las congas sueltas, que son mas numerosas pero no son la base.

    Si no se dice velocidad, dentro de esa carpeta se coge la que mas
    material tenga, que es la que luego dara mas variedad.
    """
    if not hay_biblioteca():
        return None
    for carpeta in ESTILO_CARPETAS.get(estilo, ()):
        objetivo = bpm
        if not objetivo:
            cuenta = {}
            for t in _de_carpeta(carpeta, papel):
                if t["bpm"]:
                    cuenta[t["bpm"]] = cuenta.get(t["bpm"], 0) + 1
            if not cuenta:
                continue
            objetivo = sorted(cuenta.items(), key=lambda x: (-x[1], x[0]))[0][0]
        cand = (_de_carpeta(carpeta, papel, objetivo, tono)
                or (_de_carpeta(carpeta, papel, objetivo) if tono else []))
        if not cand:
            continue
        # Los de dos compases primero: repiten mejor y cansan menos que los de uno.
        cand.sort(key=lambda t: (abs(t["compases"] - 2), t["ruta"]))
        mejores = [c for c in cand if c["compases"] == cand[0]["compases"]]
        elegido = az.choice(mejores) if az else mejores[0]
        return (elegido["ruta"], elegido["compases"], elegido["bpm"])
    return None


def resumen():
    ts = indexar()
    papeles = {}
    carpetas = set()
    con_bpm = sum(1 for t in ts if t["bpm"])
    con_loop = sum(1 for t in ts if t["compases"])
    for t in ts:
        papeles[t["papel"]] = papeles.get(t["papel"], 0) + 1
        carpetas.add(t["carpeta"])
    return {"total": len(ts), "con_bpm": con_bpm, "loops": con_loop,
            "papeles": papeles, "carpetas": len(carpetas)}


if __name__ == "__main__":
    r = resumen()
    print("trozos indexados: %d" % r["total"])
    print("con velocidad:    %d" % r["con_bpm"])
    print("loops usables:    %d" % r["loops"])
    print("carpetas:         %d" % r["carpetas"])
    print("papeles: " + ", ".join("%s=%d" % kv
                                  for kv in sorted(r["papeles"].items())))
