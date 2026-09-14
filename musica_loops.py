# -*- coding: utf-8 -*-
"""Canciones montadas con GRABACIONES REALES, no con sintetizador.

POR QUE EXISTE ESTE MODULO (04/09/2026)
---------------------------------------
Berna componia todo con un banco General MIDI y patrones programados. Se midio
lo que salia y el resultado era malo de forma objetiva, no opinable:

    energia entre 60 y 250 Hz .... 94 %   (un disco de verdad: 65 %)
    agudos entre 2 y 8 kHz ....... 0,3 %  (un disco de verdad: 7 %)
    factor de cresta ............. 9,8 dB (un disco de verdad: 14-15 dB)

O sea: un retumbe apagado, sin agudos y aplastado. Angel decia que sonaba
insipido y tenia razon. Y no se arregla anadiendo notas, porque el problema no
es la cantidad: es que un banco MIDI tocando patrones suena a fichero MIDI.

Lo que SI suena a musica son los 13.244 trozos grabados de la biblioteca,
porque son producciones profesionales de verdad. Asi que aqui la cancion se
monta al reves que en musica.py: apilando grabaciones, como se hace en
cualquier estudio, y dejando el banco MIDI para adornar si acaso.

La condicion que lo hace funcionar es que todos los trozos vengan del MISMO
conjunto: misma carpeta, misma velocidad y mismo tono. De eso se encarga
biblioteca.kit_para().
"""

import os
import random

import biblioteca
import musica

TICS_COMPAS = musica.TICS_PULSO * 4          # 192, un compas de 4/4

# Cuando entra cada instrumento, segun lo intenso que sea el tramo. El plan de
# secciones da nivel 0 en la entrada, 2 en las estrofas y 4 en el estribillo.
DESDE = {"bateria": 0, "bajo": 1, "armonia": 2, "melodia": 4}

# Volumenes de salida. La bateria manda. El bajo y la armonia se bajaron el
# 04/09/2026 (de 96 y 76) porque entre los dos amontonaban tanta energia grave
# que tapaban los agudos: la cancion medía un 3% de energia entre 2 y 8 kHz
# cuando un disco tiene un 7%. Bajarlos es dejar sitio, no perder graves.
VOLUMEN = {"bateria": 100, "bajo": 74, "armonia": 58, "melodia": 78,
           "efecto": 70, "charles": 90, "shaker": 74}

# Cuanto se normaliza al final. musica.py usa 0.24 porque lo sintetizado sale
# flojo y hay que levantarlo. Aqui NO hace falta: estos trozos ya vienen
# masterizados de estudio (traen 0.199 de nivel y 13,9 dB de cresta). Subirlos
# igual solo sirve para empotrarlos contra el limitador y comerse la pegada,
# que es justo lo que hacia que las canciones sonaran planas.
NIVEL_LOOPS = 0.17


def _esc(t):
    return (str(t).replace("&", "&amp;").replace('"', "&quot;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def _pista(nombre, volumen, trozos):
    """Una pista de audio con sus trozos colocados en la linea de tiempo."""
    cuerpo = "".join(
        '<sampletco pos="%d" len="%d" muted="0" src="%s"/>'
        % (pos, largo, _esc(ruta)) for pos, largo, ruta in trozos)
    return ('<track name="%s" solo="0" muted="0" type="2">'
            '<sampletrack vol="%d" pan="0"><fxchain numofeffects="0"'
            ' enabled="0"/></sampletrack>%s</track>'
            % (_esc(nombre), volumen, cuerpo))


def _elegir(az, trozos, usados):
    """Un trozo del monton, evitando repetir el mismo una y otra vez.

    Es justo el fallo que tenia la 'Base grabada' de musica.py: colaba once
    veces el MISMO loop sin una sola variacion, y eso es lo que hace que una
    cancion canse a los treinta segundos.
    """
    frescos = [t for t in trozos if t["ruta"] not in usados]
    elegido = az.choice(frescos if frescos else trozos)
    usados.add(elegido["ruta"])
    return elegido


def montar(estilo, compases=32, bpm=None, semilla=None):
    """Devuelve (xml, datos) o (None, motivo) si no hay material."""
    kit = biblioteca.kit_para(estilo, bpm=bpm)
    if not kit:
        return None, "no tengo grabaciones de ese estilo en la biblioteca"

    az = random.Random(semilla or "%s|%d|%s" % (estilo, compases, kit["bpm"]))
    plan = musica._secciones(compases)
    pistas, cuenta = [], {}

    for papel, desde in DESDE.items():
        trozos = kit["papeles"].get(papel)
        if not trozos:
            continue
        usados, puestos, c = set(), [], 0
        while c < compases:
            _sec, nivel = plan[c]
            if nivel < desde:
                c += 1
                continue
            t = _elegir(az, trozos, usados)
            largo = t["compases"] * TICS_COMPAS
            # que no se salga del final de la cancion
            if c + t["compases"] > compases:
                c += 1
                continue
            puestos.append((c * TICS_COMPAS, largo, t["ruta"]))
            c += t["compases"]
        if puestos:
            pistas.append(_pista(papel.capitalize(), VOLUMEN[papel], puestos))
            cuenta[papel] = len(puestos)

    # LA CAPA DE ARRIBA (04/09/2026). Charles y shakers programados golpe a
    # golpe encima de todo. Es lo que le faltaba a la mezcla: sin esto la
    # cancion se queda en un retumbe sin brillo. Se PROGRAMA en vez de usar un
    # bucle porque el material agudo de estos packs son golpes sueltos, y ahi
    # hay una ventaja: un golpe suelto vale para cualquier velocidad, porque no
    # hay nada que estirar.
    golpes = biblioteca.golpes_agudos(estilo)
    if golpes:
        hats = [t for t in golpes if "hat" in os.path.basename(t["ruta"]).lower()
                or "cymbal" in os.path.basename(t["ruta"]).lower()]
        agita = [t for t in golpes if t not in hats]
        paso = TICS_COMPAS // 16                 # una semicorchea
        for nombre, fuente, sitios, vol in (
                ("Charles", hats or golpes, range(0, 16, 2), VOLUMEN["charles"]),
                ("Shaker", agita, range(2, 16, 4), VOLUMEN["shaker"])):
            if not fuente:
                continue
            puestos = []
            for c in range(compases):
                if plan[c][1] < 1:               # en la entrada, todavia no
                    continue
                for s in sitios:
                    t = az.choice(fuente)        # alternar da sensacion de mano
                    puestos.append((c * TICS_COMPAS + s * paso,
                                    max(paso * 2 - 2, 10), t["ruta"]))
            if puestos:
                pistas.append(_pista(nombre, vol, puestos))
                cuenta[nombre.lower()] = len(puestos)

    # Los efectos van en el compas ANTES de cada cambio de seccion: son el
    # pegamento. Sin ellos los cortes suenan secos.
    efectos = kit["papeles"].get("efecto")
    if efectos:
        cambios, puestos, usados = [], [], set()
        for c in range(1, compases):
            if plan[c][0] != plan[c - 1][0]:
                cambios.append(c)
        for c in cambios:
            t = _elegir(az, efectos, usados)
            inicio = c - t["compases"]
            if inicio >= 0:
                puestos.append((inicio * TICS_COMPAS,
                                t["compases"] * TICS_COMPAS, t["ruta"]))
        if puestos:
            pistas.append(_pista("Efectos", VOLUMEN["efecto"], puestos))
            cuenta["efecto"] = len(puestos)

    if not pistas:
        return None, "no he podido colocar ningun trozo"

    # SE PROBO a quitar el compresor y dejar solo el limitador, pensando que
    # estos trozos ya vienen masterizados y sobraba. FUE PEOR y se midio: la
    # cresta cayo de 9,8 a 7,1 dB. El motivo es que sin compresor el nivelador
    # empuja mas fuerte y entonces aplasta el LIMITADOR, que es mas bruto. Se
    # deja la cadena entera. Lo que si sobra es normalizar tan alto: eso se
    # controla con NIVEL_LOOPS aqui abajo.
    cadena = musica._cadena_master()
    maestro = "".join(cadena)
    xml = (
        '<?xml version="1.0"?>\n<!DOCTYPE lmms-project>\n'
        '<lmms-project creator="Berna" version="1.0" type="song"'
        ' creatorversion="1.2.2">\n'
        '<head timesig_numerator="4" bpm="%d" timesig_denominator="4"'
        ' mastervol="100" masterpitch="0"/>\n<song>\n'
        '<trackcontainer visible="1" maximized="0" x="5" minimized="0" y="5"'
        ' width="1200" height="600" type="song">%s</trackcontainer>\n'
        '<fxmixer><fxchannel num="0" name="Master" volume="1" muted="0">'
        '<fxchain numofeffects="%d" enabled="1">%s</fxchain></fxchannel>'
        '</fxmixer>\n'
        '<timeline lp0pos="0" lpstate="0" lp1pos="%d"/>\n'
        '<controllerrackview visible="0" maximized="0" x="700" y="200"'
        ' minimized="0" width="350" height="200"/>\n'
        '<pianoroll visible="0" maximized="0" x="5" y="266" minimized="0"'
        ' width="800" height="480"/>\n'
        '<automationeditor visible="0" maximized="0" x="0" y="0"'
        ' minimized="0" width="640" height="480"/>\n'
        '<projectnotes visible="0" maximized="0" x="830" y="20"'
        ' minimized="0" width="330" height="200"/>\n'
        '<controllers/>\n</song>\n</lmms-project>\n'
        % (kit["bpm"], "".join(pistas), len(cadena),
           maestro, compases * TICS_COMPAS))

    return xml, {"kit": kit, "cuenta": cuenta, "pistas": len(pistas)}


def crear(estilo, nombre="", compases=32, bpm=None, permiso=None,
          abrir=True):
    """Monta la cancion, la guarda, la renderiza y comprueba que suena."""
    clave = musica._buscar_estilo(estilo) or estilo
    xml, datos = montar(clave, compases=compases, bpm=bpm)
    if xml is None:
        return "No he podido: %s." % datos

    kit = datos["kit"]
    aviso = ("Berna va a montar una cancion con grabaciones de verdad:\n\n"
             "  estilo: %s\n  velocidad: %d pulsaciones\n  tono: %s\n"
             "  material: %s\n  duracion: %d compases\n\nLe dejas?"
             % (clave, kit["bpm"], kit["tono"] or "sin tono definido",
                kit["carpeta"], compases))
    if permiso is not None and not permiso(aviso):
        return "No me has dado permiso, no he montado nada."

    carpeta = musica._carpeta_musica()
    base = musica._limpio(nombre or ("%s de Berna" % clave))
    destino = os.path.join(carpeta, base + ".mmp")
    n = 2
    while os.path.exists(destino):
        destino = os.path.join(carpeta, "%s_%d.mmp" % (base, n))
        n += 1
    with open(destino, "w", encoding="utf-8") as f:
        f.write(xml)

    # _nivelar devuelve (dB que sube, nivel medio, pico), o None si no pudo.
    nivelado = ""
    try:
        r = musica._nivelar(destino, objetivo=NIVEL_LOOPS)
        if r:
            nivelado = ("%+d dB a la entrada del limitador "
                        "(medido: nivel %.3f, pico %.2f)" % r)
    except Exception:
        pass
    bien, texto, mp3 = musica.comprobar_que_suena(destino)

    lineas = ["He montado '%s' con grabaciones de verdad." % base,
              "  estilo: %s   %d pulsaciones   tono: %s"
              % (clave, kit["bpm"], kit["tono"] or "-"),
              "  material: %s" % kit["carpeta"],
              "  pistas: %s" % ", ".join(
                  "%s (%d trozos)" % (p, c)
                  for p, c in sorted(datos["cuenta"].items())),
              "  archivo: %s" % destino]
    if nivelado:
        lineas.append("  nivelado: %s" % nivelado)
    lineas.append("  comprobado: %s" % texto)
    if mp3:
        lineas.append("  para escucharla: %s" % mp3)
    if abrir and os.path.exists(musica.LMMS):
        try:
            import subprocess
            subprocess.Popen([musica.LMMS, destino])
            lineas.append("  lo he abierto en LMMS.")
        except Exception:
            pass
    return "\n".join(lineas)
