# Downloads whisper.cpp (prebuilt Windows binary) and the English "base" model into .\whisper
# Run from PowerShell:   powershell -ExecutionPolicy Bypass -File .\setup_whisper.ps1
$ErrorActionPreference = "Stop"
$root   = Join-Path $PSScriptRoot "whisper"
$models = Join-Path $root "models"
New-Item -ItemType Directory -Force -Path $root, $models | Out-Null

$zip = Join-Path $root "whisper-bin-x64.zip"
$binUrl = "https://github.com/ggml-org/whisper.cpp/releases/latest/download/whisper-bin-x64.zip"
Write-Host "Downloading whisper.cpp binaries..."
Invoke-WebRequest -Uri $binUrl -OutFile $zip
$tmp = Join-Path $root "_unzip"
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
Expand-Archive -Path $zip -DestinationPath $tmp -Force

# The zip may nest files in a Release\ folder; copy the exe and its DLLs next to each other.
$cli = Get-ChildItem -Path $tmp -Recurse -Filter "whisper-cli.exe" | Select-Object -First 1
if (-not $cli) { throw "whisper-cli.exe not found in the download. Get it manually from https://github.com/ggml-org/whisper.cpp/releases" }
Copy-Item -Path (Join-Path $cli.DirectoryName "*") -Destination $root -Recurse -Force
Remove-Item $tmp -Recurse -Force
Remove-Item $zip -Force

$modelPath = Join-Path $models "ggml-base.en.bin"
if (-not (Test-Path $modelPath)) {
    Write-Host "Downloading Whisper model (about 150 MB)..."
    Invoke-WebRequest -Uri "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin" -OutFile $modelPath
}
Write-Host "Done. whisper.cpp is ready in $root"
