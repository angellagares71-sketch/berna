# -*- coding: utf-8 -*-
r"""
Git para Berna: guardar el trabajo y poder volver atras.

Angel lo pidio el 2026-09-09 junto con el resto de la "opcion code".

POR QUE HACE FALTA, dicho en cristiano
  Programar sin git es trabajar sin red. Berna ya hace copias .bak de cada
  archivo que toca, pero eso no te dice QUE cambio entre el lunes y el martes
  en los ocho archivos del proyecto, ni te deja volver a "como estaba cuando
  funcionaba". Git si.

  Y hay una razon mas: el repositorio de las actualizaciones de Berna (el que
  Angel tiene pendiente de crear en GitHub) se lleva con esto mismo.

COMO ESTA PENSADO
  Las de MIRAR son libres: estado, historial, cambios, ramas. No tocan nada.
  Las de TOCAR piden permiso con la ventana de siempre, ensenando antes que
  archivos entran en el saco:

      git_guardar   -> add + commit (lo mas normal del mundo)
      git_empezar   -> init de un repositorio nuevo
      git_deshacer  -> tirar los cambios que aun no se han guardado
      git_rama      -> crear o cambiar de rama
      git_subir / git_bajar / git_clonar -> hablar con GitHub

  Ninguna reescribe la historia: no hay reset --hard sobre commits ya hechos,
  ni push --force, ni rebase. Eso son las tres formas clasicas de perder
  trabajo de verdad, y no las quiero en manos de nadie que trabaje solo.
"""
import os
import re
import subprocess

BASE = os.path.dirname(os.path.abspath(__file__))
SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
SEGUNDOS = 60
MAX_SALIDA = 9000

IGNORA_NORMAL = (
    "__pycache__/\n*.pyc\nvenv/\n.venv/\n_entorno/\nnode_modules/\n"
    "*.bak-*\n*.anterior\n*.log\n*.lock\n.env\n.env.*\nclaves.json\ntoken.json\n"
)
IGNORA_BERNA = (
    "config.json\nmemoria.json\nperfil.json\ncaras.json\n"
    "oportunidades.json\nvigilancias.json\nrecordatorios.json\ngoogle/\n"
    "biblioteca_pistas.json\nprogramas/\npublicacion/\ncopias/\n"
)


def _tareas():
    import tareas
    return tareas


def _apuntar(que, detalle, resultado=""):
    try:
        _tareas()._apuntar("GIT " + que, detalle, resultado)
    except Exception:
        pass


def _ruta(r):
    return os.path.abspath(os.path.expandvars(os.path.expanduser(str(r or BASE))))


def _corta(t):
    t = t or ""
    return t if len(t) <= MAX_SALIDA else t[:MAX_SALIDA] + "\n[...cortado...]"


def _hay_git():
    try:
        p = subprocess.run(["git", "--version"], capture_output=True, timeout=20,
                           creationflags=SIN_VENTANA)
        return p.returncode == 0
    except Exception:
        return False


def _git(carpeta, *args, **kw):
    """Lanza git y devuelve (codigo, salida). Nunca revienta."""
    if not _hay_git():
        return (127, "En este ordenador no hay git instalado. Se baja de "
                     "git-scm.com; puedo buscartelo con buscar_programa.")
    try:
        p = subprocess.run(["git"] + [str(a) for a in args], cwd=carpeta,
                           capture_output=True, timeout=kw.get("segundos", SEGUNDOS),
                           creationflags=SIN_VENTANA)
    except subprocess.TimeoutExpired:
        return (124, "git ha tardado demasiado y lo he parado.")
    except Exception as e:
        return (1, "No he podido lanzar git: %s" % e)
    t = _tareas()
    return (p.returncode, (t._texto(p.stdout) + t._texto(p.stderr)).strip())


def _es_repo(carpeta):
    codigo, salida = _git(carpeta, "rev-parse", "--is-inside-work-tree")
    return codigo == 0 and salida.strip().startswith("true")


def _raiz(carpeta):
    codigo, salida = _git(carpeta, "rev-parse", "--show-toplevel")
    return salida.strip() if codigo == 0 else carpeta


def _falta_repo(carpeta):
    return ("En %s no hay ningun repositorio de git. Si quieres llevar el "
            "control de los cambios de este proyecto, empiezalo con "
            "git_empezar." % carpeta)


def _gitignore_inicial(carpeta):
    mismo_berna = (os.path.normcase(os.path.abspath(carpeta)) ==
                   os.path.normcase(os.path.abspath(BASE)))
    return IGNORA_NORMAL + (IGNORA_BERNA if mismo_berna else "")


# ================================================================ mirar
def git_estado(carpeta=""):
    """Que hay cambiado ahora mismo y todavia sin guardar."""
    c = _ruta(carpeta)
    if not os.path.isdir(c):
        return "No existe la carpeta %s." % c
    if not _es_repo(c):
        return _falta_repo(c)
    _codigo, rama = _git(c, "rev-parse", "--abbrev-ref", "HEAD")
    _c2, breve = _git(c, "status", "--porcelain")
    if not breve.strip():
        return ("En %s no hay nada pendiente: todo lo que hay esta guardado. "
                "Estas en la rama '%s'." % (_raiz(c), rama.strip()))
    nuevos, tocados, borrados, sueltos = [], [], [], []
    for linea in breve.splitlines():
        marca, nombre = linea[:2], linea[3:].strip()
        if marca == "??":
            sueltos.append(nombre)
        elif "D" in marca:
            borrados.append(nombre)
        elif "A" in marca:
            nuevos.append(nombre)
        else:
            tocados.append(nombre)
    partes = ["En %s, rama '%s':" % (_raiz(c), rama.strip()), ""]
    for titulo, lista in (("Cambiados", tocados), ("Nuevos ya apuntados", nuevos),
                          ("Borrados", borrados),
                          ("Sin apuntar todavia (git no los conoce)", sueltos)):
        if lista:
            partes.append("%s (%d):" % (titulo, len(lista)))
            partes += ["  " + n for n in lista[:30]]
            if len(lista) > 30:
                partes.append("  ...y %d mas" % (len(lista) - 30))
            partes.append("")
    partes.append("Para ver linea a linea que ha cambiado: git_cambios. "
                  "Para guardarlo todo: git_guardar con un mensaje.")
    return _corta("\n".join(partes))


def git_cambios(carpeta="", archivo="", desde=""):
    """Linea a linea, que se ha tocado desde el ultimo guardado."""
    c = _ruta(carpeta)
    if not os.path.isdir(c):
        return "No existe la carpeta %s." % c
    if not _es_repo(c):
        return _falta_repo(c)
    args = ["diff"]
    if desde:
        args.append(re.sub(r"[^\w\.\-/^~]", "", str(desde)))
    args.append("--")
    if archivo:
        args.append(str(archivo))
    codigo, salida = _git(c, *args)
    if codigo != 0:
        return "git no ha podido: %s" % salida
    if not salida.strip():
        codigo2, en_saco = _git(c, "diff", "--cached")
        if en_saco.strip():
            return _corta("Sin cambios sueltos, pero SI hay cosas ya apuntadas "
                          "esperando a guardarse:\n\n" + en_saco)
        return "No hay ningun cambio sin guardar."
    return _corta("Esto es lo que ha cambiado (- lo de antes, + lo de ahora):\n\n"
                  + salida)


def git_historial(carpeta="", cuantos=15, archivo=""):
    """Los ultimos guardados: quien, cuando y que dijo que hacia."""
    c = _ruta(carpeta)
    if not os.path.isdir(c):
        return "No existe la carpeta %s." % c
    if not _es_repo(c):
        return _falta_repo(c)
    try:
        cuantos = max(1, min(100, int(float(cuantos))))
    except Exception:
        cuantos = 15
    args = ["log", "-%d" % cuantos, "--date=format:%d/%m/%Y %H:%M",
            "--pretty=format:%h  %ad  %an: %s"]
    if archivo:
        args += ["--", str(archivo)]
    codigo, salida = _git(c, *args)
    if codigo != 0:
        return ("No hay historial todavia (o git no ha podido): %s" % salida)
    if not salida.strip():
        return "Este repositorio no tiene ningun guardado todavia."
    return _corta("Los ultimos %d guardados de %s:\n\n%s\n\nCada linea empieza "
                  "por su codigo corto; con ese codigo puedes pedirme "
                  "git_cambios(desde=ese_codigo)." % (cuantos, _raiz(c), salida))


def git_ramas(carpeta=""):
    """Que ramas hay y en cual estas."""
    c = _ruta(carpeta)
    if not _es_repo(c):
        return _falta_repo(c)
    codigo, salida = _git(c, "branch", "-a", "-v")
    if codigo != 0:
        return "git no ha podido: %s" % salida
    return _corta("Ramas de %s (la del asterisco es en la que estas):\n\n%s"
                  % (_raiz(c), salida))


# ================================================================ tocar
def git_empezar(carpeta="", permiso=None):
    """Empieza a llevar el control de cambios de una carpeta."""
    c = _ruta(carpeta)
    if not os.path.isdir(c):
        return "No existe la carpeta %s." % c
    if _es_repo(c):
        return ("%s ya lleva control de cambios con git. Mira como esta con "
                "git_estado." % _raiz(c))
    if permiso is None or not permiso(
            "Berna va a EMPEZAR UN CONTROL DE CAMBIOS (git) en:\n\n%s\n\n"
            "Crea una carpeta oculta .git dentro. No cambia ni borra nada de lo "
            "que ya hay, solo permite guardar versiones y volver atras. Le dejas?"
            % c):
        return "No me has dado permiso, no he creado nada."
    codigo, salida = _git(c, "init")
    if codigo != 0:
        return "No he podido: %s" % salida
    # un .gitignore basico, que si no acaba entrando el venv entero
    ignora = os.path.join(c, ".gitignore")
    if not os.path.exists(ignora):
        try:
            with open(ignora, "w", encoding="utf-8") as f:
                f.write(_gitignore_inicial(c))
        except Exception:
            pass
    _apuntar("EMPEZAR", c)
    return ("Listo: %s ya lleva control de cambios. He dejado un .gitignore para "
            "que no se cuelen el entorno de Python ni las claves.\n\nAhora haz el "
            "primer guardado con git_guardar y un mensaje tipo 'primera version'."
            % _raiz(c))


def git_guardar(carpeta="", mensaje="", archivos="", permiso=None):
    """Guarda una version de lo que hay ahora (add + commit)."""
    c = _ruta(carpeta)
    if not os.path.isdir(c):
        return "No existe la carpeta %s." % c
    if not _es_repo(c):
        return _falta_repo(c)
    msg = str(mensaje or "").strip()
    if not msg:
        return ("Dime en una frase que has cambiado. Un guardado sin mensaje no "
                "sirve para nada dentro de tres meses.")
    if len(msg) > 300:
        msg = msg[:300]
    seleccion = [a.strip() for a in re.split(r"[,\n]+", str(archivos or ""))
                 if a.strip()]
    estado_args = ["status", "--porcelain"]
    if seleccion:
        estado_args += ["--"] + seleccion
    _c, breve = _git(c, *estado_args)
    if not breve.strip():
        return ("No hay cambios en los archivos elegidos."
                if seleccion else
                "No hay nada que guardar: esta todo igual que en el ultimo guardado.")
    lista = [l[3:].strip() for l in breve.splitlines()][:30]
    aviso = ("Berna va a GUARDAR UNA VERSION del proyecto:\n\n%s\n\n"
             "Mensaje: %s\n\nEntran estos archivos:\n%s\n\n"
             "Esto no borra nada: guarda una foto de como esta todo ahora, para "
             "poder volver. Le dejas?"
             % (_raiz(c), msg, "\n".join("  " + n for n in lista)))
    if permiso is None or not permiso(aviso):
        return "No me has dado permiso, no he guardado nada."
    if seleccion:
        codigo_add, salida_add = _git(c, "add", "--", *seleccion)
    else:
        codigo_add, salida_add = _git(c, "add", "-A")
    if codigo_add != 0:
        return ("No he guardado nada porque git no ha podido preparar los "
                "archivos: %s" % salida_add)
    # Con una seleccion, --only impide que entren por accidente otros archivos
    # que ya estuvieran preparados de antes.
    commit_args = ["commit", "-m", msg]
    if seleccion:
        commit_args += ["--only", "--"] + seleccion
    codigo, salida = _git(c, *commit_args)
    _apuntar("GUARDAR", "%s: %s" % (c, msg), "codigo %s" % codigo)
    if codigo != 0:
        if "user.email" in salida or "user.name" in salida:
            return ("Git no sabe todavia quien eres y por eso no guarda. Dime tu "
                    "nombre y tu correo y te lo configuro yo con ejecutar_orden:\n"
                    "  git config --global user.name \"Angel\"\n"
                    "  git config --global user.email \"tu@correo\"")
        return "No he podido guardar: %s" % salida
    return _corta("Guardado.\n\n%s\n\nSi te arrepientes, el historial esta en "
                  "git_historial y siempre puedes volver." % salida)


def git_deshacer(carpeta="", archivo="", permiso=None):
    """Tira los cambios que AUN NO se han guardado y vuelve al ultimo guardado.

    Solo toca lo no guardado. La historia ya guardada no se reescribe nunca
    desde aqui: eso es la unica forma segura de que Berna no borre trabajo.
    """
    c = _ruta(carpeta)
    if not _es_repo(c):
        return _falta_repo(c)
    _cod, breve = _git(c, "status", "--porcelain")
    if not breve.strip():
        return "No hay nada sin guardar, no hay nada que deshacer."
    que = ("el archivo %s" % archivo) if archivo else "TODOS los archivos cambiados"
    aviso = ("Berna va a TIRAR LOS CAMBIOS SIN GUARDAR de %s en:\n\n%s\n\n"
             "Vuelve a como estaba en el ultimo guardado. LO DE DESPUES SE "
             "PIERDE y no hay vuelta atras.\n\nAsi esta la cosa ahora:\n%s\n\n"
             "Seguro?" % (que, _raiz(c), breve[:1200]))
    if permiso is None or not permiso(aviso):
        return "No me has dado permiso, no he deshecho nada."
    objetivo = str(archivo) if archivo else "."
    # checkout solo devolvia la copia preparada y dejaba vivos los cambios del
    # area de preparacion. restore con HEAD limpia las dos capas de verdad.
    codigo, salida = _git(c, "restore", "--source=HEAD", "--staged",
                          "--worktree", "--", objetivo)
    _apuntar("DESHACER", "%s %s" % (c, archivo or "(todo)"), "codigo %s" % codigo)
    if codigo != 0:
        return "No he podido: %s" % salida
    return ("Deshecho. %s vuelve a estar como en el ultimo guardado.\n\nOjo: los "
            "archivos que git no conocia (los que salian como 'sin apuntar') "
            "siguen ahi, esos no los toco." % que.capitalize())


def git_rama(carpeta="", nombre="", crear=False, permiso=None):
    """Cambia de rama, o crea una nueva para trastear sin romper lo que funciona."""
    c = _ruta(carpeta)
    if not _es_repo(c):
        return _falta_repo(c)
    n = re.sub(r"[^A-Za-z0-9_\-/\.]", "", str(nombre or "")).strip("/")
    if not n:
        return "Dime como se llama la rama. Si solo quieres verlas, usa git_ramas."
    crear = str(crear).lower() in ("true", "si", "1", "yes")
    if permiso is None or not permiso(
            "Berna va a %s la rama '%s' en:\n\n%s\n\n%s Le dejas?"
            % ("CREAR Y PASARSE A" if crear else "CAMBIARSE A", n, _raiz(c),
               "Una rama es una copia del trabajo donde puedes probar cosas sin "
               "estropear la buena." if crear else
               "Los archivos de la carpeta van a cambiar a como estan en esa rama.")):
        return "No me has dado permiso, no he cambiado de rama."
    codigo, salida = _git(c, "checkout", "-b", n) if crear else _git(c, "checkout", n)
    _apuntar("RAMA", "%s -> %s" % (c, n), "codigo %s" % codigo)
    if codigo != 0:
        return "No he podido: %s" % salida
    return "Ahora estas en la rama '%s'.\n\n%s" % (n, salida)


def git_bajar(carpeta="", permiso=None):
    """Trae de internet lo que haya nuevo en el repositorio (pull)."""
    c = _ruta(carpeta)
    if not _es_repo(c):
        return _falta_repo(c)
    if permiso is None or not permiso(
            "Berna va a TRAER DE INTERNET los cambios del repositorio en:\n\n%s\n\n"
            "Puede cambiar archivos de esa carpeta. Hace falta internet. Le dejas?"
            % _raiz(c)):
        return "No me has dado permiso, no he bajado nada."
    codigo, salida = _git(c, "pull", segundos=180)
    _apuntar("BAJAR", c, "codigo %s" % codigo)
    if codigo != 0:
        return ("No he podido bajarlo: %s\n\nSi habla de conflictos es que hay "
                "cambios tuyos que chocan con los de fuera; guarda los tuyos "
                "primero con git_guardar." % salida)
    return _corta("Bajado:\n\n%s" % salida)


def git_subir(carpeta="", permiso=None):
    """Sube a internet lo que has guardado (push).

    Publicar es de las cosas que no se deshacen: una vez fuera, esta fuera. Por
    eso el aviso dice a donde va y con que cuenta, y nunca se fuerza.
    """
    c = _ruta(carpeta)
    if not _es_repo(c):
        return _falta_repo(c)
    _cod, remoto = _git(c, "remote", "-v")
    if not remoto.strip():
        return ("Este repositorio no esta enlazado con ningun sitio de internet, "
                "asi que no hay a donde subirlo. En C:\\Asistente tienes "
                "'Enlazar-con-GitHub.bat' para eso.")
    _c2, rama = _git(c, "rev-parse", "--abbrev-ref", "HEAD")
    _c3, pendientes = _git(c, "log", "--oneline", "@{u}..HEAD")
    if permiso is None or not permiso(
            "Berna va a SUBIR A INTERNET el trabajo guardado:\n\n%s\n\nRama: %s\n"
            "Va a:\n%s\n\nGuardados que se suben:\n%s\n\n"
            "OJO: lo que se sube queda publicado y ya no se puede 'des-subir'. "
            "Mira que no haya claves ni datos tuyos dentro. Le dejas?"
            % (_raiz(c), rama.strip(), remoto.strip()[:500],
               pendientes.strip()[:800] or "(no se cuales, mira git_historial)")):
        return "No me has dado permiso, no he subido nada."
    codigo, salida = _git(c, "push", segundos=300)
    _apuntar("SUBIR", c, "codigo %s" % codigo)
    if codigo != 0:
        return ("No he podido subirlo: %s\n\nSi pide usuario y contrasena, eso lo "
                "tienes que poner tu: yo no meto claves en ningun sitio." % salida)
    return _corta("Subido:\n\n%s" % salida)


def git_clonar(url, destino="", permiso=None):
    """Se trae un proyecto entero de internet para poder mirarlo o trabajarlo."""
    u = str(url or "").strip()
    if not re.match(r"^(https://|git@)[\w\.\-@:/~]+$", u):
        return ("Esa direccion no me cuadra. Tiene que ser algo como "
                "https://github.com/alguien/proyecto.git")
    d = _ruta(destino) if destino else os.path.join(BASE, "programas")
    if not os.path.isdir(d):
        try:
            os.makedirs(d, exist_ok=True)
        except Exception as e:
            return "No he podido preparar la carpeta: %s" % e
    nombre = re.sub(r"\.git$", "", u.rstrip("/").split("/")[-1])
    if os.path.isdir(os.path.join(d, nombre)):
        return ("Ya hay una carpeta '%s' dentro de %s. Ponle otro destino o mira "
                "la que hay." % (nombre, d))
    if permiso is None or not permiso(
            "Berna va a TRAERSE UN PROYECTO ENTERO de internet:\n\n%s\n\n"
            "Lo deja en:\n%s\n\nDescarga codigo de otra gente: no lo ejecutes sin "
            "mirarlo antes. Le dejas?" % (u, os.path.join(d, nombre))):
        return "No me has dado permiso, no he descargado nada."
    codigo, salida = _git(d, "clone", u, segundos=600)
    _apuntar("CLONAR", u, "codigo %s" % codigo)
    if codigo != 0:
        return "No he podido traerlo: %s" % salida
    return ("Traido en %s.\n\n%s\n\nAntes de ejecutar nada de ahi dentro, mira "
            "que es con arbol_de_carpeta y revisar_proyecto."
            % (os.path.join(d, nombre), salida[-800:]))
