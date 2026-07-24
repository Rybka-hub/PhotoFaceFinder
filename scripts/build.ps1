$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$modelDir = Join-Path $projectRoot "resources\models"
$yunet = Join-Path $modelDir "face_detection_yunet_2023mar.onnx"
$sface = Join-Path $modelDir "face_recognition_sface_2021dec.onnx"

if (-not (Test-Path -LiteralPath $venvPython)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        py -3.12 -m venv (Join-Path $projectRoot ".venv")
    }
    elseif (Get-Command python -ErrorAction SilentlyContinue) {
        python -m venv (Join-Path $projectRoot ".venv")
    }
    else {
        throw "Nie znaleziono Pythona 3.12. Zainstaluj go przed budowaniem projektu."
    }
}

& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $projectRoot "requirements.lock.txt")

New-Item -ItemType Directory -Force -Path $modelDir | Out-Null
if (-not (Test-Path -LiteralPath $yunet)) {
    Invoke-WebRequest `
        -Uri "https://huggingface.co/opencv/face_detection_yunet/resolve/main/face_detection_yunet_2023mar.onnx?download=true" `
        -OutFile $yunet
}
if (-not (Test-Path -LiteralPath $sface)) {
    Invoke-WebRequest `
        -Uri "https://huggingface.co/opencv/face_recognition_sface/resolve/main/face_recognition_sface_2021dec.onnx?download=true" `
        -OutFile $sface
}

$expectedYunet = "8F2383E4DD3CFBB4553EA8718107FC0423210DC964F9F4280604804ED2552FA4"
$expectedSface = "0BA9FBFA01B5270C96627C4EF784DA859931E02F04419C829E83484087C34E79"
if ((Get-FileHash $yunet -Algorithm SHA256).Hash -ne $expectedYunet) {
    throw "Nieprawidłowa suma kontrolna modelu YuNet."
}
if ((Get-FileHash $sface -Algorithm SHA256).Hash -ne $expectedSface) {
    throw "Nieprawidłowa suma kontrolna modelu SFace."
}

Push-Location $projectRoot
try {
    $env:PYTHONPATH = "src"
    & $venvPython -m pytest
    & $venvPython -m PyInstaller --noconfirm --clean PhotoFaceFinder.spec
    $distEnv = Join-Path $projectRoot "dist\.env"
    if (-not (Test-Path -LiteralPath $distEnv)) {
        Copy-Item -LiteralPath (Join-Path $projectRoot ".env.example") -Destination $distEnv
    }
}
finally {
    Pop-Location
}

Write-Host "Gotowy plik: $projectRoot\dist\PhotoFaceFinder.exe"
