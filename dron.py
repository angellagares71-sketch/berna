# -*- coding: utf-8 -*-
r"""
Volar el dron: si hoy se puede, a que hora conviene y cuando hay buena luz.

Es lo que mas le puede servir a Angel de todo lo que tiene Berna, porque es
lo suyo: tiene equipo DJI pagado y de ahi puede sacar trabajo. Y la pregunta
que se hace cada manana es siempre la misma: **"¿puedo volar hoy?"**.

DE DONDE SALEN LOS DATOS
  De wttr.in en formato JSON (`?format=j1`), que es el mismo sitio que ya
  usaba `el_tiempo` y no necesita clave. Trae por horas el viento medio, LAS
  RACHAS, la probabilidad de lluvia y la visibilidad, y por dias la hora de
  amanecer y de anochecer.

LO QUE DE VERDAD TUMBA UN DRON SON LAS RACHAS, NO EL VIENTO MEDIO
  Por eso aqui se mira sobre todo `WindGustKmph`. Un viento medio de 20 con
  rachas de 45 es peor que un viento constante de 30.

LOS LIMITES SON DE FABRICA, EL CRITERIO ES MIO Y SE DICE
  DJI publica la "resistencia maxima al viento" de cada modelo (Mini 4 Pro:
  10,7 m/s = 38,5 km/h; Mavic 3: 12 m/s = 43 km/h). **Eso es el maximo que
  aguanta antes de perderse, no lo que es sensato.** Aqui se avisa en rojo
  bastante antes: a partir del 60% de ese limite ya se recomienda no volar,
  porque a esas alturas el dron gasta bateria peleando con el aire, las fotos
  salen movidas y un despiste te lo lleva.

  El modelo se guarda en `config.json` -> `dron_modelo`. Si no esta puesto,
  se usa un limite prudente de dron pequeno.

LO QUE NO HACE, Y ES A PROPOSITO
  Esto NO dice si es LEGAL volar ahi. Las zonas restringidas se miran en
  ENAIRE Drones y las obligaciones son las de AESA. Berna lo recuerda, pero
  la decision y la responsabilidad son de Angel, que es quien tiene el
  titulo y quien responde.
"""
import os
import json
import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(BASE, "config.json")

# Resistencia maxima al viento que publica DJI, en km/h.
DRONES = {
    "mini 4 pro": 38.5, "mini 3 pro": 38.5, "mini 3": 38.5, "mini 4k": 38.5,
    "mini 2": 29.0, "mini se": 29.0,
    "air 3": 43.0, "air 2s": 38.5, "air 3s": 43.0,
    "mavic 3": 43.0, "mavic 3 pro": 43.0, "mavic 3 classic": 43.0,
    "mavic 2": 38.5, "avata": 38.5, "neo": 29.0,
}
LIMITE_POR_DEFECTO = 36.0        # dron pequeno, prudente

# Fracciones del limite del fabricante a partir de las cuales se avisa.
BIEN, REGULAR, MAL = 0.40, 0.60, 0.75

RECORDATORIO_AESA = (
    "Recuerdale lo de siempre en una frase, sin sermonear: mirar la zona en "
    "ENAIRE Drones, no perderlo de vista, no pasar de 120 metros y no volar "
    "sobre gente.")


def _cfg():
    try:
        with open(CONFIG, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _limite(modelo=""):
    """El limite del fabricante y el nombre del modelo que se ha usado."""
    m = str(modelo or _cfg().get("dron_modelo") or "").strip().lower()
    m = m.replace("dji", "").strip()
    if m:
        if m in DRONES:
            return DRONES[m], m
        for k, v in DRONES.items():
            if k in m or m in k:
                return v, k
    return LIMITE_POR_DEFECTO, ""


def _tiempo(lugar):
    """Los datos por horas de wttr.in. Devuelve (datos, fallo)."""
    import requests
    lugar = (lugar or "Sevilla").strip()
    try:
        r = requests.get("https://wttr.in/%s?format=j1" % lugar,
                         headers={"User-Agent": "curl/8"}, timeout=25)
        if r.status_code != 200:
            return None, ("No he podido mirar el tiempo de %s (el servicio ha "
                          "contestado %s). Prueba en un rato." % (lugar, r.status_code))
        return r.json(), None
    except Exception as e:
        return None, "No he podido mirar el tiempo: %s" % e


def _hora(h):
    """wttr.in da las horas como '0', '300', '1200'..."""
    try:
        return int(str(h).strip() or 0) // 100
    except Exception:
        return 0


def _num(d, clave, por_defecto=0.0):
    try:
        return float(d.get(clave) or 0)
    except Exception:
        return por_defecto


def _veredicto(viento, racha, lluvia, mm, visibilidad, limite):
    """Devuelve (se_puede, semaforo, motivos). El criterio esta explicado arriba."""
    motivos = []
    malo = False
    regular = False
    if racha >= limite * MAL:
        motivos.append("rachas de %d km/h, demasiado para tu dron (aguanta %d "
                       "como maximo)" % (racha, limite))
        malo = True
    elif racha >= limite * REGULAR:
        motivos.append("rachas de %d km/h, que ya es mucho" % racha)
        regular = True
    elif racha >= limite * BIEN:
        motivos.append("rachas de %d km/h, se nota pero se lleva" % racha)
    if viento >= limite * REGULAR:
        motivos.append("viento constante de %d km/h" % viento)
        regular = True
    if mm > 0.2 or lluvia >= 50:
        motivos.append("lluvia (%d%% de probabilidad, %.1f mm)" % (lluvia, mm))
        malo = True
    elif lluvia >= 30:
        motivos.append("puede caer algo (%d%%)" % lluvia)
        regular = True
    if visibilidad and visibilidad < 5:
        motivos.append("visibilidad de solo %d km, y hay que verlo en todo "
                       "momento" % visibilidad)
        malo = True
    if malo:
        return False, "NO", motivos
    if regular:
        return True, "CON CUIDADO", motivos
    return True, "SI", motivos or ["viento flojo y cielo despejado"]


# ------------------------------------------------------------------ herramientas
def puedo_volar(lugar="", modelo=""):
    datos, fallo = _tiempo(lugar or _cfg().get("dron_lugar") or "Sevilla")
    if datos is None:
        return fallo
    limite, nombre = _limite(modelo)
    sitio = lugar or "Sevilla"
    try:
        area = datos["nearest_area"][0]
        sitio = "%s (%s)" % (area["areaName"][0]["value"], area["region"][0]["value"])
    except Exception:
        pass

    ahora = datos.get("current_condition", [{}])[0]
    viento = _num(ahora, "windspeedKmph")
    visibilidad = _num(ahora, "visibility")
    # las rachas de ahora no vienen en current_condition: se cogen de la hora
    hoy = datos.get("weather", [{}])[0]
    h_actual = datetime.datetime.now().hour
    tramo = min(hoy.get("hourly", []), key=lambda x: abs(_hora(x.get("time")) - h_actual)) \
        if hoy.get("hourly") else {}
    racha = _num(tramo, "WindGustKmph", viento * 1.4)
    lluvia = _num(tramo, "chanceofrain")
    mm = _num(tramo, "precipMM")

    se_puede, semaforo, motivos = _veredicto(viento, racha, lluvia, mm,
                                             visibilidad, limite)
    partes = ["¿Se puede volar ahora en %s? %s" % (sitio, semaforo)]
    partes.append("  Viento: %d km/h, con rachas de %d km/h." % (viento, racha))
    partes.append("  Tu dron%s aguanta hasta %d km/h de fabrica."
                  % ((" (" + nombre + ")") if nombre else "", limite))
    partes.append("  Lluvia: %d%% de probabilidad. Visibilidad: %d km."
                  % (lluvia, visibilidad))
    partes.append("  Temperatura: %s grados." % ahora.get("temp_C", "?"))
    partes.append("  Por que: " + "; ".join(motivos) + ".")

    # las proximas horas, por si conviene esperar
    siguientes = []
    for h in hoy.get("hourly", []):
        hh = _hora(h.get("time"))
        if hh <= h_actual:
            continue
        r = _num(h, "WindGustKmph")
        ok, sem, _ = _veredicto(_num(h, "windspeedKmph"), r, _num(h, "chanceofrain"),
                                _num(h, "precipMM"), 10, limite)
        siguientes.append("%02d:00 %s (rachas %d)" % (hh, sem, r))
    if siguientes:
        partes.append("  Lo que queda de hoy: " + ", ".join(siguientes[:6]) + ".")

    partes.append("")
    partes.append("Dale el veredicto claro en la primera frase (si, no, o con "
                  "cuidado) y luego el porque en dos palabras. " + RECORDATORIO_AESA)
    if not nombre:
        partes.append("Y como no sabes que dron tiene, dile que te lo diga una "
                      "vez y lo guardas para siempre.")
    return "\n".join(partes)


def mejor_hora_para_volar(lugar="", dias=2, modelo=""):
    datos, fallo = _tiempo(lugar or _cfg().get("dron_lugar") or "Sevilla")
    if datos is None:
        return fallo
    limite, nombre = _limite(modelo)
    try:
        dias = max(1, min(3, int(float(dias))))
    except Exception:
        dias = 2
    ahora = datetime.datetime.now()
    buenas = []
    for i, dia in enumerate(datos.get("weather", [])[:dias]):
        try:
            fecha = datetime.datetime.strptime(dia["date"], "%Y-%m-%d")
        except Exception:
            continue
        for h in dia.get("hourly", []):
            hh = _hora(h.get("time"))
            cuando = fecha.replace(hour=hh)
            if cuando < ahora or hh < 7 or hh > 21:
                continue
            racha = _num(h, "WindGustKmph")
            ok, sem, _ = _veredicto(_num(h, "windspeedKmph"), racha,
                                    _num(h, "chanceofrain"), _num(h, "precipMM"),
                                    10, limite)
            if ok:
                buenas.append((racha, cuando, sem, _num(h, "windspeedKmph"),
                               _num(h, "chanceofrain")))
    if not buenas:
        return ("No veo ni una hora buena para volar en los proximos %d dias en "
                "%s: o hay demasiado viento o llueve. Dale la mala noticia "
                "claramente y ofrecele mirarlo otra vez manana."
                % (dias, lugar or "tu zona"))
    buenas.sort(key=lambda x: x[0])
    partes = ["Las mejores horas para volar en %s:" % (lugar or "tu zona")]
    for racha, cuando, sem, viento, lluvia in buenas[:6]:
        dia = "hoy" if cuando.date() == ahora.date() else (
            "manana" if (cuando.date() - ahora.date()).days == 1
            else cuando.strftime("el %d/%m"))
        partes.append("  %s a las %02d:00 -> %s (viento %d, rachas %d, lluvia %d%%)"
                      % (dia, cuando.hour, sem, viento, racha, lluvia))
    partes.append("")
    partes.append("Recomiendale UNA, la mejor, y di la hora en cristiano. " +
                  RECORDATORIO_AESA)
    return "\n".join(partes)


def hora_dorada(lugar=""):
    """Cuando hay buena luz: la hora dorada y la azul, que es cuando salen las buenas."""
    datos, fallo = _tiempo(lugar or _cfg().get("dron_lugar") or "Sevilla")
    if datos is None:
        return fallo

    def _a_hora(texto):
        for f in ("%I:%M %p", "%H:%M"):
            try:
                return datetime.datetime.strptime(texto.strip(), f)
            except Exception:
                pass
        return None

    partes = ["Luz buena para grabar en %s:" % (lugar or "tu zona")]
    for i, dia in enumerate(datos.get("weather", [])[:2]):
        astro = (dia.get("astronomy") or [{}])[0]
        sale = _a_hora(astro.get("sunrise", ""))
        pone = _a_hora(astro.get("sunset", ""))
        if not sale or not pone:
            continue
        cual = "Hoy" if i == 0 else "Manana"
        partes.append("  %s:" % cual)
        partes.append("    Amanece a las %s y anochece a las %s."
                      % (sale.strftime("%H:%M"), pone.strftime("%H:%M")))
        partes.append("    Hora dorada de la manana: de %s a %s."
                      % (sale.strftime("%H:%M"),
                         (sale + datetime.timedelta(minutes=60)).strftime("%H:%M")))
        partes.append("    Hora dorada de la tarde: de %s a %s."
                      % ((pone - datetime.timedelta(minutes=60)).strftime("%H:%M"),
                         pone.strftime("%H:%M")))
        partes.append("    Hora azul (justo despues): de %s a %s."
                      % (pone.strftime("%H:%M"),
                         (pone + datetime.timedelta(minutes=25)).strftime("%H:%M")))
    if len(partes) == 1:
        return "No he podido sacar las horas de sol de ese sitio."
    partes.append("")
    partes.append("Cuentaselo corto y recuerdale que la hora dorada es cuando "
                  "salen las tomas buenas, y que la azul dura poquisimo.")
    return "\n".join(partes)


def guardar_mi_dron(modelo, lugar=""):
    """Se apunta el modelo y la zona para no preguntarlo cada vez."""
    limite, nombre = _limite(modelo)
    try:
        with open(CONFIG, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return "No he podido abrir la configuracion."
    cfg["dron_modelo"] = str(modelo or "").strip()
    if lugar:
        cfg["dron_lugar"] = str(lugar).strip()
    tmp = CONFIG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    os.replace(tmp, CONFIG)
    if nombre:
        return ("Apuntado: tienes un %s, que aguanta hasta %d km/h de viento. Ya "
                "no te lo pregunto mas.%s"
                % (modelo, limite, (" Y vuelas por %s." % lugar) if lugar else ""))
    return ("Apuntado que tu dron es un '%s', pero ese modelo no lo tengo en la "
            "lista, asi que usare un limite prudente de %d km/h. Si me dices que "
            "aguanta segun el fabricante, mejor." % (modelo, LIMITE_POR_DEFECTO))
