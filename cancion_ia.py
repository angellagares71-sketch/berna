# -*- coding: utf-8 -*-
r"""
Canciones de verdad, generadas por la IA de musica de Google (Lyria 3).

POR QUE EXISTE ESTO, y por que no basta con musica.py
  `musica.py` compone escribiendo notas y dejando que LMMS las toque. Eso tiene
  un techo, y se toco: Angel dijo CINCO veces que sonaba a politono, y llevaba
  razon. Un banco General MIDI es, en esencia, la misma tecnologia con la que se
  hacian los politonos. Por muchos loops, reverb y compresores que se le metan,
  no va a sonar a un tema de hoy, porque le faltan tres cosas que no se
  programan: instrumentos grabados de verdad (no 141 MB, sino gigas), una
  interpretacion humana, y una VOZ cantando.

  Lyria 3 hace exactamente eso: le dices en cristiano que quieres y devuelve
  audio de 44.100 Hz en estereo, con su arreglo, su produccion y, si se le pide,
  con voz y letra.

LAS DOS SIGUEN HACIENDO FALTA, y no se pisan
  - `crear_cancion` (musica.py) da un PROYECTO DE LMMS que Angel puede abrir y
    tocar nota a nota. Es suyo, es gratis y funciona sin internet.
  - `crear_cancion_ia` (esto) da una CANCION TERMINADA que suena a disco, pero
    es un archivo de audio: no se puede editar por dentro, necesita internet y
    cuesta unos centimos.

LO QUE CUESTA (consultado el 03-09-2026)
  Un trozo de 30 segundos, 0,04 dolares. Una cancion entera de un par de
  minutos, 0,08. O sea, unos cuatro centimos y ocho centimos. NO hay capa
  gratuita: la cuenta de Google tiene que tener la facturacion activada, y si no
  la tiene la API contesta con "limit: 0" y aqui se le explica a Angel que
  hacer, en vez de soltarle el error tal cual.

LA CLAVE ES LA MISMA que ya usa Sobri para ver por la camara y mirar la
pantalla (`clave_gemini` en config.json). No hay que dar de alta nada nuevo.
"""
import base64
import io
import json
import os
import re
import time
import unicodedata

BASE = os.path.dirname(os.path.abspath(__file__))
URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
MODELO_CORTO = "lyria-3-clip-preview"     # 30 segundos, 0,04 dolares
MODELO_LARGO = "lyria-3-pro-preview"      # un par de minutos, 0,08 dolares
ESPERA = 300

SIN_CLAVE = ("No tengo la clave de Google puesta. Es la misma que uso para ver "
             "por la camara: va en clave_gemini, dentro de config.json.")

SIN_SALDO = (
    "Google me deja pedirlo, pero la cuenta no tiene la musica activada: "
    "contesta que el limite gratuito es CERO.\n"
    "  Se arregla una sola vez, entrando en aistudio.google.com/apikey y "
    "activando la facturacion de esa clave.\n"
    "  Cuesta 4 centimos el trozo de medio minuto y 8 la cancion entera, asi "
    "que con un euro salen mas de diez canciones.\n"
    "  Mientras tanto puedo hacerte la base yo mismo en LMMS con crear_cancion, "
    "que es gratis y no necesita internet.")


def _cfg():
    try:
        with io.open(os.path.join(BASE, "config.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _clave():
    return (_cfg().get("clave_gemini") or "").strip()


def _sin_tildes(t):
    t = unicodedata.normalize("NFD", str(t or ""))
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower()


def _limpio(nombre):
    n = re.sub(r"[^\w\s-]", "", str(nombre or "")).strip()
    n = re.sub(r"\s+", "_", n)
    return n[:60] or "cancion"


def _carpeta():
    """La misma carpeta donde deja las que compone ella, para no dispersar."""
    try:
        import musica
        return musica._carpeta_musica()
    except Exception:
        return os.path.join(os.path.expanduser("~"), "Music", "Canciones de Berna")


def _buscar_audio(o):
    """El audio viene en base64 dentro de la respuesta. Se busca sin suponer.

    Se recorre el arbol entero en vez de ir por una ruta fija ("steps > 0 >
    model_output > ...") porque esa ruta es de un modelo en pruebas y cambia. Si
    cambia, esto sigue encontrandolo.
    """
    if isinstance(o, dict):
        a = o.get("audio")
        if isinstance(a, dict) and a.get("data"):
            return a["data"], a.get("mime_type", "")
        for v in o.values():
            hallado = _buscar_audio(v)
            if hallado:
                return hallado
    elif isinstance(o, list):
        for v in o:
            hallado = _buscar_audio(v)
            if hallado:
                return hallado
    return None


def _describir(peticion, letra, con_voz):
    """Convierte lo que ha dicho Angel en un encargo claro para el modelo.

    Se le anaden las cosas que casi nunca se dicen pero siempre se dan por
    supuestas (que este bien mezclado, que tenga estructura), porque el modelo
    responde mucho mejor a un encargo concreto que a dos palabras sueltas.
    """
    trozos = [str(peticion or "").strip() or "una cancion alegre"]
    if con_voz and letra:
        trozos.append("Cantada en espanol, con esta letra:\n" + letra.strip())
    elif con_voz:
        trozos.append("Con voz cantando en espanol de Espana.")
    else:
        trozos.append("Instrumental, sin voz.")
    trozos.append("Bien producida y mezclada, con estructura de cancion "
                  "(entrada, estrofa y estribillo) y un final que cierre.")
    return "\n\n".join(trozos)


def crear_cancion_ia(peticion, letra="", completa="si", con_voz="si",
                     nombre="", abrir="no", permiso=None):
    r"""Le encarga a la IA de musica de Google una cancion de verdad.

    Devuelve el parte por escrito: donde ha quedado, cuanto dura y que ha
    costado. Si la cuenta no tiene la musica activada, lo explica en cristiano
    en vez de soltar el error de Google.
    """
    clave = _clave()
    if not clave:
        return SIN_CLAVE

    largo = str(completa).strip().lower() in ("si", "sí", "1", "true", "yes")
    voz = str(con_voz).strip().lower() in ("si", "sí", "1", "true", "yes")
    modelo = MODELO_LARGO if largo else MODELO_CORTO
    precio = "8 centimos" if largo else "4 centimos"
    dura = "un par de minutos" if largo else "medio minuto"

    encargo = _describir(peticion, letra, voz)

    aviso = ("Sobri va a encargarle una cancion a la inteligencia artificial de "
             "musica de Google:\n\n%s\n\nDura %s y cuesta unos %s. Le dejas?"
             % (encargo[:400], dura, precio))
    if permiso is not None and not permiso(aviso):
        return "No me has dado permiso, no he pedido nada."

    import requests
    t0 = time.time()
    try:
        r = requests.post(URL, timeout=ESPERA,
                          headers={"x-goog-api-key": clave,
                                   "Content-Type": "application/json"},
                          json={"model": modelo, "input": encargo})
    except Exception as ex:
        return "No he podido conectar con Google: %s" % str(ex)[:120]

    if r.status_code == 429 and "limit: 0" in (r.text or ""):
        return SIN_SALDO
    if r.status_code == 429:
        return ("Google me ha dicho que espere un poco, que va saturado. "
                "Vuelve a pedirmelo en un minuto.")
    if r.status_code in (401, 403):
        return ("Google no me acepta la clave para la musica. Comprueba en "
                "aistudio.google.com/apikey que sigue valida.")
    if r.status_code != 200:
        return ("Google ha contestado con un error %d: %s"
                % (r.status_code, (r.text or "")[:200]))

    try:
        datos = r.json()
    except Exception:
        return "Google ha contestado algo que no entiendo."

    hallado = _buscar_audio(datos)
    if not hallado:
        return ("Google ha contestado pero no venia el audio. Puede que la "
                "peticion tenga algo que no le ha gustado. Prueba a decirmelo "
                "de otra forma.")

    b64, mime = hallado
    try:
        crudo = base64.b64decode(b64)
    except Exception:
        return "El audio ha venido roto."

    ext = "wav" if "wav" in (mime or "").lower() else "mp3"
    carpeta = _carpeta()
    try:
        os.makedirs(carpeta, exist_ok=True)
    except Exception as ex:
        return "No he podido crear la carpeta de las canciones: %s" % ex

    titulo = str(nombre or "").strip() or (str(peticion or "cancion")[:40])
    destino = os.path.join(carpeta, _limpio(titulo) + "." + ext)
    n = 2
    while os.path.exists(destino):
        destino = os.path.join(carpeta, "%s_%d.%s" % (_limpio(titulo), n, ext))
        n += 1
    try:
        with open(destino, "wb") as f:
            f.write(crudo)
    except Exception as ex:
        return "No he podido guardarla: %s" % ex

    parte = ["Ya la tienes: '%s'." % titulo,
             "  la ha hecho la IA de musica de Google (%s)"
             % ("cancion entera" if largo else "trozo de medio minuto"),
             "  %s" % ("con voz cantando" if voz else "instrumental"),
             "  archivo: %s  (%d KB)" % (destino, len(crudo) // 1024),
             "  ha tardado %.0f segundos y ha costado unos %s"
             % (time.time() - t0, precio)]

    # comprobar que suena de verdad, igual que con las que compone ella
    try:
        import musica
        import numpy as np
        d, ritmo = musica._leer_audio(destino)
        if d.size:
            nivel = float(np.sqrt(np.mean(d * d)))
            parte.append("  comprobado: %.0f segundos, nivel medio %.3f"
                         % (d.size / float(ritmo or 44100), nivel))
            if nivel < 0.002:
                parte.append("  OJO: ha venido en silencio. Diselo a Angel.")
    except Exception:
        pass

    if str(abrir).strip().lower() in ("si", "sí", "1", "true", "yes"):
        try:
            os.startfile(destino)
            parte.append("  te la he puesto ya.")
        except Exception:
            pass
    return "\n".join(parte)


def main():
    import sys
    print(crear_cancion_ia(sys.argv[1] if len(sys.argv) > 1
                           else "una rumba flamenca alegre", completa="no"))


if __name__ == "__main__":
    main()
