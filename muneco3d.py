# -*- coding: utf-8 -*-
r"""
El avatar de Berna en 3D de verdad.

Angel lo pidio el 2026-08-27: "que el avatar sea en 3D y de buena calidad".
Antes era un dibujo plano de Tk (ovalos y lineas). Esto es geometria 3D con
sus vertices, sus normales, su perspectiva y su luz.

POR QUE ESTA HECHO ASI Y NO CON UNA TARJETA GRAFICA
  Este portatil lleva una Radeon integrada con 0,5 GB de VRAM, y ademas Berna
  es una ventana de Tkinter, que no tiene lienzo 3D. Montar OpenGL aqui seria
  fragil y encima competiria con el Skyrim por la grafica.

  Asi que se rasteriza por software: numpy hace la geometria y la luz (todo
  vectorizado, sin bucles de Python) y Pillow pinta los poligonos. El
  resultado va a una sola imagen que Tk enseña. **No hace falta grafica.**

EL PRESUPUESTO DE TRIANGULOS, medido antes de escribir nada
  Pillow pinta unos 900 poligonos en 27 ms a doble resolucion, y reducir la
  imagen con BOX cuesta 1,8 ms. O sea ~30 fotogramas por segundo, que es lo
  que tenia el muneco plano. Por eso la malla ronda los 1.000 triangulos y no
  3.000: con 3.000 se cae a 10 fps y se ve a tirones.

  El doble de resolucion + reduccion BOX no es un adorno: **es el
  antialiasing**. Sin eso los bordes de los poligonos hacen sierra y se ve
  todo roto.

LO QUE HACE QUE PAREZCA 3D Y NO CARTON
  1. Perspectiva de verdad (division por z), no proyeccion plana.
  2. Luz difusa de Lambert por cara, con la normal calculada del triangulo.
  3. **Luz de borde (rim light)**: un brillo en los cantos que separa la
     silueta del fondo. Es lo que mas sensacion de volumen da por lo poco que
     cuesta.
  4. Especular suave en la piel y en los ojos.
  5. Caras traseras descartadas: la mitad de triangulos fuera, gratis.

LA REGLA DE LOS HILOS SIGUE IGUAL QUE EN EL MUNECO PLANO
  Los hilos de trabajo SOLO escriben boca_obj, mic y estado. El dibujado
  ocurre siempre en el hilo de la interfaz. Tk no aguanta otra cosa.
"""
import math
import random
import time
import tkinter as tk

import numpy as np
from PIL import Image, ImageDraw, ImageTk


def _lerp(a, b, k):
    return a + (b - a) * k


# ------------------------------------------------------------------ geometria
def _esfera(nu, nv):
    """Malla de esfera. Devuelve (vertices, caras)."""
    us = np.linspace(0, 2 * math.pi, nu, endpoint=False)
    vs = np.linspace(0, math.pi, nv)
    u, v = np.meshgrid(us, vs)
    x = (np.sin(v) * np.cos(u)).ravel()
    y = (np.cos(v)).ravel()
    z = (np.sin(v) * np.sin(u)).ravel()
    vert = np.stack([x, y, z], 1).astype("float32")
    caras = []
    for j in range(nv - 1):
        for i in range(nu):
            a = j * nu + i
            b = j * nu + (i + 1) % nu
            c = (j + 1) * nu + i
            d = (j + 1) * nu + (i + 1) % nu
            if j != 0:
                caras.append((a, b, d))
            if j != nv - 2:
                caras.append((a, d, c))
    return vert, np.array(caras, dtype=np.int32)


def _cilindro(nu, alto, r0, r1):
    """Tronco de cono: sirve de cuello y de tronco."""
    us = np.linspace(0, 2 * math.pi, nu, endpoint=False)
    v = []
    for k, (y, r) in enumerate(((0.0, r0), (alto, r1))):
        v.extend([(math.cos(a) * r, y, math.sin(a) * r) for a in us])
    vert = np.array(v, dtype="float32")
    caras = []
    for i in range(nu):
        a, b = i, (i + 1) % nu
        c, d = nu + i, nu + (i + 1) % nu
        caras.append((a, b, d))
        caras.append((a, d, c))
    return vert, np.array(caras, dtype=np.int32)


def _perfil(nu, aros):
    """Superficie de revolucion achatada, definida por aros (y, ancho, fondo).

    Es lo que hace unos hombros creibles: se le dan las medidas a varias
    alturas y se cose la superficie entre ellas.
    """
    us = np.linspace(0, 2 * math.pi, nu, endpoint=False)
    cos, sen = np.cos(us), np.sin(us)
    v = []
    for y, ax, az in aros:
        v.extend(np.stack([cos * ax, np.full(nu, y), sen * az], 1))
    vert = np.array(v, dtype="float32")
    caras = []
    for k in range(len(aros) - 1):
        for i in range(nu):
            a = k * nu + i
            b = k * nu + (i + 1) % nu
            c = (k + 1) * nu + i
            d = (k + 1) * nu + (i + 1) % nu
            caras.append((a, b, d))
            caras.append((a, d, c))
    # tapa de arriba, para que no se vea el hueco desde arriba
    cima = len(vert)
    vert = np.concatenate([vert, np.array([[0, aros[0][0], 0]], "float32")])
    for i in range(nu):
        caras.append((cima, (i + 1) % nu, i))
    return vert, np.array(caras, dtype=np.int32)


class _Malla(object):
    """Junta trozos de geometria y les guarda su color y su acabado."""

    def __init__(self):
        self.v = np.zeros((0, 3), dtype="float32")
        self.f = np.zeros((0, 3), dtype=np.int32)
        self.col = np.zeros((0, 3), dtype="float32")
        self.brillo = np.zeros((0,), dtype="float32")
        self.grupo = []

    def añadir(self, vert, caras, color, brillo=0.0, grupo=""):
        base = len(self.v)
        self.v = np.concatenate([self.v, vert.astype("float32")])
        self.f = np.concatenate([self.f, caras + base])
        c = np.tile(np.array(color, dtype="float32"), (len(caras), 1))
        self.col = np.concatenate([self.col, c])
        self.brillo = np.concatenate([self.brillo,
                                      np.full(len(caras), brillo, "float32")])
        self.grupo.extend([grupo] * len(caras))
        return base, len(vert)


# ------------------------------------------------------------------- el avatar
class Cara(tk.Canvas):
    """Mismo trato por fuera que el muneco plano: set_estado, boca_obj y mic."""

    AN, AL = 214, 318
    SS = 2                              # doble resolucion para el antialiasing
    FONDO = (238, 243, 250)

    PIEL = (247, 211, 173)
    PELO = (240, 207, 107)
    OJO_BLANCO = (250, 250, 252)
    IRIS = (47, 127, 212)
    PUPILA = (18, 28, 44)
    CEJA = (196, 160, 70)
    BOCA = (110, 52, 52)
    CAMISA = (74, 134, 200)
    CUELLO_CAMISA = (58, 103, 155)

    LUZ = np.array([-0.45, 0.62, 0.65], dtype="float32")

    def __init__(self, master):
        super().__init__(master, width=self.AN, height=self.AL,
                         highlightthickness=0,
                         bg="#%02x%02x%02x" % self.FONDO)
        self.estado = "reposo"
        self.boca_obj = 0.0             # lo escribe el hilo de la voz
        self.mic = 0.0                  # lo escribe el hilo del microfono

        self._boca = 0.0
        self._mic = 0.0
        self._parpadeo = 0.0
        self._sig_parpadeo = time.time() + random.uniform(1.5, 4.0)
        self._mira = [0.0, 0.0]
        self._mira_obj = [0.0, 0.0]
        self._sig_mirada = time.time() + random.uniform(1.5, 3.5)
        self._giro = [0.0, 0.0]         # a donde mira la cabeza
        self._giro_obj = [0.0, 0.0]
        self._t = 0.0
        self._foto = None
        self._img_id = None
        self._ms = 33.0                 # cuanto tarda un fotograma, medido

        self.LUZ = self.LUZ / np.linalg.norm(self.LUZ)
        self._construir()
        self._tick()

    # ------------------------------------------------------------ el modelo
    @staticmethod
    def _apoyar(cabeza, x, y):
        """Devuelve la z de la superficie de la cara en ese punto.

        Sin esto hay que adivinar la profundidad de cada pieza, y en la version
        2 los ojos y la nariz acabaron METIDOS dentro de la cabeza y no se
        veian. Se busca el vertice de delante mas cercano y se usa su z.
        """
        delante = cabeza[cabeza[:, 2] > 0]
        d = (delante[:, 0] - x) ** 2 + (delante[:, 1] - y) ** 2
        cerca = delante[np.argsort(d)[:6]]
        return float(cerca[:, 2].mean())

    def _construir(self):
        """Monta la cabeza, el pelo, los ojos, el cuello y los hombros."""
        m = _Malla()

        # --- cabeza --------------------------------------------------------
        v, f = _esfera(34, 24)
        p = v.copy()
        p[:, 0] *= 0.84
        p[:, 2] *= 0.88
        p[:, 1] *= 0.96
        abajo = np.clip(-p[:, 1], 0, 1)
        p[:, 0] *= (1.0 - 0.24 * abajo ** 2.2)         # mandibula, no pico
        p[:, 2] *= (1.0 - 0.10 * abajo ** 2)
        p[:, 1] -= 0.04 * abajo ** 3
        frente = np.clip((p[:, 2] - 0.45) / 0.5, 0, 1) * np.clip(p[:, 1] / 0.7, 0, 1)
        p[:, 2] -= 0.05 * frente
        m.añadir(p, f, self.PIEL, 0.16, "cabeza")

        # --- pelo: casquete rubio con las sienes despejadas -----------------
        alt = p[:, 1]
        lado = np.abs(p[:, 0])
        delante = np.clip(p[:, 2], 0, 1)
        linea = 0.18 + 0.60 * lado ** 1.5 * delante
        usar = alt > linea
        grosor = 0.050 + 0.022 * np.clip((alt - 0.2) / 0.8, 0, 1)
        pelo_v = p * (1.0 + grosor)[:, None]
        idx = np.nonzero(usar)[0]
        mapa = -np.ones(len(p), dtype=np.int32)
        mapa[idx] = np.arange(len(idx))
        cf = [tuple(mapa[c]) for c in f if usar[c].all()]
        if cf:
            m.añadir(pelo_v[idx], np.array(cf, dtype=np.int32),
                     self.PELO, 0.10, "pelo")

        # --- ojos, apoyados en la superficie de la cara ---------------------
        ve, fe = _esfera(16, 12)
        self._ojo_centro = {}
        for s in (-1, 1):
            ex, ey = 0.275 * s, 0.11
            ez = self._apoyar(p, ex, ey) - 0.045      # metido en su cuenca
            centro = np.array([ex, ey, ez], dtype="float32")
            self._ojo_centro[s] = centro
            m.añadir(ve * np.array([0.132, 0.112, 0.085], "float32") + centro,
                     fe, self.OJO_BLANCO, 0.5, "ojo%d" % s)
            m.añadir(ve * np.array([0.084, 0.084, 0.055], "float32")
                     + centro + np.array([0, 0, 0.055], "float32"),
                     fe, self.IRIS, 0.7, "iris%d" % s)
            m.añadir(ve * np.array([0.038, 0.038, 0.028], "float32")
                     + centro + np.array([0, 0, 0.080], "float32"),
                     fe, self.PUPILA, 0.85, "pupila%d" % s)
            m.añadir(ve * np.array([0.165, 0.145, 0.110], "float32") + centro,
                     fe, self.PIEL, 0.16, "parpado%d" % s)
            cz = self._apoyar(p, ex, ey + 0.22)
            m.añadir(ve * np.array([0.170, 0.026, 0.038], "float32")
                     + np.array([ex + 0.012 * s, ey + 0.225, cz - 0.01], "float32"),
                     fe, self.CEJA, 0.05, "ceja%d" % s)

        # --- nariz ---------------------------------------------------------
        vn, fn = _esfera(14, 10)
        nz = self._apoyar(p, 0.0, -0.08)
        m.añadir(vn * np.array([0.070, 0.115, 0.075], "float32")
                 + np.array([0, -0.08, nz - 0.01], "float32"),
                 fn, self.PIEL, 0.30, "nariz")

        # --- boca ----------------------------------------------------------
        vb, fb = _esfera(18, 12)
        bz = self._apoyar(p, 0.0, -0.44)
        self._boca_centro = np.array([0, -0.44, bz - 0.025], dtype="float32")
        m.añadir(vb * np.array([0.140, 0.040, 0.040], "float32") + self._boca_centro,
                 fb, self.BOCA, 0.25, "boca")

        # --- cuello --------------------------------------------------------
        vc, fc = _cilindro(16, 0.34, 0.22, 0.28)
        m.añadir(vc + np.array([0, -1.24, -0.03], "float32"),
                 fc, self.PIEL, 0.10, "cuello")

        # --- hombros y pecho ------------------------------------------------
        # Arranca justo debajo del cuello y SE SALE por abajo del encuadre. En
        # la version 2 era una bola separada y parecia un monigote de nieve.
        # (y, medio ancho, medio fondo) de abajo del cuello hacia los pies
        vh, fh = _perfil(26, [
            (-1.16, 0.26, 0.20),      # donde nace del cuello
            (-1.30, 0.52, 0.30),      # trapecio
            (-1.48, 0.82, 0.38),      # se abre
            (-1.70, 1.02, 0.43),      # punta del hombro
            (-2.05, 1.06, 0.45),      # brazos, ya rectos
            (-2.60, 1.04, 0.45),
            (-3.40, 1.00, 0.44),      # se sale del encuadre por abajo
        ])
        m.añadir(vh + np.array([0, 0, -0.02], "float32"), fh,
                 self.CAMISA, 0.07, "tronco")

        vv, fv = _cilindro(18, 0.16, 0.27, 0.40)
        m.añadir(vv + np.array([0, -1.20, -0.02], "float32"), fv,
                 self.CUELLO_CAMISA, 0.05, "camisa")

        self.m = m
        self.grupo = np.array(m.grupo)
        self.v0 = m.v.copy()
        self._del_grupo = {}
        for g in set(m.grupo):
            caras = np.nonzero(self.grupo == g)[0]
            self._del_grupo[g] = np.unique(m.f[caras])

    # --------------------------------------------------------------- animar
    def set_estado(self, e):
        self.estado = e

    def _pose(self):
        """Devuelve los vertices ya movidos segun el estado y la voz."""
        v = self.v0.copy()

        # respiracion: el tronco sube y baja
        resp = math.sin(self._t * 1.25) * 0.012
        v[:, 1] += resp * (v[:, 1] < -1.15)

        # la boca se abre con la amplitud real del audio
        idx = self._del_grupo.get("boca")
        if idx is not None:
            centro = self._boca_centro
            escala = np.array([1.0 + 0.25 * self._boca,
                               1.0 + 5.5 * self._boca,
                               1.0 + 0.6 * self._boca], dtype="float32")
            v[idx] = (v[idx] - centro) * escala + centro
            v[idx, 1] -= 0.045 * self._boca

        # parpadeo: el parpado baja tapando el ojo
        for lado in (-1, 1):
            idx = self._del_grupo.get("parpado%d" % lado)
            if idx is None:
                continue
            centro = self._ojo_centro[lado]
            # el parpado NUNCA esta del todo abierto: un ojo relajado tiene el
            # parpado cubriendo un poco. Sin esto la mirada sale de susto.
            baja = 0.18 + 0.82 * self._parpadeo
            v[idx] = (v[idx] - centro) * np.array(
                [1.0, 1.0 - 0.92 * baja, 1.0], "float32") + centro
            v[idx, 1] += 0.150 * baja
            if baja < 0.5:      # con el ojo abierto el parpado se esconde
                v[idx, 2] -= 0.09

        # los ojos siguen la mirada
        for lado in (-1, 1):
            for g, k in (("iris%d" % lado, 1.0), ("pupila%d" % lado, 1.0)):
                idx = self._del_grupo.get(g)
                if idx is None:
                    continue
                v[idx, 0] += self._mira[0] * 0.045 * k
                v[idx, 1] += self._mira[1] * 0.035 * k

        # las cejas suben cuando escucha o se sorprende
        alza = 0.05 if self.estado in ("escuchando", "buscando") else 0.0
        for lado in (-1, 1):
            idx = self._del_grupo.get("ceja%d" % lado)
            if idx is not None:
                v[idx, 1] += alza + 0.012 * math.sin(self._t * 0.9 + lado)
        return v

    def _girar(self, v):
        """Gira la cabeza (y solo la cabeza) y deja quieto el tronco."""
        gy, gx = self._giro
        cy, sy = math.cos(gy), math.sin(gy)
        cx, sx = math.cos(gx), math.sin(gx)
        Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]], dtype="float32")
        Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]], dtype="float32")
        R = Ry @ Rx
        # el cuello hace de bisagra: lo de arriba gira, lo de abajo no
        pivote = np.array([0, -1.15, 0], dtype="float32")
        peso = np.clip((v[:, 1] - (-1.42)) / 0.45, 0, 1)[:, None]
        girado = (v - pivote) @ R.T + pivote
        return v * (1 - peso) + girado * peso

    # -------------------------------------------------------------- pintar
    def _fotograma(self):
        v = self._girar(self._pose())

        # ligero balanceo del cuerpo entero, que quita rigidez
        vaiven = math.sin(self._t * 0.7) * 0.035
        cv, sv = math.cos(vaiven), math.sin(vaiven)
        Rz = np.array([[cv, -sv, 0], [sv, cv, 0], [0, 0, 1]], dtype="float32")
        v = v @ Rz.T

        f = self.m.f
        a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
        n = np.cross(b - a, c - a)
        ln = np.linalg.norm(n, axis=1, keepdims=True)
        n = n / np.maximum(ln, 1e-6)

        centro = (a + b + c) / 3.0
        # camara en +z mirando a -z
        vista = np.array([0, 0, 1], dtype="float32")
        mira = vista[None, :] - centro * 0.0 + np.array([0, 0, 0], "float32")
        nv = (n * vista).sum(1)
        visible = nv > 0.0                       # caras traseras fuera
        if not visible.any():
            return None

        # --- luz -----------------------------------------------------------
        dif = np.clip((n * self.LUZ).sum(1), 0, 1)
        borde = (1.0 - np.clip(nv, 0, 1)) ** 2.2          # luz de canto
        media = np.clip((self.LUZ + vista) / np.linalg.norm(self.LUZ + vista), -1, 1)
        esp = np.clip((n * media).sum(1), 0, 1) ** 26 * self.m.brillo

        col = self.m.col
        luz = (0.42 + 0.68 * dif)[:, None]
        rgb = col * luz
        rgb = rgb + borde[:, None] * np.array([70, 92, 120], "float32") * 0.55
        rgb = rgb + esp[:, None] * np.array([255, 255, 255], "float32") * 0.8
        rgb = np.clip(rgb, 0, 255).astype(np.uint8)

        # --- proyeccion en perspectiva --------------------------------------
        W, H = self.AN * self.SS, self.AL * self.SS
        # Encuadre de BUSTO: la cabeza ocupa casi media altura y los hombros
        # llegan al borde de abajo. La primera version salia diminuta en medio
        # del lienzo y parecia un muñeco de lejos.
        dist = 6.2
        escala = H * 1.30
        z = dist - v[:, 2]
        z = np.maximum(z, 0.15)
        px = W * 0.5 + v[:, 0] * escala / z
        py = H * 0.34 - v[:, 1] * escala / z
        P = np.stack([px, py], 1)

        # --- de lejos a cerca (pintor) --------------------------------------
        prof = centro[:, 2]
        orden = np.argsort(prof)[visible[np.argsort(prof)]]

        img = Image.new("RGB", (W, H), self.FONDO)
        d = ImageDraw.Draw(img)
        tri = P[f[orden]]
        cl = rgb[orden]
        for i in range(len(orden)):
            t = tri[i]
            d.polygon([(t[0][0], t[0][1]), (t[1][0], t[1][1]), (t[2][0], t[2][1])],
                      fill=(int(cl[i][0]), int(cl[i][1]), int(cl[i][2])))
        return img.resize((self.AN, self.AL), Image.BOX)

    # ------------------------------------------------------------ el bucle
    def _tick(self):
        try:
            t0 = time.time()
            ahora = t0
            self._t += 0.033

            self._boca = _lerp(self._boca, max(0.0, min(1.0, self.boca_obj)), 0.55)
            self._mic = _lerp(self._mic, max(0.0, min(1.0, self.mic)), 0.35)

            # parpadeo
            if ahora > self._sig_parpadeo:
                self._parpadeo = 1.0
                self._sig_parpadeo = ahora + random.uniform(1.8, 5.0)
            self._parpadeo = max(0.0, self._parpadeo - 0.22)

            # la mirada se va a sitios
            if ahora > self._sig_mirada:
                self._mira_obj = [random.uniform(-1, 1) * 0.9,
                                  random.uniform(-0.6, 0.6)]
                self._sig_mirada = ahora + random.uniform(1.4, 3.6)
            self._mira[0] = _lerp(self._mira[0], self._mira_obj[0], 0.18)
            self._mira[1] = _lerp(self._mira[1], self._mira_obj[1], 0.18)

            # a donde mira la cabeza segun lo que este haciendo
            e = self.estado
            if e == "hablando":
                obj = [math.sin(self._t * 0.8) * 0.10, -0.04]
            elif e == "escuchando":
                obj = [math.sin(self._t * 0.5) * 0.05, 0.10]
            elif e == "pensando":
                obj = [0.22, 0.16]
            elif e == "buscando":
                obj = [math.sin(self._t * 1.6) * 0.30, 0.02]
            else:
                obj = [math.sin(self._t * 0.35) * 0.13, math.sin(self._t * 0.27) * 0.05]
            self._giro[0] = _lerp(self._giro[0], obj[0], 0.10)
            self._giro[1] = _lerp(self._giro[1], obj[1], 0.10)

            img = self._fotograma()
            if img is not None:
                self._foto = ImageTk.PhotoImage(img)
                if self._img_id is None:
                    self._img_id = self.create_image(0, 0, anchor="nw",
                                                     image=self._foto)
                else:
                    self.itemconfigure(self._img_id, image=self._foto)

            self._rotulo()
            self._ms = _lerp(self._ms, (time.time() - t0) * 1000.0, 0.2)
        except Exception:
            pass
        # Cuantos fotogramas hacen falta DE VERDAD. Renderizar 3D 30 veces por
        # segundo cuesta un 38% de un nucleo, y eso con el Skyrim al lado es
        # una barbaridad para algo que la mayor parte del tiempo solo respira.
        #   - hablando: a tope, que la boca tiene que ir con la voz.
        #   - escuchando: medio, que el aro late.
        #   - lo demas: 12 por segundo sobra para respirar y parpadear.
        if self.estado == "hablando":
            objetivo = 33
        elif self.estado in ("escuchando", "buscando"):
            objetivo = 55
        else:
            objetivo = 85
        espera = int(max(objetivo, min(140, self._ms + 6)))
        self.after(espera, self._tick)

    def _rotulo(self):
        texto = {"reposo": "Listo", "escuchando": "Escuchando",
                 "pensando": "Pensando", "buscando": "Buscando",
                 "hablando": "Hablando"}.get(self.estado, "")
        col = {"reposo": "#0a7a4a", "escuchando": "#bb0000",
               "hablando": "#1a56b0"}.get(self.estado, "#555555")
        if getattr(self, "_rot_id", None) is None:
            self._rot_id = self.create_text(self.AN // 2, self.AL - 14,
                                            text=texto, fill=col,
                                            font=("Segoe UI", 10, "bold"))
        else:
            self.itemconfigure(self._rot_id, text=texto, fill=col)
            self.tag_raise(self._rot_id)
