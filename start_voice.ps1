Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $python) {
	& $python -m assistant.cli --voice --speak
} else {
	python -m assistant.cli --voice --speak
}
