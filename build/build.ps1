# Construction reproductible de Mat & Méthode (Windows 11 64 bits, Python 3.12 64 bits ; 3.13 accepté).
#   powershell -ExecutionPolicy Bypass -File build\build.ps1
# Résultat : build\dist\MatMethode_1.0\  (MatMethode.exe + _internal\), à déposer tel quel sur SharePoint.
$ErrorActionPreference = "Stop"
$Racine = Split-Path -Parent $PSScriptRoot
Set-Location $Racine

# Python 3.12 conseillé ; 3.13 accepté. On cherche avec le lanceur « py », puis « python ».
$Python = $null
foreach ($v in @("3.12", "3.13")) {
    try { & py "-$v" -c "import sys" 2>$null; if ($LASTEXITCODE -eq 0) { $Python = @("py", "-$v"); break } } catch { }
}
if (-not $Python) {
    try {
        $ver = & python -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and @("3.12", "3.13") -contains $ver) { $Python = @("python") }
    } catch { }
}
if (-not $Python) {
    Write-Host ""
    Write-Host "Python 3.12 (64 bits) est introuvable sur ce PC." -ForegroundColor Red
    Write-Host "Installez-le depuis https://www.python.org/downloads/windows/ (« Windows installer (64-bit) »)," -ForegroundColor Red
    Write-Host "en cochant « Add python.exe to PATH », puis relancez ce script dans une NOUVELLE fenêtre PowerShell." -ForegroundColor Red
    exit 1
}
Write-Host "Python utilisé : $($Python -join ' ')"

Write-Host "1/5 Environnement virtuel propre (.venv-build)"
if (Test-Path .venv-build) { Remove-Item -Recurse -Force .venv-build }
$PyCmd = $Python[0]
$PyArgs = @($Python | Select-Object -Skip 1) + @("-m", "venv", ".venv-build")
& $PyCmd @PyArgs
$Py = Join-Path $Racine ".venv-build\Scripts\python.exe"
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $Py)) { throw "Création de l'environnement virtuel impossible" }

Write-Host "2/5 Dépendances"
& $Py -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Mise à jour de pip impossible (connexion internet ?)" }
& $Py -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "pip install a échoué" }

Write-Host "3/5 Tests"
$env:QT_QPA_PLATFORM = "offscreen"
& $Py -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Les tests ont échoué : construction arrêtée" }
Remove-Item Env:\QT_QPA_PLATFORM

Write-Host "4/5 PyInstaller (--onedir --windowed)"
& $Py -m PyInstaller --noconfirm --clean --distpath build\dist --workpath build\work build\MatMethode.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller a échoué" }

Write-Host "5/5 Empreinte SHA-256"
$Dossier = Get-ChildItem build\dist -Directory | Where-Object { $_.Name -like "MatMethode_*" } | Select-Object -First 1
$Exe = Join-Path $Dossier.FullName "MatMethode.exe"
$Hash = (Get-FileHash $Exe -Algorithm SHA256).Hash
"$Hash  MatMethode.exe" | Out-File -Encoding ascii (Join-Path $Dossier.FullName "MatMethode.exe.sha256")
Write-Host ""
Write-Host "Terminé : $($Dossier.FullName)"
Write-Host "SHA-256 : $Hash"
Write-Host "Copier ce dossier sur SharePoint. Le dossier donnees\ (s'il existe déjà) est conservé : ne pas l'écraser."
