# -*- coding: utf-8 -*-
"""Lo que hace que Sobri piense mas rapido y se equivoque menos.

Aqui vive lo que NO es ni la ventana ni las herramientas: decidir que
herramientas merece la pena ensenarle al modelo en cada frase, y resumir lo
viejo de la conversacion para que no se pierda al pasar de doce turnos.

POR QUE EXISTE (medido el 01-09-2026):
  Sobri mandaba los 151 esquemas de herramientas EN CADA PETICION: 60.723
  caracteres, unos 15.180 tokens. Mas 2.689 del prompt de sistema. O sea que
  cada "hola" arrastraba ~18.000 tokens antes de empezar. Eso es lento, se come
  la cuota y ademas hace al modelo MAS TONTO: con 151 opciones delante acierta
  menos que con veinte bien elegidas.

COMO SE ARREGLA, sin perder ni una capacidad:
  1. En el prompt va la LISTA DE NOMBRES de todas (barata comparada con las fichas),
     asi el modelo siempre sabe todo lo que sabe hacer.
  2. Con esquema completo van solo las que hacen falta: un nucleo fijo, mas las
     que casan con lo que se acaba de hablar, mas las que se han usado hace
     poco.
  3. Si aun asi le falta una, tiene `mas_herramientas`: pide las de un tema y en
     la vuelta siguiente las tiene enteras. Nada queda fuera de su alcance.
"""

import math
import re
import time
import unicodedata

# Las que van SIEMPRE. Son las que sirven para casi cualquier peticion y las
# que mas se usan; dejarlas fuera saldria mas caro que llevarlas.
NUCLEO = (
    "buscar_en_internet", "leer_pagina_web", "hora_y_fecha", "recordar",
    "que_recuerdas", "ejecutar_orden", "hacer_tarea", "leer_archivo",
    "buscar_archivos", "mirar_pantalla", "estado_del_pc", "calcular",
    "el_tiempo", "recordarme", "poner_temporizador", "mas_herramientas",
)

# En modo de programacion estas forman un ciclo y tienen que viajar juntas:
# entender, tocar, comprobar y guardar. Con mas de doscientas herramientas,
# fiarlo todo al desempate por palabras podia dejar fuera justo una de ellas.
CODIGO_ESENCIAL = (
    "arbol_de_carpeta", "buscar_en_proyecto", "mapa_de_codigo",
    "ver_archivo", "editar_archivo", "insertar_en_archivo",
    "comprobar_codigo", "pasar_pruebas", "explicar_error",
    "git_estado", "git_cambios", "git_guardar",
)

# Palabras que apuntan a un grupo de herramientas. No hace falta que sean
# exhaustivas: lo que no case por aqui, casa por el nombre y la descripcion.
TEMAS = {
    "dron":     ("dron", "volar", "viento", "racha", "dji", "vuelo"),
    "foto":     ("foto", "imagen", "camara", "exif", "revelar", "raw"),
    "video":    ("video", "subtitulo", "transcribir", "grabacion", "editar"),
    "musica":   ("cancion", "cantar", "musica", "letra", "ritmo", "reggaeton",
                  "componer", "producir", "estudio", "ace", "generar",
                  "music", "musi", "musy", "music2000", "m2k", "riff", "bpm", "sample", "loop",
                  "ventana", "pantalla", "teclado", "raton", "clic", "control",
                  "boton", "coordenada"),
    "correo":   ("correo", "email", "gmail", "imap", "bandeja", "mensaje"),
    "agenda":   ("agenda", "calendario", "cita", "evento", "reunion"),
    "papeles":  ("pdf", "documento", "presupuesto", "factura", "word", "excel"),
    "skyrim":   ("skyrim", "mantella", "npc", "juego", "mod"),
    "casa":     ("ventana", "programa", "instalar", "abrir", "cerrar", "pantalla"),
    "dinero":   ("precio", "oferta", "comprar", "chollo", "oportunidad"),
    "berna":    ("actualizar", "version", "voz", "acento", "caracter", "muneco"),
    # la musica en redes: que casi cualquier frase de canal o subida traiga
    # el bloque entero, que ahi se encadenan preparar, subir y apuntar
    "redes":    ("youtube", "tiktok", "redes", "canal", "suscriptores", "visitas",
                 "vistas", "short", "shorts", "subir", "publicar", "comentarios",
                 "miniatura", "mercado", "tendencia", "tendencias", "suno", "viral",
                 "seguidores", "hashtag", "etiquetas", "estadisticas", "analiticas",
                 "manager", "subo", "sube"),
    # El tema de la "opcion code". Es el mas largo a proposito: cuando Angel
    # esta programando, casi cualquier palabra suya (error, funcion, linea,
    # libreria) tiene que traer las herramientas de codigo de golpe, que es
    # justo cuando se encadenan diez llamadas seguidas y no se puede estar
    # pidiendo mas_herramientas cada dos por tres.
    "codigo":   ("codigo", "codi", "programar", "programacion", "funcion",
                 "python", "script", "proyecto", "libreria", "modulo",
                 "error", "fallo", "bug", "traceback", "compilar", "depurar",
                 "prueba", "pruebas", "test", "linea", "lineas", "archivo",
                 "arreglar", "refactor", "json", "api", "servidor", "regex",
                 "expresion", "exe", "ejecutable", "requisitos",
                 "git", "repositorio", "commit", "rama", "github"),
}


def _limpio(t):
    t = unicodedata.normalize("NFD", (t or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]+", " ", t)


RAIZ = 4          # cuantas letras del principio valen como raiz

# Las claves de TRES letras de los temas (pdf, git, dji, bpm, npc, api, exe...).
# _palabras tiraba todo lo de tres letras o menos, asi que estas claves NUNCA
# casaban: "une estos dos pdf" no traia unir_pdfs (medido el 14-09-2026).
CORTAS = frozenset(w for claves in TEMAS.values()
                   for w in _limpio(" ".join(claves)).split() if len(w) <= 3)

# Una palabra que sale en muchas fichas ("archivo", "hace", "tiempo") no dice
# cual hace falta y llenaba el tope con herramientas de relleno. Solo puntuan
# las que salen en como mucho el 8 % de las fichas, y pesan mas cuanto mas raras;
# y solo entran las que llegan al 10 % de la mejor puntuacion. Medido el
# 14-09-2026 con 34 frases: 34/34 aciertos (antes 33) y ~6 % menos tokens.
COMUN = 0.08
RELATIVO = 0.1


def _palabras(t):
    """Las palabras de un texto, MAS su raiz de cuatro letras.

    Comparar palabras enteras se quedaba corto en castellano: "cantame",
    "cantale", "cante" y "cantar" son la misma cosa y no casaban entre si, asi
    que a "echate un cante" NO se le mandaba la herramienta de cantar y Sobri
    contestaba que no sabia. Con la raiz de cuatro letras, "cant" las une todas.
    Cuatro y no cinco porque "cante" y "canta" ya se separan en la quinta.
    """
    salida = set()
    for p in _limpio(t).split():
        if len(p) > 3:
            salida.add(p)
            salida.add(p[:RAIZ])
        elif p in CORTAS:
            salida.add(p)
    return salida


def indice(esquemas):
    """Para cada herramienta, el saco de palabras por el que se la encuentra."""
    idx = {}
    for e in esquemas:
        f = e.get("function") or {}
        nombre = f.get("name") or ""
        if not nombre:
            continue
        texto = nombre.replace("_", " ") + " " + (f.get("description") or "")
        idx[nombre] = _palabras(texto)
    return idx


def _pesos(idx):
    """Cuanto vale cada palabra: mas cuanto menos fichas la tienen (0 si es comun)."""
    total = len(idx) or 1
    cuantas = {}
    for saco in idx.values():
        for w in saco:
            cuantas[w] = cuantas.get(w, 0) + 1
    return {w: math.log(total / c) for w, c in cuantas.items() if c / total <= COMUN}


def elegir(esquemas, texto, usadas=(), extra=(), tope=45):
    """Que herramientas se le ensenan al modelo para esta frase.

    `usadas` son las de los ultimos turnos (si acaba de mirar el tiempo, es muy
    probable que la siguiente frase siga por ahi). `extra` son las que ha pedido
    a proposito con mas_herramientas. `tope` es el maximo, para que una frase
    llena de palabras comunes no acabe mandandolas todas otra vez.
    """
    idx = indice(esquemas)
    peso = _pesos(idx)
    directas = _palabras(texto)
    pal = set(directas)

    # los temas amplian la busqueda: "el dron" trae todas las de dron
    temas_activos = []
    for tema, claves in TEMAS.items():
        palabras_tema = _palabras(" ".join(claves))
        if pal & palabras_tema:
            pal |= palabras_tema
            temas_activos.append(tema)

    puntos = {}
    for nombre, saco in idx.items():
        # Lo que Angel ha dicho de verdad pesa mas que las palabras anadidas
        # por tema. Asi "guarda" no se pierde entre cuarenta herramientas de
        # codigo solo porque tambien haya dicho "programando".
        n = (sum(peso.get(w, 0) for w in pal & saco)
             + 3 * sum(peso.get(w, 0) for w in directas & saco))
        if n > 0:
            puntos[nombre] = n

    elegidas = []
    fijas = list(NUCLEO)
    if "codigo" in temas_activos:
        fijas += list(CODIGO_ESENCIAL)
    for nombre in fijas + list(extra) + list(usadas):
        if nombre in idx and nombre not in elegidas:
            elegidas.append(nombre)
    mejor = max(puntos.values(), default=0)
    for nombre, n in sorted(puntos.items(), key=lambda x: -x[1]):
        if len(elegidas) >= tope or n < RELATIVO * mejor:
            break
        if nombre not in elegidas:
            elegidas.append(nombre)

    orden = {e["function"]["name"]: e for e in esquemas
             if (e.get("function") or {}).get("name")}
    return [orden[n] for n in elegidas if n in orden]


def por_tema(esquemas, tema, tope=25):
    """Las herramientas que casan con un tema. Para `mas_herramientas`."""
    idx = indice(esquemas)
    pal = _palabras(tema)
    for _t, claves in TEMAS.items():
        palabras_tema = _palabras(" ".join(claves))
        if pal & palabras_tema:
            pal |= palabras_tema
    puntos = {n: len(pal & s) for n, s in idx.items() if pal & s}
    orden = {e["function"]["name"]: e for e in esquemas
             if (e.get("function") or {}).get("name")}
    salida = []
    for n, _p in sorted(puntos.items(), key=lambda x: -x[1])[:tope]:
        if n in orden:
            salida.append(orden[n])
    return salida


def catalogo(esquemas):
    """La lista de nombres, para el prompt. Barata y lo dice todo."""
    ns = [(e.get("function") or {}).get("name") for e in esquemas]
    return ", ".join(sorted(n for n in ns if n))


# La valvula de escape: si le falta una herramienta, la pide por tema y en la
# vuelta siguiente la tiene entera. Asi ninguna capacidad queda fuera de su
# alcance por haberla dejado fuera de esta peticion.
ESQUEMA_MAS = {
    "type": "function",
    "function": {
        "name": "mas_herramientas",
        "description": (
            "Pide las herramientas de un tema cuando la que necesitas no esta "
            "entre las que tienes ahora mismo. Las tendras enteras en tu "
            "siguiente turno. Usalo en vez de decir que no puedes."),
        "parameters": {
            "type": "object",
            "properties": {
                "tema": {"type": "string",
                         "description": "El tema o el nombre de la herramienta "
                                        "que te falta. Por ejemplo: dron, fotos, "
                                        "correo, skyrim, pdf."}},
            "required": ["tema"],
        },
    },
}


def bloque_de_prompt(esquemas):
    """Lo que se le cuenta al modelo sobre sus herramientas.

    Va la lista ENTERA de nombres, que es barata, para que sepa siempre todo lo
    que sabe hacer aunque en esta peticion solo lleve unas pocas con su ficha
    completa.
    """
    return ("\n\nTUS HERRAMIENTAS: en cada turno llevas la ficha completa solo "
            "de las que hacen falta para lo que se esta hablando, no de las "
            "de todas. Estas son TODAS las que tienes:\n" + catalogo(esquemas) +
            "\nSi necesitas una que ahora no llevas, llama a mas_herramientas "
            "con el tema y en tu siguiente turno la tendras. Nunca digas que no "
            "puedes hacer algo que este en esa lista.")


# ------------------------------------------------------ cuanto apartar un cerebro
# Cuanto tiempo se deja sin llamar a un modelo que acaba de fallar. Vive aqui
# para que la ventana y el movil apliquen LA MISMA regla (14-09-2026): el movil
# ya distinguia la cuota del dia, pero la ventana apartaba 30 minutos CUALQUIER
# 429, y un simple pico por minuto dejaba a Sobri sin ningun Gemini a la vez.
UN_DIA_DE_CUOTA = 6 * 60 * 60


def detalle_429(cuerpo):
    """Lo que importa de un 429 de Google, en pocas palabras.

    Devuelve algo como " PerDay", " PerMinute reintentar 37s" o "". El tipo sale
    del quotaId ("...PerDayPerProjectPerModel...") y la espera del retryDelay.
    """
    t = str(cuerpo or "")
    trozos = []
    if "PerDay" in t:
        trozos.append("PerDay")
    elif "PerMinute" in t:
        trozos.append("PerMinute")
    m = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', t)
    if m:
        trozos.append("reintentar %ds" % math.ceil(float(m.group(1))))
    return "".join(" " + x for x in trozos)


# Un cerebro que cae UNA Y OTRA VEZ por saturacion se aparta cada vez mas: el
# 18-09-2026 gemini-3.8-flash dio 503 o se quedo sin contestar en casi cada
# frase, y con 3 minutos fijos Sobri volvia a tropezar con el en la siguiente.
# Ahora: 3 min, 15 min, 1 h. La racha se olvida con un acierto (fue_bien) o si
# pasan dos horas sin fallar.
ESCALONES = (1, 5, 20)
OLVIDO_RACHA = 2 * 60 * 60
_racha = {}
_CORTES = ("timeout", "timed out", "connectionpool", "connection aborted",
           "connection reset", "max retries")


def _es_saturado(e):
    b = e.lower()
    return "503" in e or "HTTP 5" in e or any(x in b for x in _CORTES)


def cuanto_apartar(error, cuota=30 * 60, saturado=3 * 60, modelo=None):
    """Segundos que se aparta un cerebro segun su error. 0 = no apartarlo.

    - cuota del dia agotada ("PerDay"): horas, que antes de manana no vuelve.
    - pico por minuto: lo que pide Google (+5 s), entre 30 s y 5 min; si no lo
      dice, un minuto.
    - otro 429 (o el tope diario de OpenRouter): `cuota`, como siempre.
    - saturado (5xx, se ha agotado el tiempo o se ha cortado la conexion):
      `saturado`, y si se pasa el `modelo`, multiplicado por su racha.
    """
    e = str(error or "")
    if "PerDay" in e:
        return UN_DIA_DE_CUOTA
    if "429" in e or e == "CUOTA_DIARIA":
        m = re.search(r"reintentar (\d+)s", e)
        if m:
            return min(max(int(m.group(1)) + 5, 30), 5 * 60)
        if "PerMinute" in e:
            return 60
        return cuota
    if _es_saturado(e):
        if modelo is None:
            return saturado
        veces, cuando = _racha.get(modelo, (0, 0.0))
        if time.time() - cuando > OLVIDO_RACHA:
            veces = 0
        veces += 1
        _racha[modelo] = (veces, time.time())
        return saturado * ESCALONES[min(veces, len(ESCALONES)) - 1]
    return 0


def fue_bien(modelo):
    """Ese cerebro ha contestado: se le olvida la racha de fallos."""
    _racha.pop(modelo, None)


def rato(segundos):
    """'40 s', '3 min', '6 h': para el registro."""
    s = int(segundos)
    if s < 120:
        return "%d s" % s
    if s < 2 * 3600:
        return "%d min" % (s // 60)
    return "%d h" % (s // 3600)
