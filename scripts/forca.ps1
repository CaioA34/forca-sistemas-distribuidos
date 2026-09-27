param(
    [Parameter(Position=0)]
    [ValidateSet('servidor', 'cliente', 'testes')]
    [string]$Modo = 'servidor',
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$Opcoes
)

$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$pythonExecutable = $env:FORCA_PYTHON
$pythonPrefix = @()
if (-not $pythonExecutable -and (Test-Path -LiteralPath (Join-Path $taskRoot '.venv/Scripts/python.exe'))) {
    $pythonExecutable = Join-Path $taskRoot '.venv/Scripts/python.exe'
}
if (-not $pythonExecutable) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand -and $pythonCommand.Source -notlike '*WindowsApps*') {
        $pythonExecutable = $pythonCommand.Source
    }
}
if (-not $pythonExecutable) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $pythonExecutable = 'py'
        $pythonPrefix = @('-3')
    } else {
        throw 'Instale Python 3.12+ ou configure FORCA_PYTHON com o caminho do executável.'
    }
}

Push-Location -LiteralPath $taskRoot
try {
    switch ($Modo) {
        'servidor' { & $pythonExecutable @pythonPrefix servidor.py @Opcoes }
        'cliente' { & $pythonExecutable @pythonPrefix cliente.py @Opcoes }
        'testes' { & $pythonExecutable @pythonPrefix -m unittest discover -s tests -v @Opcoes }
    }
    exit $LASTEXITCODE
} finally {
    Pop-Location
}

