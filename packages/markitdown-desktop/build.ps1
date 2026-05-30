$ErrorActionPreference = "Stop"
$PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$TesseractRoot = Join-Path $PackageRoot "resources\tesseract"
$Checksums = Join-Path $TesseractRoot "checksums.sha256"
$RequirementsLock = Join-Path $PackageRoot "approved-requirements.lock"
$BuildVenv = Join-Path $PackageRoot ".build-venv"
$Python = Join-Path $BuildVenv "Scripts\python.exe"
Set-Location $PackageRoot

if (-not (Test-Path $Python -PathType Leaf)) {
    python -m venv $BuildVenv
}

foreach ($requiredFile in @(
    "tesseract.exe",
    "tessdata\por.traineddata",
    "tessdata\eng.traineddata"
)) {
    if (-not (Test-Path (Join-Path $TesseractRoot $requiredFile) -PathType Leaf)) {
        throw "Arquivo Tesseract obrigatorio ausente: $requiredFile"
    }
}

$entries = Get-Content $Checksums | Where-Object {
    $_.Trim() -and -not $_.Trim().StartsWith("#")
}
if (-not $entries) {
    throw "resources\tesseract\checksums.sha256 nao contem binarios aprovados."
}
foreach ($entry in $entries) {
    $parts = $entry.Trim() -split "\s+", 2
    $expected = $parts[0].ToLowerInvariant()
    $relativePath = $parts[1].Trim()
    $path = Join-Path $TesseractRoot $relativePath
    if (-not (Test-Path $path -PathType Leaf)) {
        throw "Arquivo Tesseract ausente: $relativePath"
    }
    $actual = (Get-FileHash -Algorithm SHA256 $path).Hash.ToLowerInvariant()
    if ($actual -ne $expected) {
        throw "Checksum divergente: $relativePath"
    }
}

$lockedRequirements = Get-Content $RequirementsLock | Where-Object {
    $_.Trim() -and -not $_.Trim().StartsWith("#")
}
if (-not $lockedRequirements) {
    throw "approved-requirements.lock nao contem dependencias aprovadas."
}

& $Python -m pip install --require-hashes -r $RequirementsLock
& $Python -m pip install --no-deps -e (Join-Path $PackageRoot "..\markitdown")
& $Python -m pip install --no-deps -e $PackageRoot
& $Python -m unittest discover -s (Join-Path $PackageRoot "tests") -v
& $Python -m PyInstaller --noconfirm --clean --onedir --windowed `
    --name "PDF para Markdown" `
    --collect-data "magika" `
    --add-data "$TesseractRoot;resources\tesseract" `
    --add-data "$(Join-Path $PackageRoot 'PRIVACY.md');." `
    --add-data "$(Join-Path $PackageRoot 'THIRD-PARTY-NOTICES.md');." `
    --add-data "$(Join-Path $PackageRoot '..\..\LICENSE');licenses\markitdown" `
    --add-data "$(Join-Path $PackageRoot '..\markitdown\ThirdPartyNotices.md');licenses\markitdown" `
    (Join-Path $PackageRoot "launch.py")

$isccCandidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)
$iscc = $isccCandidates | Where-Object { Test-Path $_ -PathType Leaf } |
    Select-Object -First 1
if (-not $iscc) {
    throw "Inno Setup 6 nao encontrado."
}
& $iscc (Join-Path $PackageRoot "installer.iss")
