# -*- coding: utf-8 -*-
r"""
Fotos y videos: lo que mas le toca a Angel, que se dedica al dron.

Aqui esta lo que un fotografo o un piloto de dron hace cien veces al mes y a
mano es un peñazo: ordenar mil fotos por fecha, ver donde y con que se tomo
una, sacar copias pequenas para mandar por WhatsApp, saber cuanto dura y a
que resolucion esta un video, sacar fotogramas, y **transcribir** lo que se
dice en un video para poner subtitulos.

DE DONDE SALEN LOS DATOS
  Las fotos traen EXIF (fecha, camara, y en las del dron TAMBIEN LAS
  COORDENADAS GPS). Se lee con Pillow, que ya estaba. Los videos se leen con
  PyAV, que tambien estaba (venia con el oido). O sea que **no hace falta
  instalar nada**.

LA REGLA QUE NO SE SALTA: NO SE PISAN LOS ORIGINALES
  Redimensionar, sacar fotogramas y cualquier cosa que genere archivos
  escribe SIEMPRE en una carpeta nueva. Ordenar SI mueve, porque para eso
  es, pero pide permiso ensenando cuantos archivos va a mover y adonde, y
  nunca sobreescribe: si ya hay uno con ese nombre, le pone un numero.

  Un fallo aqui no es un error de programa, es el trabajo de alguien.

LO DE TRANSCRIBIR
  Usa el mismo Whisper que ya tiene cargado para oir a Angel, que se lo pasa
  la ventana (NECESITAN_OIDO en herramientas.py). Asi no se carga un segundo
  modelo en memoria. Saca el texto y, si se pide, un .srt de subtitulos con
  sus tiempos, listo para meter en el editor de video.
"""
import os
import time
import shutil
import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
REGISTRO = os.path.join(BASE, "tareas", "registro.log")

FOTOS = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".heic", ".webp", ".dng", ".raw")
VIDEOS = (".mp4", ".mov", ".avi", ".mkv", ".m4v", ".mts", ".webm")
AUDIOS = (".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".wma")

MAX_ARCHIVOS = 5000
MAX_SEGUNDOS = 120          # tope para cualquier recorrido de disco


def _apuntar(que, detalle, resultado=""):
    try:
        import tareas
        tareas._apuntar("MEDIOS " + que, detalle, resultado)
    except Exception:
        pass


def _listar(carpeta, extensiones, hondo=False):
    fuera, t0 = [], time.time()
    if not os.path.isdir(carpeta):
        return fuera
    if hondo:
        for raiz, dirs, files in os.walk(carpeta):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for f in files:
                if f.lower().endswith(extensiones):
                    fuera.append(os.path.join(raiz, f))
                if len(fuera) >= MAX_ARCHIVOS or time.time() - t0 > MAX_SEGUNDOS:
                    return fuera
    else:
        for f in sorted(os.listdir(carpeta)):
            ruta = os.path.join(carpeta, f)
            if os.path.isfile(ruta) and f.lower().endswith(extensiones):
                fuera.append(ruta)
    return fuera


def _sin_pisar(ruta):
    """Nunca sobreescribir: si existe, ruta-2.jpg, ruta-3.jpg..."""
    if not os.path.exists(ruta):
        return ruta
    raiz, ext = os.path.splitext(ruta)
    i = 2
    while os.path.exists("%s-%d%s" % (raiz, i, ext)):
        i += 1
    return "%s-%d%s" % (raiz, i, ext)


def _tamano(n):
    for u in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return "%.0f %s" % (n, u) if u != "GB" else "%.2f GB" % n
        n /= 1024.0
    return "%.2f GB" % n


# ------------------------------------------------------------------ EXIF
def _exif(ruta):
    """Los datos de dentro de una foto. Devuelve un diccionario, nunca revienta."""
    datos = {}
    try:
        from PIL import Image, ExifTags
        with Image.open(ruta) as img:
            datos["ancho"], datos["alto"] = img.size
            crudo = img.getexif()
            if not crudo:
                return datos
            nombres = {v: k for k, v in ExifTags.TAGS.items()}
            for etiqueta, valor in crudo.items():
                nombre = ExifTags.TAGS.get(etiqueta)
                if nombre in ("DateTimeOriginal", "DateTime", "Make", "Model",
                              "LensModel", "FNumber", "ExposureTime", "ISOSpeedRatings",
                              "FocalLength", "Orientation"):
                    datos[nombre] = valor
            ifd = crudo.get_ifd(nombres.get("ExifOffset", 0x8769)) or {}
            for etiqueta, valor in ifd.items():
                nombre = ExifTags.TAGS.get(etiqueta)
                if nombre in ("DateTimeOriginal", "FNumber", "ExposureTime",
                              "ISOSpeedRatings", "FocalLength", "LensModel"):
                    datos.setdefault(nombre, valor)
            gps = crudo.get_ifd(nombres.get("GPSInfo", 0x8825)) or {}
            if gps:
                coord = _gps(gps)
                if coord:
                    datos["gps"] = coord
                alt = gps.get(6)
                if alt:
                    try:
                        datos["altura"] = float(alt)
                    except Exception:
                        pass
    except Exception:
        pass
    return datos


def _gps(gps):
    """De los grados/minutos/segundos del EXIF a numeros normales."""
    try:
        def grados(v):
            d, m, s = [float(x) for x in v]
            return d + m / 60.0 + s / 3600.0
        lat = grados(gps[2])
        lon = grados(gps[4])
        if str(gps.get(1, "N")).upper().startswith("S"):
            lat = -lat
        if str(gps.get(3, "E")).upper().startswith("W"):
            lon = -lon
        return round(lat, 6), round(lon, 6)
    except Exception:
        return None


def _fecha_de(ruta, datos=None):
    """Cuando se tomo de verdad; si no hay EXIF, cuando se creo el archivo."""
    datos = datos if datos is not None else _exif(ruta)
    crudo = datos.get("DateTimeOriginal") or datos.get("DateTime")
    if crudo:
        try:
            return datetime.datetime.strptime(str(crudo)[:19], "%Y:%m:%d %H:%M:%S"), True
        except Exception:
            pass
    try:
        return datetime.datetime.fromtimestamp(os.path.getmtime(ruta)), False
    except Exception:
        return datetime.datetime.now(), False


# ------------------------------------------------------------------ herramientas
def datos_de_foto(ruta):
    if not os.path.isfile(ruta):
        return "No encuentro esa foto: %s" % ruta
    d = _exif(ruta)
    if not d:
        return ("De %s no puedo sacar datos: o no es una foto o no trae "
                "informacion dentro." % os.path.basename(ruta))
    fecha, de_exif = _fecha_de(ruta, d)
    partes = ["Datos de %s:" % os.path.basename(ruta)]
    partes.append("  Tamano de la imagen: %sx%s" % (d.get("ancho", "?"), d.get("alto", "?")))
    partes.append("  Ocupa: %s" % _tamano(os.path.getsize(ruta)))
    partes.append("  Tomada: %s%s" % (fecha.strftime("%d/%m/%Y a las %H:%M"),
                                      "" if de_exif else " (por la fecha del archivo, "
                                                         "no trae la de la camara)"))
    camara = " ".join(str(d[k]).strip() for k in ("Make", "Model") if d.get(k))
    if camara:
        partes.append("  Camara: %s" % camara)
    if d.get("LensModel"):
        partes.append("  Objetivo: %s" % d["LensModel"])
    ajustes = []
    if d.get("FNumber"):
        ajustes.append("f/%.1f" % float(d["FNumber"]))
    if d.get("ExposureTime"):
        e = float(d["ExposureTime"])
        ajustes.append("1/%d s" % round(1 / e) if e and e < 1 else "%.1f s" % e)
    if d.get("ISOSpeedRatings"):
        ajustes.append("ISO %s" % d["ISOSpeedRatings"])
    if d.get("FocalLength"):
        ajustes.append("%.0f mm" % float(d["FocalLength"]))
    if ajustes:
        partes.append("  Ajustes: %s" % ", ".join(ajustes))
    if d.get("gps"):
        lat, lon = d["gps"]
        partes.append("  DONDE SE TOMO: %.6f, %.6f" % (lat, lon))
        partes.append("  Verlo en el mapa: https://www.google.com/maps?q=%.6f,%.6f"
                      % (lat, lon))
        if d.get("altura"):
            partes.append("  Altura: %.0f metros" % d["altura"])
    partes.append("")
    partes.append("Cuentaselo con tus palabras. Si tiene coordenadas, dile que "
                  "puedes decirle de que sitio es si te lo pide.")
    return "\n".join(partes)


def ordenar_fotos(carpeta, destino="", permiso=None):
    if not os.path.isdir(carpeta):
        return "No encuentro esa carpeta: %s" % carpeta
    fotos = _listar(carpeta, FOTOS + VIDEOS)
    if not fotos:
        return ("En %s no hay ninguna foto ni video sueltos. Mira que sea la "
                "carpeta buena." % carpeta)
    destino = destino or carpeta
    if not os.path.isdir(destino):
        try:
            os.makedirs(destino, exist_ok=True)
        except Exception as e:
            return "No he podido preparar la carpeta de destino: %s" % e
    # se calcula antes para poder ensenarselo en el aviso
    plan, meses = {}, {}
    for ruta in fotos:
        fecha, _ = _fecha_de(ruta)
        carpetita = fecha.strftime("%Y-%m")
        plan[ruta] = carpetita
        meses[carpetita] = meses.get(carpetita, 0) + 1
    resumen = ", ".join("%s (%d)" % (k, v) for k, v in sorted(meses.items())[:8])
    if len(meses) > 8:
        resumen += "..."
    aviso = ("Berna va a ORDENAR %d archivos por la fecha en que se tomaron.\n\n"
             "De: %s\nA:  %s\n\nSe crearan carpetas por ano y mes: %s\n\n"
             "Los archivos SE MUEVEN (no se copian) y no se sobreescribe "
             "ninguno. Le dejas?" % (len(fotos), carpeta, destino, resumen))
    if permiso is None or not permiso(aviso):
        return "No me has dado permiso, no he movido nada."
    movidos, fallos = 0, []
    for ruta, carpetita in plan.items():
        try:
            fuera = os.path.join(destino, carpetita)
            os.makedirs(fuera, exist_ok=True)
            shutil.move(ruta, _sin_pisar(os.path.join(fuera, os.path.basename(ruta))))
            movidos += 1
        except Exception as e:
            fallos.append("%s (%s)" % (os.path.basename(ruta), e))
    _apuntar("ORDENAR", carpeta, "%d movidos" % movidos)
    salida = ("Ordenadas %d cosas en %d carpetas por ano y mes, dentro de %s."
              % (movidos, len(meses), destino))
    if fallos:
        salida += "\n\nNo he podido con %d: %s" % (len(fallos), "; ".join(fallos[:5]))
    return salida


def redimensionar_fotos(carpeta, ancho=1600, destino=""):
    if not os.path.isdir(carpeta):
        return "No encuentro esa carpeta: %s" % carpeta
    try:
        ancho = max(100, min(8000, int(float(ancho))))
    except Exception:
        ancho = 1600
    fotos = _listar(carpeta, FOTOS)
    if not fotos:
        return "En esa carpeta no hay fotos."
    destino = destino or os.path.join(carpeta, "copias-%d" % ancho)
    os.makedirs(destino, exist_ok=True)
    hechas, ahorro = 0, 0
    try:
        from PIL import Image
    except Exception as e:
        return "No tengo Pillow para tocar imagenes: %s" % e
    t0 = time.time()
    for ruta in fotos:
        if time.time() - t0 > MAX_SEGUNDOS:
            break
        try:
            with Image.open(ruta) as img:
                if img.width <= ancho:
                    continue
                alto = int(img.height * ancho / float(img.width))
                copia = img.convert("RGB").resize((ancho, alto), Image.LANCZOS)
                fuera = _sin_pisar(os.path.join(
                    destino, os.path.splitext(os.path.basename(ruta))[0] + ".jpg"))
                copia.save(fuera, "JPEG", quality=88)
                ahorro += os.path.getsize(ruta) - os.path.getsize(fuera)
                hechas += 1
        except Exception:
            pass
    _apuntar("REDIMENSIONAR", carpeta, "%d fotos a %dpx" % (hechas, ancho))
    if not hechas:
        return ("No he encogido ninguna: o ya eran mas pequenas de %d puntos de "
                "ancho, o no he podido abrirlas." % ancho)
    return ("Hechas %d copias de %d puntos de ancho en:\n%s\n\nLos originales "
            "NO se han tocado. Asi ocupan %s menos y se pueden mandar por "
            "WhatsApp o correo sin problema." % (hechas, ancho, destino,
                                                 _tamano(max(0, ahorro))))


def info_de_video(ruta):
    if not os.path.isfile(ruta):
        return "No encuentro ese video: %s" % ruta
    try:
        import av
    except Exception as e:
        return "No tengo la libreria de video: %s" % e
    try:
        with av.open(ruta) as c:
            v = next((s for s in c.streams if s.type == "video"), None)
            a = next((s for s in c.streams if s.type == "audio"), None)
            dur = float(c.duration) / 1000000.0 if c.duration else 0
            partes = ["Datos de %s:" % os.path.basename(ruta)]
            partes.append("  Ocupa: %s" % _tamano(os.path.getsize(ruta)))
            if dur:
                partes.append("  Dura: %d minutos y %d segundos"
                              % (int(dur // 60), int(dur % 60)))
            if v:
                fps = float(v.average_rate) if v.average_rate else 0
                partes.append("  Imagen: %dx%d a %.2f fotogramas por segundo"
                              % (v.codec_context.width, v.codec_context.height, fps))
                partes.append("  Codec de video: %s" % v.codec_context.name)
                if v.codec_context.height >= 2160:
                    partes.append("  O sea, 4K.")
                elif v.codec_context.height >= 1080:
                    partes.append("  O sea, Full HD.")
            if a:
                partes.append("  Sonido: %s, %d Hz, %d canales"
                              % (a.codec_context.name, a.codec_context.sample_rate or 0,
                                 a.codec_context.channels or 0))
            else:
                partes.append("  NO tiene sonido.")
            if dur and os.path.getsize(ruta):
                partes.append("  Calidad media: %.1f megabits por segundo"
                              % (os.path.getsize(ruta) * 8 / dur / 1000000.0))
            return "\n".join(partes)
    except Exception as e:
        return "No he podido leer ese video: %s" % e


def sacar_fotogramas(ruta, cada_segundos=5, cuantos=12, destino=""):
    if not os.path.isfile(ruta):
        return "No encuentro ese video: %s" % ruta
    try:
        import av
    except Exception as e:
        return "No tengo la libreria de video: %s" % e
    try:
        cada = max(0.2, float(cada_segundos))
        cuantos = max(1, min(60, int(float(cuantos))))
    except Exception:
        cada, cuantos = 5.0, 12
    destino = destino or os.path.join(os.path.dirname(ruta),
                                      os.path.splitext(os.path.basename(ruta))[0]
                                      + "-fotogramas")
    os.makedirs(destino, exist_ok=True)
    sacados, siguiente, t0 = 0, 0.0, time.time()
    try:
        with av.open(ruta) as c:
            v = next((s for s in c.streams if s.type == "video"), None)
            if v is None:
                return "Ese archivo no tiene imagen."
            v.thread_type = "AUTO"
            for cuadro in c.decode(v):
                if sacados >= cuantos or time.time() - t0 > MAX_SEGUNDOS:
                    break
                if cuadro.time is None or cuadro.time + 0.001 < siguiente:
                    continue
                fuera = os.path.join(destino, "fotograma-%03d-%ds.jpg"
                                     % (sacados + 1, int(cuadro.time)))
                cuadro.to_image().save(_sin_pisar(fuera), "JPEG", quality=90)
                sacados += 1
                siguiente = cuadro.time + cada
    except Exception as e:
        return "No he podido sacar los fotogramas: %s" % e
    _apuntar("FOTOGRAMAS", ruta, "%d" % sacados)
    if not sacados:
        return "No he conseguido sacar ningun fotograma de ese video."
    return ("Sacados %d fotogramas (uno cada %.0f segundos) en:\n%s\n\nPuedo "
            "mirarlos si quieres que te diga que sale en ellos."
            % (sacados, cada, destino))


def _srt(tiempo):
    h = int(tiempo // 3600)
    m = int((tiempo % 3600) // 60)
    s = int(tiempo % 60)
    ms = int((tiempo - int(tiempo)) * 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def transcribir(ruta, subtitulos=False, oido=None):
    if not os.path.isfile(ruta):
        return "No encuentro ese archivo: %s" % ruta
    if not ruta.lower().endswith(VIDEOS + AUDIOS):
        return ("Eso no parece ni un video ni un audio. Paso archivos como .mp4, "
                ".mov, .mp3 o .wav.")
    modelo = oido
    if modelo is None:
        try:
            from faster_whisper import WhisperModel
            modelo = WhisperModel("base", device="cpu", compute_type="int8")
        except Exception as e:
            return "No tengo el oido preparado: %s" % e
    try:
        trozos, info = modelo.transcribe(ruta, language="es", vad_filter=True)
        trozos = list(trozos)
    except Exception as e:
        return "No he podido escucharlo: %s" % e
    if not trozos:
        return "He escuchado el archivo y no se dice nada que se entienda."
    texto = " ".join(t.text.strip() for t in trozos).strip()
    base = os.path.splitext(ruta)[0]
    salidas = []
    try:
        con_texto = _sin_pisar(base + "-transcripcion.txt")
        with open(con_texto, "w", encoding="utf-8") as f:
            f.write(texto)
        salidas.append(con_texto)
    except Exception:
        pass
    quiere_srt = subtitulos is True or str(subtitulos).strip().lower() in (
        "si", "true", "1", "yes", "subtitulos")
    if quiere_srt:
        try:
            con_srt = _sin_pisar(base + ".srt")
            with open(con_srt, "w", encoding="utf-8") as f:
                for i, tr in enumerate(trozos, 1):
                    f.write("%d\n%s --> %s\n%s\n\n"
                            % (i, _srt(tr.start), _srt(tr.end), tr.text.strip()))
            salidas.append(con_srt)
        except Exception:
            pass
    _apuntar("TRANSCRIBIR", ruta, "%d trozos" % len(trozos))
    duracion = trozos[-1].end if trozos else 0
    resumen = texto if len(texto) <= 4000 else texto[:4000] + " [...cortado...]"
    return ("Transcrito %s (%d minutos de audio):\n\n%s\n\nGuardado en: %s\n\n"
            "Resumeselo a Angel en dos frases; el texto entero lo tiene en el "
            "archivo." % (os.path.basename(ruta), int(duracion // 60), resumen,
                          ", ".join(salidas) or "(no he podido guardar el archivo)"))


def revisar_carpeta_de_medios(carpeta, hondo=False):
    """Un vistazo rapido: cuantas fotos y videos hay, de cuando y cuanto ocupan."""
    if not os.path.isdir(carpeta):
        return "No encuentro esa carpeta: %s" % carpeta
    hondo = hondo is True or str(hondo).strip().lower() in ("si", "true", "1")
    fotos = _listar(carpeta, FOTOS, hondo)
    videos = _listar(carpeta, VIDEOS, hondo)
    if not fotos and not videos:
        return "En esa carpeta no hay fotos ni videos."
    ocupa = 0
    fechas = []
    for r in (fotos + videos)[:MAX_ARCHIVOS]:
        try:
            ocupa += os.path.getsize(r)
            fechas.append(datetime.datetime.fromtimestamp(os.path.getmtime(r)))
        except Exception:
            pass
    partes = ["En %s%s hay:" % (carpeta, " (y sus subcarpetas)" if hondo else "")]
    partes.append("  %d fotos y %d videos" % (len(fotos), len(videos)))
    partes.append("  Ocupan en total %s" % _tamano(ocupa))
    if fechas:
        partes.append("  De %s a %s" % (min(fechas).strftime("%d/%m/%Y"),
                                        max(fechas).strftime("%d/%m/%Y")))
    if videos:
        mayor = max(videos, key=lambda r: os.path.getsize(r))
        partes.append("  El video mas gordo: %s (%s)"
                      % (os.path.basename(mayor), _tamano(os.path.getsize(mayor))))
    con_gps = 0
    for r in fotos[:40]:
        if _exif(r).get("gps"):
            con_gps += 1
    if con_gps:
        partes.append("  Al menos %d de las primeras 40 fotos traen coordenadas "
                      "de donde se tomaron." % con_gps)
    partes.append("")
    partes.append("Cuentaselo en dos frases y ofrecele ordenarlas por fecha si "
                  "estan revueltas.")
    return "\n".join(partes)
