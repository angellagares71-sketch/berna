# -*- coding: utf-8 -*-
r"""
Berna cantando. Tercera version, y la buena.

LAS DOS QUE NO FUNCIONARON, para no repetirlas
  1. Remuestrear cada silaba para subirle el tono. Mueve las formantes (voz de
     ardilla arriba, de ogro abajo) y no quita la entonacion de Piper. Se iba
     entre 100 y 350 cents de la nota. Angel: "una autentica porqueria".
  2. PSOLA silaba a silaba. Afinaba fino (7 cents de error medio) y AUN ASI
     sonaba mal. La leccion: **afinar no es cantar**. El fallo era sintetizar
     cada silaba SUELTA: Piper la dice como una palabra aislada, sobrearticulada
     y con su propio cierre, y pegar veinte de esas nunca suena a una frase.

LO QUE SE HACE AHORA
  Piper dice el VERSO ENTERO, natural, de una vez. Sobre esa frase se aplica
  una sola pasada de PSOLA con una curva de tono continua. Ventajas:
    - la coarticulacion es la de verdad (las silabas se enlazan solas)
    - no hay ni una costura, porque no se pega nada
    - las transiciones entre notas son un glissando suave, como una persona
    - las consonantes sordas se copian tal cual, sin tocarlas: pasar PSOLA por
      una "s" la vuelve un zumbido

  Las silabas se localizan en el audio por los PICOS DE ENERGIA de la parte
  sonora (cada vocal es un pico), no cortando el texto. Cada pico recibe su
  nota, y el tiempo se estira con una funcion continua a trozos que pasa por
  las fronteras de cada silaba: asi hay ritmo sin cortar nada.

  Las marcas de glotis se sacan de la senal FILTRADA alrededor del tono
  fundamental. Sobre la onda cruda los picos bailan y el PSOLA sale con fase
  inconsistente, que es lo que produce ese timbre metalico de robot.

SOBRE LAS CANCIONES DE OTROS
  Aqui no hay ninguna letra guardada, y no se debe anadir. Berna canta lo
  que le dicte Angel o lo que se invente el. Las melodias son escalas y
  arpegios, no son de nadie.
"""
import re, math, unicodedata

VOCALES = "aeiouáéíóúü"
FUERTES = "aeoáéó"
DIGRAFOS = ("ch", "ll", "rr")
GRUPOS = ("pr", "br", "tr", "dr", "cr", "gr", "fr",
          "pl", "bl", "cl", "gl", "fl")

MELODIAS = {
    "alegre":  [(0, 1), (0, 1), (4, 1), (4, 1), (5, 1), (4, 2), (2, 1), (0, 2)],
    "nana":    [(4, 1), (2, 1), (0, 2), (2, 1), (4, 1), (5, 2), (4, 3)],
    "triste":  [(0, 1), (3, 1), (7, 2), (5, 1), (3, 1), (2, 2), (0, 3)],
    "marcha":  [(0, 1), (0, 1), (7, 1), (7, 1), (9, 1), (7, 2), (5, 1), (4, 2)],
    "burlona": [(7, 1), (7, 1), (5, 1), (7, 1), (9, 1), (7, 2), (5, 2)],
    "escala":  [(0, 1), (2, 1), (4, 1), (5, 1), (7, 1), (9, 1), (11, 1), (12, 2)],
}
POR_DEFECTO = "alegre"

TONICA = 138.6            # re3, comoda para la voz masculina de Piper
VIBRATO_HZ = 5.4
VIBRATO_PROF = 0.30       # semitonos
GLISSANDO = 0.075         # segundos de transicion entre notas
SALTO = 0.005             # 5 ms de paso de analisis


def _sin_tildes(t):
    t = unicodedata.normalize("NFD", str(t or ""))
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower()


# ------------------------------------------------------------- las silabas
def _es_vocal(c):
    return c.lower() in VOCALES


def _nucleos_texto(p):
    fuera, i = [], 0
    while i < len(p):
        if _es_vocal(p[i]):
            j = i + 1
            while j < len(p) and _es_vocal(p[j]):
                if p[j - 1].lower() in FUERTES and p[j].lower() in FUERTES:
                    break
                j += 1
            fuera.append((i, j))
            i = j
        else:
            i += 1
    return fuera


def silabas(palabra):
    """Parte una palabra espanola en silabas. Sirve para contar, no para cortar."""
    p = palabra
    if len(p) < 2:
        return [p] if p else []
    nuc = _nucleos_texto(p)
    if len(nuc) <= 1:
        return [p]
    cortes = []
    for k in range(len(nuc) - 1):
        fin, ini = nuc[k][1], nuc[k + 1][0]
        entre = p[fin:ini]
        n = len(entre)
        if n <= 1:
            corte = fin
        elif n == 2:
            par = _sin_tildes(entre)
            corte = fin if (par in DIGRAFOS or par in GRUPOS) else fin + 1
        elif n == 3:
            par = _sin_tildes(entre[1:])
            corte = fin + 1 if (par in DIGRAFOS or par in GRUPOS) else fin + 2
        else:
            corte = fin + 2
        cortes.append(corte)
    trozos, ant = [], 0
    for c in cortes:
        trozos.append(p[ant:c])
        ant = c
    trozos.append(p[ant:])
    return [t for t in trozos if t]


def versos(letra):
    """La letra en versos; de cada verso, el texto y cuantas silabas tiene."""
    fuera = []
    for linea in str(letra or "").splitlines():
        palabras = re.findall(r"[0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+", linea)
        if not palabras:
            continue
        n = sum(len(silabas(w)) for w in palabras)
        fuera.append((" ".join(palabras), n))
    return fuera


# --------------------------------------------------------------- analisis
def _analizar(x, sr, np):
    """Tono, energia y si hay voz, trama a trama."""
    salto = max(1, int(SALTO * sr))
    ventana = int(0.040 * sr)
    lo, hi = int(sr / 400.0), int(sr / 70.0)
    f0, ene = [], []
    for i in range(0, max(1, len(x) - ventana), salto):
        seg = x[i:i + ventana]
        seg = seg - seg.mean()
        e = float(np.sqrt((seg ** 2).mean()))
        ene.append(e)
        if e < 90:
            f0.append(0.0)
            continue
        c = np.correlate(seg, seg, "full")[ventana - 1:]
        if c[0] <= 0 or hi >= len(c):
            f0.append(0.0)
            continue
        c = c / c[0]
        k = int(np.argmax(c[lo:hi])) + lo
        f0.append(sr / float(k) if c[k] > 0.32 else 0.0)
    return np.array(f0, np.float32), np.array(ene, np.float32), salto


def _picos_silabicos(ene, f0, cuantas, np):
    """Cada vocal es un bulto de energia sonora. Devuelve donde esta cada uno."""
    e = ene.copy()
    e[f0 <= 0] *= 0.25                       # lo sordo no es nucleo de silaba
    n = max(3, int(0.030 / SALTO))           # suavizado de 30 ms
    e = np.convolve(e, np.ones(n) / n, mode="same")
    if e.max() <= 0:
        return []
    e = e / e.max()

    picos = []
    for i in range(1, len(e) - 1):
        if e[i] >= e[i - 1] and e[i] > e[i + 1] and e[i] > 0.16:
            if picos and (i - picos[-1]) < int(0.070 / SALTO):
                if e[i] > e[picos[-1]]:      # dos picos pegados: el mas alto
                    picos[-1] = i
                continue
            picos.append(i)
    if not picos:
        return []

    # ajustar al numero de silabas que dice el texto
    while len(picos) > cuantas:               # fuera los mas flojos
        peor = min(range(len(picos)), key=lambda k: e[picos[k]])
        picos.pop(peor)
    while len(picos) < cuantas and len(picos) >= 1:
        # partir el hueco mas largo
        huecos = [(picos[k + 1] - picos[k], k) for k in range(len(picos) - 1)]
        if not huecos:
            break
        _, k = max(huecos)
        picos.insert(k + 1, (picos[k] + picos[k + 1]) // 2)
    return picos


def _marcas(x, sr, f0, salto, np):
    """Golpes de glotis, sacados de la senal filtrada al fundamental."""
    voz = f0[f0 > 0]
    medio = float(np.median(voz)) if len(voz) else 130.0

    # filtro paso banda alrededor del fundamental, por FFT
    n = 1
    while n < len(x):
        n *= 2
    X = np.fft.rfft(x, n)
    frec = np.fft.rfftfreq(n, 1.0 / sr)
    banda = np.exp(-0.5 * ((frec - medio) / (medio * 0.45)) ** 2)
    onda = np.fft.irfft(X * banda, n)[:len(x)]

    marcas = []
    i = int(0.002 * sr)
    while i < len(x) - 4:
        t = min(len(f0) - 1, i // salto)
        f = f0[t] if f0[t] > 0 else medio
        T = int(sr / max(70.0, min(400.0, f)))
        a, b = i + T // 2, min(len(x), i + (3 * T) // 2)
        if b <= a + 1:
            break
        j = a + int(np.argmax(onda[a:b]))
        marcas.append(j)
        i = j
    return marcas, medio


# ------------------------------------------------- curva de tono y de tiempo
def _a_trozos(entradas, salidas):
    """Funcion continua a trozos que pasa por los puntos dados."""
    def f(t):
        if t <= salidas[0]:
            return entradas[0] + (t - salidas[0])
        for k in range(len(salidas) - 1):
            if t <= salidas[k + 1]:
                d = salidas[k + 1] - salidas[k]
                if d <= 0:
                    return entradas[k]
                r = (t - salidas[k]) / d
                return entradas[k] + r * (entradas[k + 1] - entradas[k])
        return entradas[-1] + (t - salidas[-1])
    return f


def _curva_tono(notas, bordes_sal, sr):
    """El tono que debe sonar en cada instante: notas planas unidas con glissando."""
    gl = GLISSANDO

    def f(seg):
        # en que nota estamos
        k = 0
        for i in range(len(bordes_sal) - 1):
            if seg >= bordes_sal[i]:
                k = i
        f_act = notas[k]
        # transicion suave hacia la siguiente
        fin = bordes_sal[k + 1] if k + 1 < len(bordes_sal) else None
        if fin is not None and k + 1 < len(notas) and seg > fin - gl:
            r = (seg - (fin - gl)) / gl
            r = r * r * (3 - 2 * r)                 # suavizado
            f_act = f_act * (1 - r) + notas[k + 1] * r
        desvio = 0.0
        dentro = seg - bordes_sal[k]
        entra = min(1.0, dentro / 0.25)
        desvio += VIBRATO_PROF * entra * math.sin(2 * math.pi * VIBRATO_HZ * seg)
        if k == 0:                                   # ataque del verso
            desvio += -0.8 * math.exp(-seg / 0.06)
        return f_act * (2.0 ** (desvio / 12.0))
    return f


# ------------------------------------------------------------------- PSOLA
def _psola(x, sr, marcas, f_obj, n_sal, mapa, f0, salto, np):
    """Una sola pasada sobre el verso entero."""
    if len(marcas) < 4:
        return None
    marcas = np.asarray(marcas, np.int64)
    periodos = np.diff(marcas)
    periodos = np.concatenate([periodos, periodos[-1:]])
    y = np.zeros(n_sal + sr // 2, np.float32)
    sordo = int(0.006 * sr)

    t = 0.0
    while t < n_sal:
        s = mapa(t)
        if s < 0 or s >= len(x) - 2:
            break
        tr = min(len(f0) - 1, int(s) // salto)
        hay_voz = f0[tr] > 0

        if hay_voz:
            paso = max(4.0, sr / max(60.0, min(600.0, f_obj(t / float(sr)))))
            k = max(0, min(len(marcas) - 1, int(np.searchsorted(marcas, s))))
            centro, L = int(marcas[k]), max(4, int(periodos[k]))
            gan = max(0.4, min(2.2, paso / float(L)))
        else:
            # lo sordo se copia tal cual: pasarle PSOLA lo vuelve un zumbido
            paso, centro, L, gan = float(sordo), int(s), sordo, 1.0

        a, b = centro - L, centro + L
        if a < 0 or b > len(x):
            t += paso
            continue
        grano = x[a:b] * np.hanning(2 * L) * gan
        c = int(t)
        ini, fin = c - L, c + L
        if ini < 0:
            grano, ini = grano[-ini:], 0
        if fin > len(y):
            grano, fin = grano[:len(y) - ini], len(y)
        if fin > ini:
            y[ini:fin] += grano[:fin - ini]
        t += paso
    return y[:n_sal]


# ------------------------------------------------------------------ cantar
def _cantar_verso(texto, n_silabas, patron, tono, compas, voz, np, cfg):
    from_piper = []
    sr = 22050
    for ch in voz.synthesize(texto, syn_config=cfg):
        from_piper.append(ch.audio_int16_array)
        sr = ch.sample_rate
    if not from_piper:
        return None, sr
    x = np.concatenate(from_piper).astype(np.float32)

    # fuera el silencio de los bordes
    e = np.abs(x)
    fuertes = np.nonzero(e > max(e.max() * 0.03, 1.0))[0]
    if len(fuertes) > 2:
        x = x[max(0, fuertes[0] - int(0.005 * sr)):
              min(len(x), fuertes[-1] + int(0.010 * sr))]

    f0, ene, salto = _analizar(x, sr, np)
    picos = _picos_silabicos(ene, f0, n_silabas, np)
    if len(picos) < 1:
        return None, sr

    # fronteras de cada silaba en la entrada: a mitad de camino entre picos
    bordes_ent = [0.0]
    for k in range(len(picos) - 1):
        bordes_ent.append((picos[k] + picos[k + 1]) / 2.0 * salto)
    bordes_ent.append(len(x) / float(sr))

    # notas y duraciones que pide la melodia
    notas, duras = [], []
    for i in range(len(picos)):
        semis, tiempos = patron[i % len(patron)]
        if i == len(picos) - 1:
            tiempos = max(tiempos, 2)
        notas.append(TONICA * (2.0 ** ((semis + tono) / 12.0)))
        duras.append(compas * tiempos)

    # fronteras en la salida, y que no se estire mas de la cuenta
    bordes_sal = [0.0]
    for i, d in enumerate(duras):
        natural = bordes_ent[i + 1] - bordes_ent[i]
        d = max(natural * 0.55, min(natural * 3.2, d))
        bordes_sal.append(bordes_sal[-1] + d)

    n_sal = int(bordes_sal[-1] * sr)
    mapa = _a_trozos([b * sr for b in bordes_ent], [b * sr for b in bordes_sal])
    marcas, _ = _marcas(x, sr, f0, salto, np)
    y = _psola(x, sr, marcas, _curva_tono(notas, bordes_sal, sr),
               n_sal, mapa, f0, salto, np)
    return y, sr


def cantar(letra, melodia=POR_DEFECTO, tono=0, compas=0.40,
           reproducir=None, voz=None):
    """Canta la letra que le den. Devuelve texto contando como fue."""
    try:
        import numpy as np
    except Exception:
        return "No tengo numpy, no puedo cantar."
    if voz is None:
        return ("Todavia no tengo la voz cargada, dile a Angel que espere unos "
                "segundos y me lo vuelva a pedir.")

    letra = str(letra or "").strip()
    if not letra:
        return "Dime que quieres que cante."
    if len(letra) > 1200:
        return "Eso es larguisimo, dame como mucho unos cuantos versos."

    m = _sin_tildes(melodia).strip()
    patron = MELODIAS.get(m)
    if patron is None:
        patron, m = MELODIAS[POR_DEFECTO], POR_DEFECTO
    try:
        tono = max(-7, min(7, int(float(tono))))
    except Exception:
        tono = 0
    try:
        compas = max(0.22, min(0.9, float(compas)))
    except Exception:
        compas = 0.40

    lineas = versos(letra)
    if not lineas:
        return "No he encontrado ninguna palabra que cantar ahi."
    if sum(n for _, n in lineas) > 110:
        return "Eso son demasiadas silabas, dame una estrofa o dos."

    from piper import SynthesisConfig
    cfg = SynthesisConfig(length_scale=1.1, noise_scale=0.4, noise_w_scale=0.45)
    piezas, sr = [], 22050
    for texto, n in lineas:
        try:
            y, sr = _cantar_verso(texto, n, patron, tono, compas, voz, np, cfg)
        except Exception as e:
            return "Se me ha atragantado la voz cantando: %s" % e
        if y is None:
            continue
        piezas.append(y)
        piezas.append(np.zeros(int(sr * compas * 0.8), np.float32))

    if not piezas:
        return "No me ha salido ni una nota, algo ha ido mal."
    cancion = np.concatenate(piezas)
    pico = float(np.max(np.abs(cancion)) or 1.0)
    cancion = (cancion / pico * 24000.0).astype(np.int16)

    if reproducir is None:
        return "No tengo por donde sacar el sonido ahora mismo."
    reproducir(cancion, sr)
    return ("Ya lo estoy cantando (melodia '%s', %d versos, %.0f segundos). "
            "Angel lo esta oyendo, asi que NO repitas la letra por escrito: "
            "comenta en una frase corta y con humor que tal ha quedado."
            % (m, len(lineas), len(cancion) / float(sr)))


def melodias_disponibles():
    """Que melodias sabe. Sin letra: la letra la pone Angel."""
    return ("Melodias que se: %s.\n\nLa letra la pones tu: dictamela y la canto, "
            "o me la invento yo si me dices de que va. No tengo canciones de "
            "otros guardadas.\n\nEjemplos de lo que te puede pedir Angel: "
            "'cantame algo', 'inventate una cancion sobre el gato', 'canta esto "
            "con la melodia triste', 'cantalo mas grave'."
            % ", ".join(sorted(MELODIAS)))
