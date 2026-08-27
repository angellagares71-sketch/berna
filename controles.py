# -*- coding: utf-8 -*-
r"""
Que Berna VEA los botones de verdad, en vez de adivinar donde estan.

Angel se quejo el 2026-08-27: "la manipulacion del teclado y el raton no da
pie con bola". Se midio antes de tocar nada, y el resultado fue revelador:

  **El clic no fallaba.** Una ventana con una rejilla de casillas que apuntan
  donde les han pinchado dio 5 aciertos de 5. El raton cae CLAVADO donde se le
  manda.

  Lo que fallaba era saber a donde apuntar, y por dos motivos a la vez:

  1. `vista.py` **encoge la captura a 1600 px** antes de mandarsela al modelo.
     Cualquier coordenada que el modelo sacase de esa imagen venia en el marco
     de 1600, y `manos.py` pincha en el de 1920. Un 20% de error, siempre
     arriba y a la izquierda.
  2. Y sobre todo: **al modelo nunca se le pidieron coordenadas**. El prompt de
     vista.py le pide que describa el sitio con palabras ("el boton azul de
     abajo a la derecha"). Con eso, Berna tenia que INVENTARSE los numeros.

  O sea que le estabamos pidiendo a un modelo que adivinara pixeles mirando
  una foto encogida. No hay ajuste fino que arregle eso.

LA SOLUCION: NO ADIVINAR
  Windows sabe exactamente donde esta cada boton, cada casilla y cada cuadro
  de texto, y como se llama. Se le pregunta a el (UI Automation) y se pincha
  en el centro exacto del control. Cero adivinanza.

  Asi, "pulsa el boton Aceptar" pasa de ser una estimacion a ser una
  coordenada exacta. Y de paso Berna puede LEER lo que hay en la ventana sin
  gastar una peticion de las de Google.

CUANDO NO SIRVE
  Los juegos, los lienzos de dibujo y algunas aplicaciones viejas no publican
  sus controles. Para eso siguen estando las coordenadas de toda la vida, que
  ya se ha comprobado que son exactas.

OJO CON LOS HILOS
  UI Automation es COM, y las herramientas de Berna corren en un hilo de
  trabajo. Hay que envolver TODA llamada en `auto.UIAutomationInitializerInThread()`
  o revienta con un error de COM que no dice nada. Es la trampa numero uno de
  esta libreria.
"""
import time
import unicodedata

# Cuanto se espera como mucho a que aparezca un control. La libreria trae 10 s
# por defecto y eso cuelga la ventana de Berna, que es sincrona.
ESPERA = 2.0

# Hasta donde se baja en el arbol. Las paginas web anidan mucho; 18 llega al
# contenido de Chrome sin tardar un siglo.
HONDO = 18
TOPE_SEGUNDOS = 8.0
MAX_CONTROLES = 400

# Lo que se puede pinchar o escribir, que es lo unico que interesa.
PINCHABLES = ("ButtonControl", "HyperlinkControl", "CheckBoxControl",
              "RadioButtonControl", "MenuItemControl", "ListItemControl",
              "TabItemControl", "TreeItemControl", "ComboBoxControl",
              "SplitButtonControl")
ESCRIBIBLES = ("EditControl", "DocumentControl", "ComboBoxControl")


def _sin_tildes(t):
    t = unicodedata.normalize("NFD", str(t or ""))
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower()


def _esta_escondida(w):
    """Si la ventana esta minimizada, y por tanto sus coordenadas son mentira.

    Windows coloca las ventanas minimizadas en -32000, y esto costo verlo: al
    listar controles salian sitios como (-31977, -31983), que al pinchar no van
    a ninguna parte. Es de los motivos por los que esto "no daba pie con bola".
    """
    try:
        import ctypes
        h = w.NativeWindowHandle
        if h and ctypes.windll.user32.IsIconic(h):
            return True
        r = w.BoundingRectangle
        return r.left < -10000 or r.top < -10000 or r.width() <= 1
    except Exception:
        return False


def hay_soporte():
    try:
        import uiautomation  # noqa: F401
        return True
    except Exception:
        return False


def _auto():
    import uiautomation as auto
    auto.SetGlobalSearchTimeout(ESPERA)
    return auto


def _listar(ventana=""):
    """Devuelve [(nombre, tipo, x, y, ancho, alto, control)] de lo que hay delante.

    Las coordenadas salen en pixeles FISICOS, que es justo el marco en el que
    pincha manos.py y en el que se hacen las capturas. No hay que convertir
    nada, y eso es media guerra ganada.
    """
    auto = _auto()
    with auto.UIAutomationInitializerInThread():
        raiz = auto.GetRootControl()
        destino = None
        if ventana:
            v = _sin_tildes(ventana)
            candidatas = []
            for w in raiz.GetChildren():
                try:
                    if not w.Name or v not in _sin_tildes(w.Name):
                        continue
                    if _esta_escondida(w):
                        continue          # minimizada: sus coordenadas no valen
                    candidatas.append(w)
                except Exception:
                    continue
            if not candidatas:
                return None, ("No hay ninguna ventana ABIERTA Y A LA VISTA que se "
                              "llame '%s'. Si la tienes minimizada, sacala primero "
                              "con enfocar_ventana." % ventana)
            exactas = [w for w in candidatas if _sin_tildes(w.Name).strip() == v.strip()]
            if exactas:
                candidatas = exactas[:1]
            if len(candidatas) > 1:
                # Mismo criterio que enfocar_ventana: ante dos que encajan, no se
                # elige. Equivocarse de ventana es escribir en el sitio de otro.
                nombres = "\n".join("  - " + (w.Name or "?") for w in candidatas[:6])
                return None, ("Hay %d ventanas que encajan con '%s' y no quiero "
                              "equivocarme:\n%s\nDime cual, con mas letras del "
                              "titulo." % (len(candidatas), ventana, nombres))
            destino = candidatas[0]
        else:
            try:
                destino = auto.GetForegroundControl().GetTopLevelControl()
            except Exception:
                return None, "No he podido ver que ventana hay delante."

        fuera = []
        t0 = time.time()
        try:
            for item in auto.WalkTree(destino, getChildren=lambda x: x.GetChildren(),
                                      maxDepth=HONDO, includeTop=False):
                if time.time() - t0 > TOPE_SEGUNDOS or len(fuera) >= MAX_CONTROLES:
                    break
                c = item[0]
                try:
                    nombre = (c.Name or "").strip()
                    tipo = c.ControlTypeName
                    r = c.BoundingRectangle
                except Exception:
                    continue
                if r.width() <= 1 or r.height() <= 1:
                    continue
                if not nombre and tipo not in ESCRIBIBLES:
                    continue
                fuera.append((nombre, tipo, (r.left + r.right) // 2,
                              (r.top + r.bottom) // 2, r.width(), r.height(), c))
        except Exception as e:
            if not fuera:
                return None, "No he podido mirar dentro de la ventana: %s" % e
        return (destino, fuera), None


def ver_controles(filtro="", ventana=""):
    """Le enseña a Berna lo que hay para pinchar, con su sitio exacto."""
    if not hay_soporte():
        return ("No tengo instalado lo que hace falta para ver los controles "
                "(uiautomation). Sin eso solo puedo pinchar por coordenadas.")
    datos, error = _listar(ventana)
    if error:
        return error
    destino, lista = datos
    f = _sin_tildes(filtro)
    if f:
        lista = [x for x in lista if f in _sin_tildes(x[0])]
    if not lista:
        return ("En '%s' no veo nada%s. Puede que sea un programa que no publica "
                "sus botones (un juego, un lienzo); ahi toca mirar la pantalla y "
                "pinchar por coordenadas."
                % (destino.Name or "esa ventana",
                   (" que lleve '%s'" % filtro) if filtro else ""))

    l = ["LO QUE HAY EN '%s' (%d cosas):" % (destino.Name or "?", len(lista)), ""]
    for nombre, tipo, x, y, an, al, _c in lista[:60]:
        que = {"ButtonControl": "boton", "EditControl": "cuadro de texto",
               "HyperlinkControl": "enlace", "CheckBoxControl": "casilla",
               "RadioButtonControl": "opcion", "ComboBoxControl": "desplegable",
               "MenuItemControl": "menu", "TextControl": "texto",
               "ListItemControl": "elemento", "TabItemControl": "pestaña"}.get(tipo, tipo)
        l.append("  %-46s %-16s en (%d, %d)"
                 % ((nombre or "(sin nombre)")[:44], que, x, y))
    if len(lista) > 60:
        l.append("  ... y %d mas. Afina con el filtro." % (len(lista) - 60))
    l.append("")
    l.append("Estas coordenadas son EXACTAS, las da Windows. Para pulsar algo usa "
             "pinchar_en con su nombre, que es mas seguro que las coordenadas. Y "
             "no le leas esta lista a Angel: dile en cristiano que ves.")
    return "\n".join(l)


def _buscar(texto, ventana="", tipos=None):
    """Encuentra el control que mejor encaja. Devuelve (elegido, candidatos, error)."""
    datos, error = _listar(ventana)
    if error:
        return None, [], error
    _destino, lista = datos
    if tipos:
        lista = [x for x in lista if x[1] in tipos]
    t = _sin_tildes(texto).strip()
    if not t:
        return None, [], "Dime que quieres pulsar."

    exactos = [x for x in lista if _sin_tildes(x[0]) == t]
    empiezan = [x for x in lista if _sin_tildes(x[0]).startswith(t)]
    dentro = [x for x in lista if t in _sin_tildes(x[0])]
    # se prefiere lo exacto, y entre varios el mas pequeño: si "Aceptar" sale
    # como boton y tambien como el panel que lo contiene, el boton es el chico
    for grupo in (exactos, empiezan, dentro):
        if grupo:
            grupo = sorted(grupo, key=lambda x: x[4] * x[5])
            return grupo[0], grupo, None
    return None, [], None


def donde_esta(texto, ventana=""):
    """Dice donde esta una cosa concreta, sin tocarla."""
    if not hay_soporte():
        return "No tengo instalado uiautomation."
    elegido, cands, error = _buscar(texto, ventana)
    if error:
        return error
    if not elegido:
        return ("No veo nada que se llame '%s' en la ventana de delante. Mira lo "
                "que hay con ver_controles." % texto)
    nombre, tipo, x, y, an, al, _c = elegido
    extra = ""
    if len(cands) > 1:
        extra = " Hay %d cosas parecidas; esta es la mas ajustada." % len(cands)
    return "'%s' esta en (%d, %d) y mide %dx%d.%s" % (nombre, x, y, an, al, extra)
