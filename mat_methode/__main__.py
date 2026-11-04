"""Point d'entrée : `python -m mat_methode` ou MatMethode.exe."""
from __future__ import annotations

import os
import sys


def icone_application():
    """QIcon de l'application : PNG puis ICO, dans le paquet puis à côté de l'exe ; None si introuvable."""
    from importlib import resources
    from pathlib import Path

    from PySide6.QtGui import QIcon
    lieux = []
    try:
        lieux.append(Path(str(resources.files("mat_methode.data"))))
    except Exception:
        pass
    base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    lieux += [base / "mat_methode" / "data", Path(sys.executable).parent / "_internal" / "mat_methode" / "data", Path(__file__).parent / "data"]
    for dossier in lieux:
        for nom in ("MatMethode.png", "MatMethode.ico"):  # PNG d'abord : lu par Qt sans module supplémentaire
            f = dossier / nom
            if f.is_file():
                icone = QIcon(str(f))
                if not icone.isNull():
                    return icone, str(f)
    return None, ""


def icone_barre_des_taches(fen) -> str:
    """Windows : pose aussi l'icône contenue dans MatMethode.exe sur la fenêtre (WM_SETICON), pour la barre des tâches."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return "sans objet"
    try:
        import ctypes
        from ctypes import wintypes
        grand, petit = wintypes.HICON(), wintypes.HICON()
        n = ctypes.windll.shell32.ExtractIconExW(sys.executable, 0, ctypes.byref(grand), ctypes.byref(petit), 1)
        envoyer = ctypes.windll.user32.SendMessageW
        envoyer.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        hwnd = int(fen.winId())
        if grand.value:
            envoyer(hwnd, 0x0080, 1, grand.value)  # WM_SETICON, ICON_BIG
        if petit.value:
            envoyer(hwnd, 0x0080, 0, petit.value)  # ICON_SMALL
        return f"{n} icône(s) lue(s) dans l'exe"
    except Exception as ex:
        return f"échec : {ex}"


def main() -> int:
    # 1) avant tout import qui écrit : fichiers temporaires dans <dossier de l'application>\temp
    from mat_methode.storage.chemins import dossier_application, poste, preparer_temp, utilisateur, vider_temp
    racine = dossier_application()
    temp = preparer_temp(racine)
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

    from PySide6.QtCore import QCoreApplication, Qt
    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtWidgets import QApplication

    from mat_methode import NOM_APPLICATION, VERSION
    from mat_methode.storage.stockage import Stockage
    from mat_methode.ui import theme
    from mat_methode.ui.controleur import Controleur
    from mat_methode.ui.fenetre import Fenetre

    if sys.platform == "win32":  # avant toute fenêtre : la barre des tâches regroupe sous l'icône de l'application
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MatMethode.MatMethode.1")
        except Exception:
            pass
    QCoreApplication.setOrganizationName("")  # aucun QSettings dans le registre (préférences dans donnees\preferences)
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(NOM_APPLICATION)
    app.setApplicationVersion(VERSION)
    icone, source_icone = icone_application()
    icone = icone or QIcon()
    app.setWindowIcon(icone)

    from mat_methode.ui.demarrage import EcranDemarrage
    accueil = EcranDemarrage(NOM_APPLICATION, VERSION, icone)  # écran d'ouverture avec barre de progression
    accueil.show()
    accueil.avancer(10, "Préparation des dossiers…")
    st = Stockage(racine, utilisateur(), poste())
    ctrl = Controleur(st)
    accueil.avancer(30, "Mise en forme de l’interface…")
    theme.appliquer(app)
    fen = Fenetre(ctrl)
    fen.setWindowIcon(icone)
    accueil.avancer(55, "Lecture des réglages et des manips…")
    ctrl.demarrer()
    accueil.avancer(85, "Ouverture de la fenêtre…")

    def suivre_theme(*_):
        theme.appliquer(app)
        fen.rafraichir()

    try:
        app.styleHints().colorSchemeChanged.connect(suivre_theme)
    except AttributeError:
        pass
    taille = st.lire_preferences().get("taille")
    if isinstance(taille, list) and len(taille) == 2:
        fen.resize(max(fen.minimumWidth(), int(taille[0])), max(fen.minimumHeight(), int(taille[1])))
    fen.aller("manips")
    accueil.avancer(100, "Prêt")
    fen.show()
    accueil.close()
    import logging
    logging.getLogger("mat_methode").info("Icône : %s ; barre des tâches : %s", source_icone or "introuvable", icone_barre_des_taches(fen))
    code = app.exec()
    vider_temp(temp)
    return code


if __name__ == "__main__":
    sys.exit(main())
