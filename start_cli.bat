@echo off
REM Get the project directory (parent of this script's location if in Startup, else use this directory)
if "%~dp0"=="%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\" (
	cd /d "D:\Assistant"
) else (
	cd /d "%~dp0"
)

REM Use absolute path to python from venv
if exist "D:\Assistant\.venv\Scripts\python.exe" (
	"D:\Assistant\.venv\Scripts\python.exe" -m assistant.cli
) else if exist ".venv\Scripts\python.exe" (
	".venv\Scripts\python.exe" -m assistant.cli
) else (
	python -m assistant.cli
)
pause
