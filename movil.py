# -*- coding: utf-8 -*-
"""Berna en el movil.

Berna vive en una ventana de Windows: tiene cuerpo, camara, manos y voz, y nada
de eso cabe en un telefono. Lo que si cabe es su cabeza. Este modulo levanta un
servidor web pequeno que reutiliza el mismo cerebro (herramientas.py, las 150
de siempre) y la misma configuracion, y lo sirve como una pagina que se ve bien
en el movil.

O sea: Berna sigue viviendo en el ordenador de casa, y el telefono es una
ventana mas para hablar con ella desde donde estes.

Se arranca con Berna-Movil.bat, o a mano:

    venv\\Scripts\\python.exe movil.py

No instala nada: solo usa la biblioteca estandar y requests, que ya estaba.
"""

import json
import os
import secrets
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CARPETA = os.path.dirname(os.path.abspath(__file__))
os.chdir(CARPETA)
sys.path.insert(0, CARPETA)

import herramientas as Hr  # noqa: E402  (despues del chdir, a proposito)

PUERTO = 8733
URL_API = "https://openrouter.ai/api/v1/chat/completions"
URL_GEMINI = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

# Cuanto se aparta un cerebro que acaba de fallar, igual que en la ventana.
CASTIGO_CUOTA = 30 * 60
CASTIGO_SATURADO = 3 * 60

# Cuantas vueltas de herramientas como mucho en una respuesta. Sin tope, un
# modelo que se atasca puede quedarse llamando a herramientas sin parar.
MAX_VUELTAS = 6

_castigados = {}
_charlas = {}          # token de sesion -> lista de mensajes
_candado = threading.Lock()


def anotar(texto):
    """Deja constancia en el mismo cuaderno que usa la Berna de escritorio."""
    try:
        with open(os.path.join(CARPETA, "berna.log"), "a", encoding="utf-8") as f:
            f.write("[%s] movil: %s\n"
                    % (time.strftime("%Y-%m-%d %H:%M:%S"), texto))
    except Exception:
        pass


def cargar_config():
    try:
        with open(os.path.join(CARPETA, "config.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def obtener_clave(cfg):
    """La clave de OpenRouter, igual que la busca asistente.py."""
    if cfg.get("clave_api"):
        return cfg["clave_api"].strip()
    ruta = cfg.get("clave_api_archivo")
    if ruta and os.path.exists(ruta):
        try:
            return open(ruta, "r", encoding="utf-8").read().strip()
        except Exception:
            return ""
    return ""


def destino(cfg, modelo):
    """A donde mandar la peticion. Devuelve (url, cabeceras, modelo) o None."""
    if modelo.startswith("gemini:"):
        clave = (cfg.get("clave_gemini") or "").strip()
        if not clave:
            return None
        return (URL_GEMINI,
                {"Authorization": "Bearer " + clave,
                 "Content-Type": "application/json"},
                modelo.split(":", 1)[1])
    clave = obtener_clave(cfg)
    if not clave:
        return None
    return (URL_API,
            {"Authorization": "Bearer " + clave, "Content-Type": "application/json"},
            modelo)


def _sirve(modelo):
    return time.time() >= _castigados.get(modelo, 0)


def _castigar(modelo, err):
    """Aparta un rato al cerebro que acaba de fallar, para no tropezar con el."""
    e = str(err or "")
    if "429" in e or e == "CUOTA_DIARIA":
        cuanto = CASTIGO_CUOTA
    elif "503" in e or "HTTP 5" in e or "timeout" in e.lower():
        cuanto = CASTIGO_SATURADO
    else:
        return
    if _sirve(modelo):
        anotar("cerebro apartado %d min: %s (%s)" % (cuanto // 60, modelo, e[:40]))
    _castigados[modelo] = time.time() + cuanto


def sistema(manos):
    """Lo que Berna lee antes de contestar.

    Es mas corto que el de la ventana a proposito: aqui no hay cuerpo que
    describir ni camara que mirar, y conviene que lo tenga claro para que no
    prometa cosas que desde el movil no puede hacer.
    """
    s = ("Eres Berna, el asistente de casa. Hablas en espanol de Espana, con "
         "naturalidad y sin florituras. Vas al grano.\n\n"
         "Ahora mismo te estan hablando desde el movil, por la web. Sigues "
         "viviendo en el ordenador de casa y tus herramientas actuan sobre ese "
         "ordenador, no sobre el telefono. No tienes camara ni voz en esta "
         "conversacion: si te piden algo de eso, dilo claramente y ofrece la "
         "alternativa que si puedas hacer.\n\n"
         "NUNCA menciones que modelo de lenguaje ni que empresa hay detras.\n\n")
    if manos:
        s += ("El interruptor de tocar el ordenador esta ENCENDIDO: puedes "
              "escribir archivos, abrir programas y ejecutar ordenes. Aun asi, "
              "avisa antes de hacer algo que no tenga vuelta atras.")
    else:
        s += ("El interruptor de tocar el ordenador esta APAGADO: puedes mirar, "
              "buscar y leer, pero cualquier herramienta que escriba, abra "
              "programas o mueva el raton va a fallar. Si hace falta una de "
              "esas, no lo intentes: dile que encienda el interruptor.")
    return s


def _sin_permiso(_pregunta):
    """Lo que responde el guardian cuando el interruptor esta apagado."""
    return False


def _con_permiso(_pregunta):
    return True


def una_ronda(cfg, modelo, mensajes):
    """Una llamada al modelo. Devuelve (texto, llamadas, error)."""
    import requests
    d = destino(cfg, modelo)
    if d is None:
        return "", [], "sin clave configurada"
    url, cab, nombre = d
    try:
        r = requests.post(url, headers=cab, timeout=180,
                          json={"model": nombre, "messages": mensajes,
                                "tools": Hr.ESQUEMAS, "max_tokens": 1400})
        if r.status_code != 200:
            cuerpo = ""
            try:
                cuerpo = r.text[:400]
            except Exception:
                pass
            if r.status_code == 429 and "free-models-per-day" in cuerpo:
                return "", [], "CUOTA_DIARIA"
            return "", [], "HTTP %d %s" % (r.status_code, cuerpo[:120])
        datos = r.json()
        msg = (datos.get("choices") or [{}])[0].get("message") or {}
        return msg.get("content") or "", msg.get("tool_calls") or [], None
    except Exception as e:
        return "", [], str(e)


def responder(texto, historial, manos):
    """El bucle de siempre: pensar, usar herramientas, volver a pensar."""
    cfg = cargar_config()
    modelos = cfg.get("modelos") or []
    permiso = _con_permiso if manos else _sin_permiso

    historial.append({"role": "user", "content": texto})
    mensajes = ([{"role": "system", "content": sistema(manos)}]
                + historial[-int(cfg.get("memoria_turnos") or 20):])
    usadas = []
    ultimo_error = "no hay ningun cerebro configurado"

    for _ in range(MAX_VUELTAS):
        salida = None
        for modelo in modelos:
            if not _sirve(modelo):
                continue
            contenido, llamadas, err = una_ronda(cfg, modelo, mensajes)
            if err:
                ultimo_error = err
                _castigar(modelo, err)
                continue
            salida = (contenido, llamadas)
            break

        if salida is None:
            historial.pop()          # esa pregunta no llego a contestarse
            return ("Ahora mismo no consigo pensar: %s." % ultimo_error), usadas

        contenido, llamadas = salida
        if not llamadas:
            historial.append({"role": "assistant", "content": contenido})
            return contenido, usadas

        # El modelo quiere herramientas. Se las damos y volvemos a preguntarle.
        mensajes.append({"role": "assistant", "content": contenido or None,
                         "tool_calls": llamadas})
        for lla in llamadas:
            fn = (lla.get("function") or {})
            nombre = fn.get("name") or ""
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except Exception:
                args = {}
            resultado = Hr.ejecutar(nombre, args, permiso=permiso)
            usadas.append(nombre)
            anotar("herramienta %s%s" % (nombre, "" if manos else " (sin manos)"))
            mensajes.append({"role": "tool", "tool_call_id": lla.get("id"),
                             "content": str(resultado)[:6000]})

    historial.append({"role": "assistant",
                      "content": "Me he liado dando vueltas. Preguntamelo de otra forma."})
    return "Me he liado dando vueltas. Preguntamelo de otra forma.", usadas


PAGINA = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#11161d">
<title>Berna</title>
<style>
:root{--fondo:#11161d;--panel:#1a222c;--linea:#2a3542;--texto:#e8eef5;
      --suave:#8fa3b8;--mia:#2f6df6;--acento:#49d17f}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;height:100%}
body{background:var(--fondo);color:var(--texto);display:flex;flex-direction:column;
     font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header{display:flex;align-items:center;gap:10px;padding:14px 16px;
       padding-top:calc(14px + env(safe-area-inset-top));
       background:var(--panel);border-bottom:1px solid var(--linea)}
.punto{width:9px;height:9px;border-radius:50%;background:var(--acento);flex:none}
h1{font-size:17px;margin:0;font-weight:600;flex:1}
.manos{display:flex;align-items:center;gap:7px;font-size:12px;color:var(--suave)}
.sw{position:relative;width:40px;height:23px;flex:none}
.sw input{opacity:0;width:0;height:0;position:absolute}
.pista{position:absolute;inset:0;background:#3a4756;border-radius:99px;
       transition:background .2s;cursor:pointer}
.pista:before{content:"";position:absolute;width:17px;height:17px;left:3px;top:3px;
              background:#fff;border-radius:50%;transition:transform .2s}
.sw input:checked + .pista{background:#c2532f}
.sw input:checked + .pista:before{transform:translateX(17px)}
#chat{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:12px;
      overscroll-behavior:contain}
.msg{max-width:86%;padding:10px 14px;border-radius:16px;white-space:pre-wrap;
     word-wrap:break-word}
.yo{align-self:flex-end;background:var(--mia);border-bottom-right-radius:5px}
.ella{align-self:flex-start;background:var(--panel);border:1px solid var(--linea);
      border-bottom-left-radius:5px}
.aviso{align-self:center;color:var(--suave);font-size:13px;text-align:center;
       max-width:92%}
.tools{align-self:flex-start;color:var(--suave);font-size:12px;margin-top:-6px;
       padding-left:6px}
footer{display:flex;gap:9px;padding:12px;padding-bottom:calc(12px + env(safe-area-inset-bottom));
       background:var(--panel);border-top:1px solid var(--linea)}
textarea{flex:1;resize:none;background:var(--fondo);color:var(--texto);
         border:1px solid var(--linea);border-radius:12px;padding:11px 13px;
         font:inherit;max-height:130px}
textarea:focus{outline:none;border-color:var(--mia)}
button{background:var(--mia);color:#fff;border:0;border-radius:12px;padding:0 20px;
       font:inherit;font-weight:600;cursor:pointer}
button:disabled{opacity:.45}
.pensando{display:inline-block;width:7px;height:7px;border-radius:50%;
          background:var(--suave);animation:p 1.1s infinite}
@keyframes p{0%,80%{opacity:.25}40%{opacity:1}}
</style>
</head>
<body>
<header>
  <span class="punto"></span>
  <h1>Berna</h1>
  <label class="manos">tocar el PC
    <span class="sw"><input type="checkbox" id="manos"><span class="pista"></span></span>
  </label>
</header>
<div id="chat">
  <div class="aviso">Berna esta en el ordenador de casa. Preguntale lo que quieras.</div>
</div>
<footer>
  <textarea id="txt" rows="1" placeholder="Escribe aqui..."></textarea>
  <button id="env">Enviar</button>
</footer>
<script>
const chat=document.getElementById('chat'), txt=document.getElementById('txt'),
      env=document.getElementById('env'), manos=document.getElementById('manos');
const ficha=localStorage.getItem('berna_sesion')||
      (Math.random().toString(36).slice(2)+Date.now().toString(36));
localStorage.setItem('berna_sesion',ficha);
manos.checked = localStorage.getItem('berna_manos')==='1';
manos.onchange = ()=>localStorage.setItem('berna_manos', manos.checked?'1':'0');

function pon(clase,texto){
  const d=document.createElement('div'); d.className='msg '+clase; d.textContent=texto;
  chat.appendChild(d); chat.scrollTop=chat.scrollHeight; return d;
}
txt.addEventListener('input',()=>{txt.style.height='auto';
                                  txt.style.height=Math.min(txt.scrollHeight,130)+'px'});
txt.addEventListener('keydown',e=>{
  if(e.key==='Enter' && !e.shiftKey && window.innerWidth>820){e.preventDefault();mandar()}});
env.onclick=mandar;

async function mandar(){
  const t=txt.value.trim(); if(!t) return;
  txt.value=''; txt.style.height='auto'; pon('yo',t);
  env.disabled=true;
  const esperando=pon('ella',''); esperando.innerHTML='<span class="pensando"></span>';
  try{
    const r=await fetch('/api/hablar',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({texto:t, sesion:ficha, manos:manos.checked})});
    const d=await r.json();
    esperando.textContent = d.respuesta || d.error || 'No he entendido nada.';
    if(d.usadas && d.usadas.length){
      const u=document.createElement('div'); u.className='tools';
      u.textContent='herramientas: '+d.usadas.join(', ');
      chat.appendChild(u);
    }
  }catch(e){ esperando.textContent='No he podido hablar con el ordenador de casa: '+e; }
  env.disabled=false; chat.scrollTop=chat.scrollHeight; txt.focus();
}
</script>
</body>
</html>
"""


# El cliente de terminal, para Termux. Se sirve desde el propio Berna con la
# direccion y la llave ya puestas, asi no hay que copiar nada a mano en el
# telefono: un curl lo baja y ya funciona.
SCRIPT_TERMUX = r"""#!/data/data/com.termux/files/usr/bin/bash
# Berna, desde la terminal del movil.
# Instalado desde el propio Berna el %(fecha)s.
#
#   berna que hora es        una pregunta suelta
#   berna                    conversacion, hasta que escribas "adios"
#   berna -m instala tal     con permiso para tocar el PC (cuidado)

URL="%(url)s"
LLAVE="%(llave)s"
SESION="termux"
MANOS=0

if [ "$1" = "-m" ]; then MANOS=1; shift; fi
if [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
  sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 0
fi

preguntar() {
  curl -s --max-time 200 \
       -X POST "$URL/api/texto?k=$LLAVE&s=$SESION&manos=$MANOS" \
       --data-binary "$1" \
    || echo "No llego al ordenador de casa. Esta encendido? Y el wifi?"
}

if [ $# -gt 0 ]; then
  preguntar "$*"
  exit 0
fi

echo "Berna. Escribe 'adios' para salir."
[ "$MANOS" = "1" ] && echo "(con permiso para tocar el PC)"
while true; do
  printf '\n> '
  read -r linea || break
  case "$linea" in
    ""|" ") continue ;;
    adios|salir|exit|q) echo "Hasta luego."; break ;;
  esac
  echo
  preguntar "$linea"
done
"""


class Manejador(BaseHTTPRequestHandler):
    server_version = "Berna"

    def log_message(self, *_a):
        pass                                  # sin ruido en la consola

    # -- utilidades -------------------------------------------------------
    def _autorizado(self):
        """La llave va en la direccion (?k=...) o en una cabecera."""
        if not LLAVE:
            return True
        if self.headers.get("X-Berna") == LLAVE:
            return True
        return ("k=" + LLAVE) in (self.path or "")

    def _responder(self, codigo, cuerpo, tipo="application/json; charset=utf-8"):
        if isinstance(cuerpo, str):
            cuerpo = cuerpo.encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(cuerpo)
        except Exception:
            pass

    # -- rutas ------------------------------------------------------------
    def do_GET(self):
        if not self._autorizado():
            self._responder(403, "Esta pagina no es para ti.", "text/plain; charset=utf-8")
            return
        ruta = self.path.split("?")[0]
        if ruta in ("/", "/index.html"):
            self._responder(200, PAGINA, "text/html; charset=utf-8")
        elif ruta == "/api/estado":
            self._responder(200, json.dumps({"vivo": True,
                                             "herramientas": len(Hr.ESQUEMAS)}))
        elif ruta in ("/berna.sh", "/termux"):
            guion = SCRIPT_TERMUX % {"url": "http://%s:%d" % (mi_ip(), PUERTO),
                                     "llave": LLAVE,
                                     "fecha": time.strftime("%Y-%m-%d")}
            self._responder(200, guion, "text/plain; charset=utf-8")
        else:
            self._responder(404, "{}")

    def do_POST(self):
        ruta = self.path.split("?")[0]
        # /api/texto habla en crudo, para la terminal: se le manda la frase tal
        # cual y devuelve la respuesta pelada, sin JSON que haya que desarmar.
        # Asi desde Termux basta un curl, sin jq ni python instalados.
        crudo = (ruta == "/api/texto")
        tipo = "text/plain; charset=utf-8" if crudo else "application/json; charset=utf-8"

        if not self._autorizado():
            self._responder(403, "Sin llave." if crudo
                            else json.dumps({"error": "sin llave"}), tipo)
            return
        if ruta not in ("/api/hablar", "/api/texto"):
            self._responder(404, "No existe esa puerta." if crudo else "{}", tipo)
            return

        try:
            n = int(self.headers.get("Content-Length") or 0)
            bruto = self.rfile.read(n).decode("utf-8", "replace")
        except Exception:
            self._responder(400, "No te he entendido." if crudo
                            else json.dumps({"error": "no te he entendido"}), tipo)
            return

        if crudo:
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            texto = bruto.strip()
            sesion = (q.get("s") or ["terminal"])[0]
            manos = (q.get("manos") or ["0"])[0] in ("1", "si", "true")
        else:
            try:
                datos = json.loads(bruto)
            except Exception:
                self._responder(400, json.dumps({"error": "no te he entendido"}), tipo)
                return
            texto = (datos.get("texto") or "").strip()
            sesion = datos.get("sesion") or "suelta"
            manos = bool(datos.get("manos"))

        if not texto:
            self._responder(400, "No has dicho nada." if crudo
                            else json.dumps({"error": "no has dicho nada"}), tipo)
            return

        with _candado:
            historial = _charlas.setdefault(sesion, [])
        try:
            respuesta, usadas = responder(texto, historial, manos)
            if crudo:
                self._responder(200, respuesta + "\n", tipo)
            else:
                self._responder(200, json.dumps({"respuesta": respuesta,
                                                 "usadas": usadas}), tipo)
        except Exception as e:
            anotar("fallo contestando: %s" % e)
            self._responder(500, ("Me he atascado: %s" % e) if crudo
                            else json.dumps({"error": "me he atascado: %s" % e}), tipo)


def mi_ip():
    """La IP de esta maquina en la red de casa."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


LLAVE = ""


def main():
    global LLAVE
    cfg = cargar_config()
    # La llave se puede fijar en config.json como "clave_movil". Si no, se
    # inventa una nueva en cada arranque: mas incordio, pero mas seguro.
    LLAVE = (cfg.get("clave_movil") or "").strip() or secrets.token_urlsafe(9)

    if not obtener_clave(cfg) and not (cfg.get("clave_gemini") or "").strip():
        print("AVISO: no hay ninguna clave de cerebro en config.json.")
        print("Berna arrancara, pero no sabra contestar.\n")

    direccion = "http://%s:%d/?k=%s" % (mi_ip(), PUERTO, LLAVE)
    print("=" * 62)
    print(" Berna, en el movil")
    print("=" * 62)
    print(" Abre esta direccion en el navegador del telefono:\n")
    print("   " + direccion + "\n")
    print(" O, si prefieres la terminal (Termux), pega esto UNA VEZ:\n")
    print("   curl -s \"http://%s:%d/berna.sh?k=%s\" -o $PREFIX/bin/berna && chmod +x $PREFIX/bin/berna"
          % (mi_ip(), PUERTO, LLAVE))
    print("\n   ...y a partir de ahi, en Termux: berna que hora es\n")
    print(" El movil tiene que estar en el mismo wifi que este ordenador.")
    print(" Para cerrar: Ctrl+C, o cierra esta ventana.")
    print("=" * 62)
    anotar("servidor movil abierto en el puerto %d" % PUERTO)

    servidor = ThreadingHTTPServer(("0.0.0.0", PUERTO), Manejador)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nBerna se despide del movil.")
    finally:
        servidor.server_close()
        anotar("servidor movil cerrado")


if __name__ == "__main__":
    main()
