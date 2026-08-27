# -*- coding: utf-8 -*-
r"""
Recordatorios, alarmas y temporizadores de Berna.

Era el agujero mas gordo que tenia: sabia hacer de todo, pero **solo cuando
le hablabas**. No podia avisar de nada por su cuenta. Con esto, Angel le dice
"recuerdame a las cinco que llame al cliente" y a las cinco Berna **habla
solo** y se lo dice en voz alta.

COMO FUNCIONA
  Los avisos se guardan en `recordatorios.json` con su fecha y hora exactas,
  asi que **sobreviven a cerrar el programa**: si Berna estaba apagado cuando
  tocaba, al abrirlo te lo dice igual (con retraso, pero te lo dice).

  La ventana tiene un hilo que llama a `vencidos()` cada pocos segundos. Esa
  funcion devuelve lo que ya toca y lo marca como avisado en el mismo paso,
  para que no lo cante dos veces.

ENTENDER LA HORA QUE LE DICEN
  El modelo suele mandar la hora ya calculada ("2026-08-26 17:30"), que es lo
  ideal. Pero tambien se aceptan las formas que dice la gente: "en 20
  minutos", "a las cinco y media", "manana a las nueve", "el lunes a las 8".
  Si no se entiende, se dice claramente en vez de inventarse una hora, que un
  aviso a la hora equivocada no sirve de nada.

REPETIR
  Un aviso puede ser de una vez, `diario`, `laborables` (de lunes a viernes)
  o `semanal`. Al sonar, los que se repiten se vuelven a colocar solos en su
  siguiente fecha.
"""
import os
import re
import json
import datetime
import unicodedata

BASE = os.path.dirname(os.path.abspath(__file__))
FICHERO = os.path.join(BASE, "recordatorios.json")

MAX_AVISOS = 200
REPETICIONES = ("no", "diario", "laborables", "semanal")

DIAS = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3,
        "viernes": 4, "sabado": 5, "domingo": 6}

NUMEROS = {"una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
           "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
           "once": 11, "doce": 12, "media": 30, "cuarto": 15}


def _sin_tildes(t):
    t = unicodedata.normalize("NFD", str(t or ""))
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower().strip()


# ------------------------------------------------------------------ el fichero
def _cargar():
    if os.path.exists(FICHERO):
        try:
            with open(FICHERO, "r", encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, list):
                return d
        except Exception:
            pass
    return []


def _guardar(lista):
    tmp = FICHERO + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(lista[-MAX_AVISOS:], f, indent=1, ensure_ascii=False)
    os.replace(tmp, FICHERO)


def _fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M")


def _en_cristiano(dt):
    """La fecha, dicha como la diria una persona."""
    ahora = datetime.datetime.now()
    dias = (dt.date() - ahora.date()).days
    hora = dt.strftime("%H:%M")
    if dias == 0:
        faltan = (dt - ahora).total_seconds() / 60.0
        if 0 < faltan < 90:
            n = round(faltan)
            return ("dentro de %d minuto%s (a las %s)"
                    % (n, "" if n == 1 else "s", hora))
        return "hoy a las %s" % hora
    if dias == 1:
        return "manana a las %s" % hora
    if 1 < dias < 7:
        nombres = ["lunes", "martes", "miercoles", "jueves", "viernes",
                   "sabado", "domingo"]
        return "el %s a las %s" % (nombres[dt.weekday()], hora)
    return "el %s a las %s" % (dt.strftime("%d/%m/%Y"), hora)


# ------------------------------------------------------------------ entender la hora
def _hora_suelta(t):
    """De 'las cinco y media' o '17:30' a (hora, minuto), o None."""
    m = re.search(r"(\d{1,2})\s*[:.]\s*(\d{2})", t)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"\bla[s]?\s+(\d{1,2})\b", t)
    if m:
        h, mi = int(m.group(1)), 0
    else:
        m = re.search(r"\bla[s]?\s+(%s)\b" % "|".join(NUMEROS), t)
        if not m:
            return None
        h, mi = NUMEROS[m.group(1)], 0
    if re.search(r"y\s+media", t):
        mi = 30
    elif re.search(r"y\s+cuarto", t):
        mi = 15
    elif re.search(r"menos\s+cuarto", t):
        h, mi = h - 1, 45
    else:
        m2 = re.search(r"y\s+(\d{1,2})\b", t)
        if m2:
            mi = int(m2.group(1))
    if re.search(r"tarde|noche", t) and h < 12:
        h += 12
    if re.search(r"manana|madrugada", t) and h == 12:
        h = 0
    return h % 24, mi % 60


def entender_cuando(texto, ahora=None):
    """Devuelve un datetime, o None si de verdad no se entiende."""
    ahora = ahora or datetime.datetime.now()
    if isinstance(texto, datetime.datetime):
        return texto
    t = _sin_tildes(texto)
    if not t:
        return None

    # 1. tal cual, que es como deberia mandarlo el modelo
    for formato in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%d/%m/%Y %H:%M",
                    "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.datetime.strptime(str(texto).strip(), formato)
        except Exception:
            pass

    # 2b. las que la gente dice sin numero delante
    if re.search(r"\b(?:en|dentro de)\s+media\s+hora\b", t):
        return ahora + datetime.timedelta(minutes=30)
    if re.search(r"\b(?:en|dentro de)\s+(?:una\s+)?hora\s+y\s+media\b", t):
        return ahora + datetime.timedelta(minutes=90)

    # 2. "en 20 minutos", "dentro de 2 horas", "en hora y media"
    m = re.search(r"\b(?:en|dentro de)\s+(\d+|%s)\s*(minuto|min|hora|dia|semana)"
                  % "|".join(NUMEROS), t)
    if m:
        n = int(m.group(1)) if m.group(1).isdigit() else NUMEROS[m.group(1)]
        u = m.group(2)
        extra = 30 if re.search(r"y\s+media", t) and u.startswith("hora") else 0
        if u.startswith("min"):
            return ahora + datetime.timedelta(minutes=n)
        if u.startswith("hora"):
            return ahora + datetime.timedelta(hours=n, minutes=extra)
        if u.startswith("dia"):
            return ahora + datetime.timedelta(days=n)
        if u.startswith("semana"):
            return ahora + datetime.timedelta(weeks=n)

    hm = _hora_suelta(t)

    # 3. un dia de la semana
    for nombre, num in DIAS.items():
        if re.search(r"\b%s\b" % nombre, t):
            faltan = (num - ahora.weekday()) % 7
            if faltan == 0 and (not hm or (hm[0], hm[1]) <= (ahora.hour, ahora.minute)):
                faltan = 7
            d = ahora + datetime.timedelta(days=faltan)
            h, mi = hm or (9, 0)
            return d.replace(hour=h, minute=mi, second=0, microsecond=0)

    # 4. hoy / manana / pasado manana
    dias = 0
    if re.search(r"pasado\s+manana", t):
        dias = 2
    elif re.search(r"\bmanana\b", t) and not re.search(r"de la manana|por la manana", t):
        dias = 1
    if hm:
        d = (ahora + datetime.timedelta(days=dias)).replace(
            hour=hm[0], minute=hm[1], second=0, microsecond=0)
        if d <= ahora and dias == 0:
            d += datetime.timedelta(days=1)      # "a las 8" ya pasadas: manana
        return d
    if dias:
        return (ahora + datetime.timedelta(days=dias)).replace(
            hour=9, minute=0, second=0, microsecond=0)
    return None


def _siguiente(dt, repetir):
    r = _sin_tildes(repetir)
    if r == "diario":
        return dt + datetime.timedelta(days=1)
    if r == "semanal":
        return dt + datetime.timedelta(weeks=1)
    if r == "laborables":
        d = dt + datetime.timedelta(days=1)
        while d.weekday() >= 5:
            d += datetime.timedelta(days=1)
        return d
    return None


# ------------------------------------------------------------------ herramientas
def recordarme(que, cuando, repetir="no"):
    que = str(que or "").strip()
    if not que:
        return "Dime que hay que recordarte."
    dt = entender_cuando(cuando)
    if dt is None:
        return ("No he entendido para cuando es. Dimelo de otra forma: 'en 20 "
                "minutos', 'hoy a las 17:30', 'manana a las nueve', o pasame la "
                "fecha y hora exactas.")
    if dt <= datetime.datetime.now():
        return ("Esa hora ya ha pasado (%s). Dime una que este por venir."
                % _fmt(dt))
    rep = _sin_tildes(repetir) if _sin_tildes(repetir) in REPETICIONES else "no"
    lista = _cargar()
    lista.append({"id": (max([a.get("id", 0) for a in lista]) + 1) if lista else 1,
                  "que": que[:300], "cuando": _fmt(dt), "repetir": rep,
                  "avisado": False, "puesto": _fmt(datetime.datetime.now())})
    _guardar(lista)
    coletilla = "" if rep == "no" else " Y se repite: %s." % rep
    return ("Apuntado: te avisare %s de esto: %s.%s Te lo dire en voz alta "
            "aunque estemos hablando de otra cosa. Confirmaselo a Angel en una "
            "frase corta." % (_en_cristiano(dt), que, coletilla))


def poner_temporizador(minutos, para_que=""):
    try:
        minutos = float(minutos)
    except Exception:
        return "Dime cuantos minutos."
    if minutos <= 0 or minutos > 60 * 24:
        return "Ponme un tiempo entre un minuto y un dia."
    dt = datetime.datetime.now() + datetime.timedelta(minutes=minutos)
    texto = para_que or "se acabo el tiempo"
    lista = _cargar()
    lista.append({"id": (max([a.get("id", 0) for a in lista]) + 1) if lista else 1,
                  "que": texto[:300], "cuando": _fmt(dt), "repetir": "no",
                  "avisado": False, "puesto": _fmt(datetime.datetime.now()),
                  "temporizador": True})
    _guardar(lista)
    if minutos < 1.5:
        cuanto = "%d segundos" % int(minutos * 60)
    elif minutos < 60:
        cuanto = "%d minutos" % round(minutos)
    else:
        cuanto = "%.1f horas" % (minutos / 60.0)
    return ("Temporizador puesto: %s, y te aviso en voz alta. Diselo en una "
            "frase." % cuanto)


def ver_recordatorios():
    lista = [a for a in _cargar() if not a.get("avisado")]
    if not lista:
        return ("No tienes ningun aviso puesto. Recuerdale que puede pedirte "
                "cosas como 'recuerdame manana a las nueve que llame al gestor'.")
    lista.sort(key=lambda a: a["cuando"])
    lineas = ["Avisos que tienes puestos (%d):" % len(lista)]
    for a in lista:
        try:
            dt = datetime.datetime.strptime(a["cuando"], "%Y-%m-%d %H:%M")
            cuando = _en_cristiano(dt)
        except Exception:
            cuando = a["cuando"]
        extra = "" if a.get("repetir", "no") == "no" else " (se repite: %s)" % a["repetir"]
        lineas.append("  %d. %s -> %s%s" % (a["id"], a["que"], cuando, extra))
    lineas.append("")
    lineas.append("Cuentaselo con tus palabras, por orden de cercania.")
    return "\n".join(lineas)


def quitar_recordatorio(cual):
    lista = _cargar()
    vivos = [a for a in lista if not a.get("avisado")]
    if not vivos:
        return "No tienes ningun aviso puesto."
    elegido = None
    t = _sin_tildes(cual)
    if t.isdigit():
        elegido = next((a for a in vivos if a["id"] == int(t)), None)
    if elegido is None and t:
        elegido = next((a for a in vivos if t in _sin_tildes(a["que"])), None)
    if elegido is None and t in ("todos", "todo"):
        for a in vivos:
            a["avisado"] = True
        _guardar(lista)
        return "Quitados los %d avisos que tenias." % len(vivos)
    if elegido is None:
        return ("No se cual quitar. Mira la lista con ver_recordatorios y dime "
                "el numero.")
    elegido["avisado"] = True
    _guardar(lista)
    return "Quitado el aviso: %s." % elegido["que"]


# ------------------------------------------------------------------ para la ventana
def vencidos():
    """Lo que ya toca avisar. Los marca en el mismo paso para no repetirlos.

    Lo llama el hilo vigilante de la ventana cada pocos segundos. Devuelve una
    lista de textos ya listos para decir en voz alta.
    """
    lista = _cargar()
    ahora = datetime.datetime.now()
    salen, cambiado = [], False
    for a in lista:
        if a.get("avisado"):
            continue
        try:
            dt = datetime.datetime.strptime(a["cuando"], "%Y-%m-%d %H:%M")
        except Exception:
            a["avisado"] = True
            cambiado = True
            continue
        if dt <= ahora:
            tarde = (ahora - dt).total_seconds() / 60.0
            if a.get("temporizador"):
                aviso = "Angel, se acabo el tiempo: %s." % a["que"]
            else:
                aviso = "Angel, te recuerdo esto: %s." % a["que"]
            if tarde > 20:
                aviso += " Perdona el retraso, era para las %s." % dt.strftime("%H:%M")
            salen.append(aviso)
            a["avisado"] = True
            cambiado = True
            siguiente = _siguiente(dt, a.get("repetir", "no"))
            if siguiente:
                lista.append({"id": max([x.get("id", 0) for x in lista]) + 1,
                              "que": a["que"], "cuando": _fmt(siguiente),
                              "repetir": a["repetir"], "avisado": False,
                              "puesto": _fmt(ahora)})
    if cambiado:
        _guardar(lista)
    return salen
