@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
	".venv\Scripts\python.exe" -m assistant.cli --voice --speak
) else (
	python -m assistant.cli --voice --speak
)
pause
