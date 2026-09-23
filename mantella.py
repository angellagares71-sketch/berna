# -*- coding: utf-8 -*-
r"""
Sobri manejando MANTELLA, la IA que hace hablar a los NPCs de Skyrim.

Angel monto Mantella el 24/08/2026 y desde entonces cada vez que algo fallaba
habia que venir a Claude a leer un log de 2.000 lineas. Esto es para que no
haga falta: Sobri arranca el juego, arranca Mantella, mira el log, TRADUCE el
fallo a cristiano y, cuando es cosa del modelo, prueba modelos y se queda con
el mejor.

LAS RUTAS, que no son las obvias (actualizadas el 28/08/2026, el montaje se
mudo de C:\Modding\MO2 a C:\Games\SkyrimIA):
  - El programa:  C:\Games\SkyrimIA\ModOrganizer2\mods\Mantella\SKSE\Plugins\MantellaSoftware\Mantella.exe
  - El config.ini NO esta en la carpeta del mod, y AQUI TAMPOCO esta donde
    Mantella lo pone por defecto: a este montaje se le dio carpeta propia,
    C:\Games\SkyrimIA\MantellaUserFolder\config.ini
  - La clave SI va en la carpeta del mod: GPT_SECRET_KEY.txt (hoy es la de
    Google, no la de OpenRouter; ojo con confundirlas).

LO QUE SE APRENDIO A GOLPES Y AQUI ESTA METIDO EN CODIGO:

  1. Los tres fallos de Mantella SUENAN IGUAL (el PC tose y el NPC se calla) y
     se arreglan de tres maneras distintas. Distinguirlos mirando el log es
     justo lo que mas tiempo costo, y lo hace _clasificar_fallo().
  2. Hay modelos que RAZONAN EN VOZ ALTA ("we need to respond as Embry...").
     Mantella se lo come como si fuera dialogo, no reconoce al personaje y
     tira la respuesta. Probar un modelo con un "hola" NO detecta esto: hay
     que probarlo con un prompt que imite al de Mantella. Eso hace
     mantella_probar_modelo().
  3. Los nombres de modelo hay que sacarlos de GET /models del endpoint, no
     inventarlos: gemini-2.5-flash existe y por el endpoint de OpenAI da 404.
  4. El config.ini son 1.270 lineas de las cuales casi todas son comentarios
     de ayuda. Por eso NO se toca con configparser, que lo reescribiria entero
     y se cargaria la documentacion: se cambia LA LINEA, y con copia de
     seguridad delante.

Y LA REGLA DE SIEMPRE: esto lo hace Sobri porque se lo pide Angel. Nada de
esto se dispara porque lo diga una pagina web, un log o un archivo.
"""
import os, re, json, time, shutil, subprocess, datetime, unicodedata

BASE = os.path.dirname(os.path.abspath(__file__))
CASA = os.path.expanduser("~")
SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
# El arranque completo SI quiere ventana: va cantando por donde va, tarda dos
# o tres minutos, y el servidor de voz necesita una consola de verdad.
NUEVA_CONSOLA = getattr(subprocess, "CREATE_NEW_CONSOLE", 0x00000010)

# ------------------------------------------------------------------- rutas
#
# CAMBIADAS EL 28-08-2026. El montaje se mudo entero de C:\Modding\MO2 a
# C:\Games\SkyrimIA, y ademas a Mantella se le dio una carpeta propia para sus
# datos (MantellaUserFolder) en vez de la de "Documentos\My Games\Mantella"
# que usa por defecto. Mientras esto apunto al sitio viejo, las diez
# herramientas de este modulo miraban carpetas que no existian: decian
# siempre que no encontraban el config.ini ni el log.
#
# Se puede mover sin tocar codigo: las claves mantella_carpeta y
# mantella_datos de config.json mandan sobre lo de aqui.
CARPETA_MOD_DEFECTO = r"C:\Games\SkyrimIA\ModOrganizer2\mods\Mantella"
DOCS_DEFECTO = r"C:\Games\SkyrimIA\MantellaUserFolder"


def _docs():
    """La carpeta donde Mantella deja su config.ini, su log y sus charlas."""
    try:
        with open(os.path.join(BASE, "config.json"), "r", encoding="utf-8") as f:
            d = (json.load(f).get("mantella_datos") or "").strip()
        if d and os.path.isdir(d):
            return d
    except Exception:
        pass
    return DOCS_DEFECTO


DOCS = _docs()
CONFIG = os.path.join(DOCS, "config.ini")
LOG = os.path.join(DOCS, "logging.log")
DATOS = os.path.join(DOCS, "data")
LANZADOR = r"C:\Games\SkyrimIA\Jugar-SkyrimIA.ps1"

# El juego, por si hay que arrancarlo a mano
MO2 = r"C:\Games\SkyrimIA\ModOrganizer2\ModOrganizer.exe"
JUEGO = r"C:\Games\SkyrimIA\ModOrganizer2\mods"

# Cuanto se espera como maximo en cada cosa. Leccion de buscar_en_contenido:
# el bucle de herramientas es sincrono y cuelga la ventana entera, asi que
# TODO lo que toque disco o red lleva tope.
ESPERA_RED = 25
ESPERA_ARRANQUE = 40


def _carpeta_mod():
    """Donde vive el mod. Se puede cambiar en config.json sin tocar codigo."""
    try:
        with open(os.path.join(BASE, "config.json"), "r", encoding="utf-8") as f:
            c = (json.load(f).get("mantella_carpeta") or "").strip()
        if c and os.path.isdir(c):
            return c
    except Exception:
        pass
    return CARPETA_MOD_DEFECTO


def _exe():
    return os.path.join(_carpeta_mod(), "SKSE", "Plugins", "MantellaSoftware",
                        "Mantella.exe")


def _archivo_clave():
    return os.path.join(_carpeta_mod(), "GPT_SECRET_KEY.txt")


def _sin_tildes(t):
    t = unicodedata.normalize("NFD", str(t or ""))
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower()


def _apuntar(que, detalle, resultado):
    try:
        import tareas
        tareas._apuntar(que, detalle, resultado)
    except Exception:
        pass


# ------------------------------------------------------------- el config.ini
def tiene_bom():
    """True si el config.ini empieza por BOM, que lo deja INSERVIBLE.

    Mantella lee su config.ini con configparser en utf-8 pelado. Si el fichero
    empieza por BOM (los tres bytes EF BB BF), la primera linea deja de ser
    "[Game]" y pasa a ser "﻿[Game]", configparser lanza
    MissingSectionHeaderError y Mantella **se traga el error y tira con los
    valores de fabrica**: se cree que juega a SkyrimVR y pide una clave de
    OpenRouter que aqui no hace falta. No avisa de que ha ignorado el fichero.

    Paso el 28-08-2026: al bajar audio_threshold de 0.07 a 0.01 para los Sony
    nuevos, quien escribio el fichero le puso BOM (en PowerShell 5.1,
    `Set-Content -Encoding utf8` lo pone siempre). El ajuste no llego a
    aplicarse NUNCA y ademas se anulo el config entero, con dos dias de
    trabajo dentro.
    """
    try:
        with open(CONFIG, "rb") as f:
            return f.read(3) == b"\xef\xbb\xbf"
    except Exception:
        return False


def _leer_config():
    """Devuelve (lineas, codificacion). El fichero no siempre es utf-8.

    Se lee con utf-8-sig, que QUITA el BOM si lo hay, y se devuelve siempre
    "utf-8" como codificacion de escritura para que no se vuelva a poner. Con
    utf-8 a secas el BOM se colaba como un caracter mas al principio de la
    primera linea y volvia al disco en cada escritura: el fichero se quedaba
    roto para siempre y Sobri era quien lo mantenia roto.
    """
    with open(CONFIG, "rb") as f:
        crudo = f.read()
    for cod in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return crudo.decode(cod).splitlines(True), "utf-8"
        except Exception:
            continue
    return crudo.decode("utf-8", "replace").splitlines(True), "utf-8"


def _ajustes():
    """Todos los 'clave = valor' del config.ini, sin los comentarios."""
    d = {}
    try:
        lineas, _ = _leer_config()
    except Exception:
        return d
    for n, l in enumerate(lineas, 1):
        m = re.match(r"^([a-z_][a-z0-9_]*)\s*=\s*(.*?)\s*$", l)
        if m and m.group(1) not in d:
            d[m.group(1)] = (m.group(2), n)
    return d


def _valor(clave, por_defecto=""):
    v = _ajustes().get(clave)
    return v[0] if v else por_defecto


def _escribir_ajuste(clave, valor):
    """Cambia UNA linea del config.ini, con copia de seguridad delante.

    Devuelve (ok, mensaje). No usa configparser a proposito: el fichero es
    casi todo documentacion y configparser la borraria.
    """
    try:
        lineas, cod = _leer_config()
    except Exception as e:
        return False, "no he podido leer el config.ini: %s" % e

    sitio = None
    for i, l in enumerate(lineas):
        if re.match(r"^%s\s*=" % re.escape(clave), l):
            sitio = i
            break
    if sitio is None:
        return False, "en el config.ini no hay ninguna linea que ponga '%s'" % clave

    viejo = lineas[sitio].rstrip("\r\n")
    fin = lineas[sitio][len(viejo):] or "\n"
    sello = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    copia = CONFIG + ".bak-berna-" + sello
    try:
        shutil.copy2(CONFIG, copia)
    except Exception as e:
        return False, "no he podido hacer la copia de seguridad: %s" % e

    lineas[sitio] = "%s = %s%s" % (clave, valor, fin)
    try:
        with open(CONFIG, "w", encoding=cod, newline="") as f:
            f.writelines(lineas)
    except Exception as e:
        try:
            shutil.copy2(copia, CONFIG)
        except Exception:
            pass
        return False, "no he podido escribir el config.ini: %s" % e
    return True, "antes ponia '%s' y ahora pone '%s = %s'. Copia en %s" % (
        viejo.strip(), clave, valor, os.path.basename(copia))


# Lo que Sobri puede cambiar, y como se comprueba que el valor vale. Fuera de
# esta lista no toca nada: el config.ini tiene 160 ajustes y la mayoria son
# prompts enteros o rutas que romperian el montaje.
def _uno_de(*opciones):
    def comprobar(v):
        if _sin_tildes(v) in [_sin_tildes(o) for o in opciones]:
            return None
        return "tiene que ser uno de estos: %s" % ", ".join(opciones)
    return comprobar


def _numero(minimo, maximo):
    def comprobar(v):
        try:
            x = float(v)
        except Exception:
            return "tiene que ser un numero"
        return None if minimo <= x <= maximo else "tiene que estar entre %s y %s" % (minimo, maximo)
    return comprobar


def _carpeta_existente(v):
    return None if os.path.isdir(v) else "esa carpeta no existe en el disco"


# Los codigos que acepta Whisper son de DOS letras. Poner 'es-ES' parece mas
# correcto y lo tumba entero: 'es-ES is not a valid language code'. Paso de
# verdad el 27/08 y dejo a Angel sin microfono en el juego.
IDIOMAS = ("default", "af", "ar", "be", "bg", "bn", "ca", "cs", "cy", "da",
           "de", "el", "en", "es", "et", "eu", "fa", "fi", "fr", "gl", "he",
           "hi", "hr", "hu", "id", "is", "it", "ja", "ko", "lt", "lv", "ms",
           "nl", "no", "pl", "pt", "ro", "ru", "sk", "sl", "sr", "sv", "th",
           "tr", "uk", "ur", "vi", "zh")


def _idioma(v):
    if str(v).strip() in IDIOMAS:
        return None
    return ("tiene que ser un codigo de DOS letras como 'es', no '%s'. Los de "
            "cuatro tipo 'es-ES' los rechaza Whisper y te quedas sin microfono" % v)


def _libre(v):
    return None


AJUSTABLES = {
    # el cerebro
    "model": (_libre, "el modelo de IA que pone las palabras en boca de los NPC"),
    "llm_api": (_libre, "la direccion del servicio de IA"),
    # el idioma y el oido
    "language": (_idioma, "el idioma en que hablan los NPC"),
    "stt_service": (_uno_de("Whisper", "Moonshine"),
                    "que motor te entiende cuando hablas (Moonshine SOLO sabe ingles)"),
    "whisper_model_size": (_uno_de("tiny", "base", "small", "medium", "large"),
                           "cuanto se esfuerza Whisper en entenderte"),
    "stt_language": (_idioma, "en que idioma te escucha (default = que lo adivine)"),
    "audio_threshold": (_numero(0, 1), "a partir de que volumen considera que hablas"),
    "pause_threshold": (_numero(0, 5), "cuanto callas para que de por terminada tu frase"),
    "listen_timeout": (_numero(0, 300), "cuanto te espera antes de rendirse"),
    "ptt_enabled": (_uno_de("True", "False"), "hablar solo mientras pulsas una tecla"),
    "ptt_hotkey": (_libre, "la tecla de hablar"),
    # la voz
    "pace": (_numero(0.3, 3), "lo deprisa que hablan los NPC"),
    "number_words_tts": (_numero(0, 20), "hasta que numero se dice en letra"),
    # la conversacion
    "max_response_sentences_single": (_numero(1, 20), "cuantas frases suelta un NPC de una vez"),
    "max_response_sentences_multi": (_numero(1, 30), "lo mismo cuando hablan varios"),
    "narration_handling": (_uno_de("Cut narrations", "Narrator", "Character"),
                           "que hacer si el modelo escribe acotaciones tipo *se rie*"),
    "automatic_greeting": (_uno_de("True", "False"), "que el NPC salude el primero"),
    "conversation_summary_enabled": (_uno_de("True", "False"),
                                     "que los NPC se acuerden de charlas anteriores"),
    "play_cough_sound": (_uno_de("True", "False"), "el sonido de tos cuando hay un fallo"),
    "player_character_description": (_libre, "como es tu personaje, para que lo sepan"),
    # el resumidor y la vista
    "summary_llm_enabled": (_uno_de("True", "False"), "usar un modelo aparte para los resumenes"),
    "summary_llm_api": (_libre, "el servicio del resumidor"),
    "summary_llm": (_libre, "el modelo del resumidor"),
    "vision_enabled": (_uno_de("True", "False"), "que los NPC VEAN lo que hay en pantalla"),
    "vision_llm_api": (_libre, "el servicio que mira las capturas"),
    "vision_model": (_libre, "el modelo que mira las capturas"),
    "piper_folder": (_carpeta_existente,
                     "donde esta piper.exe. VACIO deja MUDOS a los NPC"),
    "lipgen_folder": (_libre, "donde esta el generador de sincronia labial"),
    # las dos trampas del montaje: se pueden cambiar, pero comprobadas
    "game": (_uno_de("Skyrim", "SkyrimVR", "Fallout4", "Fallout4VR"),
             "a que juego se conecta. VIENE MAL DE FABRICA (SkyrimVR)"),
    "skyrim_mod_folder": (_carpeta_existente,
                          "la carpeta del mod. Si esta mal, los NPC repiten la misma frase"),
}


# ------------------------------------------------------------------ procesos
def _procesos():
    """Que hay corriendo ahora mismo de todo esto."""
    fuera = {"mantella": None, "skyrim": None, "mo2": None, "steam": None}
    try:
        import psutil
    except Exception:
        return fuera
    for p in psutil.process_iter(["name", "pid", "create_time"]):
        try:
            n = (p.info.get("name") or "").lower()
        except Exception:
            continue
        if n == "mantella.exe":
            fuera["mantella"] = p.info
        elif n in ("skyrimse.exe", "skyrim.exe", "skyrimvr.exe"):
            fuera["skyrim"] = p.info
        elif n == "modorganizer.exe":
            fuera["mo2"] = p.info
        elif n == "steam.exe":
            fuera["steam"] = p.info
    return fuera


def _servidor_vivo():
    """Mantella levanta su interfaz web en el puerto del config (4999)."""
    puerto = _valor("port", "4999")
    try:
        import requests
        requests.get("http://127.0.0.1:%s" % puerto, timeout=3)
        return True
    except Exception:
        return False


# --------------------------------------------------------------- la clave
def _cerebro_local():
    """True si el modelo corre en este PC, en cuyo caso NO hace falta clave.

    Angel lo tiene asi desde el 28/08/2026: koboldcpp sirviendo un Llama 3.1
    en el puerto 5001. Sale gratis y funciona sin internet.
    """
    api = _sin_tildes(_valor("llm_api"))
    if any(x in api for x in ("koboldcpp", "kobold", "local", "llama.cpp",
                              "textgen", "ollama", "lm studio", "lmstudio")):
        return True
    # Tambien vale cualquier direccion que apunte a esta misma maquina.
    return "127.0.0.1" in api or "localhost" in api


def _clave():
    try:
        with open(_archivo_clave(), "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def _pinta_de_clave(k):
    """Que clave parece. OJO: las nuevas de Google empiezan por AQ. y miden 53,
    no AIza/39. Una validacion que exija AIza rechaza una clave buena."""
    if not k:
        return "no hay clave"
    if k.startswith("sk-or-"):
        return "de OpenRouter"
    if k.startswith("AQ.") or k.startswith("AIza"):
        return "de Google"
    if k.startswith("sk-"):
        return "de OpenAI"
    return "de un servicio que no reconozco"


# =========================================================== 1. COMO ESTA TODO
def mantella_estado():
    """Repasa el montaje entero y dice, en cristiano, si esta listo para jugar."""
    a = _ajustes()
    if not a:
        return ("No encuentro el config.ini de Mantella en %s. O Mantella no se "
                "ha arrancado nunca (se genera solo la primera vez) o esta "
                "instalado en otro sitio." % CONFIG)

    pr = _procesos()
    l = ["ESTADO DE MANTELLA (la IA de los NPC de Skyrim)", ""]

    # Lo primero de todo, porque si pasa esto lo demas que se lea del fichero
    # es MENTIRA: aqui pondra lo que diga el config.ini, pero Mantella no lo
    # ha leido y esta tirando con los valores de fabrica.
    if tiene_bom():
        l.append("*** OJO, ESTO PRIMERO ***")
        l.append("  El config.ini empieza por BOM y Mantella NO LO ESTA")
        l.append("  LEYENDO. Se cree que juegas a SkyrimVR y pide una clave de")
        l.append("  OpenRouter que no hace falta. Todo lo que ponga aqui abajo")
        l.append("  es lo que dice el fichero, no lo que Mantella esta usando.")
        l.append("  Se arregla con mantella_quitar_bom().")
        l.append("")

    l.append("CORRIENDO AHORA:")
    l.append("  Mantella: " + ("SI, encendido" if pr["mantella"] else "no, apagado"))
    l.append("  Skyrim:   " + ("SI, jugando" if pr["skyrim"] else "no"))
    l.append("  MO2:      " + ("abierto" if pr["mo2"] else "cerrado"))
    l.append("  Steam:    " + ("abierto" if pr["steam"] else "cerrado"))
    if pr["mantella"]:
        l.append("  Su pagina interna: " + ("responde" if _servidor_vivo()
                                            else "NO responde (raro, esta arrancando o se ha colgado)"))

    l.append("")
    l.append("COMO ESTA CONFIGURADO:")
    l.append("  Juego:    %s" % _valor("game", "?"))
    l.append("  Idioma:   %s" % _valor("language", "?"))
    l.append("  Cerebro:  %s en %s" % (_valor("model", "?"), _valor("llm_api", "?")))
    l.append("  Te oye:   %s (%s)" % (_valor("stt_service", "?"),
                                      _valor("whisper_model_size", "-")))
    l.append("  Voz:      %s" % _valor("tts_service", "?"))

    k = _clave()
    l.append("  Clave:    %s, %d caracteres, empieza por %s"
             % (_pinta_de_clave(k), len(k), (k[:4] + "...") if k else "-"))

    l.append("")
    l.append("REVISION:")
    fallos, avisos = [], []

    if not os.path.isfile(_exe()):
        fallos.append("no encuentro Mantella.exe en %s" % _exe())
    if _valor("game") == "SkyrimVR":
        fallos.append("'game' pone SkyrimVR y el juego de Angel NO es el de VR. "
                      "Asi Mantella ni arranca. Viene mal de fabrica")
    carp = _valor("skyrim_mod_folder")
    if carp and not os.path.isdir(carp):
        fallos.append("'skyrim_mod_folder' apunta a %s, que no existe. Con esto "
                      "los NPC repiten la misma frase en bucle" % carp)
    if not k and not _cerebro_local():
        fallos.append("no hay clave en %s" % _archivo_clave())
    elif not k:
        # Con el modelo corriendo en el propio PC no hace falta clave ninguna.
        # Sin esta salvedad, Sobri cantaba "FALLO GORDO: no hay clave" cada vez
        # y mandaba a Angel a buscar un problema que no existe. Paso el
        # 28/08/2026, cuando el montaje se paso a koboldcpp en el puerto 5001.
        avisos.append("no hay clave, pero da igual: el cerebro (%s) corre en "
                      "este mismo ordenador y no la necesita"
                      % _valor("llm_api", "local"))
    elif "generativelanguage.googleapis" in _valor("llm_api") and not (
            k.startswith("AQ.") or k.startswith("AIza")):
        fallos.append("el cerebro es Google pero la clave no parece de Google (%s). "
                      "Se estan cruzando las dos claves otra vez" % _pinta_de_clave(k))
    if _valor("language") != "en" and _valor("stt_service") == "Moonshine":
        fallos.append("hablais en '%s' pero el oido es Moonshine, que SOLO entiende "
                      "ingles. Tiene que ser Whisper" % _valor("language"))

    if _valor("language") not in ("", "en") and _valor("stt_language") == "default":
        avisos.append("'stt_language' esta en 'default', o sea que Whisper adivina "
                      "el idioma en cada frase. Poniendolo en '%s' te entiende "
                      "mejor y mas rapido" % _valor("language"))
    if _valor("summary_llm_enabled") == "True" and "openrouter" in _sin_tildes(_valor("summary_llm_api")):
        avisos.append("el resumidor sigue apuntando a OpenRouter, que tiene la "
                      "cuota diaria agotada")
    cache = os.path.join(CASA, ".cache", "huggingface")
    if _valor("stt_service") == "Whisper" and not os.path.isdir(cache):
        avisos.append("Whisper todavia no se ha descargado. La PRIMERA frase que "
                      "digas en el juego se va a tirar un rato bajando unos 150 MB. "
                      "Es normal, no esta colgado")

    if fallos:
        for f in fallos:
            l.append("  FALLO GORDO: " + f)
    if avisos:
        for x in avisos:
            l.append("  Se puede mejorar: " + x)
    if not fallos and not avisos:
        l.append("  Todo correcto. Listo para jugar.")

    l.append("")
    l.append("Cuentaselo a Angel con tus palabras, sin leerle la lista tal cual. "
             "Si hay algun FALLO GORDO, dile primero eso y ofrecete a arreglarlo.")
    return "\n".join(l)


# ============================================== 2. QUE HA FALLADO (LEER EL LOG)
def _clasificar_fallo(texto):
    """El nudo de todo esto.

    Los tres fallos tipicos de Mantella se notan igual jugando (el PC hace un
    sonido de tos y el NPC se queda callado) y se arreglan de tres maneras
    completamente distintas. Distinguirlos es lo que costo dos tardes.
    """
    t = texto.lower()
    encontrados = []

    if "free-models-per-day" in t:
        encontrados.append((
            "CUOTA DIARIA AGOTADA",
            "Se han acabado las peticiones gratis del dia de esa cuenta. NO es "
            "culpa del modelo: cambiar de modelo no lo arregla, ni sacar una "
            "clave nueva, porque el limite es de la CUENTA. O se espera al "
            "reset del dia siguiente, o se mete saldo, o se cambia de "
            "proveedor. Esto es justo lo que paso con OpenRouter y por lo que "
            "se paso a Google."))
    if re.search(r"429", t) and re.search(r"overload|rate-limited upstream|temporarily rate", t):
        encontrados.append((
            "EL MODELO ESTA SATURADO",
            "Ese modelo concreto esta petado de gente ahora mismo. Esto SI se "
            "arregla cambiando de modelo, o esperando un rato: es inestable y "
            "va y viene en cuestion de minutos. Un 429 de estos no significa "
            "que el montaje este mal."))
    if "unrecognized character" in t or "discarding text" in t:
        encontrados.append((
            "EL MODELO PIENSA EN VOZ ALTA",
            "El modelo, en vez de soltar el diaogo del personaje, esta "
            "escribiendo su razonamiento ('we need to respond as...'). Mantella "
            "no reconoce ahi a ningun personaje y TIRA la respuesta entera. Se "
            "arregla cambiando a un modelo que no razone. Los de tipo "
            "'reasoning' o 'thinking' no valen para esto."))
    if re.search(r"api key not valid|invalid api key|please pass a valid api key|401", t):
        encontrados.append((
            "LA CLAVE NO VALE",
            "El servicio de IA rechaza la clave de GPT_SECRET_KEY.txt. O esta "
            "caducada, o es la del otro proveedor. Recuerda que Mantella lleva "
            "la de Google y Sobri la suya aparte."))
    if re.search(r"404", t) and "model" in t:
        encontrados.append((
            "ESE MODELO NO EXISTE EN ESE SERVICIO",
            "El nombre del modelo no le suena al servicio. Los nombres hay que "
            "sacarlos de la lista real del servicio, no escribirlos de memoria."))
    if "failed to open address library" in t:
        encontrados.append((
            "LOS PLUGINS NO CUADRAN CON LA VERSION DEL JUEGO",
            "Esto no es un archivo que falte: es que la version de Skyrim "
            "instalada no es para la que estan compilados los plugins de "
            "Mantella. Es lo que obligo a bajar el juego a la 1.6.1170."))
    if "piper only supports english" in t:
        encontrados.append((
            "AVISO DE PIPER (esto NO es un fallo)",
            "Mantella avisa de que Piper es de ingles, pero SIGUE ADELANTE y "
            "habla espanol igual, con acento ingles. Esta comprobado. No des "
            "por rota la instalacion por leer este aviso: mira si despues hay "
            "lineas de 'Synthesizing voiceline', que es la prueba de que ha "
            "hablado."))
    return encontrados


def mantella_revisar_fallos(lineas=400):
    """Lee el log de Mantella y dice QUE ha fallado y COMO se arregla.

    Sin permiso: solo lee.
    """
    if not os.path.isfile(LOG):
        return ("No hay log de Mantella en %s, asi que o no se ha arrancado "
                "nunca o esta en otro sitio." % LOG)

    try:
        n = max(50, min(int(lineas or 400), 2000))
    except Exception:
        n = 400

    try:
        with open(LOG, "rb") as f:
            crudo = f.read()
    except Exception as e:
        return "No he podido leer el log: %s" % e
    # El log lo escribe una consola de Windows, asi que no siempre es utf-8:
    # si se fuerza, las enes y las tildes salen como interrogantes y luego no
    # se entiende lo que dijo el NPC.
    texto = None
    for cod in ("utf-8", "cp1252", "cp850"):
        try:
            texto = crudo.decode(cod)
            break
        except Exception:
            continue
    if texto is None:
        texto = crudo.decode("utf-8", "replace")
    todas = texto.splitlines()
    cola = todas[-n:]
    trozo = "\n".join(cola)

    edad = ""
    try:
        cuando = datetime.datetime.fromtimestamp(os.path.getmtime(LOG))
        horas = (datetime.datetime.now() - cuando).total_seconds() / 3600.0
        if horas < 1:
            edad = "hace %d minutos" % int(horas * 60)
        elif horas < 48:
            edad = "hace %d horas" % int(horas)
        else:
            edad = "el %s" % cuando.strftime("%d/%m a las %H:%M")
    except Exception:
        pass

    l = ["LO QUE DICE EL LOG DE MANTELLA (ultimas %d lineas de %d, la ultima %s)"
         % (len(cola), len(todas), edad), ""]

    graves = [x for x in cola if re.search(r"\b(ERROR|CRITICAL)\b", x)]
    problemas = _clasificar_fallo(trozo)

    if problemas:
        l.append("HE RECONOCIDO ESTO:")
        for titulo, explicacion in problemas:
            l.append("")
            l.append("  * " + titulo)
            l.append("    " + explicacion)
    elif graves:
        l.append("Hay errores que no se de que son. Los ultimos:")
        for x in graves[-6:]:
            l.append("  " + x.strip()[:300])
    else:
        l.append("Ni un ERROR ni un CRITICAL. Por el log, esto va bien.")

    hablado = [x for x in cola if "synthesizing voiceline" in x.lower()]
    oido = [x for x in cola if "player said" in x.lower()]
    l.append("")
    l.append("SENALES DE VIDA en ese tramo: ha hablado %d veces y te ha "
             "entendido %d." % (len(hablado), len(oido)))
    if hablado:
        l.append("  Lo ultimo que dijo un NPC: " + hablado[-1].strip()[-160:])
    if oido:
        l.append("  Lo ultimo que te entendio: " + oido[-1].strip()[-160:])

    l.append("")
    l.append("Resumeselo a Angel en dos frases: que pasa y que hay que hacer. "
             "Si el fallo es del modelo, ofrecete a buscarle uno mejor tu mismo.")
    return "\n".join(l)


def mantella_quitar_bom():
    """Quita el BOM del config.ini de Mantella, que lo deja inservible.

    Ver tiene_bom() para el porque. Hace copia de seguridad antes y no toca
    nada mas del fichero: solo se le quitan los tres primeros bytes.

    Despues hay que REINICIAR Mantella, porque el config solo se lee al
    arrancar: mientras siga en marcha seguira creyendose que juega a SkyrimVR.
    """
    if not os.path.isfile(CONFIG):
        return "No encuentro el config.ini de Mantella en %s." % CONFIG
    if not tiene_bom():
        return ("El config.ini NO tiene BOM, asi que por ahi esta bien. Si "
                "Mantella sigue diciendo que juega a SkyrimVR o pidiendo una "
                "clave de OpenRouter, es otra cosa.")
    try:
        with open(CONFIG, "rb") as f:
            crudo = f.read()
        sello = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        copia = CONFIG + ".bak-berna-" + sello
        shutil.copy2(CONFIG, copia)
        with open(CONFIG, "wb") as f:
            f.write(crudo[3:])
    except Exception as e:
        return "No he podido arreglarlo: %s" % e
    return ("Arreglado: le he quitado el BOM al config.ini (copia en %s).\n\n"
            "Ahora hay que REINICIAR Mantella para que lo lea, porque el "
            "config solo se mira al arrancar. Lo mas comodo es cerrar la IA de "
            "Skyrim y volver a arrancarla." % os.path.basename(copia))


# ================================================= 3. AUDITORIA DE LOS AJUSTES
def mantella_revisar_ajustes():
    """Repasa el config.ini entero buscando cosas mejorables. Solo mira."""
    a = _ajustes()
    if not a:
        return "No encuentro el config.ini de Mantella en %s." % CONFIG

    def v(k, d=""):
        return _valor(k, d)

    hallazgos = []   # (gravedad, que pasa, que hacer)

    # Este va el primero a proposito: si hay BOM, Mantella no esta leyendo
    # NADA de este fichero y el resto de hallazgos, aunque sean ciertos sobre
    # el papel, no explican lo que esta pasando en el juego.
    if tiene_bom():
        hallazgos.append(("GORDO", "el config.ini empieza por BOM y Mantella "
                          "lo esta ignorando ENTERO (se cree que juega a "
                          "SkyrimVR y pide clave de OpenRouter)",
                          "usar mantella_quitar_bom() y reiniciar Mantella"))

    if v("game") == "SkyrimVR":
        hallazgos.append(("GORDO", "el juego esta puesto como SkyrimVR",
                          "cambiar 'game' a Skyrim"))
    carp = v("skyrim_mod_folder")
    if carp and not os.path.isdir(carp):
        hallazgos.append(("GORDO", "la carpeta del mod (%s) no existe" % carp,
                          "apuntar 'skyrim_mod_folder' a %s" % _carpeta_mod()))
    if v("language") != "en" and v("stt_service") == "Moonshine":
        hallazgos.append(("GORDO", "juegas en %s pero el oido es Moonshine, que solo "
                          "sabe ingles" % v("language"),
                          "cambiar 'stt_service' a Whisper"))

    if v("language") not in ("", "en") and v("stt_language") == "default":
        hallazgos.append(("MEJORA", "Whisper esta adivinando el idioma en cada frase",
                          "poner 'stt_language' en '%s': te entiende mejor y tarda "
                          "menos, porque se ahorra el detector" % v("language")))
    if v("stt_service") == "Whisper" and v("whisper_model_size") == "tiny":
        hallazgos.append(("MEJORA", "Whisper esta en 'tiny', que con el espanol se "
                          "come palabras", "subirlo a 'base' o 'small'"))
    if v("narration_handling") != "Cut narrations":
        hallazgos.append(("MEJORA", "las acotaciones (*se tambalea*) no se estan "
                          "cortando, y Piper las lee en voz alta",
                          "poner 'narration_handling' en 'Cut narrations'"))
    if v("conversation_summary_enabled") != "True":
        hallazgos.append(("MEJORA", "los NPC no guardan memoria de charlas anteriores",
                          "poner 'conversation_summary_enabled' en True"))
    if not v("player_character_description"):
        hallazgos.append(("MEJORA", "los NPC no saben nada de tu personaje",
                          "escribir dos lineas en 'player_character_description' "
                          "(quien eres, tu raza, a que te dedicas): es lo que mas "
                          "cambia las conversaciones por lo poco que cuesta"))

    for nombre, etiqueta, interruptor in (
            ("summary_llm_api", "el resumidor de conversaciones", "summary_llm_enabled"),
            ("vision_llm_api", "el que mira las capturas", "custom_vision_model"),
            ("function_llm_api", "el que decide las acciones", "custom_function_model")):
        if "openrouter" in _sin_tildes(v(nombre)):
            if v(interruptor) == "True":
                hallazgos.append(("GORDO", "%s esta ENCENDIDO y apunta a OpenRouter, "
                                  "que tiene la cuota agotada" % etiqueta,
                                  "apuntarlo al mismo sitio que el cerebro principal"))
            else:
                hallazgos.append(("APUNTADO", "%s apunta a OpenRouter, pero esta "
                                  "apagado, asi que hoy da igual" % etiqueta,
                                  "si algun dia se enciende, cambiarlo antes"))

    if v("vision_enabled") != "True":
        hallazgos.append(("OPCIONAL", "los NPC no ven lo que hay en pantalla",
                          "encender 'vision_enabled' hace que comenten el sitio, el "
                          "dragon o lo que lleves puesto. Gasta mas cuota y tarda "
                          "algo mas en contestar"))
    if v("advanced_actions_enabled") != "True":
        hallazgos.append(("OPCIONAL", "los NPC solo hablan, no hacen cosas",
                          "'advanced_actions_enabled' les deja seguirte, ir a un "
                          "sitio o pelearse. Necesita un modelo que maneje bien las "
                          "herramientas y da mas guerra"))
    if v("ptt_enabled") != "True":
        hallazgos.append(("OPCIONAL", "el microfono esta siempre escuchando",
                          "con 'ptt_enabled' hablarias solo al pulsar la tecla %s. "
                          "Va mejor si tienes ruido alrededor" % v("ptt_hotkey", "V")))

    orden = {"GORDO": 0, "MEJORA": 1, "OPCIONAL": 2, "APUNTADO": 3}
    hallazgos.sort(key=lambda h: orden.get(h[0], 9))

    l = ["REPASO DE LOS AJUSTES DE MANTELLA", "",
         "Ahora mismo: %s en %s, idioma %s, oido %s, voz %s."
         % (v("model"), v("llm_api"), v("language"), v("stt_service"), v("tts_service")),
         ""]
    if not hallazgos:
        l.append("No he visto nada que mejorar. Esta bien puesto.")
    for g, que, como in hallazgos:
        l.append("[%s] %s" % (g, que))
        l.append("        -> %s" % como)
    l.append("")
    l.append("Cuentale a Angel lo GORDO primero, luego una o dos mejoras, y no le "
             "sueltes la lista entera de golpe. Lo que el diga que si, se lo "
             "cambias tu con mantella_cambiar_ajuste.")
    return "\n".join(l)


# ================================================== 4. HABLAR CON EL SERVICIO
def _url_base():
    u = _valor("llm_api", "").strip()
    if not u or "://" not in u:
        return ""
    return u.rstrip("/") + "/"


def _cabeceras():
    return {"Authorization": "Bearer " + _clave(),
            "Content-Type": "application/json"}


def mantella_modelos_disponibles(filtro=""):
    """Le pregunta al servicio de IA que modelos tiene la cuenta de Angel.

    Es importante hacerlo asi y no de memoria: por el endpoint de OpenAI de
    Google, 'gemini-2.5-flash' da 404 aunque el modelo exista.
    """
    base = _url_base()
    if not base:
        return ("El 'llm_api' del config.ini no es una direccion web (pone '%s'), "
                "asi que no puedo preguntarle nada." % _valor("llm_api"))
    if not _clave():
        return "No hay clave en %s, sin eso no me contestan." % _archivo_clave()
    try:
        import requests
        r = requests.get(base + "models", headers=_cabeceras(), timeout=ESPERA_RED)
    except Exception as e:
        return "No he podido conectar con %s: %s" % (base, e)
    if r.status_code != 200:
        return ("El servicio ha contestado %s: %s" % (r.status_code, r.text[:300]))
    try:
        datos = r.json().get("data") or []
    except Exception:
        return "Me han contestado algo que no entiendo: %s" % r.text[:300]

    ids = sorted({(d.get("id") or "").split("/")[-1] if "models/" in (d.get("id") or "")
                  else (d.get("id") or "") for d in datos})
    ids = [i for i in ids if i]
    f = _sin_tildes(filtro)
    if f:
        ids = [i for i in ids if f in _sin_tildes(i)]
    if not ids:
        return "No hay ningun modelo que encaje con '%s'." % filtro
    return ("Modelos que tiene disponibles la cuenta (%d)%s:\n  %s\n\n"
            "El que esta puesto ahora es '%s'. Si Angel quiere cambiarlo, "
            "pruebalo antes con mantella_probar_modelo: hay modelos que "
            "contestan bien a una pregunta suelta y luego, con el prompt de "
            "Mantella, se ponen a razonar en voz alta y no sirven."
            % (len(ids), (" que llevan '%s'" % filtro) if filtro else "",
               "\n  ".join(ids), _valor("model")))


# ------------------------- el prompt de mentira, que imita al real de Mantella
_SISTEMA_PRUEBA = (
    "# Overview\nYou are Alvor in Skyrim. You are talking with Angel (the player).\n\n"
    "# Background\nAlvor is the blacksmith of Riverwood, a practical and kind Nord.\n\n"
    "# Current Scene\nYou are now in Riverwood. The time is 14 in the afternoon.\n\n"
    "# Rules\nBegin your response with an indication of who you are speaking as, "
    "for example: 'Alvor: Good evening.'.\nOutput ONLY spoken dialogue. No narration, "
    "no descriptions, no thoughts.\nDo not use quotation marks.\nStay in character.\n\n"
    "Respond as Alvor now in Spanish.")
_USUARIO_PRUEBA = "Buenas, Alvor. Necesito que me forjes una espada de acero."

_HUELLAS_DE_RAZONAMIENTO = (
    "we need to", "we should", "the user says", "the player says", "okay,", "ok,",
    "let me ", "i should", "as an ai", "<think", "</think", "first,", "the user is",
    "el usuario dice", "hay que responder", "debo responder", "analicemos",
    "reasoning:", "thought:")

_PALABRAS_ESPANOLAS = (" que ", " de ", " el ", " la ", " los ", " para ", " con ",
                       " una ", " por ", " te ", " se ", " mi ", "\u00bf", "\u00e1",
                       "\u00e9", "\u00ed", "\u00f3", "\u00fa", "\u00f1")
_PALABRAS_INGLESAS = (" the ", " you ", " and ", " your ", " have ", " will ",
                      " what ", " need ", " good ")


def _juzgar_respuesta(t):
    """Devuelve (nota sobre 10, lista de pegas). La nota manda al elegir modelo."""
    pegas = []
    nota = 10.0
    s = " " + t.lower().replace("\n", " ") + " "

    if not t.strip():
        return 0.0, ["no ha contestado nada"]

    fugas = [h for h in _HUELLAS_DE_RAZONAMIENTO if h in s]
    if fugas:
        nota -= 6
        pegas.append("PIENSA EN VOZ ALTA (se le ve '%s'). Mantella tirara la "
                     "respuesta entera" % fugas[0].strip())

    esp = sum(1 for p in _PALABRAS_ESPANOLAS if p in s)
    ing = sum(1 for p in _PALABRAS_INGLESAS if p in s)
    if ing > esp:
        nota -= 4
        pegas.append("contesta en ingles aunque se le pide espanol")
    elif esp == 0:
        nota -= 2
        pegas.append("no se yo si eso es espanol")

    if re.search(r"\*[^*]{3,}\*|\([^)]{6,}\)|\[[^\]]{6,}\]", t):
        nota -= 1.5
        pegas.append("mete acotaciones (*se rie*), que la voz leeria en alto")

    if not re.match(r"^\s*[A-Z\u00c1\u00c9\u00cd\u00d3\u00da][\w\u00e0-\u00ff' ]{1,24}\s*:", t):
        nota -= 2
        pegas.append("no empieza con 'Alvor:', que es como Mantella sabe quien habla")

    if '"' in t or "\u201c" in t:
        nota -= 0.5
        pegas.append("usa comillas, y se le pide que no")

    if len(t.strip()) < 12:
        nota -= 2
        pegas.append("suelta cuatro palabras y ya")

    return max(0.0, nota), pegas


def _probar_uno(modelo, base, segundos=ESPERA_RED):
    """Una llamada EN STREAMING, que es como llama Mantella de verdad.

    Se mide el primer trozo aparte del total a proposito: lo que nota el
    jugador es cuanto tarda el NPC en EMPEZAR a hablar, no en terminar.
    """
    import requests
    cuerpo = {"model": modelo,
              "messages": [{"role": "system", "content": _SISTEMA_PRUEBA},
                           {"role": "user", "content": _USUARIO_PRUEBA}],
              "max_tokens": 250, "stream": True}
    t0 = time.time()
    primero = None
    piezas = []
    try:
        r = requests.post(base + "chat/completions", headers=_cabeceras(),
                          json=cuerpo, timeout=segundos, stream=True)
        if r.status_code != 200:
            return {"modelo": modelo, "ok": False,
                    "error": "HTTP %s: %s" % (r.status_code, r.text[:200])}
        for linea in r.iter_lines(decode_unicode=True):
            if time.time() - t0 > segundos:
                break
            if not linea or not linea.startswith("data:"):
                continue
            trozo = linea[5:].strip()
            if trozo == "[DONE]":
                break
            try:
                d = json.loads(trozo)
                c = (d.get("choices") or [{}])[0].get("delta", {}).get("content") or ""
            except Exception:
                continue
            if c:
                if primero is None:
                    primero = time.time() - t0
                piezas.append(c)
    except Exception as e:
        return {"modelo": modelo, "ok": False, "error": str(e)[:200]}

    texto = "".join(piezas).strip()
    nota, pegas = _juzgar_respuesta(texto)
    total = time.time() - t0
    # La velocidad tambien cuenta: por encima de 5 s el NPC parece tonto.
    if primero is None:
        nota = 0.0
        pegas = ["no ha soltado ni una palabra"]
        primero = total
    elif primero > 8:
        nota -= 3
        pegas.append("tarda %.0f segundos en empezar a hablar, es inaguantable" % primero)
    elif primero > 4:
        nota -= 1.5
        pegas.append("tarda %.1f s en arrancar, se nota" % primero)

    return {"modelo": modelo, "ok": True, "primero": primero, "total": total,
            "texto": texto, "nota": max(0.0, nota), "pegas": pegas}


def mantella_probar_modelo(modelo=""):
    """Prueba un modelo CON EL PROMPT DE MANTELLA y dice si sirve.

    Probar un modelo con un 'hola' no vale: con pocas instrucciones se porta
    bien y con el prompt real se pone a razonar. Por eso aqui se le manda un
    system igualito al de Mantella y se busca en la respuesta si se le escapa
    el razonamiento.
    """
    base = _url_base()
    if not base:
        return "El 'llm_api' del config.ini no es una direccion web."
    if not _clave():
        return "No hay clave en %s." % _archivo_clave()
    m = (modelo or "").strip() or _valor("model")
    if not m:
        return "No se que modelo probar y en el config.ini tampoco hay ninguno."

    r = _probar_uno(m, base)
    if not r["ok"]:
        return ("El modelo '%s' NO responde: %s\n\n%s" % (m, r["error"],
                "Si pone 429 mira si es cuota diaria o saturacion; si pone 404, "
                "ese nombre no existe en este servicio y hay que sacarlo de "
                "mantella_modelos_disponibles."))

    l = ["PRUEBA DEL MODELO '%s' con el prompt de verdad de Mantella" % m, "",
         "Tarda %.1f s en empezar a hablar y %.1f s en total." % (r["primero"], r["total"]),
         "", "Esto es lo que ha contestado:", "  " + (r["texto"][:500] or "(nada)"), ""]
    if r["pegas"]:
        l.append("PEGAS:")
        for p in r["pegas"]:
            l.append("  - " + p)
    else:
        l.append("Sin pegas: espanol, en personaje, formato correcto y rapido.")
    l.append("")
    l.append("Nota: %.1f sobre 10." % r["nota"])
    if r["nota"] >= 7:
        l.append("Sirve. Si Angel quiere, se lo pongo con mantella_cambiar_ajuste.")
    else:
        l.append("Yo no lo pondria. Busca otro con mantella_elegir_mejor_modelo.")
    return "\n".join(l)


# ========================================== 5. BUSCAR EL MEJOR MODELO Y PONERLO
_CANDIDATOS_PREFERIDOS = (
    "flash-lite", "flash", "mini", "small", "lite", "haiku", "instant")
_CANDIDATOS_VETADOS = (
    "thinking", "reasoning", "-think", "embedding", "imagen", "image", "vision",
    "tts", "audio", "veo", "aqa", "learnlm", "gemma-2", "-vision", "live",
    "native-audio", "exp-", "preview-tts")


def _candidatos(base, cuantos):
    """Saca de la lista real del servicio los modelos que pinta que valen."""
    import requests
    r = requests.get(base + "models", headers=_cabeceras(), timeout=ESPERA_RED)
    if r.status_code != 200:
        return [], "el servicio ha contestado %s" % r.status_code
    ids = []
    for d in (r.json().get("data") or []):
        i = (d.get("id") or "")
        i = i.split("models/")[-1]
        if not i:
            continue
        s = i.lower()
        if any(v in s for v in _CANDIDATOS_VETADOS):
            continue
        ids.append(i)

    def peso(i):
        s = i.lower()
        for n, p in enumerate(_CANDIDATOS_PREFERIDOS):
            if p in s:
                return n
        return len(_CANDIDATOS_PREFERIDOS)

    ids = sorted(set(ids), key=lambda i: (peso(i), i))
    return ids[:cuantos], None


def mantella_elegir_mejor_modelo(cuantos=5, aplicar=False, permiso=None):
    """Prueba varios modelos con el prompt de Mantella y se queda con el mejor.

    Es la herramienta que mas mejora Mantella de una sentada, porque el eslabon
    que se ha roto SIEMPRE ha sido el modelo, nunca el mod.
    """
    base = _url_base()
    if not base:
        return "El 'llm_api' del config.ini no es una direccion web."
    if not _clave():
        return "No hay clave en %s." % _archivo_clave()
    try:
        cuantos = max(2, min(int(cuantos or 5), 8))
    except Exception:
        cuantos = 5

    try:
        lista, error = _candidatos(base, cuantos)
    except Exception as e:
        return "No he podido pedir la lista de modelos: %s" % e
    if error:
        return "No he podido pedir la lista de modelos: %s" % error
    if not lista:
        return "El servicio no me ha dado ningun modelo que sirva para conversar."

    actual = _valor("model")
    if actual and actual not in lista:
        lista.insert(0, actual)

    resultados = []
    limite = time.time() + 150          # tope duro: esto cuelga la ventana
    for m in lista:
        if time.time() > limite:
            break
        resultados.append(_probar_uno(m, base, segundos=20))

    buenos = [r for r in resultados if r.get("ok")]
    buenos.sort(key=lambda r: (-r["nota"], r["primero"]))

    l = ["HE PROBADO %d MODELOS con el prompt de verdad de Mantella:" % len(resultados), ""]
    for r in resultados:
        if not r.get("ok"):
            escueto = " ".join(str(r["error"]).split())
            l.append("  %-34s NO responde (%s)" % (r["modelo"], escueto[:90]))
            continue
        marca = "  <-- el que hay puesto" if r["modelo"] == actual else ""
        l.append("  %-34s nota %.1f | arranca en %.1f s%s"
                 % (r["modelo"], r["nota"], r["primero"], marca))
        if r["pegas"]:
            l.append("       pega: " + r["pegas"][0])

    if not buenos:
        return "\n".join(l + ["", "Ninguno ha respondido bien. Si todos dan 429 es "
                              "la cuota, no los modelos: hay que esperar."])

    mejor = buenos[0]
    l.append("")
    l.append("EL MEJOR ES '%s' (nota %.1f, arranca en %.1f s)."
             % (mejor["modelo"], mejor["nota"], mejor["primero"]))
    l.append('Ha dicho: "%s"' % mejor["texto"][:220].replace("\n", " "))

    if mejor["modelo"] == actual:
        l.append("")
        l.append("O sea que el que ya tiene puesto es el mejor. No hay nada que cambiar.")
        return "\n".join(l)

    if not aplicar:
        l.append("")
        l.append("No he cambiado nada. Preguntale a Angel si se lo pongo, y si dice "
                 "que si, vuelve a llamarme con aplicar=true.")
        return "\n".join(l)

    if mejor["nota"] < 6:
        l.append("")
        l.append("No se lo pongo: ni el mejor llega a la nota minima. Mejor "
                 "esperar un rato y volver a probar.")
        return "\n".join(l)

    aviso = ("Sobri va a cambiar el cerebro de los NPC de Skyrim.\n\n"
             "Ahora:   %s\n"
             "Nuevo:   %s\n\n"
             "Lo ha probado y arranca en %.1f segundos, habla espanol y se "
             "mantiene en personaje. Se guarda copia del config.ini antes de "
             "tocarlo.\n\nLe dejas?" % (actual or "(ninguno)", mejor["modelo"],
                                        mejor["primero"]))
    if permiso is None or not permiso(aviso):
        _apuntar("SIN PERMISO", "mantella model=" + mejor["modelo"], "Angel ha dicho que no")
        return "\n".join(l + ["", "Angel no me ha dado permiso, lo he dejado como estaba."])

    ok, msg = _escribir_ajuste("model", mejor["modelo"])
    _apuntar("MANTELLA", "model = " + mejor["modelo"], "ok" if ok else msg)
    if not ok:
        return "\n".join(l + ["", "No he podido cambiarlo: " + msg])
    l.append("")
    l.append("CAMBIADO: " + msg)
    l.append("Si Mantella esta encendido, hay que reiniciarlo para que lo coja. "
             "Ofrecete a hacerlo tu con mantella_parar y mantella_arrancar.")
    return "\n".join(l)


# ============================================= 6. CAMBIAR UN AJUSTE A MANO
def mantella_cambiar_ajuste(ajuste, valor, permiso=None):
    """Cambia un ajuste del config.ini, con copia de seguridad y con permiso."""
    ajuste = _sin_tildes(ajuste).strip().replace(" ", "_")
    valor = str(valor).strip()

    if ajuste not in AJUSTABLES:
        parecidos = [k for k in AJUSTABLES if ajuste and ajuste in k]
        return ("'%s' no esta entre los ajustes que puedo tocar. Los que si: %s.%s"
                % (ajuste, ", ".join(sorted(AJUSTABLES)),
                   ("\nA lo mejor te referias a: %s" % ", ".join(parecidos)) if parecidos else ""))

    comprobar, para_que = AJUSTABLES[ajuste]
    pega = comprobar(valor)
    if pega:
        return "Ese valor no vale para '%s': %s." % (ajuste, pega)

    actual = _valor(ajuste, "(vacio)")
    if actual == valor:
        return "'%s' ya esta en '%s'. No hay nada que hacer." % (ajuste, valor)

    aviso = ("Sobri va a cambiar un ajuste de Mantella (la IA de los NPC).\n\n"
             "Ajuste:  %s\n(%s)\n\n"
             "Ahora:   %s\nNuevo:   %s\n\n"
             "Se guarda copia del config.ini antes. Si Mantella esta encendido "
             "habra que reiniciarlo.\n\nLe dejas?" % (ajuste, para_que, actual, valor))
    if permiso is None or not permiso(aviso):
        _apuntar("SIN PERMISO", "mantella %s=%s" % (ajuste, valor), "Angel ha dicho que no")
        return "Angel no me ha dado permiso, no he tocado nada."

    ok, msg = _escribir_ajuste(ajuste, valor)
    _apuntar("MANTELLA", "%s = %s" % (ajuste, valor), "ok" if ok else msg)
    if not ok:
        return "No he podido cambiarlo: " + msg
    extra = ""
    if _procesos()["mantella"]:
        extra = (" Mantella esta encendido ahora mismo, asi que hay que reiniciarlo "
                 "para que lo note; puedo hacerlo yo.")
    return "Hecho. " + msg + "." + extra


# ================================================== 7. LO QUE HABLO CON LOS NPC
def mantella_conversaciones(personaje=""):
    """Enseña con quien ha hablado Angel en el juego y que recuerdan de el."""
    raiz = os.path.join(DATOS, _valor("game", "Skyrim"), "conversations")
    if not os.path.isdir(raiz):
        return ("Todavia no hay ninguna conversacion guardada. Se guardan cuando "
                "hablas con un NPC y la charla termina.")

    partidas = sorted([d for d in os.listdir(raiz)
                       if os.path.isdir(os.path.join(raiz, d))])
    if not partidas:
        return "No hay ninguna partida con conversaciones guardadas."

    f = _sin_tildes(personaje)
    l = []
    for partida in partidas:
        pr = os.path.join(raiz, partida)
        gente = sorted([d for d in os.listdir(pr) if os.path.isdir(os.path.join(pr, d))])
        if not f:
            l.append("Partida '%s': ha hablado con %d personajes." % (partida, len(gente)))
            l.append("  " + ", ".join(g.split(" - ")[0] for g in gente))
            continue
        for g in gente:
            if f not in _sin_tildes(g):
                continue
            carpeta = os.path.join(pr, g)
            for arch in sorted(os.listdir(carpeta)):
                if not arch.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(carpeta, arch), "r", encoding="utf-8") as fh:
                        d = json.load(fh)
                except Exception as e:
                    l.append("  (no he podido leer %s: %s)" % (arch, e))
                    continue
                # El fichero es una lista de charlas, y cada charla una lista de
                # mensajes {role, content}. Se aplana y se pone como dialogo,
                # que es como se entiende: 'assistant' es el NPC, 'user' Angel.
                quien = g.split(" - ")[0]
                mensajes = []

                def _aplanar(x):
                    if isinstance(x, dict):
                        mensajes.append(x)
                    elif isinstance(x, list):
                        for y in x:
                            _aplanar(y)

                _aplanar(d)
                if not mensajes:
                    continue
                l.append("LO QUE HABLO CON %s (%d intervenciones, las ultimas):"
                         % (quien.upper(), len(mensajes)))
                for m in mensajes[-12:]:
                    papel = m.get("role")
                    texto = str(m.get("content") or "").strip()
                    if not texto:
                        continue
                    if papel == "user":
                        nombre = "Angel"
                    elif papel == "assistant":
                        nombre = quien
                    else:
                        nombre = papel or "?"
                    l.append("  %s: %s" % (nombre, texto[:300]))
                l.append("")
    if not l:
        return "No he encontrado a ningun personaje que se llame '%s'." % personaje
    l.append("")
    l.append("Esto son recuerdos del juego, no cosas de la vida real de Angel. "
             "Comentaselo con gracia, que es su partida.")
    return "\n".join(l)


# =============================================== 8. ARRANCAR, PARAR Y JUGAR
def mantella_arrancar(permiso=None):
    """Enciende Mantella.exe, que es lo que hace hablar a los NPC."""
    exe = _exe()
    if not os.path.isfile(exe):
        return "No encuentro Mantella.exe en %s." % exe
    if _procesos()["mantella"]:
        return ("Mantella ya esta encendido. Su pagina interna %s. Si quieres que "
                "coja cambios nuevos del config, hay que pararlo y volverlo a "
                "arrancar." % ("responde" if _servidor_vivo() else "no responde"))

    a = _ajustes()
    pegas = []
    if a.get("game", ("",))[0] == "SkyrimVR":
        pegas.append("'game' pone SkyrimVR: no va a arrancar bien")
    if not _clave():
        pegas.append("no hay clave, los NPC no van a contestar")

    aviso = ("Sobri va a arrancar MANTELLA, la IA que hace hablar a los NPC de "
             "Skyrim.\n\n%s\n\nCerebro: %s\nIdioma: %s\n\n%sLe dejas?"
             % (exe, _valor("model", "?"), _valor("language", "?"),
                ("OJO: " + "; ".join(pegas) + ".\n\n") if pegas else ""))
    if permiso is None or not permiso(aviso):
        _apuntar("SIN PERMISO", "arrancar Mantella", "Angel ha dicho que no")
        return "Angel no me ha dado permiso, no he arrancado nada."

    try:
        subprocess.Popen([exe], cwd=os.path.dirname(exe),
                         creationflags=SIN_VENTANA)
    except Exception as e:
        _apuntar("MANTELLA", "arrancar", "fallo: %s" % e)
        return "No he podido arrancarlo: %s" % e

    # Se espera a que levante su servidor, en trozos, para no colgar la ventana
    # mas de la cuenta ni mentir diciendo que ya esta.
    fin = time.time() + ESPERA_ARRANQUE
    while time.time() < fin:
        time.sleep(1.5)
        if _servidor_vivo():
            _apuntar("MANTELLA", "arrancar", "arrancado")
            return ("Mantella arrancado y respondiendo. Cuando entres al juego y "
                    "hables con alguien, ya contesta. Si el PC hace un ruido de "
                    "tos es que algo ha fallado; dimelo y miro el log.")
    if _procesos()["mantella"]:
        return ("Mantella esta arrancando, pero todavia no responde su pagina. "
                "Dale unos segundos. Si tarda mucho, puedo mirarle el log.")
    _apuntar("MANTELLA", "arrancar", "se ha cerrado solo")
    return ("Lo he arrancado y se ha cerrado solo. Eso suele ser el config.ini "
            "mal. Dejame mirar el log y te digo que pasa.")


def mantella_parar(permiso=None):
    """Apaga Mantella.exe. Hace falta para que coja cambios del config."""
    if not _procesos()["mantella"]:
        return "Mantella no esta encendido, no hay nada que apagar."
    aviso = ("Sobri va a CERRAR Mantella.\n\nSi Angel esta jugando, los NPC dejan "
             "de contestar en cuanto se cierre.\n\nLe dejas?")
    if permiso is None or not permiso(aviso):
        return "Angel no me ha dado permiso, lo dejo encendido."
    try:
        import psutil
        muertos = 0
        for p in psutil.process_iter(["name"]):
            if (p.info.get("name") or "").lower() == "mantella.exe":
                p.terminate()
                muertos += 1
        _apuntar("MANTELLA", "parar", "%d procesos" % muertos)
        return "Mantella cerrado. Cuando quieras lo vuelvo a arrancar."
    except Exception as e:
        return "No he podido cerrarlo: %s" % e


def _escucha_puerto(puerto):
    """True si hay algo escuchando en ese puerto de esta maquina."""
    import socket
    try:
        with socket.create_connection(("127.0.0.1", int(puerto)), 0.6):
            return True
    except Exception:
        return False


def _microfono_abierto():
    """Cuando Windows dejo a Mantella abrir el microfono por ultima vez.

    Es el juez de paz del diagnostico: si esta fecha NO se mueve mientras
    Angel habla, el problema no esta en el audio, esta en que Mantella ni
    siquiera intenta escuchar. Y eso, en la practica, siempre ha sido la
    entrada por texto del MCM. Vale la pena porque no depende de creerse el
    log: lo dice Windows.
    """
    try:
        import winreg
    except Exception:
        return ""
    ruta = (r"SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager"
            r"\ConsentStore\microphone\NonPackaged")
    mejor = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, ruta) as k:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(k, i)
                except OSError:
                    break
                i += 1
                if "mantella" not in sub.lower():
                    continue
                with winreg.OpenKey(k, sub) as sk:
                    for v in ("LastUsedTimeStop", "LastUsedTimeStart"):
                        try:
                            ft = winreg.QueryValueEx(sk, v)[0]
                        except Exception:
                            continue
                        if isinstance(ft, int) and ft > mejor:
                            mejor = ft
    except Exception:
        return ""
    if not mejor:
        return ""
    # FILETIME: cienmilesimas de microsegundo desde 1601. A segundos desde 1970.
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S",
                             time.localtime(mejor / 10000000.0 - 11644473600))
    except Exception:
        return ""


def mantella_no_me_oye():
    """Por que no te oye o no te da el turno, con UN solo siguiente paso.

    Esto NO es un volcado del log: es el orden de descarte que costo dos dias
    enteros (26 y 27 de agosto de 2026). El orden importa, y esta puesto de
    mas probable a menos. Sin permiso: solo mira, no cambia nada.
    """
    if not os.path.isfile(LOG):
        return ("No hay log de Mantella todavia, asi que no ha llegado ni a "
                "arrancar. Lo primero es arrancar Skyrim con IA.")

    try:
        with open(LOG, "rb") as f:
            crudo = f.read()
    except Exception as e:
        return "No he podido leer el log: %s" % e
    texto = None
    for cod in ("utf-8", "cp1252", "cp850"):
        try:
            texto = crudo.decode(cod)
            break
        except Exception:
            continue
    if texto is None:
        texto = crudo.decode("utf-8", "replace")
    cola = texto.splitlines()[-800:]

    def ultima(marca):
        for l in reversed(cola):
            if marca in l:
                m = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", l)
                return m.group(1) if m else "sin hora"
        return ""

    servicios = [(5001, "el modelo de lenguaje"), (8020, "la voz"),
                 (4999, "Mantella")]
    caidos = [n for p, n in servicios if not _escucha_puerto(p)]
    colgado = _escucha_puerto(4999) and not _servidor_vivo()

    hablo = ultima("Player said")
    turno = ultima("Listening")
    paso = ultima("Text passed to NPC")
    espera = ultima("Waiting for player to select an NPC")
    micro = _microfono_abierto()
    umbral = _valor("audio_threshold", "?")
    jugando = bool(_procesos()["skyrim"])

    datos = ["LO QUE VEO:",
             "  servicios caidos: %s" % (", ".join(caidos) if caidos else "ninguno"),
             "  el juego: %s" % ("abierto" if jugando else "cerrado"),
             "  te oyo por ultima vez: %s" % (hablo or "nunca en este log"),
             "  te dio el turno para hablar: %s" % (turno or "NUNCA"),
             "  Windows le abrio el microfono: %s" % (micro or "no consta"),
             "  umbral de voz: %s" % umbral]

    # ESTE ORDEN ES EL DIAGNOSTICO. No reordenar sin un motivo muy bueno.
    if colgado:
        paso_sig = ("Mantella esta colgado: tiene el puerto abierto pero no "
                    "contesta. Pasa cuando intenta usar un microfono que ya no "
                    "esta, por ejemplo si se desconectan los auriculares a "
                    "media partida.\n"
                    "SIGUIENTE PASO: pararlo y volverlo a arrancar. Ofrecete a "
                    "hacerlo tu, que son segundos.")
    elif caidos:
        paso_sig = ("Falta por levantar: %s. Sin eso no hay nada que "
                    "diagnosticar: si falta el modelo o la voz, el personaje "
                    "no puede contestar aunque te oiga perfectamente.\n"
                    "SIGUIENTE PASO: arrancar Skyrim con IA otra vez. Lo que ya "
                    "este en marcha no se duplica." % ", ".join(caidos))
    elif not jugando:
        paso_sig = ("Los servicios estan bien; lo que no esta es el juego.\n"
                    "SIGUIENTE PASO: abrir Skyrim.")
    elif not espera and not paso:
        paso_sig = ("Mantella no ha llegado a hablar con ningun personaje "
                    "todavia.\n"
                    "SIGUIENTE PASO: dentro del juego, mira a un personaje y "
                    "pulsa la tecla de hablar. Si al mirarlo no pasa nada, es "
                    "que Mantella no esta enganchado a la partida.")
    elif not turno:
        paso_sig = ("AQUI ESTA EL FALLO. Mantella escribe la voz del personaje "
                    "pero el juego no la lee, asi que para el juego el NPC "
                    "nunca termina de hablar y no te devuelve el turno. Por eso "
                    "no te pide que hables nunca.\n"
                    "SIGUIENTE PASO, y es el que lo arregla casi siempre: "
                    "GUARDA LA PARTIDA EN UNA RANURA NUEVA Y CARGA ESA PARTIDA. "
                    "Es lo que recomiendan los autores del mod cuando se han "
                    "cambiado ficheros, y el 27 de agosto lo arreglo al primer "
                    "intento.\n"
                    "Si con eso sigue igual, entonces si: en el juego, tecla "
                    "Escape, configuracion de mods, Mantella, y comprueba que "
                    "la ENTRADA POR TEXTO ESTA DESACTIVADA. Mientras esa opcion "
                    "este puesta, Mantella no abre el microfono nunca, y eso no "
                    "se puede cambiar desde fuera del juego.")
    elif not hablo:
        paso_sig = ("Te da el turno pero no te oye: el problema es el "
                    "microfono o el umbral, no el mod.\n"
                    "SIGUIENTE PASO: subir el microfono de Windows al maximo y, "
                    "si aun asi nada, bajar el umbral (ahora esta en %s). "
                    "Ofrecete a cambiarlo tu con mantella_cambiar_ajuste."
                    % umbral)
    else:
        paso_sig = ("El ciclo completo funciona: te da el turno, te oye y se lo "
                    "pasa al personaje. La ultima vez fue %s.\n"
                    "SIGUIENTE PASO: ninguno, esto esta bien. Si aun asi no "
                    "suena la voz del personaje, es cosa del altavoz de "
                    "Windows, no del mod." % hablo)

    return ("\n".join(datos) + "\n\n" + paso_sig +
            "\n\nNO menciones nunca los errores de out.lip ni de FaceFXWrapper "
            "si los ves: salen en cada frase, son normales en este montaje y "
            "solo afectan al movimiento de la boca.\n"
            "Dile a Angel SOLO el siguiente paso, en dos o tres frases y sin "
            "leerle la lista de datos. Si es algo que puedes hacer tu, "
            "ofrecetelo.")


def jugar_a_skyrim(con_mantella=True, permiso=None):
    """Le monta a Angel la partida entera: Steam, MO2 con SKSE y Mantella."""
    pasos = []
    if not os.path.isfile(LANZADOR) and not os.path.isfile(MO2):
        return ("No encuentro ni el lanzador del escritorio ni el Mod Organizer, "
                "asi que no se por donde arrancarle el juego.")

    aviso = ("Sobri va a arrancar SKYRIM.\n\nLevanta el modelo de lenguaje, el "
             "servidor de voz%s, y luego abre el juego con SKSE desde Mod "
             "Organizer.\n\nTarda entre dos y tres minutos y se come casi toda "
             "la tarjeta grafica.\n\nLe dejas?"
             % (" y Mantella, que es lo que hace hablar a los NPC"
                if con_mantella else ""))
    if permiso is None or not permiso(aviso):
        _apuntar("SIN PERMISO", "jugar a Skyrim", "Angel ha dicho que no")
        return "Angel no me ha dado permiso, no he arrancado el juego."

    pr = _procesos()
    uso_lanzador = False
    if pr["skyrim"]:
        pasos.append("Skyrim ya estaba abierto")
    else:
        try:
            if os.path.isfile(LANZADOR):
                # OJO: el lanzador es un .ps1, y con "start" Windows lo abriria
                # en el bloc de notas en vez de ejecutarlo. Hay que llamar a
                # PowerShell. Y se le da consola propia a proposito: va
                # contando por donde va y hace falta ver si algo no sube.
                subprocess.Popen(["powershell", "-NoProfile",
                                  "-ExecutionPolicy", "Bypass",
                                  "-File", LANZADOR],
                                 cwd=os.path.dirname(LANZADOR),
                                 creationflags=NUEVA_CONSOLA)
                pasos.append("lanzado el arranque completo: el modelo, la voz, "
                             "Mantella y el juego, en ese orden")
                uso_lanzador = True
            else:
                subprocess.Popen([MO2, "moshortcut://:SKSE"], cwd=JUEGO,
                                 creationflags=SIN_VENTANA)
                pasos.append("lanzado MO2 con SKSE")
        except Exception as e:
            return "No he podido arrancar el juego: %s" % e

    # El lanzador ya enciende Mantella, y ademas el modelo de lenguaje y el
    # servidor de voz, que sin esos dos los NPC no dicen ni mu. Asi que cuando
    # se ha usado el lanzador no hay que arrancar Mantella otra vez por
    # nuestra cuenta: se duplicaria.
    if con_mantella and not uso_lanzador:
        if pr["mantella"]:
            pasos.append("Mantella ya estaba encendido")
        elif os.path.isfile(_exe()):
            try:
                subprocess.Popen([_exe()], cwd=os.path.dirname(_exe()),
                                 creationflags=SIN_VENTANA)
                pasos.append("Mantella arrancado")
            except Exception as e:
                pasos.append("Mantella NO ha arrancado (%s)" % e)
        else:
            pasos.append("no encuentro Mantella.exe")

    _apuntar("SKYRIM", "jugar", "; ".join(pasos))
    return ("Ya esta en marcha: %s. Steam puede tardar en iniciar sesion y el "
            "juego un par de minutos. Si los NPC no contestan o el PC hace un "
            "ruido de tos, dimelo y le miro el log a Mantella."
            % ", ".join(pasos))


# ===================================================================
#  EL CEREBRO DE SOBRI (no el de Mantella)
# ===================================================================
#
# Va en este modulo porque aqui ya estaba toda la fontaneria para hablar con
# Google y medir modelos. Angel pidio el 27/08 que Sobri fuera "lo mas
# inteligente y resolutivo posible", y parte de ser resolutivo es que cuando
# se le atasque la cabeza sepa DECIR por que, en vez de contestar despacio y
# que parezca que esta roto.
#
# El caso real: su cerebro principal (`gemini-3.1-flash-lite`) se quedo sin
# cuota diaria y daba 429. Sobri seguia funcionando, pero tirando del tercero
# de la lista, que tarda 6 segundos por frase. Desde fuera eso es "me falla".

def _cerebros_de_berna():
    try:
        with open(os.path.join(BASE, "config.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def estado_del_cerebro():
    """Prueba uno a uno los cerebros de Sobri y dice cual sirve hoy."""
    import requests
    cfg = _cerebros_de_berna()
    modelos = cfg.get("modelos") or []
    if not modelos:
        return "No tengo ninguna lista de modelos en config.json."
    clave = (cfg.get("clave_gemini") or "").strip()
    l = ["MIS CEREBROS, PROBADOS UNO A UNO AHORA MISMO:", ""]
    vivos = 0
    for m in modelos[:8]:
        if not m.startswith("gemini:"):
            l.append("  %-34s (de OpenRouter, no lo pruebo aqui)" % m)
            continue
        if "@" in m:
            continue            # el mismo modelo con otra clave: ya se prueba sin '@'
        nombre = m.split(":", 1)[1]
        if not clave:
            l.append("  %-34s sin clave de Google" % nombre)
            continue
        t0 = time.time()
        try:
            r = requests.post(
                "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                headers={"Authorization": "Bearer " + clave,
                         "Content-Type": "application/json"},
                json={"model": nombre, "max_tokens": 10,
                      "messages": [{"role": "user", "content": "Di solo hola"}]},
                timeout=45)
            t = time.time() - t0
            if r.status_code == 200:
                vivos += 1
                l.append("  %-34s BIEN, %.1f s" % (nombre, t))
            elif r.status_code == 429:
                l.append("  %-34s SIN CUOTA por hoy" % nombre)
            elif r.status_code == 503:
                l.append("  %-34s saturado ahora mismo" % nombre)
            else:
                l.append("  %-34s error %s" % (nombre, r.status_code))
        except Exception as e:
            l.append("  %-34s no contesta (%s)" % (nombre, str(e)[:30]))
    l.append("")
    if vivos == 0:
        l.append("NINGUNO responde. O no hay internet, o se ha acabado la cuota "
                 "del dia entera. La de Google se renueva sola; hasta entonces no "
                 "hay mucho que hacer.")
    else:
        l.append("Tengo %d cerebro(s) que funcionan, asi que voy tirando. Uso "
                 "siempre el primero de la lista que responda, y al que falla lo "
                 "aparto media hora para no tropezar con el en cada frase."
                 % vivos)
    l.append("")
    l.append("Cuentaselo a Angel en dos frases, sin leerle la lista. Si el "
             "primero esta sin cuota y hay otro bien, dile que vas mas lento "
             "pero que sigues funcionando.")
    return "\n".join(l)
