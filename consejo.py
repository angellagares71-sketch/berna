# -*- coding: utf-8 -*-
r"""
El consejo: varias IA contestan y luego se cotejan entre ellas.

Angel lo pidio el 2026-08-28: "que fluctuen entre ellas y asi de siempre mejor
resultado, ya que analizaran y cotejaran unas con otras antes de responder".

POR QUE NO SE HACE EN CADA FRASE, que es lo primero que hay que decir
  Preguntarle a tres IA en cada mensaje multiplica por tres el gasto de una
  cuota GRATUITA que ya se agota sola, y que ademas se comparte con Mantella.
  Y pasa el tiempo de respuesta de 0,9 s a varios segundos, que en algo que
  contesta hablando se nota muchisimo (Angel ya se quejo una vez de que iba
  lento cuando tardaba 6 s).

  Ademas, la mayoria de lo que le pide a Berna NO se beneficia: "abre el
  Skyrim" o "que hora es" se resuelven con una herramienta, y ahi tres
  opiniones no aportan nada.

  Asi que el consejo se convoca CUANDO MERECE LA PENA: preguntas de criterio,
  cuentas, cosas donde equivocarse tiene coste, o cuando Angel dice
  expresamente que se lo piense bien.

COMO FUNCIONA
  1. Se eligen las IA que estan vivas y que son DISTINTAS entre si.
  2. Se les pregunta A LA VEZ, en hilos. Asi tarda lo que la mas lenta, no la
     suma de todas.
  3. Una hace de ponente: ve todas las respuestas, mira en que coinciden y en
     que se contradicen, y redacta la buena. **Y tiene orden de decir cuando
     no se ponen de acuerdo**, en vez de disimularlo.

  Lo tercero es lo importante. Un consejo que siempre saca una respuesta
  segura es peor que una sola IA, porque esconde la duda. Cuando discrepan en
  algo que importa, Angel tiene que enterarse.
"""
import json
import os
import re
import threading
import time

BASE = os.path.dirname(os.path.abspath(__file__))
URL_GEMINI = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
URL_OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"

ESPERA = 25
# Plazo del consejo entero. Sin esto tardaba 36 s por pregunta, porque esperaba
# a la mas lenta y hay candidatas que tardan 20 s. Con 9 s se aprovecha a las
# que llegan y las demas se quedan fuera: mas vale un consejo de dos rapidas
# que uno de cuatro que llega tarde.
PLAZO = 9.0
MAX_CONSEJOS_HORA = 12          # freno para no fundir la cuota
_HISTORIAL = []


def _cfg():
    try:
        with open(os.path.join(BASE, "config.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _destino(modelo, cfg):
    """(url, cabeceras, nombre) para ese modelo, o None si no hay clave."""
    if modelo.startswith("gemini:"):
        k = (cfg.get("clave_gemini") or "").strip()
        return (URL_GEMINI, k, modelo.split(":", 1)[1]) if k else None
    k = (cfg.get("clave_api") or "").strip()
    return (URL_OPENROUTER, k, modelo) if k else None


def _preguntar(modelo, mensajes, cfg, maxtok=700):
    """Una llamada. Devuelve (texto, segundos, error)."""
    import requests
    d = _destino(modelo, cfg)
    if d is None:
        return "", 0.0, "sin clave"
    url, clave, nombre = d
    t0 = time.time()
    try:
        r = requests.post(url, timeout=ESPERA,
                          headers={"Authorization": "Bearer " + clave,
                                   "Content-Type": "application/json"},
                          json={"model": nombre, "messages": mensajes,
                                "max_tokens": maxtok})
        if r.status_code != 200:
            return "", time.time() - t0, "HTTP %s" % r.status_code
        t = (r.json()["choices"][0]["message"].get("content") or "").strip()
        return t, time.time() - t0, None if t else "vacio"
    except Exception as e:
        return "", time.time() - t0, str(e)[:60]


def _sin_markdown(t):
    """Quita asteriscos, almohadillas, comillas de codigo y vinetas."""
    t = re.sub(r"```.*?```", " ", t or "", flags=re.S)
    t = re.sub(r"[*#`_~|]", "", t)
    t = re.sub(r"^\s*[-\u2022]\s+", "", t, flags=re.M)
    t = re.sub(r"[ \t]+", " ", t)
    return t.strip()


def _familia(modelo):
    """Para no meter en el consejo tres versiones de lo mismo.

    'gemini:gemini-3.5-flash-lite' y 'gemini:gemini-flash-lite-latest' pueden
    ser el MISMO modelo con dos nombres. Un consejo de clones no cotejo nada.
    """
    n = modelo.split(":")[-1]
    n = re.sub(r"-(latest|preview|image|tts)$", "", n)
    n = re.sub(r"-\d{2}-\d{4}$", "", n)
    return n


def _vocales(cfg, cuantos):
    """Elige las IA del consejo: vivas, distintas y por orden de la cadena."""
    lista = cfg.get("modelos") or []
    fuera, vistas = [], set()
    for m in lista:
        f = _familia(m)
        if f in vistas:
            continue
        vistas.add(f)
        fuera.append(m)
        if len(fuera) >= cuantos * 2:      # de sobra, luego se cae el que falle
            break
    return fuera


def _hay_hueco():
    ahora = time.time()
    while _HISTORIAL and ahora - _HISTORIAL[0] > 3600:
        _HISTORIAL.pop(0)
    return len(_HISTORIAL) < MAX_CONSEJOS_HORA


def consultar_al_consejo(pregunta, cuantos=3):
    """Pregunta a varias IA a la vez y las hace cotejarse entre ellas."""
    pregunta = str(pregunta or "").strip()
    if not pregunta:
        return "Dime que quieres que consulte."
    try:
        cuantos = max(2, min(int(cuantos or 3), 4))
    except Exception:
        cuantos = 3
    if not _hay_hueco():
        return ("He convocado el consejo %d veces en la ultima hora y no quiero "
                "fundir la cuota, que la comparte con el Skyrim. Contesto yo "
                "solo, o esperamos un rato." % MAX_CONSEJOS_HORA)

    cfg = _cfg()
    candidatos = _vocales(cfg, cuantos)
    if len(candidatos) < 2:
        return ("Solo tengo un cerebro configurado, asi que no hay con quien "
                "cotejar. Contesto yo solo.")

    sistema = ("Contesta en espanol de Espana, claro y al grano. Si no estas "
               "seguro de algo, DILO en vez de rellenar. Si hay que calcular, "
               "haz la cuenta paso a paso y da el resultado.")
    mensajes = [{"role": "system", "content": sistema},
                {"role": "user", "content": pregunta}]

    # --- todas a la vez, que si no se suman los tiempos --------------------
    respuestas, hilos = {}, []
    orden = []

    def trabajo(m):
        txt, seg, err = _preguntar(m, mensajes, cfg)
        respuestas[m] = (txt, seg, err)

    for m in candidatos:
        h = threading.Thread(target=trabajo, args=(m,), daemon=True)
        h.start()
        hilos.append((m, h))
        orden.append(m)
    t0 = time.time()
    for m, h in hilos:
        h.join(timeout=max(0.2, PLAZO - (time.time() - t0)))

    # Una respuesta vacia no es un voto. Hay modelos que se gastan el
    # presupuesto razonando por dentro y devuelven la nada; medido en
    # gemini-3-flash-preview.
    buenas = [(m, respuestas[m][0], respuestas[m][1])
              for m in orden
              if m in respuestas and respuestas[m][2] is None
              and len((respuestas[m][0] or "").strip()) > 12]
    caidas = [(m, respuestas.get(m, ("", 0, "sin respuesta"))[2])
              for m in orden if m not in respuestas or respuestas[m][2]]
    buenas = buenas[:cuantos]

    if not buenas:
        return ("No me ha contestado ninguna IA (%s). Sera la cuota o la "
                "conexion." % "; ".join("%s: %s" % (m.split(":")[-1], e)
                                        for m, e in caidas[:3]))
    if len(buenas) == 1:
        m, txt, seg = buenas[0]
        return ("Solo ha contestado una de las IA (%s), asi que no he podido "
                "cotejar nada. Esto es lo que dice, tomalo con pinzas:\n\n%s"
                % (m.split(":")[-1], _sin_markdown(txt)))

    _HISTORIAL.append(time.time())

    # --- la ponente: cotejar y redactar ------------------------------------
    trozos = []
    for i, (m, txt, seg) in enumerate(buenas, 1):
        trozos.append("RESPUESTA %d (de %s):\n%s" % (i, m.split(":")[-1], txt))

    encargo = (
        "Te doy %d respuestas de %d inteligencias artificiales distintas a la "
        "MISMA pregunta. Tu trabajo es cotejarlas, no repetirlas.\n\n"
        "PREGUNTA: %s\n\n%s\n\n"
        "Ahora escribe la respuesta buena para Angel, en espanol de Espana, "
        "hablado y sin markdown, siguiendo estas reglas:\n"
        "1. Si coinciden, da la respuesta directamente y con seguridad.\n"
        "2. Si se CONTRADICEN en algo que importa, DILO claramente: en que "
        "discrepan y cual te parece mas fiable y por que. No lo disimules.\n"
        "3. Si una ha metido un dato o un matiz que las otras no tienen y es "
        "bueno, incluyelo.\n"
        "4. Si hay cuentas, comprueba tu la aritmetica y corrige al que se "
        "haya equivocado.\n"
        "5. No menciones que eres varias IA ni cuentes este proceso. Habla "
        "como Berna, en primera persona."
        % (len(buenas), len(buenas), pregunta, "\n\n".join(trozos)))

    ponente = sorted(buenas, key=lambda x: x[2])[0][0]
    final, seg_p, err = _preguntar(ponente, [
        {"role": "system", "content": "Eres Berna, el asistente de Angel."},
        {"role": "user", "content": encargo}], cfg, maxtok=900)
    if err or not final:
        # si la ponente falla, se devuelve la primera respuesta antes que nada
        return _sin_markdown(buenas[0][1])

    total = max(s for _m, _t, s in buenas) + seg_p
    nota = ("\n\n[Lo he consultado con %d inteligencias artificiales y las he "
            "cotejado. %.1f s.]" % (len(buenas), total))
    return _sin_markdown(final) + nota


def estado_del_consejo():
    """Que IA hay disponibles hoy para el consejo."""
    cfg = _cfg()
    cands = _vocales(cfg, 4)
    l = ["LAS IA QUE PUEDO REUNIR EN CONSEJO:", ""]
    vivas = 0
    for m in cands:
        txt, seg, err = _preguntar(m, [{"role": "user", "content": "Di solo hola"}],
                                   cfg, maxtok=8)
        if err is None:
            vivas += 1
            l.append("  %-30s disponible, %.1f s" % (m.split(":")[-1], seg))
        elif "429" in str(err):
            l.append("  %-30s sin cuota por hoy" % m.split(":")[-1])
        else:
            l.append("  %-30s no contesta (%s)" % (m.split(":")[-1], err))
    l.append("")
    if vivas >= 2:
        l.append("Puedo reunir %d, asi que el consejo funciona. Usalo cuando la "
                 "pregunta lo merezca, no para todo." % vivas)
    else:
        l.append("Solo tengo %d disponible, asi que hoy no hay consejo posible: "
                 "hace falta al menos dos para poder cotejar." % vivas)
    l.append("Consejos convocados en la ultima hora: %d de %d."
             % (len(_HISTORIAL), MAX_CONSEJOS_HORA))
    return "\n".join(l)
