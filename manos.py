# -*- coding: utf-8 -*-
r"""
Las manos de Berna sobre el teclado y el raton de verdad.

Hasta ahora Berna miraba la pantalla y le decia a Angel donde pinchar. Con
esto ya pincha y escribe el. Angel lo pidio asi: "que pueda tocar el
ordenador, las aplicaciones, las teclas".

COMO SE USA, que es lo que importa
  1. Berna enciende el MODO MANOS con modo_manos(minutos). Sale UNA ventana
     de permiso que explica que va a hacer y cuanto rato. Mientras dure, ya
     no pregunta en cada tecla, que seria inaguantable.
  2. Si el modo manos esta apagado, cada accion suelta pide su permiso.
  3. Para cortar en seco: soltar lo que se este haciendo y DEJAR PULSADA LA
     TECLA ESC UN SEGUNDO. Se apaga solo. Tambien vale decirle "para" (la
     herramienta parar_manos) o esperar a que se acabe el tiempo.

LOS CERROJOS, que no se relajan
  - Tiempo: el modo manos dura como mucho MAX_MINUTOS y se apaga solo.
  - Tope de acciones: MAX_ACCIONES por sesion, para que un bucle no se
    quede tecleando toda la tarde.
  - Ventanas intocables: si delante hay un banco, una pasarela de pago, un
    gestor de contrasenas o una ventana de seguridad de Windows, NO toca
    nada, ni aunque el modo manos este encendido.
  - No escribe secretos: numeros de tarjeta, IBAN, ni ninguna de las claves
    que hay guardadas en config.json. Eso lo teclea Angel con sus dedos.
  - No se escribe a si mismo: si delante esta su propia ventana, se niega.
  - Todo queda apuntado en tareas\registro.log.

Y LA REGLA DE SIEMPRE, que aqui importa mas que nunca: Berna lee paginas web
y correos, y eso es texto de terceros. Solo mueve las manos cuando se lo pide
Angel. Nunca porque lo diga una pagina, un correo, un chat o un documento.

Detalle tecnico de esta maquina: la pantalla va a 1920x1080 con el escalado
de Windows al 125%, asi que Windows le cuenta al programa que mide 1536x864.
Las capturas de pantalla SI salen a 1920x1080. Por eso aqui las coordenadas
son SIEMPRE las de la captura (pixeles de verdad) y la conversion se hace
dentro, en _a_absoluto(). Si algun dia bailan los clics, mirar eso primero.
"""
import os, re, time, json, ctypes, datetime, threading, unicodedata
from ctypes import wintypes

BASE = os.path.dirname(os.path.abspath(__file__))
REGISTRO = os.path.join(BASE, "tareas", "registro.log")
CONFIG = os.path.join(BASE, "config.json")

MAX_MINUTOS = 15        # lo que puede durar el modo manos como mucho
MAX_ACCIONES = 200      # acciones por sesion de modo manos
MAX_TEXTO = 4000        # caracteres de un tiron
PAUSA_TECLA = 0.008     # entre caracteres, para que la aplicacion siga el ritmo

u32 = ctypes.windll.user32
g32 = ctypes.windll.gdi32

# ------------------------------------------------------------------ SendInput
INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP = 0x0001, 0x0002
KEYEVENTF_UNICODE, KEYEVENTF_SCANCODE = 0x0004, 0x0008
MOUSEEVENTF_MOVE, MOUSEEVENTF_ABSOLUTE, MOUSEEVENTF_VIRTUALDESK = 0x0001, 0x8000, 0x4000
MOUSEEVENTF_WHEEL = 0x0800
BOTONES = {"izquierdo": (0x0002, 0x0004), "derecho": (0x0008, 0x0010),
           "central": (0x0020, 0x0040)}

ULONG_PTR = wintypes.WPARAM


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD)]


class _UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _UNION)]


u32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
u32.SendInput.restype = wintypes.UINT


def _enviar(*entradas):
    n = len(entradas)
    arr = (INPUT * n)(*entradas)
    return u32.SendInput(n, arr, ctypes.sizeof(INPUT))


def _tecla(vk, arriba=False, extendida=False):
    """Una tecla, con su codigo virtual Y su scan code.

    El scan code no es un adorno: las aplicaciones modernas de Windows 11 (el
    Bloc de notas nuevo, sin ir mas lejos) se comen los atajos si va a cero.
    Costo una prueba entera: el texto se escribia bien pero el ctrl+s no
    guardaba nada.
    """
    f = (KEYEVENTF_KEYUP if arriba else 0) | (KEYEVENTF_EXTENDEDKEY if extendida else 0)
    try:
        scan = u32.MapVirtualKeyW(vk, 0) & 0xFF     # MAPVK_VK_TO_VSC
    except Exception:
        scan = 0
    return INPUT(type=INPUT_KEYBOARD,
                 u=_UNION(ki=KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=f, time=0,
                                        dwExtraInfo=0)))


def _caracter(cod, arriba=False):
    f = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if arriba else 0)
    return INPUT(type=INPUT_KEYBOARD,
                 u=_UNION(ki=KEYBDINPUT(wVk=0, wScan=cod, dwFlags=f, time=0,
                                        dwExtraInfo=0)))


def _teclear_caracter(cod):
    """Un caracter, bajada y subida EN UNA SOLA llamada a SendInput.

    Mandarlas en dos llamadas hacia que algunas aplicaciones se comieran letras
    o las repitieran ("Hola Angel,ssoy eerna"). Se vio de verdad en el Bloc de
    notas de Windows 11. Aun asi, para textos largos se pega, que es fiable.
    """
    _enviar(_caracter(cod), _caracter(cod, arriba=True))


# ------------------------------------------------------------------ portapapeles
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
k32 = ctypes.windll.kernel32
k32.GlobalAlloc.restype = ctypes.c_void_p
k32.GlobalLock.restype = ctypes.c_void_p
k32.GlobalLock.argtypes = [ctypes.c_void_p]
k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
u32.GetClipboardData.restype = ctypes.c_void_p
u32.SetClipboardData.restype = ctypes.c_void_p
u32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]


def _abrir_portapapeles(intentos=8):
    """Otro programa puede tenerlo cogido un instante. Se reintenta."""
    for _ in range(intentos):
        if u32.OpenClipboard(0):
            return True
        time.sleep(0.05)
    return False


def _leer_portapapeles():
    if not _abrir_portapapeles():
        return None
    try:
        h = u32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return None
        p = k32.GlobalLock(h)
        if not p:
            return None
        try:
            return ctypes.c_wchar_p(p).value
        finally:
            k32.GlobalUnlock(h)
    except Exception:
        return None
    finally:
        u32.CloseClipboard()


def _poner_portapapeles(texto):
    if not _abrir_portapapeles():
        return False
    try:
        u32.EmptyClipboard()
        datos = ctypes.create_unicode_buffer(texto)
        tam = ctypes.sizeof(datos)
        h = k32.GlobalAlloc(GMEM_MOVEABLE, tam)
        if not h:
            return False
        p = k32.GlobalLock(h)
        if not p:
            return False
        ctypes.memmove(p, ctypes.byref(datos), tam)
        k32.GlobalUnlock(h)
        return bool(u32.SetClipboardData(CF_UNICODETEXT, h))
    except Exception:
        return False
    finally:
        u32.CloseClipboard()


def _raton(dx=0, dy=0, datos=0, flags=0):
    return INPUT(type=INPUT_MOUSE,
                 u=_UNION(mi=MOUSEINPUT(dx=dx, dy=dy, mouseData=datos,
                                        dwFlags=flags, time=0, dwExtraInfo=0)))


# ------------------------------------------------------------------ pantalla
def _escala():
    """Cuanto miente Windows por culpa del escalado. Aqui sale 1.25."""
    try:
        dc = u32.GetDC(0)
        fisico = g32.GetDeviceCaps(dc, 118)      # DESKTOPHORZRES
        u32.ReleaseDC(0, dc)
        logico = u32.GetSystemMetrics(0)         # SM_CXSCREEN
        if fisico and logico:
            return float(fisico) / float(logico)
    except Exception:
        pass
    return 1.0


def _pantalla_fisica():
    """Tamano y origen del escritorio en pixeles de verdad, los de la captura."""
    e = _escala()
    x = int(round(u32.GetSystemMetrics(76) * e))   # SM_XVIRTUALSCREEN
    y = int(round(u32.GetSystemMetrics(77) * e))
    an = int(round(u32.GetSystemMetrics(78) * e))  # SM_CXVIRTUALSCREEN
    al = int(round(u32.GetSystemMetrics(79) * e))
    return x, y, max(an, 1), max(al, 1)


def _a_absoluto(x, y):
    """De pixeles de la captura a las coordenadas 0-65535 que quiere SendInput."""
    vx, vy, an, al = _pantalla_fisica()
    dx = int(round((float(x) - vx) * 65535.0 / float(an - 1 if an > 1 else 1)))
    dy = int(round((float(y) - vy) * 65535.0 / float(al - 1 if al > 1 else 1)))
    return max(0, min(65535, dx)), max(0, min(65535, dy))


def _donde_esta_el_raton():
    class P(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    p = P()
    u32.GetCursorPos(ctypes.byref(p))
    e = _escala()
    return int(round(p.x * e)), int(round(p.y * e))


def _titulo(h):
    n = u32.GetWindowTextLengthW(h)
    if n <= 0:
        return ""
    b = ctypes.create_unicode_buffer(n + 1)
    u32.GetWindowTextW(h, b, n + 1)
    return b.value or ""


def _primer_plano():
    return _titulo(u32.GetForegroundWindow())


# ------------------------------------------------------------------ prohibido
# Ventanas que no se tocan jamas, ni con el modo manos encendido.
INTOCABLES = [
    ("banco", "el banco"), ("bbva", "el banco"), ("santander", "el banco"),
    ("caixa", "el banco"), ("bankinter", "el banco"), ("sabadell", "el banco"),
    ("unicaja", "el banco"), ("ing.es", "el banco"), ("openbank", "el banco"),
    ("paypal", "una pasarela de pago"), ("bizum", "una pasarela de pago"),
    ("checkout", "una pantalla de pago"), ("pagar", "una pantalla de pago"),
    ("pago seguro", "una pantalla de pago"), ("tarjeta de credito", "datos de tarjeta"),
    ("bitwarden", "un gestor de contrasenas"), ("keepass", "un gestor de contrasenas"),
    ("lastpass", "un gestor de contrasenas"), ("1password", "un gestor de contrasenas"),
    ("seguridad de windows", "una ventana de seguridad de Windows"),
    ("windows security", "una ventana de seguridad de Windows"),
    ("control de cuentas de usuario", "el aviso de administrador de Windows"),
    ("iniciar sesion", "una pantalla de inicio de sesion"),
    ("sign in", "una pantalla de inicio de sesion"),
]

# Texto que no teclea aunque se lo dicten.
SECRETOS = [
    (r"\b(?:\d[ -]?){13,19}\b", "parece un numero de tarjeta"),
    (r"\b[A-Z]{2}\d{2}[ ]?(?:\w{4}[ ]?){3,7}\w{1,4}\b", "parece un IBAN"),
    (r"\bsk-[A-Za-z0-9_\-]{20,}", "parece una clave de API"),
    (r"\bAQ\.[A-Za-z0-9_\-]{20,}", "parece una clave de Google"),
    (r"\btvly-[A-Za-z0-9_\-]{10,}", "parece una clave de busqueda"),
]


def _sin_tildes(t):
    t = unicodedata.normalize("NFD", str(t or ""))
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower()


def _claves_guardadas():
    """Las claves del propio Berna, para no soltarlas por ahi en un formulario."""
    fuera = []
    try:
        with open(CONFIG, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        for c in ("clave_api", "clave_gemini", "clave_busqueda", "imap_password"):
            v = (cfg.get(c) or "").strip()
            if len(v) >= 12:
                fuera.append(v)
    except Exception:
        pass
    return fuera


def _ventana_intocable():
    t = _sin_tildes(_primer_plano())
    if not t:
        return None
    for aguja, que in INTOCABLES:
        if aguja in t:
            return que
    return None


def _es_su_ventana():
    return _sin_tildes(_primer_plano()).strip() in ("berna", "berna pide permiso")


def _texto_prohibido(texto):
    for patron, motivo in SECRETOS:
        if re.search(patron, texto):
            return motivo
    for clave in _claves_guardadas():
        if clave in texto:
            return "es una de tus propias claves"
    return None


def _apuntar(que, detalle, resultado):
    try:
        os.makedirs(os.path.dirname(REGISTRO), exist_ok=True)
        with open(REGISTRO, "a", encoding="utf-8") as f:
            f.write("\n[%s] MANOS %s\n  QUE: %s\n  RESULTADO: %s\n"
                    % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), que,
                       str(detalle).replace("\n", " ; ")[:500],
                       str(resultado).replace("\n", " ")[:300]))
    except Exception:
        pass


# ------------------------------------------------------------------ modo manos
_ESTADO = {"hasta": 0.0, "acciones": 0, "para_que": "", "vigilante": None}


def _activo():
    return time.time() < _ESTADO["hasta"] and _ESTADO["acciones"] < MAX_ACCIONES


def _apagar(motivo=""):
    _ESTADO["hasta"] = 0.0
    if motivo:
        _apuntar("MODO MANOS APAGADO", motivo, "")


def _vigilar_esc():
    """Con ESC pulsado un segundo se apaga el modo manos. Es el freno de mano."""
    seguidas = 0
    while _activo():
        try:
            if u32.GetAsyncKeyState(0x1B) & 0x8000:
                seguidas += 1
                if seguidas >= 10:          # 10 x 0,1 s = un segundo
                    _apagar("Angel ha dejado pulsado ESC")
                    return
            else:
                seguidas = 0
        except Exception:
            return
        time.sleep(0.1)


def _consumir(que, detalle, permiso):
    """El unico sitio por donde se pasa antes de tocar nada.

    Devuelve None si se puede seguir, o el texto que hay que contestarle a
    Angel si no.
    """
    intocable = _ventana_intocable()
    if intocable:
        _apuntar("NEGADA", detalle, "delante hay %s" % intocable)
        return ("Ahi NO toco nada: delante tienes %s. Esas pantallas las manejas "
                "tu, que para eso son tuyas. Cambia de ventana y me lo dices."
                % intocable)
    if _es_su_ventana():
        return ("Delante esta mi propia ventana, asi que me estaria escribiendo a "
                "mi mismo. Pon delante el programa donde quieres que escriba, o "
                "dime como se llama la ventana y la busco yo.")
    if _activo():
        _ESTADO["acciones"] += 1
        _apuntar(que, detalle, "modo manos")
        return None
    if _ESTADO["acciones"] >= MAX_ACCIONES and _ESTADO["hasta"] > time.time():
        _apagar("tope de %d acciones" % MAX_ACCIONES)
        return ("He llegado al tope de %d acciones seguidas y he soltado el teclado "
                "solo, por si me habia quedado en bucle. Dime si sigo."
                % MAX_ACCIONES)
    aviso = ("Berna va a tocar tu ordenador:\n\n%s\n\nVentana que hay delante: %s"
             "\n\nDile que SI solo si se lo has pedido tu. Le dejas?"
             % (detalle, _primer_plano() or "ninguna"))
    if permiso is None or not permiso(aviso):
        _apuntar("SIN PERMISO", detalle, "Angel ha dicho que no")
        return "No me has dado permiso, no he tocado nada."
    _apuntar(que, detalle, "permiso suelto")
    return None


def modo_manos(minutos=5, para_que="", permiso=None):
    try:
        minutos = max(1, min(MAX_MINUTOS, int(float(minutos))))
    except Exception:
        minutos = 5
    aviso = ("Berna quiere las MANOS LIBRES durante %d minutos.\n\n"
             "Durante ese rato va a poder mover el raton, pinchar y escribir "
             "con el teclado como si fueras tu, sin volver a preguntar en cada "
             "paso.\n\n%s"
             "Para cortarlo en cualquier momento: DEJA PULSADA LA TECLA ESC UN "
             "SEGUNDO, o dile que pare.\n\n"
             "No tocara bancos, pagos, gestores de contrasenas ni ventanas de "
             "seguridad, y no escribira claves ni numeros de tarjeta.\n\n"
             "Le dejas?" % (minutos, ("Para que: %s\n\n" % para_que) if para_que else ""))
    if permiso is None or not permiso(aviso):
        _apuntar("MODO MANOS", para_que, "Angel ha dicho que no")
        return "No me has dado permiso, sigo con las manos quietas."
    _ESTADO["hasta"] = time.time() + minutos * 60
    _ESTADO["acciones"] = 0
    _ESTADO["para_que"] = str(para_que or "")
    _apuntar("MODO MANOS", para_que, "%d minutos" % minutos)
    v = threading.Thread(target=_vigilar_esc, daemon=True)
    v.start()
    _ESTADO["vigilante"] = v
    return ("Manos libres durante %d minutos. Diselo a Angel y recuerdale que si "
            "quiere que pare de golpe solo tiene que dejar pulsada la tecla ESC "
            "un segundo. Ahora ve paso a paso y mirando la pantalla entre paso y "
            "paso, no dispares diez acciones a ciegas." % minutos)


def parar_manos():
    if not _activo():
        return "Ya tenia las manos quietas."
    _apagar("Angel me ha dicho que pare")
    return "Manos quietas. Ya no toco nada hasta que me lo vuelvas a pedir."


def estado_del_raton():
    x, y = _donde_esta_el_raton()
    _vx, _vy, an, al = _pantalla_fisica()
    quedan = max(0, int(_ESTADO["hasta"] - time.time()))
    partes = ["La pantalla mide %d por %d puntos (los mismos de las capturas)." % (an, al),
              "El raton esta en x=%d y=%d." % (x, y),
              "Delante tienes: %s." % (_primer_plano() or "nada con titulo")]
    if _activo():
        partes.append("Tengo las manos libres %d minutos y %d segundos mas, y llevo "
                      "%d acciones." % (quedan // 60, quedan % 60, _ESTADO["acciones"]))
    else:
        partes.append("No tengo las manos libres: cada cosa que toque te la preguntare.")
    intocable = _ventana_intocable()
    if intocable:
        partes.append("Y esa ventana es de las que no toco: %s." % intocable)
    return " ".join(partes)


# ------------------------------------------------------------------ ventanas
def _traer_al_frente(h):
    r"""Robarle el foco a Windows sin tocar la tecla ALT.

    El truco clasico de dar un toque a ALT para que SetForegroundWindow cuele
    NO se puede usar aqui, y costo una prueba entenderlo: un ALT suelto deja
    ARMADA la barra de menus del programa que hay delante, asi que la siguiente
    tecla se va al menu. En la primera prueba, un ctrl+a acabo abriendo el
    dialogo Archivo > Abrir del Bloc de notas. Se hace con AttachThreadInput,
    que es lo mismo pero sin efectos secundarios.
    """
    try:
        mio = ctypes.windll.kernel32.GetCurrentThreadId()
        suyo = u32.GetWindowThreadProcessId(u32.GetForegroundWindow(), None)
        pegado = False
        if suyo and suyo != mio:
            pegado = bool(u32.AttachThreadInput(suyo, mio, True))
        try:
            u32.BringWindowToTop(h)
            u32.SetForegroundWindow(h)
            u32.SetFocus(h)
        finally:
            if pegado:
                u32.AttachThreadInput(suyo, mio, False)
    except Exception:
        try:
            u32.SetForegroundWindow(h)
        except Exception:
            pass


def enfocar_ventana(titulo, permiso=None):
    buscado = _sin_tildes(titulo)
    if not buscado:
        return "Dime el titulo o un trozo del titulo de la ventana."
    encontradas = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def _cada(h, _lp):
        if u32.IsWindowVisible(h):
            t = _titulo(h)
            if t and buscado in _sin_tildes(t):
                encontradas.append((h, t))
        return True

    u32.EnumWindows(_cada, 0)
    if not encontradas:
        return ("No hay ninguna ventana abierta que se llame asi. Mira con "
                "ventanas_abiertas cuales hay, o abre el programa primero.")
    exactas = [p for p in encontradas if _sin_tildes(p[1]).strip() == buscado.strip()]
    if exactas:
        encontradas = exactas[:1]
    if len(encontradas) > 1:
        # Esto paso de verdad en la primera prueba: se pidio "Bloc de notas" y
        # habia dos, y se escribio en el que no era. Ante la duda, no se elige.
        lista = "\n".join("  - " + t for _h, t in sorted(encontradas, key=lambda p: p[1]))
        return ("Hay %d ventanas que encajan con '%s' y no quiero equivocarme de "
                "sitio:\n%s\nDime cual, con mas letras del titulo."
                % (len(encontradas), titulo, lista))
    h, t = encontradas[0]
    fallo = _consumir("ENFOCAR", "poner delante la ventana '%s'" % t, permiso)
    if fallo:
        return fallo
    try:
        u32.ShowWindow(h, 9)                       # SW_RESTORE
        _traer_al_frente(h)
        time.sleep(0.35)
        ahora = _primer_plano()
        if _sin_tildes(t)[:20] not in _sin_tildes(ahora):
            return ("He pedido poner delante '%s' pero Windows se ha quedado en "
                    "'%s'. Pincha tu una vez en esa ventana y sigo." % (t, ahora))
        return "Ya tengo delante '%s'." % t
    except Exception as e:
        return "No he podido poner esa ventana delante: %s" % e


# ------------------------------------------------------------------ teclado
TECLAS = {
    "ctrl": 0x11, "control": 0x11, "alt": 0x12, "altgr": 0xA5,
    "shift": 0x10, "mayus": 0x10, "mayusculas": 0x10,
    "win": 0x5B, "windows": 0x5B, "menu": 0x5D,
    "intro": 0x0D, "enter": 0x0D, "entrar": 0x0D, "return": 0x0D,
    "esc": 0x1B, "escape": 0x1B, "tab": 0x09, "tabulador": 0x09,
    "espacio": 0x20, "space": 0x20, "barra espaciadora": 0x20,
    "retroceso": 0x08, "borrar": 0x08, "backspace": 0x08,
    "supr": 0x2E, "suprimir": 0x2E, "delete": 0x2E, "del": 0x2E,
    "insert": 0x2D, "insertar": 0x2D,
    "arriba": 0x26, "abajo": 0x28, "izquierda": 0x25, "derecha": 0x27,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "inicio": 0x24, "home": 0x24, "fin": 0x23, "end": 0x23,
    "repag": 0x21, "avpag": 0x22, "pageup": 0x21, "pagedown": 0x22,
    "imppant": 0x2C, "bloqmayus": 0x14, "pausa": 0x13,
}
for _i in range(1, 25):
    TECLAS["f%d" % _i] = 0x6F + _i

# Estas piden el bit de "extendida" o algunos programas las entienden mal.
EXTENDIDAS = {0x26, 0x28, 0x25, 0x27, 0x24, 0x23, 0x21, 0x22, 0x2D, 0x2E,
              0x5B, 0x5D, 0xA5, 0x2C}


def _vk_de(nombre):
    """Devuelve (vk, hace_falta_shift) o (None, False)."""
    n = _sin_tildes(nombre).strip()
    if n in TECLAS:
        return TECLAS[n], False
    if len(n) == 1:
        r = u32.VkKeyScanW(ctypes.c_wchar(n))
        if r != -1:
            return r & 0xFF, bool(r >> 8 & 1)
    return None, False


def pulsar_teclas(teclas, veces=1, ventana="", permiso=None):
    if ventana:
        r = enfocar_ventana(ventana, permiso=permiso)
        if r.startswith("No hay") or r.startswith("No he podido"):
            return r
    try:
        veces = max(1, min(50, int(float(veces))))
    except Exception:
        veces = 1
    combo = str(teclas or "").strip()
    if not combo:
        return "Dime que teclas hay que pulsar, por ejemplo ctrl+s o intro."
    partes = [p for p in re.split(r"\s*\+\s*", combo) if p]
    vks, modificadores = [], []
    for p in partes:
        vk, con_shift = _vk_de(p)
        if vk is None:
            return ("No conozco la tecla '%s'. Usa nombres como intro, tab, esc, "
                    "supr, f5, arriba, o combinaciones como ctrl+s." % p)
        if vk in (0x11, 0x12, 0x10, 0x5B, 0xA5):
            modificadores.append(vk)
        else:
            if con_shift and 0x10 not in modificadores:
                modificadores.append(0x10)
            vks.append(vk)
    if not vks:
        return "Eso son solo teclas de las que acompanan. Dime tambien cual es la principal."
    fallo = _consumir("TECLAS", "pulsar %s%s" % (combo, (" %d veces" % veces) if veces > 1 else ""),
                      permiso)
    if fallo:
        return fallo
    try:
        for _ in range(veces):
            for m in modificadores:
                _enviar(_tecla(m, extendida=m in EXTENDIDAS))
            if modificadores:
                time.sleep(0.03)      # dale tiempo al programa a enterarse
            for vk in vks:
                _enviar(_tecla(vk, extendida=vk in EXTENDIDAS))
                _enviar(_tecla(vk, arriba=True, extendida=vk in EXTENDIDAS))
            for m in reversed(modificadores):
                _enviar(_tecla(m, arriba=True, extendida=m in EXTENDIDAS))
            time.sleep(0.06)
        time.sleep(0.2)
        return ("Pulsado %s%s. Delante tienes '%s'. Mira la pantalla con "
                "mirar_pantalla antes del siguiente paso."
                % (combo, (" %d veces" % veces) if veces > 1 else "",
                   _primer_plano() or "nada"))
    except Exception as e:
        # si algo revienta, no dejar una tecla hundida
        for m in reversed(modificadores):
            try:
                _enviar(_tecla(m, arriba=True))
            except Exception:
                pass
        return "No he podido pulsar esas teclas: %s" % e


def _pegar(texto):
    """Mete el texto por el portapapeles y lo devuelve como estaba.

    Es MUCHO mas fiable que teclear letra a letra, sobre todo con acentos y
    con las aplicaciones nuevas de Windows. Lo que Angel tuviera copiado se
    guarda antes y se le devuelve despues, que si no le desaparece.
    """
    viejo = _leer_portapapeles()
    if not _poner_portapapeles(texto):
        return False
    time.sleep(0.12)
    _enviar(_tecla(0x11))                    # ctrl
    time.sleep(0.03)
    _enviar(_tecla(0x56))                    # v
    _enviar(_tecla(0x56, arriba=True))
    _enviar(_tecla(0x11, arriba=True))
    time.sleep(0.45)                         # que le de tiempo a leerlo
    if viejo is not None:
        _poner_portapapeles(viejo)
    else:
        _poner_portapapeles("")              # no dejarle ahi lo que he escrito
    return True


def _teclear(texto):
    for ch in texto:
        if ch == "\n":
            _enviar(_tecla(0x0D), _tecla(0x0D, arriba=True))
        elif ch == "\t":
            _enviar(_tecla(0x09), _tecla(0x09, arriba=True))
        elif ch == "\r":
            continue
        else:
            cod = ord(ch)
            if cod > 0xFFFF:                 # emoji y demas, van en dos mitades
                cod -= 0x10000
                _teclear_caracter(0xD800 + (cod >> 10))
                _teclear_caracter(0xDC00 + (cod & 0x3FF))
            else:
                _teclear_caracter(cod)
        time.sleep(PAUSA_TECLA)


def escribir_texto(texto, ventana="", intro=False, despacio=False, permiso=None):
    texto = str(texto if texto is not None else "")
    if not texto:
        return "No me has dado nada que escribir."
    if len(texto) > MAX_TEXTO:
        return ("Son %d caracteres y de un tiron solo escribo %d. Pasamelo por "
                "trozos, o mejor te lo copio al portapapeles y lo pegas con "
                "ctrl+v." % (len(texto), MAX_TEXTO))
    malo = _texto_prohibido(texto)
    if malo:
        _apuntar("NEGADA", texto[:40] + "...", malo)
        return ("Eso NO lo escribo yo: %s. Los numeros de tarjeta, los IBAN y las "
                "claves los tecleas tu con tus dedos, aunque me los dictes. No es "
                "desconfianza, es que yo leo paginas web y no debo ser quien las "
                "escriba." % malo)
    if ventana:
        r = enfocar_ventana(ventana, permiso=permiso)
        if r.startswith("No hay") or r.startswith("No he podido"):
            return r
    resumen = texto if len(texto) <= 300 else texto[:300] + " [...]"
    fallo = _consumir("ESCRIBIR", "escribir esto:\n\n" + resumen, permiso)
    if fallo:
        return fallo
    letra_a_letra = despacio is True or _sin_tildes(despacio).strip() in ("si", "true", "1", "yes")
    try:
        if letra_a_letra or not _pegar(texto):
            _teclear(texto)
            como = "tecleado letra a letra"
        else:
            como = "pegado de golpe"
        if intro is True or _sin_tildes(intro).strip() in ("si", "true", "1", "yes"):
            time.sleep(0.15)
            _enviar(_tecla(0x0D), _tecla(0x0D, arriba=True))
        time.sleep(0.2)
        return ("Escrito (%d caracteres, %s) en '%s'. Comprueba con mirar_pantalla "
                "que ha entrado donde tocaba antes de seguir."
                % (len(texto), como, _primer_plano() or "la ventana de delante"))
    except Exception as e:
        return "No he podido escribirlo: %s" % e


# ------------------------------------------------------------------ raton
def mover_raton(x, y, permiso=None):
    try:
        x, y = int(float(x)), int(float(y))
    except Exception:
        return "Dame las dos coordenadas en numeros, tal como las ves en la captura."
    fallo = _consumir("RATON", "mover el raton a x=%d y=%d" % (x, y), permiso)
    if fallo:
        return fallo
    dx, dy = _a_absoluto(x, y)
    _enviar(_raton(dx=dx, dy=dy,
                   flags=MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK))
    time.sleep(0.1)
    rx, ry = _donde_esta_el_raton()
    return "Raton en x=%d y=%d." % (rx, ry)


def clic_raton(x=None, y=None, boton="izquierdo", doble=False, permiso=None):
    b = _sin_tildes(boton).strip() or "izquierdo"
    if b in ("izq", "left", "principal"):
        b = "izquierdo"
    if b in ("der", "right", "secundario", "contextual"):
        b = "derecho"
    if b in ("medio", "middle", "rueda"):
        b = "central"
    if b not in BOTONES:
        return "El boton es izquierdo, derecho o central."
    doble = doble is True or _sin_tildes(doble).strip() in ("si", "true", "1", "yes")
    if x is None or y is None:
        px, py = _donde_esta_el_raton()
        donde = "donde esta ahora el raton (x=%d y=%d)" % (px, py)
        mover = False
    else:
        try:
            x, y = int(float(x)), int(float(y))
        except Exception:
            return "Dame las dos coordenadas en numeros."
        donde = "x=%d y=%d" % (x, y)
        mover = True
    fallo = _consumir("CLIC", "%s clic con el boton %s en %s"
                      % ("doble" if doble else "un", b, donde), permiso)
    if fallo:
        return fallo
    try:
        if mover:
            dx, dy = _a_absoluto(x, y)
            _enviar(_raton(dx=dx, dy=dy, flags=MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE
                           | MOUSEEVENTF_VIRTUALDESK))
            time.sleep(0.12)
        abajo, arriba = BOTONES[b]
        for _ in range(2 if doble else 1):
            _enviar(_raton(flags=abajo))
            time.sleep(0.03)
            _enviar(_raton(flags=arriba))
            time.sleep(0.06)
        time.sleep(0.3)
        return ("Clic dado en %s. Ahora delante tienes '%s'. Mira la pantalla antes "
                "de seguir, que un clic puede haber abierto otra cosa."
                % (donde, _primer_plano() or "nada"))
    except Exception as e:
        return "No he podido dar el clic: %s" % e


def arrastrar_raton(x1, y1, x2, y2, permiso=None):
    try:
        x1, y1, x2, y2 = (int(float(v)) for v in (x1, y1, x2, y2))
    except Exception:
        return "Dame las cuatro coordenadas en numeros."
    fallo = _consumir("ARRASTRAR", "arrastrar desde x=%d y=%d hasta x=%d y=%d"
                      % (x1, y1, x2, y2), permiso)
    if fallo:
        return fallo
    try:
        mover_flags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
        dx, dy = _a_absoluto(x1, y1)
        _enviar(_raton(dx=dx, dy=dy, flags=mover_flags))
        time.sleep(0.15)
        _enviar(_raton(flags=BOTONES["izquierdo"][0]))
        time.sleep(0.1)
        pasos = 20
        for i in range(1, pasos + 1):
            ix = x1 + (x2 - x1) * i / float(pasos)
            iy = y1 + (y2 - y1) * i / float(pasos)
            ax, ay = _a_absoluto(ix, iy)
            _enviar(_raton(dx=ax, dy=ay, flags=mover_flags))
            time.sleep(0.015)
        time.sleep(0.1)
        _enviar(_raton(flags=BOTONES["izquierdo"][1]))
        time.sleep(0.25)
        return "Arrastrado hasta x=%d y=%d." % (x2, y2)
    except Exception as e:
        try:
            _enviar(_raton(flags=BOTONES["izquierdo"][1]))
        except Exception:
            pass
        return "No he podido arrastrar: %s" % e


def rueda_raton(pasos=3, permiso=None):
    try:
        pasos = int(float(pasos))
    except Exception:
        pasos = 3
    pasos = max(-30, min(30, pasos))
    if pasos == 0:
        return "Dime cuantos pasos, en positivo para subir y en negativo para bajar."
    fallo = _consumir("RUEDA", "girar la rueda %d pasos hacia %s"
                      % (abs(pasos), "arriba" if pasos > 0 else "abajo"), permiso)
    if fallo:
        return fallo
    try:
        for _ in range(abs(pasos)):
            _enviar(_raton(datos=120 if pasos > 0 else -120, flags=MOUSEEVENTF_WHEEL))
            time.sleep(0.05)
        time.sleep(0.2)
        return "Rueda girada %d pasos hacia %s." % (abs(pasos), "arriba" if pasos > 0 else "abajo")
    except Exception as e:
        return "No he podido girar la rueda: %s" % e
