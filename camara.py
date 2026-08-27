# -*- coding: utf-8 -*-
r"""
Berna mirando por la camara, y acordandose de quien ve.

Angel lo pidio asi: "que sea capaz de verme por la camara, que reconozca a
las personas diferentes cada vez que las vea, y que se acuerde de ellas".

COMO FUNCIONA
  Se enciende la camara un instante, se coge un fotograma, se buscan las
  caras (modelo YuNet) y de cada cara se saca un vector de 128 numeros
  (modelo SFace). Ese vector es como una huella: dos fotos de la misma
  persona dan vectores parecidos, y de personas distintas, no. Los vectores
  se guardan en caras.json, asi que **reconoce a la gente entre un dia y
  otro**, no solo dentro de la misma conversacion.

  A quien no conoce lo apunta solo como "persona 1", "persona 2"... para
  poder distinguirlo la proxima vez. Cuando Angel dice quien es, se le pone
  el nombre y se conservan sus vectores.

PRIVACIDAD, que aqui importa de verdad
  - La camara se enciende SOLO cuando Angel lo pide, para un fotograma, y se
    apaga enseguida. No hay vigilancia continua ni se graba video.
  - Las caras NO salen del ordenador: el reconocimiento es local, con los dos
    modelos que hay en la carpeta modelos\. Solo sale una foto hacia Google
    si Angel pide expresamente que se la describan, igual que en vista.py.
  - Todo uso de la camara queda apuntado en tareas\registro.log.
  - Se puede olvidar a cualquiera con olvidar_a_persona, y eso borra sus
    vectores de verdad.

LOS DOS MODELOS
  modelos\deteccion_caras.onnx  (YuNet, 227 KB)   busca donde hay caras
  modelos\reconocer_caras.onnx  (SFace, 37 MB)    saca la huella de cada una
  Salen del zoo oficial de OpenCV. Si faltan, las herramientas lo dicen en
  cristiano en vez de reventar.
"""
import os, json, time, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
CARAS = os.path.join(BASE, "caras.json")
MODELOS = os.path.join(BASE, "modelos")
REGISTRO = os.path.join(BASE, "tareas", "registro.log")
CARPETA_FOTOS = os.path.join(os.path.expanduser("~"), "Pictures", "Berna")

DETECTOR = os.path.join(MODELOS, "deteccion_caras.onnx")
RECONOCEDOR = os.path.join(MODELOS, "reconocer_caras.onnx")

# Umbral de parecido del coseno. El oficial de SFace es 0,363; se sube un poco
# porque equivocarse de persona es peor que decir "no te conozco".
UMBRAL = 0.38
CARA_MINIMA = 60        # pixeles de ancho; mas pequena es alguien del fondo
CONFIANZA_MINIMA = 0.85
CALENTAR = 6            # fotogramas que se tiran; la webcam sale oscura al abrir
MAX_VECTORES = 6        # huellas guardadas por persona (varias luces y angulos)

FALTAN_MODELOS = ("Me faltan los modelos de reconocer caras. Tendrian que estar "
                  "en C:\\Asistente\\modelos. Sin ellos veo que hay una cara "
                  "pero no puedo saber de quien es.")


# ------------------------------------------------------------------ registro
def _apuntar(que, detalle=""):
    try:
        os.makedirs(os.path.dirname(REGISTRO), exist_ok=True)
        with open(REGISTRO, "a", encoding="utf-8") as f:
            f.write("\n[%s] CAMARA %s\n  %s\n"
                    % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                       que, str(detalle)[:300]))
    except Exception:
        pass


def _ahora():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def _cuando(texto):
    """De una fecha guardada a algo que se pueda decir en voz alta."""
    try:
        d = datetime.datetime.strptime(texto, "%Y-%m-%d %H:%M")
    except Exception:
        return texto
    dias = (datetime.datetime.now().date() - d.date()).days
    if dias == 0:
        return "hoy a las %s" % d.strftime("%H:%M")
    if dias == 1:
        return "ayer"
    if dias < 7:
        return "hace %d dias" % dias
    return "el %s" % d.strftime("%d/%m/%Y")


# ------------------------------------------------------------------ la libreta
def _cargar():
    if os.path.exists(CARAS):
        try:
            with open(CARAS, "r", encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict) and "personas" in d:
                return d
        except Exception:
            pass
    return {"personas": []}


def _guardar(d):
    tmp = CARAS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)
    os.replace(tmp, CARAS)


def _buscar_persona(d, nombre):
    n = (nombre or "").strip().lower()
    for p in d["personas"]:
        if p["nombre"].strip().lower() == n:
            return p
    return None


def _siguiente_apodo(d):
    usados = set()
    for p in d["personas"]:
        n = p["nombre"].lower()
        if n.startswith("persona "):
            try:
                usados.add(int(n.split()[1]))
            except Exception:
                pass
    i = 1
    while i in usados:
        i += 1
    return "persona %d" % i


# ------------------------------------------------------------------ los modelos
_det = {"obj": None, "tam": None}
_rec = {"obj": None}


def hay_modelos():
    return os.path.exists(DETECTOR) and os.path.exists(RECONOCEDOR)


def _detector(ancho, alto):
    import cv2
    if _det["obj"] is None or _det["tam"] != (ancho, alto):
        _det["obj"] = cv2.FaceDetectorYN.create(DETECTOR, "", (ancho, alto),
                                                CONFIANZA_MINIMA, 0.3, 5000)
        _det["tam"] = (ancho, alto)
    return _det["obj"]


def _reconocedor():
    import cv2
    if _rec["obj"] is None:
        _rec["obj"] = cv2.FaceRecognizerSF.create(RECONOCEDOR, "")
    return _rec["obj"]


def _vector(imagen, cara):
    """La huella de 128 numeros de una cara, ya recortada y enderezada."""
    import numpy as np
    rec = _reconocedor()
    recorte = rec.alignCrop(imagen, cara)
    v = rec.feature(recorte)
    v = np.asarray(v, dtype="float32").reshape(-1)
    n = float(np.linalg.norm(v))
    return (v / n) if n else v          # normalizado: el coseno es el producto


def _parecido(v1, v2):
    import numpy as np
    a, b = np.asarray(v1, "float32"), np.asarray(v2, "float32")
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if not na or not nb:
        return 0.0
    return float(a.dot(b) / (na * nb))


def _identificar(d, vector):
    """Devuelve (persona, parecido) de la mas parecida, o (None, mejor)."""
    mejor, cual = 0.0, None
    for p in d["personas"]:
        for v in p.get("vectores", []):
            s = _parecido(vector, v)
            if s > mejor:
                mejor, cual = s, p
    return (cual, mejor) if mejor >= UMBRAL else (None, mejor)


# ------------------------------------------------------------------ la camara
def _abrir(indice=0):
    import cv2
    for modo in (cv2.CAP_DSHOW, cv2.CAP_MSMF, 0):
        try:
            cap = cv2.VideoCapture(indice, modo) if modo else cv2.VideoCapture(indice)
            if cap.isOpened():
                return cap
            cap.release()
        except Exception:
            pass
    return None


APAGADA = ("La camara esta APAGADA. Angel la ha desconectado con el boton "
           "'Camara' de mi ventana. Diselo tal cual: que si quiere que mire, "
           "tiene que volver a encenderla el con ese boton. Yo no puedo "
           "encenderla, y eso es a proposito.")


def camara_encendida():
    """Si el interruptor de la ventana esta puesto. Por defecto, si.

    Se lee del config.json en CADA uso, no se guarda en memoria: asi apagarla
    tiene efecto en el acto, sin reiniciar nada.
    """
    try:
        with open(os.path.join(BASE, "config.json"), "r", encoding="utf-8") as f:
            return bool(json.load(f).get("camara_activada", True))
    except Exception:
        return True


def apagar_camara():
    """Berna puede APAGARLA, pero no encenderla. La asimetria es el invento.

    Encender es lo que tiene riesgo, asi que eso pide una mano humana en el
    boton: ni una pagina web ni un correo pueden convencerle de que la
    encienda. Apagar no se lo puede negar a nadie, asi que eso si lo hace.
    """
    ruta = os.path.join(BASE, "config.json")
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if not cfg.get("camara_activada", True):
            return "La camara ya estaba apagada."
        cfg["camara_activada"] = False
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        _apuntar("CAMARA APAGADA", "se lo ha pedido Angel")
        return ("Camara apagada. No voy a poder mirar nada hasta que Angel la "
                "vuelva a encender con el boton 'Camara' de mi ventana; yo solo "
                "no puedo. Diselo, para que sepa como recuperarla.")
    except Exception as e:
        return "No he podido apagarla: %s" % e


def _fotograma(indice=0):
    """Un fotograma decente, o (None, motivo)."""
    # El interruptor va LO PRIMERO y aqui dentro a proposito: todas las
    # herramientas de camara pasan por este sitio, asi que no hay forma de
    # colarse por otro lado.
    if not camara_encendida():
        return None, APAGADA
    try:
        import cv2  # noqa: F401
    except Exception:
        return None, ("No tengo instalado OpenCV, que es lo que maneja la camara. "
                      "Se arregla con: pip install opencv-python")
    cap = _abrir(indice)
    if cap is None:
        return None, ("No he podido encender la camara. Mira que no la tenga "
                      "cogida otro programa (Teams, Meet, la camara de Windows) "
                      "y que este permitida en Configuracion, Privacidad, Camara.")
    try:
        imagen, t0 = None, time.time()
        for _ in range(CALENTAR):          # la webcam sale negra los primeros
            ok, f = cap.read()
            if ok:
                imagen = f
            if time.time() - t0 > 6:
                break
            time.sleep(0.05)
        if imagen is None:
            return None, "La camara se ha encendido pero no me da imagen."
        return imagen, None
    finally:
        cap.release()


def _caras_de(imagen):
    alto, ancho = imagen.shape[:2]
    n, caras = _detector(ancho, alto).detect(imagen)
    if caras is None:
        return []
    buenas = []
    for c in caras:
        if float(c[2]) >= CARA_MINIMA:     # de frente y lo bastante cerca
            buenas.append(c)
    buenas.sort(key=lambda c: -float(c[2]) * float(c[3]))
    return buenas


# ------------------------------------------------------------------ mirar
def mirar_por_la_camara(pregunta="", apuntar_desconocidos=True):
    if not hay_modelos():
        return FALTAN_MODELOS
    imagen, fallo = _fotograma()
    if imagen is None:
        return fallo
    caras = _caras_de(imagen)
    d = _cargar()
    vistos, nuevos = [], []
    for c in caras:
        try:
            v = _vector(imagen, c)
        except Exception:
            continue
        p, parecido = _identificar(d, v)
        if p is None:
            if not apuntar_desconocidos:
                vistos.append("alguien a quien no conozco")
                continue
            p = {"nombre": _siguiente_apodo(d), "vectores": [], "notas": "",
                 "primera_vez": _ahora(), "ultima_vez": "", "veces": 0,
                 "sin_nombre": True}
            d["personas"].append(p)
            nuevos.append(p["nombre"])
        else:
            # una huella mas, que ayuda con otra luz u otro angulo
            if len(p.get("vectores", [])) < MAX_VECTORES and parecido < 0.75:
                p.setdefault("vectores", []).append([float(x) for x in v])
        if not p.get("vectores"):
            p["vectores"] = [[float(x) for x in v]]
        antes = p.get("ultima_vez", "")
        p["veces"] = int(p.get("veces", 0)) + 1
        p["ultima_vez"] = _ahora()
        trozo = p["nombre"]
        if p.get("notas"):
            trozo += " (%s)" % p["notas"]
        if antes:
            trozo += ", que ya habias visto %s" % _cuando(antes)
        elif p["nombre"] not in nuevos:
            trozo += ", que ya conocias"
        vistos.append(trozo)
    _guardar(d)
    _apuntar("MIRAR", "%d caras: %s" % (len(caras), ", ".join(vistos) or "nadie"))

    if not caras:
        salida = ("He mirado por la camara y no veo a nadie delante. Puede que "
                  "este tapada, o que la persona no este de frente.")
    else:
        salida = "Por la camara veo a %d: %s." % (len(caras), "; ".join(vistos))
        if nuevos:
            salida += (" A %s no le conozco todavia: le he apuntado con ese apodo "
                       "para reconocerle la proxima vez. PREGUNTALE A ANGEL COMO "
                       "SE LLAMA y guardalo con poner_nombre_a_persona."
                       % " y ".join(nuevos))
    if pregunta:
        salida += "\n\n" + _describir(imagen, pregunta)
    return salida


def _describir(imagen, pregunta):
    """Lo que no es una cara lo describe el modelo de Google, como vista.py."""
    try:
        import cv2, vista
        from PIL import Image
        rgb = cv2.cvtColor(imagen, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        if not vista._clave():
            return vista.SIN_CLAVE
        uri = vista._a_data_uri(img)
        return vista._preguntar_a_los_ojos(
            uri, pregunta,
            "Es una foto tomada ahora con la camara del ordenador de Angel.")
    except Exception as e:
        return "No he podido describir lo que veo: %s" % e


# ------------------------------------------------------------------ recordar gente
def recordar_a_esta_persona(nombre, notas="", permiso=None):
    nombre = (nombre or "").strip()
    if not nombre:
        return "Dime como se llama para poder apuntarla."
    if not hay_modelos():
        return FALTAN_MODELOS
    pregunta = ("Berna va a APUNTAR LA CARA de esta persona para reconocerla "
                "en adelante:\n\n%s\n\nSe guardan unos numeros que representan "
                "la cara (no la foto) en C:\\Asistente\\caras.json, y no salen "
                "del ordenador. Se puede borrar cuando quieras.\n\n"
                "Que este mirando a la camara. Le dejas?" % nombre)
    if permiso is None or not permiso(pregunta):
        return "No me has dado permiso, no he apuntado a nadie."
    d = _cargar()
    vectores, intentos = [], 0
    while len(vectores) < 3 and intentos < 5:
        intentos += 1
        imagen, fallo = _fotograma()
        if imagen is None:
            return fallo
        caras = _caras_de(imagen)
        if caras:
            try:
                vectores.append([float(x) for x in _vector(imagen, caras[0])])
            except Exception:
                pass
        time.sleep(0.3)
    if not vectores:
        return ("No he conseguido verle la cara. Que se ponga de frente, con luz "
                "y a medio metro de la camara, y lo intento otra vez.")
    # si ya le conocia con otro nombre (o como "persona 3"), es la misma
    p, parecido = _identificar(d, vectores[0])
    ya = _buscar_persona(d, nombre)
    if p is not None and ya is not None and p is not ya:
        return ("Ojo: esa cara ya la tengo apuntada como %s, y ademas ya existe "
                "otra ficha llamada %s. Dime cual me quedo para no liarla."
                % (p["nombre"], nombre))
    ficha = ya or p
    if ficha is None:
        ficha = {"nombre": nombre, "vectores": [], "notas": "",
                 "primera_vez": _ahora(), "ultima_vez": _ahora(), "veces": 1}
        d["personas"].append(ficha)
        que = "apuntada por primera vez"
    else:
        que = ("ya la conocia como '%s' y le he puesto el nombre bueno"
               % ficha["nombre"]) if ficha["nombre"] != nombre else "ya la conocia"
        ficha["nombre"] = nombre
    ficha.pop("sin_nombre", None)
    ficha["vectores"] = (ficha.get("vectores", []) + vectores)[-MAX_VECTORES:]
    if notas:
        ficha["notas"] = notas
    ficha["ultima_vez"] = _ahora()
    _guardar(d)
    _apuntar("APUNTAR PERSONA", "%s (%s)" % (nombre, que))
    return ("Listo: %s, %s. Tengo %d huellas suyas y le reconocere la proxima vez "
            "que se ponga delante." % (nombre, que, len(ficha["vectores"])))


def poner_nombre_a_persona(apodo, nombre, notas=""):
    d = _cargar()
    p = _buscar_persona(d, apodo)
    if p is None:
        return ("No tengo a nadie apuntado como '%s'. Mira la lista con "
                "personas_que_conozco." % apodo)
    if _buscar_persona(d, nombre) is not None:
        return ("Ya tengo a alguien llamado '%s'. Si son la misma persona, "
                "olvidame al del apodo y vuelve a apuntarle mirando a la camara."
                % nombre)
    viejo = p["nombre"]
    p["nombre"] = (nombre or "").strip() or viejo
    p.pop("sin_nombre", None)
    if notas:
        p["notas"] = notas
    _guardar(d)
    _apuntar("NOMBRE", "%s -> %s" % (viejo, p["nombre"]))
    return "Hecho: %s se llama %s. Ya le reconocere por su nombre." % (viejo, p["nombre"])


def anotar_de_persona(nombre, nota):
    d = _cargar()
    p = _buscar_persona(d, nombre)
    if p is None:
        return "No conozco a nadie llamado '%s'." % nombre
    p["notas"] = ((p.get("notas", "") + ". ") if p.get("notas") else "") + str(nota)
    p["notas"] = p["notas"][:400]
    _guardar(d)
    return "Apuntado sobre %s: %s" % (nombre, nota)


def personas_que_conozco():
    d = _cargar()
    if not d["personas"]:
        return ("Todavia no conozco a nadie de cara. Cuando alguien se ponga "
                "delante de la camara le apunto, y si me dices como se llama, "
                "mejor.")
    lineas = ["Gente que reconozco de cara (%d):" % len(d["personas"])]
    for p in sorted(d["personas"], key=lambda x: x.get("ultima_vez", ""), reverse=True):
        t = "  - %s" % p["nombre"]
        if p.get("sin_nombre"):
            t += " (aun no se como se llama)"
        if p.get("notas"):
            t += ": %s" % p["notas"]
        t += ". Visto %d veces, la ultima %s, desde %s." % (
            p.get("veces", 0), _cuando(p.get("ultima_vez", "")),
            _cuando(p.get("primera_vez", "")))
        lineas.append(t)
    lineas.append("")
    lineas.append("Cuentaselo con tus palabras, no como una lista.")
    return "\n".join(lineas)


def olvidar_a_persona(nombre, permiso=None):
    d = _cargar()
    p = _buscar_persona(d, nombre)
    if p is None:
        return "No tengo a nadie apuntado como '%s'." % nombre
    if permiso is None or not permiso(
            "Berna va a OLVIDAR la cara de %s.\n\nSe borran sus huellas de "
            "caras.json y dejara de reconocerle. No tiene vuelta atras.\n\n"
            "Le dejas?" % p["nombre"]):
        return "No me has dado permiso, no he borrado nada."
    d["personas"].remove(p)
    _guardar(d)
    _apuntar("OLVIDAR", p["nombre"])
    return "Olvidado. Ya no reconozco a %s." % p["nombre"]


# ------------------------------------------------------------------ fotos y estado
def hacer_foto(permiso=None):
    if permiso is None or not permiso(
            "Berna va a HACER UNA FOTO con la camara y guardarla en tus "
            "Imagenes.\n\nLe dejas?"):
        return "No me has dado permiso, no he hecho ninguna foto."
    imagen, fallo = _fotograma()
    if imagen is None:
        return fallo
    try:
        import cv2
        os.makedirs(CARPETA_FOTOS, exist_ok=True)
        ruta = os.path.join(CARPETA_FOTOS, time.strftime("camara-%Y%m%d-%H%M%S.png"))
        cv2.imwrite(ruta, imagen)
        _apuntar("FOTO", ruta)
        return "Foto guardada en %s." % ruta
    except Exception as e:
        return "No he podido guardarla: %s" % e


def estado_camara():
    partes = []
    if not camara_encendida():
        return ("La camara esta APAGADA con el boton de mi ventana, asi que no "
                "puedo ni comprobarla. Si Angel quiere que vuelva a ver, tiene "
                "que encenderla el con el boton 'Camara'.")
    try:
        import cv2
        partes.append("OpenCV %s instalado." % cv2.__version__)
    except Exception:
        return ("No tengo OpenCV, asi que no puedo usar la camara. Se instala "
                "con pip install opencv-python.")
    partes.append("Modelos de reconocer caras: %s."
                  % ("puestos" if hay_modelos() else "FALTAN, mirar C:\\Asistente\\modelos"))
    imagen, fallo = _fotograma()
    if imagen is None:
        partes.append("La camara NO responde: " + fallo)
    else:
        alto, ancho = imagen.shape[:2]
        partes.append("La camara funciona y da imagen de %dx%d." % (ancho, alto))
        partes.append("Ahora mismo veo %d caras." % len(_caras_de(imagen)))
    d = _cargar()
    partes.append("Tengo apuntadas %d personas." % len(d["personas"]))
    return " ".join(partes)
