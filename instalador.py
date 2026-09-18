# -*- coding: utf-8 -*-
r"""
Vuelca Sobri, tal y como este ahora mismo, a la carpeta de instalacion
del escritorio para llevarselo en un pen.

Angel lo pidio asi el 2026-08-26: "cualquier modificacion que le vayamos
aplicando se la vas aplicando tambien a la carpeta, para que cuando yo lo
descargue este como lo hayamos dejado".

  ASI QUE: DESPUES DE TOCAR CUALQUIER COSA DE C:\Asistente, EJECUTA ESTO.
  Es lo unico que hay que acordarse de hacer.

      C:\Asistente\venv\Scripts\python.exe C:\Asistente\instalador.py

  Se puede repetir las veces que haga falta: solo copia lo que ha cambiado,
  asi que tarda un par de segundos salvo la primera vez.

QUE SE LLEVA Y QUE NO, que es la parte importante
  SI  el codigo, las voces, los modelos de reconocer caras, el modelo del
      oido, las guias, y las ruedas de pip para poder instalar SIN INTERNET.
  NO  el token de Google (da acceso a su Gmail), las caras que conoce, el
      registro, los backups ni el venv (que no se puede copiar de un
      ordenador a otro: apunta con ruta absoluta al Python de esta maquina).

  Sus cosas privadas (las claves, lo que recuerda de el, su perfil) van
  APARTE, en la carpeta TUS-DATOS-PRIVADOS, para que pueda borrarla de un
  tiron si le presta el pen a alguien.

LAS RUEDAS DE PIP
  Ocupan lo suyo y solo hacen falta cuando cambian las dependencias, asi que
  por defecto NO se vuelven a bajar. Si has instalado un paquete nuevo:

      ...python.exe instalador.py --paquetes
"""
import os
import sys
import json
import time
import shutil
import filecmp
import subprocess

BASE = os.path.dirname(os.path.abspath(__file__))


def escritorio():
    """La carpeta del escritorio DE VERDAD.

    NO vale os.path.expanduser("~") + "\\Desktop". Con OneDrive sincronizando
    el escritorio -- que es el caso de Angel -- el escritorio real es
    C:\\Users\\alaga\\OneDrive\\Escritorio, y "~/Desktop" ni siquiera existe...
    hasta que un os.makedirs lo CREA. Eso es justo lo que llevaba pasando:
    la sincronizacion de fin de sesion volcaba 373 MB a una carpeta fantasma
    que Angel no ve, mientras el kit que si ve en su escritorio se quedaba
    con la Sobri del 26 de agosto. Si llegaba a pinchar aquel INSTALAR.bat,
    se cargaba la Sobri buena con una vieja.

    Windows guarda la ruta buena en el registro y la respeta aunque OneDrive
    la haya movido. Si por lo que sea no se pudiera leer, se cae a la de
    siempre, que en un equipo sin OneDrive es la correcta.

    Esta funcion esta repetida en taller.py y en operar.py a proposito: esos
    modulos y este tienen que poder funcionar sueltos, sin importar a Sobri.
    """
    try:
        import winreg
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer"
                r"\User Shell Folders") as k:
            ruta = os.path.expandvars(winreg.QueryValueEx(k, "Desktop")[0])
        if os.path.isdir(ruta):
            return ruta
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Desktop")


ESCRITORIO = escritorio()
DESTINO = os.path.join(ESCRITORIO, "Instalar Sobri")
PROGRAMA = os.path.join(DESTINO, "Programa")
PAQUETES = os.path.join(DESTINO, "Paquetes")
PRIVADO = os.path.join(DESTINO, "TUS-DATOS-PRIVADOS")
OIDO = os.path.join(DESTINO, "Modelo-de-oido")
PYTHON_DIR = os.path.join(DESTINO, "Python")

CACHE_HF = os.path.join(os.path.expanduser("~"), ".cache", "huggingface")

# Lo que se copia tal cual (carpetas enteras)
# "sonidos" lleva el banco de instrumentos grabados (141 MB). Sin el, en
# otro ordenador las canciones sonarian a sintetizador otra vez.
CARPETAS = ["voces", "modelos", "sonidos"]

# Lo que NUNCA sale de este ordenador
NUNCA = {"caras.json", "berna.log", "google", "venv", "__pycache__",
         "tareas", "config.json",
         # la herramienta de publicar es de Angel, no del producto
         "publicar_actualizacion.py", "Enlazar-con-GitHub.bat",
         # y su boton: en otro ordenador no hay publicador y solo daria error
         "Publicar Sobri.bat", "Publicar Berna.bat",   # el de antes del cambio
         # el enganche de Claude Code que pone al dia ESTA carpeta del pen
         # desde este ordenador; en otro no tiene nada que sincronizar
         "sincronizar-al-terminar.bat"}

# Los datos suyos, que van a la carpeta aparte
PRIVADOS = ["config.json", "memoria.json", "perfil.json",
            "oportunidades.json", "vigilancias.json"]

# clave_movil (02-09-2026): es la contrasena con la que el movil se engancha
# a Sobri. Se colaba tal cual en el config del programa, o sea que viajaba en
# el pen aunque se borrase TUS-DATOS-PRIVADOS, que es justo lo que el LEEME
# promete que no pasa. Al dueno le sigue llegando: va en su carpeta privada.
CLAVES = ["clave_api", "clave_gemini", "clave_busqueda", "imap_password",
          "imap_usuario", "imap_servidor", "clave_movil"]

cuenta = {"copiados": 0, "iguales": 0, "carpetas": 0}


def _copiar(origen, destino):
    """Copia solo si ha cambiado, para que repetirlo sea instantaneo."""
    if os.path.exists(destino) and filecmp.cmp(origen, destino, shallow=False):
        cuenta["iguales"] += 1
        return False
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    shutil.copy2(origen, destino)
    cuenta["copiados"] += 1
    return True


def _copiar_arbol(origen, destino, saltar=()):
    if not os.path.isdir(origen):
        return
    for raiz, dirs, files in os.walk(origen):
        dirs[:] = [d for d in dirs if d not in ("__pycache__",) and d not in saltar]
        for f in files:
            if f in saltar or f.endswith(".pyc"):
                continue
            rel = os.path.relpath(os.path.join(raiz, f), origen)
            _copiar(os.path.join(raiz, f), os.path.join(destino, rel))


def _es_copia_de_seguridad(nombre):
    return ".bak" in nombre or nombre.endswith(".tmp")


# ------------------------------------------------------------------ el codigo
def volcar_programa():
    for f in sorted(os.listdir(BASE)):
        ruta = os.path.join(BASE, f)
        if not os.path.isfile(ruta) or _es_copia_de_seguridad(f) or f in NUNCA:
            continue
        if f.endswith((".py", ".txt", ".bat")):
            _copiar(ruta, os.path.join(PROGRAMA, f))
    for c in CARPETAS:
        _copiar_arbol(os.path.join(BASE, c), os.path.join(PROGRAMA, c))
        cuenta["carpetas"] += 1
    # el buzon de tareas va vacio, pero con sus explicaciones
    tareas_dir = os.path.join(BASE, "tareas")
    if os.path.isdir(tareas_dir):
        for nombre in ("COMO-FUNCIONA.txt", "_COMO_CODEX_DEJA_TAREAS.txt"):
            guia = os.path.join(tareas_dir, nombre)
            if os.path.exists(guia):
                _copiar(guia, os.path.join(PROGRAMA, "tareas", nombre))


def limpiar_sobras():
    """Borra de la carpeta lo que ya no existe en C:\\Asistente.

    Hace falta de verdad: al renombrar `actualizar-instalador.py` a
    `instalador.py`, el viejo se quedo alli tirado. Un modulo fantasma en la
    carpeta de instalacion es un modulo que se instala en el ordenador nuevo,
    y con suerte solo estorba.

    Tambien quita lo que se ha metido en NUNCA despues de haberse copiado
    (14-09-2026, "Publicar Sobri.bat"): sigue existiendo en C:\\Asistente, asi
    que sin esto se quedaba en el pen para siempre. Solo los .py/.txt/.bat,
    que son los que copia volcar_programa; el config.json del pen lo escribe
    config_sin_claves a proposito y no se toca.
    """
    if not os.path.isdir(PROGRAMA):
        return []
    fuera = []
    for raiz, dirs, files in os.walk(PROGRAMA):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            ruta = os.path.join(raiz, f)
            rel = os.path.relpath(ruta, PROGRAMA)
            vetado = rel in NUNCA and rel.endswith((".py", ".txt", ".bat"))
            if os.path.exists(os.path.join(BASE, rel)) and not vetado:
                continue
            os.remove(ruta)
            fuera.append(rel)
    for raiz, dirs, files in os.walk(PROGRAMA, topdown=False):
        if not os.listdir(raiz) and raiz != PROGRAMA:
            os.rmdir(raiz)
    return fuera


def config_sin_claves():
    """El config que va en el programa: todo igual pero con las claves fuera."""
    with open(os.path.join(BASE, "config.json"), "r", encoding="utf-8") as f:
        cfg = json.load(f)
    for k in CLAVES:
        if k in cfg:
            cfg[k] = ""
    # El microfono elegido a mano son unos cascos concretos de ESTE ordenador.
    # En otro no estan enchufados, y Sobri se quedaba buscando un aparato que
    # no existe en vez de coger el que hubiera. En blanco lo busca sola.
    for k in ("microfono", "altavoz"):
        if cfg.get(k):
            cfg[k] = None if k == "microfono" else ""
    destino = os.path.join(PROGRAMA, "config.json")
    nuevo = json.dumps(cfg, indent=2, ensure_ascii=False)
    viejo = ""
    if os.path.exists(destino):
        with open(destino, "r", encoding="utf-8") as f:
            viejo = f.read()
    if nuevo != viejo:
        os.makedirs(PROGRAMA, exist_ok=True)
        with open(destino, "w", encoding="utf-8") as f:
            f.write(nuevo)
        cuenta["copiados"] += 1
    else:
        cuenta["iguales"] += 1


def volcar_privados():
    os.makedirs(PRIVADO, exist_ok=True)
    for f in PRIVADOS:
        ruta = os.path.join(BASE, f)
        if os.path.exists(ruta):
            _copiar(ruta, os.path.join(PRIVADO, f))
    # Los programas que Sobri le haya escrito son cosas suyas, asi que viajan
    # con sus datos. El entorno del taller no: un venv no se puede copiar de un
    # ordenador a otro, y se vuelve a crear solo cuando haga falta.
    taller = os.path.join(BASE, "programas")
    if os.path.isdir(taller):
        for d in os.listdir(taller):
            if d.startswith("_"):
                continue
            origen = os.path.join(taller, d)
            if os.path.isdir(origen):
                _copiar_arbol(origen, os.path.join(PRIVADO, "programas", d),
                              saltar=("_entorno",))
    with open(os.path.join(PRIVADO, "LEE-ESTO-PRIMERO.txt"), "w",
              encoding="utf-8") as f:
        f.write(AVISO_PRIVADO)


MINIMO_PAQUETES = 20


def requisitos():
    """Guarda la lista de piezas que hay que instalar.

    OJO: esto rompio a Sobri el 30-ago-2026 y se llevo la instalacion entera.
    Antes se guardaba lo que soltara `pip freeze` SIN MIRARLO. El 28-ago el
    venv estaba a medias, `pip freeze` no devolvio nada, y aqui se escribio un
    requisitos.txt VACIO. Dos dias despues INSTALAR.bat hizo lo suyo: borrar el
    venv, crearlo de nuevo y pedirle a pip que instale ese fichero, o sea nada.
    Sobri arranco sin numpy, sin piper y sin sounddevice: sorda y muda.
    Un fichero de dos bytes se llevo por delante todo lo instalado.

    Por eso ahora NO se guarda si la lista viene vacia, si pip ha fallado o si
    trae menos de MINIMO_PAQUETES: mas vale un requisitos.txt viejo que uno
    vacio. Ademas se deja copia .bak del anterior y se devuelve el motivo,
    que sale en el informe.
    """
    destino = os.path.join(DESTINO, "requisitos.txt")
    try:
        r = subprocess.run([os.path.join(BASE, "venv", "Scripts", "python.exe"),
                            # "freeze" a secas escribe "paquete @ file:///C:/Users/..."
                            # cuando se instalo desde las ruedas de Paquetes, y ese
                            # requisitos.txt solo vale en este ordenador. "list" da
                            # siempre nombre==version.
                            "-m", "pip", "list", "--format=freeze"],
                           capture_output=True, text=True, timeout=180)
    except Exception as e:
        return False, 0, "no he podido preguntarle a pip (%s); dejo el de antes" % e
    if r.returncode != 0:
        return False, 0, ("pip ha fallado (codigo %d); dejo el de antes"
                          % r.returncode)
    lista = (r.stdout or "").strip()
    n = len(lista.splitlines()) if lista else 0
    if n < MINIMO_PAQUETES:
        return False, n, ("la lista venia con %d paquetes, menos de %d: huele a "
                          "entorno roto, NO la guardo" % (n, MINIMO_PAQUETES))
    viejo = ""
    if os.path.exists(destino):
        with open(destino, "r", encoding="utf-8-sig") as f:
            viejo = f.read().strip()
    if lista != viejo:
        if viejo:
            try:
                shutil.copy2(destino, destino + ".bak")
            except OSError:
                pass
        with open(destino, "w", encoding="utf-8") as f:
            f.write(lista + "\n")
        return True, n, ""
    return False, n, ""


def volcar_oido():
    """Los modelos de Whisper ya descargados, para no depender de internet.

    SOLO los que Sobri usa de verdad, no todos los que haya en la cache, y lo
    que sobre se borra mas abajo: por probar el 'small' una vez, la carpeta de
    instalacion paso de 613 MB a 1.077 MB para llevarse un modelo que nadie
    iba a usar.

    OJO (02-09-2026): AHORA SON DOS. Desde que existe el oido fino, Sobri
    arranca con el de `whisper_tam` (rapido, para ir siguiendo la conversacion)
    y carga aparte el de `oido_fino` (mejor, para lo que cuesta entender). Aqui
    se copiaba solo el primero Y SE BORRABA EL SEGUNDO, que es justo lo que
    hacia esta linea de abajo. Resultado: en un ordenador nuevo y sin internet
    el oido fino no estaba, y sin conexion no habia forma de bajarlo. Si algun
    dia se anade un tercer modelo, va aqui.
    """
    origen = os.path.join(CACHE_HF, "hub")
    if not os.path.isdir(origen):
        return False
    try:
        with open(os.path.join(BASE, "config.json"), "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    # Mismo criterio que asistente.py: el fino viene puesto salvo que lo apaguen.
    tams = [str(cfg.get("whisper_tam") or "base")]
    fino = str(cfg.get("oido_fino") or "small")
    if fino.lower() not in ("", "no", "0") and fino not in tams:
        tams.append(fino)
    quiero = [("faster-whisper-%s" % t).lower() for t in tams]
    destino = os.path.join(OIDO, "hub")
    for d in os.listdir(origen):
        if "whisper" in d.lower() and any(d.lower().endswith(q) for q in quiero):
            _copiar_arbol(os.path.join(origen, d), os.path.join(destino, d))
    # y fuera el que se colase en su dia
    if os.path.isdir(destino):
        for d in os.listdir(destino):
            if "whisper" in d.lower() and not any(d.lower().endswith(q)
                                                  for q in quiero):
                shutil.rmtree(os.path.join(destino, d), ignore_errors=True)
    tag = os.path.join(CACHE_HF, "CACHEDIR.TAG")
    if os.path.exists(tag):
        _copiar(tag, os.path.join(OIDO, "CACHEDIR.TAG"))
    return True


def bajar_paquetes(forzar=False):
    os.makedirs(PAQUETES, exist_ok=True)
    if not forzar and len(os.listdir(PAQUETES)) > 40:
        return "ya estaban (%d ruedas)" % len(os.listdir(PAQUETES))
    r = subprocess.run([os.path.join(BASE, "venv", "Scripts", "python.exe"),
                        "-m", "pip", "download", "-r",
                        os.path.join(DESTINO, "requisitos.txt"),
                        "-d", PAQUETES, "--only-binary=:all:"],
                       capture_output=True, text=True, timeout=3600)
    if r.returncode != 0:
        return "FALLO: " + (r.stderr or "")[-300:]
    return "descargadas (%d ruedas)" % len(os.listdir(PAQUETES))


def _tam(carpeta):
    t = 0
    for raiz, _d, files in os.walk(carpeta):
        for f in files:
            try:
                t += os.path.getsize(os.path.join(raiz, f))
            except OSError:
                pass
    return t


# ------------------------------------------------------------------ los textos
AVISO_PRIVADO = u"""ESTA CARPETA LLEVA TUS COSAS. LEE ESTO.

Aqui dentro estan:

  config.json ........ TUS CLAVES (la de Google, la de OpenRouter y la
                       de busqueda). Con ellas cualquiera podria gastar
                       tu cuota.
  memoria.json ....... lo que Sobri recuerda de ti
  perfil.json ........ tu perfil profesional
  oportunidades.json . los encargos que tienes apuntados
  programas\\ ......... los programas que Sobri te ha escrito

El instalador las copia solas, asi que al instalar en otro ordenador
Sobri funciona de una vez, sin que tengas que escribir ninguna clave.

  >>> SI LE PRESTAS EL PEN A ALGUIEN, BORRA ESTA CARPETA ENTERA. <<<

Si la borras, Sobri se instala igual: solo que la primera vez te pedira
las claves. Todo lo demas funciona.

Lo que NO esta aqui, y es a proposito:
  - Tu permiso de Google (google\\token.json). Eso da entrada a tu correo,
    y no debe viajar en un pen. En el ordenador nuevo se vuelve a
    autorizar con: venv\\Scripts\\python.exe autorizar_google.py
  - Las caras que Sobri conoce (caras.json). Son datos de personas y se
    quedan en su ordenador.
"""

LEEME = u"""========================================================
   SOBRI - CARPETA DE INSTALACION
   Para llevartelo en un pen e instalarlo donde quieras
========================================================

COMO SE INSTALA
  1. Copia esta carpeta entera a un pen (o dejala donde esta).
  2. En el ordenador nuevo, entra en la carpeta.
  3. Doble clic en INSTALAR.bat
  4. Espera. Te va contando lo que hace.
  5. Cuando termine tendras un acceso directo "Sobri" en el
     escritorio. Doble clic y a hablar.

NO HACE FALTA INTERNET
  Va todo dentro: el Python, los paquetes, las voces, el modelo
  para reconocer caras y el del oido. Se puede instalar en un
  ordenador recien formateado y sin conexion.

NO HACE FALTA SER ADMINISTRADOR
  El Python se instala solo para tu usuario.

DONDE SE INSTALA
  En C:\\Asistente. Si ya existe algo ahi, te avisa antes de tocarlo.

CUANTO TARDA
  Entre tres y diez minutos, segun el ordenador. Lo que mas tarda
  es instalar los paquetes.

QUE HAY EN CADA CARPETA
  Programa\\ ............. Sobri: el codigo, las voces y los modelos
  Paquetes\\ ............. las piezas de Python que necesita
  Python\\ ............... el instalador de Python, por si no lo tiene
  Modelo-de-oido\\ ....... lo que usa para entenderte al hablar
  TUS-DATOS-PRIVADOS\\ ... TUS CLAVES. Lee el aviso de dentro.
                          Si prestas el pen, borra esa carpeta.

DESPUES DE INSTALAR
  - La camara: la primera vez Windows puede preguntar si dejas que
    las aplicaciones de escritorio usen la camara. Hay que decir
    que si, o Sobri no vera nada.
  - Google (tu Gmail y tu agenda): hay que volver a autorizarlo en
    el ordenador nuevo. Sobri te guia si se lo pides.
  - Todo lo demas ya viene puesto tal y como lo tenias: el acento,
    la personalidad, la voz y lo que sabe hacer.

SI ALGO FALLA
  Abre "Diagnostico (si falla).bat" dentro de C:\\Asistente, o
  pideselo a Claude tal cual: "Sobri no arranca en el portatil".
"""


def escribir_textos():
    os.makedirs(DESTINO, exist_ok=True)
    for nombre, texto in (("LEEME-PRIMERO.txt", LEEME),
                          ("INSTALAR.bat", BAT),
                          ("instalar.ps1", PS1)):
        ruta = os.path.join(DESTINO, nombre)
        viejo = ""
        if os.path.exists(ruta):
            with open(ruta, "r", encoding="utf-8-sig", errors="replace") as f:
                viejo = f.read()
        if viejo.replace("\r\n", "\n") != texto.replace("\r\n", "\n"):
            # los .bat de Windows se llevan mal con el utf-8 con BOM
            cod = "utf-8-sig" if nombre.endswith(".ps1") else "utf-8"
            with open(ruta, "w", encoding=cod, newline="\r\n") as f:
                f.write(texto)
            cuenta["copiados"] += 1
        else:
            cuenta["iguales"] += 1


BAT = u"""@echo off
title Instalar Sobri
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar.ps1"
if errorlevel 1 (
  echo.
  echo Algo ha fallado. Apunta lo que pone arriba y pideselo a Claude.
  pause
)
"""

PS1 = u"""# Instalador de Sobri. Se lanza desde INSTALAR.bat.
# Funciona sin internet y sin ser administrador.
#
# Los dos parametros son para poder ENSAYAR la instalacion sin tocar la que
# ya funciona (se instala en otra carpeta y con otro acceso directo). En uso
# normal no se tocan.
param(
  [string]$destino = "C:\\Asistente",
  [string]$atajo = "Sobri"
)
$ErrorActionPreference = "Stop"
$aqui = Split-Path -Parent $MyInvocation.MyCommand.Path

function Paso($t) { Write-Host ""; Write-Host ">>> $t" -ForegroundColor Cyan }
function Bien($t) { Write-Host "    $t" -ForegroundColor Green }
function Ojo($t)  { Write-Host "    $t" -ForegroundColor Yellow }

Write-Host ""
Write-Host "==========================================" -ForegroundColor White
Write-Host "   INSTALANDO SOBRI" -ForegroundColor White
Write-Host "==========================================" -ForegroundColor White
Write-Host "   Se instala en $destino"
Write-Host "   No hace falta internet ni ser administrador."

if (Test-Path $destino) {
  Write-Host ""
  Ojo "OJO: ya existe $destino"
  Ojo "Se van a sobrescribir los programas, pero NO se toca lo que"
  Ojo "Sobri recuerde ni las caras que conozca."
  $r = Read-Host "    Escribe SI para seguir"
  if ($r -ne "SI" -and $r -ne "si" -and $r -ne "Si") { Write-Host "Cancelado."; exit 0 }
}

# ---------------------------------------------------------------- 1. Python
Paso "1 de 6: buscando Python"
$py = $null
foreach ($c in @("$env:LOCALAPPDATA\\Programs\\Python\\Python314\\python.exe",
                 "$env:LOCALAPPDATA\\Programs\\Python\\Python313\\python.exe")) {
  if (Test-Path $c) { $py = $c; break }
}
if (-not $py) {
  try {
    $v = & py -3 -c "import sys; print(sys.executable)" 2>$null
    if ($LASTEXITCODE -eq 0 -and $v) { $py = $v.Trim() }
  } catch {}
}
if ($py) {
  Bien "Ya tienes Python: $py"
} else {
  $inst = Get-ChildItem -Path (Join-Path $aqui "Python") -Filter "python-*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $inst) { Write-Host "No encuentro el instalador de Python." -ForegroundColor Red; exit 1 }
  Ojo "No tienes Python. Instalandolo (tarda un par de minutos)..."
  $p = Start-Process -FilePath $inst.FullName -Wait -PassThru -ArgumentList @(
        "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_launcher=1",
        "Include_test=0", "Include_doc=0", "AssociateFiles=0")
  Start-Sleep -Seconds 3
  foreach ($c in @("$env:LOCALAPPDATA\\Programs\\Python\\Python314\\python.exe",
                   "$env:LOCALAPPDATA\\Programs\\Python\\Python313\\python.exe")) {
    if (Test-Path $c) { $py = $c; break }
  }
  if (-not $py) { Write-Host "Python no se ha instalado bien (codigo $($p.ExitCode))." -ForegroundColor Red; exit 1 }
  Bien "Python instalado."
}

# ---------------------------------------------------------------- 2. copiar
Paso "2 de 6: copiando Sobri a $destino"
New-Item -ItemType Directory -Force -Path $destino | Out-Null
Copy-Item -Path (Join-Path $aqui "Programa\\*") -Destination $destino -Recurse -Force
Bien "Copiado."

# ---------------------------------------------------------------- 3. venv
Paso "3 de 6: preparando el entorno de Python"
if (Test-Path "$destino\\venv") { Remove-Item "$destino\\venv" -Recurse -Force }
& $py -m venv "$destino\\venv"
if (-not (Test-Path "$destino\\venv\\Scripts\\python.exe")) {
  Write-Host "No se ha podido crear el entorno." -ForegroundColor Red; exit 1
}
Bien "Entorno listo."

# ---------------------------------------------------------------- 4. paquetes
Paso "4 de 6: instalando las piezas (esto es lo que mas tarda)"
& "$destino\\venv\\Scripts\\python.exe" -m pip install --no-index `
    --find-links (Join-Path $aqui "Paquetes") `
    -r (Join-Path $aqui "requisitos.txt") --quiet
if ($LASTEXITCODE -ne 0) {
  Ojo "Sin internet no ha podido con todo. Reintentando con internet..."
  & "$destino\\venv\\Scripts\\python.exe" -m pip install `
      -r (Join-Path $aqui "requisitos.txt") --quiet
  if ($LASTEXITCODE -ne 0) { Write-Host "No se han podido instalar las piezas." -ForegroundColor Red; exit 1 }
}
Bien "Piezas instaladas."

# ---------------------------------------------------------------- 5. modelos y datos
Paso "5 de 6: poniendo el oido y tus datos"
$oido = Join-Path $aqui "Modelo-de-oido"
if (Test-Path $oido) {
  $cache = "$env:USERPROFILE\\.cache\\huggingface"
  New-Item -ItemType Directory -Force -Path $cache | Out-Null
  Copy-Item -Path "$oido\\*" -Destination $cache -Recurse -Force
  Bien "Oido puesto (no tendra que descargarlo)."
}
$priv = Join-Path $aqui "TUS-DATOS-PRIVADOS"
if (Test-Path $priv) {
  Get-ChildItem -Path $priv -Filter "*.json" | ForEach-Object {
    Copy-Item $_.FullName -Destination $destino -Force
  }
  Bien "Tus claves y tu memoria, puestas."
  if (Test-Path (Join-Path $priv "programas")) {
    New-Item -ItemType Directory -Force -Path "$destino\\programas" | Out-Null
    Copy-Item -Path (Join-Path $priv "programas\\*") -Destination "$destino\\programas" -Recurse -Force
    Bien "Los programas que Sobri te ha escrito, tambien."
  }
} else {
  Ojo "Sin la carpeta TUS-DATOS-PRIVADOS: tendras que darle las claves."
  Ojo "Cuando arranque, pideselo a Sobri o escribelas en config.json."
}

# ---------------------------------------------------------------- 6. acceso directo
Paso "6 de 6: creando el acceso directo"
$ws = New-Object -ComObject WScript.Shell
# El escritorio de verdad. Con OneDrive sincronizandolo NO es
# $env:USERPROFILE\\Desktop, y el acceso directo acababa en una carpeta que
# el dueno del ordenador no ve nunca.
$escritorio = [Environment]::GetFolderPath("Desktop")
$lnk = $ws.CreateShortcut("$escritorio\\$atajo.lnk")
$lnk.TargetPath = "$destino\\venv\\Scripts\\pythonw.exe"
$lnk.Arguments = "`"$destino\\asistente.py`""
$lnk.WorkingDirectory = $destino
$lnk.Description = "Sobri, tu asistente"
$lnk.Save()
Bien "Acceso directo '$atajo' en el escritorio."

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "   LISTO. Sobri esta instalado." -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "   Doble clic en '$atajo' en el escritorio."
Write-Host ""
Write-Host "   Dos cosas de la primera vez:" -ForegroundColor White
Write-Host "   - Si Windows pregunta por la camara o el microfono, di que si."
Write-Host "   - Para tu Gmail y tu agenda hay que volver a autorizar Google."
Write-Host ""
$r = Read-Host "   Quieres abrirlo ahora? (S/N)"
if ($r -eq "S" -or $r -eq "s") {
  Start-Process -FilePath "$destino\\venv\\Scripts\\pythonw.exe" `
                -ArgumentList "$destino\\asistente.py" -WorkingDirectory $destino
}
"""


# ------------------------------------------------------------------ marcha
def sincronizar(forzar=False):
    """Hace el volcado y devuelve el parte por escrito.

    Devuelve texto en vez de imprimirlo para que Sobri pueda usarlo como
    herramienta y contarselo a Angel de viva voz.
    """
    t0 = time.time()
    cuenta["copiados"] = cuenta["iguales"] = cuenta["carpetas"] = 0
    lineas = ["Volcando Sobri a: %s" % DESTINO]
    os.makedirs(DESTINO, exist_ok=True)

    volcar_programa()
    sobras = limpiar_sobras()
    if sobras:
        lineas.append("  quitado lo que ya no existe: %s" % ", ".join(sobras))
    config_sin_claves()
    volcar_privados()
    escribir_textos()
    cambio, n, aviso = requisitos()
    lineas.append("  requisitos.txt: %d paquetes%s"
                  % (n, " (han cambiado)" if cambio else ""))
    if aviso:
        lineas.append("  OJO con requisitos.txt: " + aviso)
    if volcar_oido():
        lineas.append("  modelo del oido: puesto")
    lineas.append("  paquetes: " + bajar_paquetes(forzar or cambio))

    if not os.path.isdir(PYTHON_DIR) or not os.listdir(PYTHON_DIR):
        lineas.append("  OJO: falta el instalador de Python en %s" % PYTHON_DIR)

    lineas.append("")
    lineas.append("Archivos copiados: %d   sin cambios: %d"
                  % (cuenta["copiados"], cuenta["iguales"]))
    lineas.append("Tamano total de la carpeta: %.0f MB"
                  % (_tam(DESTINO) / 1024.0 / 1024.0))
    lineas.append("Tardado: %.1f s" % (time.time() - t0))
    return "\n".join(lineas)


def actualizar_carpeta_del_pen():
    """Herramienta: deja la carpeta del escritorio con la ultima version."""
    try:
        parte = sincronizar()
    except Exception as e:
        return ("No he podido actualizar la carpeta de instalacion: %s. "
                "Diselo a Angel tal cual." % e)
    return (parte + "\n\nCuentaselo en una frase: que la carpeta 'Instalar "
            "Sobri' del escritorio ya tiene la ultima version, y que puede "
            "copiarla al pen cuando quiera.")


def main():
    print(sincronizar(forzar="--paquetes" in sys.argv))


if __name__ == "__main__":
    main()
