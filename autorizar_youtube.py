# -*- coding: utf-8 -*-
"""Abre el navegador para que Angel de permiso a Sobri en su canal de YouTube.

Lo lanza la herramienta redes_conectar_youtube con pythonw, sin consola: al
terminar sale una ventanita que dice si ha ido bien o que ha fallado.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import redes  # noqa: E402


def main():
    ok, mensaje = redes.autorizar_youtube_ahora()
    redes._anotar("autorizar YouTube: %s" % mensaje)
    try:
        import tkinter as tk
        from tkinter import messagebox
        raiz = tk.Tk()
        raiz.withdraw()
        raiz.attributes("-topmost", True)
        (messagebox.showinfo if ok else messagebox.showerror)("Sobri y YouTube", mensaje)
        raiz.destroy()
    except Exception:
        print(mensaje)


if __name__ == "__main__":
    main()
