# Construction reproductible de Mat & Méthode (Windows 11 64 bits, Python 3.12 64 bits).
#   powershell -ExecutionPolicy Bypass -File build\build.ps1
# Résultat : build\dist\MatMethode_1.0\  (MatMethode.exe + _internal\), à déposer tel quel sur SharePoint.
$ErrorActionPreference = "Stop"
$Racine = Split-Path -Parent $PSScriptRoot
Set-Location $Racine

$Python = "py -3.12"
Write-Host "1/5 Environnement virtuel propre (.venv-build)"
if (Test-Path .venv-build) { Remove-Item -Recurse -Force .venv-build }
Invoke-Expression "$Python -m venv .venv-build"
$Py = Join-Path $Racine ".venv-build\Scripts\python.exe"

Write-Host "2/5 Dépendances"
& $Py -m pip install --upgrade pip
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
