"""Point d'entrée : `python -m mat_methode` ou MatMethode.exe."""
from __future__ import annotations

import os
import sys


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

    QCoreApplication.setOrganizationName("")  # aucun QSettings dans le registre (préférences dans donnees\preferences)
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(NOM_APPLICATION)
    app.setApplicationVersion(VERSION)
    ico = racine / "_internal" / "MatMethode.ico"
    if ico.exists():
        app.setWindowIcon(QIcon(str(ico)))

    st = Stockage(racine, utilisateur(), poste())
    ctrl = Controleur(st)
    theme.appliquer(app)
    fen = Fenetre(ctrl)
    ctrl.demarrer()

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
    fen.show()
    code = app.exec()
    vider_temp(temp)
    return code


if __name__ == "__main__":
    sys.exit(main())
