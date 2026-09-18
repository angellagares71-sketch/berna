# -*- coding: utf-8 -*-
"""Canciones hechas por IA EN ESTE ORDENADOR, gratis y sin limites.

Sobri ya sabia pedirle canciones a la IA de Google (cancion_ia.py), pero eso
cuesta centimos y necesita internet. Esto es la alternativa: ACE-Step 1.5,
un modelo libre con licencia MIT instalado en C:\\ACEStep. No cuesta nada, no
tiene limite diario, funciona sin internet y **lo que sale se puede publicar
y hasta vender**, que era justo lo que Angel pedia.

POR QUE SE LLAMA POR SEPARADO Y NO SE IMPORTA:
Sobri corre en Python 3.14 y ACE-Step exige 3.11 o 3.12. Son dos entornos
distintos y no se pueden mezclar en el mismo proceso, asi que se le llama como
programa aparte con su propio Python. Es feo pero es lo unico que funciona.

LO QUE HAY QUE SABER ANTES DE PROMETERLE NADA A ANGEL:
Este portatil no tiene grafica utilizable (Radeon integrada), asi que va por
procesador. Medido el 04/09/2026: **unos 5,4 segundos de calculo por cada
segundo de musica**. Medio minuto de cancion son casi 3 minutos de espera, y
una cancion entera de 3 minutos son unos 16. Hay que avisarle SIEMPRE antes,
que si no parece que se ha colgado.
"""

import difflib
import importlib.util
import json
import os
import re
import socket
import subprocess
import time
import unicodedata
import uuid

PYTHON_IA = r"C:\ACEStep\venv\Scripts\python.exe"
GENERADOR = r"C:\ACEStep\generar.py"
RAIZ_IA = r"C:\ACEStep\repo"
ESTUDIO = r"C:\ACEStep\estudio.pyw"
PYTHONW_IA = r"C:\ACEStep\venv\Scripts\pythonw.exe"
PUENTE = r"C:\ACEStep\puente_berna"
ORDEN_PUENTE = os.path.join(PUENTE, "orden.json")
ESTADO_PUENTE = os.path.join(PUENTE, "estado.json")
PUERTO_ESTUDIO = 51765

# Lo que tarda por cada segundo de musica, medido en esta maquina.
FACTOR = 5.4

# Los estilos, con su velocidad, su tono y la descripcion en ingles, que es lo
# que entiende el modelo. Son los mismos nombres que usa el resto de Sobri.
ESTILOS = {
    "reggaeton": (95, "A minor",
        "reggaeton, dembow rhythm, deep punchy sub bass, latin percussion, "
        "bright synth stabs, crisp hi hats, modern club production, confident"),
    "reggaeton romantico": (92, "F# minor",
        "romantic reggaeton, smooth dembow rhythm, warm sub bass, soft piano, "
        "latin percussion, lush reverb, emotional and sensual"),
    "trap": (140, "C minor",
        "latin trap, deep 808 sub bass with slides, crisp rolling hi hats, "
        "dark piano, sparse arrangement, moody and nocturnal"),
    "hiphop": (92, "D minor",
        "boom bap hip hop, dusty drum break, upright bass, jazzy piano "
        "samples, vinyl crackle, laid back and nostalgic, 90s production"),
    "breakbeat": (135, "G minor",
        "breakbeat, chopped amen break, rolling sub bass, rave stabs, "
        "filtered pads, energetic warehouse feel"),
    "house": (124, "A minor",
        "house, four on the floor kick, deep rolling bassline, warm rhodes "
        "chords, hand claps, bright hi hats, uplifting club production"),
    "salsa": (190, "G minor",
        "salsa, montuno piano, brass section, congas and timbales, walking "
        "upright bass, live band recording, joyful and danceable"),
    "bachata": (128, "B minor",
        "bachata, requinto guitar lead, bongo and guira, warm bass, "
        "romantic and heartfelt, modern production"),
    "pop": (120, "C major",
        "modern pop, punchy drums, warm synth bass, bright piano chords, "
        "catchy and radio ready, polished production"),
    "disco": (125, "A minor",
        "nu disco, four on the floor groove, slap bass, funky guitar, "
        "string stabs, warm analog production, feel good"),
}


def _normalizar(texto):
    texto = unicodedata.normalize("NFD", str(texto or "").lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", texto).strip()


def _si(valor):
    if isinstance(valor, bool):
        return valor
    return _normalizar(valor) in ("si", "1", "true", "yes", "vale")


def _cargar_catalogo_completo():
    """Lee el catalogo del estudio sin confundirlo con estilos.py de Sobri.

    Los dos archivos se llaman igual por razones historicas: el de Sobri lleva
    acentos y personalidades; el del estudio lleva generos musicales. Cargarlo
    con un nombre interno evita que uno pise al otro.
    """
    ruta = r"C:\ACEStep\estilos.py"
    spec = importlib.util.spec_from_file_location("_catalogo_musical_ace", ruta)
    if spec is None or spec.loader is None:
        raise ImportError("no se puede leer %s" % ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)

    catalogo = {}
    nombres = {}
    for nombre, datos in modulo.ESTILOS.items():
        clave = _normalizar(nombre)
        catalogo[clave] = datos
        nombres[clave] = nombre
    familias = {familia: list(nombres_familia)
                for familia, nombres_familia in modulo.FAMILIAS.items()}
    return catalogo, nombres, familias


_ESTILOS_BASICOS = ESTILOS
try:
    ESTILOS, NOMBRES_ESTILOS, FAMILIAS_ESTILOS = _cargar_catalogo_completo()
except Exception:
    ESTILOS = {_normalizar(nombre): datos
               for nombre, datos in _ESTILOS_BASICOS.items()}
    NOMBRES_ESTILOS = {clave: clave.title() for clave in ESTILOS}
    FAMILIAS_ESTILOS = {"Favoritos": list(NOMBRES_ESTILOS.values())}

_ALIAS_ESTILOS = {
    "reggaeton": "regueton",
    "reggaeton romantico": "regueton romantico",
    "hiphop": "hip hop",
    "breakbeat": "break beat",
    "lofi": "lo fi",
    "drum n bass": "drum and bass",
    "dnb": "drum and bass",
    "rnb": "neo soul",
}

MOTORES = {
    "rapido": ("Rapido", "acestep-v15-turbo"),
    "alta calidad": ("Alta calidad", "acestep-v15-sft"),
}

VOCES = {
    "ia": "Que elija la IA",
    "femenina": "Voz femenina",
    "masculina": "Voz masculina",
    "duo": "Duo",
    "coro": "Coro",
    "instrumental": "Instrumental",
}

ACABADOS = {
    "natural": "Natural",
    "intimo": "Intimo",
    "radio": "Radio",
    "directo": "Directo",
    "cinematico": "Cinematico",
}

_ALIAS_MOTORES = {
    "alta": "alta calidad", "calidad": "alta calidad", "sft": "alta calidad",
    "turbo": "rapido",
}

_ALIAS_VOCES = {
    "mujer": "femenina", "chica": "femenina", "hombre": "masculina",
    "chico": "masculina", "dueto": "duo", "sin voz": "instrumental",
}


def _resolver_opcion(valor, opciones, alias, defecto):
    """Normaliza una opcion visible y devuelve su valor seguro."""
    clave = _normalizar(valor or defecto)
    clave = alias.get(clave, clave)
    return opciones.get(clave, opciones[defecto])


def _limite_corte():
    """Los minutos a los que el motor corta y tira el trabajo a la basura.

    No es un aviso teorico: el 05/09/2026 una cancion de 225 segundos se paso
    del limite y se perdieron diez minutos de espera. Con el motor de alta
    calidad pasarse es facilisimo, asi que se dice ANTES de pedir permiso.
    """
    try:
        with open(r"C:\ACEStep\ajustes.json", "r", encoding="utf-8") as f:
            return max(10, int(json.load(f).get("limite_minutos") or 60))
    except Exception:
        return 60


def _resolver_estilo(nombre):
    clave = _normalizar(nombre or "regueton")
    clave = _ALIAS_ESTILOS.get(clave, clave)
    if clave in ESTILOS:
        return clave
    parecidos = difflib.get_close_matches(clave, list(ESTILOS), n=1, cutoff=0.78)
    return parecidos[0] if parecidos else ""


def _hay_motor():
    return os.path.exists(PYTHON_IA) and os.path.exists(GENERADOR)


def _estudio_abierto():
    try:
        with socket.create_connection(("127.0.0.1", PUERTO_ESTUDIO), timeout=0.4):
            return True
    except OSError:
        return False


def _leer_estado_puente():
    try:
        with open(ESTADO_PUENTE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _abrir_estudio():
    """Abre el estudio de escritorio; si ya estaba, lo trae al frente."""
    try:
        subprocess.Popen([PYTHONW_IA, ESTUDIO], cwd=r"C:\ACEStep",
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return True, ""
    except Exception as e:
        return False, str(e)


def _mandar_al_estudio(orden, timeout):
    """Entrega una composicion al programa visible y espera su resultado."""
    os.makedirs(PUENTE, exist_ok=True)
    if not _estudio_abierto():
        ok, err = _abrir_estudio()
        if not ok:
            return None, "No he podido abrir Musica IA: %s" % err

    # Escritura atomica: el estudio nunca puede leer media orden.
    tmp = ORDEN_PUENTE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(orden, f, ensure_ascii=False, indent=2)
    os.replace(tmp, ORDEN_PUENTE)

    limite = time.time() + timeout
    visto_arranque = False
    while time.time() < limite:
        estado = _leer_estado_puente()
        if estado.get("id") == orden["id"]:
            if estado.get("estado") == "componiendo":
                visto_arranque = True
            elif estado.get("estado") == "terminada":
                return estado, ""
            elif estado.get("estado") == "fallo":
                return None, estado.get("error") or "fallo desconocido del motor"
        # Si la ventana no llega a arrancar, no hacemos esperar una hora.
        if not visto_arranque and time.time() > limite - timeout + 45:
            if not _estudio_abierto():
                return None, "El programa Musica IA no ha conseguido abrirse."
        time.sleep(0.5)
    return None, ("La composicion sigue sin terminar despues del limite de "
                  "seguridad. Mira la ventana de Musica IA: puede seguir alli.")


def abrir_estudio_musica_ia(permiso=None):
    """Abre el programa de Musica IA o trae al frente la copia existente."""
    if permiso is not None and not permiso(
            "Sobri va a abrir el programa Musica IA. Le dejas?"):
        return "No me has dado permiso, no lo he abierto."
    ok, err = _abrir_estudio()
    if not ok:
        return "No he podido abrir Musica IA: %s" % err
    return ("Musica IA ya estaba abierto y lo he traido al frente."
            if _estudio_abierto() else
            "Estoy abriendo Musica IA; aparecera en unos segundos.")


def estado_musica_ia():
    """Cuenta si el estudio esta abierto y si Sobri esta componiendo."""
    abierto = _estudio_abierto()
    estado = _leer_estado_puente()
    if estado.get("estado") == "componiendo" and abierto:
        cuanto = max(0, int(time.time() - float(estado.get("momento") or time.time())))
        return ("Musica IA esta abierto y componiendo '%s' desde hace %d min %d s."
                % (estado.get("titulo") or "una cancion", cuanto // 60,
                   cuanto % 60))
    if estado.get("estado") == "componiendo" and not abierto:
        return ("Musica IA esta cerrado. La ultima composicion quedo "
                "interrumpida antes de terminar.")
    if estado.get("estado") == "terminada":
        archivos = estado.get("archivos") or []
        return ("Musica IA esta %s. La ultima composicion termino: %s"
                % ("abierto" if abierto else "cerrado",
                   ", ".join(archivos) if archivos else "sin archivo indicado"))
    if estado.get("estado") == "fallo":
        return ("Musica IA esta %s. La ultima composicion fallo: %s"
                % ("abierto" if abierto else "cerrado",
                   estado.get("error") or "sin detalle"))
    return "Musica IA esta %s y listo." % ("abierto" if abierto else "cerrado")


def biblioteca_musica_ia(limite=10):
    """Lista las ultimas canciones y los datos musicales de su ficha."""
    carpeta = os.path.join(os.path.expanduser("~"), "Music", "Canciones de Berna")
    try:
        ruta_ajustes = r"C:\ACEStep\ajustes.json"
        with open(ruta_ajustes, "r", encoding="utf-8") as f:
            carpeta = json.load(f).get("carpeta_canciones") or carpeta
    except Exception:
        pass
    try:
        limite = max(1, min(50, int(limite)))
    except Exception:
        limite = 10
    if not os.path.isdir(carpeta):
        return "La biblioteca esta vacia: %s" % carpeta
    audios = []
    for nombre in os.listdir(carpeta):
        if os.path.splitext(nombre)[1].lower() not in (".wav", ".mp3", ".flac", ".ogg"):
            continue
        ruta = os.path.join(carpeta, nombre)
        try:
            audios.append((os.path.getmtime(ruta), ruta))
        except OSError:
            pass
    audios.sort(reverse=True)
    if not audios:
        return "La biblioteca esta vacia: %s" % carpeta
    lineas = ["Ultimas canciones de Musica IA:"]
    for _fecha, ruta in audios[:limite]:
        ficha = {}
        try:
            with open(os.path.splitext(ruta)[0] + ".json", "r", encoding="utf-8") as f:
                ficha = json.load(f)
        except Exception:
            pass
        extras = []
        if ficha.get("bpm"):
            extras.append("%s BPM" % ficha["bpm"])
        if ficha.get("tono"):
            extras.append(str(ficha["tono"]))
        if ficha.get("nota") is not None:
            extras.append("nota %s/100" % ficha["nota"])
        lineas.append("- %s%s\n  %s" % (
            ficha.get("titulo") or os.path.basename(ruta),
            " (%s)" % ", ".join(extras) if extras else "", ruta))
    return "\n".join(lineas)


def _con_estructura(letra):
    """Le pone las etiquetas de estructura a la letra si no las lleva.

    El modelo necesita saber donde empieza la estrofa y donde el estribillo:
    si le llega la letra a pelo, canta de corrido y suena a lista de la compra.
    Las etiquetas van EN INGLES a proposito, que es lo que entiende; la letra
    en si va en el idioma que sea.
    """
    t = (letra or "").strip()
    if not t:
        return ""
    if "[" in t and "]" in t:
        return t                      # ya trae etiquetas puestas
    trozos = [b.strip() for b in t.split("\n\n") if b.strip()]
    if len(trozos) == 1:
        # un solo bloque: se parte por la mitad, estrofa y estribillo
        lineas = [l for l in trozos[0].splitlines() if l.strip()]
        if len(lineas) >= 4:
            mitad = len(lineas) // 2
            trozos = ["\n".join(lineas[:mitad]), "\n".join(lineas[mitad:])]
        else:
            return "[Verse]\n" + trozos[0]
    etiquetas = ["[Verse]", "[Chorus]", "[Verse]", "[Chorus]", "[Bridge]",
                 "[Outro]"]
    salida = []
    for i, bloque in enumerate(trozos):
        salida.append("%s\n%s" % (etiquetas[i] if i < len(etiquetas)
                                  else "[Verse]", bloque))
    return "\n\n".join(salida)


def _limpio(nombre):
    n = re.sub(r'[<>:"/\\|?*]', "", str(nombre or "")).strip()
    return (n or "cancion")[:60]


def estilos_de_musica_ia():
    """Que estilos sabe hacer la IA local."""
    if not _hay_motor():
        return ("La IA de musica no esta instalada en este ordenador. "
                "Deberia estar en C:\\ACEStep.")
    filas = ["La IA local sabe hacer %d estilos, gratis y sin limite:" %
             len(ESTILOS)]
    for familia, nombres in FAMILIAS_ESTILOS.items():
        filas.append("\n%s (%d):" % (familia, len(nombres)))
        filas.append("  " + ", ".join(nombres))
    filas.append("")
    filas.append("Tarda unos %.1f segundos por cada segundo de musica." % FACTOR)
    filas.append("Motores: Rapido, o Alta calidad si prefieres mejor acabado.")
    filas.append("Voces: a eleccion de la IA, femenina, masculina, duo, coro o instrumental.")
    filas.append("Acabados: natural, intimo, radio, directo o cinematografico.")
    return "\n".join(filas)


def crear_cancion_local(estilo="reggaeton", peticion="", nombre="",
                        segundos=40, con_voz=False, letra="", bpm=0, tono="",
                        abrir=False, variaciones=1, calidad="Rapida",
                        idioma="es", semilla=-1, pensar=True, motor="rapido",
                        voz="ia", acabado="natural", permiso=None):
    """Compone en el programa Musica IA. Gratis, local y sin limites."""
    if not _hay_motor():
        return ("No tengo la IA de musica instalada. Tendria que estar en "
                "C:\\ACEStep con su propio Python.")

    pedido = (estilo or "regueton").strip()
    clave = _resolver_estilo(pedido)
    if clave not in ESTILOS:
        # si no lo reconoce pero Angel ha descrito lo que quiere, tira de eso
        if not peticion:
            cercanos = difflib.get_close_matches(
                _normalizar(pedido), list(ESTILOS), n=5, cutoff=0.45)
            sugeridos = [NOMBRES_ESTILOS[c] for c in cercanos]
            return ("No conozco el estilo '%s'.%s Pideme "
                    "estilos_de_musica_ia para ver los %d disponibles."
                    % (estilo,
                       " Quiza querias: %s." % ", ".join(sugeridos)
                       if sugeridos else "",
                       len(ESTILOS)))
        v_bpm, v_tono, descripcion = 95, "A minor", peticion
        nombre_estilo = pedido or "A medida"
    else:
        v_bpm, v_tono, descripcion = ESTILOS[clave]
        nombre_estilo = NOMBRES_ESTILOS.get(clave, pedido)
        if peticion:
            descripcion = "%s, %s" % (descripcion, peticion)

    try:
        segundos = max(10, min(300, int(segundos)))
    except Exception:
        segundos = 40
    try:
        v_bpm = max(60, min(200, int(float(bpm)))) if bpm else v_bpm
    except Exception:
        pass
    v_tono = tono or v_tono
    try:
        variaciones = max(1, min(4, int(variaciones)))
    except Exception:
        variaciones = 1
    calidades = {"rapida": "Rapida", "media": "Media", "alta": "Alta"}
    calidad = calidades.get(_normalizar(calidad), "Rapida")
    motor_nombre, modelo_musica = _resolver_opcion(
        motor, MOTORES, _ALIAS_MOTORES, "rapido")
    voz_nombre = _resolver_opcion(voz, VOCES, _ALIAS_VOCES, "ia")
    acabado_nombre = _resolver_opcion(acabado, ACABADOS, {}, "natural")
    try:
        semilla = int(semilla)
    except Exception:
        semilla = -1
    idioma_clave = _normalizar(idioma) or "es"
    idiomas = {
        "es": "es", "espanol": "es", "castellano": "es",
        "en": "en", "ingles": "en", "english": "en",
        "it": "it", "italiano": "it", "fr": "fr", "frances": "fr",
        "de": "de", "aleman": "de", "pt": "pt", "portugues": "pt",
        "ja": "ja", "japones": "ja", "ko": "ko", "coreano": "ko",
        "zh": "zh", "chino": "zh",
    }
    idioma = idiomas.get(idioma_clave, "es")

    # Si hay letra, se canta. Elegir una voz concreta tambien significa que
    # Angel quiere una cancion cantada. Instrumental manda sobre lo demas.
    letra_final = _con_estructura(letra) if (letra or "").strip() else ""
    if voz_nombre == "Instrumental":
        letra_final = ""
        con_voz = False
    elif not letra_final and (_si(con_voz) or voz_nombre != "Que elija la IA"):
        return ("Quieres que cante pero no me has dado letra. Escribeme una "
                "(o dime de que va y te la invento yo) y lo hacemos.")

    pasos = ({"Rapida": 32, "Media": 50, "Alta": 64}[calidad]
             if modelo_musica.endswith("-sft") else
             {"Rapida": 8, "Media": 14, "Alta": 20}[calidad])
    # El reloj, igual que en el estudio (estudio.pyw:minutos_espera). Se suma
    # lo que cuesta cada cosa en vez de multiplicar a ojo:
    #   - pensar cuesta la cuarta parte de los 5,4 s medidos por segundo
    #   - cada paso de difusion cuesta las otras tres cuartas partes / 8
    #   - el motor de alta calidad usa CFG y hace DOS pasadas por paso, no una
    # Antes el aviso prometia doce minutos donde el PC se tiraba cerca de una
    # hora, y Angel decia que si sin saber a lo que se apuntaba.
    pasadas = 2 if modelo_musica.endswith("-sft") else 1
    pensando = _si(pensar) if not isinstance(pensar, bool) else pensar
    por_segundo = FACTOR * 0.75 / 8 * pasos * pasadas
    if pensando:
        por_segundo += FACTOR * 0.25
    factor_versiones = 1 + 0.85 * (variaciones - 1)
    minutos = segundos * por_segundo * factor_versiones / 60.0

    limite = _limite_corte()
    corte = ("" if minutos < limite * 0.8 else
             "\n\nOJO: el motor corta a los %d minutos y esto se pasa o se "
             "queda al borde. Si se pasa se pierde la cancion entera. Mejor "
             "bajamos la calidad o la duracion, o subes el limite en los "
             "ajustes del estudio." % limite)

    aviso = ("Sobri va a hacer una cancion con la IA de este ordenador:\n\n"
             "  estilo: %s\n  duracion: %d segundos\n"
             "  velocidad: %d pulsaciones\n  tono: %s\n"
             "  motor: %s\n  calidad: %s%s\n"
             "  voz: %s\n  acabado: %s\n\n"
             "Va a tardar unos %.0f minutos, porque este portatil no tiene "
             "grafica y lo hace con el procesador. No cuesta dinero y no hay "
             "limite de canciones.%s\n\nLe dejas?"
             % (nombre_estilo, segundos, v_bpm, v_tono, motor_nombre, calidad,
                " · %d versiones" % variaciones if variaciones > 1 else "",
                voz_nombre, acabado_nombre, minutos, corte))
    if permiso is not None and not permiso(aviso):
        return "No me has dado permiso, no he hecho nada."

    id_trabajo = uuid.uuid4().hex
    orden = {
        "id": id_trabajo, "accion": "crear", "estilo": nombre_estilo,
        "descripcion": descripcion[:512], "idea": peticion,
        "nombre": _limpio(nombre or ("IA_%s" % nombre_estilo)),
        "bpm": v_bpm, "tono": v_tono, "segundos": segundos,
        "idioma": idioma, "calidad": calidad, "variaciones": variaciones,
        "modelo_musica": modelo_musica, "motor": motor_nombre,
        "voz": voz_nombre, "acabado": acabado_nombre,
        "semilla": semilla, "pensar": pensando,
        "letra": letra_final[:4096],
    }
    # El margen cubre el arranque, el masterizado y ordenadores ocupados.
    timeout = max(180, int(minutos * 60 * 2.2 + 180))
    try:
        resultado, error = _mandar_al_estudio(orden, timeout)
    except Exception as e:
        return "No he podido hablar con el programa Musica IA: %s" % e
    if not resultado:
        return "Musica IA no ha terminado la cancion: %s" % error

    ficheros = resultado.get("archivos") or []
    if not ficheros:
        return "Musica IA termino pero no indico ningun archivo."
    ruta = ficheros[0]
    lineas = ["Te he compuesto la cancion dentro del programa Musica IA.",
              "  estilo: %s   %d pulsaciones   tono: %s" %
              (nombre_estilo, v_bpm, v_tono),
              "  motor: %s   voz: %s   acabado: %s" %
              (motor_nombre, voz_nombre, acabado_nombre),
              "  duracion: %d segundos" % segundos,
              "  archivo%s: %s" % ("s" if len(ficheros) > 1 else "",
                                     ", ".join(ficheros))]
    if resultado.get("tardado") is not None:
        lineas.append("  ha tardado: %.0f minutos" %
                      (float(resultado["tardado"]) / 60))
    if resultado.get("pegas"):
        lineas.append("  aviso de calidad: %s" %
                      "; ".join(resultado["pegas"]))
    lineas.append("  no ha costado nada y puedes publicarla: la licencia lo permite.")

    if _si(abrir) and os.path.exists(ruta):
        try:
            os.startfile(ruta)
            lineas.append("  te la he puesto ya.")
        except Exception:
            pass
    return "\n".join(lineas)
