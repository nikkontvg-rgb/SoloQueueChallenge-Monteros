@echo off
setlocal
cd /d "%~dp0"
echo === Construccion del agente SoloQ Challenge Monteros ===
where py >nul 2>nul
if errorlevel 1 (
  echo No se encontro Python. Instala Python 3.11 o 3.12 desde python.org y marca "Add Python to PATH".
  pause
  exit /b 1
)
py -m pip install --upgrade pip
py -m pip install -r requirements-agente.txt
if errorlevel 1 goto error
py -m PyInstaller --noconfirm --clean --windowed --onefile --name SoloQChallengeAgente agente_windows.py
if errorlevel 1 goto error
echo.
echo EXE creado en dist\SoloQChallengeAgente.exe
echo Para crear el instalador completo, instala Inno Setup y ejecuta:
echo ISCC.exe installer\SoloQChallenge.iss
pause
exit /b 0
:error
echo Hubo un error al construir el programa.
pause
exit /b 1
