# -*- coding: utf-8 -*-
"""Navegador de Sobri: sesion temporal propia, separada de Chrome del usuario.

Playwright vive en un unico hilo porque sus paginas no son seguras entre hilos.
No se usa el perfil, las cookies ni las pestanas abiertas del usuario.
"""

from concurrent.futures import Future, TimeoutError as FutureTimeout
import importlib.util
from queue import Queue
import subprocess
import sys
from threading import Lock, Thread
from urllib.parse import urlsplit

_cola = Queue()
_hilo = None
_cerrojo = Lock()
_estado = {"playwright": None, "browser": None, "context": None, "page": None}
_ROLES = {"button", "link", "textbox", "checkbox", "radio", "combobox", "tab", "menuitem"}


def _iniciar():
    global _hilo
    with _cerrojo:
        if _hilo is None or not _hilo.is_alive():
            _hilo = Thread(target=_trabajar, name="Sobri navegador aislado", daemon=True)
            _hilo.start()


def _trabajar():
    while True:
        funcion, argumentos, futuro = _cola.get()
        if not futuro.set_running_or_notify_cancel():
            continue
        try:
            futuro.set_result(funcion(*argumentos))
        except Exception as error:
            futuro.set_exception(error)


def _enviar(funcion, *argumentos):
    _iniciar()
    futuro = Future()
    _cola.put((funcion, argumentos, futuro))
    try:
        return futuro.result(timeout=55)
    except FutureTimeout:
        futuro.cancel()
        return ("No he podido confirmar si la accion termino: el navegador ha tardado "
                "demasiado. Lee la pagina antes de repetirla.")
    except Exception as error:
        return "No he podido usar el navegador aislado: %s" % str(error)[:400]


def _pagina():
    if _estado["page"] is None or _estado["page"].is_closed():
        raise RuntimeError("Primero abre una direccion con web_abrir.")
    return _estado["page"]


def _abrir(url):
    from playwright.sync_api import sync_playwright
    if _estado["playwright"] is None:
        pw = sync_playwright().start()
        try:
            # Cada canal inicia otro proceso con perfil temporal vacio.
            try:
                browser = pw.chromium.launch(channel="chrome", headless=True)
            except Exception:
                try:
                    browser = pw.chromium.launch(channel="msedge", headless=True)
                except Exception:
                    browser = pw.chromium.launch(headless=True)
            context = browser.new_context(accept_downloads=False)
            context.set_default_timeout(12000)
            _estado.update(playwright=pw, browser=browser, context=context)
        except Exception:
            pw.stop()
            raise
    if _estado["page"] is None or _estado["page"].is_closed():
        _estado["page"] = _estado["context"].new_page()
    page = _estado["page"]
    page.goto(url, wait_until="domcontentloaded", timeout=20000)
    return _resumen(page)


def _resumen(page):
    try:
        texto = page.locator("body").inner_text(timeout=5000)[:6500]
    except Exception:
        texto = ""
    controles = page.locator("a,button,input,textarea,select,[role]").evaluate_all("""els =>
      els.filter(el => { const r = el.getBoundingClientRect(); return r.width && r.height; })
         .slice(0, 50).map(el => ({
           rol: el.getAttribute('role') || ({A:'link',BUTTON:'button',
             INPUT: el.type === 'checkbox' ? 'checkbox' : 'textbox',
             TEXTAREA:'textbox',SELECT:'combobox'}[el.tagName] || el.tagName.toLowerCase()),
           nombre: (el.getAttribute('aria-label') || el.labels?.[0]?.innerText ||
             el.innerText || el.getAttribute('placeholder') || el.getAttribute('title') || '').trim().slice(0, 100)
         })).filter(x => x.nombre)
    """)
    return ("Navegador aislado de Sobri (sin perfil ni sesion de Chrome).\n"
            "Direccion: %s\nTitulo: %s\nTexto: %s\nControles: %s" %
            (page.url, page.title()[:150], texto, controles))[:11000]


def _preparar_playwright(permiso):
    if importlib.util.find_spec("playwright") is not None:
        return None
    aviso = ("Para usar webs interactivas necesito instalar Playwright en el "
             "entorno de Sobri (paquete Python playwright==1.63.0, desde PyPI). "
             "No usare tu perfil ni tus sesiones de Chrome. Me dejas instalarlo?")
    if permiso is None or not permiso(aviso):
        return "No he podido abrirla: falta Playwright y no tengo permiso para instalarlo."
    try:
        r = subprocess.run([sys.executable, "-m", "pip", "install", "playwright==1.63.0"],
                           capture_output=True, text=True, timeout=180,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as error:
        return "No he podido instalar Playwright: %s" % str(error)[:200]
    if r.returncode or importlib.util.find_spec("playwright") is None:
        return "No he podido instalar Playwright: %s" % (r.stderr or r.stdout)[-350:]
    return None


def web_abrir(url, permiso=None):
    """Abre una web en la sesion aislada y devuelve sus controles visibles."""
    partes = urlsplit(str(url).strip())
    if partes.scheme not in ("http", "https") or not partes.netloc or partes.username:
        return "No he podido abrirla: usa una URL completa http o https sin credenciales."
    error = _preparar_playwright(permiso)
    if error:
        return error
    return _enviar(_abrir, url)


def web_leer():
    """Lee la pagina activa del navegador aislado."""
    return _enviar(lambda: _resumen(_pagina()))


def _cerrar():
    if _estado["browser"] is not None:
        _estado["browser"].close()
    if _estado["playwright"] is not None:
        _estado["playwright"].stop()
    _estado.update(playwright=None, browser=None, context=None, page=None)
    return "Navegador aislado de Sobri cerrado; sesion temporal descartada."


def web_cerrar():
    """Descarta la sesion, sus cookies y las paginas del navegador aislado."""
    return _enviar(_cerrar)


def _actuar(accion, rol, nombre, texto, esperado_texto, esperado_url):
    page = _pagina()
    if rol not in _ROLES or not nombre:
        return "No he podido actuar: indica un rol y nombre de control visibles en web_leer."
    control = page.get_by_role(rol, name=nombre, exact=True)
    cuantos = control.count()
    if cuantos != 1:
        return "No he podido actuar: encontre %d controles con rol %s y nombre %r. Lee la pagina y concreta uno." % (cuantos, rol, nombre)
    comprobado = False
    texto_ya_estaba = False
    url_anterior = page.url
    if esperado_texto:
        try:
            texto_ya_estaba = page.get_by_text(esperado_texto, exact=False).first.is_visible()
        except Exception:
            pass
    try:
        if accion == "rellenar":
            control.fill(texto, timeout=12000)
            comprobado = control.input_value() == texto
        elif accion == "clic":
            control.click(timeout=12000)
        else:
            return "No he podido actuar: usa clic o rellenar."
    except Exception as error:
        return ("No he podido confirmar si la accion llego a ejecutarse (%s). "
                "Lee la pagina antes de repetirla." % str(error)[:180])
    if esperado_texto:
        try:
            page.get_by_text(esperado_texto, exact=False).first.wait_for(
                state="visible", timeout=12000)
            comprobado = comprobado or not texto_ya_estaba
        except Exception:
            pass
    if esperado_url:
        try:
            page.wait_for_url(esperado_url, timeout=12000)
            comprobado = comprobado or page.url != url_anterior
        except Exception:
            pass
    return ("Accion realizada %s. Direccion actual: %s. %s" %
            ("y resultado comprobado" if comprobado else "pero resultado aun sin comprobar",
             page.url, _resumen(page)[:3500]))


def web_actuar(accion, rol, nombre, texto="", esperado_texto="", esperado_url="", permiso=None):
    """Actua por nombre accesible y comprueba el resultado indicado."""
    if accion not in ("clic", "rellenar"):
        return "No he podido actuar: usa clic o rellenar."
    if accion == "rellenar" and rol not in ("textbox", "combobox"):
        return "No he podido actuar: solo se puede rellenar un cuadro de texto o lista editable."
    pagina = web_leer()
    if not pagina.startswith("Navegador aislado de Sobri"):
        return pagina
    direccion = next((linea.removeprefix("Direccion: ") for linea in pagina.splitlines()
                      if linea.startswith("Direccion: ")), "web desconocida")
    if permiso is None or not permiso("Usar el navegador aislado de Sobri en %s: %s en %s (%s)" %
                                     (direccion, accion, nombre, rol)):
        return "No he podido actuar: falta permiso para actuar en la web."
    return _enviar(_actuar, accion, rol, nombre, texto, esperado_texto, esperado_url)
