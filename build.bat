@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>&1
if %errorlevel%==0 (
    set "PYLAUNCH=py -3"
) else (
    set "PYLAUNCH=python"
)

call %PYLAUNCH% -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
call %PYLAUNCH% -m PyInstaller --noconfirm --windowed --name Modulador --paths . --collect-all customtkinter --collect-all sounddevice app\main.py
if errorlevel 1 exit /b 1
echo.
echo Listo: dist\Modulador\Modulador.exe
echo En FiveM el microfono es el otro extremo del cable, normalmente CABLE Output.
endlocal
