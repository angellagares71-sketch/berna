# -*- coding: utf-8 -*-
"""Escribe las peticiones para Suno, que es donde de verdad se decide todo.

POR QUE ESTE MODULO (04/09/2026)
--------------------------------
Sobri monta bases con trozos grabados (musica_loops.py), y para eso vale. Pero
una cancion terminada y actual no la hace: apilar bloques prefabricados tiene
un techo, y Angel lo describio perfecto: suena a musica de Mega Drive, que es
exactamente el mismo principio (muestras + patrones).

Lo que si hace canciones de verdad hoy es Suno. Y Suno NO tiene API publica
-solo un programa cerrado de socios-, asi que Sobri no puede pedirselas sola.
Las "APIs" de terceros que circulan incumplen sus condiciones de uso, que
prohiben el acceso automatizado, y pueden costar la cuenta. NO USARLAS.

Lo que si se puede hacer, que ademas es donde esta la diferencia entre una
cancion mediocre y una buena, es escribir bien la peticion. Eso es lo que hay
aqui: Sobri redacta el texto y Angel lo pega.

LAS REGLAS, sacadas de las guias de 2026:
  - Entre 8 y 15 etiquetas. Menos de 5 es vago; mas de 20 se diluye.
  - El orden manda: genero primero (el primero pesa mas), luego instrumento
    principal, dos o tres de acompanamiento, velocidad EXACTA, tono, ambiente,
    y al final lo que NO se quiere.
  - Pasados unos 350 caracteres el modelo empieza a ignorar el resto.
  - En regueton la palabra decisiva es "dembow rhythm", no "reggaeton": sin
    ella devuelve pop latino generico.
  - La estructura se manda aparte, en la caja de la letra, con [Intro],
    [Verse], [Chorus], [Bridge], [Outro].
"""

# genero(s) -> descripcion en el idioma que entiende Suno, que es el ingles
ESTILOS = {
    "reggaeton": {
        "tags": ["reggaeton", "dembow rhythm", "deep punchy sub bass",
                 "latin percussion", "bright synth stabs",
                 "spanish male vocals", "modern club production"],
        "bpm": 95, "tono": "A minor", "ambiente": "night club, confident",
    },
    "reggaeton romantico": {
        "tags": ["reggaeton romantico", "smooth dembow rhythm", "warm sub bass",
                 "soft piano", "latin percussion", "melodic spanish vocals",
                 "lush reverb production"],
        "bpm": 92, "tono": "F# minor", "ambiente": "romantic, sensual, late night",
    },
    "trap": {
        "tags": ["latin trap", "808 slides", "crisp hi hat rolls",
                 "dark piano", "spanish male vocals", "sparse arrangement",
                 "modern trap production"],
        "bpm": 140, "tono": "C minor", "ambiente": "dark, moody, street",
    },
    "hiphop": {
        "tags": ["boom bap hip hop", "dusty drum break", "upright bass",
                 "jazzy piano samples", "vinyl crackle", "spanish rap vocals",
                 "90s production"],
        "bpm": 92, "tono": "D minor", "ambiente": "nostalgic, laid back",
    },
    "breakbeat": {
        "tags": ["breakbeat", "chopped amen break", "rolling sub bass",
                 "rave stabs", "filtered pads", "instrumental",
                 "punchy analog production"],
        "bpm": 135, "tono": "G minor", "ambiente": "energetic, warehouse",
    },
    "house": {
        "tags": ["house", "four on the floor kick", "deep rolling bassline",
                 "warm rhodes chords", "soulful female vocals", "hand claps",
                 "clean club production"],
        "bpm": 124, "tono": "A minor", "ambiente": "uplifting, sunset terrace",
    },
    "salsa": {
        "tags": ["salsa", "montuno piano", "brass section", "congas and timbales",
                 "walking upright bass", "spanish male vocals",
                 "live band recording"],
        "bpm": 190, "tono": "G minor", "ambiente": "joyful, dancefloor",
    },
    "bachata": {
        "tags": ["bachata", "requinto guitar lead", "bongo and guira",
                 "warm bass", "romantic spanish vocals", "modern production"],
        "bpm": 128, "tono": "B minor", "ambiente": "romantic, heartfelt",
    },
    "drill": {
        "tags": ["latin drill", "sliding 808 bass", "skippy hi hats",
                 "dark string stabs", "spanish male vocals", "sparse mix",
                 "aggressive modern production"],
        "bpm": 142, "tono": "F minor", "ambiente": "cold, tense, night",
    },
}

# Lo que casi nunca se quiere y conviene decir explicitamente. OJO: "no lo-fi"
# NO puede ir en el boom bap ni en el lofi, porque ahi lo sucio y el vinilo son
# el genero, no un defecto. Pedirlo seria contradecirse en la misma frase.
FUERA = "no muddy mix, no midi sounding instruments"
FUERA_LIMPIO = FUERA + ", no lo-fi"
SIN_LIMPIAR = ("hiphop", "lofi")


def _norma(t):
    return (t or "").strip().lower().replace("ó", "o").replace("é", "e")


def peticion(estilo="reggaeton", bpm=0, tono="", ambiente="", instrumental=False,
             extra=""):
    """El texto que se pega en la casilla 'Style' de Suno."""
    e = ESTILOS.get(_norma(estilo))
    if not e:
        disponibles = ", ".join(sorted(ESTILOS))
        return "No tengo plantilla de ese estilo. Tengo: %s" % disponibles

    tags = list(e["tags"])
    if instrumental:
        tags = [t for t in tags if "vocal" not in t] + ["instrumental"]
    if extra:
        tags.append(extra.strip())

    fuera = FUERA if _norma(estilo) in SIN_LIMPIAR else FUERA_LIMPIO

    def _armar():
        return "%s, %s, %d bpm, %s, %s" % (
            ", ".join(tags), ambiente or e["ambiente"],
            int(bpm) if bpm else e["bpm"], tono or e["tono"], fuera)

    texto = _armar()
    # pasados ~350 caracteres Suno empieza a ignorar; se recorta por etiquetas
    while len(texto) > 350 and len(tags) > 6:
        tags.pop(-2)
        texto = _armar()
    return texto


def estructura(estribillos=2, con_puente=True, instrumental=False):
    """El esqueleto que se pega en la casilla de la letra.

    Va aparte de la peticion a proposito: las etiquetas entre corchetes son
    instrucciones de estructura, no se cantan, y Suno solo las lee ahi.
    """
    partes = ["[Intro]"]
    for i in range(estribillos):
        partes += ["[Verse]", "[Pre-Chorus]", "[Chorus]"]
        if i == 0 and con_puente:
            continue
    if con_puente:
        partes += ["[Bridge]", "[Chorus]"]
    partes += ["[Outro]", "[End]"]
    if instrumental:
        partes = [p for p in partes if p not in ("[Pre-Chorus]",)]
    return "\n\n".join(partes)


def preparar(estilo="reggaeton", bpm=0, tono="", instrumental=False, extra=""):
    """Todo listo para copiar y pegar en Suno."""
    p = peticion(estilo, bpm=bpm, tono=tono, instrumental=instrumental,
                 extra=extra)
    if p.startswith("No tengo"):
        return p
    return "\n".join([
        "Para Suno, estilo %s:" % estilo,
        "",
        "1) Pega esto en la casilla 'Style' (%d caracteres):" % len(p),
        "",
        "   " + p,
        "",
        "2) Y esto en la casilla de la letra, encima de lo que escribas:",
        "",
        "\n".join("   " + l for l in estructura(
            instrumental=instrumental).splitlines()),
        "",
        "Consejo: si no te convence, NO reescribas todo. Cambia UNA cosa y",
        "vuelve a generar. Las etiquetas son pistas, no ordenes: a veces las",
        "ignora y con darle otra vez sale.",
    ])


def estilos():
    return sorted(ESTILOS)


if __name__ == "__main__":
    for e in ("reggaeton", "hiphop", "breakbeat"):
        print(preparar(e))
        print("\n" + "=" * 70 + "\n")
