@echo off
REM ---------------------------------------------------------------------
REM  Deja la carpeta "Instalar Berna" del escritorio con la ultima version.
REM
REM  Lo llama solo Claude Code al terminar de trabajar (un enganche de tipo
REM  Stop en C:\Users\alaga\.claude\settings.json), para que Angel nunca se
REM  lleve al pen una version vieja. Tambien se puede pinchar a mano.
REM
REM  La hora que se apunta arriba del registro sirve para comprobar de un
REM  vistazo si el enganche esta saltando de verdad.
REM
REM  Sale SIEMPRE con codigo 0: si algo falla, se apunta en el registro
REM  pero no se corta la sesion de Claude por esto.
REM ---------------------------------------------------------------------
if not exist "C:\Asistente\instalador.py" exit /b 0
if not exist "C:\Asistente\venv\Scripts\python.exe" exit /b 0
if not exist "C:\Asistente\tareas" mkdir "C:\Asistente\tareas"
echo Ultima sincronizacion: %date% %time% > "C:\Asistente\tareas\sincronizacion.log"
"C:\Asistente\venv\Scripts\python.exe" "C:\Asistente\instalador.py" >> "C:\Asistente\tareas\sincronizacion.log" 2>&1
exit /b 0
