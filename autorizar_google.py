# -*- coding: utf-8 -*-
"""Abre el navegador para que Angel autorice a Berna en su cuenta de Google."""
import sys, os
sys.path.insert(0, r"C:\Asistente")
import cuentas as C

print("Abriendo el navegador para autorizar...")
try:
    creds = C._credenciales()
    print("AUTORIZADO CORRECTAMENTE")
    print("Token guardado en:", C.TOKEN)
except Exception as e:
    print("FALLO:", e)
