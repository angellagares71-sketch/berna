# -*- coding: utf-8 -*-
r"""
La pantalla para publicar Sobri en GitHub, sin escribir nada en la consola.

Angel lo pidio el 2026-09-26: tenia cambios en C:\Asistente sin publicar
(quedarse_sola, es_grabacion...) y queria "la pantalla para publicarlo" en vez
de pelearse con Publicar Sobri.bat.

QUE HACE
  Mira que version tiene este ordenador y cual hay publicada en GitHub, y
  propone ya el numero siguiente. Al pulsar Publicar abre una consola que
  ejecuta publicar_actualizacion.py con ese numero y lo que trae. Es el mismo
  programa de publicar de siempre (el de "Publicar Sobri.bat"): esta pantalla
  solo le pone los datos. La consola se queda abierta al terminar para que se
  pueda leer como ha ido y, si falla, copiar el mensaje.

QUE NO HACE
  No sube nada ella sola ni guarda contrasenas: si GitHub pide entrar, se
  entra en el navegador, como siempre.

ARRANCARLO
  Doble clic en "Publicar con pantalla.bat" (en C:\Asistente).
"""
import os
import re
import sys
import json
import subprocess

BASE = os.path.dirname(os.path.abspath(__file__))
PUBLICAR = os.path.join(BASE, "publicar_actualizacion.py")
PUBLICAR_BAT = os.path.join(BASE, "Publicar Sobri.bat")
TITULO = "Publicar Sobri"
REPOSITORIO = "angellagares71-sketch/berna"

COLOR_FONDO = "#1e1f24"
COLOR_TARJETA = "#2a2c33"
COLOR_TEXTO = "#f2f2f2"
COLOR_SUAVE = "#a9adb8"
COLOR_ACENTO = "#3d8bfd"
COLOR_AVISO = "#e8912d"


# ------------------------------------------------------------ la logica
def version_de_aqui():
    """La VERSION de actualizaciones.py, leida sin importarlo."""
    try:
        with open(os.path.join(BASE, "actualizaciones.py"), encoding="utf-8") as f:
            m = re.search(r'^VERSION\s*=\s*"([^"]+)"', f.read(), re.M)
        return m.group(1) if m else ""
    except Exception:
        return ""


def _repositorio():
    """El de config.json si lo hay (como hace actualizaciones.py), si no el
    de siempre."""
    try:
        with open(os.path.join(BASE, "config.json"), encoding="utf-8") as f:
            r = str(json.load(f).get("repositorio") or "").strip().strip("/")
        r = re.sub(r"^https?://(www\.)?github\.com/", "", r, flags=re.I)
        r = re.sub(r"\.git$", "", r)
        if re.match(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$", r):
            return r
    except Exception:
        pass
    return REPOSITORIO


def version_publicada():
    """La version del version.json de GitHub, o '' si no se puede mirar."""
    import time
    url = ("https://raw.githubusercontent.com/%s/main/version.json?cache=%d"
           % (_repositorio(), int(time.time())))
    try:
        import requests
        r = requests.get(url, timeout=20, headers={"Cache-Control": "no-cache"})
        if r.status_code == 200:
            return str(r.json().get("version") or "")
    except Exception:
        pass
    return ""


def como_numeros(v):
    """'1.10.2' -> (1, 10, 2), para que 1.10 sea mas que 1.9."""
    nums = [int(x) for x in re.findall(r"\d+", str(v or ""))[:3]]
    return tuple(nums + [0] * (3 - len(nums))) if nums else (0, 0, 0)


def siguiente(*versiones):
    """La siguiente a la mas alta de las que se le pasan: 1.15.4 -> 1.15.5."""
    a, b, c = max(como_numeros(v) for v in versiones)
    return "%d.%d.%d" % (a, b, c + 1)


def version_valida(v):
    return bool(re.match(r"^\d+\.\d+\.\d+$", str(v or "").strip()))


def limpiar_texto(t):
    """Lo que trae, sin nada que la consola de Windows pueda malinterpretar:
    ni comillas ni simbolos de cmd, y sin tildes, que la consola las cambia."""
    import unicodedata
    t = unicodedata.normalize("NFKD", str(t or ""))
    t = t.encode("ascii", "ignore").decode("ascii")
    t = re.sub(r'[\"&|<>^%!\r\n]', " ", t)
    return re.sub(r"\s+", " ", t).strip()[:200]


def _python_de_consola():
    """El python.exe del venv de Sobri (con consola, no el pythonw)."""
    venv = os.path.join(BASE, "venv", "Scripts", "python.exe")
    if os.path.isfile(venv):
        return venv
    exe = sys.executable
    if exe.lower().endswith("pythonw.exe"):
        exe = exe[:-len("pythonw.exe")] + "python.exe"
    return exe


def orden_de_publicar(version, texto):
    """El .bat que se ejecuta en la consola. Se escribe a un archivo en vez de
    pasarlo por 'cmd /k', que se come las comillas."""
    return ("@echo off\r\n"
            "title Publicando Sobri %s\r\n"
            "cd /d \"%s\"\r\n"
            "echo Publicando Sobri %s en GitHub...\r\n"
            "echo.\r\n"
            "\"%s\" \"%s\" %s \"%s\"\r\n"
            "echo.\r\n"
            "echo ------------------------------------------------------------\r\n"
            "echo  Ya ha terminado. Si pone algun error, copialo y pasaselo\r\n"
            "echo  a Claude. Puedes cerrar esta ventana.\r\n"
            "echo ------------------------------------------------------------\r\n"
            "pause\r\n"
            % (version, BASE, version, _python_de_consola(), PUBLICAR,
               version, texto))


def lanzar(version, texto):
    """Abre la consola que publica. Devuelve (ok, mensaje)."""
    if not os.path.isfile(PUBLICAR):
        return False, ("No encuentro publicar_actualizacion.py en %s, que es "
                       "el programa que sube a GitHub." % BASE)
    if os.name != "nt":
        return False, "Publicar solo se puede desde Windows."
    # En la carpeta temporal y no en C:\Asistente: si no, el propio programa
    # de publicar se lo llevaria a GitHub con lo demas.
    import tempfile
    lanzador = os.path.join(tempfile.gettempdir(), "sobri_publicar_ahora.bat")
    try:
        with open(lanzador, "w", encoding="ascii", errors="replace",
                  newline="") as f:
            f.write(orden_de_publicar(version, texto))
        subprocess.Popen(["cmd", "/c", lanzador], cwd=BASE,
                         creationflags=getattr(subprocess,
                                               "CREATE_NEW_CONSOLE", 0))
    except Exception as e:
        return False, "No he podido abrir la consola de publicar: %s" % e
    return True, ("Se ha abierto una ventana negra que esta publicando la "
                  "%s. Espera a que diga que ha terminado." % version)


# ------------------------------------------------------------ la ventana
class App:
    def __init__(self, raiz):
        import tkinter as tk
        self.tk = tk
        self.raiz = raiz
        raiz.title(TITULO)
        raiz.configure(bg=COLOR_FONDO)
        raiz.geometry("640x470")
        raiz.minsize(560, 440)

        self.aqui = version_de_aqui()
        self.fuera = ""

        cab = tk.Frame(raiz, bg=COLOR_FONDO)
        cab.pack(fill="x", padx=22, pady=(18, 6))
        tk.Label(cab, text="Publicar Sobri en GitHub", bg=COLOR_FONDO,
                 fg=COLOR_TEXTO, font=("Segoe UI", 20, "bold")).pack(anchor="w")
        tk.Label(cab, text="Sube lo que tienes en este ordenador, para que no "
                           "se pierda y los demas puedan actualizarse.",
                 bg=COLOR_FONDO, fg=COLOR_SUAVE, wraplength=590,
                 justify="left", font=("Segoe UI", 11)).pack(anchor="w")

        t = tk.Frame(raiz, bg=COLOR_TARJETA)
        t.pack(fill="x", padx=22, pady=10)
        self.l_versiones = tk.Label(t, text="", bg=COLOR_TARJETA,
                                    fg=COLOR_TEXTO, justify="left",
                                    font=("Segoe UI", 11))
        self.l_versiones.grid(row=0, column=0, columnspan=2, sticky="w",
                              padx=16, pady=(14, 10))
        tk.Label(t, text="Numero nuevo:", bg=COLOR_TARJETA, fg=COLOR_SUAVE,
                 font=("Segoe UI", 11)).grid(row=1, column=0, sticky="w",
                                             padx=16, pady=6)
        self.v_version = tk.StringVar(value=siguiente(self.aqui))
        tk.Entry(t, textvariable=self.v_version, width=12,
                 font=("Segoe UI", 13, "bold")).grid(row=1, column=1,
                                                     sticky="w", padx=6)
        tk.Label(t, text="Lo que trae:", bg=COLOR_TARJETA, fg=COLOR_SUAVE,
                 font=("Segoe UI", 11)).grid(row=2, column=0, sticky="w",
                                             padx=16, pady=(6, 16))
        self.v_texto = tk.StringVar(
            value="Cambios hechos en el ordenador de Angel")
        tk.Entry(t, textvariable=self.v_texto, width=40,
                 font=("Segoe UI", 11)).grid(row=2, column=1, sticky="w",
                                             padx=6, pady=(6, 16))

        self.l_estado = tk.Label(raiz, text="", bg=COLOR_FONDO, fg=COLOR_SUAVE,
                                 wraplength=590, justify="left",
                                 font=("Segoe UI", 11))
        self.l_estado.pack(anchor="w", padx=22, pady=(4, 8))

        self.b_publicar = tk.Button(raiz, text="Publicar", relief="flat",
                                    bg=COLOR_ACENTO, fg="white", bd=0,
                                    activebackground=COLOR_ACENTO,
                                    activeforeground="white", cursor="hand2",
                                    font=("Segoe UI", 14, "bold"), padx=26,
                                    pady=10, command=self.publicar)
        self.b_publicar.pack(anchor="e", padx=22, pady=(0, 16))

        self._pintar_versiones()
        raiz.after(200, self._mirar_github)

    def _pintar_versiones(self):
        self.l_versiones.configure(
            text="En este ordenador:   %s\nPublicada en GitHub:   %s"
                 % (self.aqui or "no lo se",
                    self.fuera or "mirando..."))

    def _mirar_github(self):
        """Mira GitHub en otro hilo; la ventana recoge el resultado ella misma,
        porque tkinter no se debe tocar desde otro hilo."""
        import threading
        caja = {}

        def trabajar():
            caja["v"] = version_publicada()

        def recoger():
            if "v" in caja:
                self._llego_github(caja["v"])
            else:
                self.raiz.after(200, recoger)

        threading.Thread(target=trabajar, daemon=True).start()
        self.raiz.after(200, recoger)

    def _llego_github(self, v):
        self.fuera = v or ""
        if not v:
            self.fuera = "no he podido mirarlo"
        else:
            self.v_version.set(siguiente(self.aqui, v))
        self._pintar_versiones()

    def publicar(self):
        from tkinter import messagebox
        version = self.v_version.get().strip()
        texto = limpiar_texto(self.v_texto.get()) or "Cambios de Angel"
        if not version_valida(version):
            messagebox.showwarning(TITULO, "El numero tiene que ser como "
                                   "1.15.6: tres numeros separados por puntos.",
                                   parent=self.raiz)
            return
        minimo = [v for v in (self.aqui, self.fuera) if version_valida(v)]
        if minimo and como_numeros(version) <= max(como_numeros(v) for v in minimo):
            messagebox.showwarning(TITULO, "El numero tiene que ser mayor que "
                                   "%s, o nadie vera la version nueva."
                                   % max(minimo, key=como_numeros),
                                   parent=self.raiz)
            return
        if not messagebox.askyesno(
                TITULO, "Publico la version %s en GitHub con lo que tienes en "
                        "este ordenador?\n\nLo que trae: %s" % (version, texto),
                parent=self.raiz):
            return
        ok, mensaje = lanzar(version, texto)
        self.l_estado.configure(text=mensaje,
                                fg=COLOR_TEXTO if ok else COLOR_AVISO)
        if not ok and os.path.isfile(PUBLICAR_BAT) and messagebox.askyesno(
                TITULO, mensaje + "\n\nAbro 'Publicar Sobri.bat', el de "
                                  "siempre?", parent=self.raiz):
            try:
                os.startfile(PUBLICAR_BAT)
            except Exception as e:
                self.l_estado.configure(text="Tampoco he podido abrirlo: %s" % e)


def main():
    import tkinter as tk
    raiz = tk.Tk()
    App(raiz)
    raiz.mainloop()


if __name__ == "__main__":
    main()
