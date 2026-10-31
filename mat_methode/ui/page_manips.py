"""Page « Mes manips » (§6.1, maquette W01)."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLineEdit, QMenu, QVBoxLayout, QWidget

from mat_methode.domain import reglages_ops as O
from mat_methode.domain.models import ARCHIVEE, NON_REALISEE
from mat_methode.domain.regles import tous_les_tags
from mat_methode.domain.texte import fmt_dt, norm
from mat_methode.ui import theme
from mat_methode.ui.controleur import Controleur
from mat_methode.ui.widgets import (
    InfoBar,
    Liste,
    bouton,
    bouton_tag_couleur,
    etiquette,
    flux_widgets,
    pastille,
    pastille_couleur,
    vider,
)


class PageManips(QWidget):
    ouvrir = Signal(str, str)  # id, mode (« comp » / « def »)
    nouvelle = Signal()
    importer = Signal()
    exporter = Signal(str)

    def __init__(self, ctrl: Controleur):
        super().__init__()
        self.ctrl = ctrl
        self.archives = False
        self.f_donneur = ""
        self.f_type = ""
        self.f_tag = ""
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        barre = QHBoxLayout()
        barre.addWidget(bouton("+  Nouvelle manip", self.nouvelle.emit, accent=True, tip="Nouvelle manip (Ctrl+N)"))
        barre.addWidget(bouton("Importer un ancien rapport", self.importer.emit))
        barre.addStretch(1)
        self.recherche = QLineEdit()
        self.recherche.setPlaceholderText("Rechercher une manip, un tag, un objectif…")
        self.recherche.setAccessibleName("Rechercher une manip (Ctrl+F)")
        self.recherche.setClearButtonEnabled(True)
        self.recherche.setMinimumWidth(260)
        self.recherche.textChanged.connect(lambda *_: self.rafraichir())
        barre.addWidget(self.recherche)
        lay.addLayout(barre)

        self.pivot = QHBoxLayout()
        self.b_actives = bouton("", lambda: self._onglet(False))
        self.b_archives = bouton("", lambda: self._onglet(True))
        for b in (self.b_actives, self.b_archives):
            b.setProperty("pivot", True)
            self.pivot.addWidget(b)
        self.pivot.addStretch(1)
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
        bas.addWidget(etiquette("Dupliquer, Exporter, Archiver : menu « … » de chaque ligne.", secondaire=True))
        bas.addStretch(1)
        bas.addWidget(bouton("Actualiser", self._actualiser))
        bas.addWidget(bouton("Restaurer les exemples", self._exemples))
        lay.addLayout(bas)
        lay.addStretch(1)

    # ------------------------------------------------------------ actions
    def _onglet(self, archives: bool):
        self.archives = archives
        self.rafraichir()

    def _actualiser(self):
        self.ctrl.actualiser()
        self.ctrl.toast.emit("Liste actualisée")

    def _exemples(self):
        from mat_methode.ui.dialogues import confirmer
        if confirmer(self, "Restaurer les exemples ?", "Les manips d’exemple sont remises à leur état d’origine et les réglages "
                     "d’exemple sont ajoutés. Tes autres manips ne sont pas touchées.", "Restaurer"):
            self.ctrl.restaurer_exemples()
            self.ctrl.toast.emit("Exemples restaurés")
            self.rafraichir()

    def _visibles(self):
        q = norm(self.recherche.text())
        out = []
        for m in self.ctrl.manips:
            if (m.etat == ARCHIVEE) != self.archives:
                continue
            c = m.contexte
            if q and q not in norm(" ".join([m.nom, c.donneur, c.ref, c.type, c.objectif, c.idee, " ".join(m.tags)])):
                continue
            if self.f_donneur and c.donneur != self.f_donneur:
                continue
            if self.f_type and c.type != self.f_type:
                continue
            if self.f_tag and not any(norm(t) == norm(self.f_tag) for t in m.tags):
                continue
            out.append(m)
        return sorted(out, key=lambda m: m.maj, reverse=True)

    def _filtre_donneur(self, nom: str):
        self.f_donneur = "" if nom == self.f_donneur else nom
        self.rafraichir()

    # ------------------------------------------------------------ affichage
    def rafraichir(self):
        ctrl, r = self.ctrl, self.ctrl.reglages
        n_a = sum(1 for m in ctrl.manips if m.etat != ARCHIVEE)
        n_r = len(ctrl.manips) - n_a
        self.b_actives.setText(f"Mes manips ({n_a})")
        self.b_archives.setText(f"Archivées ({n_r})")
        for b, actif in ((self.b_actives, not self.archives), (self.b_archives, self.archives)):
            b.setProperty("actif", actif)
            b.style().unpolish(b)
            b.style().polish(b)

        vider(self.filtres)
        self.filtres.addWidget(etiquette("Donneur d’ordre", secondaire=True))
        tous = bouton("Tous", lambda: self._filtre_donneur(""))
        tous.setProperty("chip", True)
        tous.setCheckable(True)
        tous.setChecked(not self.f_donneur)
        self.filtres.addWidget(tous)
        for nom in r.donneurs_ordre:
            n = sum(1 for m in ctrl.manips if m.contexte.donneur == nom and (m.etat == ARCHIVEE) == self.archives)
            self.filtres.addWidget(bouton_tag_couleur(nom, O.couleur_donneur(r, nom), n, self.f_donneur == nom,
                                                      lambda nom=nom: self._filtre_donneur(nom)))
        types = Liste(r.types_demande, self.f_type, vide="Tous les types")
        types.setAccessibleName("Filtrer par type de demande")
        types.choisi.connect(lambda v: (setattr(self, "f_type", v), self.rafraichir()))
        self.filtres.addWidget(types)
        if self.f_tag:
            self.filtres.addWidget(bouton(f"Tag : {self.f_tag}  ✕", lambda: (setattr(self, "f_tag", ""), self.rafraichir()),
                                          tip="Retirer le filtre tag"))
        else:
            self.filtres.addWidget(etiquette("Clique un tag pour filtrer.", secondaire=True))
        self.filtres.addStretch(1)

        vider(self.bandeaux)
        if ctrl.liste.conflits:
            n = len(ctrl.liste.conflits)
            self.bandeaux.addWidget(InfoBar(f"{', '.join(ctrl.liste.conflits)} : copie créée par la synchronisation SharePoint / OneDrive. "
                                            "Compare-la à la manip d’origine ; l’application ne la supprime jamais.",
                                            titre=f"{n} conflit{'s' if n > 1 else ''} de synchronisation à vérifier"))
        if ctrl.liste.illisibles:
            self.bandeaux.addWidget(InfoBar("Ignoré(s) : " + " ; ".join(ctrl.liste.illisibles), titre="Fichier illisible"))

        vider(self.l_liste)
        lignes = self._visibles()
        if not lignes:
            vide = etiquette("Aucune manip archivée." if self.archives else "Aucune manip. Crée-en une avec « Nouvelle manip ».", secondaire=True)
            vide.setContentsMargins(16, 24, 16, 24)
            self.l_liste.addWidget(vide)
        for i, m in enumerate(lignes):
            self.l_liste.addWidget(self._ligne(m, i == len(lignes) - 1))

    def _ligne(self, m, derniere: bool) -> QWidget:
        r, p = self.ctrl.reglages, theme.P
        w = QFrame()
        w.setStyleSheet("" if derniere else f"QFrame#ligneManip{{border-bottom:1px solid {p.trait};}}")
        w.setObjectName("ligneManip")
        g = QGridLayout(w)
        g.setContentsMargins(14, 12, 14, 12)
        g.setHorizontalSpacing(12)
        gauche = QVBoxLayout()
        gauche.setSpacing(4)
        nom = etiquette(m.nom, "titreCarte")
        gauche.addWidget(nom)
        tags = []
        if m.contexte.donneur:
            tags.append(pastille_couleur(m.contexte.donneur, O.couleur_donneur(r, m.contexte.donneur)))
        if m.contexte.type:
            tags.append(pastille(m.contexte.type))
        for t in m.tags:
            b = bouton(f"#{t}", lambda t=t: (setattr(self, "f_tag", t), self.rafraichir()), tip=f"Filtrer sur le tag {t}")
            b.setStyleSheet(f"QPushButton{{background:{p.selection};border:none;border-radius:4px;padding:2px 8px;font-size:9pt;}}")
            tags.append(b)
        if m.lancee:
            n = len(m.journal)
            tags.append(pastille(f"Lancée · modifiée après lancement ({n})" if n else "Lancée", "warn" if n else "ok"))
        v = self.ctrl.st.verrou_autre(m.id)
        if v:
            tags.append(pastille(f"Modifiée en ce moment par {self.ctrl.nom_de(v.utilisateur)}", "info"))
        gauche.addWidget(flux_widgets(tags))
        if m.contexte.objectif:
            o = etiquette("", secondaire=True)
            o.setStyleSheet("font-style:italic;")
            o.setText(o.fontMetrics().elidedText(m.contexte.objectif, Qt.TextElideMode.ElideRight, 330))
            o.setToolTip(m.contexte.objectif)
            gauche.addWidget(o)
        cg = QWidget()
        cg.setLayout(gauche)
        cg.setMaximumWidth(380)
        g.addWidget(cg, 0, 0)
        g.setColumnStretch(0, 1)
        ne = len(m.etapes)
        g.addWidget(etiquette(f"{ne} étape{'s' if ne > 1 else ''} · {len(m.prelevements)} éch.<br>{fmt_dt(m.maj)} · v{m.rev}",
                              secondaire=True), 0, 1)
        g.addWidget(pastille(*O.nom_etat(r, m.etat)), 0, 2)
        g.addWidget(bouton("Ouvrir", lambda: self.ouvrir.emit(m.id, "comp" if m.etapes else "def"), accent=True, tip=f"Ouvrir {m.nom}"), 0, 3)
        g.addWidget(bouton("Modifier le flux", lambda: self.ouvrir.emit(m.id, "def")), 0, 4)
        plus = bouton("…", tip=f"Autres actions pour {m.nom}")
        menu = QMenu(plus)
        menu.addAction("Dupliquer", lambda: self._dupliquer(m.id))
        menu.addAction("Exporter", lambda: self.exporter.emit(m.id))
        if m.etat != ARCHIVEE:
            menu.addAction("Remettre comme réalisée" if m.etat == NON_REALISEE else "Marquer comme non réalisée",
                           lambda: self._non_realisee(m))
        menu.addAction("Restaurer" if m.etat == ARCHIVEE else "Archiver", lambda: self._archiver(m))
        if O.peut_supprimer(m):
            menu.addAction("Supprimer", lambda: self._supprimer(m))
        plus.setMenu(menu)
        plus.setStyleSheet("QPushButton::menu-indicator{width:0;}")
        plus.setFixedWidth(40)
        g.addWidget(plus, 0, 5)
        g.setColumnMinimumWidth(1, 175)
        g.setColumnMinimumWidth(2, 105)
        for k in range(1, 6):
            g.setAlignment(g.itemAtPosition(0, k).widget(), Qt.AlignmentFlag.AlignVCenter)
        return w

    def _dupliquer(self, ident):
        c = self.ctrl.dupliquer(ident)
        self.ctrl.toast.emit(f"Copie créée : {c.nom}")
        self.rafraichir()

    def _archiver(self, m):
        if self.ctrl.st.verrou_autre(m.id):
            self.ctrl.toast.emit("Impossible : la manip est modifiée en ce moment par quelqu’un d’autre")
            return
        from mat_methode.ui.dialogues import confirmer
        if m.etat != ARCHIVEE and not confirmer(
                self, "Archiver cette manip ?", f"« {m.nom} » passera dans l’onglet Archivées. Elle reste consultable et peut être restaurée.",
                "Archiver", danger=False):
            return
        a = O.archiver_ou_restaurer(self.ctrl.reglages, m)
        self.ctrl.toucher(m)
        self.ctrl.enregistrer_tout()
        self.ctrl.toast.emit("Archivée" if a else "Restaurée")
        self.rafraichir()

    def _non_realisee(self, m):
        if self.ctrl.st.verrou_autre(m.id):
            self.ctrl.toast.emit("Impossible : la manip est modifiée en ce moment par quelqu’un d’autre")
            return
        from mat_methode.ui.dialogues import confirmer
        if m.etat != NON_REALISEE and not confirmer(
                self, "Marquer comme non réalisée ?", f"« {m.nom} » sera marquée « Non réalisée ». Tu pourras ensuite l’archiver "
                "ou la supprimer (menu « … »), ou la remettre comme réalisée.", "Marquer non réalisée", danger=False):
            return
        marquee = O.basculer_non_realisee(self.ctrl.reglages, m)
        self.ctrl.toucher(m)
        self.ctrl.enregistrer_tout()
        self.ctrl.toast.emit("Marquée non réalisée : archive-la ou supprime-la avec le menu « … »" if marquee else "Remise comme réalisée")
        self.rafraichir()

    def _supprimer(self, m):
        from mat_methode.ui.dialogues import confirmer
        if confirmer(self, "Supprimer définitivement ?", f"« {m.nom} » sera supprimée. Une copie reste dans les sauvegardes du jour ; "
                     "Ctrl+Z annule tant que l’application est ouverte.", "Supprimer"):
            self.ctrl.supprimer(m.id)
            self.ctrl.toast.emit("Manip supprimée (Ctrl+Z pour annuler)")
            self.rafraichir()

    def tous_tags(self):
        return tous_les_tags(self.ctrl.manips)

    def focus_recherche(self):
        self.recherche.setFocus()
        self.recherche.selectAll()

