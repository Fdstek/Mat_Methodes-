"""Écran d'ouverture (comme Word) : logo, nom, version, barre de progression et étape en cours."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QProgressBar, QVBoxLayout, QWidget


class EcranDemarrage(QWidget):
    def __init__(self, nom: str, version: str, icone: QIcon | None = None, date: str = ""):
        super().__init__(None, Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setObjectName("demarrage")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(460, 280)
        cadre = QFrame(self)
        cadre.setObjectName("cadreDemarrage")
        cadre.setGeometry(0, 0, 460, 280)
        cadre.setStyleSheet("QFrame#cadreDemarrage{background:#0F6B5C;border-radius:10px;}"
                            "QLabel{color:white;background:transparent;}"
                            "QProgressBar{background:rgba(255,255,255,0.25);border:none;border-radius:3px;height:6px;}"
                            "QProgressBar::chunk{background:white;border-radius:3px;}")
        v = QVBoxLayout(cadre)
        v.setContentsMargins(32, 28, 32, 24)
        v.setSpacing(6)
        logo = QLabel()
        if icone is not None and not icone.isNull():
            logo.setPixmap(icone.pixmap(64, 64))
        v.addWidget(logo, 0, Qt.AlignmentFlag.AlignLeft)
        titre = QLabel(nom)
        titre.setStyleSheet("font-size:22pt;font-weight:700;")
        v.addWidget(titre)
        sous = QLabel(f"Matériel et méthodes · version {version}" + (f" · mise à jour du {date}" if date else ""))
        sous.setStyleSheet("font-size:10pt;color:rgba(255,255,255,0.85);")
        v.addWidget(sous)
        v.addStretch(1)
        self.etape = QLabel("Démarrage…")
        self.etape.setStyleSheet("font-size:9pt;color:rgba(255,255,255,0.9);")
        v.addWidget(self.etape)
        self.barre = QProgressBar()
        self.barre.setRange(0, 100)
        self.barre.setTextVisible(False)
        self.barre.setFixedHeight(6)
        v.addWidget(self.barre)
        ecran = QGuiApplication.primaryScreen()
        if ecran is not None:
            g = ecran.availableGeometry()
            self.move(g.center().x() - self.width() // 2, g.center().y() - self.height() // 2)

    def avancer(self, valeur: int, texte: str) -> None:
        """Met à jour la barre et le texte, et laisse l'écran se redessiner."""
        self.barre.setValue(valeur)
        self.etape.setText(texte)
        QApplication.processEvents()
