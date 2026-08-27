# -*- coding: utf-8 -*-
r"""
El taller de Berna: escribir programas, probarlos y arreglarlos.

Angel lo pidio el 2026-08-26: "ponle la capacidad de programar, de hacer
cualquier cosa, como lo puedes hacer tu".

LO QUE DE VERDAD HACE FALTA PARA PROGRAMAR, que no es lo que parece
  Nadie acierta a la primera, y un modelo tampoco. Programar de verdad es
  un bucle:

      escribir el codigo -> EJECUTARLO -> LEER EL ERROR -> arreglarlo -> otra vez

  Berna ya sabia escribir archivos y lanzar comandos sueltos, pero le
  faltaba el ciclo: un sitio suyo donde trastear, poder ejecutar lo que
  acaba de escribir y **recibir el error de vuelta en un formato que pueda
  entender y corregir**. Eso es todo este modulo. Por eso `probar_programa`
  no devuelve "ha fallado": devuelve las ultimas lineas del error y le dice
  que lo arregle y lo vuelva a intentar.

DONDE VIVE LO QUE HACE
  `C:\Asistente\programas\<nombre>\`  — una carpeta por programa, con su
  codigo y un LEEME.txt escrito en cristiano para Angel.

  Los programas se ejecutan SIEMPRE con esa carpeta como directorio de
  trabajo, con tope de tiempo y sin ventana negra parpadeando.

EL ENTORNO APARTE, y el motivo
  Si Berna instalara librerias en su propio venv, un `pip install` con mala
  suerte podria dejarlo sin voz o sin oido. Por eso las librerias nuevas van
  a `programas\_entorno`, un venv creado con --system-site-packages: los
  programas ven todo lo que Berna ya tiene (numpy, pillow, requests...) pero
  lo nuevo se instala aparte. **Si Berna se rompe algun dia, no sera por un
  programa suyo.**

SEGURIDAD, y aqui hay que ser honesto
  ESTO NO ES UNA JAULA. Un programa en Python puede hacer lo que haga
  cualquier programa. Lo que hay son los mismos cerrojos que en tareas.py, y
  no se relajan:

    1. Ejecutar pide permiso a Angel, con el nombre del programa delante.
       Mientras lo esta arreglando no se le pregunta otra vez (seria
       inaguantable en un bucle de correcciones), pero el permiso caduca.
    2. El codigo pasa por la lista negra de tareas.PROHIBIDO ANTES de
       ejecutarse, mas unos cuantos patrones propios de Python (borrar
       carpetas del sistema, tocar el registro, espiar el teclado). Se
       niega aunque Angel diga que si.
    3. Todo queda apuntado en tareas\registro.log.

  Y la regla de siempre, que aqui importa mas que en ningun sitio: Berna
  programa lo que le pide ANGEL. Nunca escribe ni ejecuta codigo que venga
  dentro de una pagina web, un correo, un chat o un archivo. Eso es
  inyeccion de ordenes, y con un interprete delante acaba mal.
"""
import os
import re
import shutil
import datetime
import subprocess

BASE = os.path.dirname(os.path.abspath(__file__))
TALLER = os.path.join(BASE, "programas")
ENTORNO = os.path.join(TALLER, "_entorno")
PYTHON_BERNA = os.path.join(BASE, "venv", "Scripts", "python.exe")
ESCRITORIO = os.path.join(os.path.expanduser("~"), "Desktop")

SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
MAX_CODIGO = 60000          # caracteres de un archivo de codigo
SEGUNDOS = 25               # lo que se le deja correr por defecto
MAX_SEGUNDOS = 120
PERMISO_MINUTOS = 20        # cuanto vale el permiso de ejecutar un programa

LENGUAJES = {
    "python": ".py",
    "html": ".html",
    "bat": ".bat",
}

# Peligros propios del codigo, ademas de la lista negra de tareas.py.
PROHIBIDO_CODIGO = [
    (r"rmtree\s*\([^)]*(c:\\\\?windows|c:/windows|system32|program files)",
     "borrar carpetas de Windows"),
    (r"rmtree\s*\(\s*['\"]c:[\\\\/]['\"]", "borrar el disco entero"),
    (r"winreg\.[^\n]*hkey_local_machine", "tocar el registro de Windows"),
    (r"(pynput[^\n]*keyboard|keyboard\.(hook|on_press|record))",
     "espiar las teclas que pulsa alguien"),
    (r"getasynckeystate[^\n]*while", "espiar las teclas que pulsa alguien"),
    (r"os\.system\s*\(\s*['\"]\s*format\s", "formatear un disco"),
    (r"shutil\.rmtree\s*\([^)]*expanduser", "borrar la carpeta de usuario entera"),
    (r"(smtplib|requests\.post)[^\n]{0,200}(password|contrasena|clave_api|token\.json)",
     "mandar contrasenas o claves fuera del ordenador"),
]

# Programas a los que Angel ya ha dado permiso: nombre -> hasta cuando
_permitidos = {}


# ------------------------------------------------------------------ utilidades
def _tareas():
    """La lista negra y el decodificador de la consola viven en tareas.py."""
    import tareas
    return tareas


def _apuntar(que, detalle, resultado=""):
    try:
        _tareas()._apuntar("TALLER " + que, detalle, resultado)
    except Exception:
        pass


def _limpio(nombre):
    """Un nombre de carpeta que no se pueda escapar a otro sitio."""
    n = re.sub(r"[^A-Za-z0-9 _\-\.]", "", str(nombre or "")).strip()
    n = n.replace("..", "").strip(". ")
    return n[:60]


def _carpeta(nombre):
    n = _limpio(nombre)
    if not n:
        return None
    return os.path.join(TALLER, n)


def _dentro(ruta):
    """Que no se escriba fuera del taller, pase lo que pase."""
    try:
        return os.path.commonpath([os.path.abspath(ruta),
                                   os.path.abspath(TALLER)]) == os.path.abspath(TALLER)
    except Exception:
        return False


def _peligro(codigo):
    """El motivo por el que NO se ejecuta, o None."""
    t = re.sub(r"[ \t]+", " ", str(codigo or "")).lower()
    motivo = None
    try:
        motivo = _tareas()._es_peligroso(t)
    except Exception:
        pass
    if motivo:
        return motivo
    for patron, m in PROHIBIDO_CODIGO:
        if re.search(patron, t, re.MULTILINE):
            return m
    return None


def _puente_con_berna():
    """Deja que los programas del taller usen las librerias que Berna ya tiene.

    OJO, que esto costo una prueba: crear el venv con --system-site-packages
    NO vale. Ese "system" es el Python base, no el venv de Berna, asi que los
    programas se quedaban sin numpy, sin requests y sin pillow. La solucion es
    un .pth que anade el site-packages de Berna AL FINAL del camino de
    busqueda: se ve todo lo suyo, pero lo que se instale en el taller manda
    por delante, y el venv de Berna sigue sin tocarse.
    """
    destino = os.path.join(ENTORNO, "Lib", "site-packages")
    if not os.path.isdir(destino):
        return False
    puente = os.path.join(destino, "librerias-de-berna.pth")
    suyas = os.path.join(BASE, "venv", "Lib", "site-packages")
    try:
        if not os.path.exists(puente) and os.path.isdir(suyas):
            with open(puente, "w", encoding="utf-8") as f:
                f.write(suyas + "\n")
        return True
    except Exception:
        return False


def _python():
    """El interprete con el que se ejecutan los programas."""
    propio = os.path.join(ENTORNO, "Scripts", "python.exe")
    if os.path.exists(propio):
        _puente_con_berna()          # por si el entorno es de antes del puente
        return propio
    return PYTHON_BERNA


def _archivos(carpeta):
    fuera = []
    for raiz, dirs, files in os.walk(carpeta):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "_entorno")]
        for f in files:
            if f.endswith((".pyc", ".anterior")):
                continue
            fuera.append(os.path.relpath(os.path.join(raiz, f), carpeta))
    return sorted(fuera)


def _principal(carpeta):
    """El archivo por el que se arranca el programa."""
    for n in ("principal.py", "main.py", "index.html", "principal.bat"):
        if os.path.exists(os.path.join(carpeta, n)):
            return n
    for f in _archivos(carpeta):
        if f.endswith((".py", ".html", ".bat")):
            return f
    return None


# ------------------------------------------------------------------ crear
ESQUELETOS = {
    "python": u'''# -*- coding: utf-8 -*-
"""%s

Escrito por Berna para Angel el %s.
"""


def main():
    print("Todavia no hago nada. Berna me tiene que terminar.")


if __name__ == "__main__":
    main()
''',
    "html": u'''<!doctype html>
<html lang="es">
<head><meta charset="utf-8"><title>%s</title></head>
<body>
  <h1>%s</h1>
  <p>Hecho por Berna el %s.</p>
</body>
</html>
''',
    "bat": u'''@echo off
REM %s
REM Escrito por Berna el %s.
echo Todavia no hago nada.
pause
''',
}


def crear_programa(nombre, que_hace="", lenguaje="python", permiso=None):
    carpeta = _carpeta(nombre)
    if not carpeta:
        return "Dime como se va a llamar el programa, con letras y numeros."
    leng = str(lenguaje or "python").strip().lower()
    if leng not in LENGUAJES:
        leng = "python"
    if os.path.isdir(carpeta):
        return ("Ya existe un programa que se llama '%s'. Miralo con ver_codigo "
                "y sigue trabajando en el, o ponle otro nombre." % _limpio(nombre))
    aviso = ("Berna va a CREAR UN PROGRAMA nuevo:\n\n%s\n\nPara que: %s\n\n"
             "Se guardara en:\n%s\n\nLe dejas?"
             % (_limpio(nombre), que_hace or "(no lo ha dicho)", carpeta))
    if permiso is None or not permiso(aviso):
        return "No me has dado permiso, no he creado nada."
    os.makedirs(carpeta, exist_ok=True)
    fecha = datetime.datetime.now().strftime("%d/%m/%Y")
    nombre_archivo = "principal" + LENGUAJES[leng]
    plantilla = ESQUELETOS[leng]
    cuerpo = (plantilla % (que_hace or _limpio(nombre), _limpio(nombre), fecha)
              if leng == "html" else plantilla % (que_hace or _limpio(nombre), fecha))
    with open(os.path.join(carpeta, nombre_archivo), "w", encoding="utf-8") as f:
        f.write(cuerpo)
    with open(os.path.join(carpeta, "LEEME.txt"), "w", encoding="utf-8") as f:
        f.write(u"%s\n%s\n\nQue hace: %s\n\nLo escribio Berna el %s.\n"
                u"Para usarlo, pidele a Berna que te lo abra.\n"
                % (_limpio(nombre), "=" * len(_limpio(nombre)),
                   que_hace or "(pendiente)", fecha))
    _apuntar("CREAR", "%s (%s)" % (_limpio(nombre), leng))
    return ("Creado el programa '%s' en %s, con el archivo %s.\n\n"
            "AHORA ESCRIBE EL CODIGO DE VERDAD con escribir_codigo, y en cuanto "
            "lo tengas, PRUEBALO con probar_programa. Si da error, lee el error, "
            "arregla el archivo y vuelve a probarlo. Asi hasta que funcione: no "
            "le digas a Angel que esta listo hasta que lo hayas visto funcionar."
            % (_limpio(nombre), carpeta, nombre_archivo))


# ------------------------------------------------------------------ escribir
def escribir_codigo(programa, codigo, archivo=""):
    carpeta = _carpeta(programa)
    if not carpeta or not os.path.isdir(carpeta):
        return ("No tengo ningun programa que se llame '%s'. Crealo primero con "
                "crear_programa." % programa)
    codigo = str(codigo if codigo is not None else "")
    if not codigo.strip():
        return "No me has dado nada que escribir."
    if len(codigo) > MAX_CODIGO:
        return ("Son %d caracteres y de una vez escribo %d. Partelo en varios "
                "archivos, que ademas queda mejor." % (len(codigo), MAX_CODIGO))
    if archivo and re.search(r"[\\/]|\.\.", str(archivo)):
        # _limpio ya lo dejaria en un nombre suelto y contenido, pero callarse
        # y escribir en otro sitio del que te han pedido es peor que avisar.
        return ("Ese nombre de archivo lleva carpetas o '..' y aqui cada "
                "programa vive en su carpeta. Dame solo el nombre, por ejemplo "
                "utiles.py.")
    nombre = _limpio(archivo) or _principal(carpeta) or "principal.py"
    if not os.path.splitext(nombre)[1]:
        nombre += ".py"
    ruta = os.path.join(carpeta, nombre)
    if not _dentro(ruta):
        return "Ese archivo se sale del taller y ahi no escribo."
    # copia de seguridad, que arreglando cosas se rompen otras
    if os.path.exists(ruta):
        try:
            shutil.copy2(ruta, ruta + ".anterior")
        except Exception:
            pass
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(codigo)
    _apuntar("ESCRIBIR", "%s / %s (%d caracteres)"
             % (_limpio(programa), nombre, len(codigo)))
    lineas = codigo.count("\n") + 1
    return ("Escrito %s (%d lineas) en el programa '%s'. AHORA PRUEBALO con "
            "probar_programa para ver si funciona de verdad."
            % (nombre, lineas, _limpio(programa)))


def ver_codigo(programa, archivo=""):
    carpeta = _carpeta(programa)
    if not carpeta or not os.path.isdir(carpeta):
        return "No tengo ningun programa que se llame '%s'." % programa
    if not archivo:
        fuera = _archivos(carpeta)
        if not fuera:
            return "El programa '%s' esta vacio." % _limpio(programa)
        principal = _principal(carpeta)
        cabecera = ("El programa '%s' tiene estos archivos: %s.\n\n"
                    % (_limpio(programa), ", ".join(fuera)))
        archivo = principal or fuera[0]
    else:
        cabecera = ""
        archivo = _limpio(archivo)
    ruta = os.path.join(carpeta, archivo)
    if not _dentro(ruta) or not os.path.exists(ruta):
        return "No encuentro el archivo '%s' en ese programa." % archivo
    try:
        with open(ruta, "r", encoding="utf-8", errors="replace") as f:
            texto = f.read()
    except Exception as e:
        return "No he podido leerlo: %s" % e
    if len(texto) > MAX_CODIGO:
        texto = texto[:MAX_CODIGO] + "\n[...cortado...]"
    numeradas = "\n".join("%4d  %s" % (i, l)
                          for i, l in enumerate(texto.splitlines(), 1))
    return cabecera + "Contenido de %s:\n\n%s" % (archivo, numeradas)


# ------------------------------------------------------------------ probar
def _resumen(codigo, salida, error):
    partes = []
    salida = (salida or "").strip()
    error = (error or "").strip()
    if codigo == 0:
        partes.append("FUNCIONA: ha terminado bien (codigo 0).")
        if salida:
            partes.append("Esto es lo que ha escrito:\n" + salida[-3000:])
        else:
            partes.append("No ha escrito nada por pantalla.")
        if error:
            partes.append("Avisos que ha soltado:\n" + error[-1000:])
        partes.append("Cuentaselo a Angel en una frase y dile como usarlo.")
    else:
        partes.append("HA FALLADO (codigo %s)." % codigo)
        if error:
            partes.append("EL ERROR ES ESTE, mira la ultima linea que es la "
                          "que manda:\n" + error[-3000:])
        if salida:
            partes.append("Lo que llego a escribir antes de romperse:\n"
                          + salida[-1000:])
        partes.append("AHORA ARREGLALO TU: mira en que linea peta, corrige el "
                      "archivo con escribir_codigo y vuelve a probarlo. No le "
                      "digas a Angel que hay un error hasta que lo hayas "
                      "intentado arreglar un par de veces.")
    return "\n\n".join(partes)


def probar_programa(programa, archivo="", segundos=SEGUNDOS, permiso=None):
    import time
    carpeta = _carpeta(programa)
    if not carpeta or not os.path.isdir(carpeta):
        return "No tengo ningun programa que se llame '%s'." % programa
    nombre = _limpio(archivo) or _principal(carpeta)
    if not nombre:
        return "Ese programa no tiene ningun archivo que se pueda ejecutar."
    ruta = os.path.join(carpeta, nombre)
    if not _dentro(ruta) or not os.path.exists(ruta):
        return "No encuentro el archivo '%s'." % nombre
    try:
        segundos = max(1, min(MAX_SEGUNDOS, int(float(segundos))))
    except Exception:
        segundos = SEGUNDOS

    if nombre.endswith(".html"):
        try:
            os.startfile(ruta)
            _apuntar("ABRIR", "%s / %s" % (_limpio(programa), nombre))
            return ("He abierto %s en el navegador. Preguntale a Angel que ve, o "
                    "miralo tu con mirar_pantalla." % nombre)
        except Exception as e:
            return "No he podido abrirlo: %s" % e

    try:
        with open(ruta, "r", encoding="utf-8", errors="replace") as f:
            codigo = f.read()
    except Exception as e:
        return "No he podido leer el archivo: %s" % e

    motivo = _peligro(codigo)
    if motivo:
        _apuntar("NEGADA", "%s / %s" % (_limpio(programa), nombre), motivo)
        return ("Eso NO lo ejecuto: el codigo intenta %s. Y no lo hare aunque "
                "Angel insista, esta en mi lista de cosas que no toco. Quita esa "
                "parte y lo volvemos a intentar." % motivo)

    clave = _limpio(programa)
    if _permitidos.get(clave, 0) < time.time():
        aviso = ("Berna va a EJECUTAR un programa que ha escrito el:\n\n"
                 "%s  (archivo %s)\n\nEsta en %s\n\n"
                 "Mientras lo va arreglando podra volver a lanzarlo durante %d "
                 "minutos sin preguntarte otra vez. Le dejas?"
                 % (clave, nombre, carpeta, PERMISO_MINUTOS))
        if permiso is None or not permiso(aviso):
            _apuntar("SIN PERMISO", "%s / %s" % (clave, nombre))
            return "Angel no me ha dado permiso, no lo he ejecutado."
        _permitidos[clave] = time.time() + PERMISO_MINUTOS * 60

    if nombre.endswith(".bat"):
        argv = ["cmd", "/c", ruta]
    else:
        argv = [_python(), ruta]
    try:
        p = subprocess.run(argv, cwd=carpeta, capture_output=True,
                           timeout=segundos, creationflags=SIN_VENTANA)
        salida = _tareas()._texto(p.stdout)
        error = _tareas()._texto(p.stderr)
        _apuntar("PROBAR", "%s / %s" % (clave, nombre), "codigo %s" % p.returncode)
        return _resumen(p.returncode, salida, error)
    except subprocess.TimeoutExpired as e:
        _apuntar("PROBAR", "%s / %s" % (clave, nombre), "se paso de %ds" % segundos)
        salida = _tareas()._texto(getattr(e, "stdout", b"") or b"")
        return ("SE HA QUEDADO COLGADO: lleva mas de %d segundos y lo he parado.\n\n"
                "%sEso suele ser un bucle sin salida o algo que espera a que "
                "alguien escriba. Miralo y arreglalo."
                % (segundos, ("Lo que llego a escribir:\n" + salida[-1000:] + "\n\n")
                   if salida else ""))
    except Exception as e:
        return "No he podido ni lanzarlo: %s" % e


# ------------------------------------------------------------------ librerias
def instalar_libreria(nombre, permiso=None):
    paquete = re.sub(r"[^A-Za-z0-9_\-\.\[\]=<>]", "", str(nombre or "")).strip()
    if not paquete:
        return "Dime que libreria hace falta."
    aviso = ("Berna necesita instalar una libreria de Python para el programa "
             "que esta haciendo:\n\n%s\n\nSe instala en el entorno del taller "
             "(programas\\_entorno), APARTE del suyo, para no romperse el.\n\n"
             "Hace falta internet. Le dejas?" % paquete)
    if permiso is None or not permiso(aviso):
        return "No me has dado permiso, no he instalado nada."
    os.makedirs(TALLER, exist_ok=True)
    propio = os.path.join(ENTORNO, "Scripts", "python.exe")
    if not os.path.exists(propio):
        try:
            subprocess.run([PYTHON_BERNA, "-m", "venv", "--system-site-packages",
                            ENTORNO], capture_output=True, timeout=300,
                           creationflags=SIN_VENTANA)
        except Exception as e:
            return "No he podido preparar el entorno del taller: %s" % e
        if not os.path.exists(propio):
            return "No he podido preparar el entorno del taller."
        _puente_con_berna()
    try:
        p = subprocess.run([propio, "-m", "pip", "install", paquete],
                           capture_output=True, timeout=900,
                           creationflags=SIN_VENTANA)
    except subprocess.TimeoutExpired:
        return "La instalacion ha tardado demasiado y la he parado."
    except Exception as e:
        return "No he podido instalarla: %s" % e
    salida = _tareas()._texto(p.stdout) + _tareas()._texto(p.stderr)
    _apuntar("LIBRERIA", paquete, "codigo %s" % p.returncode)
    if p.returncode != 0:
        return ("No se ha podido instalar %s:\n%s\n\nMira si el nombre esta bien "
                "escrito, o si hace falta otra cosa." % (paquete, salida[-1200:]))
    return ("Instalada %s en el entorno del taller. Ya la puedes usar en el "
            "programa: importala y vuelve a probarlo." % paquete)


# ------------------------------------------------------------------ publicar
def publicar_programa(programa, permiso=None):
    carpeta = _carpeta(programa)
    if not carpeta or not os.path.isdir(carpeta):
        return "No tengo ningun programa que se llame '%s'." % programa
    nombre = _principal(carpeta)
    if not nombre:
        return "Ese programa no tiene nada que se pueda arrancar."
    clave = _limpio(programa)
    aviso = ("Berna quiere DEJARTE EN EL ESCRITORIO un acceso directo para "
             "usar el programa que ha hecho:\n\n%s\n\nAsi lo abres con doble "
             "clic cuando quieras. Le dejas?" % clave)
    if permiso is None or not permiso(aviso):
        return "No me has dado permiso, no he puesto nada en el escritorio."
    lanzador = os.path.join(carpeta, "abrir.bat")
    if nombre.endswith(".html"):
        cuerpo = '@echo off\r\nstart "" "%s"\r\n' % os.path.join(carpeta, nombre)
    elif nombre.endswith(".bat"):
        cuerpo = '@echo off\r\ncall "%s"\r\n' % os.path.join(carpeta, nombre)
    else:
        cuerpo = ('@echo off\r\ncd /d "%s"\r\n"%s" "%s"\r\npause\r\n'
                  % (carpeta, _python(), nombre))
    try:
        with open(lanzador, "w", encoding="utf-8") as f:
            f.write(cuerpo)
        atajo = os.path.join(ESCRITORIO, clave + ".lnk")
        ps = ('$w = New-Object -ComObject WScript.Shell; '
              '$s = $w.CreateShortcut("%s"); $s.TargetPath = "%s"; '
              '$s.WorkingDirectory = "%s"; $s.Description = "Hecho por Berna"; '
              '$s.Save()' % (atajo, lanzador, carpeta))
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, timeout=60, creationflags=SIN_VENTANA)
        _apuntar("PUBLICAR", clave, atajo)
        if not os.path.exists(atajo):
            return ("He dejado el lanzador en %s, pero no he podido crear el "
                    "acceso directo del escritorio." % lanzador)
        return ("Listo: tienes '%s' en el escritorio. Doble clic y se abre. "
                "Diselo a Angel." % clave)
    except Exception as e:
        return "No he podido publicarlo: %s" % e


# ------------------------------------------------------------------ repasar
def listar_programas_creados():
    if not os.path.isdir(TALLER):
        return ("Todavia no he hecho ningun programa. Pideme uno: 'hazme un "
                "programa que...' y me pongo.")
    hechos = [d for d in sorted(os.listdir(TALLER))
              if os.path.isdir(os.path.join(TALLER, d)) and not d.startswith("_")]
    if not hechos:
        return ("Todavia no he hecho ningun programa. Pideme uno y me pongo.")
    lineas = ["Programas que he escrito (%d):" % len(hechos)]
    for d in hechos:
        carpeta = os.path.join(TALLER, d)
        archivos = _archivos(carpeta)
        que = ""
        leeme = os.path.join(carpeta, "LEEME.txt")
        if os.path.exists(leeme):
            try:
                with open(leeme, "r", encoding="utf-8", errors="replace") as f:
                    for l in f:
                        if l.lower().startswith("que hace:"):
                            que = l.split(":", 1)[1].strip()
                            break
            except Exception:
                pass
        fecha = datetime.datetime.fromtimestamp(
            os.path.getmtime(carpeta)).strftime("%d/%m/%Y")
        lineas.append("  - %s: %s (%d archivos, del %s)"
                      % (d, que or "sin descripcion", len(archivos), fecha))
    lineas.append("")
    lineas.append("Cuentaselo con tus palabras y recuerdale que puede pedirte "
                  "que le ponga cualquiera en el escritorio.")
    return "\n".join(lineas)


def borrar_programa(programa, permiso=None):
    carpeta = _carpeta(programa)
    if not carpeta or not os.path.isdir(carpeta):
        return "No tengo ningun programa que se llame '%s'." % programa
    clave = _limpio(programa)
    if permiso is None or not permiso(
            "Berna va a BORRAR el programa '%s' y todo lo que tiene dentro:\n\n"
            "%s\n\nEsto no tiene vuelta atras. Le dejas?" % (clave, carpeta)):
        return "No me has dado permiso, no he borrado nada."
    try:
        shutil.rmtree(carpeta)
        atajo = os.path.join(ESCRITORIO, clave + ".lnk")
        if os.path.exists(atajo):
            os.remove(atajo)
        _apuntar("BORRAR", clave)
        return "Borrado el programa '%s'." % clave
    except Exception as e:
        return "No he podido borrarlo: %s" % e
