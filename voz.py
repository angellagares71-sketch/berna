# -*- coding: utf-8 -*-
"""La voz de Sobri. Neuronal si hay internet, Piper si no.

POR QUE (01-09-2026): Piper suena a robot. Es rapido y funciona sin internet,
y por eso SIGUE SIENDO EL RESPALDO y no se quita, pero las voces "medium" que
hay descargadas tienen entonacion plana y se nota a la legua que es una maquina.
Las voces neuronales de Microsoft (las mismas que usan los asistentes de
verdad) respiran, entonan y hacen pausas donde las haria una persona.

COMO ENCAJA SIN TOCAR NADA MAS: esta clase imita la interfaz de Piper. Devuelve
trozos con `.audio_int16_array` y `.sample_rate`, que es lo que `_bucle_voz` ya
sabe reproducir. Se cambia el motor y el resto de Sobri ni se entera.

EL ACENTO AHORA ES DE VERDAD: antes "ponte mexicano" cargaba una voz mexicana
de Piper y para el resto de paises no habia nada. Microsoft tiene voz masculina
en 22 paises hispanohablantes, asi que el argentino suena argentino.
"""

import io
import asyncio

# Cada acento de estilos.py con su voz. Los de España comparten la de España:
# el andaluz o el gallego no son otro idioma, son la misma voz con otra forma
# de hablar, y de eso ya se encarga el prompt.
VOCES = {
    "neutro": "es-ES-AlvaroNeural",
    "andaluz": "es-ES-AlvaroNeural",
    "gallego": "es-ES-AlvaroNeural",
    "catalan": "es-ES-AlvaroNeural",
    "vasco": "es-ES-AlvaroNeural",
    "canario": "es-ES-AlvaroNeural",
    "madrileno": "es-ES-AlvaroNeural",
    "mexicano": "es-MX-JorgeNeural",
    "argentino": "es-AR-TomasNeural",
    "uruguayo": "es-UY-MateoNeural",
    "cubano": "es-CU-ManuelNeural",
    "colombiano": "es-CO-GonzaloNeural",
    "venezolano": "es-VE-SebastianNeural",
    "chileno": "es-CL-LorenzoNeural",
    "peruano": "es-PE-AlexNeural",
}
POR_DEFECTO = "es-ES-AlvaroNeural"


def voz_para_acento(acento):
    return VOCES.get((acento or "").strip().lower(), POR_DEFECTO)


class _Trozo(object):
    """Lo mismo que devuelve Piper, para que _bucle_voz no note el cambio."""
    __slots__ = ("audio_int16_array", "sample_rate")

    def __init__(self, arr, sr):
        self.audio_int16_array = arr
        self.sample_rate = sr


class VozNeural(object):
    def __init__(self, nombre=POR_DEFECTO):
        self.nombre = nombre

    @staticmethod
    def _ritmo(ajustes):
        """La velocidad del acento, traducida a lo que entiende Microsoft.

        Piper usa `length_scale`: por debajo de 1 habla mas rapido. Aqui se pide
        en porcentaje. Se limita a +-30% porque mas alla suena a dibujos.
        """
        escala = getattr(ajustes, "length_scale", None) or 1.0
        try:
            pct = int(round((1.0 / float(escala) - 1.0) * 100))
        except Exception:
            pct = 0
        pct = max(-30, min(30, pct))
        return ("+%d%%" % pct) if pct >= 0 else ("%d%%" % pct)

    def _bajar(self, texto, ritmo):
        import edge_tts

        async def traer():
            trozos = []
            # La voz espanola disponible es adulta. Al subir el tono sin
            # acelerar demasiado conserva claridad y adquiere timbre infantil.
            # Las voces de otros paises mantienen su tono natural.
            tono = "+48Hz" if self.nombre.startswith("es-ES-") else "-2Hz"
            com = edge_tts.Communicate(
                texto, self.nombre, rate=ritmo, pitch=tono)
            async for m in com.stream():
                if m["type"] == "audio":
                    trozos.append(m["data"])
            return b"".join(trozos)

        try:
            bucle = asyncio.new_event_loop()
            try:
                return bucle.run_until_complete(traer())
            finally:
                bucle.close()
        except Exception:
            return b""

    def synthesize(self, texto, ajustes=None, syn_config=None):
        """Devuelve el audio ya en crudo, listo para sonar.

        Acepta `syn_config` porque asi la llama `cantar.py`, que espera la
        firma de Piper. Sin esto reventaba con un TypeError y Sobri decia
        que no sabia cantar.
        """
        ajustes = ajustes if ajustes is not None else syn_config
        texto = (texto or "").strip()
        if not texto:
            return
        crudo = self._bajar(texto, self._ritmo(ajustes))
        if not crudo:
            raise RuntimeError("la voz neuronal no ha devuelto audio")
        import av
        import numpy as np
        cont = av.open(io.BytesIO(crudo))
        remuestreador = av.audio.resampler.AudioResampler(
            format="s16", layout="mono", rate=24000)
        partes = []
        for cuadro in cont.decode(audio=0):
            for salida in remuestreador.resample(cuadro):
                arr = salida.to_ndarray().reshape(-1).astype(np.int16)
                if arr.size:
                    partes.append(arr)
        cont.close()
        if not partes:
            raise RuntimeError("el audio venia vacio")
        # UN SOLO TROZO, y esto importa: Sobri hace sd.play() + sd.wait() con
        # cada trozo que le des. Descodificando se sacan 225 fotogramas para
        # cinco segundos, y devolverlos sueltos era abrir y cerrar el altavoz
        # 225 veces: se oia entrecortado o no se oia. Piper devuelve pocos y
        # gordos, y aqui hay que hacer lo mismo.
        yield _Trozo(np.concatenate(partes), 24000)


def probar(nombre=POR_DEFECTO, texto="Probando la voz nueva."):
    """Devuelve (segundos_de_audio, milisegundos_que_ha_tardado) o revienta."""
    import time
    t0 = time.time()
    total = 0
    for ch in VozNeural(nombre).synthesize(texto):
        total += len(ch.audio_int16_array)
    return total / 24000.0, int((time.time() - t0) * 1000)


class VozConRespaldo(object):
    """La neuronal, y si falla, Piper. Sin que Sobri se quede muda nunca.

    El respaldo NO es un adorno: el kit de instalacion presume de funcionar sin
    internet, y ademas Microsoft puede cortar o tardar. Si la neuronal falla una
    vez se avisa y se sigue con ella; si falla tres seguidas, se pasa a Piper y
    ya no se vuelve a intentar hasta el siguiente arranque, para no meter dos
    segundos de espera en cada frase.
    """

    FALLOS_PARA_RENDIRSE = 3

    def __init__(self, nombre_neural, piper=None, avisar=None):
        self.neural = VozNeural(nombre_neural)
        self.piper = piper
        self.avisar = avisar or (lambda _t: None)
        self.fallos = 0
        self.rendida = False

    @property
    def nombre(self):
        return self.neural.nombre

    def cambiar_a(self, nombre):
        if nombre and nombre != self.neural.nombre:
            self.neural = VozNeural(nombre)

    def synthesize(self, texto, ajustes=None, syn_config=None):
        # CANTAR VA POR PIPER, a proposito. `cantar.py` llama con
        # `syn_config=` y ademas manosea el audio despues: le cambia el
        # tono, lo estira y lo encaja en el compas. Eso se afino con la voz
        # plana de Piper. La neuronal ya viene con su propia entonacion, y
        # estirar algo que ya entona suena a muneco roto. Ademas cantar
        # trocea el verso en muchas llamadas cortas: por internet serian
        # decenas de viajes y una espera larguisima.
        if syn_config is not None and self.piper is not None:
            for ch in self.piper.synthesize(texto, syn_config=syn_config):
                yield ch
            return
        if not self.rendida:
            try:
                hubo = False
                for ch in self.neural.synthesize(texto, ajustes):
                    hubo = True
                    yield ch
                if hubo:
                    self.fallos = 0
                    return
                raise RuntimeError("sin audio")
            except Exception as e:
                # Si falta el modulo, reintentar no va a arreglarlo nunca: eso le
                # pasa a quien actualice y no tenga edge-tts instalado, y no hay
                # que hacerle esperar tres veces para nada.
                if isinstance(e, ImportError):
                    self.rendida = True
                    self.avisar("sin edge-tts instalado; hablo con Piper")
                else:
                    self.fallos += 1
                    self.avisar("voz neuronal fallo (%d de %d): %s"
                                % (self.fallos, self.FALLOS_PARA_RENDIRSE, str(e)[:60]))
                if not self.rendida and self.fallos >= self.FALLOS_PARA_RENDIRSE:
                    self.rendida = True
                    self.avisar("me quedo con Piper hasta el proximo arranque")
        if self.piper is not None:
            for ch in self.piper.synthesize(texto, ajustes):
                yield ch
