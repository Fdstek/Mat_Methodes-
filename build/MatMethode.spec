# -*- mode: python ; coding: utf-8 -*-
# PyInstaller : dossier portable (--onedir --windowed), PAS --onefile (qui se décompresse dans %TEMP%, §9.1).
# Construire avec build\build.ps1 sur un Windows 11 64 bits.
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

RACINE = Path(SPECPATH).parent
sys.path.insert(0, str(RACINE))
from mat_methode import VERSION  # noqa: E402

datas = [
    (str(RACINE / "mat_methode" / "data" / "exemples.json"), "mat_methode/data"),
    (str(RACINE / "mat_methode" / "data" / "fleche_bas_clair.png"), "mat_methode/data"),
    (str(RACINE / "mat_methode" / "data" / "fleche_bas_sombre.png"), "mat_methode/data"),
    (str(RACINE / "build" / "MatMethode.ico"), "."),
]
datas += collect_data_files("reportlab")   # polices Vera (repli si Segoe UI absente), données
datas += collect_data_files("docx")        # modèle Word par défaut
datas += collect_data_files("pdfminer")    # tables de caractères pour l'extraction PDF

a = Analysis(
    [str(RACINE / "mat_methode" / "__main__.py")],
    pathex=[str(RACINE)],
    datas=datas,
    hiddenimports=["mat_methode.data", "openpyxl"] + (["win32com.client", "pythoncom", "pywintypes"] if sys.platform == "win32" else []),
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtQuick",
              "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtPdf",
              "PySide6.QtBluetooth", "PySide6.QtNetworkAuth", "PySide6.QtSql", "PySide6.QtTest", "pytest", "pytestqt"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MatMethode",
    console=False,          # --windowed
    icon=str(RACINE / "build" / "MatMethode.ico"),
    version=str(RACINE / "build" / "version_info.txt") if sys.platform == "win32" else None,
    upx=False,              # UPX déclenche plus souvent les antivirus
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name=f"MatMethode_{VERSION.rsplit('.', 1)[0]}")
