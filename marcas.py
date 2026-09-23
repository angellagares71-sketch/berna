# -*- coding: utf-8 -*-
"""Marca temporal y transparente sobre la pantalla, sin pulsar nada."""

import ctypes
import os
import re
import subprocess
import sys
import threading

BASE = os.path.dirname(os.path.abspath(__file__))
COLORES = {"rojo": "#ef3434", "verde": "#21cf6b", "azul": "#34a8ff",
           "amarillo": "#ffcf27", "naranja": "#ff8932"}
_proceso = None
_cerrojo = threading.Lock()


def _situar(objetivo, ventana):
    """Primero pregunta a Windows; solo mira una captura si no hay control."""
    if not objetivo:
        import manos
        return (*manos._donde_esta_el_raton(), "raton")
    import controles
    elegido, _candidatos, error = controles._buscar(objetivo, ventana)
    if elegido:
        return elegido[2], elegido[3], "control '%s'" % elegido[0]
    try:
        import ocr_local
        ox, oy, detalle = ocr_local.localizar_texto(objetivo)
        if ox is not None:
            return ox, oy, detalle
    except Exception:
        pass
    import vista
    respuesta = vista.mirar_para_pinchar(objetivo)
    punto = re.search(r"hacia \((-?\d+),\s*(-?\d+)\)", respuesta)
    if punto:
        return int(punto.group(1)), int(punto.group(2)), "imagen"
    return None, None, error or respuesta


def marcar_en_pantalla(objetivo="", x=None, y=None, color="rojo", segundos=8,
                       ventana=""):
    """Dibuja un anillo visible que desaparece solo; no mueve el raton."""
    objetivo = str(objetivo or "").strip()[:120]
    color = str(color or "rojo").lower().strip()
    if color not in COLORES:
        return "Elige rojo, verde, azul, amarillo o naranja."
    try:
        duracion = max(2, min(20, int(segundos)))
    except (TypeError, ValueError):
        duracion = 8
    if x is not None or y is not None:
        try:
            punto_x, punto_y = int(x), int(y)
        except (TypeError, ValueError):
            return "Necesito las dos coordenadas en numeros."
        origen = "coordenadas"
    else:
        punto_x, punto_y, origen = _situar(objetivo, ventana)
        if punto_x is None:
            return "No he encontrado '%s' para marcarlo: %s" % (objetivo, origen)
    import manos
    vx, vy, ancho, alto = manos._pantalla_fisica()
    if not (vx <= punto_x < vx + ancho and vy <= punto_y < vy + alto):
        return "Ese punto queda fuera de la pantalla; no he dibujado nada."
    pythonw = os.path.join(BASE, "venv", "Scripts", "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = sys.executable
    global _proceso
    with _cerrojo:
        if _proceso is not None and _proceso.poll() is None:
            _proceso.terminate()
        try:
            _proceso = subprocess.Popen(
                [pythonw, __file__, "--mostrar", str(punto_x), str(punto_y),
                 COLORES[color], str(duracion)], cwd=BASE,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as err:
            return "No he podido dibujar la marca: %s" % err
    detalle = ("sobre %s" % origen) if origen != "raton" else "donde esta el raton"
    return "He marcado %s %s durante %d segundos, sin pulsar nada." % (
        objetivo or "el punto", detalle, duracion)


def quitar_marca():
    """Retira la marca antes de que venza su tiempo."""
    global _proceso
    with _cerrojo:
        if _proceso is None or _proceso.poll() is not None:
            return "Ahora no hay ninguna marca en pantalla."
        _proceso.terminate()
        _proceso = None
    return "He quitado la marca."


def _mostrar(x, y, color, segundos):
    """Ventana independiente para que Tk solo se use desde su hilo principal."""
    import tkinter as tk
    u32 = ctypes.windll.user32
    try:
        u32.SetProcessDPIAware()
    except OSError:
        pass
    raiz = tk.Tk()
    raiz.title("Marca de Sobri")
    raiz.overrideredirect(True)
    raiz.attributes("-topmost", True)
    raiz.configure(bg="#010203")
    raiz.geometry("150x150+%d+%d" % (x - 75, y - 75))
    try:
        raiz.attributes("-transparentcolor", "#010203")
    except tk.TclError:
        raiz.attributes("-alpha", 0.82)
    lienzo = tk.Canvas(raiz, width=150, height=150, highlightthickness=0,
                       bg="#010203")
    lienzo.pack()
    lienzo.create_oval(20, 20, 130, 130, outline=color, width=7)
    lienzo.create_oval(65, 65, 85, 85, outline=color, width=3)
    raiz.update()
    # En Tk sobre Windows, winfo_id es el hijo; mover ese hijo dejaba la
    # ventana real en la esquina. El padre es el HWND del Toplevel.
    h = u32.GetParent(raiz.winfo_id()) or raiz.winfo_id()
    # WS_EX_TRANSPARENT permite seguir pinchando en lo que haya debajo.
    GWL_EXSTYLE, WS_EX_TRANSPARENT, WS_EX_LAYERED, WS_EX_TOOLWINDOW = -20, 0x20, 0x80000, 0x80
    estilo = u32.GetWindowLongW(h, GWL_EXSTYLE)
    u32.SetWindowLongW(h, GWL_EXSTYLE,
                       estilo | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_TOOLWINDOW)
    # Ya es topmost por el atributo de Tk. Pasar HWND_TOPMOST (-1) a ctypes
    # sin declarar argtypes fallaba silenciosamente en Windows de 64 bits.
    u32.SetWindowPos(h, 0, x - 75, y - 75, 150, 150, 0x0010 | 0x0040)
    raiz.after(int(segundos * 1000), raiz.destroy)
    raiz.mainloop()


if __name__ == "__main__" and len(sys.argv) == 6 and sys.argv[1] == "--mostrar":
    _mostrar(int(sys.argv[2]), int(sys.argv[3]), sys.argv[4], int(sys.argv[5]))
