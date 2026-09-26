# -*- coding: utf-8 -*-
r"""
Calibrar Gimbal: un programa aparte, con su icono en el escritorio, que guia
paso a paso la calibracion del gimbal de los drones DJI de Angel.

Angel lo pidio el 2026-09-26: la guia ya estaba dentro de Sobri (se le pide
hablando), pero la queria tambien como programa suelto, para abrirlo con doble
clic con el dron delante y sin tener que hablarle a nadie.

QUE HACE
  Eliges el dron (Mini 3, Mini 3 Pro, Mini 4 Pro, Avata o FPV), y te ensena
  los pasos de uno en uno, con la lista entera al lado para ver por donde vas.
  En el paso de "no toques el dron" sale un aviso bien grande.

QUE NO HACE, Y ES A PROPOSITO
  No le manda nada al dron. La calibracion la hace el propio dron cuando tu
  pulsas en DJI Fly o en las gafas. El protocolo interno de DJI no es publico
  y una orden mal mandada puede dejar el gimbal peor de lo que estaba.

DE DONDE SALEN LOS PASOS
  De `dron.GIMBAL`, lo mismo que usa Sobri al hablar. Asi hay una sola lista
  y el programa y Sobri no pueden decir cosas distintas.

ARRANCARLO
  Doble clic en "Calibrar Gimbal.bat" (en C:\Asistente), o en el acceso directo
  del escritorio, que lo crea el boton "Poner en el escritorio".
"""
import os
import sys
import subprocess

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import dron

TITULO = "Calibrar Gimbal"
ATAJO = "Calibrar Gimbal"

# Los pasos en los que hay que dejar el dron quieto. Se buscan en el texto del
# paso para no tener que marcarlos a mano en dron.GIMBAL.
_QUIETO = ("no toques", "sin mover", "no lo toques")

COLOR_FONDO = "#1e1f24"
COLOR_TARJETA = "#2a2c33"
COLOR_TEXTO = "#f2f2f2"
COLOR_SUAVE = "#a9adb8"
COLOR_ACENTO = "#3d8bfd"
COLOR_HECHO = "#3fb950"
COLOR_AVISO = "#e8912d"


# ------------------------------------------------------------ la logica
# Separada de la ventana para poder probarla sin pantalla.
def modelos():
    """(clave, nombre) de cada dron, en el orden de dron.GIMBAL."""
    return [(k, v["nombre"]) for k, v in dron.GIMBAL.items()]


def modelo_guardado():
    """La clave del dron que Angel tiene guardado en Sobri, o ''."""
    try:
        return dron._modelo_gimbal("")
    except Exception:
        return ""


def es_paso_quieto(texto):
    t = str(texto or "").lower()
    return any(q in t for q in _QUIETO)


def titulo_corto(texto, maximo=50):
    """El principio de un paso, para la lista de la izquierda.

    Se corta en la primera pausa (coma, punto, dos puntos o parentesis) y, si
    aun es largo, por la ultima palabra entera que quepa.
    """
    t = str(texto or "").strip()
    for corte in (" (", ", ", ". ", ": "):
        i = t.find(corte)
        if i > 0:
            t = t[:i]
    t = t.rstrip(".:,")
    if len(t) > maximo:
        t = t[:maximo].rsplit(" ", 1)[0].rstrip(",.:") + "..."
    return t


def resumen(clave):
    g = dron.GIMBAL[clave]
    return "%s  -  gimbal de %d eje%s  -  se calibra desde %s" % (
        g["nombre"], g["ejes"], "s" if g["ejes"] > 1 else "", g["donde"])


def escritorio():
    """La carpeta del escritorio DE VERDAD, aunque OneDrive la haya movido.

    Repetida de instalador.py a proposito, como en taller.py y operar.py: este
    programa tiene que poder funcionar suelto.
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


def _pythonw():
    """El pythonw.exe del mismo Python que nos esta ejecutando."""
    carpeta = os.path.dirname(sys.executable)
    w = os.path.join(carpeta, "pythonw.exe")
    return w if os.path.isfile(w) else sys.executable


def crear_acceso_directo():
    """Pone 'Calibrar Gimbal' en el escritorio. Devuelve (ok, mensaje)."""
    if os.name != "nt":
        return False, "El acceso directo solo se puede crear en Windows."
    atajo = os.path.join(escritorio(), ATAJO + ".lnk")
    script = os.path.abspath(__file__)
    ps = ('$w = New-Object -ComObject WScript.Shell; '
          '$s = $w.CreateShortcut("%s"); $s.TargetPath = "%s"; '
          '$s.Arguments = \'"%s"\'; $s.WorkingDirectory = "%s"; '
          '$s.Description = "Calibrar el gimbal del dron, paso a paso"; '
          '$s.Save()' % (atajo, _pythonw(), script, BASE))
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, timeout=60,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as e:
        return False, "No he podido crear el acceso directo: %s" % e
    if not os.path.exists(atajo):
        return False, "No he podido crear el acceso directo en el escritorio."
    return True, "Listo: tienes '%s' en el escritorio." % ATAJO


# ------------------------------------------------------------ la ventana
class App:
    def __init__(self, raiz):
        import tkinter as tk
        self.tk = tk
        self.raiz = raiz
        raiz.title(TITULO)
        raiz.configure(bg=COLOR_FONDO)
        raiz.geometry("920x620")
        raiz.minsize(760, 540)

        self.clave = ""
        self.paso = 0
        self.botones_modelo = {}
        self.etiquetas_lista = []

        self._cabecera()
        self._selector()
        self.cuerpo = tk.Frame(raiz, bg=COLOR_FONDO)
        self.cuerpo.pack(fill="both", expand=True, padx=20, pady=(6, 10))
        self._pie()

        raiz.bind("<Right>", lambda e: self.siguiente())
        raiz.bind("<Return>", lambda e: self.siguiente())
        raiz.bind("<Left>", lambda e: self.anterior())

        guardado = modelo_guardado()
        if guardado:
            self.elegir(guardado)
        else:
            self._pantalla_inicio()

    # ---- piezas fijas
    def _cabecera(self):
        tk = self.tk
        f = tk.Frame(self.raiz, bg=COLOR_FONDO)
        f.pack(fill="x", padx=20, pady=(16, 4))
        tk.Label(f, text="Calibrar el gimbal", bg=COLOR_FONDO, fg=COLOR_TEXTO,
                 font=("Segoe UI", 20, "bold")).pack(anchor="w")
        tk.Label(f, text="Elige tu dron y sigue los pasos con el dron delante.",
                 bg=COLOR_FONDO, fg=COLOR_SUAVE,
                 font=("Segoe UI", 11)).pack(anchor="w")

    def _selector(self):
        tk = self.tk
        f = tk.Frame(self.raiz, bg=COLOR_FONDO)
        f.pack(fill="x", padx=20, pady=(8, 4))
        for clave, nombre in modelos():
            b = tk.Button(f, text=nombre.replace("DJI ", ""), relief="flat",
                          bg=COLOR_TARJETA, fg=COLOR_TEXTO, bd=0,
                          activebackground=COLOR_ACENTO,
                          activeforeground="white", cursor="hand2",
                          font=("Segoe UI", 11, "bold"), padx=14, pady=8,
                          command=lambda c=clave: self.elegir(c))
            b.pack(side="left", padx=(0, 8))
            self.botones_modelo[clave] = b
        self.linea_resumen = tk.Label(self.raiz, text="", bg=COLOR_FONDO,
                                      fg=COLOR_SUAVE, font=("Segoe UI", 10))
        self.linea_resumen.pack(anchor="w", padx=20)

    def _pie(self):
        tk = self.tk
        f = tk.Frame(self.raiz, bg=COLOR_FONDO)
        f.pack(fill="x", side="bottom", padx=20, pady=(0, 12))
        tk.Label(f, text="Este programa solo te guia: no le manda nada al dron.",
                 bg=COLOR_FONDO, fg=COLOR_SUAVE,
                 font=("Segoe UI", 9)).pack(side="left")
        tk.Button(f, text="Poner en el escritorio", relief="flat",
                  bg=COLOR_TARJETA, fg=COLOR_SUAVE, bd=0, cursor="hand2",
                  activebackground=COLOR_TARJETA, activeforeground=COLOR_TEXTO,
                  font=("Segoe UI", 9), padx=10, pady=4,
                  command=self.poner_en_escritorio).pack(side="right")

    # ---- pantallas
    def _limpiar(self):
        for w in self.cuerpo.winfo_children():
            w.destroy()
        self.etiquetas_lista = []

    def _pantalla_inicio(self):
        self._limpiar()
        self.tk.Label(self.cuerpo, text="Pulsa arriba el dron que tienes.",
                      bg=COLOR_FONDO, fg=COLOR_TEXTO,
                      font=("Segoe UI", 14)).pack(pady=60)

    def elegir(self, clave):
        if clave not in dron.GIMBAL:
            return
        self.clave = clave
        self.paso = 0
        for c, b in self.botones_modelo.items():
            b.configure(bg=COLOR_ACENTO if c == clave else COLOR_TARJETA)
        self.linea_resumen.configure(text=resumen(clave))
        self._pantalla_pasos()

    def _pantalla_pasos(self):
        tk = self.tk
        self._limpiar()
        pasos = dron.GIMBAL[self.clave]["pasos"]

        # a la izquierda, la lista entera
        lista = tk.Frame(self.cuerpo, bg=COLOR_TARJETA, width=270)
        lista.pack(side="left", fill="y", padx=(0, 14))
        lista.pack_propagate(False)
        tk.Label(lista, text="Los pasos", bg=COLOR_TARJETA, fg=COLOR_SUAVE,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12,
                                                     pady=(10, 4))
        for i, texto in enumerate(pasos):
            corto = titulo_corto(texto)
            e = tk.Label(lista, text="", bg=COLOR_TARJETA, anchor="w",
                         justify="left", wraplength=240,
                         font=("Segoe UI", 10), cursor="hand2")
            e.pack(fill="x", padx=12, pady=2)
            e.bind("<Button-1>", lambda ev, n=i: self.ir_a(n))
            self.etiquetas_lista.append((e, corto))

        # a la derecha, el paso de ahora
        derecha = tk.Frame(self.cuerpo, bg=COLOR_FONDO)
        derecha.pack(side="left", fill="both", expand=True)
        self.contador = tk.Label(derecha, text="", bg=COLOR_FONDO,
                                 fg=COLOR_SUAVE, font=("Segoe UI", 11, "bold"))
        self.contador.pack(anchor="w")
        self.aviso = tk.Label(derecha, text="NO TOQUES EL DRON NI LA MESA",
                              bg=COLOR_AVISO, fg="black",
                              font=("Segoe UI", 16, "bold"), pady=10)
        tarjeta = tk.Frame(derecha, bg=COLOR_TARJETA)
        tarjeta.pack(fill="both", expand=True, pady=(8, 10))
        self.texto_paso = tk.Label(tarjeta, text="", bg=COLOR_TARJETA,
                                   fg=COLOR_TEXTO, justify="left", anchor="nw",
                                   wraplength=520, font=("Segoe UI", 16))
        self.texto_paso.pack(fill="both", expand=True, padx=22, pady=22)
        self.aviso_ancla = tarjeta

        botones = tk.Frame(derecha, bg=COLOR_FONDO)
        botones.pack(fill="x")
        self.b_atras = tk.Button(botones, text="<  Anterior", relief="flat",
                                 bg=COLOR_TARJETA, fg=COLOR_TEXTO, bd=0,
                                 cursor="hand2", font=("Segoe UI", 12),
                                 padx=16, pady=8, command=self.anterior)
        self.b_atras.pack(side="left")
        self.b_sigue = tk.Button(botones, text="Hecho, siguiente  >",
                                 relief="flat", bg=COLOR_ACENTO, fg="white",
                                 bd=0, cursor="hand2",
                                 activebackground=COLOR_ACENTO,
                                 activeforeground="white",
                                 font=("Segoe UI", 12, "bold"), padx=16,
                                 pady=8, command=self.siguiente)
        self.b_sigue.pack(side="right")
        self._pintar_paso()

    def _pintar_paso(self):
        pasos = dron.GIMBAL[self.clave]["pasos"]
        n = self.paso
        self.contador.configure(text="Paso %d de %d" % (n + 1, len(pasos)))
        self.texto_paso.configure(text=pasos[n])
        if es_paso_quieto(pasos[n]):
            self.aviso.pack(fill="x", pady=(8, 0), before=self.aviso_ancla)
        else:
            self.aviso.pack_forget()
        for i, (e, corto) in enumerate(self.etiquetas_lista):
            if i < n:
                e.configure(text="\u2714  " + corto, fg=COLOR_HECHO)
            elif i == n:
                e.configure(text="\u25b6  " + corto, fg=COLOR_TEXTO)
            else:
                e.configure(text="%d.  %s" % (i + 1, corto), fg=COLOR_SUAVE)
        self.b_atras.configure(state="normal" if n > 0 else "disabled")
        ultimo = n == len(pasos) - 1
        self.b_sigue.configure(text="Terminado  \u2714" if ultimo
                               else "Hecho, siguiente  >")

    def _pantalla_final(self):
        tk = self.tk
        self._limpiar()
        g = dron.GIMBAL[self.clave]
        tk.Label(self.cuerpo, text="\u2714  Calibracion terminada", bg=COLOR_FONDO,
                 fg=COLOR_HECHO, font=("Segoe UI", 20, "bold")).pack(
                     anchor="w", pady=(10, 10))
        texto = []
        if g.get("nota"):
            texto.append("Ojo: " + g["nota"])
        texto.append(dron._SI_SIGUE_MAL)
        tk.Label(self.cuerpo, text="\n\n".join(texto), bg=COLOR_FONDO,
                 fg=COLOR_TEXTO, justify="left", anchor="w", wraplength=820,
                 font=("Segoe UI", 12)).pack(anchor="w", fill="x")
        tk.Button(self.cuerpo, text="Empezar otra vez", relief="flat",
                  bg=COLOR_TARJETA, fg=COLOR_TEXTO, bd=0, cursor="hand2",
                  font=("Segoe UI", 12), padx=16, pady=8,
                  command=lambda: self.elegir(self.clave)).pack(anchor="w",
                                                                pady=20)

    # ---- acciones
    def siguiente(self):
        if not self.clave or not self.etiquetas_lista:
            return
        if self.paso >= len(dron.GIMBAL[self.clave]["pasos"]) - 1:
            self._pantalla_final()
            return
        self.paso += 1
        self._pintar_paso()

    def anterior(self):
        if not self.clave or not self.etiquetas_lista or self.paso == 0:
            return
        self.paso -= 1
        self._pintar_paso()

    def ir_a(self, n):
        self.paso = n
        self._pintar_paso()

    def poner_en_escritorio(self):
        from tkinter import messagebox
        if not messagebox.askyesno(
                TITULO, "Pongo un acceso directo 'Calibrar Gimbal' en el "
                        "escritorio?", parent=self.raiz):
            return
        ok, mensaje = crear_acceso_directo()
        (messagebox.showinfo if ok else messagebox.showwarning)(
            TITULO, mensaje, parent=self.raiz)


def main():
    import tkinter as tk
    raiz = tk.Tk()
    App(raiz)
    raiz.mainloop()


if __name__ == "__main__":
    main()
