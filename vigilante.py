# -*- coding: utf-8 -*-
r"""
Berna pendiente de lo que hace Angel, sin que se lo tenga que pedir.

Angel lo pidio el 2026-08-27: "que desde que lo enciendo siempre este
monitoreando la pantalla, siempre este pendiente de lo que estoy haciendo,
hasta que yo lo apague". El motivo que dio es el de siempre: el no puede estar
pendiente de todo.

LA DECISION QUE LO ORDENA TODO
  Vigilar de verdad la pantalla querria decir mandarle a Google una foto de la
  pantalla cada pocos segundos. Eso son dos problemas: **su correo, sus
  cuentas y sus documentos saliendo del ordenador todo el dia**, y **la cuota**
  (unas 1.000 peticiones diarias que ademas comparte con Mantella; una foto
  cada 10 segundos son 8.600). Asi que:

  - **Lo que se vigila SIEMPRE es local y gratis**: que ventana tiene delante,
    de que programa, cuanto lleva en ella, y si le ha saltado algo con pinta de
    error. Eso se lo pregunta a Windows, es instantaneo y NO SALE NADA del
    ordenador.
  - **La foto a Google solo se hace cuando hay motivo** (lleva mucho rato
    atascado, o le ha saltado un error), con tope por hora, y NUNCA si delante
    hay un banco, un pago, un gestor de contrasenas o una pantalla de entrar
    en una cuenta.

  Angel eligio esto sabiendo la alternativa, y eligio tambien que Berna le
  HABLE el solo cuando lo vea atascado.

LO QUE NO HACE, Y ES A PROPOSITO
  No graba la pantalla, no guarda fotos por su cuenta, no lee lo que escribe y
  no apunta contenido: solo titulos de ventana y tiempos, y en memoria. El
  diario se pierde al cerrar. Nada de esto se manda a ningun sitio salvo la
  foto puntual de la que se habla arriba.
"""
import os, re, json, time, ctypes, threading, unicodedata, collections

BASE = os.path.dirname(os.path.abspath(__file__))
u32 = ctypes.windll.user32

# Cada cuanto mira que ventana hay delante. Es una llamada a Windows, no
# cuesta nada; 2 segundos da precision de sobra sin notarse.
LATIDO = 2.0

# Cuanto tiene que llevar en la MISMA ventana para pensar que esta atascado.
ATASCO_MINUTOS = 8

# Topes para no ponerse pesado ni gastarle la cuota de Google.
MAX_MIRADAS_POR_HORA = 4
MINUTOS_ENTRE_AVISOS = 10

# Titulos que huelen a que algo ha salido mal.
ERRORES = ("error", "ha dejado de funcionar", "no responde", "no se puede",
           "no se ha podido", "fallo", "excepcion", "failed", "exception",
           "advertencia", "problema", "ha ocurrido", "denegado", "denied")

# Ventanas donde NO se hace foto jamas. Se leen de manos.py para no tener dos
# listas que se desincronicen: alli ya estan los bancos, los pagos, los
# gestores de contrasenas y las pantallas de iniciar sesion.
def _lista_sensible():
    try:
        import manos
        return list(manos.INTOCABLES)
    except Exception:
        return [("banco", "el banco"), ("paypal", "una pasarela de pago"),
                ("iniciar sesion", "una pantalla de inicio de sesion")]


# Programas que no cuentan como "estar trabajando en algo": si esta en el
# escritorio o en el propio Berna, no hay nada que vigilar.
IGNORAR = ("berna", "program manager", "")


def _sin_tildes(t):
    t = unicodedata.normalize("NFD", str(t or ""))
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower()


def _ventana_de_delante():
    """(titulo, programa) de lo que hay en primer plano. Todo local."""
    try:
        h = u32.GetForegroundWindow()
        if not h:
            return "", ""
        n = u32.GetWindowTextLengthW(h)
        buf = ctypes.create_unicode_buffer(n + 1)
        u32.GetWindowTextW(h, buf, n + 1)
        titulo = buf.value or ""
    except Exception:
        return "", ""
    programa = ""
    try:
        import psutil
        pid = ctypes.c_ulong()
        u32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        programa = psutil.Process(pid.value).name()
    except Exception:
        pass
    return titulo, programa


class Vigilante(object):
    """Lleva la cuenta de lo que hace Angel y avisa cuando conviene.

    Vive en su propio hilo. La ventana solo tiene que llamar a `arrancar()` y
    luego ir recogiendo con `hay_algo_que_decir()`.
    """

    def __init__(self, config):
        self._config = config          # funcion que devuelve el config al dia
        self.diario = collections.deque(maxlen=400)
        self.actual = None             # {titulo, programa, desde}
        self.avisos = collections.deque()
        self.miradas = collections.deque()      # cuando se hizo cada foto
        self.ultimo_aviso = 0.0
        self.ya_avisado = set()        # para no repetir el mismo atasco
        self.vivo = False

    # ---------------------------------------------------------- el bucle
    def arrancar(self):
        if self.vivo:
            return
        self.vivo = True
        threading.Thread(target=self._bucle, daemon=True).start()

    def encendido(self):
        try:
            return bool(self._config().get("vigilar_pantalla", False))
        except Exception:
            return False

    def _bucle(self):
        while True:
            try:
                if self.encendido():
                    self._latido()
                else:
                    self.actual = None
            except Exception:
                pass
            time.sleep(LATIDO)

    def _latido(self):
        titulo, programa = _ventana_de_delante()
        if _sin_tildes(programa).replace(".exe", "") in IGNORAR or not titulo:
            return
        ahora = time.time()

        if self.actual is None or self.actual["titulo"] != titulo:
            if self.actual is not None:
                self.actual["hasta"] = ahora
                self.diario.append(dict(self.actual))
            self.actual = {"titulo": titulo, "programa": programa, "desde": ahora}
            # una ventana nueva con pinta de error se mira enseguida
            if self._huele_a_error(titulo):
                self._proponer("error", titulo, programa)
            return

        minutos = (ahora - self.actual["desde"]) / 60.0
        if minutos >= self._minutos_atasco():
            self._proponer("atasco", titulo, programa, minutos)

    def _minutos_atasco(self):
        try:
            return float(self._config().get("minutos_atasco", ATASCO_MINUTOS))
        except Exception:
            return ATASCO_MINUTOS

    @staticmethod
    def _huele_a_error(titulo):
        t = _sin_tildes(titulo)
        return any(p in t for p in ERRORES)

    # ------------------------------------------------------- los frenos
    def ventana_sensible(self, titulo=None):
        """Devuelve que es, si lo que hay delante no se debe fotografiar."""
        t = _sin_tildes(titulo if titulo is not None else (self.actual or {}).get("titulo", ""))
        for aguja, que in _lista_sensible():
            if aguja in t:
                return que
        return None

    def _puede_mirar(self):
        """Tope de fotos por hora, para no comerse la cuota de Google."""
        ahora = time.time()
        while self.miradas and ahora - self.miradas[0] > 3600:
            self.miradas.popleft()
        return len(self.miradas) < MAX_MIRADAS_POR_HORA

    def _proponer(self, motivo, titulo, programa, minutos=0.0):
        ahora = time.time()
        if (ahora - self.ultimo_aviso) / 60.0 < MINUTOS_ENTRE_AVISOS:
            return
        clave = (motivo, titulo)
        if clave in self.ya_avisado:
            return
        sensible = self.ventana_sensible(titulo)
        self.ya_avisado.add(clave)
        self.ultimo_aviso = ahora
        self.avisos.append({"motivo": motivo, "titulo": titulo,
                            "programa": programa, "minutos": minutos,
                            # solo se mira si hay permiso, hueco y no es
                            # una ventana de las suyas
                            "mirar": (sensible is None) and self._puede_mirar(),
                            "sensible": sensible})

    def hay_algo_que_decir(self):
        """La ventana llama a esto; devuelve un aviso o None."""
        try:
            return self.avisos.popleft()
        except IndexError:
            return None

    def apunta_una_mirada(self):
        self.miradas.append(time.time())

    # -------------------------------------------------------- lo que sabe
    def en_que_esta(self):
        if not self.encendido():
            return ("No estoy vigilando la pantalla ahora mismo. Angel puede "
                    "encenderlo con el boton 'Pendiente de ti' de mi ventana.")
        if not self.actual:
            return "Ahora mismo no veo ninguna ventana suya en primer plano."
        m = (time.time() - self.actual["desde"]) / 60.0
        return ("Angel tiene delante '%s' (%s) y lleva %s en ella."
                % (self.actual["titulo"], self.actual["programa"] or "?",
                   "menos de un minuto" if m < 1 else "%d minutos" % m))

    def que_ha_hecho(self, minutos=60):
        """El diario de las ultimas horas. Solo titulos y tiempos, en memoria."""
        if not self.diario and not self.actual:
            return ("Todavia no tengo nada apuntado. O acabo de arrancar, o la "
                    "vigilancia esta apagada.")
        desde = time.time() - float(minutos or 60) * 60
        junto = {}
        trozos = list(self.diario) + ([dict(self.actual, hasta=time.time())]
                                      if self.actual else [])
        for t in trozos:
            fin = t.get("hasta", time.time())
            if fin < desde:
                continue
            dur = fin - max(t["desde"], desde)
            if dur <= 0:
                continue
            k = (t["programa"] or "?", t["titulo"])
            junto[k] = junto.get(k, 0) + dur
        if not junto:
            return "En esa ultima hora no he apuntado nada."
        orden = sorted(junto.items(), key=lambda x: -x[1])[:12]
        l = ["EN LOS ULTIMOS %d MINUTOS, Angel ha estado en:" % minutos, ""]
        for (prog, tit), seg in orden:
            l.append("  %5.1f min  %s  (%s)" % (seg / 60.0, tit[:70], prog))
        l.append("")
        l.append("Son titulos de ventana y tiempos, nada de lo que haya escrito. "
                 "Resumeselo en una o dos frases, no le leas la tabla.")
        return "\n".join(l)

    def estado(self):
        return ("Vigilancia: %s. Avisa cuando lleves mas de %d minutos en la "
                "misma ventana o te salte un error. Fotos de pantalla hechas en "
                "la ultima hora: %d de %d como mucho. Lo que sigue de las "
                "ventanas no sale de tu ordenador."
                % ("encendida" if self.encendido() else "APAGADA",
                   self._minutos_atasco(), len(self.miradas), MAX_MIRADAS_POR_HORA))


# ---------------------------------------------------------------- el unico
_EL = None


def el_vigilante(config=None):
    global _EL
    if _EL is None and config is not None:
        _EL = Vigilante(config)
    return _EL


# ------------------------------------------------ herramientas para Berna
def _cfg():
    try:
        with open(os.path.join(BASE, "config.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def en_que_estoy_ahora():
    v = el_vigilante(_cfg)
    return v.en_que_esta() if v else "La vigilancia no esta en marcha."


def que_he_estado_haciendo(minutos=60):
    v = el_vigilante(_cfg)
    return v.que_ha_hecho(minutos) if v else "La vigilancia no esta en marcha."


def estado_de_la_vigilancia():
    v = el_vigilante(_cfg)
    return v.estado() if v else "La vigilancia no esta en marcha."


def dejar_de_vigilar():
    """Berna puede APAGARLA (como con la camara), pero no encenderla."""
    ruta = os.path.join(BASE, "config.json")
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if not cfg.get("vigilar_pantalla", False):
            return "Ya estaba apagada, no estoy mirando lo que haces."
        cfg["vigilar_pantalla"] = False
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        return ("Dejo de estar pendiente de lo que haces. Para que vuelva, "
                "Angel tiene que pulsar el boton 'Pendiente de ti' de mi "
                "ventana; yo solo no puedo volver a encenderme. Diselo.")
    except Exception as e:
        return "No he podido apagarla: %s" % e
