# -*- coding: utf-8 -*-
r"""
Berna actualizandose solo por internet.

Angel lo pidio el 2026-08-27: que cualquiera que tenga a Berna pueda ponerlo
al dia desde el desplegable de la ventana, sin pen y sin que nadie le toque el
ordenador.

COMO FUNCIONA
  En un repositorio de GitHub hay un `version.json` con el numero de version,
  las novedades y la lista de archivos con su SHA256. Berna se lo baja, compara
  con lo que tiene, le ENSENA a la persona que va a cambiar, y solo si dice que
  si se baja los archivos, los comprueba uno a uno, guarda copia de los viejos
  y los cambia.

POR QUE ESTA TAN ATADO, QUE NO ES MANIA
  Berna teclea, pincha, ejecuta ordenes de consola y entra en las cuentas de
  quien lo use. Un canal de actualizacion es la llave de todo eso: quien
  controle el sitio de donde se baja, controla el ordenador de todo el que se
  actualice. Por eso:

  1. **Solo se baja de GitHub.** El host esta clavado en el codigo. Aunque
     alguien le meta otra direccion en el config.json, no la sigue. Es la
     defensa contra el clasico "cambiale la url y ya es tuyo".
  2. **Solo se tocan archivos del programa**, y con el nombre pelado: nada de
     rutas, ni de `..`, ni de unidades. Un manifiesto envenenado no puede
     escribir en `C:\Windows`.
  3. **Nunca se toca lo que es de la persona:** ni el config.json, ni las
     claves, ni la memoria, ni el perfil, ni las caras, ni sus programas.
  4. **Todo .py que entra se COMPILA antes de instalarse.** Si no compila, no
     se instala nada. Es lo que evita dejar a alguien con un Berna roto y sin
     ventana desde la que arreglarlo.
  5. **Copia de seguridad de todo lo que se cambia** en `copias\<fecha>`, y
     `volver_atras()` para deshacerlo.
  6. **Lo aprueba la persona**, en una ventana que dice que archivos cambian.
     Nunca se actualiza sola al arrancar. Lo eligio Angel a proposito.

  Lo que esto NO arregla, y hay que decirlo claro: si alguien le roba a Angel
  la cuenta de GitHub y publica una version mala, la firma cuadra y la version
  parece buena. Contra eso la unica defensa real es la ventana de permiso y que
  la cuenta tenga verificacion en dos pasos.
"""
import os, re, io, json, time, shutil, hashlib, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
COPIAS = os.path.join(BASE, "copias")

# ---------------------------------------------------------------- la version
# Sube esto cada vez que se publique algo. Es lo que se compara con el
# version.json del repositorio para saber si hay novedades.
VERSION = "1.3.0"
FECHA_VERSION = "2026-08-27"

# Solo de aqui se baja nada. Clavado a proposito: ver el punto 1 de arriba.
HOST = "https://raw.githubusercontent.com"
RAMA = "main"

# El repositorio de donde se baja todo el mundo, en formato usuario/proyecto.
# VA AQUI Y NO EN EL config.json a proposito: asi viaja DENTRO del programa y
# quien reciba a Berna no tiene que configurar nada para poder actualizarse.
# El config.json solo puede pisarlo, y eso es para probar.
REPOSITORIO = "angellagares71-sketch/berna"

ESPERA = 25
MAX_BYTES_ARCHIVO = 5 * 1024 * 1024      # ningun .py de Berna llega a 100 KB


# ------------------------------------------------------------------ ajustes
def _cfg():
    try:
        with io.open(os.path.join(BASE, "config.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _repositorio():
    """Cual es el repositorio, en formato 'usuario/proyecto'.

    Manda el config.json si lo han puesto, y si no el que viene dentro del
    programa. Asi el que reciba a Berna se actualiza sin tocar nada.
    """
    r = str(_cfg().get("repositorio") or REPOSITORIO or "").strip().strip("/")
    # Si le han pegado la url entera del navegador, se le quita la paja.
    r = re.sub(r"^https?://(www\.)?github\.com/", "", r, flags=re.I)
    r = re.sub(r"\.git$", "", r)
    return r if re.match(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$", r) else ""


# ------------------------------------------------- que se puede y que no
# Lo que es de la persona y NO se toca nunca, aunque venga en el manifiesto.
INTOCABLES = {
    "config.json", "memoria.json", "perfil.json", "caras.json",
    "oportunidades.json", "gpt_secret_key.txt", "berna.log",
}
CARPETAS_INTOCABLES = {"google", "voces", "tareas", "programas", "modelos",
                       "copias", "venv", "__pycache__", "imagenes"}

# Y lo unico que SI puede venir en una actualizacion.
EXTENSIONES = (".py", ".txt", ".bat")


def _nombre_seguro(nombre):
    """Devuelve el motivo por el que NO vale, o None si vale.

    Aqui se para el ataque de 'archivo': '..\\..\\Windows\\algo.py'.
    """
    n = str(nombre or "").strip()
    if not n:
        return "viene un archivo sin nombre"
    if n != os.path.basename(n):
        return "'%s' lleva ruta, y solo se aceptan nombres pelados" % n
    if n.startswith(".") or ".." in n:
        return "'%s' no es un nombre normal" % n
    if os.path.isabs(n) or ":" in n or "\\" in n or "/" in n:
        return "'%s' apunta fuera de la carpeta del programa" % n
    if not n.lower().endswith(EXTENSIONES):
        return "'%s' no es un archivo del programa" % n
    if n.lower() in INTOCABLES:
        return "'%s' es tuyo y no se toca en una actualizacion" % n
    if n.split(os.sep)[0].lower() in CARPETAS_INTOCABLES:
        return "'%s' esta en una carpeta que no se toca" % n
    return None


def _sha256(ruta):
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for trozo in iter(lambda: f.read(65536), b""):
            h.update(trozo)
    return h.hexdigest()


def _sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def _version_como_numeros(v):
    """'1.10.2' -> (1, 10, 2). Para que 1.10 sea MAS que 1.9, que si se
    comparan como texto sale al reves y no se entera nadie."""
    try:
        return tuple(int(x) for x in re.findall(r"\d+", str(v))[:4]) or (0,)
    except Exception:
        return (0,)


# ------------------------------------------------------------ mirar si hay
def _bajar(url, maximo=MAX_BYTES_ARCHIVO):
    import requests
    r = requests.get(url, timeout=ESPERA,
                     headers={"User-Agent": "Berna/%s" % VERSION})
    if r.status_code == 404:
        raise ValueError("no existe (404)")
    if r.status_code != 200:
        raise ValueError("el servidor ha contestado %s" % r.status_code)
    if len(r.content) > maximo:
        raise ValueError("ocupa mas de la cuenta (%d bytes)" % len(r.content))
    return r.content


def _manifiesto():
    """Se baja el version.json del repositorio. Devuelve (datos, error)."""
    repo = _repositorio()
    if not repo:
        return None, ("Todavia no esta puesto de donde bajarse las "
                      "actualizaciones. Se hace UNA vez y lo cuenta paso a paso "
                      "el archivo ACTUALIZACIONES-COMO-ACTIVARLO.txt que hay en "
                      "la carpeta de Berna.")
    url = "%s/%s/%s/version.json" % (HOST, repo, RAMA)
    try:
        crudo = _bajar(url, 200 * 1024)
    except Exception as e:
        return None, ("No he podido mirar si hay actualizaciones: %s. "
                      "Mira si hay internet y si el repositorio '%s' existe y es "
                      "publico." % (e, repo))
    try:
        d = json.loads(crudo.decode("utf-8"))
    except Exception as e:
        return None, "El archivo de versiones esta mal escrito: %s" % e
    if not isinstance(d, dict) or "version" not in d or "archivos" not in d:
        return None, "El archivo de versiones no tiene la forma que espero."
    return d, None


def version_actual():
    """Que version tiene puesta este Berna."""
    return "Berna version %s, del %s.%s" % (
        VERSION, FECHA_VERSION,
        ("" if _repositorio() else
         " Todavia no esta configurado de donde bajarse las actualizaciones; "
         "lo cuenta el archivo ACTUALIZACIONES-COMO-ACTIVARLO.txt."))


def buscar_actualizaciones():
    """Mira si hay version nueva. NO instala nada: solo mira y lo cuenta."""
    d, error = _manifiesto()
    if error:
        return error

    nueva = str(d.get("version", "?"))
    if _version_como_numeros(nueva) <= _version_como_numeros(VERSION):
        return ("Berna ya esta al dia: tienes la version %s y la ultima "
                "publicada es la %s." % (VERSION, nueva))

    cambios, motivos = _que_cambia(d)
    l = ["HAY UNA VERSION NUEVA DE BERNA",
         "",
         "Tienes la %s y hay publicada la %s, del %s."
         % (VERSION, nueva, d.get("fecha", "?")), ""]
    novedades = d.get("novedades") or []
    if novedades:
        l.append("Lo que trae:")
        for n in novedades[:12]:
            l.append("  - " + str(n)[:200])
        l.append("")
    if cambios:
        l.append("Archivos que cambiarian (%d): %s"
                 % (len(cambios), ", ".join(sorted(cambios))))
    else:
        l.append("Curiosamente no cambia ningun archivo. Raro.")
    if motivos:
        l.append("")
        l.append("Y esto lo voy a dejar en paz:")
        for m in motivos[:8]:
            l.append("  - " + m)
    l.append("")
    l.append("No he instalado nada todavia. Preguntale si quiere que se la "
             "ponga, y si dice que si usa instalar_actualizacion.")
    return "\n".join(l)


def _que_cambia(d):
    """Devuelve (archivos que hay que cambiar, motivos de los descartados)."""
    cambios, motivos = [], []
    for nombre, info in (d.get("archivos") or {}).items():
        pega = _nombre_seguro(nombre)
        if pega:
            motivos.append(pega)
            continue
        firma = str((info or {}).get("sha256") or "").lower()
        if not re.match(r"^[0-9a-f]{64}$", firma):
            motivos.append("'%s' viene sin una firma en condiciones" % nombre)
            continue
        mio = os.path.join(BASE, nombre)
        if os.path.isfile(mio) and _sha256(mio) == firma:
            continue                      # ya lo tengo igual
        cambios.append(nombre)
    return cambios, motivos


# ------------------------------------------------------------- instalarla
def instalar_actualizacion(permiso=None):
    """Se baja la version nueva, la comprueba entera y la instala.

    El orden importa: primero se baja TODO y se comprueba TODO, y solo cuando
    esta todo bien se toca la carpeta. Asi no se queda nadie a medias.
    """
    d, error = _manifiesto()
    if error:
        return error

    nueva = str(d.get("version", "?"))
    if _version_como_numeros(nueva) <= _version_como_numeros(VERSION):
        return "No hay nada que instalar: ya tienes la %s." % VERSION

    cambios, motivos = _que_cambia(d)
    if not cambios:
        return ("La version publicada es la %s pero no cambia ningun archivo "
                "que yo pueda tocar. No hago nada." % nueva)

    repo = _repositorio()
    aviso = ("Berna se va a ACTUALIZAR por internet.\n\n"
             "De la version %s a la %s.\n"
             "Se baja de: github.com/%s\n\n"
             "Archivos que cambian (%d):\n  %s\n\n"
             "%s"
             "Se guarda copia de los actuales antes de tocarlos, y se puede "
             "deshacer. NO se toca tu configuracion, ni tus claves, ni tu "
             "memoria, ni tus programas.\n\n"
             "Al terminar hay que cerrar Berna y volverlo a abrir.\n\nLe dejas?"
             % (VERSION, nueva, repo, len(cambios),
                "\n  ".join(sorted(cambios)),
                ("Novedades: " + "; ".join(str(x) for x in (d.get("novedades") or [])[:5])
                 + "\n\n") if d.get("novedades") else ""))
    if permiso is None or not permiso(aviso):
        _apuntar("SIN PERMISO", "actualizar a " + nueva, "ha dicho que no")
        return "No me han dado permiso, no he tocado nada."

    # 1) bajarlo todo a un lado, sin tocar la carpeta buena
    bajados = {}
    for nombre in cambios:
        url = "%s/%s/%s/%s" % (HOST, repo, RAMA, nombre)
        try:
            crudo = _bajar(url)
        except Exception as e:
            return ("Me he quedado a medias bajando '%s': %s. No he cambiado "
                    "nada, sigues con la %s." % (nombre, e, VERSION))
        firma = str(d["archivos"][nombre]["sha256"]).lower()
        if _sha256_bytes(crudo) != firma:
            _apuntar("ACTUALIZAR", nombre, "la firma no cuadra")
            return ("El archivo '%s' no coincide con su firma. O se ha bajado "
                    "mal o alguien lo ha cambiado por el camino. No instalo "
                    "nada." % nombre)
        bajados[nombre] = crudo

    # 2) que todo el codigo que entra COMPILE. Sin esto, una version mala deja
    #    a la persona sin ventana desde la que arreglarlo.
    for nombre, crudo in bajados.items():
        if not nombre.lower().endswith(".py"):
            continue
        try:
            compile(crudo.decode("utf-8"), nombre, "exec")
        except Exception as e:
            _apuntar("ACTUALIZAR", nombre, "no compila: %s" % e)
            return ("El archivo '%s' que me he bajado tiene un fallo de "
                    "programacion (%s). No instalo nada: prefiero dejarte con la "
                    "version %s que dejarte con Berna roto." % (nombre, e, VERSION))

    # 3) copia de seguridad y cambiazo
    sello = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    carpeta_copia = os.path.join(COPIAS, sello)
    try:
        os.makedirs(carpeta_copia, exist_ok=True)
    except Exception as e:
        return "No he podido preparar la copia de seguridad: %s" % e

    puestos, fallidos = [], []
    for nombre, crudo in bajados.items():
        destino = os.path.join(BASE, nombre)
        try:
            if os.path.isfile(destino):
                shutil.copy2(destino, os.path.join(carpeta_copia, nombre))
            with open(destino, "wb") as f:
                f.write(crudo)
            puestos.append(nombre)
        except Exception as e:
            fallidos.append("%s (%s)" % (nombre, e))

    if fallidos and puestos:
        _volver(carpeta_copia)
        _apuntar("ACTUALIZAR", nueva, "fallo a medias, deshecho")
        return ("Se me ha atragantado %s, asi que lo he dejado todo como "
                "estaba. Sigues con la %s." % (fallidos[0], VERSION))
    if fallidos:
        return "No he podido escribir ningun archivo: %s" % fallidos[0]

    with io.open(os.path.join(carpeta_copia, "_de-que-version-venia.txt"),
                 "w", encoding="utf-8") as f:
        f.write("Copia hecha al actualizar de la %s a la %s el %s.\n"
                % (VERSION, nueva, sello))
    _apuntar("ACTUALIZAR", "%s -> %s" % (VERSION, nueva),
             "%d archivos" % len(puestos))

    return ("ACTUALIZADO a la version %s. He cambiado %d archivos (%s) y he "
            "guardado los viejos en copias\\%s por si acaso.\n\n"
            "IMPORTANTE: hay que cerrar Berna y volverlo a abrir para que se "
            "note. Diselo asi, que es lo unico que tiene que hacer. Si algo va "
            "raro despues, se puede deshacer."
            % (nueva, len(puestos), ", ".join(sorted(puestos)), sello))


# --------------------------------------------------------------- deshacer
def _volver(carpeta_copia):
    vueltos = 0
    for nombre in os.listdir(carpeta_copia):
        if nombre.startswith("_"):
            continue
        try:
            shutil.copy2(os.path.join(carpeta_copia, nombre),
                         os.path.join(BASE, nombre))
            vueltos += 1
        except Exception:
            pass
    return vueltos


def volver_atras(permiso=None):
    """Deshace la ultima actualizacion."""
    if not os.path.isdir(COPIAS):
        return "No hay ninguna copia guardada, asi que no hay nada que deshacer."
    copias = sorted([d for d in os.listdir(COPIAS)
                     if os.path.isdir(os.path.join(COPIAS, d))])
    if not copias:
        return "No hay ninguna copia guardada."
    ultima = copias[-1]
    carpeta = os.path.join(COPIAS, ultima)
    archivos = [n for n in os.listdir(carpeta) if not n.startswith("_")]

    aviso = ("Berna va a DESHACER la ultima actualizacion.\n\n"
             "Vuelve a como estaba el %s, cambiando %d archivos:\n  %s\n\n"
             "Despues hay que cerrarlo y volverlo a abrir.\n\nLe dejas?"
             % (ultima, len(archivos), "\n  ".join(sorted(archivos))))
    if permiso is None or not permiso(aviso):
        return "No me han dado permiso, lo dejo como esta."

    n = _volver(carpeta)
    _apuntar("ACTUALIZAR", "volver atras a " + ultima, "%d archivos" % n)
    return ("Deshecho: he devuelto %d archivos a como estaban el %s. Cierra "
            "Berna y vuelvelo a abrir." % (n, ultima))


def _apuntar(que, detalle, resultado):
    try:
        import tareas
        tareas._apuntar(que, detalle, resultado)
    except Exception:
        pass
