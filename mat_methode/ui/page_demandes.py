"""Page « Bugs et idées » (bas du menu) : formulaire, liste des demandes avec leur statut, export en fichier .md."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFileDialog, QFrame, QHBoxLayout, QPlainTextEdit, QVBoxLayout, QWidget

from mat_methode import NOM_APPLICATION, VERSION
from mat_methode.domain.demandes import MENUS_DEMANDE, STATUTS_DEMANDE, TYPES_DEMANDE, Demande, vers_markdown
from mat_methode.domain.models import maintenant_iso
from mat_methode.domain.texte import fmt_dt
from mat_methode.storage import demandes as S
from mat_methode.ui import colonnes as C
from mat_methode.ui.controleur import Controleur
from mat_methode.ui.widgets import ChampTexte, Liste, bouton, carte, champ, etiquette, flux_widgets, pastille, vider


class PageDemandes(QWidget):
    ouvrir_fichier = Signal(str)

    def _actualiser(self):
        f = getattr(self, "sur_place", None)
        f() if f else self.rafraichir()

    def __init__(self, ctrl: Controleur):
        super().__init__()
        self.ctrl = ctrl
        self.filtre = ""  # statut affiché ("" = tous)
        self.joints: list[str] = []  # fichiers choisis pour la nouvelle demande
        self.type, self.titre_saisi, self.texte_saisi = TYPES_DEMANDE[0], "", ""
        self.tags_saisis: set[str] = set()
        self.edition: str | None = None  # identifiant de la demande en cours de modification
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(14)

    # ------------------------------------------------------------ données
    def _demandes(self) -> list[Demande]:
        return S.lister(self.ctrl.st)

    def _nom(self, igg: str) -> str:
        return self.ctrl.nom_de(igg)

    # ------------------------------------------------------------ affichage
    def rafraichir(self):
        vider(self.lay)
        self.lay.addWidget(etiquette("Signale un bug ou propose une bonne idée. Tout le monde voit les demandes ; "
                                     "chacun peut en changer le statut (le nom et la date sont gardés).", secondaire=True, wrap=True))
        self.lay.addWidget(self._formulaire())
        toutes = self._demandes()
        barre = []
        for texte, val in [(f"Toutes ({len(toutes)})", "")] + [(f"{s} ({sum(1 for d in toutes if d.statut == s)})", s) for s in STATUTS_DEMANDE]:
            b = bouton(texte, lambda v=val: self._filtrer(v))
            b.setProperty("pivot", True)
            b.setProperty("actif", self.filtre == val)
            barre.append(b)
        barre.append(bouton("Exporter les nouvelles (.md)", self._exporter, tip="Enregistre les demandes « Nouvelle » dans un fichier .md daté (avec leurs pièces) ; elles passent à « À vérifier »"))
        self.lay.addWidget(flux_widgets(barre))
        f, v = carte()
        v.setSpacing(0)
        liste = [d for d in toutes if not self.filtre or d.statut == self.filtre]
        if not liste:
            vide = etiquette("Aucune demande pour l’instant." if not toutes else "Aucune demande avec ce statut.", secondaire=True)
            vide.setContentsMargins(16, 24, 16, 24)
            v.addWidget(vide)
        for i, d in enumerate(liste):
            v.addWidget(self._ligne(d, i == len(liste) - 1))
        self.lay.addWidget(f)
        self.lay.addStretch(1)

    def _formulaire(self) -> QWidget:
        f, lay = carte()
        lay.addWidget(etiquette("Modifier la demande" if self.edition else "Nouvelle demande", "titreCarte"))
        typ = Liste(list(TYPES_DEMANDE), self.type, vide=None)
        typ.choisi.connect(lambda v: setattr(self, "type", v))
        titre = ChampTexte(self.titre_saisi, "En une phrase")
        titre.modifie.connect(lambda v: setattr(self, "titre_saisi", v))
        self._titre = titre
        texte = QPlainTextEdit(self.texte_saisi)
        texte.setPlaceholderText("Décris ce qui s’est passé (où, que faisais-tu ?) ou ton idée")
        texte.setFixedHeight(110)
        texte.textChanged.connect(lambda: setattr(self, "texte_saisi", texte.toPlainText()))
        self._texte = texte
        menus = C.ListeMulti("Choisir le ou les menus", list(MENUS_DEMANDE), self.tags_saisis, "Menus concernés")
        lay.addWidget(self._ligne_champs(champ("Type", typ), champ("Menus concernés (plusieurs choix)", menus)))
        lay.addWidget(champ("Titre", titre))
        lay.addWidget(champ("Description", texte))
        self.noms = etiquette(", ".join(Path(p).name for p in self.joints) or "Aucun fichier joint", secondaire=True)
        lay.addWidget(flux_widgets([bouton("Joindre un fichier…", self._joindre, tip="Capture d’écran, document, journal…"), self.noms]))
        actions = [bouton("Annuler", self._annuler_edition)] if self.edition else []
        actions.append(bouton("Enregistrer la modification" if self.edition else "Envoyer la demande", self._envoyer, accent=True))
        lay.addWidget(flux_widgets(actions))
        return f

    @staticmethod
    def _ligne_champs(a: QWidget, b: QWidget) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(a)
        h.addWidget(b, 1)
        return w

    def _ligne(self, d: Demande, derniere: bool) -> QWidget:
        w = QFrame()
        w.setObjectName("ligneManip")
        h = QVBoxLayout(w)
        h.setContentsMargins(14, 10, 14, 10)
        gauche = QVBoxLayout()
        gauche.setSpacing(2)
        gauche.addWidget(etiquette(d.titre or "(sans titre)", "titreCarte", wrap=True))
        if d.texte.strip():
            gauche.addWidget(etiquette(d.texte.strip(), wrap=True))
        gauche.addWidget(etiquette(f"{d.type} · {self._nom(d.auteur)} · {fmt_dt(d.cree)}"
                                   + (f" · statut changé le {fmt_dt(d.historique[-1].t)} par {self._nom(d.historique[-1].par)}" if d.historique else ""),
                                   secondaire=True, wrap=True))
        if d.tags:
            gauche.addWidget(flux_widgets([C.pilule(t, "#2F6FB8") for t in d.tags]))
        g = QWidget()
        g.setLayout(gauche)
        gauche.setContentsMargins(0, 0, 0, 0)
        h.addWidget(g)
        actions = [bouton(f"📎 {nom}", lambda nom=nom, d=d: self.ouvrir_fichier.emit(str(S.dossier_pieces(self.ctrl.st, d) / nom)),
                          tip="Ouvrir la pièce jointe", lien=True) for nom in d.pieces]
        if d.type == "Bug":
            actions.append(pastille("Bug", "warn"))
        actions.append(bouton("Modifier", lambda d=d: self._modifier(d), tip="Changer le type, le titre, la description ou les menus"))
        st = Liste(list(STATUTS_DEMANDE), d.statut, vide=None)
        st.setMinimumWidth(130)
        st.setAccessibleName(f"Statut de la demande {d.titre}")
        st.choisi.connect(lambda v, d=d: self._statut(d, v))
        actions.append(st)
        h.addWidget(flux_widgets(actions))
        w.setStyleSheet("" if derniere else "QFrame#ligneManip{border-bottom:1px solid rgba(128,128,128,0.35);}")
        return w

    # ------------------------------------------------------------ actions
    def _filtrer(self, statut: str):
        self.filtre = statut
        self._actualiser()

    def _joindre(self):
        fichiers, _ = QFileDialog.getOpenFileNames(self, "Joindre un ou plusieurs fichiers")
        if fichiers:
            self.joints += [f for f in fichiers if f not in self.joints]
            self.noms.setText(", ".join(Path(p).name for p in self.joints))

    def _modifier(self, d: Demande):
        """Recharge la demande dans le formulaire : type, titre, description, menus."""
        self.edition, self.type, self.titre_saisi, self.texte_saisi = d.id, d.type, d.titre, d.texte
        self.tags_saisis, self.joints = set(d.tags), []
        self._actualiser()
        self.ctrl.toast.emit("Modifie la demande puis « Enregistrer la modification »")

    def _annuler_edition(self):
        self.edition, self.titre_saisi, self.texte_saisi, self.joints, self.tags_saisis = None, "", "", [], set()
        self._actualiser()

    def _envoyer(self):
        titre = self.titre_saisi.strip()
        if not titre and not self.texte_saisi.strip():
            self.ctrl.toast.emit("Écris au moins un titre ou une description")
            return
        d = (S.relire(self.ctrl.st, self.edition) if self.edition else None)
        modif = d is not None
        if d is None:
            d = Demande(auteur=self.ctrl.st.utilisateur)
        d.type, d.titre, d.texte, d.tags = self.type, titre, self.texte_saisi.strip(), [t for t in MENUS_DEMANDE if t in self.tags_saisis]
        if modif:
            d.maj = maintenant_iso()
        try:
            for f in self.joints:
                S.joindre(self.ctrl.st, d, f)
            S.enregistrer(self.ctrl.st, d)
        except OSError as ex:
            self.ctrl.toast.emit(f"Demande non enregistrée : {ex}")
            return
        self.edition, self.titre_saisi, self.texte_saisi, self.joints, self.tags_saisis = None, "", "", [], set()
        self.ctrl.toast.emit("Demande modifiée" if modif else "Demande enregistrée, merci !")
        self._actualiser()

    def _statut(self, d: Demande, statut: str):
        frais = S.relire(self.ctrl.st, d.id) or d  # une autre personne a peut-être modifié la demande entre-temps
        if frais.changer_statut(statut, self.ctrl.st.utilisateur):
            try:
                S.enregistrer(self.ctrl.st, frais)
            except OSError as ex:
                self.ctrl.toast.emit(f"Statut non enregistré : {ex}")
        self._actualiser()

    def _exporter(self):
        """Exporte seulement les demandes « Nouvelle » ; une fois exportées, elles passent à « À vérifier »."""
        nouvelles = [d for d in self._demandes() if d.statut == "Nouvelle"]
        if not nouvelles:
            self.ctrl.toast.emit("Aucune nouvelle demande à exporter")
            return
        horodatage = datetime.now().strftime("%Y-%m-%d_%Hh%M")
        defaut = str(self.ctrl.st.donnees / "exports" / f"Bugs_et_idees_{horodatage}.md")
        chemin, _ = QFileDialog.getSaveFileName(self, f"Exporter les {len(nouvelles)} nouvelle(s) demande(s)", defaut, "Fichier Markdown (*.md)")
        if not chemin:
            return
        try:
            cible = Path(chemin)
            copies: dict[tuple[str, str], str] = {}
            if any(d.pieces for d in nouvelles):  # les pièces jointes sont copiées dans un dossier voisin du .md
                dossier = cible.with_name(cible.stem + "_pieces")
                dossier.mkdir(parents=True, exist_ok=True)
                for d in nouvelles:
                    for nom in d.pieces:
                        source = S.dossier_pieces(self.ctrl.st, d) / nom
                        if source.exists():
                            nouveau = f"{d.id[:6]}_{nom}"
                            shutil.copy2(source, dossier / nouveau)
                            copies[(d.id, nom)] = f"{dossier.name}/{nouveau}".replace(" ", "%20")
            cible.write_text(vers_markdown(nouvelles, self._nom, f"{NOM_APPLICATION} {VERSION}", lambda d, nom: copies.get((d.id, nom))), encoding="utf-8")
        except OSError as ex:
            self.ctrl.toast.emit(f"Export impossible : {ex}")
            return
        for d in nouvelles:  # exportée : passe à « À vérifier »
            frais = S.relire(self.ctrl.st, d.id) or d
            if frais.changer_statut("À vérifier", self.ctrl.st.utilisateur):
                S.enregistrer(self.ctrl.st, frais)
        self.ctrl.toast.emit(f"{len(nouvelles)} demande(s) exportée(s), passées à « À vérifier »")
        self._actualiser()
        self.ouvrir_fichier.emit(chemin)
