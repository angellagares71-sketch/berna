# -*- coding: utf-8 -*-
"""Lo que hace que Berna piense mas rapido y se equivoque menos.

Aqui vive lo que NO es ni la ventana ni las herramientas: decidir que
herramientas merece la pena ensenarle al modelo en cada frase, y resumir lo
viejo de la conversacion para que no se pierda al pasar de doce turnos.

POR QUE EXISTE (medido el 01-09-2026):
  Berna mandaba los 151 esquemas de herramientas EN CADA PETICION: 60.723
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

import re
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


def _palabras(t):
    """Las palabras de un texto, MAS su raiz de cuatro letras.

    Comparar palabras enteras se quedaba corto en castellano: "cantame",
    "cantale", "cante" y "cantar" son la misma cosa y no casaban entre si, asi
    que a "echate un cante" NO se le mandaba la herramienta de cantar y Berna
    contestaba que no sabia. Con la raiz de cuatro letras, "cant" las une todas.
    Cuatro y no cinco porque "cante" y "canta" ya se separan en la quinta.
    """
    salida = set()
    for p in _limpio(t).split():
        if len(p) > 3:
            salida.add(p)
            salida.add(p[:RAIZ])
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


def elegir(esquemas, texto, usadas=(), extra=(), tope=45):
    """Que herramientas se le ensenan al modelo para esta frase.

    `usadas` son las de los ultimos turnos (si acaba de mirar el tiempo, es muy
    probable que la siguiente frase siga por ahi). `extra` son las que ha pedido
    a proposito con mas_herramientas. `tope` es el maximo, para que una frase
    llena de palabras comunes no acabe mandandolas todas otra vez.
    """
    idx = indice(esquemas)
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
        n = len(pal & saco) + 3 * len(directas & saco)
        if n:
            puntos[nombre] = n

    elegidas = []
    fijas = list(NUCLEO)
    if "codigo" in temas_activos:
        fijas += list(CODIGO_ESENCIAL)
    for nombre in fijas + list(extra) + list(usadas):
        if nombre in idx and nombre not in elegidas:
            elegidas.append(nombre)
    for nombre, _n in sorted(puntos.items(), key=lambda x: -x[1]):
        if len(elegidas) >= tope:
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
