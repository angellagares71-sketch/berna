# -*- coding: utf-8 -*-
r"""
Como se llama el asistente, y el paso de Berna a Sobri.

Angel lo pidio el 2026-09-15: "cambiale el nombre a mi asistente Berna y ponle
Sobri, tanto en el movil como en el ordenador, como en todo el mundo que se lo
haya descargado".

POR QUE HACE FALTA ESTE MODULO
  El actualizador solo cambia ARCHIVOS del programa. No toca config.json de
  nadie (ahi van sus claves) ni renombra accesos directos. Asi que en el PC de
  cualquiera que actualice seguiria poniendo "Te llamas Berna" en su
  personalidad, y le seguiria despertando "Oye Berna". Esto lo arregla UNA sola
  vez, al arrancar la version nueva:

    - Si su nombre para llamarle sigue siendo Berna, pasa a Sobri. Si alguien
      le puso otro nombre a proposito, se respeta.
    - En la personalidad, Berna pasa a Sobri.
    - "Berna" se queda como nombre viejo: le sigue despertando un tiempo, para
      quien tenga la costumbre (lo eligio Angel).
    - El acceso directo del escritorio y el del arranque de Windows pasan a
      llamarse Sobri, y la carpeta Imagenes\Berna pasa a Imagenes\Sobri.
    - Los .bat con el nombre viejo que dejo la version anterior se apartan a
      copias\, no se borran.

  Lo que NO cambia a proposito, y el motivo, esta en el LEEME: la clase interna
  Berna, la cabecera X-Berna, el paquete del movil y el repositorio.

"SOBRI" SUENA A "SOBRE", Y ESO SE MIDIO (15-09-2026)
  Para Whisper, "Sobri" y "sobre" son la misma palabra: sin pista, de 16
  llamadas "Oye Sobri" solo reconocio el nombre 2. Con la pista de siempre
  ("Sobri. Oye Sobri.") lo oye 16 de 16, pero se INVENTA el nombre: "Oye, sobre
  lo de ayer" salia "Oye Sobri. Oye Sobri." y "Hoy estoy sobrio", "Oye Sobri".
  Se desperto solo 8 veces de 24 frases trampa. Dandole en la pista tambien las
  palabras con las que se confunde, lo oye 16 de 16 y se despierta solo 1 de
  24, a la misma velocidad. El modelo "small" daba 3 de 24 y tardaba el triple.
"""
import os
import re
import shutil

BASE = os.path.dirname(os.path.abspath(__file__))
NOMBRE = "Sobri"
VIEJO = "Berna"

# Las palabras corrientes con las que Whisper confunde el nombre. Van en la
# pista para que las sepa distinguir, y en la lista de las que no despiertan.
PARECIDAS = {
    "sobri": ("sobre", "sobra", "sobrio", "pobre"),
}
NO_DESPIERTAN = frozenset((
    "sobre", "sobres", "sobra", "sobras", "sobran", "sobro", "sobrio", "sobria",
    "pobre", "pobres", "cobre", "cobra",
))


def pista_para_whisper(nombre):
    """El initial_prompt para oir el nombre sin inventarselo."""
    n = str(nombre or NOMBRE).strip() or NOMBRE
    pista = "%s. Oye %s. Hola %s." % (n, n, n)
    parecidas = PARECIDAS.get(n.lower())
    if parecidas:
        pista += " " + ", ".join(p.capitalize() if i == 0 else p
                                 for i, p in enumerate(parecidas)) + "."
    return pista


def nombres_para_despertar(cfg):
    """El nombre de ahora y los viejos que siguen valiendo, sin repetir."""
    fuera = []
    for n in [cfg.get("palabra_magica") or NOMBRE] + list(cfg.get("nombres_viejos") or []):
        n = str(n or "").strip()
        if n and n.lower() not in [x.lower() for x in fuera]:
            fuera.append(n)
    return fuera


# ------------------------------------------------------------------ el paso
def _escritorio():
    try:
        import taller
        return taller.escritorio()
    except Exception:
        return os.path.join(os.path.expanduser("~"), "Desktop")


def _es_acceso_a_este_programa(lnk):
    """Si un .lnk arranca ESTE asistente, mirando dentro sin abrir nada.

    Un .lnk guarda las rutas en utf-16 (y a veces tambien en ansi). Basta con
    ver que dentro aparece asistente.py: asi no se renombra un "Berna.lnk" que
    sea otra cosa que tuviera la persona.
    """
    try:
        with open(lnk, "rb") as f:
            crudo = f.read(64 * 1024)
    except OSError:
        return False
    aguja = "asistente.py"
    bajo = crudo.lower()          # bytes.lower() solo toca A-Z: vale para las dos
    return aguja.encode("utf-16-le") in bajo or aguja.encode("ascii") in bajo


def _renombrar_acceso(carpeta, hecho):
    viejo = os.path.join(carpeta, VIEJO + ".lnk")
    nuevo = os.path.join(carpeta, NOMBRE + ".lnk")
    if not os.path.isfile(viejo) or os.path.exists(nuevo):
        return
    if not _es_acceso_a_este_programa(viejo):
        return
    try:
        os.replace(viejo, nuevo)
        hecho.append("acceso directo en %s" % carpeta)
    except OSError:
        pass


def migrar(cfg, guardar, anotar=lambda _t: None):
    """El paso de Berna a Sobri, una sola vez. Devuelve el aviso o None.

    `guardar(cambios)` escribe SOLO esas claves en config.json (atomico). Se
    llama igual desde los dos procesos con los que arranca la ventana: todo lo
    de aqui aguanta hacerse dos veces a la vez.
    """
    if cfg.get("nombre_migrado") == NOMBRE:
        return None
    era_berna = str(cfg.get("palabra_magica") or VIEJO).strip().lower() == VIEJO.lower()
    cambios = {"nombre_migrado": NOMBRE}
    if era_berna:
        cambios["palabra_magica"] = NOMBRE
        viejos = [n for n in (cfg.get("nombres_viejos") or []) if n]
        if VIEJO not in viejos:
            viejos.append(VIEJO)
        cambios["nombres_viejos"] = viejos
        pers = cfg.get("personalidad")
        if isinstance(pers, str) and re.search(r"\b%s\b" % VIEJO, pers):
            cambios["personalidad"] = re.sub(r"\b%s\b" % VIEJO, NOMBRE, pers)
    cfg.update(cambios)
    try:
        guardar(cambios)
    except Exception as e:
        anotar("no he podido guardar el cambio de nombre: %s" % e)

    hecho = []
    if era_berna:
        _renombrar_acceso(_escritorio(), hecho)
        inicio = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows",
                              "Start Menu", "Programs", "Startup")
        if os.path.isdir(inicio):
            _renombrar_acceso(inicio, hecho)
        fotos_viejas = os.path.join(os.path.expanduser("~"), "Pictures", VIEJO)
        fotos_nuevas = os.path.join(os.path.expanduser("~"), "Pictures", NOMBRE)
        if os.path.isdir(fotos_viejas) and not os.path.exists(fotos_nuevas):
            try:
                os.rename(fotos_viejas, fotos_nuevas)
                hecho.append("Imagenes\\%s" % NOMBRE)
            except OSError as e:
                anotar("no he podido renombrar Imagenes\\%s: %s" % (VIEJO, e))
    # los .bat que dejo la version anterior, si ya esta el nuevo
    for viejo_bat, nuevo_bat in (("Berna-Movil.bat", "Sobri-Movil.bat"),
                                 ("Publicar Berna.bat", "Publicar Sobri.bat")):
        v = os.path.join(BASE, viejo_bat)
        if os.path.isfile(v) and os.path.isfile(os.path.join(BASE, nuevo_bat)):
            try:
                apartado = os.path.join(BASE, "copias", "nombre-berna")
                os.makedirs(apartado, exist_ok=True)
                shutil.move(v, os.path.join(apartado, viejo_bat))
            except OSError:
                pass
    anotar("cambio de nombre a %s hecho (%s)" % (NOMBRE, ", ".join(hecho) or "solo ajustes"))
    if not era_berna:
        return None
    return ("Desde hoy me llamo %s. Para llamarme di «Oye, %s»; si se te escapa "
            "«Oye, %s», tambien te hago caso." % (NOMBRE, NOMBRE, VIEJO))
