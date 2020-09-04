""" APP TRANSPORTADOR : """
$GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"
$GET_PIP_PATH = "C:\get-pip.py"

function InstallPip ($python_home) {
    $pip_path = $python_home + "/Scripts/pip.exe"
    $python_path = $python_home + "/python.exe"
    if (-not (Test-Path $pip_path)) {
        Write-Host "Instalando pip..."
        if (-not (Test-Path $GET_PIP_PATH)) {
            $webclient = New-Object System.Net.WebClient
            $webclient.DownloadFile($GET_PIP_URL, $GET_PIP_PATH)
        }
        Write-Host "Ejecutando:" $python_path $GET_PIP_PATH
        Start-Process -FilePath "$python_path" -ArgumentList "$GET_PIP_PATH" -Wait
    } else {
        Write-Host "pip esta instalado y listo."
    }
}

InstallPip $env:PYTHON

# Instale los requisitos de desarrollo (solo necesitamos algunos de estos,
# pero no se preocupe por eso por ahora)
& ($env:PYTHON + "/Scripts/pip.exe") install -r requisitos-desarrollo.txt
