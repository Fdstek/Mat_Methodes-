"""Page « Définition Mat & Méthode » (anciennement « Mes manips », §6.1) : liste des manips et leur statut."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLineEdit, QMenu, QVBoxLayout, QWidget

from mat_methode.domain import reglages_ops as O
from mat_methode.domain import regles as R
from mat_methode.domain.models import ARCHIVEE, STATUTS_DEFINITION
from mat_methode.domain.regles import tous_les_tags
from mat_methode.domain.texte import norm
from mat_methode.ui import colonnes as C
from mat_methode.ui import theme
from mat_methode.ui.controleur import Controleur
from mat_methode.ui.widgets import (
    InfoBar,
    bouton,
    etiquette,
    liste_statut,
    vider,
)


class PageManips(QWidget):
    ouvrir = Signal(str, str)  # id, mode (« comp » / « def »)
    nouvelle = Signal()
    importer = Signal()
    importer_mm = Signal()
    exporter = Signal(str)

    def _actualiser(self):
        """Reconstruit la page sans la faire remonter (position gardée par la fenêtre)."""
        f = getattr(self, "sur_place", None)
        f() if f else self.rafraichir()

    def __init__(self, ctrl: Controleur):
        super().__init__()
        self.ctrl = ctrl
        self.archives = False
        self.filtres_liste = C.Filtres()  # choix multiples : donneurs d'ordre, attribués, types, tags
        self.tri = None  # (« donneur » | « type », croissant) : clic sur l'en-tête de colonne
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        self.recherche = QLineEdit()  # placée à droite des onglets Manips / Archivées
        self.recherche.setPlaceholderText("Rechercher une manip, un tag, un objectif…")
        self.recherche.setAccessibleName("Rechercher une manip (Ctrl+F)")
        self.recherche.setClearButtonEnabled(True)
        self.recherche.setMinimumWidth(180)
        self.recherche.textChanged.connect(lambda *_: self._actualiser())

        self.pivot = QHBoxLayout()
        self.b_actives = bouton("", lambda: self._onglet(False))
        self.b_archives = bouton("", lambda: self._onglet(True))
        for b in (self.b_actives, self.b_archives):
            b.setProperty("pivot", True)
            self.pivot.addWidget(b)
        self.pivot.addStretch(1)
        self.pivot.addWidget(self.recherche)
        lay.addLayout(self.pivot)

        self.filtres = QHBoxLayout()
        lay.addLayout(self.filtres)
        self.bandeaux = QVBoxLayout()
        lay.addLayout(self.bandeaux)
        self.liste = QFrame()
        self.liste.setObjectName("carte")
        self.l_liste = QVBoxLayout(self.liste)
        self.l_liste.setContentsMargins(0, 0, 0, 0)
        self.l_liste.setSpacing(0)
        lay.addWidget(self.liste)
        bas = QHBoxLayout()
        bas.addWidget(etiquette("Modifier le flux, Dupliquer, Exporter, Archiver : menu « … » de chaque ligne.", secondaire=True, wrap=True), 1)
        bas.addStretch(1)
        bas.addWidget(bouton("Actualiser", self._recharger))
        bas.addWidget(bouton("Restaurer les exemples", self._exemples))
        lay.addLayout(bas)
        lay.addStretch(1)

    # ------------------------------------------------------------ actions
    def _onglet(self, archives: bool):
        self.archives = archives
        self.rafraichir()

    def _choisir_version(self):
        """Comparaison des deux versions d'une manip enregistrée en même temps par deux postes ; l'une est gardée, l'autre peut devenir une manip."""
        from mat_methode.ui.dialogues import choisir_version
        for ident in list(self.ctrl.liste.conflits):
            m = self.ctrl.manip(ident)
            versions = self.ctrl.versions_en_conflit(ident)
            if m is None or not versions:
                continue
            choix = choisir_version(self, m.nom, versions, self.ctrl.nom_de, lambda e: O.nom_etat(self.ctrl.reglages, e)[0])
            if choix is None:
                return
            msg = self.ctrl.resoudre_conflit(ident, choix[0], choix[1])
            self.ctrl.toast.emit(msg or "Version gardée" + (" ; l’autre est devenue une nouvelle manip" if choix[1] else ""))
            self._actualiser()
            if msg:
                return

    def _recharger(self):
        self.ctrl.actualiser()
        self.ctrl.toast.emit("Liste actualisée")

    def _exemples(self):
        from mat_methode.ui.dialogues import confirmer
        if confirmer(self, "Restaurer les exemples ?", "Les manips d’exemple sont remises à leur état d’origine et les réglages "
                     "d’exemple sont ajoutés. Tes autres manips ne sont pas touchées.", "Restaurer"):
            self.ctrl.restaurer_exemples()
            self.ctrl.toast.emit("Exemples restaurés")
            self._actualiser()

    def _visibles(self):
        q = norm(self.recherche.text())
        out = []
        for m in self.ctrl.manips:
            if (m.etat == ARCHIVEE) != self.archives:
                continue
            c = m.contexte
            if q and q not in norm(" ".join([m.nom, c.donneur, c.attribue, c.experience, c.ref, c.type, c.objectif, c.idee, " ".join(m.tags)])):
                continue
            out.append(m)
        out = self.filtres_liste.appliquer(out)
        return C.trier_manips(sorted(out, key=lambda m: m.maj, reverse=True), self.tri)

    def _trier(self, cle: str):
        self.tri = C.basculer_tri(self.tri, cle)
        self._actualiser()

    # ------------------------------------------------------------ affichage
    def rafraichir(self):
        ctrl, r = self.ctrl, self.ctrl.reglages
        n_a = sum(1 for m in ctrl.manips if m.etat != ARCHIVEE)
        n_r = len(ctrl.manips) - n_a
        self.b_actives.setText(f"Manips ({n_a})")
        self.b_archives.setText(f"Archivées ({n_r})")
        for b, actif in ((self.b_actives, not self.archives), (self.b_archives, self.archives)):
            b.setProperty("actif", actif)
            b.style().unpolish(b)
            b.style().polish(b)

        vider(self.filtres)
        de_la_liste = [m for m in ctrl.manips if (m.etat == ARCHIVEE) == self.archives]
        self.filtres.addWidget(self.filtres_liste.barre(de_la_liste, r, self._actualiser, tous_les_tags(de_la_liste, ctrl.reglages.ordre_tags)), 1)

        vider(self.bandeaux)
        if ctrl.liste.conflits:
            n = len(ctrl.liste.conflits)
            noms = " ; ".join(f"« {ctrl.manip(i).nom} »" for i in ctrl.liste.conflits if ctrl.manip(i))
            self.bandeaux.addWidget(InfoBar(f"{noms} : deux postes ont enregistré en même temps. Rien n’est perdu : les deux versions sont gardées, "
                                            "choisis celle à conserver.",
                                            titre=f"{n} manip{'s' if n > 1 else ''} avec deux versions à choisir",
                                            actions=[bouton("Choisir la version…", self._choisir_version, accent=True)]))
        if ctrl.liste.illisibles:
            self.bandeaux.addWidget(InfoBar("Ignoré(s) : " + " ; ".join(ctrl.liste.illisibles), titre="Fichier illisible"))

        vider(self.l_liste)
        lignes = self._visibles()
        if not lignes:
            vide = etiquette("Aucune manip archivée." if self.archives else "Aucune manip. Crée-en une avec « Nouvelle manip ».", secondaire=True)
            vide.setContentsMargins(16, 24, 16, 24)
            self.l_liste.addWidget(vide)
        else:
            self.l_liste.addWidget(self._entete())
        for i, m in enumerate(lignes):
            self.l_liste.addWidget(self._ligne(m, i == len(lignes) - 1))

    # colonnes alignées sur l'en-tête : donneur, type, tags, statut, Ouvrir, « … »
    LARGEURS = tuple(lg for _, lg in C.COMMUNES) + (135, 70, 40)

    def _grille(self, g: QGridLayout):
        g.setContentsMargins(14, 12, 14, 12)
        g.setHorizontalSpacing(16)
        g.setColumnStretch(0, 1)
        for k, lg in enumerate(self.LARGEURS, start=1):
            g.setColumnMinimumWidth(k, lg)

    def _fixe(self, w: QWidget, k: int) -> QWidget:
        w.setFixedWidth(self.LARGEURS[k - 1])
        return w

    def _entete(self) -> QWidget:
        w = QFrame()
        w.setObjectName("ligneManip")
        w.setStyleSheet(f"QFrame#ligneManip{{border-bottom:1px solid {theme.P.trait};}}")
        g = QGridLayout(w)
        self._grille(g)
        g.setContentsMargins(14, 8, 14, 8)
        g.addWidget(etiquette("MANIP", "etiquetteChamp"), 0, 0)
        for k, x in enumerate(C.entetes_communes(self.tri, self._trier), start=1):
            g.addWidget(x, 0, k)
        k0 = len(C.COMMUNES) + 1
        g.addWidget(self._fixe(etiquette("STATUT", "etiquetteChamp"), k0), 0, k0)
        for k in (k0 + 1, k0 + 2):
            g.addWidget(self._fixe(QWidget(), k), 0, k)
        return w

    def _ligne(self, m, derniere: bool) -> QWidget:
        r, p = self.ctrl.reglages, theme.P
        w = QFrame()
        w.setStyleSheet("" if derniere else f"QFrame#ligneManip{{border-bottom:1px solid {p.trait};}}")
        w.setObjectName("ligneManip")
        g = QGridLayout(w)
        self._grille(g)
        g.addWidget(C.resume_manip(self.ctrl, m), 0, 0)
        for k, x in enumerate(C.cellules_communes(m, r, lambda t: (self.filtres_liste.tag.add(t), self._actualiser()), self._trier), start=1):
            g.addWidget(x, 0, k)
        k0 = len(C.COMMUNES) + 1
        if m.etat == ARCHIVEE:
            g.addWidget(self._fixe(etiquette("Archivée", secondaire=True), k0), 0, k0)
        else:
            st = liste_statut(m, STATUTS_DEFINITION)
            st.setMinimumWidth(0)
            st.setMinimumContentsLength(6)
            st.choisi.connect(lambda v, m=m: self._statut(m, v))
            if m.statuts:
                st.setToolTip(O.texte_statut(self.ctrl.reglages, m.statuts[-1]))
            g.addWidget(self._fixe(st, k0), 0, k0)
        g.addWidget(self._fixe(bouton("Ouvrir", lambda: self.ouvrir.emit(m.id, "comp" if m.etapes else "def"), accent=True,
                                      tip=f"Ouvrir le flux de {m.nom}"), k0 + 1), 0, k0 + 1)
        plus = bouton("…", tip=f"Autres actions pour {m.nom}")
        menu = QMenu(plus)
        menu.addAction("Modifier le flux (étapes)", lambda: self.ouvrir.emit(m.id, "def"))
        menu.addAction("Dupliquer", lambda: self._dupliquer(m.id))
        menu.addAction("Exporter", lambda: self.exporter.emit(m.id))
        menu.addAction("Restaurer" if m.etat == ARCHIVEE else "Archiver", lambda: self._archiver(m))
        if O.peut_supprimer(m):
            menu.addAction("Supprimer", lambda: self._supprimer(m))
        plus.setMenu(menu)
        plus.setStyleSheet("QPushButton::menu-indicator{width:0;}")
        self._fixe(plus, k0 + 2)
        g.addWidget(plus, 0, k0 + 2)
        for k in range(1, k0 + 3):
            g.setAlignment(g.itemAtPosition(0, k).widget(), Qt.AlignmentFlag.AlignVCenter)
        return w

    def _dupliquer(self, ident):
        c = self.ctrl.dupliquer(ident)
        self.ctrl.toast.emit(f"Copie créée : {c.nom}")
        self._actualiser()

    def _archiver(self, m):
        if self.ctrl.st.verrou_autre(m.id):
            self.ctrl.toast.emit("Impossible : la manip est modifiée en ce moment par quelqu’un d’autre")
            return
        from mat_methode.ui.dialogues import confirmer
        if m.etat != ARCHIVEE and not confirmer(
                self, "Archiver cette manip ?", f"« {m.nom} » passera dans l’onglet Archivées. Elle reste consultable et peut être restaurée.",
                "Archiver", danger=False):
            return
        avant = m.etat
        a = O.archiver_ou_restaurer(self.ctrl.reglages, m)
        R.noter_statut(m, avant, m.etat, self.ctrl.st.utilisateur)
        self.ctrl.toucher(m)
        self.ctrl.enregistrer_tout()
        self.ctrl.toast.emit("Archivée" if a else "Restaurée")
        self._actualiser()

    def _statut(self, m, statut: str):
        msg = self.ctrl.changer_statut(m, statut)
        if msg:
            self.ctrl.toast.emit(msg)
        elif statut == "validee":
            self.ctrl.toast.emit("Validée : elle apparaît maintenant dans Protocole")
        self._actualiser()

    def _supprimer(self, m):
        from mat_methode.ui.dialogues import confirmer
        if confirmer(self, "Supprimer définitivement ?", f"« {m.nom} » sera supprimée. Une copie reste dans les sauvegardes du jour ; "
                     "Ctrl+Z annule tant que l’application est ouverte.", "Supprimer"):
            self.ctrl.supprimer(m.id)
            self.ctrl.toast.emit("Manip supprimée (Ctrl+Z pour annuler)")
            self._actualiser()

    def tous_tags(self):
        return tous_les_tags(self.ctrl.manips, self.ctrl.reglages.ordre_tags)

    def focus_recherche(self):
        self.recherche.setFocus()
        self.recherche.selectAll()

