# -*- coding: utf-8 -*-
r"""
El muneco de Berna: cuerpo entero, rubio, ojos azules y pelo solo arriba.

Angel lo pidio asi el 2026-08-26: "rubio con los ojos azules, que solo tenga
pelo por la parte superior de la cabeza, con cuerpo completo, y que haga
movimientos". Antes era solo una cabeza flotando.

COMO ESTA HECHO
  Un Canvas de Tk que se borra y se vuelve a pintar entero 30 veces por
  segundo. No hay imagenes ni GIF: todo son ovalos, lineas gordas con las
  puntas redondas y poligonos suavizados. Asi pesa nada y se puede animar
  cualquier cosa.

  LA REGLA DE LOS HILOS, que no se toca: los hilos de trabajo (la voz, el
  microfono) SOLO escriben en tres atributos sueltos -- boca_obj, mic y
  estado -- y el dibujado ocurre siempre en el hilo de la interfaz, dentro
  de _tick. Tk no aguanta que le pinten desde otro hilo.

  La boca sale de la amplitud REAL del audio que esta sonando (boca_obj lo
  va escribiendo el reproductor), no es al azar. Por eso encaja con la voz.

LOS BRAZOS Y LAS PIERNAS
  Cada miembro son dos huesos. Y aqui esta la unica decision de fondo del
  modulo, que se tomo despues de que la primera version saliera mal:

  **Las poses se describen por DONDE VA LA MANO, no por el angulo del codo.**

  Al principio se guardaban los angulos del hombro y del codo, y salio un
  muneco con la mano en la barriga cuando tenia que estar en la oreja: con
  angulos a ojo es imposible saber donde acaba la mano, y peor todavia
  saber si el brazo llega. Ahora se dice "la mano a la oreja" y una
  cinematica inversa de dos huesos (_angulos_hacia) calcula los angulos.
  Si el sitio queda mas lejos que el brazo, se estira todo lo que puede en
  esa direccion en vez de romperse.

  Las manos van en coordenadas relativas al hombro: dx positivo es HACIA
  AFUERA (espejado por el signo s) y dy positivo es HACIA ABAJO. Asi la
  misma pose vale para los dos lados.

  Y las poses no saltan de golpe: cada fotograma la mano actual persigue a
  la de destino. Eso es lo que hace que parezca un gesto y no un pantallazo.
"""
import math
import time
import random
import tkinter as tk


def _lerp(a, b, f):
    return a + (b - a) * f


class Cara(tk.Canvas):
    """El muneco entero. Se sigue llamando Cara porque asi lo llama la ventana."""

    AN, AL = 214, 368

    PIEL = "#f7d3ad"
    PIEL_S = "#e8bd91"          # sombra de la piel
    BORDE = "#c08b5c"
    PELO = "#f0cf6b"            # rubio
    PELO_S = "#d4ac3f"          # rubio de sombra
    CEJA = "#d9b24e"
    OJO = "#2f7fd4"             # azul
    OJO_B = "#1c4f8f"
    BOCA = "#93343c"
    BOCA_B = "#6d2229"
    CAMISA = "#4a86c8"
    CAMISA_S = "#39679b"
    CUELLO_C = "#6ea3dd"
    PANTALON = "#3d4759"
    PANTALON_S = "#2f3746"
    ZAPATO = "#332e2a"
    FONDO = "#eef3fa"
    SUELO = "#dbe4f0"

    ROTULO = {
        "reposo": ("Listo", "#5b7a5e"),
        "escuchando": ("Te escucho...", "#b23a3a"),
        "pensando": ("Pensando...", "#8a6a1f"),
        "buscando": ("Trabajando...", "#7a4fa8"),
        "hablando": ("Hablando", "#2c5fa8"),
    }

    HUESO1, HUESO2 = 40, 38          # brazo y antebrazo

    # Donde va cada mano, medido DESDE SU HOMBRO: (afuera, abajo).
    # Primero la izquierda, luego la derecha.
    MANOS = {
        "reposo":     ((4, 74), (4, 74)),            # colgando al lado
        "escuchando": ((4, 74), (14, -58)),          # la derecha, a la oreja
        "pensando":   ((-16, 46), (-26, -34)),       # la derecha, a la barbilla
        "buscando":   ((17, 36), (17, 36)),          # las dos delante, tecleando
        "hablando":   ((26, 26), (26, 26)),          # gesticulando a la altura del pecho
        "saludo":     ((22, -70), (4, 74)),          # la izquierda arriba
    }

    def __init__(self, master):
        super().__init__(master, width=self.AN, height=self.AL,
                         highlightthickness=0, bg=self.FONDO)
        self.estado = "reposo"
        self.boca_obj = 0.0          # lo escribe el hilo de la voz
        self.mic = 0.0               # lo escribe el hilo del microfono
        self._boca = 0.0
        self._mic = 0.0
        self._parpadeo = 0.0
        self._sig_parpadeo = time.time() + random.uniform(1.5, 4.0)
        self._mira = [0.0, 0.0]
        self._mira_obj = [0.0, 0.0]
        self._sig_mirada = time.time() + random.uniform(1.5, 3.5)
        self._manos = [list(self.MANOS["reposo"][0]), list(self.MANOS["reposo"][1])]
        self._saludando = 0.0
        self._sig_saludo = time.time() + random.uniform(14, 26)
        self._t = 0.0
        self._tick()

    def set_estado(self, e):
        self.estado = e

    # ---------------------------------------------------- animacion
    def _tick(self):
        try:
            ahora = time.time()
            self._t += 0.033

            self._boca = _lerp(self._boca, max(0.0, min(1.0, self.boca_obj)), 0.55)
            self._mic = _lerp(self._mic, max(0.0, min(1.0, self.mic)), 0.35)

            # parpadeo
            if self._parpadeo > 0:
                self._parpadeo -= 0.16
                if self._parpadeo <= 0:
                    self._parpadeo = 0.0
                    self._sig_parpadeo = ahora + random.uniform(1.8, 5.5)
            elif ahora >= self._sig_parpadeo:
                self._parpadeo = 1.0

            # de vez en cuando saluda con la mano, pero solo si esta parado
            if self._saludando > 0:
                self._saludando -= 0.033
                if self._saludando <= 0:
                    self._saludando = 0.0
                    self._sig_saludo = ahora + random.uniform(20, 40)
            elif self.estado == "reposo" and ahora >= self._sig_saludo:
                self._saludando = 2.2

            # la mirada deriva sola
            if ahora >= self._sig_mirada:
                if self.estado == "pensando":
                    self._mira_obj = [random.uniform(-1, 1), random.uniform(-1.0, -0.35)]
                    self._sig_mirada = ahora + random.uniform(0.5, 1.1)
                elif self.estado == "buscando":
                    self._mira_obj = [-self._mira_obj[0] or 1.0, 0.4]
                    self._sig_mirada = ahora + random.uniform(0.26, 0.45)
                elif self.estado == "escuchando":
                    self._mira_obj = [random.uniform(-0.25, 0.25), 0.1]
                    self._sig_mirada = ahora + random.uniform(1.0, 2.0)
                else:
                    self._mira_obj = [random.uniform(-0.8, 0.8), random.uniform(-0.4, 0.5)]
                    self._sig_mirada = ahora + random.uniform(1.4, 3.6)
            self._mira[0] = _lerp(self._mira[0], self._mira_obj[0], 0.14)
            self._mira[1] = _lerp(self._mira[1], self._mira_obj[1], 0.14)

            self._mover_brazos()
            self._dibujar()
        except Exception:
            pass
        self.after(33, self._tick)

    def _mover_brazos(self):
        """Lleva las manos a donde toca segun el estado, sin saltos."""
        pose = "saludo" if self._saludando > 0 else self.estado
        base = self.MANOS.get(pose, self.MANOS["reposo"])
        objetivo = [list(base[0]), list(base[1])]
        t = self._t

        if pose == "saludo":                       # la mano va y viene
            objetivo[0][0] += math.sin(t * 9.0) * 13
            objetivo[0][1] += math.cos(t * 9.0) * 5
        elif pose == "hablando":                   # gesticula al hablar
            g = 0.35 + self._boca * 1.5
            for i, desfase in ((0, 0.0), (1, 2.6)):
                objetivo[i][0] += math.sin(t * 2.4 + desfase) * 13 * g
                objetivo[i][1] += math.sin(t * 3.1 + desfase) * 17 * g
        elif pose == "buscando":                   # teclear
            objetivo[0][1] += math.sin(t * 7.5) * 6
            objetivo[1][1] += math.sin(t * 7.5 + 1.7) * 6
        elif pose == "escuchando":
            objetivo[1][1] += math.sin(t * 1.6) * 2
        elif pose == "pensando":
            objetivo[1][1] += math.sin(t * 1.2) * 2
        else:                                      # respirar
            for i in (0, 1):
                objetivo[i][0] += math.sin(t * 1.1 + i * 0.4) * 2.5
                objetivo[i][1] += math.sin(t * 1.5) * 2.0

        rapidez = 0.34 if pose == "saludo" else 0.15
        for i in (0, 1):
            for j in (0, 1):
                self._manos[i][j] = _lerp(self._manos[i][j], objetivo[i][j], rapidez)

    # ---------------------------------------------------- utilidades de dibujo
    @staticmethod
    def _angulos_hacia(dx, dy, l1, l2, codo=1):
        """Cinematica inversa de dos huesos: donde quiero la mano -> angulos.

        (dx, dy) es el sitio al que va la punta, medido desde la articulacion
        de arriba, con dx hacia afuera y dy hacia abajo. Devuelve los dos
        angulos en grados con el mismo criterio que _miembro: 0 = colgando.

        Si el sitio queda mas lejos de lo que da el brazo, se estira todo lo
        que puede en esa direccion, que es lo que hace una persona; y si queda
        demasiado cerca, se dobla al maximo. Nunca se rompe.
        """
        d = math.hypot(dx, dy)
        d = max(abs(l1 - l2) + 0.5, min(l1 + l2 - 0.5, d))
        # angulo de la direccion, midiendo desde "hacia abajo"
        base = math.degrees(math.atan2(dx, dy))
        cos_a = (d * d + l1 * l1 - l2 * l2) / (2.0 * d * l1)
        alfa = math.degrees(math.acos(max(-1.0, min(1.0, cos_a))))
        cos_b = (l1 * l1 + l2 * l2 - d * d) / (2.0 * l1 * l2)
        beta = math.degrees(math.acos(max(-1.0, min(1.0, cos_b))))
        return base + alfa * codo, -(180.0 - beta) * codo

    def _brazo(self, x, y, dx, dy, s, grosor, color, mano):
        a1, a2 = self._angulos_hacia(dx, dy, self.HUESO1, self.HUESO2)
        return self._miembro(x, y, a1, a2, self.HUESO1, self.HUESO2, s,
                             grosor, color, mano=mano)

    def _miembro(self, x, y, a1, a2, l1, l2, s, grosor, color, mano=None, pie=None):
        """Dibuja un brazo o una pierna de dos huesos y devuelve donde cae la punta."""
        r1 = math.radians(a1)
        cx1 = x + s * l1 * math.sin(r1)
        cy1 = y + l1 * math.cos(r1)
        r2 = math.radians(a1 + a2)
        cx2 = cx1 + s * l2 * math.sin(r2)
        cy2 = cy1 + l2 * math.cos(r2)
        self.create_line(x, y, cx1, cy1, fill=color, width=grosor, capstyle="round")
        self.create_line(cx1, cy1, cx2, cy2, fill=color, width=grosor - 1,
                         capstyle="round")
        if mano:
            self.create_oval(cx2 - 7, cy2 - 7, cx2 + 7, cy2 + 7,
                             fill=mano, outline=self.BORDE, width=1)
        if pie:
            self.create_oval(cx2 - 15, cy2 - 7, cx2 + 10, cy2 + 9,
                             fill=pie, outline="")
        return cx2, cy2

    # ---------------------------------------------------- dibujo
    def _dibujar(self):
        self.delete("all")
        t = self._t

        cx = self.AN / 2.0
        respira = math.sin(t * 1.5)
        balanceo = math.sin(t * 0.8) * 2.0

        # cuanto se agita segun lo que este haciendo
        if self.estado == "hablando":
            balanceo += math.sin(t * 2.3) * 2.2 + self._boca * 1.5
        elif self.estado == "escuchando":
            balanceo -= 3.0                        # se echa un poco hacia ti
        elif self.estado == "buscando":
            balanceo += math.sin(t * 3.4) * 1.2

        # ---- medidas del cuerpo (todas cuelgan de estas)
        # Proporciones: la primera version salio con unas piernas larguisimas
        # y un torso de nino. La regla que cuadra es que las piernas midan mas
        # o menos lo que el torso mas la cabeza.
        y_cabeza = 62 + respira * 1.4
        r_ancho, r_alto = 41, 44
        y_hombros = y_cabeza + r_alto + 22
        y_cadera = y_hombros + 96
        y_suelo = self.AL - 34
        cxc = cx + balanceo                        # el cuerpo se balancea entero

        # inclinacion de la cabeza: donde mas se nota el estado de animo
        inclina = balanceo * 0.9
        if self.estado == "pensando":
            inclina += 8.0 + math.sin(t * 1.8) * 1.6
        elif self.estado == "escuchando":
            inclina -= 5.0
        elif self.estado == "hablando":
            inclina += math.sin(t * 2.3) * 2.4
        cxh = cx + inclina

        # ---- sombra en el suelo
        self.create_oval(cxc - 52, y_suelo - 8, cxc + 52, y_suelo + 8,
                         fill=self.SUELO, outline="")

        # ---- aro que late con el microfono
        if self.estado == "escuchando":
            for r0, col, gr in ((104, "#7fb0ff", 3), (104, "#b9d3ff", 2)):
                r = r0 + self._mic * (30 if gr == 3 else 14)
                self.create_oval(cxh - r, y_cabeza + 24 - r, cxh + r, y_cabeza + 24 + r,
                                 outline=col, width=gr)

        # ---- burbujas de pensar
        if self.estado == "pensando":
            for i in range(3):
                f = (math.sin(t * 4.0 - i * 0.9) + 1) / 2.0
                rr = 4 + f * 3
                bx = cxh + 44 + i * 15
                by = y_cabeza - 44 - i * 9
                self.create_oval(bx - rr, by - rr, bx + rr, by + rr,
                                 fill="#c4b483", outline="")

        # ---- piernas (van detras del torso)
        for s in (-1, 1):
            base = 4 if s < 0 else -4
            paso = 0
            if self.estado == "buscando":
                paso = math.sin(t * 3.4 + (0 if s < 0 else math.pi)) * 3
            self._miembro(cxc + s * 17, y_cadera, base + paso, -base * 0.6,
                          (y_suelo - y_cadera) * 0.52, (y_suelo - y_cadera) * 0.46,
                          s, 17, self.PANTALON, pie=self.ZAPATO)

        # ---- brazo de detras (el mas alejado se pinta antes que el torso)
        self._brazo(cxc - 28, y_hombros + 6, self._manos[0][0], self._manos[0][1],
                    -1, 13, self.CAMISA_S, self.PIEL_S)

        # ---- torso
        ancho = 34 + respira * 0.9
        self.create_polygon(
            cxc - ancho, y_cadera, cxc - ancho - 4, y_hombros + 6,
            cxc - 26, y_hombros - 8, cxc, y_hombros - 12, cxc + 26, y_hombros - 8,
            cxc + ancho + 4, y_hombros + 6, cxc + ancho, y_cadera,
            fill=self.CAMISA, outline=self.CAMISA_S, width=2, smooth=True)
        # cuello de la camisa
        self.create_polygon(cxc - 15, y_hombros - 10, cxc, y_hombros + 14,
                            cxc + 15, y_hombros - 10,
                            fill=self.CUELLO_C, outline="")
        # cinturon
        self.create_rectangle(cxc - ancho + 1, y_cadera - 9, cxc + ancho - 1,
                              y_cadera + 1, fill=self.PANTALON_S, outline="")

        # ---- brazo de delante
        self._brazo(cxc + 28, y_hombros + 6, self._manos[1][0], self._manos[1][1],
                    1, 13, self.CAMISA, self.PIEL)

        # ---- cuello
        self.create_polygon(cxh - 9, y_cabeza + r_alto - 8, cxh + 9,
                            y_cabeza + r_alto - 8, cxc + 11, y_hombros - 2,
                            cxc - 11, y_hombros - 2,
                            fill=self.PIEL_S, outline="", smooth=False)

        # ---- orejas
        for s in (-1, 1):
            x = cxh + s * (r_ancho - 2)
            self.create_oval(x - 7, y_cabeza + 2, x + 7, y_cabeza + 22,
                             fill=self.PIEL, outline=self.BORDE, width=2)

        # ---- cabeza
        self.create_oval(cxh - r_ancho, y_cabeza - r_alto,
                         cxh + r_ancho, y_cabeza + r_alto,
                         fill=self.PIEL, outline=self.BORDE, width=2)

        # ---- pelo: SOLO por arriba, con las sienes despejadas
        # Es media elipse mas estrecha que la cabeza, apoyada en la coronilla:
        # asi se ve piel a los lados y queda claro que arriba tiene y a los
        # lados no. Lo pidio expresamente.
        pa, pal = r_ancho - 9, 34
        py = y_cabeza - r_alto + 20
        self.create_arc(cxh - pa, py - pal, cxh + pa, py + pal,
                        start=0, extent=180, style="chord",
                        fill=self.PELO, outline=self.PELO_S, width=2)
        # entradas: dos curvitas que bajan un poco por delante
        for s in (-1, 1):
            self.create_arc(cxh + s * (pa - 13) - 11, py - 13,
                            cxh + s * (pa - 13) + 11, py + 13,
                            start=0, extent=180, style="chord",
                            fill=self.PELO, outline="")
        # mechon que se mueve al respirar
        mech = math.sin(t * 1.5) * 2.5
        self.create_line(cxh - 6, py - pal + 6, cxh + 6 + mech, py - pal - 4,
                         fill=self.PELO_S, width=4, capstyle="round", smooth=True)

        # ---- cejas
        for s in (-1, 1):
            x = cxh + s * 17
            y = y_cabeza - 22
            if self.estado == "pensando":
                dy_i, dy_e = (-6, 3) if s < 0 else (3, 1)
            elif self.estado == "buscando":
                dy_i, dy_e = 4, -2
            elif self.estado == "escuchando":
                dy_i, dy_e = -5, -4
            elif self.estado == "hablando":
                sube = -self._boca * 5
                dy_i, dy_e = sube, sube - 1
            else:
                dy_i, dy_e = 0, 1
            self.create_line(x + s * -10, y + dy_i, x + s * 11, y + dy_e,
                             fill=self.CEJA, width=5, capstyle="round")

        # ---- ojos azules
        for s in (-1, 1):
            x = cxh + s * 17
            y = y_cabeza - 4
            ancho_o = 12 if self.estado != "escuchando" else 13
            alto_o = 10 if self.estado != "escuchando" else 11
            self.create_oval(x - ancho_o, y - alto_o, x + ancho_o, y + alto_o,
                             fill="white", outline=self.BORDE, width=2)
            px = x + self._mira[0] * 4.5
            py2 = y + self._mira[1] * 3.5
            self.create_oval(px - 6, py2 - 6, px + 6, py2 + 6,
                             fill=self.OJO, outline=self.OJO_B, width=1)
            self.create_oval(px - 2.6, py2 - 2.6, px + 2.6, py2 + 2.6,
                             fill="#20242c", outline="")
            self.create_oval(px - 4.4, py2 - 4.8, px - 1.4, py2 - 1.8,
                             fill="white", outline="")
            if self._parpadeo > 0.02:
                h = (alto_o * 2 + 4) * self._parpadeo
                self.create_rectangle(x - ancho_o - 1, y - alto_o - 2,
                                      x + ancho_o + 1, y - alto_o - 2 + h,
                                      fill=self.PIEL, outline="")
                self.create_line(x - ancho_o, y - alto_o - 2 + h,
                                 x + ancho_o, y - alto_o - 2 + h,
                                 fill=self.BORDE, width=2)

        # ---- nariz
        self.create_line(cxh, y_cabeza + 4, cxh - 4, y_cabeza + 16,
                         cxh + 3, y_cabeza + 17,
                         fill=self.BORDE, width=2, smooth=True, capstyle="round")

        # ---- boca, con la altura del audio de verdad
        by = y_cabeza + 30
        if self._boca < 0.07:
            if self.estado == "pensando":
                self.create_line(cxh - 11, by, cxh + 11, by - 3,
                                 fill=self.BOCA, width=3, capstyle="round")
            else:
                self.create_arc(cxh - 17, by - 13, cxh + 17, by + 9,
                                start=200, extent=140, style="arc",
                                outline=self.BOCA, width=3)
        else:
            an = 20 + self._boca * 11
            al = 4 + self._boca * 21
            self.create_oval(cxh - an / 2, by - al / 2, cxh + an / 2, by + al / 2,
                             fill=self.BOCA, outline=self.BOCA_B, width=2)
            if self._boca > 0.42:
                lw, lh = an * 0.5, al * 0.34
                self.create_oval(cxh - lw / 2, by + al / 2 - lh - 2,
                                 cxh + lw / 2, by + al / 2 - 2,
                                 fill="#d8737a", outline="")

        # ---- rotulo de estado
        txt, col = self.ROTULO.get(self.estado, ("", "#666"))
        self.create_text(self.AN / 2, self.AL - 10, text=txt,
                         fill=col, font=("Segoe UI", 10, "bold"))
