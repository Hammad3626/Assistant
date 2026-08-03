@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
	".venv\Scripts\python.exe" -m assistant.cli
) else (
	python -m assistant.cli
)
pause
