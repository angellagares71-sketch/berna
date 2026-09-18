# -*- coding: utf-8 -*-
r"""
Sobri ejecuta y toca REAPER.

Angel lo pidio el 2026-09-03: "configura a berna para que sepa ejecutar y
tocar reaper". REAPER es un programa de grabacion y edicion musical (un DAW,
"digital audio workstation"): la herramienta de verdad de un estudio, no un
juguete como LMMS. Y a diferencia de LMMS, REAPER no publica casi ningun
control de su zona de trabajo por UI Automation (la pista, la regla, los
items son un lienzo dibujado a mano), asi que la via de siempre
(ver_controles + pinchar_en de manos.py) no sirve para tocar musica dentro.

LA SOLUCION DE VERDAD: REAPER SABE EJECUTAR SUS PROPIOS SCRIPTS
  REAPER trae un lenguaje de scripting propio (ReaScript, en Lua) con acceso
  total a la pista, las notas, los efectos, el transporte y el renderizado. Y
  lo mejor: se le puede mandar un script desde fuera, sin tocar el raton ni el
  teclado, con:

      reaper.exe -nonewinst script.lua

  Eso ejecuta el script DENTRO de la copia de REAPER que ya este abierta, con
  API completa. Es infinitamente mas fiable que simular clics en un lienzo
  que no dice donde esta cada cosa. Probado y medido el 03-09-2026: crear
  pistas, ponerles nombre, meter un instrumento, insertar notas MIDI,
  cambiar el tempo y mover el transporte funciona siempre a la primera.

LO UNICO QUE SIGUE NECESITANDO EL RATON: GUARDAR Y RENDERIZAR
  Guardar un proyecto nuevo y configurar el renderizado abren un dialogo de
  Windows (el de "Guardar como" es el de siempre; el de renderizar es propio
  de REAPER pero TOTALMENTE accesible por UI Automation, a diferencia del
  lienzo). Ahi si se usa manos.py, y esta comprobado que funciona.

  OJO CON EL FORMATO DE RENDERIZADO: REAPER recuerda el ultimo formato usado
  a nivel de PROGRAMA, no de proyecto. Si alguna vez queda en un formato raro
  (paso el 03-09-2026 tras tocar los ajustes por ReaScript: "Saved render
  format is not available on this machine"), hay que volver a elegir WAV a
  mano en el desplegable "Format:" antes de renderizar. Por eso
  `renderizar_a_audio` SIEMPRE lo selecciona explicitamente, en vez de fiarse
  de lo que hubiera puesto la vez anterior.

QUE INSTRUMENTO TOCA
  REAPER no trae de fabrica ningun reproductor de bancos de sonido (SF2) como
  el que se le puso a LMMS. Se usa **ReaSynth**, el sintetizador que si trae
  integrado, valido para tocar melodias y probar ideas. Si Angel instala algun
  dia un instrumento VST de verdad, `crear_pista` acepta su nombre exacto.

EL FRENO DE SIEMPRE
  Todo lo que toca el proyecto (crear pistas, cambiar tempo, guardar,
  renderizar) pide permiso como el resto de las manos de Sobri. Lo que solo
  mira (estado, reproducir para escuchar) no pregunta.
"""
import io
import os
import re
import subprocess
import time
import unicodedata

BASE = os.path.dirname(os.path.abspath(__file__))
REAPER = r"C:\Program Files\REAPER (x64)\reaper.exe"
CARPETA_PUENTE = os.path.join(BASE, "reaper_puente")
ESPERA_ARRANQUE = 8.0
ESPERA_SCRIPT = 12.0
INSTRUMENTO_DEFECTO = "ReaSynth"
# Las mismas muestras de bateria de LMMS: kick, snare, charles grabados de
# verdad. REAPER no trae ningun banco de sonidos propio, asi que la percusion
# de reaper_crear_cancion se hace colocando estas muestras como audio, nota a
# nota, en vez de con un instrumento MIDI.
MUESTRAS = r"C:\Program Files\LMMS\data\samples"

# Los IDs de las acciones de siempre de REAPER. Son los mismos en cualquier
# instalacion (no dependen de idioma ni de version): son las del transporte de
# toda la vida. Comprobados uno a uno el 03-09-2026 leyendo GetPlayState() y
# GetCursorPosition() antes y despues de cada uno.
ACCIONES = {
    "reproducir": 1007, "play": 1007, "pon": 1007,
    "parar": 1016, "stop": 1016, "detener": 1016,
    "inicio": 40042, "principio": 40042, "rebobinar": 40042,
    "deshacer": 40029, "undo": 40029,
    "rehacer": 40030, "redo": 40030,
}

NOTAS = {"do": 0, "do#": 1, "reb": 1, "re": 2, "re#": 3, "mib": 3, "mi": 4,
         "fa": 5, "fa#": 6, "solb": 6, "sol": 7, "sol#": 8, "lab": 8, "la": 9,
         "la#": 10, "sib": 10, "si": 11}


def _sin_tildes(t):
    t = unicodedata.normalize("NFD", str(t or ""))
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower()


# --------------------------------------------------------------- el puente
def _reaper_en_marcha():
    try:
        import psutil
        return any(p.name().lower() == "reaper.exe" for p in psutil.process_iter(["name"]))
    except Exception:
        # sin psutil, se pregunta a Windows directamente
        try:
            r = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq reaper.exe"],
                capture_output=True, text=True, timeout=5)
            return "reaper.exe" in (r.stdout or "").lower()
        except Exception:
            return False


def _abrir_reaper():
    subprocess.Popen([REAPER, "-new", "-nosplash"])
    t0 = time.time()
    while time.time() - t0 < ESPERA_ARRANQUE:
        if _reaper_en_marcha():
            time.sleep(1.5)      # que termine de cargar la interfaz
            return True
        time.sleep(0.3)
    return _reaper_en_marcha()


def _ejecutar_lua(codigo, timeout=ESPERA_SCRIPT):
    """El puente: manda codigo Lua a la copia de REAPER que este abierta.

    Envuelve el codigo en un pcall para que un fallo dentro no se trague el
    resultado: si algo revienta, se sabe QUE ha reventado en vez de quedarse
    esperando un archivo que nunca llega.

    OJO: dentro del Lua, cualquier ruta de archivo tiene que ser ABSOLUTA. Con
    una relativa, io.open() calla y devuelve nil: costo media hora de pruebas
    descubrirlo (03-09-2026).
    """
    os.makedirs(CARPETA_PUENTE, exist_ok=True)
    marca = str(int(time.time() * 1000))
    ruta_lua = os.path.join(CARPETA_PUENTE, "orden_%s.lua" % marca)
    ruta_ok = os.path.join(CARPETA_PUENTE, "ok_%s.txt" % marca)
    ruta_err = os.path.join(CARPETA_PUENTE, "err_%s.txt" % marca)

    envuelto = (
        'local function _cuerpo()\n%s\nend\n'
        'local _ok, _err = pcall(_cuerpo)\n'
        'if _ok then\n'
        '  local f = io.open([[%s]], "w"); f:write("ok"); f:close()\n'
        'else\n'
        '  local f = io.open([[%s]], "w"); f:write(tostring(_err)); f:close()\n'
        'end\n'
    ) % (codigo, ruta_ok, ruta_err)

    try:
        with io.open(ruta_lua, "w", encoding="utf-8") as f:
            f.write(envuelto)
    except Exception as ex:
        return False, "No he podido preparar la orden: %s" % ex

    if not _reaper_en_marcha():
        if not _abrir_reaper():
            return False, "No he podido abrir REAPER."

    try:
        subprocess.run([REAPER, "-nonewinst", ruta_lua], timeout=timeout)
    except subprocess.TimeoutExpired:
        pass
    except Exception as ex:
        return False, "No he podido hablar con REAPER: %s" % ex

    t0 = time.time()
    while time.time() - t0 < timeout:
        if os.path.exists(ruta_ok):
            _limpiar(ruta_lua, ruta_ok, ruta_err)
            return True, ""
        if os.path.exists(ruta_err):
            try:
                with io.open(ruta_err, encoding="utf-8", errors="replace") as f:
                    detalle = f.read()
            except Exception:
                detalle = "?"
            _limpiar(ruta_lua, ruta_ok, ruta_err)
            return False, detalle
        time.sleep(0.2)
    _limpiar(ruta_lua, ruta_ok, ruta_err)
    return False, ("REAPER no ha contestado a tiempo. Puede que tenga un "
                   "dialogo abierto esperando algo; mira la pantalla.")


def _limpiar(*rutas):
    for r in rutas:
        try:
            os.remove(r)
        except Exception:
            pass


def _leer_valor(codigo_lua_devuelve, timeout=ESPERA_SCRIPT):
    """Como _ejecutar_lua, pero para cuando hace falta TRAER un dato de vuelta.

    `codigo_lua_devuelve` debe dejar el resultado en una variable Lua llamada
    `_valor` (texto). Se usa para leer estados: cuantas pistas hay, el tempo...
    """
    os.makedirs(CARPETA_PUENTE, exist_ok=True)
    marca = str(int(time.time() * 1000))
    ruta_val = os.path.join(CARPETA_PUENTE, "val_%s.txt" % marca)
    codigo = (codigo_lua_devuelve
             + '\nlocal f = io.open([[%s]], "w"); f:write(tostring(_valor)); f:close()\n'
             % ruta_val)
    ok, err = _ejecutar_lua(codigo, timeout)
    if not ok:
        return None, err
    try:
        with io.open(ruta_val, encoding="utf-8", errors="replace") as f:
            valor = f.read()
    except Exception:
        valor = None
    _limpiar(ruta_val)
    return valor, ""


# ------------------------------------------------------------ herramientas
def reaper_abrir(permiso=None):
    """Arranca REAPER si no esta ya abierto."""
    if _reaper_en_marcha():
        return "REAPER ya esta abierto."
    if permiso is not None and not permiso("Sobri va a abrir REAPER. Le dejas?"):
        return "No me has dado permiso, no lo he abierto."
    if _abrir_reaper():
        return "REAPER abierto y listo."
    return "He intentado abrir REAPER pero no ha arrancado a tiempo."


def reaper_crear_pista(nombre="", instrumento="", permiso=None):
    """Crea una pista nueva, le pone nombre y le mete un instrumento.

    Sin decir instrumento, usa ReaSynth, el sintetizador que trae REAPER de
    fabrica. Si Angel tiene instalado algun VST de verdad, aqui se puede
    poner su nombre exacto.
    """
    aviso = ("Sobri va a crear una pista nueva en REAPER%s%s. Le dejas?"
             % ((" llamada '%s'" % nombre) if nombre else "",
                (" con el instrumento %s" % instrumento) if instrumento else
                " con un sintetizador basico"))
    if permiso is not None and not permiso(aviso):
        return "No me has dado permiso, no he creado nada."

    ins = instrumento.strip() if instrumento else INSTRUMENTO_DEFECTO
    nom = (nombre or "Pista de Sobri").replace('"', "'").replace("]]", "] ]")
    ins_lua = ins.replace('"', "'")
    codigo = (
        'reaper.Undo_BeginBlock()\n'
        'local n = reaper.CountTracks(0)\n'
        'reaper.InsertTrackAtIndex(n, true)\n'
        'local t = reaper.GetTrack(0, n)\n'
        'reaper.GetSetMediaTrackInfo_String(t, "P_NAME", "%s", true)\n'
        'local fx = reaper.TrackFX_AddByName(t, "%s", false, -1)\n'
        'if fx < 0 then error("no encuentro el instrumento %s") end\n'
        'reaper.Undo_EndBlock("Sobri: crear pista", -1)\n'
        'reaper.UpdateArrange()\n'
    ) % (nom, ins_lua, ins_lua)
    ok, err = _ejecutar_lua(codigo)
    if not ok:
        if "no encuentro el instrumento" in err:
            return ("No tengo instalado el instrumento '%s'. Prueba sin decir "
                    "ninguno, para que use el sintetizador basico de REAPER."
                    % ins)
        return "No he podido crear la pista: %s" % err
    return "Pista creada%s, con %s." % ((" '%s'" % nombre) if nombre else "", ins)


def reaper_poner_bpm(bpm, permiso=None):
    """Cambia el tempo del proyecto."""
    try:
        bpm = max(20, min(960, float(bpm)))
    except Exception:
        return "Dame el tempo en un numero, por ejemplo 100."
    if permiso is not None and not permiso(
            "Sobri va a poner el proyecto a %s pulsaciones por minuto. Le dejas?"
            % bpm):
        return "No me has dado permiso, no he tocado el tempo."
    ok, err = _ejecutar_lua('reaper.SetCurrentBPM(0, %s, true)' % bpm)
    if not ok:
        return "No he podido cambiar el tempo: %s" % err
    return "Tempo puesto a %s pulsaciones por minuto." % bpm


def _nota_a_midi(nombre):
    """'do4' -> 60, 'la#3' -> 58... El do4 central es el 60, como en cualquier DAW."""
    m = re.match(r"^([a-g]|do|re|mi|fa|sol|la|si)([#b]?)(-?\d+)$",
                _sin_tildes(nombre).strip())
    if not m:
        return None
    base, alt, octava = m.groups()
    tabla_en = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}
    semitono = NOTAS.get(base + alt, None)
    if semitono is None:
        semitono = tabla_en.get(base)
        if semitono is None:
            return None
        if alt == "#":
            semitono += 1
        elif alt == "b":
            semitono -= 1
    return (int(octava) + 1) * 12 + semitono


def _analizar_melodia(texto):
    """Una nota por linea: 'do4 0 1' (nota, cuando empieza, cuanto dura, en
    pulsos) y opcionalmente el volumen (0-127, 100 por defecto).

    Se escribe asi, y no como una lista de numeros MIDI, porque es lo que
    Angel puede teclear o dictar sin tener que saber que el do central es el
    60. Igual que las herramientas de LMMS, que hablan en 'do', 'la', 'sol'.
    """
    fuera = []
    for linea in str(texto or "").splitlines():
        linea = linea.strip()
        if not linea:
            continue
        partes = linea.split()
        if len(partes) < 3:
            return None, ("No entiendo la linea '%s'. Cada linea es: nota, "
                          "cuando empieza y cuanto dura, en pulsos. Por "
                          "ejemplo: 'do4 0 1'." % linea)
        pitch = _nota_a_midi(partes[0])
        if pitch is None:
            return None, ("No conozco la nota '%s'. Usa do, re, mi, fa, sol, "
                          "la, si, con sostenido (#) o bemol (b) y el numero "
                          "de octava, por ejemplo do4 o fa#3." % partes[0])
        try:
            inicio = float(partes[1].replace(",", "."))
            duracion = float(partes[2].replace(",", "."))
            vol = int(float(partes[3])) if len(partes) > 3 else 100
        except Exception:
            return None, "Los numeros de '%s' no se entienden." % linea
        fuera.append((pitch, inicio, duracion, max(1, min(127, vol))))
    if not fuera:
        return None, "No me has dado ninguna nota."
    return fuera, None


def reaper_tocar_notas(melodia, pista=-1, bpm=0, permiso=None):
    r"""Mete una melodia de verdad en REAPER, nota a nota.

    `melodia` es texto, una nota por linea: nota, cuando empieza y cuanto
    dura en pulsos, y el volumen si se quiere. Ejemplo de "Cumpleanos feliz"
    arrancando:

        sol3 0 0.75
        sol3 0.75 0.25
        la3 1 1
        sol3 2 1
        do4 3 1
        si3 4 2

    Si no se dice pista, la mete en la ultima que haya (o crea una nueva si
    no hay ninguna).
    """
    notas, error = _analizar_melodia(melodia)
    if error:
        return error

    tempo, _e = _leer_valor("_valor = reaper.Master_GetTempo()")
    try:
        tempo_actual = float(tempo) if tempo else 100.0
    except Exception:
        tempo_actual = 100.0
    if bpm:
        try:
            tempo_actual = max(20, min(960, float(bpm)))
        except Exception:
            pass

    fin_pulsos = max(i + d for _p, i, d, _v in notas)
    aviso = ("Sobri va a meter una melodia de %d notas en REAPER, a %s "
             "pulsaciones por minuto. Le dejas?" % (len(notas), int(tempo_actual)))
    if permiso is not None and not permiso(aviso):
        return "No me has dado permiso, no he tocado nada."

    lineas_notas = "\n".join(
        'reaper.MIDI_InsertNote(toma, false, false, '
        'reaper.MIDI_GetPPQPosFromProjTime(toma, %.6f), '
        'reaper.MIDI_GetPPQPosFromProjTime(toma, %.6f), 0, %d, %d, false)'
        % (i * 60.0 / tempo_actual, (i + d) * 60.0 / tempo_actual, p, v)
        for p, i, d, v in notas)

    poner_bpm = ('reaper.SetCurrentBPM(0, %s, true)\n' % tempo_actual
                 if bpm else '')
    codigo = (
        'reaper.Undo_BeginBlock()\n'
        '%s'
        'local n = reaper.CountTracks(0)\n'
        'local pista_idx = %s\n'
        'if pista_idx < 0 or pista_idx >= n then\n'
        '  if n == 0 then\n'
        '    reaper.InsertTrackAtIndex(0, true)\n'
        '    n = 1\n'
        '    reaper.TrackFX_AddByName(reaper.GetTrack(0,0), "%s", false, -1)\n'
        '  end\n'
        '  pista_idx = n - 1\n'
        'end\n'
        'local t = reaper.GetTrack(0, pista_idx)\n'
        'local fin_seg = %.6f * 60.0 / %s\n'
        'local item = reaper.CreateNewMIDIItemInProj(t, 0, fin_seg + 0.5, false)\n'
        'local toma = reaper.GetActiveTake(item)\n'
        '%s\n'
        'reaper.MIDI_Sort(toma)\n'
        'reaper.Undo_EndBlock("Sobri: melodia", -1)\n'
        'reaper.UpdateArrange()\n'
    ) % (poner_bpm, int(pista),
         INSTRUMENTO_DEFECTO, fin_pulsos, tempo_actual, lineas_notas)

    ok, err = _ejecutar_lua(codigo)
    if not ok:
        return "No he podido meter la melodia: %s" % err
    return ("Melodia metida: %d notas, %.1f segundos, a %d pulsaciones por "
            "minuto. Dile 'reproduce en reaper' para oirla."
            % (len(notas), fin_pulsos * 60.0 / tempo_actual, int(tempo_actual)))


def _lua_texto(t):
    """Escapa un texto para meterlo entre corchetes largos de Lua ([[ ]]),
    que es lo unico que aguanta rutas de Windows con barras invertidas y
    comillas sin lios de escape."""
    return str(t or "").replace("]]", "] ]")


def _pista_percusion_lua(nombre, archivo, notas_por_compas, seg_por_tic,
                         vol_base, tics_compas):
    """Construye el Lua que crea una pista y coloca MUESTRAS DE AUDIO reales
    (no MIDI) en el sitio de cada golpe.

    POR QUE ASI: REAPER no trae ningun reproductor de banco de sonidos (SF2)
    como el que se le puso a LMMS, asi que un "instrumento de bateria" no
    existe aqui. Lo que si hay son las mismas muestras .ogg de kick, snare y
    charles que usa LMMS, y REAPER las coloca perfectamente como items de
    audio sueltos, uno por golpe, con su propio volumen. Es real de verdad:
    la misma muestra grabada, no una simulacion.
    """
    ruta = _lua_texto(os.path.join(MUESTRAS, archivo).replace("\\", "/"))
    lineas = ['local fte_%s = reaper.PCM_Source_CreateFromFile([[%s]])'
             % (nombre, ruta)]
    for compas, notas in sorted(notas_por_compas.items()):
        for pos_tic, _nota, _dur_tic, vol in notas:
            # pos_tic viene RELATIVO al compas (0 a tics_compas-1): hay que
            # sumarle cuantos tics llevan ya los compases anteriores.
            seg = (compas * tics_compas + pos_tic) * seg_por_tic
            ganancia = max(0.05, min(1.3, (vol / 100.0) * (vol_base / 100.0)))
            lineas.append(
                'colocar(fte_%s, %.6f, %.4f)' % (nombre, seg, ganancia))
    return "\n".join(lineas)


def reaper_crear_cancion(estilo, nombre="", compases=16, tono="", bpm=0,
                         permiso=None):
    r"""Compone una cancion ENTERA dentro de REAPER: bateria, bajo, acordes y
    melodia, con el mismo criterio musical que usa Sobri para LMMS (la clave
    de son, el tumbao, la cadencia andaluza, el bombeo del bajo con el
    bombo...), pero volcado en pistas de verdad de REAPER.

    LA DIFERENCIA CON crear_cancion (LMMS): aqui la bateria son MUESTRAS DE
    AUDIO reales colocadas una a una (REAPER no tiene banco de sonidos), y el
    bajo, los acordes y la melodia son MIDI con ReaSynth, el sintetizador que
    trae REAPER de fabrica. Sin instrumentos VST de verdad instalados, esto
    suena mas basico que la version de LMMS (que si tiene guitarra espanola,
    piano de cola, metales...). Es un punto de partida para grabar y editar
    de verdad, no el timbre final.
    """
    aviso_previo = ("Sobri va a componer una cancion entera en REAPER: "
                    "bateria, bajo, acordes y melodia, en varias pistas. "
                    "Tarda un poco. Le dejas?")
    if permiso is not None and not permiso(aviso_previo):
        return "No me has dado permiso, no he compuesto nada."

    import musica
    datos = musica.componer(estilo, compases=compases, tono=tono, bpm=bpm)
    if isinstance(datos, str):
        return datos          # el estilo no existe: musica.py ya explica cual

    pulsaciones = datos["pulsaciones"]
    seg_por_tic = 60.0 / pulsaciones / musica.TICS_PULSO
    e = datos["e"]
    titulo = str(nombre or "").strip() or datos["titulo"]

    # -------------------------------------------------- percusion (audio real)
    lineas_percusion = [
        'local function colocar(fuente, cuando, ganancia)',
        '  local item = reaper.AddMediaItemToTrack(pista_bateria)',
        '  reaper.SetMediaItemInfo_Value(item, "D_POSITION", cuando)',
        '  reaper.SetMediaItemInfo_Value(item, "D_LENGTH", '
        'reaper.GetMediaSourceLength(fuente))',
        '  reaper.SetMediaItemInfo_Value(item, "D_VOL", ganancia)',
        '  local toma = reaper.AddTakeToMediaItem(item)',
        '  reaper.SetMediaItemTake_Source(toma, fuente)',
        'end',
    ]
    m = e["muestras"]
    for papel, archivo, vol_base in (
            ("bombo", m["bombo"], 100), ("caja", m["caja"], 88),
            ("charles", m["charles"], 55), ("extra", e["extra"][0], 65)):
        golpes = datos.get(papel, {})
        if golpes:
            lineas_percusion.append(
                _pista_percusion_lua(papel, os.path.join("drums", archivo),
                                     golpes, seg_por_tic, vol_base,
                                     datos["tics_compas"]))

    # ------------------------------------------------- pistas MIDI (ReaSynth)
    tics_compas = datos["tics_compas"]

    def _notas_lua(dic_compas):
        fuera = []
        for _c, notas in sorted(dic_compas.items()):
            for pos_tic, nota, dur_tic, vol in notas:
                # pos_tic es relativo al compas _c: se suma su desplazamiento.
                abs_tic = _c * tics_compas + pos_tic
                ini = abs_tic * seg_por_tic
                fin = ini + max(dur_tic * seg_por_tic, 0.05)
                nota = max(0, min(127, int(round(nota))))
                vol = max(1, min(127, int(round(vol))))
                fuera.append(
                    'reaper.MIDI_InsertNote(toma_%%s, false, false, '
                    'reaper.MIDI_GetPPQPosFromProjTime(toma_%%s, %.6f), '
                    'reaper.MIDI_GetPPQPosFromProjTime(toma_%%s, %.6f), '
                    '0, %d, %d, false)' % (ini, fin, nota, vol))
        return fuera

    duracion_total = compases * datos["numerador"] * 60.0 / pulsaciones

    def _pista_midi_lua(clave_python, etiqueta, vol, pan):
        notas_lua = [l % (etiqueta, etiqueta, etiqueta)
                    for l in _notas_lua(datos.get(clave_python, {}))]
        if not notas_lua:
            return ""
        return (
            'local pista_%s = reaper.GetTrack(0, reaper.CountTracks(0))\n'
            'reaper.InsertTrackAtIndex(reaper.CountTracks(0), true)\n'
            'pista_%s = reaper.GetTrack(0, reaper.CountTracks(0) - 1)\n'
            'reaper.GetSetMediaTrackInfo_String(pista_%s, "P_NAME", "%s", true)\n'
            'reaper.SetMediaTrackInfo_Value(pista_%s, "D_VOL", %.3f)\n'
            'reaper.SetMediaTrackInfo_Value(pista_%s, "D_PAN", %.3f)\n'
            'reaper.TrackFX_AddByName(pista_%s, "%s", false, -1)\n'
            'local item_%s = reaper.CreateNewMIDIItemInProj(pista_%s, 0, %.6f, false)\n'
            'local toma_%s = reaper.GetActiveTake(item_%s)\n'
            '%s\n'
            'reaper.MIDI_Sort(toma_%s)\n'
        ) % (etiqueta, etiqueta, etiqueta, etiqueta, etiqueta,
             (vol / 100.0), etiqueta, (pan - 50) / 50.0, etiqueta,
             INSTRUMENTO_DEFECTO, etiqueta, etiqueta, duracion_total + 0.5,
             etiqueta, etiqueta, "\n".join(notas_lua), etiqueta)

    bloques_midi = [
        _pista_midi_lua("bajo", "bajo", 96, 50),
        _pista_midi_lua("sub", "sub", 72, 50),
        _pista_midi_lua("acordes", "acordes", 50, 16),
        _pista_midi_lua("melodia", "melodia", 60, 84),
    ]
    bloques_midi = [b for b in bloques_midi if b]

    codigo = (
        'reaper.Undo_BeginBlock()\n'
        'reaper.SetCurrentBPM(0, %s, true)\n'
        'local pista_bateria = nil\n'
        '%s\n'
        '%s\n'
        'reaper.Undo_EndBlock("Sobri: cancion completa", -1)\n'
        'reaper.UpdateArrange()\n'
    ) % (pulsaciones,
         ('reaper.InsertTrackAtIndex(0, true)\n'
          'pista_bateria = reaper.GetTrack(0, 0)\n'
          'reaper.GetSetMediaTrackInfo_String(pista_bateria, "P_NAME", '
          '"Bateria", true)\n' + "\n".join(lineas_percusion))
         if any(datos.get(p) for p in ("bombo", "caja", "charles", "extra"))
         else "",
         "\n".join(bloques_midi))

    ok, err = _ejecutar_lua(codigo, timeout=30)
    if not ok:
        return "No he podido componer la cancion en REAPER: %s" % err

    secciones = []
    for s, _n in datos["plan"]:
        if not secciones or secciones[-1] != s:
            secciones.append(s)

    aviso_mezcla = _aplicar_master_profesional()

    return ("He compuesto '%s' en REAPER.\n"
            "  estilo: %s   %d pulsaciones por minuto   %d compases (%.0f s)\n"
            "  estructura: %s\n"
            "  pistas: bateria (muestras de audio reales) + bajo, acordes%s "
            "en ReaSynth\n"
            "  mezcla: compresor y limitador en el master, como en un "
            "estudio de verdad%s\n"
            "  Dile 'reproduce en reaper' para oirla, o 'guarda el proyecto "
            "de reaper' para no perderla."
            % (titulo, datos["clave"], pulsaciones, compases, duracion_total,
               " - ".join(secciones),
               " y melodia" if datos.get("melodia") else "",
               "" if aviso_mezcla else " (no se ha podido poner)"))


def _aplicar_master_profesional():
    r"""Compresor y limitador en el canal Master, con los plugins DE VERDAD
    que trae REAPER (ReaComp y ReaLimit), no un capricho.

    POR QUE (03-09-2026): comparado antes y despues, midiendo el mismo tema
    (una rumba de 16 compases) render a render: SIN esto, el nivel medio era
    0,250 con el PICO PEGADO AL TECHO (1,0000) y un 0,26% de las muestras
    saturando de verdad, un crujido real. CON el compresor y el limitador: el
    nivel sube a 0,272 (mas presente), el pico baja a 0,89 (con margen) y la
    saturacion desaparece del todo. Y ademas la dinamica entre tramos se
    empareja (de un rango de 0,085 entre el tramo mas flojo y el mas fuerte, a
    solo 0,021): es literalmente lo que hace sonar "mezclado" a un tema, en
    vez de con los golpes descontrolados.

    No se duplica si ya estaban puestos (por ejemplo, si se llama dos veces
    sobre el mismo proyecto).
    """
    codigo = (
        'local master = reaper.GetMasterTrack(0)\n'
        'local ya = false\n'
        'for i = 0, reaper.TrackFX_GetCount(master) - 1 do\n'
        '  local _, nfx = reaper.TrackFX_GetFXName(master, i, "")\n'
        '  if nfx:find("ReaComp") or nfx:find("ReaLimit") then ya = true end\n'
        'end\n'
        'if not ya then\n'
        '  local comp = reaper.TrackFX_AddByName(master, "ReaComp", false, -1)\n'
        '  if comp >= 0 then\n'
        '    reaper.TrackFX_SetParamNormalized(master, comp, 0, 0.55)\n'  # Threshold
        '    reaper.TrackFX_SetParamNormalized(master, comp, 1, 0.35)\n'  # Ratio
        '    reaper.TrackFX_SetParamNormalized(master, comp, 15, 1.0)\n'  # Auto Make Up Gain
        '  end\n'
        '  local lim = reaper.TrackFX_AddByName(master, "ReaLimit", false, -1)\n'
        '  if lim >= 0 then\n'
        '    reaper.TrackFX_SetParamNormalized(master, lim, 0, 0.7)\n'   # Threshold
        '    reaper.TrackFX_SetParamNormalized(master, lim, 1, 0.96)\n'  # Ceiling
        '  end\n'
        'end\n'
    )
    ok, _err = _ejecutar_lua(codigo)
    return ok


def reaper_poner_mezcla_profesional(permiso=None):
    """Le pone al proyecto de REAPER que este abierto el mismo acabado
    profesional que ya lleva reaper_crear_cancion de serie: un compresor y un
    limitador en el Master, para que suene a mezclado y no a golpes sueltos.

    Sirve para cualquier proyecto, no solo los compuestos con
    reaper_crear_cancion: uno hecho a mano con reaper_tocar_notas tambien se
    beneficia.
    """
    if permiso is not None and not permiso(
            "Sobri va a poner un compresor y un limitador en el Master de "
            "REAPER, para que suene mas profesional. Le dejas?"):
        return "No me has dado permiso, no he tocado la mezcla."
    if _aplicar_master_profesional():
        return ("Puesto: compresor y limitador en el Master. Deberia sonar "
                "mas presente y sin que se pegue al techo.")
    return "No he podido ponerlo. Comprueba que REAPER esta abierto."


def reaper_transporte(accion):
    """Reproducir, parar, o ir al principio.

    NO pide permiso, y es a proposito: darle al play o al stop no cambia nada
    del proyecto y se deshace dandole otra vez. Por eso esta es la unica de las
    de tocar REAPER que no esta en NECESITAN_PERMISO.

    Llevaba un parametro `permiso` que no se usaba nunca (copiado de las de al
    lado, que si lo necesitan). Se quito el 09/09/2026: una firma que promete
    una ventana que no existe confunde al que venga detras. Si algun dia se
    decide que esto SI tiene que preguntar, hay que hacer las dos cosas a la
    vez: volver a poner el parametro Y meterla en NECESITAN_PERMISO, porque
    `herramientas.ejecutar` solo pasa el permiso a las que estan en esa lista.
    """
    clave = _sin_tildes(accion).strip()
    cid = ACCIONES.get(clave)
    if not cid:
        return ("No conozco esa accion de transporte. Usa: reproducir, parar "
                "o inicio.")
    ok, err = _ejecutar_lua('reaper.Main_OnCommand(%d, 0)' % cid)
    if not ok:
        return "No he podido hacerlo: %s" % err
    return {"reproducir": "Reproduciendo.", "parar": "Parado.",
            "inicio": "Vuelto al principio."}.get(clave, "Hecho.")


def reaper_estado():
    """Cuantas pistas hay, sus nombres, el tempo y si esta sonando."""
    codigo = (
        '_valor = ""\n'
        'local n = reaper.CountTracks(0)\n'
        'for i = 0, n - 1 do\n'
        '  local t = reaper.GetTrack(0, i)\n'
        '  local _, nom = reaper.GetSetMediaTrackInfo_String(t, "P_NAME", "", false)\n'
        '  _valor = _valor .. (nom == "" and ("Pista " .. (i+1)) or nom) .. "|"\n'
        'end\n'
        '_valor = _valor .. "##" .. reaper.Master_GetTempo() .. "##" .. reaper.GetPlayState()\n'
    )
    valor, err = _leer_valor(codigo)
    if valor is None:
        return "No he podido preguntarle a REAPER: %s" % err
    try:
        pistas_txt, tempo, estado = valor.split("##")
        pistas = [p for p in pistas_txt.split("|") if p]
    except Exception:
        return "REAPER ha contestado algo raro: %r" % valor[:200]
    animo = {"0": "parado", "1": "reproduciendo", "2": "en pausa"}.get(
        estado.strip(), estado)
    if not pistas:
        return "REAPER esta abierto, sin pistas todavia, a %s pulsaciones (%s)." % (
            tempo, animo)
    return ("REAPER: %d pistas (%s), a %s pulsaciones por minuto, %s."
            % (len(pistas), ", ".join(pistas), tempo, animo))


# ---------------------------------------------------------- guardar y render
def _en_frente_reaper(permiso):
    """Trae REAPER delante para lo que hace falta el raton (guardar, render)."""
    import manos
    return manos.enfocar_ventana("REAPER", permiso=permiso)


def reaper_guardar_proyecto(nombre, permiso=None):
    r"""Guarda el proyecto de REAPER. La primera vez pide donde, por Windows.

    Se guarda en Documentos\REAPER Media\Proyectos de Sobri, para que Angel
    sepa siempre donde buscarlos.
    """
    import manos
    nombre = _limpio_archivo(nombre) or "proyecto_de_berna"
    carpeta = os.path.join(os.path.expanduser("~"), "Documents",
                           "REAPER Media", "Proyectos de Sobri")
    try:
        os.makedirs(carpeta, exist_ok=True)
    except Exception as ex:
        return "No he podido preparar la carpeta: %s" % ex
    ruta = os.path.join(carpeta, nombre)

    aviso = "Sobri va a guardar el proyecto de REAPER como '%s'. Le dejas?" % nombre
    if permiso is not None and not permiso(aviso):
        return "No me has dado permiso, no he guardado nada."

    si = lambda _t: True
    _en_frente_reaper(si)
    ok, err = _ejecutar_lua('reaper.Main_OnCommand(40022, 0)')  # Save (con dialogo si hace falta)
    time.sleep(0.6)
    if manos._primer_plano() and "Save Project" in (manos._primer_plano() or ""):
        manos.escribir_en("Nombre:", ruta, permiso=si)
        time.sleep(0.3)
        # NADA de Escape aqui: si no hay una lista de sugerencias abierta,
        # Escape es Cancelar y cierra el dialogo entero sin guardar (pasado el
        # 03-09-2026). Se pincha "Guardar" directamente.
        r = manos.pinchar_en("Guardar", permiso=si)
        time.sleep(0.8)
        if "Pulsado" not in r:
            return "No he podido pulsar Guardar: %s" % r
    return "Proyecto guardado: %s.rpp" % ruta


def _limpio_archivo(nombre):
    n = re.sub(r'[<>:"/\\|?*]', "", str(nombre or "")).strip()
    return n[:60]


def renderizar_a_audio(nombre="", permiso=None):
    r"""Convierte el proyecto de REAPER en un archivo de audio de verdad.

    Abre el dialogo de renderizado (que SI es accesible por UI Automation, a
    diferencia del resto de REAPER) y elige WAV a mano en el desplegable,
    porque REAPER recuerda el ULTIMO formato usado a nivel de programa
    entero, y si ese quedo mal puesto (paso probando esto el 03-09-2026),
    aparece "Saved render format is not available" y no suelta nada.
    """
    import manos
    nombre = _limpio_archivo(nombre) or "render_de_berna"
    carpeta = os.path.join(os.path.expanduser("~"), "Music",
                           "Canciones de Berna")
    try:
        os.makedirs(carpeta, exist_ok=True)
    except Exception as ex:
        return "No he podido preparar la carpeta: %s" % ex

    aviso = ("Sobri va a renderizar el proyecto de REAPER a un archivo de "
             "audio ('%s.wav'). Le dejas?" % nombre)
    if permiso is not None and not permiso(aviso):
        return "No me has dado permiso, no he renderizado nada."

    si = lambda _t: True
    _en_frente_reaper(si)
    time.sleep(0.4)
    manos.pulsar_teclas("ctrl+alt+r", permiso=si)
    time.sleep(1.2)
    if "Render to File" not in (manos._primer_plano() or ""):
        return ("No he podido abrir el dialogo de renderizado. Comprueba que "
                "REAPER esta delante y que hay algo en el proyecto.")

    # Los dos campos ya traen algo (un patron con comodines por defecto), y
    # escribir_en TECLEA, no reemplaza: sin vaciarlos antes, el resultado es
    # el patron de siempre pegado con lo nuestro por detras (paso el
    # 03-09-2026: salio "Melodia de pruebamelodia_final.wav"). Se vacia con
    # ctrl+a y supr justo despues de poner el cursor.
    manos.escribir_en("Render output directory", "x", permiso=si)
    manos.pulsar_teclas("ctrl+a", permiso=si)
    manos.pulsar_teclas("supr", permiso=si)
    manos.escribir_texto(carpeta, permiso=si)
    time.sleep(0.3)
    manos.escribir_en("Render output file name", "x", permiso=si)
    manos.pulsar_teclas("ctrl+a", permiso=si)
    manos.pulsar_teclas("supr", permiso=si)
    manos.escribir_texto(nombre, permiso=si)
    time.sleep(0.3)
    # el desplegable de FORMATO tiene un gemelo (la etiqueta de texto) con el
    # mismo nombre: se pincha por coordenadas, que es donde esta SIEMPRE el
    # combo de verdad en este dialogo.
    manos.clic_raton(892, 649, permiso=si)
    time.sleep(0.5)
    r = manos.pinchar_en("WAV", permiso=si)
    if "Pulsado" not in r:
        manos.pulsar_teclas("esc", permiso=si)
        return "No he encontrado la opcion WAV en el desplegable de formato."
    time.sleep(0.3)
    manos.pinchar_en("Render 1 file", permiso=si)
    time.sleep(2.5)

    destino_probable = os.path.join(carpeta, nombre + ".wav")
    t0 = time.time()
    while time.time() - t0 < 30:
        if os.path.exists(destino_probable):
            break
        # el nombre del proyecto se antepone si nunca se ha guardado
        candidatos = [f for f in os.listdir(carpeta)
                     if f.lower().endswith(nombre.lower() + ".wav")]
        if candidatos:
            destino_probable = os.path.join(carpeta, candidatos[0])
            break
        time.sleep(1)

    if not os.path.exists(destino_probable):
        return ("No veo el archivo renderizado en %s. Mira la pantalla: puede "
                "que REAPER siga preguntando algo." % carpeta)

    try:
        import musica
        import numpy as np
        datos, ritmo = musica._leer_audio(destino_probable)
        nivel = float(np.sqrt(np.mean(datos * datos))) if datos.size else 0.0
        aviso_nivel = ("suena bien (nivel medio %.3f)" % nivel if nivel > 0.002
                       else "OJO: parece que ha salido en silencio")
    except Exception:
        aviso_nivel = "no he podido comprobar el nivel"
    return "Renderizado: %s (%s)" % (destino_probable, aviso_nivel)


def reaper_ejecutar_accion(accion, permiso=None):
    """Ejecuta cualquier accion de REAPER por su numero, para lo que no tiene
    su propia herramienta. Los numeros se buscan en la lista de acciones de
    REAPER (Actions > Show action list), con el boton derecho > Copy
    selected action command ID."""
    try:
        cid = int(str(accion).strip())
    except Exception:
        return "Dame el numero de la accion, por ejemplo 40022."
    if permiso is not None and not permiso(
            "Sobri va a ejecutar la accion %d de REAPER. Le dejas?" % cid):
        return "No me has dado permiso, no he hecho nada."
    ok, err = _ejecutar_lua('reaper.Main_OnCommand(%d, 0)' % cid)
    if not ok:
        return "No he podido ejecutarla: %s" % err
    return "Accion %d ejecutada." % cid
