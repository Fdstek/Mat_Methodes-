"""Fenêtres (ContentDialog) : modales, avec voile (scrim), fermeture par Échap ou clic hors de la fenêtre.
Le focus reste dans la fenêtre tant qu'elle est ouverte (§14.7)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mat_methode.domain.texte import fmt_dt
from mat_methode.ui import theme
from mat_methode.ui.widgets import ChampTexte, Liste, bouton, champ, etiquette


class Voile(QWidget):
    def __init__(self, parent: QWidget, fermer: Callable):
        super().__init__(parent)
        self.setObjectName("scrim")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._fermer = fermer
        self.setGeometry(parent.rect())

    def mousePressEvent(self, _):
        self._fermer()


class Dialogue(QDialog):
    def __init__(self, parent: QWidget, titre: str, largeur: int = 520):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self.setAccessibleName(titre)
        self.setMinimumWidth(largeur)
        self.setStyleSheet(f"QDialog{{background:{theme.P.carte};border:1px solid {theme.P.trait};border-radius:8px;}}")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(24, 22, 24, 20)
        self.lay.setSpacing(12)
        t = etiquette(titre, "sousTitre")
        self.lay.addWidget(t)
        self.boutons = QHBoxLayout()
        self.boutons.addStretch(1)
        self._voile = None

    def finir(self):
        self.lay.addSpacing(6)
        self.lay.addLayout(self.boutons)

    def exec(self):
        fen = self.parentWidget().window()
        self._voile = Voile(fen, self.reject)
        self._voile.show()
        self.adjustSize()
        g = fen.geometry()
        self.move(g.x() + (g.width() - self.width()) // 2, g.y() + max(40, (g.height() - self.height()) // 3))
        try:
            return super().exec()
        finally:
            self._voile.deleteLater()


def confirmer(parent, titre: str, message: str, libelle: str = "Confirmer", danger=True) -> bool:
    d = Dialogue(parent, titre)
    d.lay.addWidget(etiquette(message, wrap=True))
    d.boutons.addWidget(bouton("Annuler", d.reject))
    ok = bouton(libelle, d.accept, accent=not danger, danger=danger)
    ok.setDefault(True)
    d.boutons.addWidget(ok)
    d.finir()
    return d.exec() == QDialog.DialogCode.Accepted


def informer(parent, titre: str, message: str) -> None:
    d = Dialogue(parent, titre)
    d.lay.addWidget(etiquette(message, wrap=True))
    ok = bouton("OK", d.accept, accent=True)
    ok.setDefault(True)
    d.boutons.addWidget(ok)
    d.finir()
    d.exec()


def demander_texte(parent, titre: str, libelle: str, valeur: str = "", aide: str = "", bouton_ok: str = "Renommer") -> str | None:
    """Petite fenêtre de saisie (renommer). Retourne le texte, ou None si annulé."""
    d = Dialogue(parent, titre)
    if aide:
        d.lay.addWidget(etiquette(aide, secondaire=True, wrap=True))
    champ_ = ChampTexte(valeur)
    champ_.selectAll()
    d.lay.addWidget(champ(libelle, champ_))
    d.boutons.addWidget(bouton("Annuler", d.reject))
    ok = bouton(bouton_ok, d.accept, accent=True)
    ok.setDefault(True)
    d.boutons.addWidget(ok)
    d.finir()
    champ_.setFocus()
    if d.exec() != QDialog.DialogCode.Accepted:
        return None
    return champ_.text().strip()


def nouvelle_manip(parent, manips: list[tuple[str, str]]) -> tuple[str, str] | None:
    """Retourne (nom, id de la manip de départ ou "")."""
    d = Dialogue(parent, "Nouvelle manip")
    nom = ChampTexte("", "Ex. Désacidification acétone")
    d.lay.addWidget(champ("Nom", nom))
    base = Liste([i for i, _ in manips], "", vide="Une manip vide", libelles=dict(manips))
    d.lay.addWidget(champ("Partir de", base))
    d.boutons.addWidget(bouton("Annuler", d.reject))
    ok = bouton("Créer", d.accept, accent=True)
    ok.setDefault(True)
    d.boutons.addWidget(ok)
    d.finir()
    nom.setFocus()
    if d.exec() != QDialog.DialogCode.Accepted:
        return None
    return nom.text().strip() or "Nouvelle manip", base.currentData() or ""


def importer(parent, dossier: str, traiter: Callable[[dict], str]) -> bool:
    """Import d'un ancien rapport : fichier PDF (extraction), fichier JSON, ou JSON collé.
    `traiter` retourne un message d'erreur, ou "" si l'import a réussi."""
    d = Dialogue(parent, "Importer un ancien rapport", 620)
    d.lay.addWidget(etiquette("Choisis le rapport PDF (texte, pas scanné) ou le fichier JSON exporté. "
                              "Tu peux aussi coller le JSON produit par l’extraction.", secondaire=True, wrap=True))
    zone = QPlainTextEdit()
    zone.setPlaceholderText("Coller le JSON ici")
    zone.setMinimumHeight(180)
    zone.setTabChangesFocus(True)
    erreur = etiquette("", wrap=True)
    erreur.setStyleSheet(f"color:{theme.P.danger};")

    def depuis_fichier():
        f, _ = QFileDialog.getOpenFileName(d, "Choisir un ancien rapport", dossier, "Rapport PDF ou JSON (*.pdf *.json)")
        if not f:
            return
        try:
            if f.lower().endswith(".pdf"):
                from mat_methode.extraction.extract_mm import extraire
                res = extraire(f)
                if not res.get("etapes"):
                    erreur.setText("Import impossible : " + (" ".join(res.get("alertes", [])) or "aucune étape reconnue."))
                    return
                data = res
            else:
                data = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception as ex:
            erreur.setText(f"Fichier non reconnu : {ex}")
            return
        msg = traiter(data)
        if msg:
            erreur.setText(msg)
        else:
            d.accept()

    def depuis_zone():
        try:
            data = json.loads(zone.toPlainText())
        except json.JSONDecodeError as ex:
            erreur.setText(f"JSON non reconnu : {ex.msg} (ligne {ex.lineno}). Vérifie le contenu collé.")
            return
        msg = traiter(data)
        if msg:
            erreur.setText(msg)
        else:
            d.accept()

    b = bouton("Choisir un fichier PDF ou JSON…", depuis_fichier, accent=True)
    d.lay.addWidget(b)
    d.lay.addWidget(champ("Ou coller le JSON", zone))
    d.lay.addWidget(erreur)
    d.boutons.addWidget(bouton("Annuler", d.reject))
    d.boutons.addWidget(bouton("Importer le texte collé", depuis_zone))
    d.finir()
    return d.exec() == QDialog.DialogCode.Accepted


FORMATS = [("pdf", "PDF avec le schéma du flux (.pdf)"), ("docx", "Word (.docx)"), ("md", "Texte (Markdown)"),
           ("html", "Rapport imprimable (HTML)"), ("json", "Données (JSON)")]


def exporter(parent, titre: str, contenu: Callable[[str], str], enregistrer: Callable[[str], None]) -> None:
    """Fenêtre « Autres formats » (W07). `contenu(fmt)` donne le texte des formats texte ;
    `enregistrer(fmt)` ouvre « Enregistrer sous »."""
    d = Dialogue(parent, titre, 640)
    fmt = Liste([k for k, _ in FORMATS], "pdf", vide=None, libelles=dict(FORMATS))
    d.lay.addWidget(champ("Format", fmt))
    info = etiquette("", secondaire=True, wrap=True)
    apercu = QPlainTextEdit()
    apercu.setReadOnly(True)
    apercu.setMinimumHeight(240)
    apercu.setProperty("mono", True)
    d.lay.addWidget(info)
    d.lay.addWidget(apercu)
    copier = bouton("Copier", lambda: (QGuiApplication.clipboard().setText(apercu.toPlainText()), copier.setText("Copié")))
    ok = bouton("Enregistrer…", lambda: (enregistrer(fmt.currentData()), d.accept()), accent=True)

    def maj():
        f = fmt.currentData()
        binaire = f in ("pdf", "docx")
        apercu.setVisible(not binaire)
        copier.setVisible(not binaire)
        copier.setText("Copier")
        info.setText("Le rapport complet : flux avec les prélèvements, texte Matériel et méthodes, détail par phase, tableaux. "
                     "Les valeurs manquantes sont signalées « à saisir »." if binaire else "")
        info.setVisible(binaire)
        if not binaire:
            apercu.setPlainText(contenu(f))
        ok.setText({"pdf": "Enregistrer le PDF…", "docx": "Enregistrer le document Word…"}.get(f, "Enregistrer…"))
        d.adjustSize()

    fmt.currentIndexChanged.connect(lambda *_: maj())
    d.boutons.addWidget(bouton("Fermer", d.reject))
    d.boutons.addWidget(copier)
    d.boutons.addWidget(ok)
    d.finir()
    maj()
    d.exec()


def journal(parent, m) -> None:
    d = Dialogue(parent, "Journal des modifications", 720)
    d.lay.addWidget(etiquette(f"Manip lancée le {fmt_dt(m.lancee.le)} par {m.lancee.par}. Version {m.rev}, enregistrée le {fmt_dt(m.maj)}. "
                              "Le journal ne peut être ni modifié ni effacé.", secondaire=True, wrap=True))
    lignes = list(reversed(m.journal))
    if lignes:
        t = QTableWidget(len(lignes), 3)
        t.setHorizontalHeaderLabels(["Date et heure", "Par", "Modification"])
        t.verticalHeader().hide()
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for i, j in enumerate(lignes):
            for k, v in enumerate((fmt_dt(j.t), j.par, j.txt)):
                t.setItem(i, k, QTableWidgetItem(v))
        t.resizeColumnsToContents()
        t.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        t.setMinimumHeight(min(420, 40 + 32 * len(lignes)))
        d.lay.addWidget(t)
    else:
        d.lay.addWidget(etiquette("Aucune modification depuis le lancement."))
    f = bouton("Fermer", d.accept, accent=True)
    f.setDefault(True)
    d.boutons.addWidget(f)
    d.finir()
    d.exec()


def conflit(parent, autre: str) -> str:
    """Retourne « recharger » ou « copie »."""
    d = Dialogue(parent, "Cette manip a été modifiée ailleurs", 560)
    d.lay.addWidget(etiquette(f"{autre} a enregistré une autre version pendant que tu travaillais. Rien n’a été écrasé. "
                              "Que veux-tu faire de tes modifications ?", wrap=True))
    choix = {"v": "copie"}
    d.boutons.addWidget(bouton(f"Recharger la version de {autre}", lambda: (choix.update(v="recharger"), d.accept())))
    c = bouton("Enregistrer ma version comme copie", lambda: (choix.update(v="copie"), d.accept()), accent=True)
    c.setDefault(True)
    d.boutons.addWidget(c)
    d.finir()
    d.exec()  # Échap = garder ma version en copie (aucune perte)
    return choix["v"]
