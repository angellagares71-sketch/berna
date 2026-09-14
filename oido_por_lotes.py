# -*- coding: utf-8 -*-
"""Escucha notas de voz por tandas en un proceso aparte.

movil.py lanza este programa para cada tanda de audios de un chat de WhatsApp y
lo deja cerrarse al terminar. Asi la memoria que va acumulando Whisper (la
libreria de calculo MKL no la devuelve) se libera en cada tanda, y un chat con
miles de audios no deja al ordenador sin RAM. Asi murio la primera lectura de
un chat de 1.204 audios el 13/09/2026: "mkl_malloc: failed to allocate memory".

Uso:  python oido_por_lotes.py <carpeta_con_audios> <modelo> <obreros>
Escribe por la salida una linea JSON por audio:
    {"archivo": "...", "texto": "..."}   o   {"archivo": "...", "error": "..."}
"""
import json
import os
import sys

os.environ.setdefault("MKL_DISABLE_FAST_MM", "1")   # que MKL no se guarde la memoria

from concurrent.futures import ThreadPoolExecutor  # noqa: E402


def main():
    carpeta, tam, obreros = sys.argv[1], sys.argv[2], max(1, int(sys.argv[3]))
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    from faster_whisper import WhisperModel
    hilos = max(2, (os.cpu_count() or 6) // obreros)
    modelo = WhisperModel(tam, device="cpu", compute_type="int8",
                          cpu_threads=hilos, num_workers=obreros)
    archivos = sorted(os.listdir(carpeta))

    def uno(nombre):
        ruta = os.path.join(carpeta, nombre)
        try:
            segmentos, _info = modelo.transcribe(
                ruta, language="es", beam_size=1, vad_filter=True,
                condition_on_previous_text=False, without_timestamps=True)
            return {"archivo": nombre, "texto": " ".join(s.text.strip() for s in segmentos).strip()}
        except Exception as e:
            return {"archivo": nombre, "error": str(e)[:200]}

    with ThreadPoolExecutor(max_workers=obreros) as pool:
        for resultado in pool.map(uno, archivos):
            sys.stdout.write(json.dumps(resultado, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
