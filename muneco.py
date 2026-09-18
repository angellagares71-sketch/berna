# -*- coding: utf-8 -*-
r"""
El muneco de Sobri: cuerpo entero dibujado a mano, con volumen y movimiento.

Angel lo pidio asi el 2026-09: "que sea muchisimo mas realista, con brazos y
piernas, que pueda girar el cuello y hacer movimientos completos".

EL CAMBIO DE FONDO: YA NO SE DIBUJA CON TK
  La version anterior usaba las figuras del Canvas de Tk (create_oval,
  create_line...). Eso tiene un techo bajisimo: **no hay suavizado de bordes,
  ni degradados, ni sombras**. Todo salia con los bordes de sierra y plano
  como una pegatina.

  Ahora cada fotograma se PINTA CON PIL al doble de resolucion y se reduce
  con LANCZOS. Al reducir, los bordes se suavizan solos. Y como es una imagen
  de verdad, se pueden meter sombras difuminadas, luces y medios tonos, que
  es lo que hace que una cosa parezca redonda en vez de recortada.

  Medido en este ordenador: **10 milisegundos por fotograma**, o sea un 25%
  de UN nucleo de los doce que tiene, yendo a 25 imagenes por segundo. El
  truco para que salga tan barato es que **el desenfoque de las sombras se
  calcula en pequeno y luego se estira**: difuminar es lo que mas cuesta, y a
  la mitad de tamano cuesta cuatro veces menos. Se probaron las cuatro
  combinaciones antes de elegir (x3 con sombra cara costaba 25 ms).

EL CUELLO GIRA DE VERDAD
  Hay un `yaw` (girar a los lados) y un `pitch` (asentir). No es que la
  cabeza se mueva de sitio: **la cara se recalcula**. Los rasgos se desplazan
  y ademas se COMPRIMEN en horizontal con el coseno del giro, la oreja del
  lado al que mira se esconde, la nariz asoma por el perfil y el cuello se
  inclina. Es el truco de dibujante de toda la vida para fingir tres
  dimensiones con dos, y funciona porque el ojo espera justo eso.

LOS MIEMBROS SON CAPSULAS QUE SE ESTRECHAN
  Cada hueso se pinta con `_capsula`: un tronco que va de gordo a fino con
  las puntas redondeadas, y encima una franja de luz y un borde de sombra.
  Tres pasadas por hueso, y de plano pasa a parecer un brazo.

  Las poses se siguen describiendo por DONDE VA LA MANO, no por angulos, y
  `_angulos_hacia` resuelve el codo. Esa decision viene de la version
  anterior y se mantiene por lo mismo: con angulos a ojo es imposible saber
  donde acaba la mano.

LA REGLA DE LOS HILOS, QUE NO SE TOCA
  Los hilos de trabajo (la voz, el microfono) SOLO escriben en tres
  atributos sueltos -- `boca_obj`, `mic` y `estado` -- y todo el pintado
  ocurre en el hilo de la interfaz, dentro de `_tick`. Tk no aguanta que le
  pinten desde otro hilo.

  La boca sale de la amplitud REAL del audio que esta sonando, no es al azar.
  Por eso encaja con lo que dice.
"""
import math
import time
import random
import tkinter as tk

from PIL import Image, ImageDraw, ImageFilter, ImageTk


def _lerp(a, b, f):
    return a + (b - a) * f


def _mez(c1, c2, f):
    """Mezcla dos colores. Para las luces y las sombras."""
    return tuple(int(_lerp(c1[i], c2[i], f)) for i in range(3))


class Cara(tk.Canvas):
    """El muneco entero. Se sigue llamando Cara porque asi lo llama la ventana."""

    AN, AL = 236, 424
    SS = 2                      # se pinta al doble y se reduce: eso suaviza
    MS = 40                     # 25 imagenes por segundo

    # ---- paleta
    FONDO = (238, 243, 250)
    SUELO = (214, 223, 235)

    PIEL = (240, 202, 170)
    PIEL_L = (252, 227, 202)
    PIEL_S = (211, 163, 128)
    PIEL_SS = (181, 130, 98)
    BOCA_D = (92, 46, 48)       # dentro de la boca
    LABIO = (196, 122, 116)
    LABIO_S = (168, 96, 92)
    DIENTE = (246, 243, 240)

    PELO = (226, 189, 104)      # rubio
    PELO_L = (247, 222, 152)
    PELO_S = (176, 139, 62)
    CEJA = (198, 158, 84)

    OJO_B = (250, 248, 246)     # blanco del ojo
    IRIS = (78, 143, 200)       # azul
    IRIS_S = (44, 90, 142)
    IRIS_L = (140, 194, 232)
    PUPILA = (26, 28, 34)

    CAMISA = (78, 122, 176)
    CAMISA_L = (108, 155, 208)
    CAMISA_S = (52, 86, 130)
    CUELLO_C = (96, 146, 200)

    PANTALON = (58, 66, 84)
    PANTALON_L = (80, 90, 112)
    PANTALON_S = (40, 46, 60)
    ZAPATO = (46, 40, 36)
    ZAPATO_L = (74, 66, 60)

    ROTULO = {
        "reposo": ("Listo", "#5b7a5e"),
        "escuchando": ("Te escucho...", "#b23a3a"),
        "pensando": ("Pensando...", "#8a6a1f"),
        "buscando": ("Trabajando...", "#7a4fa8"),
        "hablando": ("Hablando", "#2c5fa8"),
    }

    # ---- medidas del cuerpo, en coordenadas de 1x
    #
    # Las proporciones se rehicieron mirando el resultado: la primera vez
    # salio una cabeza pequena sobre unas piernas larguisimas, que es el
    # fallo tipico de repartir el alto a ojo. La regla que cuadra es que
    # **las piernas midan mas o menos lo que el torso mas la cabeza**, y que
    # la cabeza no baje de un sexto del total, o la cara se queda sin sitio
    # para tener rasgos.
    CAB_CY, CAB_RX, CAB_RY = 66, 31, 36
    CUELLO_Y = 100
    HOMBRO_Y = 118
    HOMBRO_X = 37
    CADERA_Y = 236
    CADERA_X = 21
    SUELO_Y = 396
    BRAZO, ANTEBRAZO = 46, 44
    MUSLO, PANTORRILLA = 80, 76

    # Donde va cada mano, medido DESDE SU HOMBRO: (afuera, abajo).
    MANOS = {
        "reposo":     ((6, 84), (6, 84)),
        "escuchando": ((6, 84), (16, -46)),      # la derecha, a la oreja
        "pensando":   ((-14, 52), (-24, -26)),   # la derecha, a la barbilla
        "buscando":   ((11, 64), (11, 64)),      # tecleando
        "hablando":   ((19, 58), (19, 58)),
        "saludo":     ((26, -62), (6, 84)),      # la izquierda arriba
    }

    def __init__(self, master):
        super().__init__(master, width=self.AN, height=self.AL,
                         highlightthickness=0, bg="#%02x%02x%02x" % self.FONDO)
        self.estado = "reposo"
        self.boca_obj = 0.0          # lo escribe el hilo de la voz
        self.mic = 0.0               # lo escribe el hilo del microfono

        self._boca = 0.0
        self._mic = 0.0
        self._parpadeo = 0.0
        self._sig_parpadeo = time.time() + random.uniform(1.5, 4.0)
        self._yaw = 0.0              # girar el cuello a los lados
        self._yaw_obj = 0.0
        self._pitch = 0.0            # asentir
        self._pitch_obj = 0.0
        self._sig_mirada = time.time() + random.uniform(1.5, 3.5)
        self._mira = [0.0, 0.0]      # los ojos dentro de las cuencas
        self._mira_obj = [0.0, 0.0]
        self._manos = [list(self.MANOS["reposo"][0]), list(self.MANOS["reposo"][1])]
        self._peso = 0.0             # a que pierna carga el peso
        self._peso_obj = 0.0
        self._sig_peso = time.time() + random.uniform(4, 9)
        self._saludando = 0.0
        self._sig_saludo = time.time() + random.uniform(14, 26)
        self._t = 0.0

        self._foto = None
        self._id_img = self.create_image(0, 0, anchor="nw")
        self._id_txt = self.create_text(self.AN / 2, self.AL - 11, text="",
                                        font=("Segoe UI", 10, "bold"))
        self._tick()

    def set_estado(self, e):
        self.estado = e

    # ================================================================ animacion
    def _tick(self):
        try:
            ahora = time.time()
            self._t += self.MS / 1000.0

            self._boca = _lerp(self._boca, max(0.0, min(1.0, self.boca_obj)), 0.5)
            self._mic = _lerp(self._mic, max(0.0, min(1.0, self.mic)), 0.35)

            # parpadeo
            if self._parpadeo > 0:
                self._parpadeo -= 0.2
                if self._parpadeo <= 0:
                    self._parpadeo = 0.0
                    self._sig_parpadeo = ahora + random.uniform(1.8, 5.5)
            elif ahora >= self._sig_parpadeo:
                self._parpadeo = 1.0

            # de vez en cuando saluda, pero solo si esta parado
            if self._saludando > 0:
                self._saludando -= self.MS / 1000.0
                if self._saludando <= 0:
                    self._saludando = 0.0
                    self._sig_saludo = ahora + random.uniform(20, 40)
            elif self.estado == "reposo" and ahora >= self._sig_saludo:
                self._saludando = 2.4

            # cambiar el peso de pierna, que estar clavado canta mucho
            if ahora >= self._sig_peso:
                self._peso_obj = random.uniform(-1, 1)
                self._sig_peso = ahora + random.uniform(5, 11)
            self._peso = _lerp(self._peso, self._peso_obj, 0.02)

            self._mover_cabeza(ahora)
            self._mover_brazos()

            self._pintar()
        except Exception:
            pass
        self.after(self.MS, self._tick)

    def _mover_cabeza(self, ahora):
        """El cuello gira y los ojos se mueven dentro, cada uno a su ritmo.

        Que los ojos lleguen ANTES que la cabeza es lo que hace que parezca
        que mira algo y luego se gira: primero van los ojos, la cabeza sigue.
        """
        if ahora >= self._sig_mirada:
            if self.estado == "pensando":
                self._yaw_obj = random.uniform(-0.8, 0.8)
                self._pitch_obj = random.uniform(-0.7, -0.2)     # mira arriba
                self._mira_obj = [random.uniform(-1, 1), random.uniform(-1, -0.3)]
                self._sig_mirada = ahora + random.uniform(0.7, 1.6)
            elif self.estado == "buscando":
                self._yaw_obj = -self._yaw_obj or 0.5
                self._pitch_obj = 0.35                            # mira al teclado
                self._mira_obj = [self._yaw_obj, 0.5]
                self._sig_mirada = ahora + random.uniform(0.4, 0.8)
            elif self.estado == "escuchando":
                self._yaw_obj = random.uniform(-0.15, 0.15)
                self._pitch_obj = -0.1
                self._mira_obj = [random.uniform(-0.2, 0.2), 0.0]
                self._sig_mirada = ahora + random.uniform(1.2, 2.4)
            elif self.estado == "hablando":
                self._yaw_obj = random.uniform(-0.35, 0.35)
                self._pitch_obj = random.uniform(-0.15, 0.15)
                self._mira_obj = [self._yaw_obj * 0.6, 0.0]
                self._sig_mirada = ahora + random.uniform(1.0, 2.2)
            else:
                self._yaw_obj = random.uniform(-0.7, 0.7)
                self._pitch_obj = random.uniform(-0.25, 0.25)
                self._mira_obj = [random.uniform(-0.9, 0.9), random.uniform(-0.5, 0.5)]
                self._sig_mirada = ahora + random.uniform(1.6, 3.8)
        self._yaw = _lerp(self._yaw, self._yaw_obj, 0.055)         # el cuello, lento
        self._pitch = _lerp(self._pitch, self._pitch_obj, 0.06)
        self._mira[0] = _lerp(self._mira[0], self._mira_obj[0], 0.2)   # los ojos, rapidos
        self._mira[1] = _lerp(self._mira[1], self._mira_obj[1], 0.2)

    def _mover_brazos(self):
        pose = "saludo" if self._saludando > 0 else self.estado
        base = self.MANOS.get(pose, self.MANOS["reposo"])
        objetivo = [list(base[0]), list(base[1])]
        t = self._t

        if pose == "saludo":
            objetivo[0][0] += math.sin(t * 9.0) * 14
            objetivo[0][1] += math.cos(t * 9.0) * 6
        elif pose == "hablando":
            g = 0.35 + self._boca * 1.5
            for i, desfase in ((0, 0.0), (1, 2.6)):
                objetivo[i][0] += math.sin(t * 2.4 + desfase) * 14 * g
                objetivo[i][1] += math.sin(t * 3.1 + desfase) * 18 * g
        elif pose == "buscando":
            objetivo[0][1] += math.sin(t * 7.5) * 7
            objetivo[1][1] += math.sin(t * 7.5 + 1.7) * 7
        elif pose == "escuchando":
            objetivo[1][1] += math.sin(t * 1.6) * 2
        elif pose == "pensando":
            objetivo[1][1] += math.sin(t * 1.2) * 2
        else:
            for i in (0, 1):
                objetivo[i][0] += math.sin(t * 1.1 + i * 0.4) * 3
                objetivo[i][1] += math.sin(t * 1.5) * 2.5

        rapidez = 0.32 if pose == "saludo" else 0.14
        for i in (0, 1):
            for j in (0, 1):
                self._manos[i][j] = _lerp(self._manos[i][j], objetivo[i][j], rapidez)

    # ================================================================ utilidades
    @staticmethod
    def _angulos_hacia(dx, dy, l1, l2, codo=1):
        """Cinematica inversa de dos huesos: donde quiero la mano -> angulos.

        Si el sitio queda mas lejos de lo que da el brazo, se estira todo lo
        que puede en esa direccion; si queda demasiado cerca, se dobla al
        maximo. Nunca se rompe.
        """
        d = math.hypot(dx, dy)
        d = max(abs(l1 - l2) + 0.5, min(l1 + l2 - 0.5, d))
        base = math.degrees(math.atan2(dx, dy))
        cos_a = (d * d + l1 * l1 - l2 * l2) / (2.0 * d * l1)
        alfa = math.degrees(math.acos(max(-1.0, min(1.0, cos_a))))
        cos_b = (l1 * l1 + l2 * l2 - d * d) / (2.0 * l1 * l2)
        beta = math.degrees(math.acos(max(-1.0, min(1.0, cos_b))))
        return base + alfa * codo, -(180.0 - beta) * codo

    @staticmethod
    def _punta(x, y, ang, largo, s):
        r = math.radians(ang)
        return x + s * largo * math.sin(r), y + largo * math.cos(r)

    def _capsula(self, d, x0, y0, x1, y1, w0, w1, color, luz=None, sombra=None):
        """Un hueso: tronco que se estrecha, puntas redondas, luz y sombra.

        Las tres pasadas (cuerpo, franja de luz, borde oscuro) son lo que
        hace que un brazo parezca redondo y no un palo.
        """
        S = self.SS
        ang = math.atan2(y1 - y0, x1 - x0)
        nx, ny = -math.sin(ang), math.cos(ang)
        p = [(x0 + nx * w0, y0 + ny * w0), (x1 + nx * w1, y1 + ny * w1),
             (x1 - nx * w1, y1 - ny * w1), (x0 - nx * w0, y0 - ny * w0)]
        d.polygon([(px * S, py * S) for px, py in p], fill=color)
        d.ellipse([(x0 - w0) * S, (y0 - w0) * S, (x0 + w0) * S, (y0 + w0) * S],
                  fill=color)
        d.ellipse([(x1 - w1) * S, (y1 - w1) * S, (x1 + w1) * S, (y1 + w1) * S],
                  fill=color)
        if sombra:
            q = [(x0 + nx * w0, y0 + ny * w0), (x1 + nx * w1, y1 + ny * w1),
                 (x1 + nx * w1 * 0.45, y1 + ny * w1 * 0.45),
                 (x0 + nx * w0 * 0.45, y0 + ny * w0 * 0.45)]
            d.polygon([(px * S, py * S) for px, py in q], fill=sombra)
        if luz:
            q = [(x0 - nx * w0 * 0.72, y0 - ny * w0 * 0.72),
                 (x1 - nx * w1 * 0.72, y1 - ny * w1 * 0.72),
                 (x1 - nx * w1 * 0.2, y1 - ny * w1 * 0.2),
                 (x0 - nx * w0 * 0.2, y0 - ny * w0 * 0.2)]
            d.polygon([(px * S, py * S) for px, py in q], fill=luz)

    def _elipse(self, d, cx, cy, rx, ry, **kw):
        S = self.SS
        d.ellipse([(cx - rx) * S, (cy - ry) * S, (cx + rx) * S, (cy + ry) * S], **kw)

    def _poli(self, d, puntos, **kw):
        S = self.SS
        d.polygon([(x * S, y * S) for x, y in puntos], **kw)

    def _linea(self, d, puntos, ancho=1, **kw):
        S = self.SS
        d.line([(x * S, y * S) for x, y in puntos], width=max(1, int(ancho * S)),
               joint="curve", **kw)

    # ================================================================ pintar
    def _pintar(self):
        S = self.SS
        img = Image.new("RGB", (self.AN * S, self.AL * S), self.FONDO)
        d = ImageDraw.Draw(img)
        t = self._t

        # ---- ritmos del cuerpo
        respira = math.sin(t * 1.35)
        balanceo = math.sin(t * 0.7) * 1.6 + self._peso * 2.2
        if self.estado == "hablando":
            balanceo += math.sin(t * 2.3) * 1.6 + self._boca * 1.2
        elif self.estado == "escuchando":
            balanceo -= 2.0
        elif self.estado == "buscando":
            balanceo += math.sin(t * 3.4) * 0.9

        cx = self.AN / 2.0 + balanceo
        hombro_y = self.HOMBRO_Y - respira * 1.1          # respirar sube los hombros
        cadera_y = self.CADERA_Y
        pecho = 1.0 + respira * 0.035                     # y ensancha el pecho

        # la cabeza cuelga del cuello, y el cuello del balanceo
        yaw, pitch = self._yaw, self._pitch
        cab_cx = cx + yaw * 4.0
        cab_cy = self.CAB_CY + pitch * 3.0 + respira * 0.6

        # ---- 1. sombra en el suelo (difuminada en pequeno, que es lo barato)
        self._sombra_suelo(img, cx)

        # ---- 2. piernas (la de detras primero)
        self._piernas(d, cx, cadera_y)

        # ---- 3. brazo de detras
        self._brazo(d, cx - self.HOMBRO_X * pecho, hombro_y + 4,
                    self._manos[0][0], self._manos[0][1], -1, atras=True)

        # ---- 4. cuello ANTES del torso: asi la camisa lo tapa por abajo y
        # parece que sale de dentro, no que esta pegado encima. Pintarlo
        # despues dejaba una banda de piel cruzando el pecho.
        self._cuello(d, cx, cab_cx, cab_cy, hombro_y)

        # ---- 5. torso
        self._torso(d, cx, hombro_y, cadera_y, pecho)

        # ---- 5. brazo de delante
        self._brazo(d, cx + self.HOMBRO_X * pecho, hombro_y + 4,
                    self._manos[1][0], self._manos[1][1], 1, atras=False)

        # ---- 6. cabeza
        self._cabeza(d, img, cab_cx, cab_cy, yaw, pitch)

        # ---- 7. adornos del estado
        if self.estado == "escuchando":
            self._aro_microfono(d, cab_cx, cab_cy)
        elif self.estado == "pensando":
            self._burbujas(d, cab_cx, cab_cy, t)

        # ---- a la pantalla
        chico = img.resize((self.AN, self.AL), Image.LANCZOS)
        if self._foto is None:
            self._foto = ImageTk.PhotoImage(chico)
            self.itemconfigure(self._id_img, image=self._foto)
        else:
            self._foto.paste(chico)       # reusar es mucho mas rapido que recrear
        txt, col = self.ROTULO.get(self.estado, ("", "#666"))
        self.itemconfigure(self._id_txt, text=txt, fill=col)

    # ---------------------------------------------------------------- piezas
    def _sombra_suelo(self, img, cx):
        S = self.SS
        capa = Image.new("L", (self.AN // 2, self.AL // 2), 0)
        ImageDraw.Draw(capa).ellipse(
            [(cx - 46) / 2, (self.SUELO_Y - 7) / 2, (cx + 46) / 2, (self.SUELO_Y + 7) / 2],
            fill=150)
        capa = capa.filter(ImageFilter.GaussianBlur(3)).resize(
            (self.AN * S, self.AL * S))
        img.paste(self.SUELO, (0, 0), capa)

    def _piernas(self, d, cx, cadera_y):
        for s in (-1, 1):
            atras = (s * self._peso) < 0            # la que no carga, un poco atras
            cargada = not atras
            cadera_x = cx + s * self.CADERA_X
            # la rodilla se abre un poco hacia afuera y la pierna floja se dobla
            abre = 3 if cargada else 7
            flex = 0 if cargada else 5
            if self.estado == "buscando":
                flex += abs(math.sin(self._t * 3.4 + (0 if s < 0 else 3.1))) * 3
            rod_x = cadera_x + s * abre
            rod_y = cadera_y + self.MUSLO * 0.98
            tob_x = cadera_x + s * (abre * 0.4) + s * flex * 0.4
            tob_y = self.SUELO_Y - 8 + flex * 0.5

            col = self.PANTALON if cargada else _mez(self.PANTALON, (0, 0, 0), 0.12)
            luz = self.PANTALON_L if cargada else None
            self._capsula(d, cadera_x, cadera_y - 6, rod_x, rod_y, 16, 10.5,
                          col, luz=luz, sombra=self.PANTALON_S)
            self._capsula(d, rod_x, rod_y, tob_x, tob_y, 10.5, 7,
                          col, luz=luz, sombra=self.PANTALON_S)
            # zapato
            pie = self.ZAPATO if cargada else _mez(self.ZAPATO, (0, 0, 0), 0.15)
            self._poli(d, [(tob_x - s * 6, tob_y - 3), (tob_x + s * 5, tob_y - 4),
                           (tob_x + s * 13, tob_y + 5), (tob_x + s * 13, tob_y + 9),
                           (tob_x - s * 7, tob_y + 9)], fill=pie)
            self._elipse(d, tob_x + s * 2, tob_y + 4, 8, 5.5, fill=pie)
            if cargada:
                self._linea(d, [(tob_x - s * 5, tob_y + 1), (tob_x + s * 9, tob_y + 2)],
                            ancho=1.2, fill=self.ZAPATO_L)

    def _torso(self, d, cx, hombro_y, cadera_y, pecho):
        an_h = (self.HOMBRO_X + 4) * pecho          # ancho de hombros
        an_c = 26 * pecho                           # ancho de cintura
        an_p = 28                                   # ancho de cadera
        # cuerpo de la camisa
        self._poli(d, [
            (cx - an_h, hombro_y + 8), (cx - an_h + 3, hombro_y - 4),
            (cx - 15, hombro_y - 10), (cx, hombro_y - 12), (cx + 15, hombro_y - 10),
            (cx + an_h - 3, hombro_y - 4), (cx + an_h, hombro_y + 8),
            (cx + an_c, hombro_y + 62), (cx + an_p, cadera_y),
            (cx - an_p, cadera_y), (cx - an_c, hombro_y + 62),
        ], fill=self.CAMISA)
        # hombros redondeados
        for s in (-1, 1):
            self._elipse(d, cx + s * (an_h - 7), hombro_y + 2, 10, 11,
                         fill=self.CAMISA)
        # luz por la izquierda y sombra por la derecha: da bulto al pecho
        self._poli(d, [(cx - an_h + 4, hombro_y + 6), (cx - 12, hombro_y - 6),
                       (cx - 10, cadera_y - 6), (cx - an_c + 2, hombro_y + 60)],
                   fill=self.CAMISA_L)
        self._poli(d, [(cx + an_h - 4, hombro_y + 6), (cx + 14, hombro_y - 4),
                       (cx + 12, cadera_y - 6), (cx + an_c - 1, hombro_y + 60)],
                   fill=self.CAMISA_S)
        # el cuello de la camisa, en pico
        self._poli(d, [(cx - 15, hombro_y - 11), (cx, hombro_y + 16),
                       (cx + 15, hombro_y - 11), (cx + 8, hombro_y - 13),
                       (cx, hombro_y - 6), (cx - 8, hombro_y - 13)],
                   fill=self.CUELLO_C)
        # dos pliegues, que la ropa lisa canta
        self._linea(d, [(cx - 8, hombro_y + 40), (cx - 2, hombro_y + 58),
                        (cx - 6, cadera_y - 12)], ancho=1, fill=self.CAMISA_S)
        self._linea(d, [(cx + 10, hombro_y + 34), (cx + 6, hombro_y + 56)],
                    ancho=1, fill=self.CAMISA_S)
        # cinturon
        self._poli(d, [(cx - an_p, cadera_y - 9), (cx + an_p, cadera_y - 9),
                       (cx + an_p, cadera_y + 1), (cx - an_p, cadera_y + 1)],
                   fill=self.PANTALON_S)
        self._poli(d, [(cx - 4, cadera_y - 8), (cx + 4, cadera_y - 8),
                       (cx + 4, cadera_y), (cx - 4, cadera_y)],
                   fill=(150, 140, 120))

    def _brazo(self, d, hx, hy, dx, dy, s, atras):
        a1, a2 = self._angulos_hacia(dx, dy, self.BRAZO, self.ANTEBRAZO)
        codo_x, codo_y = self._punta(hx, hy, a1, self.BRAZO, s)
        mano_x, mano_y = self._punta(codo_x, codo_y, a1 + a2, self.ANTEBRAZO, s)

        if atras:
            manga = _mez(self.CAMISA, (0, 0, 0), 0.18)
            manga_l = None
            piel = _mez(self.PIEL, (0, 0, 0), 0.14)
            piel_s = _mez(self.PIEL_S, (0, 0, 0), 0.14)
        else:
            manga, manga_l = self.CAMISA, self.CAMISA_L
            piel, piel_s = self.PIEL, self.PIEL_S

        # el brazo: manga hasta medio antebrazo, luego piel
        self._capsula(d, hx, hy, codo_x, codo_y, 11, 8, manga,
                      luz=manga_l, sombra=self.CAMISA_S)
        mitad_x = codo_x + (mano_x - codo_x) * 0.35
        mitad_y = codo_y + (mano_y - codo_y) * 0.35
        self._capsula(d, codo_x, codo_y, mitad_x, mitad_y, 8, 7, manga,
                      luz=manga_l, sombra=self.CAMISA_S)
        self._capsula(d, mitad_x, mitad_y, mano_x, mano_y, 6.5, 5, piel,
                      luz=None if atras else self.PIEL_L, sombra=piel_s)
        self._mano(d, mano_x, mano_y, a1 + a2, s, piel, piel_s, atras)

    def _mano(self, d, x, y, ang, s, piel, piel_s, atras):
        """Una mano de verdad: palma y dedos marcados, no un circulo."""
        r = math.radians(ang)
        ux, uy = s * math.sin(r), math.cos(r)          # hacia donde apunta
        px, py = -uy * s, ux * s                       # perpendicular
        self._elipse(d, x + ux * 2, y + uy * 2, 6.2, 6.8, fill=piel)
        # los dedos: cuatro capsulitas juntas
        for i in range(4):
            off = (i - 1.5) * 2.6
            bx = x + ux * 3 + px * off
            by = y + uy * 3 + py * off
            largo = 6.5 - abs(i - 1.2) * 0.7
            self._capsula(d, bx, by, bx + ux * largo, by + uy * largo, 1.7, 1.4,
                          piel, sombra=None if atras else piel_s)
        # el pulgar, cruzado
        self._capsula(d, x - px * s * 4.4, y - py * s * 4.4,
                      x - px * s * 6.2 + ux * 3.4, y - py * s * 6.2 + uy * 3.4,
                      2.1, 1.7, piel, sombra=None if atras else piel_s)

    def _cuello(self, d, cx, cab_cx, cab_cy, hombro_y):
        base_x = cx + (cab_cx - cx) * 0.35
        self._capsula(d, cab_cx, cab_cy + self.CAB_RY - 11, base_x, hombro_y + 4,
                      13, 15, self.PIEL_S, sombra=self.PIEL_SS)
        # la sombra que echa la barbilla sobre el cuello
        self._elipse(d, cab_cx, cab_cy + self.CAB_RY - 2, 9, 4,
                     fill=self.PIEL_SS)

    # ---------------------------------------------------------------- la cara
    def _cabeza(self, d, img, cx, cy, yaw, pitch):
        """La cabeza, con el giro del cuello resuelto rasgo a rasgo.

        `desp` mueve la cara entera hacia donde mira y `comp` la estrecha:
        juntas fingen la perspectiva. La oreja del lado al que gira se
        esconde, y la nariz asoma por el perfil.
        """
        rx, ry = self.CAB_RX, self.CAB_RY
        # Mas alla de 0,75 la cara se descuadra: los rasgos se salen del
        # craneo y el pelo no acompana. Se limita ahi, que ademas es giro de
        # sobra para lo que hace falta.
        yaw = max(-0.75, min(0.75, yaw))
        desp = yaw * rx * 0.42
        comp = math.cos(yaw * 0.95)
        baja = pitch * 5.0

        # ---- orejas (la del lado hacia el que gira se va tapando)
        for s in (-1, 1):
            visible = 1.0 - max(0.0, s * yaw) * 1.5
            if visible <= 0.05:
                continue
            ex = cx + s * (rx - 1) + desp * 0.5
            ey = cy + 4 + baja * 0.5
            an = 5.0 * min(1.0, visible)
            self._elipse(d, ex, ey, an, 7.5, fill=self.PIEL_S)
            self._elipse(d, ex - s * 0.6, ey, an * 0.55, 5.0, fill=self.PIEL_SS)

        # ---- craneo y cara
        # La mandibula sale del craneo hacia abajo estrechandose, pero SIN
        # alargarse: la primera version tenia un menton larguisimo porque la
        # cara llegaba hasta cy+ry. Ahora la barbilla queda en cy+ry*0.92 y
        # los pomulos marcan el ancho a media altura.
        fx = cx + desp * 0.35
        self._poli(d, [
            (fx - rx * comp, cy - 8), (fx - rx * 0.97 * comp, cy + 6),
            (fx - rx * 0.86 * comp + desp * 0.2, cy + ry * 0.46),
            (fx - rx * 0.6 * comp + desp * 0.45, cy + ry * 0.76),
            (fx - rx * 0.28 * comp + desp * 0.6, cy + ry * 0.9),
            (fx + desp * 0.65, cy + ry * 0.93),
            (fx + rx * 0.28 * comp + desp * 0.6, cy + ry * 0.9),
            (fx + rx * 0.6 * comp + desp * 0.45, cy + ry * 0.76),
            (fx + rx * 0.86 * comp + desp * 0.2, cy + ry * 0.46),
            (fx + rx * 0.97 * comp, cy + 6), (fx + rx * comp, cy - 8),
        ], fill=self.PIEL)
        self._elipse(d, fx, cy - 6, rx * comp, ry * 0.8, fill=self.PIEL)

        # ---- volumen de la cara: luz a un lado, sombra al otro
        self._sombra_cara(img, cx + desp * 0.35, cy, rx * comp, ry, yaw)

        # ---- pelo rubio, SOLO por arriba, con las sienes despejadas
        self._pelo(d, cx, cy, rx, ry, desp, comp)

        # ---- cejas, ojos, nariz y boca, repartidos como en una cara de verdad:
        # los ojos a media altura, la nariz a tres cuartos, la boca entre la
        # nariz y la barbilla.
        for s in (-1, 1):
            self._ceja(d, cx + desp + s * 12 * comp, cy - 13 + baja, s, comp)
        for s in (-1, 1):
            self._ojo(d, cx + desp + s * 12 * comp, cy - 2 + baja, s, comp)
        self._nariz(d, cx + desp, cy + 9 + baja, yaw, comp)
        self._boca_dibujo(d, cx + desp * 1.05, cy + 22 + baja * 1.1, comp)

        # ---- barbilla marcada
        self._elipse(d, cx + desp * 0.9, cy + ry * 0.78 + baja, 5.5 * comp, 2.6,
                     fill=_mez(self.PIEL, self.PIEL_L, 0.5))

    def _sombra_cara(self, img, cx, cy, rx, ry, yaw):
        """Medio tono en un lado de la cara y bajo los pomulos.

        Es lo que quita la sensacion de pegatina. Va difuminado y en pequeno,
        que es lo que lo hace barato.
        """
        S = self.SS
        capa = Image.new("L", (self.AN // 2, self.AL // 2), 0)
        cd = ImageDraw.Draw(capa)
        lado = 1 if yaw >= 0 else -1
        # medio tono en el lado contrario a la luz, pegado al borde
        cd.ellipse([(cx + lado * rx * 0.55 - rx * 0.85) / 2, (cy - ry * 0.6) / 2,
                    (cx + lado * rx * 0.55 + rx * 0.85) / 2, (cy + ry * 0.8) / 2],
                   fill=52)
        # y otra pizca bajo los pomulos
        cd.ellipse([(cx - rx * 0.62) / 2, (cy + ry * 0.3) / 2,
                    (cx + rx * 0.62) / 2, (cy + ry * 0.72) / 2], fill=30)
        capa = capa.filter(ImageFilter.GaussianBlur(3.5)).resize(
            (self.AN * S, self.AL * S))
        img.paste(self.PIEL_S, (0, 0), capa)

    def _pelo(self, d, cx, cy, rx, ry, desp, comp):
        """Rubio y solo por arriba: se ve piel en las sienes, como pidio."""
        # El pelo tiene que ENVOLVER el craneo, no posarse encima como una
        # gorra: baja por los lados hasta la altura de la oreja, pero deja las
        # sienes y las entradas al aire, que es como lo pidio Angel.
        pa = (rx - 1.5) * comp
        py = cy - ry + 15
        self._poli(d, [
            (cx - pa + desp * 0.35, py + 22),                 # patilla izquierda
            (cx - pa * 1.0 + desp * 0.35, py + 4),
            (cx - pa * 0.82 + desp * 0.5, py - 9),
            (cx - pa * 0.4 + desp * 0.7, py - 15),
            (cx + desp * 0.85, py - 16.5),
            (cx + pa * 0.4 + desp * 0.7, py - 15),
            (cx + pa * 0.82 + desp * 0.5, py - 9),
            (cx + pa * 1.0 + desp * 0.35, py + 4),
            (cx + pa + desp * 0.35, py + 22),                 # patilla derecha
            (cx + pa * 0.86 + desp * 0.4, py + 11),           # entrada derecha
            (cx + pa * 0.5 + desp * 0.6, py + 1),
            (cx + desp * 0.75, py - 2),
            (cx - pa * 0.5 + desp * 0.6, py + 1),
            (cx - pa * 0.86 + desp * 0.4, py + 11),           # entrada izquierda
        ], fill=self.PELO)
        # brillo ancho arriba, que es donde da la luz
        self._poli(d, [
            (cx - pa * 0.78 + desp * 0.45, py - 4), (cx - pa * 0.42 + desp * 0.65, py - 13),
            (cx + pa * 0.06 + desp * 0.8, py - 14.5),
            (cx - pa * 0.3 + desp * 0.6, py - 3),
        ], fill=self.PELO_L)
        # mechones: van con el pelo, del remolino hacia los lados
        for i, (a, b) in enumerate(((-0.8, -0.45), (-0.4, 0.0), (0.15, 0.55),
                                    (0.6, 0.88))):
            self._linea(d, [(cx + pa * a + desp * 0.45, py + 6),
                            (cx + pa * (a + b) * 0.5 + desp * 0.6, py - 7),
                            (cx + pa * b + desp * 0.75, py - 14)],
                        ancho=1.1, fill=self.PELO_S if i % 2 else self.PELO_L)
        # sombra del pelo sobre la frente
        self._linea(d, [(cx - pa * 0.86 + desp * 0.4, py + 10),
                        (cx - pa * 0.5 + desp * 0.6, py + 0.5),
                        (cx + desp * 0.75, py - 2.5),
                        (cx + pa * 0.5 + desp * 0.6, py + 0.5),
                        (cx + pa * 0.86 + desp * 0.4, py + 10)],
                    ancho=1.4, fill=self.PELO_S)

    def _ceja(self, d, x, y, s, comp):
        e = self.estado
        if e == "pensando":
            dy_i, dy_e, grosor = (-3.5, 1.5, 2.6) if s < 0 else (1.5, 0.5, 2.2)
        elif e == "buscando":
            dy_i, dy_e, grosor = 2.0, -1.0, 2.2
        elif e == "escuchando":
            dy_i, dy_e, grosor = -2.5, -2.0, 2.4
        elif e == "hablando":
            sube = -self._boca * 2.6
            dy_i, dy_e, grosor = sube, sube - 0.5, 2.3
        else:
            dy_i, dy_e, grosor = 0.0, 0.5, 2.3
        xi, xe = x + s * -6 * comp, x + s * 6.5 * comp
        self._capsula(d, xi, y + dy_i, xe, y + dy_e, grosor, grosor * 0.55,
                      self.CEJA, sombra=self.PELO_S)

    def _ojo(self, d, x, y, s, comp):
        an, al = 7.0 * comp, 4.3
        # cuenca: una sombra suave alrededor
        self._elipse(d, x, y, an + 1.6, al + 1.8, fill=self.PIEL_S)
        # blanco
        self._elipse(d, x, y, an, al, fill=self.OJO_B)
        # iris
        ix = x + self._mira[0] * an * 0.34
        iy = y + self._mira[1] * al * 0.3
        r = 3.5
        self._elipse(d, ix, iy, r * comp, r, fill=self.IRIS)
        self._elipse(d, ix, iy, r * comp, r, outline=self.IRIS_S,
                     width=max(1, int(1.1 * self.SS)))
        self._elipse(d, ix, iy - r * 0.28, r * 0.72 * comp, r * 0.6, fill=self.IRIS_L)
        self._elipse(d, ix, iy, r * 0.44 * comp, r * 0.44, fill=self.PUPILA)
        self._elipse(d, ix - r * 0.38 * comp, iy - r * 0.4, r * 0.26, r * 0.26,
                     fill=(255, 255, 255))
        # sombra del parpado por arriba
        self._poli(d, [(x - an, y - al), (x + an, y - al),
                       (x + an, y - al * 0.35), (x - an, y - al * 0.2)],
                   fill=_mez(self.OJO_B, self.PIEL_SS, 0.35))
        # parpado de verdad al parpadear
        if self._parpadeo > 0.02:
            h = (al * 2 + 2.5) * self._parpadeo
            self._poli(d, [(x - an - 1, y - al - 1.5), (x + an + 1, y - al - 1.5),
                           (x + an + 1, y - al - 1.5 + h), (x - an - 1, y - al - 1.5 + h)],
                       fill=self.PIEL)
            self._linea(d, [(x - an, y - al - 1.5 + h), (x + an, y - al - 1.5 + h)],
                        ancho=1.1, fill=self.PIEL_SS)
        else:
            # pestanas: una linea fina arriba
            self._linea(d, [(x - an, y - al * 0.75), (x, y - al * 1.05),
                            (x + an, y - al * 0.7)], ancho=1.3, fill=(96, 74, 52))
        # parpado de abajo
        self._linea(d, [(x - an * 0.85, y + al * 0.92), (x, y + al * 1.1),
                        (x + an * 0.85, y + al * 0.88)], ancho=1, fill=self.PIEL_S)

    def _nariz(self, d, x, y, yaw, comp):
        lado = 1 if yaw >= 0 else -1
        # el caballete, con su luz
        self._capsula(d, x - yaw * 1.2, y - 7, x + yaw * 1.5, y + 4, 2.2, 3.2,
                      _mez(self.PIEL, self.PIEL_L, 0.5))
        # la punta
        self._elipse(d, x + yaw * 2.0, y + 5, 3.4 * comp + abs(yaw) * 1.2, 2.9,
                     fill=_mez(self.PIEL, self.PIEL_L, 0.35))
        # sombra debajo y aletas
        self._elipse(d, x + yaw * 2.0, y + 7.2, 3.6 * comp + abs(yaw), 1.5,
                     fill=self.PIEL_S)
        for s in (-1, 1):
            vis = 1.0 - max(0.0, s * yaw * 0.9)
            if vis < 0.25:
                continue
            self._elipse(d, x + yaw * 2.0 + s * 2.4 * comp, y + 6.4, 1.0 * vis, 0.8,
                         fill=self.PIEL_SS)
        # si gira mucho, el perfil de la nariz asoma por el borde
        if abs(yaw) > 0.3:
            self._poli(d, [(x + lado * 3 * comp, y - 2), (x + lado * (5 + abs(yaw) * 4), y + 4),
                           (x + lado * 3 * comp, y + 6)],
                       fill=_mez(self.PIEL, self.PIEL_L, 0.3))

    def _boca_dibujo(self, d, x, y, comp):
        a = self._boca
        if a < 0.06:
            if self.estado == "pensando":
                # boca torcida de estar dandole vueltas
                self._linea(d, [(x - 6 * comp, y + 0.5), (x, y - 0.5),
                                (x + 6 * comp, y - 1.5)], ancho=1.6, fill=self.LABIO_S)
            else:
                # sonrisa cerrada
                self._linea(d, [(x - 6.5 * comp, y - 1), (x, y + 1.8),
                                (x + 6.5 * comp, y - 1)], ancho=1.6, fill=self.LABIO_S)
                self._linea(d, [(x - 5 * comp, y + 2.4), (x, y + 3.4),
                                (x + 5 * comp, y + 2.4)], ancho=1, fill=self.PIEL_S)
            # labio de arriba insinuado
            self._linea(d, [(x - 4 * comp, y - 2.2), (x, y - 1.4), (x + 4 * comp, y - 2.2)],
                        ancho=1, fill=self.LABIO)
            return
        # boca abierta hablando
        an = (5.2 + a * 2.6) * comp
        al = 1.5 + a * 4.6
        self._elipse(d, x, y, an + 1.2, al + 1.2, fill=self.LABIO)
        self._elipse(d, x, y, an, al, fill=self.BOCA_D)
        # dientes de arriba
        self._poli(d, [(x - an * 0.82, y - al + 0.3), (x + an * 0.82, y - al + 0.3),
                       (x + an * 0.7, y - al + 1.8), (x - an * 0.7, y - al + 1.8)],
                   fill=self.DIENTE)
        if a > 0.45:
            # lengua al fondo
            self._elipse(d, x, y + al * 0.45, an * 0.55, al * 0.32,
                         fill=(178, 96, 96))
        # labio de abajo con su luz
        self._linea(d, [(x - an, y + al * 0.9), (x, y + al + 1.4), (x + an, y + al * 0.9)],
                    ancho=1.4, fill=self.LABIO_S)

    # ---------------------------------------------------------------- adornos
    def _aro_microfono(self, d, cx, cy):
        for r0, col, gr in ((58, (127, 176, 255), 2.2), (58, (185, 211, 255), 1.4)):
            r = r0 + self._mic * (26 if gr > 2 else 12)
            self._elipse(d, cx, cy + 18, r, r, outline=col,
                         width=max(1, int(gr * self.SS)))

    def _burbujas(self, d, cx, cy, t):
        for i in range(3):
            f = (math.sin(t * 3.6 - i * 0.9) + 1) / 2.0
            rr = 2.6 + f * 2.4
            bx = cx + 30 + i * 12
            by = cy - 26 - i * 9
            self._elipse(d, bx, by, rr, rr, fill=(196, 180, 131))
