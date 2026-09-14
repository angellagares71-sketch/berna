# -*- coding: utf-8 -*-
r"""
Berna compone una cancion entera en LMMS, ella sola.

Angel lo pidio el 2026-09-02: "que solo Berna pueda generar una cancion del
estilo que yo le diga". Y ese mismo dia, oyendo la primera version, dijo lo que
habia que oir: "parecen politonos". Tenia razon, y esta segunda version existe
por eso.

POR QUE SONABA A POLITONO, y que se ha hecho con cada cosa
  1. OSCILADORES CRUDOS. Una onda de sierra sin filtro ni envolvente decente es
     un pitido, no un instrumento. Ahora se usan los PRESETS que trae LMMS (125
     en su formato propio: TripleOscillator, Kicker, LB302, Organic...), hechos
     por gente que sabe, con sus filtros, sus envolventes y hasta sus efectos.
  2. TODO SECO Y CENTRADO. Sin una sala alrededor, cualquier sonido parece de
     telefono. Ahora hay reverb de verdad (reverbsc) donde toca, y las pistas
     estan repartidas a izquierda y derecha.
  3. TODAS LAS NOTAS IGUALES Y CLAVADAS EN LA REJA. Eso es, literalmente, lo
     que hace un politono. Ahora hay acentos, el volumen baila, el tiempo
     tiembla unos tics, hay golpes fantasma en la caja y swing en los estilos
     que lo piden.
  4. ACORDES DE ORGANILLO. Siempre la misma triada en la misma posicion. Ahora
     se enlazan por la voz mas cercana y hay septimas donde pintan.
  5. UN BUCLE DE CUATRO COMPASES REPETIDO. Ahora hay secciones: entrada,
     estrofa, subida con redoble, estribillo y final; y la melodia tiene un
     motivo que vuelve, en vez de notas al azar.

LAS UNIDADES DE LMMS, que es lo que hay que acertar
  Un compas de 4/4 son 192 tics. O sea 48 por pulso y 12 por cada paso de la
  cuadricula de dieciseisavos. En 3/4 (el vals) son 144. Los numeros de nota
  son los del MIDI: el 60 es el do central.

COMO SE COMPRUEBA QUE SUENA, sin fiarse
  LMMS trae `lmms render`, que convierte el proyecto en audio sin abrir
  ventana. Se renderiza, se mide el nivel y se mira que no sature. Un XML puede
  estar perfecto y sonar a nada.
"""
import os
import io
import re
import time
import random
import subprocess
import unicodedata

BASE = os.path.dirname(os.path.abspath(__file__))
LMMS = r"C:\Program Files\LMMS\lmms.exe"
MUESTRAS = r"C:\Program Files\LMMS\data\samples"
PRESETS = r"C:\Program Files\LMMS\data\presets"

TICS_PULSO = 48                 # lo que dura una negra en LMMS
SEGUNDOS_RENDER = 300
# El volumen general. Con presets de verdad, que traen su propio nivel, la suma
# se va de escala enseguida. Este numero sale de renderizar y contar cuantas
# muestras se quedan pegadas al techo, no de estimarlo a ojo.
# A 100 y que mande el limitador. Con 45 se tiraban 7 decibelios DESPUES de
# limitar: el limitador dejaba la senal pegada a su techo y luego el volumen
# general la bajaba a la mitad. Trabajo tirado (medido el 02-09-2026).
VOLUMEN_MAESTRO = 100


# ---------------------------------------------------------------- carpetas
def _carpeta_musica():
    """Donde se guardan las canciones. La de Musica del usuario, de verdad.

    Con OneDrive por medio no es "~/Music". Windows guarda la buena en el
    registro. Mismo truco que operar.escritorio(); si se toca una, mirar la otra.
    """
    try:
        import winreg
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer"
                r"\User Shell Folders") as k:
            ruta = os.path.expandvars(winreg.QueryValueEx(k, "My Music")[0])
        if os.path.isdir(ruta):
            return os.path.join(ruta, "Canciones de Berna")
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Music", "Canciones de Berna")


def _sin_tildes(t):
    t = unicodedata.normalize("NFD", str(t or ""))
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower()


def _limpio(nombre):
    n = re.sub(r"[^\w\s-]", "", str(nombre or "")).strip()
    n = re.sub(r"\s+", "_", n)
    return n[:60] or "cancion"


# ------------------------------------------------------------- teoria musical
NOTAS = {"do": 0, "do#": 1, "reb": 1, "re": 2, "re#": 3, "mib": 3, "mi": 4,
         "fa": 5, "fa#": 6, "solb": 6, "sol": 7, "sol#": 8, "lab": 8, "la": 9,
         "la#": 10, "sib": 10, "si": 11,
         "c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}

ESCALAS = {
    "mayor": [0, 2, 4, 5, 7, 9, 11],
    "menor": [0, 2, 3, 5, 7, 8, 10],
    "menor_armonica": [0, 2, 3, 5, 7, 8, 11],
    # la frigia es el sonido flamenco: ese segundo grado bajito es el "duende"
    "frigia": [0, 1, 3, 5, 7, 8, 10],
    "dorica": [0, 2, 3, 5, 7, 9, 10],
    "pentatonica": [0, 3, 5, 7, 10],
    "blues": [0, 3, 5, 6, 7, 10],
}


def _grado(escala, i):
    """La nota del grado i de la escala, subiendo de octava cuando hace falta."""
    n = len(escala)
    return escala[i % n] + 12 * (i // n)


def _voces(escala, grado, septima, raiz, anterior=None, quinto_mayor=False):
    """El acorde, colocado para enlazar bien con el anterior.

    Un acorde siempre en la misma posicion suena a organillo. Cambiando la
    inversion para que las voces se muevan lo menos posible, suena a alguien
    tocando de verdad.
    """
    grados = [grado, grado + 2, grado + 4] + ([grado + 6] if septima else [])
    base = [60 + raiz + _grado(escala, g) for g in grados]
    # EL ACORDE DEL DUENDE. En la cadencia andaluza el ultimo acorde (el V) es
    # MAYOR aunque la escala sea menor: en la menor, el Mi lleva sol SOSTENIDO.
    # Ese semitono es, literalmente, el sonido del flamenco. Sacado de la
    # escala tal cual sale menor y suena a otra cosa.
    if quinto_mayor and grado % 7 == 4 and len(base) >= 3:
        # En la frigia el acorde del V sale DISMINUIDO (mi-sol-si bemol). Para
        # la cadencia andaluza tiene que ser MI MAYOR: hay que subir un
        # semitono la tercera Y la quinta (sol -> sol#, si bemol -> si).
        base[1] += 1
        base[2] += 1
    mejor, coste_mejor = base, None
    for giro in range(len(base)):
        cand = base[giro:] + [n + 12 for n in base[:giro]]
        cand = [n - 12 if n > 79 else n for n in cand]
        coste = (sum(abs(n - 67) for n in cand) if anterior is None
                 else sum(min(abs(n - a) for a in anterior) for n in cand))
        if coste_mejor is None or coste < coste_mejor:
            mejor, coste_mejor = cand, coste
    return sorted(mejor)


# --------------------------------------------------------------- los estilos
def _p(patron, compas=0, pasos=16):
    """Convierte 'x..x' en [0, 3]. Se escribe asi porque se LEE el ritmo.

    Si el patron mide el DOBLE, es de dos compases y se coge la mitad que toca.
    Hace falta de verdad: la clave de la salsa dura dos compases (tres golpes en
    uno y dos en el otro) y meterla en uno solo la destroza. Lo mismo pasa con
    casi toda la percusion afrocubana.
    """
    if len(patron) >= pasos * 2:
        patron = patron[pasos:pasos * 2] if compas % 2 else patron[:pasos]
    return [i for i, c in enumerate(patron) if c != "."]


T = "TripleOscillator/%s.xpf"
O = "Organic/%s.xpf"

ESTILOS = {
    "reggaeton": {
        "alias": ("regueton", "reguetón", "reggaetón", "perreo", "dembow"),
        "bpm": 95, "escala": "menor", "acordes": [0, 5, 3, 4], "septimas": 0,
        "swing": 0.0,
        "bombo": "x.......x.......", "caja": "...x..x....x..x.",
        "charles": "x.x.x.x.x.x.x.x.", "extra": ("shaker01.ogg", "..x...x...x...x."),
        "muestras": {"bombo": "kick02.ogg", "caja": "snare_electro01.ogg",
                     "charles": "hihat_closed03.ogg"},
        "bajo": "x.......x...x...", "acordes_ritmo": "x.......x.......",
        "p_bajo": T % "FuzzyAnalogBass", "p_acordes": O % "pad_rich",
        "p_melodia": T % "PluckArpeggio", "melodia": 1,
    },
    "trap": {
        "alias": ("trap latino", "drill"),
        "bpm": 140, "escala": "menor_armonica", "acordes": [0, 0, 5, 4],
        "septimas": 0, "swing": 0.0,
        "bombo": "x.....x...x.....", "caja": "........x.......",
        "charles": "x.x.x.x.x.x.xxx.", "extra": ("clap02.ogg", "........x......."),
        "muestras": {"bombo": "kick_hard01.ogg", "caja": "snare_hiphop01.ogg",
                     "charles": "hihat_closed01.ogg"},
        "bajo": "x.....x...x.....", "acordes_ritmo": "x...............",
        "p_bajo": T % "PMbass", "p_acordes": T % "CryingPads",
        "p_melodia": T % "Bell", "melodia": 1,
    },
    "hiphop": {
        "alias": ("hip hop", "rap", "boom bap"),
        # Boom bap de verdad: bombo en el 1 y el 3, caja en el 2 y el 4, golpes
        # fantasma en los dieciseisavos de antes de la caja, y swing del 60%,
        # que es el "feel" de las MPC con las que se hizo todo esto. La
        # velocidad buena son 94, no 90.
        "bpm": 94, "escala": "menor", "acordes": [0, 3, 5, 4], "septimas": 1,
        "swing": 0.6,
        "bombo": "x.x.....x.......", "caja": "....x.......x...",
        "charles": "x.x.x.x.x.x.x.x.", "extra": ("rim01.ogg", "..............x."),
        "muestras": {"bombo": "kick_hiphop01.ogg", "caja": "snare_hiphop02.ogg",
                     "charles": "hihat_closed02.ogg"},
        "bajo": "x.....x..x......", "acordes_ritmo": "x.......x.......",
        "p_bajo": T % "PluckBass", "p_acordes": T % "Harmonium",
        "p_melodia": T % "Xylophon", "melodia": 1,
    },
    "house": {
        "alias": ("deep house", "electronica", "electrónica"),
        "bpm": 124, "escala": "menor", "acordes": [0, 5, 3, 4], "septimas": 1,
        "swing": 0.0,
        "bombo": "x...x...x...x...", "caja": "....x.......x...",
        "charles": "..x...x...x...x.", "extra": ("clap01.ogg", "....x.......x..."),
        "muestras": {"bombo": "kick01.ogg", "caja": "clap03.ogg",
                     "charles": "hihat_opened01.ogg"},
        "bajo": "x.x.x.x.x.x.x.x.", "acordes_ritmo": "..x...x...x...x.",
        "p_bajo": T % "MoveYourBody", "p_acordes": T % "ResonantPad",
        "p_melodia": T % "PluckArpeggio", "melodia": 1,
    },
    "techno": {
        "alias": ("tecno", "minimal"),
        "bpm": 132, "escala": "menor", "acordes": [0, 0, 5, 5], "septimas": 0,
        "swing": 0.0,
        "bombo": "x...x...x...x...", "caja": "....x.......x...",
        "charles": "xxxxxxxxxxxxxxxx", "extra": ("zap01.ogg", "..........x....."),
        "muestras": {"bombo": "kick_hard01.ogg", "caja": "clap04.ogg",
                     "charles": "hihat_closed04.ogg"},
        "bajo": "x.x.x.x.x.x.x.x.", "acordes_ritmo": "x.......x.......",
        "p_bajo": T % "TB303", "p_acordes": T % "HiPad",
        "p_melodia": T % "SuperSawLead", "melodia": 1,
    },
    "dance": {
        "alias": ("edm", "makina", "bakalao", "discoteca"),
        "bpm": 128, "escala": "mayor", "acordes": [5, 3, 0, 4], "septimas": 0,
        "swing": 0.0,
        "bombo": "x...x...x...x...", "caja": "....x.......x...",
        "charles": "..x...x...x...x.", "extra": ("crash01.ogg", "x..............."),
        "muestras": {"bombo": "kick01.ogg", "caja": "clap01.ogg",
                     "charles": "hihat_opened02.ogg"},
        "bajo": "x.x.x.x.x.x.x.x.", "acordes_ritmo": "x...x...x...x...",
        "p_bajo": T % "RaveBass", "p_acordes": T % "PowerStrings",
        "p_melodia": T % "Supernova", "melodia": 1,
    },
    "drumandbass": {
        "alias": ("drum and bass", "dnb", "jungle", "breakcore"),
        "bpm": 174, "escala": "menor", "acordes": [0, 0, 3, 4], "septimas": 1,
        "swing": 0.0,
        "bombo": "x........x......", "caja": "....x.......x...",
        "charles": "..x...x...x...x.", "extra": ("ride01.ogg", "x.......x......."),
        "muestras": {"bombo": "kick_long01.ogg", "caja": "snare05.ogg",
                     "charles": "hihat_closed05.ogg"},
        "bajo": "x.......x.......", "acordes_ritmo": "x...............",
        "p_bajo": T % "DirtyReece", "p_acordes": T % "HiPad",
        "p_melodia": T % "Bell", "melodia": 1,
    },
    "breakbeat": {
        "alias": ("break", "breaks", "big beat"),
        "bpm": 130, "escala": "menor", "acordes": [0, 3, 5, 4], "septimas": 0,
        "swing": 0.15,
        "bombo": "x.....x.....x...", "caja": "....x.......x...",
        "charles": "x.x.x.x.x.x.x.x.", "extra": ("clap02.ogg", "............x..."),
        "muestras": {"bombo": "bassdrum02.ogg", "caja": "snare03.ogg",
                     "charles": "hihat_closed01.ogg"},
        "bajo": "x.....x.....x...", "acordes_ritmo": "x.......x.......",
        "p_bajo": T % "FuzzyAnalogBass", "p_acordes": T % "ResonantPad",
        "p_melodia": T % "SquarePing", "melodia": 1,
    },
    "rock": {
        "alias": ("rock and roll", "rockero"),
        "bpm": 120, "escala": "mayor", "acordes": [0, 4, 5, 3], "septimas": 0,
        "swing": 0.0,
        "bombo": "x.......x.......", "caja": "....x.......x...",
        "charles": "x.x.x.x.x.x.x.x.", "extra": ("crash01.ogg", "x..............."),
        "muestras": {"bombo": "bassdrum_acoustic01.ogg",
                     "caja": "snare_acoustic01.ogg",
                     "charles": "hihat_closed02.ogg"},
        "bajo": "x...x...x...x...", "acordes_ritmo": "x...x...x...x...",
        "p_bajo": T % "PluckBass", "p_acordes": T % "SEGuitar",
        "p_melodia": T % "SEGuitar", "melodia": 1,
    },
    "metal": {
        "alias": ("heavy", "trash", "metalero"),
        "bpm": 160, "escala": "frigia", "acordes": [0, 0, 1, 0], "septimas": 0,
        "swing": 0.0,
        "bombo": "x.x.x.x.x.x.x.x.", "caja": "....x.......x...",
        "charles": "x...x...x...x...", "extra": ("crash02.ogg", "x.......x......."),
        "muestras": {"bombo": "kick_distorted01.ogg", "caja": "snare_harsh01.ogg",
                     "charles": "ride02.ogg"},
        "bajo": "x.x.x.x.x.x.x.x.", "acordes_ritmo": "x.x.x.x.x.x.x.x.",
        "p_bajo": T % "HugeGrittyBass", "p_acordes": T % "Erazzor",
        "p_melodia": T % "Erazzor", "melodia": 1,
    },
    "punk": {
        "alias": ("punky",),
        "bpm": 175, "escala": "mayor", "acordes": [0, 4, 5, 4], "septimas": 0,
        "swing": 0.0,
        "bombo": "x...x...x...x...", "caja": "....x.......x...",
        "charles": "x.x.x.x.x.x.x.x.", "extra": ("crash01.ogg", "x..............."),
        "muestras": {"bombo": "bassdrum03.ogg", "caja": "snare_short01.ogg",
                     "charles": "hihat_closed03.ogg"},
        "bajo": "x.x.x.x.x.x.x.x.", "acordes_ritmo": "x...x...x...x...",
        "p_bajo": T % "PercussiveBass", "p_acordes": T % "SEGuitar",
        "p_melodia": T % "SEGuitar", "melodia": 0,
    },
    "pop": {
        "alias": ("comercial", "cancion pop"),
        "bpm": 110, "escala": "mayor", "acordes": [0, 4, 5, 3], "septimas": 0,
        "swing": 0.0,
        "bombo": "x.......x.......", "caja": "....x.......x...",
        "charles": "x.x.x.x.x.x.x.x.", "extra": ("clap01.ogg", "....x.......x..."),
        "muestras": {"bombo": "bassdrum01.ogg", "caja": "snare02.ogg",
                     "charles": "hihat_closed01.ogg"},
        "bajo": "x.......x...x...", "acordes_ritmo": "x...x...x...x...",
        "p_bajo": T % "PluckBass", "p_acordes": T % "WarmStack",
        "p_melodia": T % "Bell", "melodia": 1,
    },
    "balada": {
        "alias": ("lenta", "romantica", "romántica", "amor"),
        "bpm": 72, "escala": "mayor", "acordes": [0, 5, 3, 4], "septimas": 1,
        "swing": 0.0,
        "bombo": "x.......x.......", "caja": "....x.......x...",
        "charles": "..x...x...x...x.", "extra": ("shaker02.ogg", "x.x.x.x.x.x.x.x."),
        "muestras": {"bombo": "bassdrum_acoustic02.ogg",
                     "caja": "snare_muffled01.ogg", "charles": "hihat_closed04.ogg"},
        "bajo": "x.......x.......", "acordes_ritmo": "x.......x.......",
        "p_bajo": T % "PMbass", "p_acordes": T % "CryingPads",
        "p_melodia": T % "Harp-of-a-Fairy", "melodia": 1,
    },
    "bolero": {
        "alias": ("boleros",),
        "bpm": 84, "escala": "menor", "acordes": [0, 3, 4, 0], "septimas": 1,
        "swing": 0.0,
        "bombo": "x.....x.x.......", "caja": "..............x.",
        "charles": "x..x..x.x..x..x.", "extra": ("clav01.ogg", "x.....x...x....."),
        "muestras": {"bombo": "bassdrum_acoustic01.ogg", "caja": "sidestick01.ogg",
                     "charles": "shaker01.ogg"},
        "bajo": "x.....x.x.......", "acordes_ritmo": "x.....x.x.......",
        "p_bajo": T % "PluckBass", "p_acordes": T % "Harmonium",
        "p_melodia": T % "SEGuitar", "melodia": 1,
    },
    "rumba": {
        "alias": ("flamenco", "rumba flamenca", "sevillanas", "gitano"),
        # LA CADENCIA ANDALUZA: i - VII - VI - V (en la menor: Am G F E). Lo que
        # le da el aire flamenco es que termina en el V y ese acorde es MAYOR,
        # no menor. Antes volvia al i y se quedaba en una escala rara sin
        # resolver, que es justo lo que le faltaba al duende.
        "bpm": 104, "escala": "frigia", "acordes": [0, 6, 5, 4],
        "quinto_mayor": 1, "septimas": 0,
        "swing": 0.0,
        "bombo": "x.......x.......", "caja": "..x.x..x..x.x..x",
        "charles": "x.x.x.x.x.x.x.x.", "extra": ("clap03.ogg", "..x.x..x..x.x..x"),
        "muestras": {"bombo": "bassdrum_acoustic02.ogg", "caja": "clap02.ogg",
                     "charles": "shaker03.ogg"},
        "bajo": "x.......x...x...", "acordes_ritmo": "x..x..x...x..x..",
        "p_bajo": T % "PluckBass", "p_acordes": T % "SEGuitar",
        "p_melodia": T % "SEGuitar", "melodia": 1,
    },
    "cumbia": {
        "alias": ("cumbiton", "tropical"),
        "bpm": 96, "escala": "menor", "acordes": [0, 4, 0, 4], "septimas": 0,
        "swing": 0.0,
        "bombo": "x.......x.......", "caja": "....x.......x...",
        "charles": "x.x.x.x.x.x.x.x.", "extra": ("clav02.ogg", "....x.......x..."),
        "muestras": {"bombo": "bassdrum02.ogg", "caja": "rim01.ogg",
                     "charles": "shaker02.ogg"},
        "bajo": "....x.......x...", "acordes_ritmo": "....x.......x...",
        "p_bajo": T % "PluckBass", "p_acordes": T % "E-Organ",
        "p_melodia": T % "Xylophon", "melodia": 1,
    },
    "salsa": {
        "alias": ("son", "latino", "latina", "mambo"),
        # La CLAVE DE SON 3-2 ocupa DOS compases: tres golpes en el primero
        # (1, el "y" del 2, y el 4) y dos en el segundo (2 y 3). Todo lo demas
        # de la orquesta se coloca respecto a ella. Antes estaba metida a
        # machamartillo en un solo compas, que es como tocar salsa sin clave.
        "bpm": 100, "escala": "menor", "acordes": [0, 4, 0, 4], "septimas": 1,
        "swing": 0.0,
        "bombo": "x.......x.......x.......x.......",
        "caja": "x..x..x...x.x...x..x..x...x.x...",
        "charles": "x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.x.",
        "extra": ("clav01.ogg", "x.....x.....x.......x...x......."),
        "muestras": {"bombo": "bassdrum01.ogg", "caja": "clav02.ogg",
                     "charles": "shaker01.ogg"},
        # El TUMBAO del bajo NO pisa el 1: entra en el "y" del 2 y en el 4,
        # y ese 4 ya adelanta la nota del compas siguiente. Es lo que hace que
        # la salsa empuje hacia delante en vez de marcar como una marcha.
        "bajo": "......x.....x...", "acordes_ritmo": "..x...x...x...x.",
        "tumbao": 1,
        "p_bajo": T % "PluckBass", "p_acordes": T % "E-Organ2",
        "p_melodia": T % "Whistle", "melodia": 1,
    },
    "reggae": {
        "alias": ("raggae", "ska", "jamaicano"),
        "bpm": 78, "escala": "menor", "acordes": [0, 3, 0, 4], "septimas": 1,
        "swing": 0.2,
        "bombo": "........x.......", "caja": "........x.......",
        "charles": "..x...x...x...x.", "extra": ("rim01.ogg", "....x.......x..."),
        "muestras": {"bombo": "bassdrum04.ogg", "caja": "snare_muffled02.ogg",
                     "charles": "hihat_closed05.ogg"},
        "bajo": "x.......x.x.....", "acordes_ritmo": "..x...x...x...x.",
        "p_bajo": T % "SpaceBass", "p_acordes": T % "E-Organ",
        "p_melodia": T % "Bell", "melodia": 1,
    },
    "funk": {
        "alias": ("funky", "groove"),
        "bpm": 108, "escala": "dorica", "acordes": [0, 0, 3, 3], "septimas": 1,
        "swing": 0.3,
        "bombo": "x.....x...x.x...", "caja": "....x.......x...",
        "charles": "xxxxxxxxxxxxxxxx", "extra": ("clap04.ogg", "............x..."),
        "muestras": {"bombo": "bassdrum01.ogg", "caja": "snare04.ogg",
                     "charles": "hihat_closed02.ogg"},
        "bajo": "x..x..x...x.x...", "acordes_ritmo": "..x..x....x..x..",
        "p_bajo": T % "ResoBass", "p_acordes": T % "E-Organ2",
        "p_melodia": T % "PluckArpeggio", "melodia": 1,
    },
    "disco": {
        "alias": ("setentero", "70s"),
        "bpm": 118, "escala": "mayor", "acordes": [0, 5, 3, 4], "septimas": 1,
        "swing": 0.0,
        "bombo": "x...x...x...x...", "caja": "....x.......x...",
        "charles": "..x...x...x...x.", "extra": ("clap01.ogg", "....x.......x..."),
        "muestras": {"bombo": "bassdrum01.ogg", "caja": "snare01.ogg",
                     "charles": "hihat_opened03.ogg"},
        "bajo": "x.x.x.x.x.x.x.x.", "acordes_ritmo": "..x...x...x...x.",
        "p_bajo": T % "MoveYourBody", "p_acordes": T % "PowerStrings",
        "p_melodia": T % "Bell", "melodia": 1,
    },
    "lofi": {
        "alias": ("lo-fi", "chill", "relajado", "para estudiar", "ambiente"),
        "bpm": 74, "escala": "dorica", "acordes": [0, 3, 5, 4], "septimas": 1,
        "swing": 0.4,
        "bombo": "x.....x.........", "caja": "....x.......x...",
        "charles": "x.x.x.x.x.x.x.x.", "extra": ("shaker03.ogg", "..x...x...x...x."),
        "muestras": {"bombo": "kick_soft01.ogg", "caja": "snare_muffled01.ogg",
                     "charles": "hihat_closed04.ogg"},
        "bajo": "x.......x.......", "acordes_ritmo": "x.......x.......",
        "p_bajo": T % "PMbass", "p_acordes": T % "LovelyDream",
        "p_melodia": T % "Xylophon", "melodia": 1,
    },
    "blues": {
        "alias": ("bluesero",),
        "bpm": 88, "escala": "blues", "acordes": [0, 0, 3, 4], "septimas": 0,
        "swing": 0.45,
        "bombo": "x.......x.......", "caja": "....x.......x...",
        "charles": "x..x..x..x..x..x", "extra": ("ride01.ogg", "x..x..x..x..x..x"),
        "muestras": {"bombo": "bassdrum_acoustic01.ogg",
                     "caja": "snare_acoustic01.ogg", "charles": "ride02.ogg"},
        "bajo": "x..x..x..x..x..x", "acordes_ritmo": "x.......x.......",
        "p_bajo": T % "PluckBass", "p_acordes": T % "E-Organ",
        "p_melodia": T % "SEGuitar", "melodia": 1,
    },
    "vals": {
        "alias": ("valses", "tres por cuatro"),
        "compas": 3,
        "bpm": 100, "escala": "mayor", "acordes": [0, 4, 0, 4], "septimas": 0,
        "swing": 0.0,
        "bombo": "x...........", "caja": "....x...x...",
        "charles": "x...x...x...", "extra": ("shaker01.ogg", "x...x...x..."),
        "muestras": {"bombo": "bassdrum_acoustic02.ogg",
                     "caja": "snare_muffled02.ogg", "charles": "hihat_closed03.ogg"},
        "bajo": "x...........", "acordes_ritmo": "....x...x...",
        "p_bajo": T % "PMbass", "p_acordes": T % "Harmonium",
        "p_melodia": T % "Harp-of-a-Fairy", "melodia": 1,
    },
}


# Que toca cada estilo, con instrumentos GRABADOS. Un valor a None quiere decir
# "aqui va un sintetizador de verdad", que en el tecno o el drum and bass no es
# una renuncia: es lo correcto. En una rumba, en cambio, tiene que sonar una
# guitarra espanola de verdad.
#   kit ....... que bateria del banco
#   golpes .... a que golpe de esa bateria corresponde cada patron
#   bajo/acordes/melodia ... instrumento grabado, o None para el sintetizador
INSTRUMENTOS = {
    "reggaeton": {"kit": "808", "bajo": "bajo_sinte", "acordes": "pad_calido",
                  "melodia": "guitarra_espanola", "extra": "palmas"},
    "trap": {"kit": "808", "bajo": "bajo_sinte2", "acordes": "pad_nuevaera",
             "melodia": "vibrafono", "extra": "palmas"},
    "hiphop": {"kit": "jazz", "bajo": "bajo_acustico",
               "acordes": "piano_electrico", "melodia": "vibrafono",
               "extra": "aro"},
    "house": {"kit": "electronica", "bajo": "bajo_sinte", "acordes": "piano",
              "melodia": "lead_sierra", "extra": "palmas"},
    "techno": {"kit": "electronica", "bajo": None, "acordes": None,
               "melodia": None, "extra": "palmas"},
    "dance": {"kit": "electronica", "bajo": "bajo_sinte",
              "acordes": "cuerdas_sinte", "melodia": "lead_sierra",
              "extra": "crash"},
    "drumandbass": {"kit": "electronica", "bajo": None, "acordes": "pad_calido",
                    "melodia": None, "extra": "ride"},
    "breakbeat": {"kit": "potente", "bajo": "bajo_sinte",
                  "acordes": "pad_polisinte", "melodia": "lead_cuadrada",
                  "extra": "palmas"},
    "rock": {"kit": "potente", "bajo": "bajo_pua",
             "acordes": "guitarra_distorsion", "melodia": "guitarra_crunch",
             "extra": "crash"},
    "metal": {"kit": "potente", "bajo": "bajo_pua",
              "acordes": "guitarra_distorsion", "melodia": "guitarra_distorsion",
              "extra": "crash"},
    "punk": {"kit": "potente", "bajo": "bajo_pua", "acordes": "guitarra_crunch",
             "melodia": "guitarra_crunch", "extra": "crash"},
    "pop": {"kit": "normal", "bajo": "bajo_dedo", "acordes": "piano",
            "melodia": "cuerdas", "extra": "palmas"},
    "balada": {"kit": "escobillas", "bajo": "bajo_sin_trastes",
               "acordes": "piano", "melodia": "cuerdas", "extra": "pandereta"},
    "bolero": {"kit": "jazz", "bajo": "bajo_acustico",
               "acordes": "guitarra_espanola", "melodia": "cuerdas",
               "extra": "claves"},
    "rumba": {"kit": "normal", "bajo": "bajo_acustico",
              "acordes": "guitarra_espanola", "melodia": "guitarra_espanola",
              "extra": "palmas"},
    "cumbia": {"kit": "normal", "bajo": "bajo_dedo", "acordes": "acordeon",
               "melodia": "acordeon", "extra": "cabasa"},
    "salsa": {"kit": "normal", "bajo": "bajo_acustico", "acordes": "piano",
              "melodia": "metales", "extra": "claves"},
    "reggae": {"kit": "sala", "bajo": "bajo_dedo", "acordes": "organo",
               "melodia": "guitarra_limpia", "extra": "aro"},
    "funk": {"kit": "potente", "bajo": "bajo_slap", "acordes": "guitarra_limpia",
             "melodia": "metales", "extra": "palmas"},
    "disco": {"kit": "normal", "bajo": "bajo_dedo", "acordes": "cuerdas",
              "melodia": "piano_electrico", "extra": "palmas"},
    "lofi": {"kit": "escobillas", "bajo": "bajo_acustico",
             "acordes": "piano_electrico", "melodia": "vibrafono",
             "extra": "cabasa"},
    "blues": {"kit": "escobillas", "bajo": "bajo_acustico", "acordes": "organo",
              "melodia": "guitarra_jazz", "extra": "ride"},
    "vals": {"kit": "orquesta", "bajo": "cello", "acordes": "piano",
             "melodia": "cuerdas", "extra": "pandereta"},
}


# Trozos de bateria GRABADOS que trae LMMS, con su velocidad de verdad.
# (archivo, cuantos compases dura, a cuantas pulsaciones va)
#
# POR QUE ESTO IMPORTA MAS QUE NADA (02-09-2026): Angel dijo TRES veces que
# sonaba a politono. Y un politono es, literalmente, esto: un MIDI tocado por
# un banco General MIDI. Da igual lo buenas que sean las muestras; mientras la
# bateria este PROGRAMADA golpe a golpe suena a maquina. Un trozo grabado trae
# dentro el pulso de una persona, el sitio de los microfonos y la compresion
# del estudio donde se grabo. Eso no se programa.
LOOPS = {
    "house": ("beats/909beat01.ogg", 2, 121),
    "techno": ("beats/electro_beat01.ogg", 2, 120),
    "dance": ("beats/electro_beat02.ogg", 1, 120),
    "drumandbass": ("beats/jungle01.ogg", 2, 173),
    "breakbeat": ("beats/break02.ogg", 1, 140),
    # El hiphop NO lleva loop a proposito: el unico break que pega va a 167 y
    # el boom bap se toca a 94. Antes que meter una base al doble de velocidad,
    # se programa con su swing del 60%, que es como se hizo siempre.
}

# Desde el 04/09/2026 hay 13.244 trozos grabados en la carpeta del LMMS, con
# la velocidad escrita en el nombre. El modulo biblioteca los tiene indexados,
# asi que ya no hace falta renunciar al loop cuando Angel pide una velocidad
# concreta: casi siempre hay uno que ya va a esa velocidad. Los cinco de
# arriba se quedan de respaldo por si algun dia no estuviera la carpeta.
try:
    import biblioteca
except Exception:
    biblioteca = None


def _loop_grabado(estilo, bpm_pedido, bpm_estilo):
    """Un trozo grabado del estilo: (archivo, compases, velocidad) o None.

    Se busca primero a la velocidad que hace falta. Si a esa velocidad no hay
    nada y Angel NO ha pedido ninguna, se deja que la biblioteca proponga la
    suya. Si Angel SI la ha pedido, se devuelve None antes que colar un trozo
    a destiempo: un trozo grabado no se estira.
    """
    if biblioteca is None:
        return None
    try:
        az = random.Random("loop|%s|%d|%d" % (estilo, bpm_pedido, bpm_estilo))
        r = biblioteca.loop_para(estilo, bpm=(bpm_pedido or bpm_estilo), az=az)
        if r is None and not bpm_pedido:
            r = biblioteca.loop_para(estilo, az=az)
        return r
    except Exception:
        return None


def _buscar_estilo(texto):
    """Encuentra el estilo aunque se escriba con tildes, junto o a medias."""
    t = _sin_tildes(texto).strip()
    if not t:
        return None
    if t in ESTILOS:
        return t
    plano = t.replace(" ", "").replace("-", "").replace("&", "and")
    for nombre, e in ESTILOS.items():
        if plano == nombre:
            return nombre
        for a in e["alias"]:
            if _sin_tildes(a).replace(" ", "").replace("-", "") == plano:
                return nombre
    for nombre, e in ESTILOS.items():
        if nombre in plano:
            return nombre
        for a in e["alias"]:
            aa = _sin_tildes(a).replace(" ", "")
            if len(aa) >= 4 and aa in plano:
                return nombre
    return None


# --------------------------------------------------------------- mezclas
SEPARADORES = (" mezclado con ", " mezclada con ", " al estilo de ",
               " al estilo ", " con toque de ", " con toques de ",
               " con aire de ", " con ", " y ", " + ", "+", "/")


def _partir_mezcla(texto):
    """Saca los dos estilos de "rumba con rap" o "flamenco + trap"."""
    crudo = _sin_tildes(texto).strip()
    for sep in SEPARADORES:
        if sep in crudo:
            izq, der = crudo.split(sep, 1)
            a, b = _buscar_estilo(izq), _buscar_estilo(der)
            if a and b and a != b:
                return a, b
    return None, None


def _fusionar(base, ritmo):
    """Junta dos estilos con criterio. Devuelve (estilo, explicacion).

    LA REGLA, y por que esta: el PRIMERO que se nombra pone la musica (la
    escala, los acordes y los instrumentos) y el SEGUNDO pone el groove (la
    bateria, la velocidad y el swing). Asi, "rumba con rap" es una rumba
    -guitarra espanola, cadencia andaluza- sonando encima de un boom bap, que
    es lo que cualquiera entiende al decirlo. Al reves saldria otra cosa, y por
    eso el orden importa y se le dice a Angel.

    Lo que NO se hace es promediarlo todo: mezclar dos escalas o dos armonias
    no da un estilo nuevo, da un churro. Se coge cada cosa entera de donde
    tiene sentido.
    """
    a, b = ESTILOS[base], ESTILOS[ritmo]
    e = dict(a)

    # el groove entero, de una pieza
    for k in ("bombo", "caja", "charles", "extra", "muestras", "swing",
              "bajo", "tumbao", "compas"):
        if k in b:
            e[k] = b[k]
        elif k in e and k not in a:
            del e[k]
    e["alias"] = ()

    # la armonia y los instrumentos se quedan como estan (vienen de `a`)
    # el ritmo de los acordes tambien: es lo que mantiene el aire del estilo base
    e["acordes_ritmo"] = a["acordes_ritmo"]

    # La velocidad. Si el estilo del ritmo tiene un trozo grabado, manda el sin
    # discusion: un loop no se puede estirar. Si no, se busca un punto entre
    # los dos, tirando hacia el del ritmo, que es quien lleva el pulso.
    if ritmo in LOOPS:
        e["bpm"] = LOOPS[ritmo][2]
        nota_bpm = "a %d, que es a lo que va la base grabada de %s" % (
            e["bpm"], ritmo)
    else:
        e["bpm"] = int(round((2 * b["bpm"] + a["bpm"]) / 3.0))
        nota_bpm = ("a %d, entre las %d de %s y las %d de %s"
                    % (e["bpm"], a["bpm"], base, b["bpm"], ritmo))

    ins_a = INSTRUMENTOS.get(base, {})
    ins_b = INSTRUMENTOS.get(ritmo, {})
    mezcla_ins = dict(ins_a)
    mezcla_ins["kit"] = ins_b.get("kit", ins_a.get("kit"))
    mezcla_ins["extra"] = ins_b.get("extra", ins_a.get("extra"))

    explica = [
        "Mezcla de %s con %s:" % (base, ritmo),
        "  de %s: la escala %s, los acordes y los instrumentos (%s, %s y %s)"
        % (base, a["escala"].replace("_", " "),
           ins_a.get("bajo") or "bajo sinte",
           ins_a.get("acordes") or "acordes sinte",
           ins_a.get("melodia") or "melodia sinte"),
        "  de %s: la bateria (%s), el bajo y el swing"
        % (ritmo, ins_b.get("kit") or "normal"),
        "  velocidad: %s" % nota_bpm,
    ]
    return e, mezcla_ins, "\n".join(explica)


def estilos_de_musica():
    """La lista de estilos que sabe tocar, para decirsela a Angel."""
    fuera = []
    for nombre in sorted(ESTILOS):
        e = ESTILOS[nombre]
        fuera.append("%-13s %3d pulsaciones, %s (tambien: %s)"
                     % (nombre, e["bpm"], e["escala"].replace("_", " "),
                        ", ".join(e["alias"][:3])))
    return ("Estilos que se me dan (%d). Dime uno y te hago la cancion "
            "entera:\n\n" % len(ESTILOS)) + "\n".join("  " + l for l in fuera)


# ------------------------------------------------------------------ el XML
def _esc(t):
    return (str(t).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


ELDATA = (
    '<eldata fres="0.5" fcut="14000" ftype="0" fwet="0">'
    '<elvol syncmode="0" ctlenvamt="0" lspd_numerator="4" lspd="0.1" pdel="0"'
    ' hold="%s" lspd_denominator="4" rel="%s" userwavefile="" sustain="%s"'
    ' latt="0" dec="%s" att="%s" lamt="0" amt="1" lpdel="0" lshp="0" x100="0"/>'
    '<elcut syncmode="0" ctlenvamt="0" lspd_numerator="4" lspd="0.1" pdel="0"'
    ' hold="0.5" lspd_denominator="4" rel="0.1" userwavefile="" sustain="0.5"'
    ' latt="0" dec="0.5" att="0" lamt="0" amt="0" lpdel="0" lshp="0" x100="0"/>'
    '<elres syncmode="0" ctlenvamt="0" lspd_numerator="4" lspd="0.1" pdel="0"'
    ' hold="0.5" lspd_denominator="4" rel="0.1" userwavefile="" sustain="0.5"'
    ' latt="0" dec="0.5" att="0" lamt="0" amt="0" lpdel="0" lshp="0" x100="0"/>'
    '</eldata>')

RESTO_PISTA = (
    '<chordcreator chord-enabled="0" chord="0" chordrange="1"/>'
    '<arpeggiator arptime_denominator="4" arpmode="0" arpdir="0" arprange="1"'
    ' arp-enabled="0" arptime_numerator="4" arp="0" arpgate="100"'
    ' arptime="100" syncmode="0"/>'
    '<midiport outputchannel="1" inputcontroller="0" outputcontroller="0"'
    ' fixedoutputnote="-1" basevelocity="127" inputchannel="0" readable="0"'
    ' fixedinputvelocity="-1" writable="0" fixedoutputvelocity="-1"'
    ' outputprogram="1"/>')


def _efecto(nombre, dentro, wet="1"):
    return ('<effect name="%s" on="1" wet="%s" autoquit="0" gate="0"'
            ' autoquit_numerator="4" autoquit_denominator="4" syncmode="0">'
            '%s</effect>' % (nombre, wet, dentro))


def _reverb(tam=0.75, color=11000, wet="0.3"):
    """La reverb de LMMS. Comprobada: alarga la cola y abre el estereo.

    Es de lo que mas separa una maqueta de un politono: un sonido seco y
    centrado parece de telefono; el mismo con un poco de sala parece grabado.
    """
    return _efecto("reverbsc",
                   '<ReverbSCControls size="%s" color="%d" input_gain="0"'
                   ' output_gain="0"/>' % (tam, color), wet=wet)


def _cadena(efectos):
    if not efectos:
        return '<fxchain numofeffects="0" enabled="0"/>'
    return ('<fxchain numofeffects="%d" enabled="1">%s</fxchain>'
            % (len(efectos), "".join(efectos)))


def _notas_xml(notas):
    return "".join('<note pan="0" len="%d" key="%d" vol="%d" pos="%d"/>'
                   % (n[2], n[1], n[3], n[0]) for n in notas)


def _patrones_xml(patrones, tics_compas):
    """Un pattern por compas. Asi se ve la cancion por bloques en LMMS."""
    fuera = []
    for compas in sorted(patrones):
        notas = patrones[compas]
        if not notas:
            continue
        fuera.append('<pattern steps="16" len="%d" name="c%d" pos="%d"'
                     ' muted="0" type="1">%s</pattern>'
                     % (tics_compas, compas + 1, compas * tics_compas,
                        _notas_xml(notas)))
    return "".join(fuera)


def _pista_muestra(nombre, archivo, patrones, tics_compas, vol=100, pan=0,
                   efectos=()):
    """Una pista de percusion: un sonido de los que trae LMMS."""
    return ('<track name="%s" solo="0" muted="0" type="0">'
            '<instrumenttrack pan="%d" fxch="0" basenote="57" vol="%d"'
            ' pitchrange="1" usemasterpitch="1" pitch="0">'
            '<instrument name="audiofileprocessor">'
            '<audiofileprocessor amp="100" looped="0" sframe="0" lframe="0"'
            ' eframe="1" reversed="0" stutter="0" src="%s" interp="1"/>'
            '</instrument>%s%s%s</instrumenttrack>%s</track>'
            % (_esc(nombre), pan, vol, _esc(archivo),
               ELDATA % ("0.1", "0.1", "0.1", "0.2", "0"), RESTO_PISTA,
               _cadena(efectos), _patrones_xml(patrones, tics_compas)))


def _pista_sinte(nombre, patrones, tics_compas, onda=2, vol=100, pan=0,
                 basenote=57, att="0", dec="0.4", sus="0.6", hold="0.5",
                 rel="0.2", corte=14000, efectos=()):
    """Respaldo: oscilador pelado, por si faltara un preset."""
    tres = ('<tripleoscillator coarse0="0" coarse1="0" vol0="33" coarse2="0"'
            ' vol1="33" stphdetun0="0" vol2="33" wavetype0="%d" stphdetun1="0"'
            ' pan0="0" pan1="0" wavetype1="%d" stphdetun2="0" pan2="0"'
            ' wavetype2="%d" phoffset0="0" phoffset1="0" modalgo1="2"'
            ' phoffset2="0" modalgo2="2" modalgo3="2" userwavefile0=""'
            ' userwavefile1="" userwavefile2="" finel0="0" finer0="0"'
            ' finel1="0" finer1="0" finel2="0" finer2="0"/>' % (onda, onda, 0))
    el = (ELDATA % (hold, rel, sus, dec, att)).replace(
        'fcut="14000"', 'fcut="%d"' % corte)
    return ('<track name="%s" solo="0" muted="0" type="0">'
            '<instrumenttrack pan="%d" fxch="0" basenote="%d" vol="%d"'
            ' pitchrange="1" usemasterpitch="1" pitch="0">'
            '<instrument name="tripleoscillator">%s</instrument>%s%s%s'
            '</instrumenttrack>%s</track>'
            % (_esc(nombre), pan, basenote, vol, tres, el, RESTO_PISTA,
               _cadena(efectos), _patrones_xml(patrones, tics_compas)))


_CACHE_PRESET = {}


def _preset(rel):
    """Saca de un .xpf la cabecera y el cuerpo de su pista.

    ESTO ES LO QUE QUITA EL SONIDO A POLITONO. LMMS trae 125 presets en su
    propio formato, cada uno con su filtro, su envolvente y a veces sus
    efectos.

    DOS TRAMPAS que costaron un buen rato (02-09-2026):
      - Buscar "<instrumenttrack" SIN el espacio atrapa
        "<instrumenttracksettings", que es la etiqueta de fuera. El XML sale
        anidado y LMMS se cae con violacion de acceso, sin dar un solo mensaje.
      - Al recomponer hay que dejar el espacio ("<instrumenttrack " + atributos)
        o queda "<instrumenttrackpan=..." y no carga nada.
    """
    if rel in _CACHE_PRESET:
        return _CACHE_PRESET[rel]
    ruta = os.path.join(PRESETS, rel.replace("/", os.sep))
    resultado = None
    try:
        if os.path.exists(ruta):
            with io.open(ruta, encoding="utf-8", errors="replace") as f:
                t = f.read()
            m = re.search(r"<instrumenttrack\s(.*?)</instrumenttrack>", t, re.S)
            if m:
                cab, cuerpo = m.group(1).split(">", 1)
                if "<fxchain" not in cuerpo:
                    cuerpo += '<fxchain numofeffects="0" enabled="0"/>'
                resultado = (cab, cuerpo)
    except Exception:
        resultado = None
    _CACHE_PRESET[rel] = resultado
    return resultado


def _atributo(cab, nombre, valor):
    if re.search(r'\b%s="[^"]*"' % nombre, cab):
        return re.sub(r'\b%s="[^"]*"' % nombre, '%s="%s"' % (nombre, valor), cab)
    return cab + ' %s="%s"' % (nombre, valor)


def _meter_efectos(cuerpo, efectos):
    """Anade efectos a la cadena del preset, respetando la que ya tenia.

    POR QUE ASI Y NO CON UNA EXPRESION REGULAR (02-09-2026): al principio esto
    era un re.sub de "<fxchain.*?(?:/>|</fxchain>)". Parece inofensivo y no lo
    es: los presets buenos traen efectos LADSPA dentro, y esos llevan
    etiquetas que se cierran solas ("<port11 data=.../>"). El .*? paraba en la
    PRIMERA de esas barras, cortaba la cadena por la mitad y dejaba un XML
    roto. LMMS no decia nada: simplemente no renderizaba. De 23 estilos solo
    salian 6, y los que fallaban eran justo los de los presets mas trabajados.

    Ademas, ahora los efectos del preset SE CONSERVAN. Son parte de su sonido:
    la guitarra SEGuitar trae seis, y sin ellos no es una guitarra.
    """
    if not efectos:
        return cuerpo
    i = cuerpo.find("<fxchain")
    if i < 0:
        return cuerpo + _cadena(efectos)
    j = cuerpo.find(">", i)
    if j < 0:
        return cuerpo + _cadena(efectos)
    if cuerpo[j - 1] == "/":                      # cadena vacia
        return cuerpo[:i] + _cadena(efectos) + cuerpo[j + 1:]
    fin = cuerpo.find("</fxchain>", j)
    if fin < 0:
        return cuerpo + _cadena(efectos)
    apertura = cuerpo[i:j + 1]
    m = re.search(r'numofeffects="(\d+)"', apertura)
    cuantos = int(m.group(1)) if m else 0
    apertura = re.sub(r'numofeffects="\d+"',
                      'numofeffects="%d"' % (cuantos + len(efectos)), apertura)
    apertura = re.sub(r'enabled="\d+"', 'enabled="1"', apertura)
    return (cuerpo[:i] + apertura + cuerpo[j + 1:fin] + "".join(efectos)
            + cuerpo[fin:])


def _pista_preset(nombre, rel, patrones, tics_compas, vol=100, pan=0,
                  basenote=None, efectos=(), onda_respaldo=2):
    """Pista con un preset de LMMS. Si faltara, tira del oscilador pelado."""
    p = _preset(rel)
    if not p:
        return _pista_sinte(nombre, patrones, tics_compas, onda=onda_respaldo,
                            vol=vol, pan=pan, efectos=efectos)
    cab, cuerpo = p
    cab = _atributo(cab, "vol", int(vol))
    cab = _atributo(cab, "pan", int(pan))
    if basenote is not None:
        cab = _atributo(cab, "basenote", int(basenote))
    cuerpo = _meter_efectos(cuerpo, efectos)
    return ('<track name="%s" solo="0" muted="0" type="0">'
            '<instrumenttrack %s>%s</instrumenttrack>%s</track>'
            % (_esc(nombre), cab, cuerpo, _patrones_xml(patrones, tics_compas)))


# ------------------------------------------------- instrumentos de verdad

# Bancos de sonidos, del que mejor suena al que peor. Se coge el primero que
# exista, asi que si algun dia se borra uno, Berna sigue funcionando con el
# siguiente. Los tres son libres: se puede publicar lo que se componga.
#
#   MuseScore General  206 MB, 272 instrumentos. El que mejor suena, sobre
#                      todo cuerdas, vientos y pianos. Come mas memoria.
#   GeneralUser GS      31 MB, 274 instrumentos. Casi tan bueno y ocupa
#                      siete veces menos. Es el de emergencia en un portatil
#                      justo de RAM como este.
#   FluidR3 GM         141 MB, 158 instrumentos. El de toda la vida.
BANCOS = (
    r"C:\Users\alaga\Documents\lmms\samples\soundfonts\MuseScore_General.sf2",
    r"C:\Users\alaga\Documents\lmms\samples\soundfonts\GeneralUser-GS.sf2",
    os.path.join(BASE, "sonidos", "FluidR3_GM.sf2"),
)


def _mejor_banco():
    for b in BANCOS:
        if os.path.exists(b):
            return b
    return BANCOS[-1]


SONIDOS = _mejor_banco()

# Los numeros del estandar General MIDI. No son un capricho: son los mismos
# que usa cualquier teclado o programa de musica del mundo desde 1991, y por
# eso el banco de sonidos los entiende sin que haya que configurar nada.
GM = {
    "piano": 0, "piano_electrico": 4, "vibrafono": 11, "organo": 16,
    "organo_rock": 18, "organo_iglesia": 19, "acordeon": 21,
    "guitarra_espanola": 24, "guitarra_acustica": 25, "guitarra_jazz": 26,
    "guitarra_limpia": 27, "guitarra_crunch": 29, "guitarra_distorsion": 30,
    "bajo_acustico": 32, "bajo_dedo": 33, "bajo_pua": 34, "bajo_sin_trastes": 35,
    "bajo_slap": 36, "bajo_sinte": 38, "bajo_sinte2": 39,
    "violin": 40, "cello": 42, "cuerdas": 48, "cuerdas2": 49,
    "cuerdas_sinte": 51, "coro": 52,
    "trompeta": 56, "trombon": 57, "metales": 61,
    "saxo_alto": 65, "saxo_tenor": 66, "clarinete": 71, "flauta": 73,
    "lead_cuadrada": 80, "lead_sierra": 81,
    "pad_calido": 89, "pad_polisinte": 91, "pad_nuevaera": 88,
}

# Las baterias que trae el banco, en el canal de percusion (banco 128)
KITS = {"normal": 0, "sala": 8, "potente": 16, "electronica": 24,
        "808": 25, "jazz": 32, "escobillas": 40, "orquesta": 48}

# Donde esta cada golpe dentro de una bateria General MIDI
GOLPE = {
    "bombo": 36, "bombo2": 35, "caja": 38, "caja2": 40, "aro": 37,
    "palmas": 39, "charles": 42, "charles_pedal": 44, "charles_abierto": 46,
    "crash": 49, "ride": 51, "campana": 53, "pandereta": 54, "cencerro": 56,
    "bongo_agudo": 60, "bongo_grave": 61, "conga_alta": 62, "conga_abierta": 63,
    "conga_grave": 64, "timbal_alto": 65, "timbal_grave": 66,
    "cabasa": 69, "maracas": 70, "claves": 75, "caja_china": 76,
    "tom_grave": 41, "tom_medio": 45, "tom_alto": 48,
}

# ---------------------------------------------------------------- percusion
# Hasta el 04/09/2026 la pista de percusion tenia DOS sonidos: el charles y un
# adorno. Con eso las canciones sonaban planas, y con razon: de los 29 golpes
# de arriba se usaban dos. Aqui se anaden las capas que hacen que un tema
# suene tocado por gente y no por una caja de ritmos.
#
# Cada capa es (golpe, patron de 16 pasos, volumen, nivel minimo). El nivel es
# el de la seccion: 1 es la entrada, 4 el estribillo. Asi la percusion CRECE
# con la cancion en vez de estar siempre igual, que es la otra mitad del
# problema de que sonara insipida.
PERCU = {
    # Latino: la conga marca el "y" del tiempo, las maracas rellenan en
    # semicorcheas y la clave manda. Es el esqueleto de todo lo caribeno.
    "latino": (
        ("conga_abierta", "..x..x.x..x..x.x", 70, 2),
        ("conga_grave",   "x.......x.......", 58, 3),
        ("maracas",       "xxxxxxxxxxxxxxxx", 40, 2),
        ("claves",        "x..x..x...x.x...", 62, 3),
        ("bongo_agudo",   "....x.......x..x", 52, 4),
    ),
    # Electronico: nada de congas. Cabasa y pandereta abriendo el estereo,
    # palmas reforzando el 2 y el 4, que es lo que hace bailar.
    "electronico": (
        ("cabasa",    "..x...x...x...x.", 52, 2),
        ("palmas",    "....x.......x...", 66, 3),
        ("pandereta", "x.x.x.x.x.x.x.x.", 38, 3),
        ("cencerro",  "........x.......", 46, 4),
    ),
    # Banda: pandereta y aro, discretos, como en un disco de pop o de rock.
    "banda": (
        ("pandereta", "..x...x...x...x.", 48, 2),
        ("aro",       "....x.......x...", 44, 3),
        ("palmas",    "....x.......x...", 40, 4),
    ),
}

# A que familia pertenece cada estilo. Lo que no este aqui va a "banda", que
# es la mas discreta y no estropea nada.
FAMILIA = {
    "reggaeton": "latino", "salsa": "latino", "rumba": "latino",
    "cumbia": "latino", "bolero": "latino", "reggae": "latino",
    "house": "electronico", "techno": "electronico", "dance": "electronico",
    "trap": "electronico", "hiphop": "electronico", "disco": "electronico",
    "funk": "electronico", "breakbeat": "electronico",
    "drumandbass": "electronico", "lofi": "electronico",
}


def _capas_percusion(estilo):
    return PERCU.get(FAMILIA.get(estilo, "banda"), PERCU["banda"])


def _pista_sf2(nombre, programa, patrones, tics_compas, banco=0, vol=100,
               pan=0, efectos=(), reverb_propia=0):
    """Una pista tocada con un instrumento GRABADO del banco de sonidos.

    POR QUE ESTO ES LO QUE FALTABA (02-09-2026): Angel dijo dos veces que las
    canciones sonaban a politono, y tenia razon las dos. El fallo no estaba en
    como se colocaban las notas: estaba en que un piano hecho con osciladores
    no es un piano, es un pitido con forma de piano. LMMS trae el reproductor
    (sf2player) pero venia sin sonidos. Con el banco FluidR3 (141 MB de
    instrumentos grabados por musicos) suena una guitarra espanola de verdad,
    un bajo de verdad y una bateria de verdad.

    El banco 128 es la percusion: ahi cada NOTA es un golpe distinto (el 36 es
    el bombo, el 38 la caja, el 42 el charles...), asi que una sola pista toca
    la bateria entera, como un bateria de carne y hueso.
    """
    return ('<track name="%s" solo="0" muted="0" type="0">'
            '<instrumenttrack pan="%d" fxch="0" basenote="57" vol="%d"'
            ' pitchrange="1" usemasterpitch="1" pitch="0">'
            '<instrument name="sf2player">'
            '<sf2player src="%s" bank="%d" patch="%d" gain="1" reverbOn="%d"'
            ' reverbRoomSize="0.4" reverbDamping="0.3" reverbWidth="0.6"'
            ' reverbLevel="0.7" chorusOn="0" chorusNum="3" chorusLevel="2"'
            ' chorusSpeed="0.3" chorusDepth="8"/>'
            '</instrument>%s%s%s</instrumenttrack>%s</track>'
            % (_esc(nombre), pan, vol, _esc(SONIDOS), banco, programa,
               1 if reverb_propia else 0,
               ELDATA % ("0.5", "0.3", "0.75", "0.6", "0"), RESTO_PISTA,
               _cadena(efectos), _patrones_xml(patrones, tics_compas)))


def _hay_sonidos():
    return os.path.exists(SONIDOS)


# ------------------------------------------------------------ el master
def _ladspa(archivo, plugin, puertos):
    """Un efecto de los LADSPA que trae LMMS.

    El bloque <key> es lo que le dice a LMMS que DLL abrir y que plugin de
    dentro usar. Sin el, el efecto se carga vacio y no hace nada.
    """
    ctrl = "".join('<port0%d data="%s"/>' % (i, v) for i, v in puertos.items())
    return ('<effect name="ladspaeffect" on="1" wet="1" autoquit="0" gate="0"'
            ' autoquit_numerator="4" autoquit_denominator="4" syncmode="0">'
            '<ladspacontrols ports="%d">%s</ladspacontrols>'
            '<key><attribute name="file" value="%s"/>'
            '<attribute name="plugin" value="%s"/></key></effect>'
            % (len(puertos), ctrl, archivo, plugin))


def _cadena_master():
    """Compresor y limitador, que es lo que hace que una mezcla suene a disco.

    POR QUE (02-09-2026): con los instrumentos grabados la cancion sonaba bien
    pero FLOJA: nivel medio 0,09 cuando cualquier cosa que pongas al lado anda
    por 0,2. La culpa la tienen los picos: el golpe de la caja llega al techo y
    no deja subir el resto. Eso es exactamente para lo que existe un limitador.

    Medido: sin nada 0,093. Con compresor mas limitador a +6 dB, 0,215 de nivel
    medio, pico 0,89 y CERO saturacion. Mas del doble de volumen sin que cruja.
    El compresor va antes para pegar la mezcla, y el limitador detras para que
    nada se salga.
    """
    compresor = _ladspa("sc4_1882", "sc4",
                        {1: "0.03", 2: "0.2", 3: "-16", 4: "3", 5: "0", 6: "3"})
    limitador = _ladspa("fast_lookahead_limiter_1913", "fastLookaheadLimiter",
                        {0: "6", 1: "-1", 2: "0.2"})
    return [compresor, limitador]


def _proyecto(bpm, numerador, pistas, titulo, compases=32):
    return ('<?xml version="1.0"?>\n<!DOCTYPE lmms-project>\n'
            '<lmms-project creator="Berna" version="1.0" type="song"'
            ' creatorversion="1.2.2">\n'
            '<head timesig_numerator="%d" bpm="%d" timesig_denominator="4"'
            ' mastervol="%d" masterpitch="0"/>\n<song>\n'
            '<trackcontainer visible="1" maximized="0" x="5" minimized="0"'
            ' y="5" width="1200" height="600" type="song">\n%s\n'
            '</trackcontainer>\n'
            '<fxmixer><fxchannel num="0" name="Master" volume="1" muted="0">'
            '%s</fxchannel></fxmixer>\n'
            '<timeline lp0pos="0" lpstate="0" lp1pos="%d"/>\n'
            '<controllerrackview visible="0" maximized="0" x="700" y="200"'
            ' minimized="0" width="350" height="200"/>\n'
            '<pianoroll visible="0" maximized="0" x="5" y="266" minimized="0"'
            ' width="800" height="480"/>\n'
            '<automationeditor visible="0" maximized="0" x="0" y="0"'
            ' minimized="0" width="640" height="480"/>\n'
            '<projectnotes visible="0" maximized="0" x="830" y="20"'
            ' minimized="0" width="330" height="200"/>\n'
            '<controllers/>\n</song>\n</lmms-project>\n'
            % (numerador, bpm, VOLUMEN_MAESTRO, pistas,
               _cadena(_cadena_master()), 48 * numerador))


# --------------------------------------------------------------- humanizar
def _humanizar(notas, az, fuerza=1.0, swing=0.0, tic_paso=12):
    """Le quita la rigidez de maquina: ni el volumen ni el tiempo son exactos.

    POR QUE: todas las notas al mismo volumen y clavadas en la reja es
    EXACTAMENTE lo que hace un politono. Un musico acentua unas y roza otras, y
    nunca cae en el tic justo. Tres cosas:
      - acento: fuerte en el pulso, mas flojo entre pulsos.
      - temblor: uno o dos tics arriba o abajo, distinto en cada nota.
      - swing: la segunda corchea de cada pulso se retrasa. Es lo que hace que
        el hiphop, el blues o el funk suenen a swing y no a metronomo.
    """
    fuera = []
    for pos, key, largo, vol in notas:
        paso = pos // tic_paso if tic_paso else 0
        if paso % 4 == 0:
            acento = 1.0
        elif paso % 2 == 0:
            acento = 0.86
        else:
            acento = 0.74
        v = vol * (acento + az.uniform(-0.06, 0.06) * fuerza)
        p = pos
        if swing and paso % 2 == 1:
            p += int(round(tic_paso * swing * 0.5))
        p += int(round(az.uniform(-1.5, 1.5) * fuerza))
        fuera.append((max(0, p), key, max(3, largo), int(max(20, min(200, v)))))
    return fuera


# ------------------------------------------------------------- el arreglo
def _secciones(compases):
    """Reparte la cancion en secciones de verdad, no un bucle repetido.

    Devuelve (nombre, nivel) por compas. El nivel manda que capas suenan: 0
    casi nada, 4 todo. Lo que hace que algo parezca una cancion y no una base
    es que entre y salga gente.
    """
    plan = []
    bloque = 4 if compases <= 16 else 8
    plan += [("entrada", 0)] * min(max(2, bloque // 2), compases)
    turno = 0
    while len(plan) < compases - bloque // 2:
        quedan = compases - bloque // 2 - len(plan)
        n = min(bloque, quedan)
        plan += ([("estrofa", 2)] * n if turno % 2 == 0
                 else [("estribillo", 4)] * n)
        turno += 1
    plan += [("final", 1)] * max(0, compases - len(plan))
    plan = plan[:compases]
    # el compas justo antes del estribillo se vacia, para que entre con fuerza
    for i in range(1, len(plan)):
        if plan[i][0] == "estribillo" and plan[i - 1][0] == "estrofa":
            plan[i - 1] = ("subida", 1)
    return plan


def _motivo(az, pasos):
    """Un motivo melodico: el mismo dibujo que vuelve, en vez de notas al azar.

    POR QUE: una melodia inventada nota a nota suena a que alguien trastea. Lo
    que hace que una melodia se reconozca es que hay una frase corta que se
    repite y se varia. Aqui se saca un ritmo y un dibujo de alturas, y luego se
    reusan sobre cada acorde.
    """
    duraciones, sitio = [], 0
    while sitio < pasos:
        d = az.choice([2, 2, 2, 4, 4, 6])
        if sitio + d > pasos:
            d = pasos - sitio
        duraciones.append((sitio, d))
        sitio += d
    dibujo = [az.choice([0, 0, 1, 2, 2, 4, -1]) for _ in duraciones]
    return [(s, d, g) for (s, d), g in zip(duraciones, dibujo)]


# ------------------------------------------------------------------ componer
def componer(estilo, compases=32, tono="", bpm=0, permiso=None):
    r"""El cerebro musical de Berna, SIN atarlo a LMMS.

    Hace exactamente lo mismo que el principio de `crear_cancion` (mismo
    estilo, misma clave de son, mismo tumbao, mismo bombeo, misma cadencia
    andaluza) pero en vez de acabar escribiendo un proyecto de LMMS, devuelve
    los datos en crudo: los patrones de percusion y las notas de cada
    instrumento, por compas, en TICS (48 por pulso, como todo en este
    modulo). Con esto, cualquier otro programa que sepa tocar notas -REAPER,
    por ejemplo- puede usar el MISMO criterio musical sin que Berna tenga que
    aprenderselo dos veces.

    ESTO ES UNA COPIA A PROPOSITO, no una funcion compartida con
    `crear_cancion` (03-09-2026). Tocar esa funcion para que las dos tiraran
    de aqui se arriesgaba a romper un pipeline de LMMS ya medido nota a nota
    con Angel. Si algun dia se cambia el criterio musical (un estilo, un
    acorde, el bombeo...), hay que cambiarlo EN LOS DOS SITIOS.

    Devuelve un diccionario con:
      clave, e, ins, titulo, pulsaciones, numerador, compases, tics_compas,
      tic_paso, raiz, escala, loop, plan (secciones), explicacion_mezcla, y
      los patrones por instrumento (bombo, caja, charles, extra, sub, bajo,
      acordes, melodia), cada uno {compas: [(pos_tics, nota_o_golpe, dur_tics,
      volumen), ...]}.

    O, si el estilo no existe, un texto de error (str) en vez del diccionario.
    """
    mezcla_de, mezcla_con = _partir_mezcla(estilo)
    explicacion_mezcla = ""
    ins_mezcla = None
    if mezcla_de:
        clave = mezcla_de
        e, ins_mezcla, explicacion_mezcla = _fusionar(mezcla_de, mezcla_con)
    else:
        clave = _buscar_estilo(estilo)
        if not clave:
            return ("No conozco el estilo '%s'. Pideme estilos_de_musica y te "
                    "digo los %d que me se. Y si quieres, mezclo dos: "
                    "'rumba con rap', 'flamenco con trap'."
                    % (estilo, len(ESTILOS)))
        e = ESTILOS[clave]

    try:
        compases = max(8, min(96, int(float(compases))))
    except Exception:
        compases = 32
    numerador = int(e.get("compas", 4))
    pasos = 4 * numerador
    tics_compas = TICS_PULSO * numerador
    tic_paso = tics_compas // pasos

    estilo_loop = mezcla_con if mezcla_de else clave
    try:
        pedido = int(float(bpm)) if bpm else 0
    except Exception:
        pedido = 0
    try:
        propia = int(e["bpm"])
    except Exception:
        propia = 120
    loop = _loop_grabado(estilo_loop, pedido, propia)
    if loop is None:
        loop = LOOPS.get(estilo_loop)
        if loop and pedido:
            loop = None
    pulsaciones = loop[2] if loop else (pedido or propia)
    pulsaciones = max(40, min(240, pulsaciones))

    raiz = NOTAS.get(_sin_tildes(tono).replace(" ", ""), None)
    if raiz is None:
        raiz = 0 if e["escala"] in ("mayor", "blues") else 9
    escala = ESCALAS[e["escala"]]
    septima = bool(e.get("septimas"))
    swing = float(e.get("swing", 0.0))

    titulo = ("%s con %s" % (mezcla_de, mezcla_con)) if mezcla_de else \
        ("%s de Berna" % clave)

    az = random.Random("%s|%s|%d|%d" % (clave, titulo, compases, pulsaciones))
    plan = _secciones(compases)
    prog = e["acordes"]
    motivo = _motivo(az, pasos)

    bombo, caja, charles, extra = {}, {}, {}, {}
    bajo, acordes, melodia = {}, {}, {}

    def _patrones_de(c):
        return (_p(e["bombo"], c, pasos), _p(e["caja"], c, pasos),
                _p(e["charles"], c, pasos), _p(e["extra"][1], c, pasos),
                _p(e["bajo"], c, pasos), _p(e["acordes_ritmo"], c, pasos))

    ins = ins_mezcla if ins_mezcla is not None else INSTRUMENTOS.get(clave, {})
    con_banco = _hay_sonidos()
    N_BOMBO = GOLPE["bombo"]
    N_CAJA = GOLPE["caja"]
    N_CHARLES = GOLPE["charles"]
    N_EXTRA = GOLPE.get(ins.get("extra") or "palmas", GOLPE["palmas"])
    PERC = 36 + raiz
    sub = {}
    voces_antes = None
    for c in range(compases):
        seccion, nivel = plan[c]
        (p_bombo, p_caja, p_charles, p_extra,
         p_bajo, p_acordes) = _patrones_de(c)
        pasos_bombo = set(p_bombo)
        grado = prog[c % len(prog)]
        voces = _voces(escala, grado, septima, raiz, voces_antes,
                       quinto_mayor=bool(e.get("quinto_mayor")))
        voces_antes = voces
        fundamental = voces[0] - 24

        if nivel >= 1:
            bombo[c] = _humanizar([(p * tic_paso, N_BOMBO if con_banco else PERC, 10, 100)
                                   for p in p_bombo], az, 0.7, 0, tic_paso)
        if nivel >= 2:
            n = [(p * tic_paso, N_CAJA if con_banco else PERC, 10, 96) for p in p_caja]
            for p in range(pasos):
                if p not in p_caja and az.random() < 0.10:
                    n.append((p * tic_paso, N_CAJA if con_banco else PERC, 8, 34))
            caja[c] = _humanizar(n, az, 1.0, swing, tic_paso)
            charles[c] = _humanizar([(p * tic_paso, N_CHARLES if con_banco else PERC, 6, 78)
                                     for p in p_charles], az, 1.0, swing,
                                    tic_paso)
        if nivel >= 4:
            extra[c] = _humanizar([(p * tic_paso, N_EXTRA if con_banco else PERC, 10, 82)
                                   for p in p_extra], az, 1.0, swing, tic_paso)
        if seccion == "subida":
            caja[c] = _humanizar(
                [((pasos - 6 + k) * tic_paso,
                  (GOLPE["tom_grave"], GOLPE["tom_medio"], GOLPE["tom_alto"])[k % 3]
                  if con_banco else PERC, 8, 60 + k * 12)
                 for k in range(6)], az, 0.6, 0, tic_paso)

        if nivel >= 1:
            n = []
            siguiente = _voces(escala, prog[(c + 1) % len(prog)], septima, raiz,
                               voces, quinto_mayor=bool(e.get("quinto_mayor")))
            for j, p in enumerate(p_bajo):
                nota = fundamental
                if e.get("tumbao"):
                    if p >= pasos * 3 // 4:
                        nota = siguiente[0] - 24
                    elif p >= pasos // 4:
                        nota = fundamental + 7
                elif j and j % 4 == 3:
                    nota += 7
                elif j and az.random() < 0.12:
                    nota += 12 if az.random() < 0.5 else -5
                largo = tic_paso * (3 if nivel >= 3 else 2)
                n.append((p * tic_paso, nota, largo, 98))
            bajo[c] = _humanizar(n, az, 0.8, swing, tic_paso)
            sub[c] = [(p * tic_paso, max(24, fundamental - 12),
                       tic_paso * 3, 88) for p in p_bombo]

        if nivel >= 1:
            largo = max(tic_paso * 2, tics_compas // max(1, len(p_acordes)) - 6)
            n = []
            for p in p_acordes:
                choca = p in pasos_bombo
                fuerza = 34 if choca else (66 if nivel >= 2 else 52)
                for tono_nota in voces:
                    n.append((p * tic_paso, tono_nota, largo, fuerza))
            acordes[c] = _humanizar(n, az, 0.6, swing, tic_paso)

        if seccion == "estribillo" and e.get("melodia"):
            n = []
            for sitio, dura, escalon in motivo:
                if az.random() < 0.45:
                    continue
                g = grado + escalon
                nota = 72 + raiz + _grado(escala, g)
                while nota > 84:
                    nota -= 12
                n.append((sitio * tic_paso, nota, dura * tic_paso - 4, 84))
            melodia[c] = _humanizar(n, az, 0.9, swing, tic_paso)

    return {
        "clave": clave, "e": e, "ins": ins, "titulo": titulo,
        "pulsaciones": pulsaciones, "numerador": numerador,
        "compases": compases, "tics_compas": tics_compas,
        "tic_paso": tic_paso, "raiz": raiz, "escala": escala,
        "septima": septima, "loop": loop, "plan": plan,
        "explicacion_mezcla": explicacion_mezcla,
        "bombo": bombo, "caja": caja, "charles": charles, "extra": extra,
        "sub": sub, "bajo": bajo, "acordes": acordes, "melodia": melodia,
    }


def crear_cancion(estilo, nombre="", compases=32, tono="", bpm=0,
                  abrir="si", permiso=None):
    r"""Compone una cancion entera del estilo que le digan y la deja en LMMS."""
    mezcla_de, mezcla_con = _partir_mezcla(estilo)
    explicacion_mezcla = ""
    ins_mezcla = None
    if mezcla_de:
        clave = mezcla_de
        e, ins_mezcla, explicacion_mezcla = _fusionar(mezcla_de, mezcla_con)
    else:
        clave = _buscar_estilo(estilo)
        if not clave:
            return ("No conozco el estilo '%s'. Pideme estilos_de_musica y te "
                    "digo los %d que me se. Y si quieres, mezclo dos: "
                    "'rumba con rap', 'flamenco con trap'."
                    % (estilo, len(ESTILOS)))
        e = ESTILOS[clave]

    try:
        compases = max(8, min(96, int(float(compases))))
    except Exception:
        compases = 32
    numerador = int(e.get("compas", 4))
    pasos = 4 * numerador
    tics_compas = TICS_PULSO * numerador
    tic_paso = tics_compas // pasos

    estilo_loop = mezcla_con if mezcla_de else clave
    try:
        pedido = int(float(bpm)) if bpm else 0
    except Exception:
        pedido = 0
    try:
        propia = int(e["bpm"])
    except Exception:
        propia = 120
    # Un trozo grabado NO se puede estirar: o va a su velocidad o suena a
    # destiempo. Antes eso obligaba a renunciar al loop en cuanto Angel pedia
    # una velocidad. Ahora se busca en la biblioteca uno que YA vaya a esa
    # velocidad, que casi siempre lo hay; solo si no lo hay se renuncia.
    loop = _loop_grabado(estilo_loop, pedido, propia)
    if loop is None:
        loop = LOOPS.get(estilo_loop)
        if loop and pedido:
            loop = None
    pulsaciones = loop[2] if loop else (pedido or propia)
    pulsaciones = max(40, min(240, pulsaciones))

    raiz = NOTAS.get(_sin_tildes(tono).replace(" ", ""), None)
    if raiz is None:
        raiz = 0 if e["escala"] in ("mayor", "blues") else 9
    escala = ESCALAS[e["escala"]]
    septima = bool(e.get("septimas"))
    swing = float(e.get("swing", 0.0))

    titulo = str(nombre or "").strip() or (
        ("%s con %s" % (mezcla_de, mezcla_con)) if mezcla_de
        else ("%s de Berna" % clave))

    aviso = ("Berna va a componer una cancion:\n\n"
             "  estilo: %s\n  ritmo: %d pulsaciones por minuto\n"
             "  duracion: %d compases (medio minuto largo)\n"
             "  se guarda en: %s\n\n"
             "Tarda unos segundos porque la comprueba escuchandola. Le dejas?"
             % (clave, pulsaciones, compases, _carpeta_musica()))
    if permiso is not None and not permiso(aviso):
        return "No me has dado permiso, no he compuesto nada."

    az = random.Random("%s|%s|%d|%d" % (clave, titulo, compases, pulsaciones))
    plan = _secciones(compases)
    prog = e["acordes"]
    motivo = _motivo(az, pasos)

    bombo, caja, charles, extra = {}, {}, {}, {}
    percu = {}
    bajo, acordes, melodia = {}, {}, {}

    # se recalculan compas a compas porque la clave cambia de un compas al otro
    def _patrones_de(c):
        return (_p(e["bombo"], c, pasos), _p(e["caja"], c, pasos),
                _p(e["charles"], c, pasos), _p(e["extra"][1], c, pasos),
                _p(e["bajo"], c, pasos), _p(e["acordes_ritmo"], c, pasos))

    p_bombo, p_caja, p_charles, p_extra, p_bajo, p_acordes = _patrones_de(0)

    ins = ins_mezcla if ins_mezcla is not None else INSTRUMENTOS.get(clave, {})
    con_banco = _hay_sonidos()
    # En una bateria General MIDI cada NOTA es un golpe distinto, asi que una
    # sola pista toca la bateria entera, como un bateria de verdad. Sin banco
    # de sonidos se sigue tirando de las muestras sueltas de siempre.
    N_BOMBO = GOLPE["bombo"]
    N_CAJA = GOLPE["caja"]
    N_CHARLES = GOLPE["charles"]
    N_EXTRA = GOLPE.get(ins.get("extra") or "palmas", GOLPE["palmas"])
    PERC = 36 + raiz
    sub = {}
    pasos_bombo = set(p_bombo)
    voces_antes = None
    for c in range(compases):
        seccion, nivel = plan[c]
        (p_bombo, p_caja, p_charles, p_extra,
         p_bajo, p_acordes) = _patrones_de(c)
        pasos_bombo = set(p_bombo)
        grado = prog[c % len(prog)]
        voces = _voces(escala, grado, septima, raiz, voces_antes,
                       quinto_mayor=bool(e.get("quinto_mayor")))
        voces_antes = voces
        fundamental = voces[0] - 24          # el bajo, dos octavas por debajo

        # ---------------------------------------------------------- percusion
        if nivel >= 1:
            bombo[c] = _humanizar([(p * tic_paso, N_BOMBO if con_banco else PERC, 10, 100)
                                   for p in p_bombo], az, 0.7, 0, tic_paso)
        if nivel >= 2:
            n = [(p * tic_paso, N_CAJA if con_banco else PERC, 10, 96) for p in p_caja]
            # golpes fantasma: los flojitos entre medias, que es lo que da groove
            for p in range(pasos):
                if p not in p_caja and az.random() < 0.10:
                    n.append((p * tic_paso, N_CAJA if con_banco else PERC, 8, 34))
            caja[c] = _humanizar(n, az, 1.0, swing, tic_paso)
            charles[c] = _humanizar([(p * tic_paso, N_CHARLES if con_banco else PERC, 6, 78)
                                     for p in p_charles], az, 1.0, swing,
                                    tic_paso)
        # El adorno entraba solo en el nivel 4, o sea casi nunca: la cancion
        # se pasaba entera con bombo, caja y charles pelados. Desde el nivel 2
        # ya suena, que es donde empieza a hacer falta (04-09-2026).
        if nivel >= 2:
            extra[c] = _humanizar([(p * tic_paso, N_EXTRA if con_banco else PERC, 10, 82)
                                   for p in p_extra], az, 1.0, swing, tic_paso)

        # Las capas de percusion de verdad: congas, maracas, claves... Cada una
        # entra en su nivel, asi la cancion crece en vez de estar siempre igual.
        if con_banco:
            n_percu = []
            for golpe, patron, volumen, desde in _capas_percusion(clave):
                if nivel < desde:
                    continue
                for p in _p(patron, c, pasos):
                    # el volumen baila un poco en cada golpe: si van todos
                    # clavados al mismo suena a maquina
                    v = max(20, min(120, volumen + az.randint(-9, 9)))
                    n_percu.append((p * tic_paso, GOLPE[golpe], 8, v))
            if n_percu:
                percu[c] = _humanizar(n_percu, az, 1.0, swing, tic_paso)

        # redoble en el compas de subida
        if seccion == "subida":
            caja[c] = _humanizar(
                [((pasos - 6 + k) * tic_paso,
                  (GOLPE["tom_grave"], GOLPE["tom_medio"], GOLPE["tom_alto"])[k % 3]
                  if con_banco else PERC, 8, 60 + k * 12)
                 for k in range(6)], az, 0.6, 0, tic_paso)

        # -------------------------------------------------------------- bajo
        if nivel >= 1:
            n = []
            siguiente = _voces(escala, prog[(c + 1) % len(prog)], septima, raiz,
                               voces, quinto_mayor=bool(e.get("quinto_mayor")))
            for j, p in enumerate(p_bajo):
                nota = fundamental
                if e.get("tumbao"):
                    # EL TUMBAO. En el "y" del 2 suena la quinta; en el 4 suena
                    # ya la nota del acorde SIGUIENTE. Por eso la salsa empuja
                    # hacia delante en vez de marcar como una marcha militar.
                    if p >= pasos * 3 // 4:
                        nota = siguiente[0] - 24
                    elif p >= pasos // 4:
                        nota = fundamental + 7
                elif j and j % 4 == 3:
                    nota += 7                      # la quinta, para respirar
                elif j and az.random() < 0.12:
                    nota += 12 if az.random() < 0.5 else -5
                largo = tic_paso * (3 if nivel >= 3 else 2)
                n.append((p * tic_paso, nota, largo, 98))
            bajo[c] = _humanizar(n, az, 0.8, swing, tic_paso)
            # EL SUB. Una onda casi pura debajo de todo, en el sitio del bombo.
            # Es lo que se siente en el pecho y lo que NINGUN politono tenia:
            # un movil no podia dar esas frecuencias, asi que la musica hecha
            # para movil no las llevaba. Sin esto, por buenos que sean los
            # instrumentos, el tema suena a "pequeno".
            sub[c] = [(p * tic_paso, max(24, fundamental - 12),
                       tic_paso * 3, 88) for p in p_bombo]

        # ------------------------------------------------------------ acordes
        if nivel >= 1:
            largo = max(tic_paso * 2, tics_compas // max(1, len(p_acordes)) - 6)
            n = []
            for p in p_acordes:
                # EL BOMBEO. En cuanto pega el bombo, todo lo demas se aparta y
                # vuelve a entrar. Es la respiracion de casi toda la musica de
                # hoy, y es de lo que mas la separa de un politono, que sonaba
                # todo apelmazado y al mismo volumen. Aqui se hace bajando el
                # golpe que coincide con el bombo y dejando crecer al siguiente.
                choca = p in pasos_bombo
                fuerza = 34 if choca else (66 if nivel >= 2 else 52)
                for tono in voces:
                    n.append((p * tic_paso, tono, largo, fuerza))
                # ENSANCHAR EL ACORDE (04-09-2026). Las voces caian dentro de
                # una octava escasa. Se ensancha SOLO HACIA ARRIBA: se probo a
                # doblar tambien la fundamental una octava por debajo y fue un
                # error medible, porque la mezcla ya tenia el 94% de la energia
                # amontonada en los graves y aquello la enterro mas. Lo que le
                # falta a esta musica son agudos, no graves.
                if nivel >= 2:
                    n.append((p * tic_paso, voces[-1] + 12, largo,
                              max(20, fuerza - 14)))
            acordes[c] = _humanizar(n, az, 0.6, swing, tic_paso)

        # ----------------------------------------------------------- melodia
        # LA MUSIQUILLA, LA CULPABLE. Un politono es una melodia finita
        # tocada encima de unos acordes: en cuanto hay una tonadilla sonando
        # todo el rato, el oido lo coloca ahi por muy real que sea el
        # instrumento. La musica de hoy no lleva una melodia constante: lleva
        # groove, y encima apariciones sueltas. Asi que la melodia solo sale en
        # el estribillo, y aun ahi con la mitad de notas y mas silencios.
        # AJUSTE DEL 04-09-2026: lo de arriba seguia siendo verdad, pero se
        # habia pasado de frenada. Con la melodia solo en el estribillo y
        # ademas comiendose el 45% de las notas, salian ONCE notas en dieciseis
        # compases: Angel dijo, con razon, que sonaba insipido y sin vida. Se
        # deja el principio (la melodia no puede sonar todo el rato) pero se
        # abre la mano: entra tambien en el final, y se silencia el 22% en vez
        # del 45%. Sigue habiendo huecos, que es lo que se buscaba.
        if seccion in ("estribillo", "final") and e.get("melodia"):
            n = []
            hueco = 0.22 if seccion == "estribillo" else 0.40
            for sitio, dura, escalon in motivo:
                if az.random() < hueco:
                    continue
                g = grado + escalon
                nota = 72 + raiz + _grado(escala, g)
                while nota > 84:
                    nota -= 12
                n.append((sitio * tic_paso, nota, dura * tic_paso - 4, 84))
            melodia[c] = _humanizar(n, az, 0.9, swing, tic_paso)

    # La reverb NO va en todo: en el bombo y el bajo emborrona. Va donde da aire.
    rev_caja = [_reverb(0.6, 9000, "0.16")]
    rev_acordes = [_reverb(0.85, 11000, "0.28")]
    rev_melodia = [_reverb(0.8, 12000, "0.24")]
    d = lambda f: "drums/" + f
    m = e["muestras"]

    def _voz(papel, patrones, vol, pan, efectos, preset, onda):
        """Instrumento grabado si lo hay y si al estilo le pega; si no, sintetizador.

        En el tecno o el drum and bass que suene un sintetizador NO es una
        renuncia: es lo que toca. En una rumba, en cambio, tiene que sonar una
        guitarra espanola de verdad, y para eso esta el banco.
        """
        nombre_gm = ins.get(papel)
        if con_banco and nombre_gm and nombre_gm in GM:
            return _pista_sf2({"bajo": "Bajo", "acordes": "Acordes",
                               "melodia": "Melodia"}[papel],
                              GM[nombre_gm], patrones, tics_compas, banco=0,
                              vol=vol, pan=pan, efectos=efectos)
        return _pista_preset({"bajo": "Bajo", "acordes": "Acordes",
                              "melodia": "Melodia"}[papel], preset, patrones,
                             tics_compas, vol=vol, pan=pan, efectos=efectos,
                             onda_respaldo=onda)

    pistas = []

    # EL LOOP GRABADO, si el estilo tiene uno. Va el primero porque es la base
    # sobre la que se apoya todo lo demas: es el unico sitio de la cancion
    # donde hay una persona tocando de verdad.
    if loop:
        archivo, compases_loop, _bpm = loop
        golpes_loop = {}
        for c in range(compases):
            _sec, niv = plan[c]
            if niv >= 2 and c % compases_loop == 0:
                # una sola nota que dura todo el loop, en su tono original
                # (la 57 es la nota base, asi no se transporta ni se desafina)
                golpes_loop[c] = [(0, 57, tics_compas * compases_loop, 100)]
        if golpes_loop:
            pistas.append(_pista_muestra("Base grabada", archivo, golpes_loop,
                                         tics_compas, vol=88, pan=0))

    if con_banco:
        # UNA sola pista para toda la bateria, como un bateria de verdad.
        kit = KITS.get(ins.get("kit") or "normal", 0)
        # DOS pistas y no una: el bombo y la caja van al CENTRO (los graves
        # repartidos en estereo se cancelan y suenan flojos) y los charles y la
        # percusion van ABIERTOS. Asi se mezcla un disco, y es lo que da esa
        # sensacion de que la bateria te rodea en vez de salir de un altavoz
        # de movil (02-09-2026).
        centro, lados = {}, {}
        for c in set(list(bombo) + list(caja) + list(charles) + list(extra)
                     + list(percu)):
            n1 = bombo.get(c, []) + caja.get(c, [])
            n2 = charles.get(c, []) + extra.get(c, []) + percu.get(c, [])
            if n1: centro[c] = n1
            if n2: lados[c] = n2
        pistas.append(_pista_sf2("Bateria", kit, centro, tics_compas, banco=128,
                                 vol=64 if loop else 100, pan=0,
                                 efectos=rev_caja, reverb_propia=1))
        if lados:
            pistas.append(_pista_sf2("Percusion", kit, lados, tics_compas,
                                     banco=128, vol=52 if loop else 78, pan=26,
                                     efectos=[_reverb(0.7, 12000, "0.22")],
                                     reverb_propia=1))
    else:
        pistas += [
            _pista_muestra("Bombo", d(m["bombo"]), bombo, tics_compas, 100),
            _pista_muestra("Caja", d(m["caja"]), caja, tics_compas, 88, 0, rev_caja),
            _pista_muestra("Charles", d(m["charles"]), charles, tics_compas, 58, 14),
            _pista_muestra("Adorno", d(e["extra"][0]), extra, tics_compas, 66, -16),
        ]
    pistas.append(_voz("bajo", bajo, 96, 0, (), e["p_bajo"], 2))
    if sub:
        # Onda casi pura y filtro bajo: esto no se oye, se SIENTE. Va centrado
        # a proposito, que los graves repartidos en estereo se cancelan.
        pistas.append(_pista_sinte("Sub", sub, tics_compas, onda=0, vol=72,
                                   pan=0, att="0.005", dec="0.5", sus="0.8",
                                   rel="0.12", corte=180))
    pistas.append(_voz("acordes", acordes, 54, -34, rev_acordes,
                       e["p_acordes"], 3))
    if melodia:
        pistas.append(_voz("melodia", melodia, 66, 30, rev_melodia,
                           e["p_melodia"], 1))

    xml = _proyecto(pulsaciones, numerador, "\n".join(pistas), titulo, compases)

    carpeta = _carpeta_musica()
    try:
        os.makedirs(carpeta, exist_ok=True)
    except Exception as ex:
        return "No he podido crear la carpeta de las canciones: %s" % ex
    destino = os.path.join(carpeta, _limpio(titulo) + ".mmp")
    n = 2
    while os.path.exists(destino):
        destino = os.path.join(carpeta, "%s_%d.mmp" % (_limpio(titulo), n))
        n += 1
    try:
        with io.open(destino, "w", encoding="utf-8") as f:
            f.write(xml)
    except Exception as ex:
        return "No he podido guardar la cancion: %s" % ex

    segundos = compases * numerador * 60.0 / pulsaciones
    nombres_tono = [k for k, v in NOTAS.items()
                    if v == raiz and len(k) > 1 and not k.endswith("b")]
    tono_txt = (nombres_tono[0] if nombres_tono else "do").upper()
    secciones = []
    for s, _n in plan:
        if not secciones or secciones[-1] != s:
            secciones.append(s)

    parte = ["He compuesto '%s'." % titulo]
    if explicacion_mezcla:
        parte += ["  " + l for l in explicacion_mezcla.split("\n")]
    parte += [
             "  estilo: %s   %d pulsaciones por minuto   compas de %d por 4"
             % (clave, pulsaciones, numerador),
             "  tono: %s %s%s   %d compases, unos %d segundos"
             % (tono_txt, e["escala"].replace("_", " "),
                " con septimas" if septima else "", compases, round(segundos)),
             "  estructura: %s" % " - ".join(secciones),
             "  pistas: %s" % ", ".join(re.search(r'name="([^"]+)"', p).group(1)
                                        for p in pistas),
             "  archivo: %s" % destino]

    nivelado = _nivelar(destino)
    if nivelado:
        parte.append("  nivelado: %+d dB a la entrada del limitador "
                     "(medido, no a ojo)" % nivelado[0])

    ok, detalle, mp3 = comprobar_que_suena(destino)
    parte.append("  comprobado: %s" % detalle)
    if mp3 and os.path.exists(mp3):
        parte.append("  para escucharla sin abrir nada: %s" % mp3)

    if str(abrir).strip().lower() in ("si", "sí", "1", "true", "yes"):
        try:
            subprocess.Popen([LMMS, destino])
            parte.append("  lo he abierto en LMMS. Dale al play.")
        except Exception as ex:
            parte.append("  no he podido abrir LMMS (%s); el archivo esta ahi." % ex)
    if not ok:
        parte.append("  OJO: al comprobarlo no ha quedado bien. Diselo a Angel, "
                     "no le digas que esta hecha.")
    return "\n".join(parte)




# Lo que se busca de volumen medio. No es un capricho: por debajo de 0,10 la
# cancion suena floja al lado de cualquier otra cosa, y por encima de 0,20 hay
# que apretarla tanto que pierde la dinamica. Se mide de verdad, no se estima.
# Cuanto tiene que sonar de fuerte lo que sale. 0.20 son unos -14 dBFS, y era
# lo que habia hasta el 04/09/2026: por eso Angel decia que las canciones se
# oian bajas al lado de cualquier otra cosa. Un disco de hoy anda por -10 dBFS,
# que es 0.30. Se sube a 0.28, un pelin por debajo, porque pasado ese punto lo
# unico que se gana es aplastar la cancion contra el limitador y perder pegada.
# Se probo 0.28 y fue pasarse: el factor de cresta cayo de 11,9 a 9,8 dB, o
# sea que la cancion salia mas alta pero aplastada contra el limitador y sin
# pegada. 0.24 sube el volumen sin comerse la dinamica.
NIVEL_OBJETIVO = 0.24
PICO_MAXIMO = 0.99


def _nivelar(ruta, objetivo=NIVEL_OBJETIVO):
    """Renderiza, mide, y corrige el volumen general del proyecto.

    POR QUE HACE FALTA (02-09-2026): con presets de verdad cada estilo trae su
    propio nivel, y medido salian desde 0,046 (el vals) hasta 0,26 (el dance).
    Eso son quince decibelios de diferencia: unas canciones se oian y otras
    habia que subir el volumen del ordenador. Ahora se renderiza una vez, se
    mide, y se ajusta el volumen del proyecto para que todas salgan parejas.

    El tope del pico manda sobre el objetivo: antes que subir hasta saturar, se
    queda mas bajo. Un pico pegado al techo cruje, y eso si que suena a barato.
    """
    import numpy as np
    prueba = os.path.join(os.environ.get("TEMP", "."),
                          "berna_nivel_%d.wav" % int(time.time() * 1000))
    try:
        subprocess.run([LMMS, "render", ruta, "-o", prueba, "-f", "wav"],
                       capture_output=True, text=True, timeout=SEGUNDOS_RENDER)
        if not os.path.exists(prueba):
            return None
        datos, _r = _leer_audio(prueba)
        if not datos.size:
            return None
        medio = float(np.sqrt(np.mean(datos * datos)))
        pico = float(np.max(np.abs(datos)))
    except Exception:
        return None
    finally:
        try:
            os.remove(prueba)
        except Exception:
            pass
    if medio <= 1e-6 or pico <= 1e-6:
        return None
    # Se corrige la ENTRADA DEL LIMITADOR, no el volumen de despues.
    #
    # POR QUE (02-09-2026): bajando el volumen general se apagaba una cancion
    # que el limitador ya habia dejado a tope, y quedaba con el pico en 0,46:
    # o sea, tirando a la basura la mitad del margen. Empujando en la entrada,
    # el limitador aplasta lo justo y la salida se queda pegada a su techo. Es
    # lo mismo que se hace en cualquier estudio.
    import math
    subir = 20.0 * math.log10(max(1e-6, objetivo / medio))
    subir = max(-12.0, min(14.0, subir))
    try:
        with io.open(ruta, encoding="utf-8") as f:
            xml = f.read()
        m = re.search(r'(<key><attribute name="file" value="fast_lookahead'
                      r'_limiter_1913"/>)', xml)
        if m:
            # el port00 del limitador es su ganancia de entrada, en decibelios
            def _cambiar(mm):
                antes = float(mm.group(1))
                return '<port00 data="%.2f"/>' % max(-20.0, min(20.0,
                                                                antes + subir))
            xml = re.sub(r'<port00 data="([-\d.]+)"/>', _cambiar, xml, count=1)
        else:
            nuevo = int(round(max(5, min(200, VOLUMEN_MAESTRO
                                         * (objetivo / medio)))))
            xml = re.sub(r'mastervol="\d+"', 'mastervol="%d"' % nuevo, xml,
                         count=1)
        with io.open(ruta, "w", encoding="utf-8") as f:
            f.write(xml)
    except Exception:
        return None
    return int(round(subir)), medio, pico


def comprobar_que_suena(ruta, guardar_mp3=True, segundos_max=SEGUNDOS_RENDER):
    """Renderiza la cancion y mide si de verdad suena. Devuelve (bien, texto, mp3).

    POR QUE SE MIDE: un proyecto puede estar perfectamente escrito y sonar a
    silencio (una ruta de muestra mal puesta, un preset que no esta, un volumen
    a cero). Sin esto, Berna diria "ya esta tu cancion" y le estaria dando a
    Angel un archivo mudo.

    Y DE PASO SE APROVECHA: el mismo renderizado deja el mp3 al lado del
    proyecto, para escucharlo con doble clic sin abrir LMMS.
    """
    if not os.path.exists(LMMS):
        return False, "no encuentro LMMS, no he podido comprobarlo", ""
    if guardar_mp3:
        salida = os.path.splitext(ruta)[0] + ".mp3"
        formato, temporal = "mp3", False
    else:
        salida = os.path.join(os.environ.get("TEMP", "."),
                              "berna_prueba_%d.wav" % int(time.time()))
        formato, temporal = "wav", True
    try:
        if os.path.exists(salida):
            os.remove(salida)
    except Exception:
        pass
    try:
        r = subprocess.run([LMMS, "render", ruta, "-o", salida,
                            "-f", formato, "-b", "192"],
                           capture_output=True, text=True, timeout=segundos_max)
    except Exception as ex:
        return False, "no he podido renderizarla (%s)" % str(ex)[:70], ""
    if not os.path.exists(salida):
        return False, ("LMMS no ha soltado el audio%s"
                       % ((": " + (r.stderr or "")[-120:]) if r.stderr else "")), ""

    try:
        import numpy as np
        datos, ritmo = _leer_audio(salida)
        medio = float(np.sqrt(np.mean(datos * datos))) if datos.size else 0.0
        pico = float(np.max(np.abs(datos))) if datos.size else 0.0
        saturado = (100.0 * float(np.mean(np.abs(datos) >= 0.9995))
                    if datos.size else 0.0)
        dur = datos.size / float(ritmo or 44100)
    except Exception as ex:
        return False, "no he sabido medir el audio (%s)" % str(ex)[:70], ""
    finally:
        if temporal:
            try:
                os.remove(salida)
            except Exception:
                pass

    mp3 = "" if temporal else salida
    if medio < 0.002:
        return False, ("SILENCIO (nivel medio %.4f en %.0f s): algo esta mal"
                       % (medio, dur)), mp3
    if saturado > 0.5:
        return False, ("SATURA: el %.1f%% del sonido se sale de la escala y "
                       "suena a roto." % saturado), mp3
    aviso = "" if saturado < 0.05 else "  (roza el techo un %.2f%%)" % saturado
    return True, ("suena bien (nivel medio %.3f, pico %.2f, %.0f segundos)%s"
                  % (medio, pico, dur, aviso)), mp3


def _leer_audio(ruta):
    """Devuelve el sonido como numeros entre -1 y 1, sea wav o mp3.

    El mp3 se abre con `av`, que ya viene instalado por la camara. Se mezcla a
    un canal porque para medir el nivel da igual el estereo.

    OJO CON LOS BITS (03-09-2026): LMMS renderiza siempre a 16 bits, pero
    REAPER por defecto usa 24. Suponer 16 bits a pelo rompia el reshape con
    un WAV de REAPER (quedaba un array que no encajaba en (-1, canales), ni
    daba error claro: silenciosamente leia numeros sin sentido). Ahora se mira
    `sampwidth` de verdad y se lee como corresponda.
    """
    import numpy as np
    if ruta.lower().endswith(".wav"):
        import wave
        with wave.open(ruta, "rb") as w:
            crudo = w.readframes(w.getnframes())
            canales, ritmo = w.getnchannels(), w.getframerate()
            ancho = w.getsampwidth()
        if ancho == 2:
            d = np.frombuffer(crudo, dtype="<i2").astype(np.float32) / 32768.0
        elif ancho == 4:
            d = np.frombuffer(crudo, dtype="<i4").astype(np.float32) / 2147483648.0
        elif ancho == 3:
            # no hay dtype de 24 bits: se rellena a 32 con un byte de signo.
            # OJO: el valor queda en los 3 bytes BAJOS (no desplazado), asi que
            # su rango es +-2^23 y hay que dividir por eso, NO por 2^31. Ese
            # factor de 256 de mas fue justo el primer intento (03-09-2026):
            # daba un nivel 256 veces mas bajo del real, o sea "silencio" que
            # no lo era.
            crudo3 = np.frombuffer(crudo, dtype=np.uint8).reshape(-1, 3)
            crudo32 = np.zeros((crudo3.shape[0], 4), dtype=np.uint8)
            crudo32[:, :3] = crudo3
            crudo32[:, 3] = np.where(crudo3[:, 2] >= 0x80, 0xFF, 0x00)
            d = crudo32.view("<i4").reshape(-1).astype(np.float32) / 8388608.0
        else:
            d = np.frombuffer(crudo, dtype=np.uint8).astype(np.float32)
            d = (d - 128.0) / 128.0
        if canales > 1 and d.size % canales == 0:
            d = d.reshape(-1, canales).mean(axis=1)
        return d, ritmo
    import av
    trozos, ritmo = [], 44100
    with av.open(ruta) as f:
        for cuadro in f.decode(audio=0):
            ritmo = cuadro.sample_rate or ritmo
            a = cuadro.to_ndarray().astype(np.float32)
            trozos.append(a.mean(axis=0) if a.ndim > 1 else a)
    if not trozos:
        return np.zeros(0, dtype=np.float32), ritmo
    d = np.concatenate(trozos)
    if d.size and (d.max() > 1.5 or d.min() < -1.5):
        d = d / 32768.0
    return d, ritmo


def main():
    import sys
    print(crear_cancion(sys.argv[1] if len(sys.argv) > 1 else "reggaeton",
                        abrir="no"))


if __name__ == "__main__":
    main()
