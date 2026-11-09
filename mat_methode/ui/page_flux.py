"""Page « Flux » (§6.2, §6.3 ; maquettes W02, W03, W06) : Ma demande, lancement, définir le flux,
compléter les étapes (maître-détail)."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from mat_methode.domain import journal as J
from mat_methode.domain import reglages_ops as O
from mat_methode.domain import regles as R
from mat_methode.domain.catalogue import est_centrifugation
from mat_methode.domain.models import (
    ANNULEE,
    ARCHIVEE,
    BROUILLON,
    DUREES,
    ENCOURS,
    REALISEE,
    STATUTS,
    STATUTS_DEFINITION,
    STATUTS_PROTOCOLE,
    UNITES_VITESSE,
    VALIDEE,
    Condition,
    ReactifEtape,
    Tache,
    maintenant_iso,
)
from mat_methode.domain.reglages_ops import auteur, texte_statut
from mat_methode.domain.regles import code_badge, echantillons_tries, etiquettes
from mat_methode.domain.texte import cap, fmt_dt, fmt_dur, fmt_num, fmt_vol, norm
from mat_methode.domain.volumes import part_voie, reunion_volumes, volume_ajoute, volumes_par_etape
from mat_methode.report.rapport import autres_conditions, resume_conditions
from mat_methode.ui import theme
from mat_methode.ui.controleur import Controleur
from mat_methode.ui.glisser import Poignee, rendre_cible, rendre_source
from mat_methode.ui.widgets import (
    ChampTexte,
    ChipSupprimable,
    ChoixVitesse,
    ChoixVolume,
    Expander,
    InfoBar,
    Liste,
    ListeSaisie,
    NumberBox,
    Segmente,
    ToggleSwitch,
    ambre,
    avatar,
    badge,
    bouton,
    carte,
    champ,
    etiquette,
    figer,
    flux_widgets,
    icone,
    ligne,
    liste_statut,
    numero,
    pastille,
    vider,
)

DEPART = "depart"


# ------------------------------------------------------------------ éléments du flux
class Frise(QWidget):
    """Barre de 0 à la durée ; badge d'un prélèvement à son moment ; effluent à droite (§8.4)."""

    def __init__(self, duree, badges: list[tuple[float, str]]):
        super().__init__()
        self.duree, self.badges = duree, badges
        self.setFixedHeight(34)
        self.setAccessibleName(f"Frise de l’étape, {fmt_dur(duree) if duree else 'durée inconnue'}, {len(badges)} prélèvement(s)")

    def paintEvent(self, _):
        p = theme.P
        q = QPainter(self)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        x0, x1, y = 9, self.width() - 9, 10
        q.setPen(QPen(QColor(p.trait if not p.sombre else "#555555"), 3))
        q.drawLine(x0, y, x1, y)
        f = QFont(self.font())
        f.setPointSizeF(7.5)
        q.setFont(f)
        q.setPen(QColor(p.texte2))
        q.drawText(QRect(x0, y + 8, 40, 14), Qt.AlignmentFlag.AlignLeft, "0")
        q.drawText(QRect(x1 - 80, y + 8, 80, 14), Qt.AlignmentFlag.AlignRight, fmt_dur(self.duree) if self.duree else "fin")
        for pct, code in self.badges:
            cx = x0 + (x1 - x0) * pct
            q.setPen(Qt.PenStyle.NoPen)
            q.setBrush(QColor(p.ambre_texte))
            q.drawEllipse(int(cx - 8), y - 8, 16, 16)
            q.setPen(QColor(p.carte))
            fb = QFont(f)
            fb.setBold(True)
            q.setFont(fb)
            q.drawText(QRect(int(cx - 8), y - 8, 16, 16), Qt.AlignmentFlag.AlignCenter, code)
            q.setFont(f)


class TitreAjuste(QLabel):
    """Titre d'étape : passe à la ligne entre les mots ; si un mot est trop large, la police est réduite
    par pas de 0,5 pt jusqu'à 11 px (§8.4 bis). Jamais de mot coupé à l'écran."""

    def __init__(self, texte: str):
        super().__init__(texte)
        self.setWordWrap(True)
        self._base = 10.5
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        f = QFont(self.font())
        f.setBold(True)
        taille = self._base
        mots = self.text().split() or [""]
        while taille > 8.25:
            f.setPointSizeF(taille)
            if max(QFontMetrics(f).horizontalAdvance(m) for m in mots) <= self.width():
                break
            taille -= 0.5
        f.setPointSizeF(taille)
        if f != self.font():
            self.setFont(f)


def position(p, e) -> float:
    if p.moment == "pendant":
        if e.duree_min and p.temps_min is not None:
            return max(0.0, min(1.0, p.temps_min / e.duree_min))
        return 0.5
    return 1.0


# ------------------------------------------------------------------ page
class PageFlux(QWidget):
    voir_rapport = Signal()
    voir_reglages = Signal(object)  # clé de la carte des Réglages à ouvrir
    dupliquer = Signal(str)
    edition_changee = Signal()

    def __init__(self, ctrl: Controleur, contexte: str = "definition"):
        super().__init__()
        self.ctrl = ctrl
        self.contexte = contexte  # « definition » (Définition › Flux) ou « protocole » (Protocole › Édition)
        self.edition = False  # « Modifier » appuyé : la vue en lecture devient modifiable
        self.mode = "def"
        self.etape_id = DEPART
        self.inserer_apres: int | None = None
        self.groupe_cible: str | None = None  # grande étape où vont les étapes ajoutées
        self.voie_cible: tuple[str, str] | None = None  # (bloc en parallèle, voie) où vont les étapes ajoutées
        self.remplacer = False
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(14)
        self._bilan = None
        self._volumes = None
        # Bandeau de statut : placé par la fenêtre au-dessus de la zone qui défile (toujours visible)
        self._lancement = QWidget()
        self._lancement.setObjectName("bandeauStatut")
        QVBoxLayout(self._lancement).setContentsMargins(0, 0, 0, 0)
        self.actions_bandeau = None  # fonction -> boutons en plus (Protocole : exporter, dossier)
        self._colonne = None
        ctrl.analyses_pretes.connect(self._analyses_lues)  # résultats d'ana explorer lus en arrière-plan

    def _analyses_lues(self, _lu=None):
        """Résultats d'analyses arrivés : seule la colonne du flux est redessinée (l'édition en cours n'est pas touchée)."""
        if self.isVisible() and self._colonne is not None and self.m is not None:
            try:
                self._remplir_colonne()
            except RuntimeError:
                pass

    def _resultats_flux(self) -> dict:
        """Résultats des échantillons (étiquette -> données) déjà lus dans ana explorer ; rien si la lecture n'est pas faite."""
        lu = getattr(self.ctrl, "_analyses", None)
        if lu is None or lu.vide:
            if lu is None:
                self.ctrl.precharger_analyses()
            return {}
        lab = etiquettes(self.m)
        res = lu.pour_export([{"id": lab[p.id], "aramis": p.aramis, "scirius": p.scirius} for p in echantillons_tries(self.m)
                              if p.aramis or p.scirius])
        return {"_res": res, **{e["id"]: e for e in res["echantillons"]}} if res else {}

    @property
    def m(self):
        return self.ctrl.courante

    @property
    def consultation(self) -> bool:
        """Vue en lecture seule : protocole (sauf « Modifier »), manip déjà validée (sauf « Modifier »), ou fichier verrouillé."""
        m = self.m
        if self.ctrl.lecture_seule:
            return True
        if self.edition:
            return False
        return self.contexte == "protocole" or (m is not None and m.etat != BROUILLON)

    @property
    def bandeau(self) -> QWidget:
        return self._lancement

    def basculer_edition(self):
        self.edition = not self.edition
        self._actualiser()
        self.edition_changee.emit()

    def ouvrir(self, mode: str):
        self.edition = False
        self.mode = mode
        self.etape_id = DEPART
        self.inserer_apres = None
        self.groupe_cible = None
        self.voie_cible = None

    def _actualiser(self):
        """Reconstruit la page sans la faire remonter (position gardée par la fenêtre)."""
        f = getattr(self, "sur_place", None)
        f() if f else self.rafraichir()

    # ------------------------------------------------------------ rendu
    def rafraichir(self, structure: bool = True):
        m = self.m
        if m is None:
            return
        if self.etape_id not in self.ordre():
            self.etape_id = self.ordre()[0]
        if not m.etapes:
            self.mode = "def"
        if not structure:
            self._maj_legere()
            return
        vider(self.lay)
        if self.ctrl.lecture_seule:
            v = self.ctrl.verrou_autre
            self.lay.addWidget(InfoBar(f"Ouverte en lecture seule (depuis {fmt_dt(v.depuis)[-5:]}).",
                                       titre=f"Modifiée en ce moment par {self.ctrl.nom_de(v.utilisateur)}",
                                       niveau="info", actions=[bouton("Dupliquer pour travailler dessus", lambda: self.dupliquer.emit(m.id))]))
        self._remplir_lancement()
        demande = self._demande()
        self.lay.addWidget(demande)
        x_vol = Expander("Volumes", "", ouvert=getattr(self, "_volumes_ouvert", True))
        x_vol.tete.clicked.connect(lambda *_: setattr(self, "_volumes_ouvert", x_vol.ouvert))
        self._volumes = QWidget()
        QVBoxLayout(self._volumes).setContentsMargins(0, 0, 0, 0)
        self._volumes_x = x_vol
        x_vol.ajouter(self._volumes)
        self._remplir_volumes()
        self.lay.addWidget(x_vol)
        a_faire = self._a_faire()
        self.lay.addWidget(a_faire)
        piv = QHBoxLayout()
        for k, t in (("def", "1 · Définir le flux"), ("comp", "2 · Compléter les étapes")):
            b = bouton(t, lambda k=k: self._mode(k))
            b.setProperty("pivot", True)
            b.setProperty("actif", self.mode == k)
            b.setEnabled(k == "def" or bool(m.etapes))
            piv.addWidget(b)
        piv.addStretch(1)
        w = QWidget()
        w.setLayout(piv)
        self.lay.addWidget(w)
        w.setProperty("garder", True)  # « Définir / Compléter » reste utilisable en lecture
        corps = self._definir() if self.mode == "def" else self._completer()
        self.lay.addWidget(corps)
        self.lay.addStretch(1)
        if self.consultation:
            figer(self)

    def _maj_legere(self):
        """Après une frappe : bilan, lancement, cartes du flux ; jamais les champs en cours de saisie."""
        if self._bilan is not None:
            self._remplir_bilan()
        if self._volumes is not None:
            self._remplir_volumes()
        self._remplir_lancement()
        if self._colonne is not None and self.mode == "comp":
            self._remplir_colonne()

    def _mode(self, k):
        self.mode = k
        if k == "comp" and self.etape_id is None:
            self.etape_id = DEPART
        self.rafraichir()

    def _toucher(self, structure=False):
        self.ctrl.toucher(self.m, structure)

    # ------------------------------------------------------------ lancement (§8.9)
    def _remplir_lancement(self):
        """Bandeau de statut (toujours visible) : statut en liste déroulante, lancement, « Modifier » et actions de la page."""
        lay = self._lancement.layout()
        vider(lay)
        m = self.m
        if m is None:
            return
        f = QFrame()
        f.setObjectName("lancement")
        f.setProperty("lancee", m.lancee is not None)
        v = QVBoxLayout(f)
        v.setContentsMargins(16, 8, 16, 8)
        v.setSpacing(4)
        h = QHBoxLayout()  # ligne 1 : statut, « Modifier », actions de la page
        h.setSpacing(10)
        h2 = QHBoxLayout()  # ligne 2 : lancement / indications
        h2.setSpacing(10)
        v.addLayout(h)
        v.addLayout(h2)
        h.addWidget(etiquette("<b>Statut</b>"))
        choix = STATUTS_PROTOCOLE if self.contexte == "protocole" else STATUTS_DEFINITION
        if m.etat == ARCHIVEE or self.ctrl.lecture_seule:
            nom, ton = STATUTS.get(m.etat, ("Archivée", "neutre"))
            h.addWidget(pastille(nom, ton))
        else:
            st = liste_statut(m, choix)
            st.choisi.connect(self._statut)
            h.addWidget(st)
        if m.statuts:  # bien visible : qui a mis ce statut, et quand
            dernier = etiquette(texte_statut(self.ctrl.reglages, m.statuts[-1]))
            dernier.setObjectName("dernierStatut")
            dernier.setStyleSheet(f"QLabel#dernierStatut{{color:{theme.P.texte};font-weight:600;}}")
            dernier.setToolTip("Dernier changement de statut (historique complet : bouton « Journal »)")
            h.addWidget(dernier)
        if m.lancee:
            n = len(m.journal)
            infos = [etiquette(f"lancée le {fmt_dt(m.lancee.le)[:10]} par {auteur(self.ctrl.reglages, m.lancee.par)}", secondaire=True)]
            if n:
                infos += [pastille(f"⚠ {n} modification{'s' if n > 1 else ''} après lancement", "warn"), bouton("Voir le journal", self._journal)]
            elif not self.ctrl.lecture_seule and self.contexte == "definition":
                infos.append(bouton("Annuler le lancement", self._annuler_lancement))
            for w in infos:
                h2.addWidget(w)
        elif m.etat == VALIDEE and self.contexte == "definition":
            rang = [x.id for x in R.protocoles(self.ctrl.manips, self.ctrl.reglages.ordre_protocoles)]
            h2.addWidget(etiquette("Dans Protocole" + (f", n° {rang.index(m.id) + 1} à réaliser" if m.id in rang else "")
                                   + " ; passe-la « En cours » au démarrage de la manip.", secondaire=True))
        elif m.etat == BROUILLON:
            h2.addWidget(etiquette("Passe-la « Validée » quand le Mat & Méthode est prêt : elle arrivera dans Protocole.", secondaire=True))
        if m.statuts and not (m.lancee and m.journal):  # « Voir le journal » est déjà là après des modifications
            h2.addWidget(bouton("Journal", self._journal, lien=True, tip="Changements de statut et modifications après lancement"))
        h.addStretch(1)
        h2.addStretch(1)
        autres = self.ctrl.presents_sur(m.id)
        if autres:  # comme dans Excel : qui d'autre a cette manip ouverte
            h.addWidget(etiquette("aussi ouverte par", secondaire=True))
            for pr in autres:
                h.addWidget(avatar(self.ctrl.initiales_de(pr.get("utilisateur", ""), pr),
                                   f"{self.ctrl.nom_present(pr)} ({pr.get('pc', '')}) a cette manip ouverte",
                                   cle=pr.get("utilisateur", "")))
        if not self.ctrl.lecture_seule and m.etat != ARCHIVEE and (self.contexte == "protocole" or m.etat != BROUILLON):
            h.addWidget(bouton("Terminer la modification" if self.edition else "✎  Modifier", self.basculer_edition,
                               accent=not self.edition, tip="Rendre la manip modifiable (elle s’affiche en lecture)"))
        for w in (self.actions_bandeau() if self.actions_bandeau else []):
            h.addWidget(w)
        lay.addWidget(f)

    def _valider(self):
        from mat_methode.ui.dialogues import confirmer
        if confirmer(self, "Valider le Mat & Méthode ?", "Il passe au statut « Validée » et apparaît dans Protocole, à la suite des "
                     "protocoles à réaliser.", "Valider", danger=False):
            self._statut(VALIDEE)

    def _statut(self, statut: str):
        if statut == self.m.etat:
            return
        msg = self.ctrl.changer_statut(self.m, statut)
        self.edition = False
        self.ctrl.toast.emit(msg or {VALIDEE: "Validée : elle est maintenant dans Protocole", BROUILLON: "Remise en brouillon",
                                     ANNULEE: "Annulée", ENCOURS: "En cours : la manip est lancée, chaque modification sera notée",
                                     REALISEE: "Réalisée : le rapport est maintenant dans Rapport"}.get(statut, "Statut changé"))

    def _lancer(self):
        from mat_methode.ui.dialogues import confirmer
        if confirmer(self, "Lancer la manip ?", "À partir de maintenant, chaque modification (étapes, conditions, réactifs, échantillons, "
                     "demande) sera notée avec la date, l’heure et ton nom, et signalée dans le rapport.", "Lancer", danger=False):
            J.lancer(self.m, par=self.ctrl.operateur(self.m))
            if self.m.etat in (BROUILLON, VALIDEE):
                if R.changer_statut(self.m, ENCOURS, self.ctrl.reglages, self.ctrl.st.utilisateur):  # le statut suit le lancement
                    self.ctrl.toucher_reglages()
            self._toucher(True)
            self.ctrl.toast.emit("Manip lancée")

    def _annuler_lancement(self):
        if J.annuler_lancement(self.m):
            if self.m.etat == ENCOURS:
                R.noter_statut(self.m, ENCOURS, VALIDEE, self.ctrl.st.utilisateur)
                self.m.etat = VALIDEE  # revient « à réaliser » dans Protocole
            self._toucher(True)
            self.ctrl.toast.emit("Lancement annulé")

    def _journal(self):
        from mat_methode.ui.dialogues import journal
        self.ctrl.journaliser()
        journal(self, self.m, self.ctrl.reglages)

    # ------------------------------------------------------------ Ma demande
    def _demande(self) -> QWidget:
        m, c, r = self.m, self.m.contexte, self.ctrl.reglages
        f, lay = carte()
        lay.addWidget(etiquette("Ma demande", "titreCarte"))
        g = QGridLayout()
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(10)
        nom = ChampTexte(m.nom, "Nom de la manip")
        nom.modifie.connect(lambda v: (setattr(m, "nom", v.strip() or "Manip"), self._toucher()))
        g.addWidget(champ("Nom de la manip", nom), 0, 0, 1, 3)
        donneur = Liste(r.donneurs_proposes, c.donneur)
        donneur.choisi.connect(self._choisir_donneur)
        g.addWidget(champ("Donneur d’ordre", donneur), 1, 0)
        ref = ChampTexte(c.ref, "choisir le donneur d’ordre", mono=True)
        ref.modifie.connect(lambda v: (setattr(c, "ref", v), self._toucher()))
        regen = icone("↻", "Générer la référence (initiales-date-n°)", self._regenerer_ref)
        g.addWidget(champ("Référence (initiales-date-n°)", ligne(ref, regen)), 1, 1)
        vol = NumberBox(c.volume_depart_ml, "mL")
        vol.valeur.connect(lambda v: (setattr(c, "volume_depart_ml", v), self._toucher()))
        g.addWidget(champ("Volume de départ", vol), 1, 2)
        typ = Liste(r.types_demande, c.type)
        typ.choisi.connect(lambda v: (setattr(c, "type", v), self._toucher(structure=R.est_test(v) != bool(self._idee))))
        g.addWidget(champ("Type de demande", typ), 2, 0)
        op = ChampTexte(c.operateur, "Nom d’utilisateur Windows")
        op.modifie.connect(lambda v: (setattr(c, "operateur", v), self._toucher()))
        g.addWidget(champ("Opérateur (nom d’utilisateur Windows)", op), 2, 1, 1, 2)
        exp = ChampTexte(c.experience, "ex. EXP-2026-014")
        exp.modifie.connect(lambda v: (setattr(c, "experience", v.strip()), self._toucher()))
        g.addWidget(champ("N° d’expérience", exp), 3, 0)
        att = Liste(r.attributions, c.attribue, vide="Non attribuée")
        att.choisi.connect(lambda v: (setattr(c, "attribue", v), self._toucher()))
        g.addWidget(champ("Attribuée à (liste : Réglages › Personnes)", att), 3, 1, 1, 2)
        for k in range(3):
            g.setColumnStretch(k, 1)
        lay.addLayout(g)
        self._idee = None
        if R.est_test(c.type):
            self._idee = ChampTexte(c.idee, "Hypothèse ou référence de l’idée")
            self._idee.modifie.connect(lambda v: (setattr(c, "idee", v), self._toucher()))
            lay.addWidget(champ("Idée testée", self._idee))
        else:
            lay.addWidget(etiquette("« Idée testée » n’apparaît que pour un type « Test d’idée ».", secondaire=True))
        obj = ChampTexte(c.objectif, "Ex. Réduire les FFA à moins de 2 %")
        obj.modifie.connect(lambda v: (setattr(c, "objectif", v), self._toucher()))
        lay.addWidget(champ("Objectif", obj))
        ctx = QPlainTextEdit(c.precisions)
        ctx.setPlaceholderText("Origine de la demande, contraintes, remarques…")
        ctx.setFixedHeight(64)
        ctx.setTabChangesFocus(True)
        ctx.textChanged.connect(lambda: (setattr(c, "precisions", ctx.toPlainText()), self._toucher()))
        lay.addWidget(champ("Contexte (facultatif)", ctx))
        # tags
        from mat_methode.domain.reglages_ops import couleur_tag
        tags = [ChipSupprimable(f"#{t}", lambda t=t: self._retirer_tag(t), f"Retirer le tag {t}", couleur=couleur_tag(r, t)) for t in m.tags]
        sugg = [t for t in R.tous_les_tags(self.ctrl.manips, self.ctrl.reglages.ordre_tags) if not any(t.lower() == x.lower() for x in m.tags)]
        self._tag = ListeSaisie(sugg, "Choisir ou taper un tag")
        self._tag.setAccessibleName("Ajouter un tag")
        self._tag.setToolTip("Liste des tags déjà utilisés ; on peut aussi en taper un nouveau (Entrée)")
        self._tag.setMaximumWidth(280)
        self._tag.valide.connect(lambda v: self._ajouter_tag(v))
        tags += [self._tag, bouton("Ajouter", lambda: self._ajouter_tag(self._tag.currentText()))]
        lay.addWidget(champ("Tags", flux_widgets(tags)))
        self._bilan = QWidget()
        QHBoxLayout(self._bilan).setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._bilan)
        self._remplir_bilan()
        return f

    # ------------------------------------------------------------ à faire
    def _a_faire(self) -> QWidget:
        """Liste de points à régler : réflexion, matériel manquant, réactif manquant…."""
        from PySide6.QtWidgets import QCheckBox
        m, p = self.m, theme.P
        reste = [t for t in m.a_faire if not t.fait]
        x = Expander("À faire", f"{len(reste)} en cours · {len(m.a_faire) - len(reste)} fait{'s' if len(m.a_faire) - len(reste) > 1 else ''}"
                     if m.a_faire else "rien pour l’instant", ouvert=bool(reste) or getattr(self, "_a_faire_ouvert", False))
        x.tete.clicked.connect(lambda *_: setattr(self, "_a_faire_ouvert", x.ouvert))
        x.ajouter(etiquette("Points à régler avant ou pendant la manip, dans l’ordre de réalisation (↑ ↓ pour le changer). "
                            "Les points non cochés sont repris en tête du protocole et du rapport (PDF et Word).", secondaire=True, wrap=True))
        n = len(m.a_faire)
        for k, t in enumerate(m.a_faire):
            case = QCheckBox()
            case.setChecked(t.fait)
            case.setAccessibleName(f"Fait : {t.texte}")
            case.toggled.connect(lambda v, t=t: (setattr(t, "fait", v), self._toucher(True)))
            cat = pastille(t.categorie or "Autre", "warn" if not t.fait else "ok")
            txt = ChampTexte(t.texte)
            if t.fait:
                txt.setStyleSheet(f"color:{p.texte2};text-decoration:line-through;")
            txt.modifie.connect(lambda v, t=t: (setattr(t, "texte", v), self._toucher()))
            qui = etiquette(f"{t.par} · {fmt_dt(t.le)[:10]}" if t.par else "", secondaire=True)
            haut = icone("↑", f"Faire avant : {t.texte}", lambda t=t: (R.deplacer_tache(m, t.id, -1), self._toucher(True)))
            haut.setEnabled(k > 0)
            bas = icone("↓", f"Faire après : {t.texte}", lambda t=t: (R.deplacer_tache(m, t.id, 1), self._toucher(True)))
            bas.setEnabled(k < n - 1)
            x.ajouter(ligne(etiquette(f"{k + 1}.", secondaire=True), case, cat, txt, qui, haut, bas,
                            icone("✕", f"Supprimer : {t.texte}", lambda t=t: self._suppr_tache(t), danger=True)))
        cats = self.ctrl.reglages.categories_a_faire
        cat = Liste(cats, cats[0] if cats else "", vide=None if cats else "Autre")
        cat.setAccessibleName("Catégorie")
        nouveau = ChampTexte("", "ex. commander une ampoule à décanter de 1 L")

        def ajout():
            texte = nouveau.text().strip()
            if not texte:
                return
            m.a_faire.append(Tache(categorie=cat.currentData() or "Autre", texte=texte, par=self.ctrl.nom_utilisateur(), le=maintenant_iso()))
            self._a_faire_ouvert = True
            self._toucher(True)

        nouveau.returnPressed.connect(ajout)
        x.ajouter(ligne(champ("Catégorie", cat), champ("Nouveau point", nouveau), bouton("Ajouter", ajout)))
        return x

    def _suppr_tache(self, t):
        self.ctrl.memoriser_manip()
        self.m.a_faire = [x for x in self.m.a_faire if x is not t]
        self._toucher(True)

    def _ajouter_tag(self, texte: str = ""):
        if texte.strip() and R.ajouter_tags(self.m, texte, R.tous_les_tags(self.ctrl.manips)):
            self._toucher(True)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda: getattr(self, "_tag", None) and self._tag.setFocus())

    def _retirer_tag(self, t):
        self.ctrl.memoriser_manip()
        R.retirer_tag(self.m, t)
        self._toucher(True)

    def _remplir_bilan(self):
        lay = self._bilan.layout()
        vider(lay)
        b = R.bilan(self.m)
        if b.depassement:
            lay.addWidget(pastille(f"Volumes : dépassement de {fmt_vol(-b.restant)} mL", "warn"))
        if b.numeros_a_saisir:
            lay.addWidget(pastille(f"{b.numeros_a_saisir} numéro{'s' if b.numeros_a_saisir > 1 else ''} à saisir", "warn"))
        lay.addStretch(1)

    def _remplir_volumes(self):
        """Section « Volumes » : engagé (départ), prélevé (échantillons), restant ; puis le détail échantillon par échantillon."""
        from PySide6.QtWidgets import QProgressBar
        lay = self._volumes.layout()
        vider(lay)
        m, p = self.m, theme.P
        b = R.bilan(m)
        self._volumes_x.changer_note((f"{fmt_vol(b.amont)} mL en amont · " if b.n_amont else "")
                                     + f"{fmt_vol(b.depart)} mL engagés · {fmt_vol(b.preleve)} mL prélevés · "
                                     + (f"dépassement de {fmt_vol(-b.restant)} mL" if b.depassement else f"{fmt_vol(b.restant)} mL restants"))

        def tuile(titre, valeur, detail, couleur=None):
            f = QFrame()
            f.setObjectName("sousCarte")
            v = QVBoxLayout(f)
            v.setContentsMargins(14, 10, 14, 10)
            v.setSpacing(2)
            v.addWidget(etiquette(titre, "etiquetteChamp"))
            val = etiquette(valeur, "titrePage")
            if couleur:
                val.setStyleSheet(f"color:{couleur};")
            v.addWidget(val)
            v.addWidget(etiquette(detail, secondaire=True, wrap=True))
            return f

        depart = m.contexte.volume_depart_ml
        tuiles = []
        if b.n_amont:  # échantillons pris avant traitement : en plus du volume de la manip
            tuiles.append(tuile("EN AMONT", f"{fmt_vol(b.amont)} mL", f"{b.n_amont} éch. avant traitement, hors manip"))
        tuiles += [tuile("ENGAGÉ", f"{fmt_vol(b.depart)} mL" if depart else "—",
                         "volume de départ (Ma demande)" if depart else "volume de départ à saisir dans Ma demande"),
                   tuile("PRÉLEVÉ", f"{fmt_vol(b.preleve)} mL", f"{b.n} éch. pendant le flux"),
                   tuile("RESTANT", f"{fmt_vol(b.restant)} mL", "dépassement : plus prélevé qu’engagé" if b.depassement else "à la fin du flux",
                         p.danger if b.depassement else p.succes)]
        if b.n_amont:
            tuiles.append(tuile("À PRÉVOIR", f"{fmt_vol(b.total)} mL", "charge totale : amont + engagé"))
        lay.addWidget(ligne(*tuiles))
        if b.depart:
            barre = QProgressBar()
            barre.setRange(0, 100)
            barre.setValue(min(100, round(100 * b.preleve / b.depart)))
            barre.setFormat(f"{min(999, round(100 * b.preleve / b.depart))} % du volume engagé est prélevé")
            barre.setTextVisible(True)
            barre.setAccessibleName("Part du volume engagé prélevée")
            lay.addWidget(barre)
        suivi = R.suivi_volumes(m)
        if suivi:
            g = QGridLayout()
            g.setHorizontalSpacing(18)
            g.setVerticalSpacing(4)
            for k, t in enumerate(("Éch.", "Où et quand", "Prélevé", "Reste ensuite")):
                g.addWidget(etiquette(t, "etiquetteChamp"), 0, k)
            for i, (lab, ou, vol, reste) in enumerate(suivi, start=1):
                g.addWidget(etiquette(f"<b style='color:{p.ambre_texte}'>{lab}</b>"), i, 0)
                g.addWidget(etiquette(ou, wrap=True), i, 1)
                g.addWidget(etiquette(f"{fmt_vol(vol)} mL"), i, 2)
                r = etiquette(f"{fmt_vol(reste)} mL" if b.depart and reste is not None else "—")
                if b.depart and reste is not None and reste < 0:
                    r.setStyleSheet(f"color:{p.danger};font-weight:600;")
                g.addWidget(r, i, 3)
            g.setColumnStretch(1, 1)
            w = QWidget()
            w.setLayout(g)
            lay.addWidget(w)
        else:
            lay.addWidget(etiquette("Aucun échantillon prévu : tout le volume engagé reste disponible.", secondaire=True))
        lignes = volumes_par_etape(m) if m.etapes and b.depart else []
        if lignes:  # volume étape par étape (voies en parallèle comprises)
            lay.addWidget(etiquette("Volumes par étape", "titreCarte"))
            g = QGridLayout()
            g.setHorizontalSpacing(18)
            g.setVerticalSpacing(4)
            for k, t in enumerate(("Étape", "Entrée", "Ajouté", "Prélevé", "Sortie")):
                g.addWidget(etiquette(t, "etiquetteChamp"), 0, k)
            for rang, lg in enumerate(lignes, start=1):
                e = m.etapes[lg.indice]
                g.addWidget(etiquette(f"{lg.indice + 1} · {cap(e.operation)}" + (f" (voie {lg.voie})" if lg.voie else ""), wrap=True), rang, 0)
                g.addWidget(etiquette(f"{fmt_vol(lg.entree)} mL"), rang, 1)
                g.addWidget(etiquette(f"{fmt_vol(lg.ajoute)} mL" if lg.ajoute else "—"), rang, 2)
                g.addWidget(etiquette(f"{fmt_vol(lg.preleve)} mL" if lg.preleve else "—"), rang, 3)
                sortie = etiquette(f"{fmt_vol(lg.sortie)} mL" + (f" ⚠ {lg.alerte}" if lg.alerte else ""))
                if lg.alerte:
                    sortie.setStyleSheet(f"color:{p.danger};font-weight:600;")
                g.addWidget(sortie, rang, 4)
            g.setColumnStretch(0, 1)
            wt = QWidget()
            wt.setLayout(g)
            lay.addWidget(wt)

    # ------------------------------------------------------------ 1 · Définir le flux
    def _definir(self) -> QWidget:
        m = self.m
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        f, cl = carte()
        cl.addWidget(etiquette("1 · Les étapes de ta manip", "titreCarte"))
        cl.addWidget(etiquette("Ajoute, déplace, duplique ou supprime les étapes. Tu complèteras chacune ensuite : conditions, réactifs, échantillons.",
                               secondaire=True, wrap=True))
        if m.etapes:
            cl.addWidget(ligne(bouton("+  Insérer une étape au début", lambda: self._inserer(-1)), "stretch"))
            if self.inserer_apres == -1:
                cl.addWidget(self._panneau_ajout("Insérer au début : que fais-tu ?", "Annuler l’insertion", lambda: self._inserer(None)))
        else:
            cl.addWidget(etiquette("Aucune étape pour l’instant.", secondaire=True))
        catalogue = [o.nom for o in self.ctrl.reglages.operations]
        groupes_vus = set()
        bl = R.blocs(m)
        for genre, par, voies in R.segments(m):
            if genre == "par":  # étapes en parallèle : cadre avec une colonne par voie
                cl.addWidget(self._bloc_parallele(par, voies, catalogue))
                continue
            dans = set(voies)
            for g, idx in bl:
                if not idx or idx[0] not in dans:
                    continue
                if g is None:
                    for i in idx:
                        cl.addWidget(self._ligne_avec_menu(i, catalogue))
                    continue
                groupes_vus.add(g.id)
                cl.addWidget(self._bloc_groupe(g, idx, catalogue))
        for g in m.groupes:  # grande étape encore vide
            if g.id not in groupes_vus:
                cl.addWidget(self._bloc_groupe(g, [], catalogue))
        ia, gc = self.inserer_apres, m.groupe(self.groupe_cible)
        if gc is None:
            self.groupe_cible = None
        vc = self.voie_cible if self.voie_cible and m.parallele(self.voie_cible[0]) else None
        self.voie_cible = vc
        if vc is not None:
            q = f"Voie {R.lettre_voie(m, vc[0], vc[1])} (en parallèle) : que fais-tu dans cette voie ?"
        elif gc is not None:
            nums = R.numeros_groupe(m, gc.id)
            q = f"{gc.nom} · étape {(nums[-1] + 1) if nums else len(m.etapes) + 1} : que fais-tu dans cette grande étape ?"
        elif ia is not None:
            q = f"Insérer {'au début' if ia < 0 else f'après l’étape {ia + 1}'} : que fais-tu ?"
        else:
            q = f"Étape {len(m.etapes) + 1} : que fais-tu {'ensuite' if m.etapes else 'en premier'} ?"
        if ia is None:  # choix de la grande étape AVANT l'opération
            choix = {"": "Hors grande étape"}
            choix.update({f"mo:{x.nom}": f"Modèle de grande étape : {x.nom} ({len(x.etapes)} étape{'s' if len(x.etapes) > 1 else ''})"
                          for x in self.ctrl.reglages.modeles_grandes_etapes})  # les modèles en tête de liste
            choix.update({f"g:{g.id}": f"Dans {g.nom} ({R.plage(R.numeros_groupe(m, g.id))})" for g in m.groupes})
            choix.update({f"n:{n}": f"Nouvelle grande étape : {n}" for n in self.ctrl.reglages.grandes_etapes})
            choix["n:*"] = "Nouvelle grande étape (autre nom)…"
            choix["p:new"] = "Nouveau bloc en parallèle (2 voies)…"
            for kp, par in enumerate(m.paralleles):
                for vo in par.voies:
                    choix[f"v:{par.id}|{vo.id}"] = f"En parallèle · bloc {kp + 1} · voie {R.lettre_voie(m, par.id, vo.id)}"
            ou = Liste(list(choix), f"v:{vc[0]}|{vc[1]}" if vc else (f"g:{gc.id}" if gc else ""), vide=None, libelles=choix)
            ou.setAccessibleName("Où ajouter l’étape")
            ou.setMinimumWidth(320)
            ou.choisi.connect(self._choisir_cible)
            cl.addWidget(ligne(champ("1. Où ajouter l’étape ? (grande étape ou voie en parallèle)", ou), "stretch"))
        if vc is None and gc is None and ia is None:  # pas d'endroit précis : le choix reste en bas (à la suite du flux)
            cl.addWidget(self._panneau_ajout(q, None, None))
        else:
            cl.addWidget(etiquette("Le choix de l’étape à ajouter s’est ouvert juste sous l’endroit concerné.", secondaire=True))
        lay.addWidget(f)
        lay.addWidget(self._communes())
        b = bouton("Mon flux est prêt : compléter les étapes  →", self._vers_completer, accent=True)
        b.setEnabled(bool(m.etapes))
        lay.addWidget(ligne(b, "stretch"))
        return w

    def _panneau_ajout(self, question: str, libelle_fin: str | None, fn_fin) -> QWidget:
        """Choix de l'opération à ajouter : s'ouvre sous l'étape, la grande étape ou la voie concernée (ou en bas pour la suite du flux)."""
        p = theme.P
        f = QFrame()
        f.setObjectName("menuAjout")
        f.setStyleSheet(f"QFrame#menuAjout{{border:2px solid {p.accent};border-radius:8px;background:{p.info_fond};}}")
        v = QVBoxLayout(f)
        v.setContentsMargins(10, 8, 10, 10)
        v.setSpacing(6)
        tete = [etiquette(question, "titreCarte"), "stretch"]
        if libelle_fin:
            tete.append(bouton(libelle_fin, fn_fin))
        v.addWidget(ligne(*tete))
        v.addWidget(flux_widgets([bouton(cap(o.nom), lambda o=o: self._ajouter_etape(o.nom)) for o in self.ctrl.reglages.operations]))
        autre = ChampTexte("", "Ex. neutralisation")
        autre.returnPressed.connect(lambda: self._ajouter_etape(autre.text()))
        v.addWidget(ligne(champ("Autre étape", autre), bouton("Ajouter", lambda: self._ajouter_etape(autre.text())), "stretch"))
        return f

    def _ligne_avec_menu(self, i: int, catalogue: list[str], **kw) -> QWidget:
        """Ligne d'étape ; si on vient de cliquer « + Insérer après » sur elle, le choix de l'opération s'ouvre juste dessous."""
        ligne_w = self._ligne_etape(i, catalogue, **kw)
        e = self.m.etapes[i]
        reunit = i > 0 and self.m.etapes[i - 1].parallele_id is not None and e.parallele_id is None  # 1re étape après un bloc en parallèle
        if (self.inserer_apres != i or self.consultation) and not reunit:
            return ligne_w
        c = QWidget()
        v = QVBoxLayout(c)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        v.addWidget(ligne_w)
        if reunit:
            v.addWidget(self._panneau_convergence(i))
        if self.inserer_apres == i and not self.consultation:
            v.addWidget(self._panneau_ajout(f"Insérer après l’étape {i + 1} : que fais-tu ?", "Annuler l’insertion", lambda: self._inserer(None)))
        return c

    def _ligne_etape(self, i: int, catalogue: list[str], dans_groupe: bool = False, dans_voie: bool = False) -> QWidget:
        m, e = self.m, self.m.etapes[i]
        sf = QFrame()
        sf.setObjectName("sousCarte")
        h = QHBoxLayout(sf)
        h.setContentsMargins(10, 6, 10, 6)
        if not self.consultation:  # glisser-déposer : poignée à gauche, la ligne reçoit les étapes et les grandes étapes
            h.addWidget(Poignee("etape", e.id, f"l’étape {i + 1}", sf))
            rendre_cible(sf, {"etape": "avant", "groupe": "avant"}, lambda genre, ident, avant, e=e: self._deposer(genre, ident, e.id, avant))
        h.addWidget(numero(i + 1))
        op = Liste(catalogue, e.operation, vide=None, libelles={o: cap(o) for o in catalogue + [e.operation]})
        op.setAccessibleName(f"Opération de l’étape {i + 1}")
        op.choisi.connect(lambda v, e=e: (setattr(e, "operation", v), self._toucher(True)))
        if dans_voie:  # voie étroite : la liste des opérations peut se réduire
            op.setMinimumWidth(100)
        h.addWidget(op, 1)
        par = m.parallele(e.parallele_id)
        if dans_voie and par is not None:  # dans une voie : changer de voie ou sortir du bloc (l'étape réunit alors les voies)
            choix = {v.id: f"Voie {R.lettre_voie(m, par.id, v.id)}" for v in par.voies}
            vo = Liste(list(choix), e.voie_id or "", vide="Sortir du bloc", libelles=choix)
            vo.setAccessibleName(f"Voie de l’étape {i + 1}")
            vo.setMinimumWidth(90)
            vo.setMaximumWidth(120)
            vo.choisi.connect(lambda val, e=e: (R.placer_dans_voie(m, e.id, e.parallele_id, val) if val else R.sortir_de_parallele(m, e.id),
                                                self._toucher(True)))
            h.addWidget(vo)
        elif m.groupes and not dans_voie:  # ranger l'étape dans une grande étape
            choix = {g.id: f"{g.nom} ({R.plage(R.numeros_groupe(m, g.id))})" for g in m.groupes}
            gr = Liste(list(choix), e.groupe_id or "", vide="Hors grande étape", libelles=choix)
            gr.setAccessibleName(f"Grande étape de l’étape {i + 1}")
            gr.setMaximumWidth(230)
            gr.choisi.connect(lambda val, e=e: (R.placer_dans_groupe(m, e.id, val or None), self._toucher(True)))
            h.addWidget(gr)
        if m.paralleles and not dans_voie:  # mettre l'étape dans une voie d'un bloc en parallèle
            choix = {f"{p.id}|{v.id}": f"Bloc {kp + 1} · voie {R.lettre_voie(m, p.id, v.id)}" for kp, p in enumerate(m.paralleles) for v in p.voies}
            pa = Liste(list(choix), "", vide="Pas parallèle", libelles=choix)
            pa.setAccessibleName(f"Mettre l’étape {i + 1} en parallèle")
            pa.setMinimumWidth(120)
            pa.setMaximumWidth(150)
            pa.choisi.connect(lambda val, e=e: (R.placer_dans_voie(m, e.id, *val.split("|")) if val else None, self._toucher(True)))
            h.addWidget(pa)
        haut = icone("↑", f"Monter l’étape {i + 1}", lambda e=e: self._deplacer(e, -1))
        bas = icone("↓", f"Descendre l’étape {i + 1}", lambda e=e: self._deplacer(e, 1))
        if dans_voie:  # dans une voie : seulement à l'intérieur de la voie
            haut.setEnabled(i > 0 and m.etapes[i - 1].voie_id == e.voie_id and m.etapes[i - 1].parallele_id == e.parallele_id)
            bas.setEnabled(i < len(m.etapes) - 1 and m.etapes[i + 1].voie_id == e.voie_id and m.etapes[i + 1].parallele_id == e.parallele_id)
        else:
            haut.setEnabled(i > 0)
            bas.setEnabled(i < len(m.etapes) - 1)
        h.addWidget(haut)
        h.addWidget(bas)
        h.addWidget(icone("⧉", f"Dupliquer l’étape {i + 1}", lambda e=e: self._dupliquer_etape(e)))
        if not dans_voie:
            h.addWidget(bouton("+ Insérer après", lambda i=i: self._inserer(i)))
        h.addWidget(icone("✕", f"Supprimer l’étape {i + 1}", lambda e=e: self._supprimer_etape(e), danger=True))
        return sf

    def _bloc_parallele(self, par, voies: list[list[int]], catalogue: list[str]) -> QWidget:
        """Cadre « En parallèle » : une colonne par voie ; l'étape qui suit le cadre réunit les voies."""
        m, p = self.m, theme.P
        f = QFrame()
        f.setObjectName("parallele")
        f.setStyleSheet(f"QFrame#parallele{{border:2px solid {p.ambre_trait};border-radius:10px;background:{p.ambre_fond};}}")
        v = QVBoxLayout(f)
        v.setContentsMargins(10, 8, 10, 10)
        v.setSpacing(6)
        tous = [i for idx in voies for i in idx]
        titre = etiquette(f"EN PARALLÈLE · {R.plage([i + 1 for i in tous])}" if tous else "EN PARALLÈLE · vide", "etiquetteChamp")
        titre.setStyleSheet(f"color:{p.ambre_texte};font-weight:700;")
        entete = [titre, "stretch"]
        if not self.consultation:
            ajout = bouton("+ Ajouter une voie", lambda: (R.ajouter_voie(m, par.id), self._toucher(True)), tip="Jusqu’à 4 voies côte à côte")
            ajout.setEnabled(len(par.voies) < 4)
            entete += [ajout, bouton("Défaire", lambda: (setattr(self, "voie_cible", None), R.defaire_parallele(m, par.id), self._toucher(True)),
                                     tip="Défaire le bloc (ses étapes restent dans le flux, l’une après l’autre)")]
        v.addWidget(ligne(*entete))
        cols = QHBoxLayout()
        cols.setSpacing(10)
        for k, vo in enumerate(par.voies):
            lettre = R.lettre_voie(m, par.id, vo.id)
            actif = self.voie_cible == (par.id, vo.id)
            lane = QFrame()
            lane.setObjectName("voie")
            lane.setStyleSheet(f"QFrame#voie{{border:{'2px solid ' + p.accent if actif else '1px dashed ' + p.ambre_trait};border-radius:8px;"
                               f"background:{p.carte};}}")
            lv = QVBoxLayout(lane)
            lv.setContentsMargins(8, 6, 8, 8)
            lv.setSpacing(6)
            nom = ChampTexte(vo.nom, "nom de la voie (facultatif)")
            nom.modifie.connect(lambda val, vo=vo: (setattr(vo, "nom", val), self._toucher()))
            tete = [etiquette(f"VOIE {lettre}", "etiquetteChamp"), nom]
            if not self.consultation:
                tete.append(bouton("+ sous-étape", lambda vo=vo: self._viser_voie(par.id, vo.id), tip=f"Ajouter une étape dans la voie {lettre}"))
                if len(par.voies) > 2:
                    tete.append(icone("✕", f"Supprimer la voie {lettre}", lambda vo=vo: (R.supprimer_voie(m, par.id, vo.id), self._toucher(True)), danger=True))
            lv.addWidget(ligne(*tete))
            lv.addWidget(self._carte_matiere_voie(par, vo, voies))
            for i in voies[k]:
                lv.addWidget(self._ligne_avec_menu(i, catalogue, dans_voie=True))
            if not voies[k] and not actif:
                lv.addWidget(etiquette("Aucune étape : « + sous-étape » ou glisse une étape ici.", secondaire=True, wrap=True))
            if actif and not self.consultation:
                lv.addWidget(self._panneau_ajout(f"Voie {lettre} · étape {R.numero_prochaine_etape_voie(m, par.id, vo.id)} : que fais-tu ?", "Terminer le bloc", self._finir_voie))
            lv.addStretch(1)
            if not self.consultation:
                rendre_cible(lane, {"etape": "dedans"}, lambda genre, ident, avant, vo=vo: self._deposer_dans_voie(ident, par.id, vo.id))
            cols.addWidget(lane, 1)
        v.addLayout(cols)
        v.addWidget(etiquette("Les voies sont réalisées en même temps ; l’étape qui suit ce cadre les réunit.", secondaire=True, wrap=True))
        return f

    def _sortie_avant_bloc(self, par) -> tuple[float, str]:
        """(volume sortant de l'étape qui précède le bloc, texte « de l'étape N » ou « du volume de départ »)."""
        m = self.m
        membres = [i for i, e in enumerate(m.etapes) if e.parallele_id == par.id]
        debut = min(membres) if membres else len(m.etapes)
        if debut == 0:
            return float(m.contexte.volume_depart_ml or 0), "du volume de départ (Ma demande)"
        lignes = {lg.indice: lg for lg in volumes_par_etape(m)}
        lg = lignes.get(debut - 1)
        return (lg.sortie if lg else float(m.contexte.volume_depart_ml or 0)), f"de la sortie de l’étape {debut}"

    def _carte_matiere_voie(self, par, vo, voies) -> QWidget:
        """Matière reçue par la voie (part de la sortie précédente, en % ou mL) et autres matières ajoutées."""
        sortie, d_ou = self._sortie_avant_bloc(par)
        f = QFrame()
        f.setObjectName("sousCarte")
        v = QVBoxLayout(f)
        v.setContentsMargins(10, 8, 10, 8)
        v.setSpacing(6)
        if R.bloc_au_depart(self.m) is par:  # le bloc ouvre le flux : la voie part de ses propres matières (Scirius ou à la main) et de leur volume
            total = volume_ajoute(vo)
            v.addWidget(etiquette(f"<b>Matière de départ de la voie {R.lettre_voie(self.m, par.id, vo.id)}</b>"
                                  + (f" = <b>{fmt_vol(total)} mL</b>" if total else " : quantités en mL à saisir"), wrap=True))
            v.addWidget(self._table_matieres(vo.autres, "matière"))
            return f
        recu = part_voie(vo, sortie, len(par.voies))
        part = NumberBox(vo.part, "", "égale")
        part.setMaximumWidth(90)
        part.valeur.connect(lambda val: setattr(vo, "part", val))
        part.editingFinished.connect(lambda: self._toucher(True))
        unite = Liste(["%", "mL"], vo.part_unite, vide=None)
        unite.setMinimumWidth(80)
        unite.setMaximumWidth(90)
        unite.setAccessibleName("Unité de la part reçue")
        unite.choisi.connect(lambda u: (setattr(vo, "part_unite", u), self._toucher(True)))
        v.addWidget(etiquette(f"<b>Matière reçue</b> {d_ou}" + (f" = <b>{fmt_vol(recu)} mL</b>" if sortie else ""), wrap=True))
        v.addWidget(ligne(champ("Part reçue", part), champ("Unité", unite), "stretch", espacement=8))
        v.addWidget(etiquette("Autres matières de la voie", "etiquetteChamp"))
        v.addWidget(self._table_matieres(vo.autres, "matière"))
        return f

    def _panneau_convergence(self, i: int) -> QWidget:
        """Étape qui réunit les voies : quantité prise de chaque voie (par défaut toute la sortie)."""
        m = self.m
        e, prec = m.etapes[i], m.etapes[i - 1]
        par = m.parallele(prec.parallele_id)
        lignes = {lg.indice: lg for lg in volumes_par_etape(m)}
        f = QFrame()
        f.setObjectName("sousCarte")
        v = QVBoxLayout(f)
        v.setContentsMargins(12, 8, 12, 8)
        v.setSpacing(4)
        v.addWidget(etiquette(f"Étape {i + 1} · matière reçue des voies en parallèle", "titreCarte"))
        termes = []  # « A 40 mL », « B 25 mL » : volume réellement pris dans chaque voie, pour la somme affichée en bas
        for vo in par.voies:
            idx = [k for k, x in enumerate(m.etapes) if x.parallele_id == par.id and x.voie_id == vo.id]
            if not idx:
                continue
            sortie = lignes[idx[-1]].sortie if idx[-1] in lignes else 0.0
            lettre = R.lettre_voie(m, par.id, vo.id)
            pris = e.apports.get(vo.id)
            termes.append((lettre, min(pris, sortie) if pris is not None else sortie))
            qte = NumberBox(pris, "mL", "tout")
            qte.setMaximumWidth(140)
            qte.valeur.connect(lambda val, vo=vo, e=e: (e.apports.pop(vo.id, None) if val is None else e.apports.__setitem__(vo.id, float(val)), self._toucher()))
            qte.editingFinished.connect(lambda: self._toucher(True))
            reste = sortie - (pris if pris is not None else sortie)
            v.addWidget(ligne(etiquette(f"Voie {lettre} (étape {idx[-1] + 1}) · sortie {fmt_vol(sortie)} mL"), "stretch", champ("Quantité prise", qte),
                              etiquette(f"{fmt_vol(reste)} mL non repris" if reste > 0.0005 else "toute la sortie", secondaire=True)))
        if termes:
            total = sum(x for _, x in termes)
            lg = lignes.get(i)
            texte = " + ".join(f"voie {lettre} {fmt_vol(x)} mL" for lettre, x in termes)
            if lg is not None and lg.ajoute:
                texte += f" + réactifs de l’étape {fmt_vol(lg.ajoute)} mL"
                total += lg.ajoute
            if lg is not None and lg.preleve:
                texte += f" − prélevé {fmt_vol(lg.preleve)} mL"
                total -= lg.preleve
            v.addWidget(etiquette(f"Volume après réunion : {texte} = {fmt_vol(total)} mL", "titreCarte", wrap=True))
        return f

    def _deposer_dans_voie(self, ident: str, pid: str, vid: str):
        self.ctrl.memoriser_manip()
        if R.placer_dans_voie(self.m, ident, pid, vid):
            self._toucher(True)
            self.ctrl.toast.emit("Étape rangée dans la voie (Ctrl+Z pour annuler)")

    def _bloc_groupe(self, g, idx: list[int], catalogue: list[str]) -> QWidget:
        """Cadre d'une grande étape : nom, ses étapes, ajout d'une sous-étape."""
        m, p = self.m, theme.P
        f = QFrame()
        f.setObjectName("groupe")
        f.setStyleSheet(f"QFrame#groupe{{border:1px solid {p.accent};border-left:4px solid {p.accent};border-radius:8px;background:{p.info_fond};}}")
        v = QVBoxLayout(f)
        v.setContentsMargins(10, 8, 10, 10)
        v.setSpacing(6)
        nom = Liste(self.ctrl.reglages.grandes_etapes, g.nom, vide=None)
        nom.setAccessibleName("Nom de la grande étape")
        nom.choisi.connect(lambda val, g=g: (setattr(g, "nom", val), self._toucher(True)))
        titre = etiquette(f"GRANDE ÉTAPE · {R.plage([i + 1 for i in idx])}" if idx else "GRANDE ÉTAPE · vide", "etiquetteChamp")
        titre.setStyleSheet(f"color:{p.accent};font-weight:700;")
        haut = icone("↑", f"Monter la grande étape {g.nom}", lambda: (R.deplacer_groupe(m, g.id, -1), self._toucher(True)))
        bas = icone("↓", f"Descendre la grande étape {g.nom}", lambda: (R.deplacer_groupe(m, g.id, 1), self._toucher(True)))
        haut.setEnabled(bool(idx) and idx[0] > 0)
        bas.setEnabled(bool(idx) and idx[-1] < len(m.etapes) - 1)
        if not self.consultation:
            v.addWidget(ligne(Poignee("groupe", g.id, f"la grande étape {g.nom}", f), titre, nom, "stretch", haut, bas,
                              bouton("+ Ajouter une sous-étape", lambda: self._viser_groupe(g.id)),
                              icone("⧉", f"Dupliquer la grande étape {g.nom} (choix du nombre de copies)", lambda: self._dupliquer_groupe(g)),
                              icone("★", f"Enregistrer la grande étape {g.nom} comme modèle (sans les quantités)", lambda: self._enregistrer_modele(g)),
                              bouton("Défaire", lambda: self._defaire_groupe(g), tip=f"Défaire la grande étape {g.nom} (ses étapes restent dans le flux)")))
            rendre_cible(f, {"etape": "dedans", "groupe": "avant"},
                         lambda genre, ident, avant, g=g, idx=idx: self._deposer_sur_groupe(genre, ident, g, idx, avant))
        else:
            v.addWidget(ligne(titre, nom, "stretch", haut, bas,
                          bouton("+ Ajouter une sous-étape", lambda: self._viser_groupe(g.id)),
                          icone("⧉", f"Dupliquer la grande étape {g.nom} (choix du nombre de copies)", lambda: self._dupliquer_groupe(g)),
                          bouton("Défaire", lambda: self._defaire_groupe(g), tip=f"Défaire la grande étape {g.nom} (ses étapes restent dans le flux)")))
        for i in idx:
            v.addWidget(self._ligne_avec_menu(i, catalogue, dans_groupe=True))
        if not idx and self.groupe_cible != g.id:
            v.addWidget(etiquette("Aucune sous-étape : « + Ajouter une sous-étape » pour choisir une opération.", secondaire=True))
        if self.groupe_cible == g.id and not self.consultation:
            nums = R.numeros_groupe(self.m, g.id)
            v.addWidget(self._panneau_ajout(f"{g.nom} · étape {(nums[-1] + 1) if nums else len(self.m.etapes) + 1} : que fais-tu dans cette grande étape ?",
                                            f"Terminer « {g.nom} »", self._finir_groupe))
        return f

    def _dupliquer_groupe(self, g):
        from mat_methode.ui.dialogues import dupliquer_groupe
        m = self.m
        ids = {e.id for e in m.etapes if e.groupe_id == g.id}
        if not ids:
            self.ctrl.toast.emit("Grande étape vide : rien à dupliquer")
            return
        choix = dupliquer_groupe(self, g.nom, len(ids), sum(1 for p in m.prelevements if p.etape_id in ids))
        if choix is None:
            return
        self.ctrl.memoriser_manip()
        n = len(R.dupliquer_groupe(m, g.id, *choix))
        self._toucher(True)
        self.ctrl.toast.emit(f"{g.nom} dupliquée {n} fois")

    def _choisir_cible(self, v: str):
        """Liste « Où ajouter l'étape ? » : hors grande étape, dans une existante, ou en commencer une."""
        if v == "p:new":
            p = R.creer_parallele(self.m)
            self.voie_cible, self.groupe_cible, self.inserer_apres = (p.id, p.voies[0].id), None, None
            self._toucher(True)
            self.ctrl.toast.emit("Bloc en parallèle créé : ajoute les étapes de la voie A, puis choisis la voie B")
        elif v.startswith("v:"):
            pid, _, vid = v[2:].partition("|")
            self.voie_cible, self.groupe_cible, self.inserer_apres = (pid, vid), None, None
            self._actualiser()
        elif not v:
            self.voie_cible = None
            self._finir_groupe()
        elif v.startswith("g:"):
            self.voie_cible = None
            self._viser_groupe(v[2:])
        elif v.startswith("mo:"):
            self._poser_modele(v[3:])
        elif v == "n:*":
            from mat_methode.ui.dialogues import demander_texte
            nom = demander_texte(self, "Nouvelle grande étape", "Nom", "", "Le nom est aussi ajouté à la liste des Réglages.",
                                 bouton_ok="Commencer")
            if nom:
                self._commencer_groupe(nom)
            else:
                self._actualiser()
        else:
            self._commencer_groupe(v[2:])

    def _poser_modele(self, nom: str):
        """Ajoute à la fin du flux une grande étape copiée d'un modèle (les quantités de réactifs sont à compléter)."""
        modele = next((x for x in self.ctrl.reglages.modeles_grandes_etapes if x.nom == nom), None)
        if modele is None:
            self._actualiser()
            return
        self.ctrl.memoriser_manip()
        g = R.appliquer_modele(self.m, modele)
        self.groupe_cible, self.inserer_apres, self.voie_cible = None, None, None
        self._toucher(True)
        self.ctrl.toast.emit(f"Grande étape « {g.nom} » ajoutée d’après le modèle : complète les quantités (Ctrl+Z pour annuler)")

    def _enregistrer_modele(self, g):
        """Enregistre la grande étape comme modèle (étapes, conditions, réactifs sans quantités), partagé avec tous les postes."""
        from mat_methode.domain import reglages_ops as O
        from mat_methode.ui.dialogues import demander_texte
        nom = demander_texte(self, "Enregistrer comme modèle", "Nom du modèle", g.nom,
                             "Les étapes, leurs conditions et leurs réactifs sont gardés, sans les quantités. Le modèle est partagé avec tous les postes ; "
                             "un modèle du même nom est remplacé.", bouton_ok="Enregistrer")
        if not nom:
            return
        remplace = O.enregistrer_modele(self.ctrl.reglages, R.modele_depuis_groupe(self.m, g.id, nom))
        self.ctrl.toucher_reglages()
        self.ctrl.toast.emit(f"Modèle « {nom.strip()} » {'remplacé' if remplace else 'enregistré'}")
        self._actualiser()

    def _commencer_groupe(self, nom: str):
        if not nom:
            self.ctrl.toast.emit("Choisis le nom de la grande étape")
            return
        if nom not in self.ctrl.reglages.grandes_etapes:
            self.ctrl.reglages.grandes_etapes.append(nom)
            self.ctrl.toucher_reglages()
        g = R.creer_groupe(self.m, nom)
        self.groupe_cible, self.inserer_apres, self.voie_cible = g.id, None, None
        self._toucher(True)
        self.ctrl.toast.emit(f"Grande étape « {nom} » : ajoute ses sous-étapes")

    def _viser_groupe(self, gid):
        self.groupe_cible, self.inserer_apres, self.voie_cible = gid, None, None
        self._actualiser()

    def _finir_groupe(self):
        self.groupe_cible = None
        self._actualiser()

    def _finir_voie(self):
        self.voie_cible = None
        self._actualiser()

    def _viser_voie(self, pid: str, vid: str):
        self.voie_cible, self.groupe_cible, self.inserer_apres = (pid, vid), None, None
        self._actualiser()

    def _defaire_groupe(self, g):
        self.ctrl.memoriser_manip()
        R.defaire_groupe(self.m, g.id)
        if self.groupe_cible == g.id:
            self.groupe_cible = None
        self._toucher(True)
        self.ctrl.toast.emit(f"Grande étape « {g.nom} » défaite : ses étapes restent (Ctrl+Z pour annuler)")

    def _communes(self) -> QWidget:
        m, c = self.m, self.m.communes
        f, cl = carte()
        cl.addWidget(etiquette("2 · Conditions communes à toutes les étapes", "titreCarte"))
        cl.addWidget(etiquette("Active ce qui est identique partout (par exemple l’agitation), puis applique-le au flux. "
                               "Tu pourras ajuster chaque étape ensuite.", secondaire=True, wrap=True))
        g = QGridLayout()
        defs = [("temperature_c", "Chauffage", "Température", "°C"), ("agitation_trmin", "Agitation", "Vitesse", "tr/min"),
                ("vide", "Sous vide", "Pression (facultatif)", "mbar")]
        for k, (cle, lib, lib_v, unite) in enumerate(defs):
            if cle == "agitation_trmin":
                unite = c.vitesse_unite if c.vitesse_unite in UNITES_VITESSE else "tr/min"
            on = (c.vide is not None) if cle == "vide" else getattr(c, cle) is not None
            g.addWidget(self._condition(lib, on, lambda cle=cle: (R.basculer_commune(m, cle), self._toucher(True)),
                                        (c.vide.mbar if c.vide else None) if cle == "vide" else getattr(c, cle), lib_v, unite,
                                        lambda v, cle=cle: self._set_commune(cle, v), *self._vitesse_commune(cle)), 0, k)
        cl.addLayout(g)
        rem = ToggleSwitch("Remplacer aussi les valeurs déjà saisies", self.remplacer)
        rem.toggled.connect(lambda v: setattr(self, "remplacer", v))
        cl.addWidget(rem)
        ap = bouton(f"Appliquer à toutes les étapes ({len(m.etapes)})", self._appliquer, accent=True)
        ap.setEnabled(bool(m.etapes))
        cl.addWidget(ligne(ap, "stretch"))
        cl.addWidget(etiquette("Les étapes que tu ajouteras ensuite reprennent ces conditions automatiquement.", secondaire=True))
        return f

    def _vitesse_commune(self, cle: str) -> tuple:
        """(liste des vitesses, sélecteur d'unité tr/min ou RCF) pour l'agitation commune ; (None, None) pour les autres conditions."""
        if cle != "agitation_trmin":
            return None, None
        c, r = self.m.communes, self.ctrl.reglages
        u = c.vitesse_unite if c.vitesse_unite in UNITES_VITESSE else "tr/min"
        unite = Liste(list(UNITES_VITESSE), u, vide=None, libelles={"tr/min": "tr/min", "g": "RCF (g)"})
        unite.setMinimumWidth(110)
        unite.setAccessibleName("Unité de la vitesse commune : tr/min ou RCF (g)")
        unite.choisi.connect(self._changer_unite_vitesse_commune)
        return (r.vitesses_rcf if u == "g" else r.vitesses_agitation), unite

    def _changer_unite_vitesse_commune(self, unite: str):
        r, c = self.ctrl.reglages, self.m.communes
        liste = r.vitesses_rcf if unite == "g" else r.vitesses_agitation
        c.vitesse_unite = unite
        if c.agitation_trmin is not None and liste:
            c.agitation_trmin = liste[0]
        self._toucher(True)

    def _set_commune(self, cle, v):
        c = self.m.communes
        if cle == "vide":
            if c.vide is not None:
                c.vide.mbar = v
        elif v is not None:
            setattr(c, cle, v)
        self._toucher()

    def _condition(self, libelle, on, basculer, valeur, lib_v, unite, changer, choix: list[float] | None = None, extra: QWidget | None = None) -> QWidget:
        sf = QFrame()
        sf.setObjectName("sousCarte")
        v = QVBoxLayout(sf)
        v.setContentsMargins(12, 10, 12, 10)
        t = ToggleSwitch(libelle, on)
        t.toggled.connect(lambda *_: basculer())
        v.addWidget(t)
        if on and choix is not None:  # vitesse choisie dans la liste des Réglages (ou « Autre valeur… »)
            lv = ChoixVitesse(choix, valeur, unite)
            lv.choisi.connect(lambda val: (changer(val), self._toucher(val is None or val not in choix)))
            v.addWidget(champ(lib_v, lv) if extra is None else ligne(champ(lib_v, lv), champ("Unité", extra), espacement=10))
        elif on:
            nb = NumberBox(valeur, unite)
            nb.valeur.connect(changer)
            v.addWidget(champ(lib_v, nb))
        v.addStretch(1)
        return sf

    def _appliquer(self):
        n = R.appliquer_communes(self.m, self.remplacer)
        self._toucher(True)
        self.ctrl.toast.emit(f"Appliqué à {n} étape{'s' if n > 1 else ''}" if n else "Rien à appliquer : active d’abord une condition")

    def _ajouter_etape(self, op: str):
        op = (op or "").strip().lower()
        if not op:
            self.ctrl.toast.emit("Écris le nom de l’étape")
            return
        gc = self.m.groupe(self.groupe_cible)
        if self.voie_cible and self.m.parallele(self.voie_cible[0]):  # ajout dans une voie du bloc en parallèle
            e = R.ajouter_etape(self.m, op, None, reglages=self.ctrl.reglages)
            R.placer_dans_voie(self.m, e.id, *self.voie_cible)
        elif gc is not None:  # ajout dans la grande étape en cours, après sa dernière sous-étape
            nums = R.numeros_groupe(self.m, gc.id)
            R.ajouter_etape(self.m, op, nums[-1] - 1 if nums else None, groupe_id=gc.id, reglages=self.ctrl.reglages)
        else:
            R.ajouter_etape(self.m, op, self.inserer_apres, reglages=self.ctrl.reglages)
            if self.inserer_apres is not None:
                self.inserer_apres += 1
        self._toucher(True)

    def _inserer(self, i):
        self.inserer_apres = i
        self.groupe_cible = None
        self.voie_cible = None
        self._actualiser()

    # ------------------------------------------------------------ glisser-déposer
    def _deposer(self, genre: str, ident: str, cible_id: str, avant: bool):
        """Une étape ou une grande étape déposée sur une ligne d'étape."""
        self.ctrl.memoriser_manip()
        ok = (R.deplacer_etape_vers if genre == "etape" else R.deplacer_groupe_vers)(self.m, ident, cible_id, avant)
        if ok:
            self._toucher(True)
            self.ctrl.toast.emit("Déplacée (Ctrl+Z pour annuler)")

    def _deposer_sur_groupe(self, genre: str, ident: str, g, idx: list[int], avant: bool):
        """Une étape déposée dans le cadre d'une grande étape (elle y entre) ou une grande étape déposée avant / après celle-ci."""
        self.ctrl.memoriser_manip()
        if genre == "etape":
            R.placer_dans_groupe(self.m, ident, g.id)
            self._toucher(True)
            self.ctrl.toast.emit(f"Étape rangée dans {g.nom} (Ctrl+Z pour annuler)")
        elif idx:
            self._deposer(genre, ident, self.m.etapes[idx[0] if avant else idx[-1]].id, avant)

    def _deposer_ech(self, ech_id: str, etape_id: str | None):
        self.ctrl.memoriser_manip()
        if R.deplacer_echantillon_vers(self.m, ech_id, etape_id):
            self._toucher(True)
            self.ctrl.toast.emit("Échantillon déplacé (Ctrl+Z pour annuler)")

    def _deplacer(self, e, sens):
        R.deplacer_etape(self.m, e.id, sens)
        self._toucher(True)

    def _dupliquer_etape(self, e):
        R.dupliquer_etape(self.m, e.id)
        self._toucher(True)
        self.ctrl.toast.emit("Étape dupliquée")

    def _supprimer_etape(self, e):
        self.ctrl.memoriser_manip()
        R.supprimer_etape(self.m, e.id)
        self._toucher(True)
        self.ctrl.toast.emit(f"Étape supprimée : {cap(e.operation)} (Ctrl+Z pour annuler)")

    def _vers_completer(self):
        self.mode = "comp"
        self.etape_id = DEPART
        self.rafraichir()
        self.ctrl.toast.emit("Complète chaque étape")

    # ------------------------------------------------------------ 2 · Compléter (maître-détail)
    def _completer(self) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(16)
        gauche = QWidget()
        gl = QVBoxLayout(gauche)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.addWidget(ligne(etiquette("Ton flux", "sousTitre"), "stretch", bouton("Modifier le flux", lambda: self._mode("def"))))
        self._colonne = QWidget()
        self._colonne.setProperty("garder", True)  # navigation entre les étapes, même en lecture
        cl = QVBoxLayout(self._colonne)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(8)
        gl.addWidget(self._colonne)
        gl.addWidget(etiquette("Badge : la place sur la frise donne le moment du prélèvement ; le bord droit est la sortie de l’étape.",
                               secondaire=True, wrap=True))
        gl.addStretch(1)
        gauche.setFixedWidth(312)
        self._remplir_colonne()
        # « Ton flux » reste en place quand on fait défiler le détail : il suit le défilement de la page (voir _epingler)
        self._zone_flux = QScrollArea(w)
        self._zone_flux.setWidget(gauche)
        self._zone_flux.setWidgetResizable(True)  # le contenu ne descend jamais sous sa taille minimale : plus de cartes écrasées
        self._zone_flux.setFrameShape(QFrame.Shape.NoFrame)
        self._zone_flux.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._zone_flux.setStyleSheet("QScrollArea{background:transparent;}")
        self._zone_flux.setFixedWidth(330)
        self._hote_flux = QWidget()
        self._hote_flux.setFixedWidth(330)
        self._zone_flux.setParent(self._hote_flux)
        self._hote_flux.installEventFilter(self)
        gauche.installEventFilter(self)  # une carte change de taille (échantillon ajouté, texte long) : on recalcule la hauteur
        h.addWidget(self._hote_flux)
        h.addWidget(self._editeur(), 1, Qt.AlignmentFlag.AlignTop)
        QTimer.singleShot(0, self._epingler)
        return w

    def _defilement_page(self):
        p = self.parentWidget()
        while p is not None and not isinstance(p, QScrollArea):
            p = p.parentWidget()
        return p

    def eventFilter(self, obj, ev):
        if ev.type() in (QEvent.Type.Resize, QEvent.Type.Show, QEvent.Type.LayoutRequest) and (
                obj is getattr(self, "_hote_flux", None) or (getattr(self, "_zone_flux", None) is not None and obj is self._zone_flux.widget())):
            QTimer.singleShot(0, self._epingler)
        return super().eventFilter(obj, ev)

    @staticmethod
    def _figer_hauteurs(contenu: QWidget) -> bool:
        """Chaque carte du flux (et chaque cadre : grande étape, voies en parallèle) garde au moins la hauteur dont elle a besoin à sa largeur :
        quand la place manque, Qt rétrécit d'abord les plus grosses cartes sous leur taille minimale (titre, conditions et frise écrasés)."""
        modifie = False
        for f in reversed(contenu.findChildren(QFrame)):  # les cartes avant les cadres qui les contiennent
            if f.objectName() in ("carteFlux", "groupe", "parallele", "voie") and f.layout() is not None and f.width() > 50:
                lay = f.layout()
                besoin = lay.totalHeightForWidth(f.width()) if lay.hasHeightForWidth() else lay.sizeHint().height()
                if besoin > 0 and f.minimumHeight() != besoin:
                    f.setMinimumHeight(besoin)
                    modifie = True
        return modifie

    def _epingler(self):
        """Place la colonne « Ton flux » en haut de ce qu'on voit : elle ne défile pas avec le détail ; trop longue, elle a son propre ascenseur."""
        hote, zone = getattr(self, "_hote_flux", None), getattr(self, "_zone_flux", None)
        if hote is None or zone is None:
            return
        try:
            defil = self._defilement_page()
            if defil is None:
                return
            if getattr(self, "_defil_connecte", None) is not defil:
                defil.verticalScrollBar().valueChanged.connect(lambda _v: self._epingler())
                self._defil_connecte = defil
            contenu = zone.widget()
            if getattr(self, "_epingle_en_cours", False):
                return
            self._epingle_en_cours = True
            try:
                modifie = self._figer_hauteurs(contenu)
            finally:
                self._epingle_en_cours = False
            if modifie:
                QTimer.singleShot(0, self._epingler)  # une carte a changé de hauteur minimale : on revérifie une fois
            largeur = contenu.width() if contenu.width() > 100 else 312
            haut_contenu = contenu.layout().totalHeightForWidth(largeur) if contenu.layout() else contenu.sizeHint().height()
            if contenu.layout() and haut_contenu > 0 and contenu.minimumHeight() != haut_contenu:
                contenu.setMinimumHeight(haut_contenu)  # jamais moins que la hauteur réellement nécessaire à cette largeur (textes à la ligne) : cartes non écrasées
            vue = defil.viewport().height() - 16
            haut = max(120, min(max(haut_contenu, contenu.minimumSizeHint().height()) + 4, vue))
            hote.setMinimumHeight(haut)
            y_hote = hote.mapTo(defil.widget(), QPoint(0, 0)).y()
            decalage = max(0, defil.verticalScrollBar().value() + 8 - y_hote)
            decalage = min(decalage, max(0, hote.height() - haut))
            zone.setGeometry(0, decalage, 330, haut)
            sel = next((c for c in contenu.findChildren(QFrame) if c.objectName() == "carteFlux" and c.property("sel")), None)
            if sel is not None and not getattr(self, "_sel_vue", None) == self.etape_id:
                zone.ensureWidgetVisible(sel, 0, 20)
                self._sel_vue = self.etape_id
        except RuntimeError:
            pass  # widgets détruits pendant une reconstruction

    def _remplir_colonne(self):
        m, lay = self.m, self._colonne.layout()
        vider(lay)
        lab, ech = etiquettes(m), echantillons_tries(m)
        resultats = self._resultats_flux()

        def ligne_resultats(p):
            """Valeurs principales rendues par les labos (ana explorer), sous la pastille de l'échantillon ; toutes au survol."""
            from mat_methode.analyses_ptt import resume_echantillon
            e = resultats.get(lab[p.id])
            if e is None:
                return None
            court = resume_echantillon(resultats["_res"], lab[p.id], limite=4)
            from html import escape
            morceaux = [escape(x).replace(" ", "&nbsp;") for x in court.split(" · ")]  # retour à la ligne entre deux analyses seulement
            w = etiquette(f"<span style='color:{theme.P.succes}'><b>✓</b></span> " + " · ".join(morceaux), wrap=True)
            w.setObjectName("resultatsEch")
            w.setStyleSheet("QLabel#resultatsEch{font-size:8.5pt;padding-left:4px;}")
            w.setToolTip(f"Résultats {lab[p.id]} (ana explorer" + (f", {', '.join(e['labos'])}" if e.get("labos") else "") + ") :\n"
                         + resume_echantillon(resultats["_res"], lab[p.id]).replace(" · ", "\n"))
            return w

        def pill(p):
            n = R.numero_etape(m, p)
            q = "avant" if n == 0 else (f"à {fmt_dur(p.temps_min)}" if p.temps_min is not None else "à ?") if p.moment == "pendant" else "sortie"
            w = ambre(f"{lab[p.id]} · {fmt_vol(p.volume_ml or 0)} mL {q}" + (f" · {p.labo}" if p.labo else ""), code_badge(lab[p.id]))
            if not self.consultation:  # glisser l'échantillon vers une autre étape (ou le départ)
                rendre_source(w, "echantillon", p.id, lambda p=p: self.aller(p.etape_id or self.ordre()[0]))
                w.setToolTip("Glisser vers une autre étape pour déplacer l’échantillon")
            return w

        dep = [p for p in ech if R.numero_etape(m, p) == 0]
        if not self._departs():  # flux qui commence par des voies : un « Départ » par voie, dans le cadre en parallèle
            c = self._carte_flux(DEPART, None, "Départ")
            if not self.consultation:
                rendre_cible(c, {"echantillon": "dedans"}, lambda genre, ident, avant: self._deposer_ech(ident, None))
            c.layout().addWidget(etiquette(f"{m.contexte.matiere or 'matière ?'}" + (f" · {fmt_vol(m.contexte.volume_depart_ml)} mL"
                                                                                     if m.contexte.volume_depart_ml is not None else ""), secondaire=True))
            for p in dep:
                c.layout().addWidget(pill(p))
                if (r := ligne_resultats(p)) is not None:
                    c.layout().addWidget(r)
            lay.addWidget(c)
        volumes = {lg.indice: lg for lg in volumes_par_etape(m)}
        cible, cadre = lay, None
        for i, e in enumerate(m.etapes):
            g = m.groupe(e.groupe_id)
            debut = g is not None and (i == 0 or m.etapes[i - 1].groupe_id != g.id)
            par = m.parallele(e.parallele_id)
            if par is not None:  # étapes en parallèle : cadre ambre, voies l'une sous l'autre avec leur lettre
                prec = m.etapes[i - 1] if i > 0 else None
                if prec is None or prec.parallele_id != par.id:
                    cadre = QFrame()
                    cadre.setObjectName("parallele")
                    cadre.setStyleSheet(f"QFrame#parallele{{border:2px solid {theme.P.ambre_trait};border-radius:8px;background:{theme.P.ambre_fond};}}")
                    cv = QVBoxLayout(cadre)
                    cv.setContentsMargins(6, 6, 6, 6)
                    cv.setSpacing(6)
                    t = etiquette("EN PARALLÈLE", "etiquetteChamp")
                    t.setStyleSheet(f"color:{theme.P.ambre_texte};font-weight:700;padding-left:4px;")
                    cv.addWidget(t)
                    lay.addWidget(cadre)
                    cible = cv
                if prec is None or prec.parallele_id != par.id or prec.voie_id != e.voie_id:
                    tv = etiquette(f"VOIE {R.lettre_voie(m, par.id, e.voie_id)}" + (f" · {next((v.nom for v in par.voies if v.id == e.voie_id), '')}".rstrip(" ·")),
                                   "etiquetteChamp")
                    tv.setStyleSheet(f"color:{theme.P.ambre_texte};padding-left:4px;")
                    cible.addWidget(tv)
                    if R.bloc_au_depart(m) is par:  # bloc qui ouvre le flux : le Départ de cette voie
                        voie_courante = next(v for v in par.voies if v.id == e.voie_id)
                        cible.addWidget(self._carte_depart_voie(voie_courante, R.lettre_voie(m, par.id, voie_courante.id)))
            elif g is None:
                cible = lay
            elif debut:  # cadre de la grande étape (ex. DEGUMMING · étapes 2 à 4)
                fin = i
                while fin + 1 < len(m.etapes) and m.etapes[fin + 1].groupe_id == g.id:
                    fin += 1
                cadre = QFrame()
                cadre.setObjectName("groupe")
                cadre.setStyleSheet(f"QFrame#groupe{{border:1px solid {theme.P.accent};border-left:4px solid {theme.P.accent};"
                                    f"border-radius:8px;background:{theme.P.info_fond};}}")
                cv = QVBoxLayout(cadre)
                cv.setContentsMargins(6, 6, 6, 6)
                cv.setSpacing(6)
                t = etiquette(f"{g.nom.upper()} · {R.plage(list(range(i + 1, fin + 2)))}", "etiquetteChamp")
                t.setStyleSheet(f"color:{theme.P.accent};font-weight:700;padding-left:4px;")
                cv.addWidget(t)
                lay.addWidget(cadre)
                cible = cv
            if self._reunit_les_voies(i):  # carte « Réunion » : volume de chaque voie et total, comme le Départ d'une voie
                cible.addWidget(self._carte_reunion(i, e, volumes))
            c = self._carte_flux(e.id, i + 1, cap(e.operation))
            if not self.consultation:
                rendre_cible(c, {"echantillon": "dedans"}, lambda genre, ident, avant, e=e: self._deposer_ech(ident, e.id))
            cl = c.layout()
            for r in e.reactifs:
                if r.nom:
                    cl.addWidget(etiquette(f"• <b>{r.nom}</b> <span style='color:{theme.P.texte2}'>{r.quantite_complete}</span>"
                                           + (f" · contact {r.contact_complet}" if r.contact_complet else ""), wrap=True))
                    if r.consigne.strip():
                        cl.addWidget(etiquette(f"<i>Consigne : {r.consigne.strip()}</i>", wrap=True))
            cond = " · ".join(x for x in [resume_conditions(e)] + autres_conditions(e) if x)
            cl.addWidget(etiquette(cond, "conditions", wrap=True) if cond else etiquette("conditions à compléter", "aCompleter"))
            if e.equipements:
                cl.addWidget(etiquette(" · ".join(e.equipements), secondaire=True, wrap=True))
            if e.remarque.strip():
                cl.addWidget(etiquette(f"<i>Consigne : {e.remarque.strip()}</i>", wrap=True))
            if self._matiere_recue_visible(i):
                cl.addWidget(self._lignes_matiere_recue(i, volumes))
            ps = [p for p in ech if p.etape_id == e.id]
            if e.duree_min or ps:
                cl.addWidget(Frise(e.duree_min, [(position(p, e), code_badge(lab[p.id])) for p in ps]))
            for p in ps:
                cl.addWidget(pill(p))
                if (r := ligne_resultats(p)) is not None:
                    cl.addWidget(r)
            cible.addWidget(c)
        if getattr(self, "_zone_flux", None) is not None:
            QTimer.singleShot(0, self._epingler)  # la colonne a changé (échantillon ajouté…) : hauteur recalculée

    def _premiere_de_voie(self, i: int) -> bool:
        m, e = self.m, self.m.etapes[i]
        return e.parallele_id is not None and (i == 0 or m.etapes[i - 1].parallele_id != e.parallele_id or m.etapes[i - 1].voie_id != e.voie_id)

    def _reunit_les_voies(self, i: int) -> bool:
        return i > 0 and self.m.etapes[i - 1].parallele_id is not None and self.m.etapes[i].parallele_id is None

    def _matiere_recue_visible(self, i: int) -> bool:
        """Carte du flux : la matière reçue s'affiche sur la 1re étape d'une voie (hors départ, qui a sa carte) et sur l'étape qui réunit les voies."""
        e = self.m.etapes[i]
        return (self._premiere_de_voie(i) and R.bloc_au_depart(self.m) is not self.m.parallele(e.parallele_id)) or self._reunit_les_voies(i)

    def _lignes_matiere_recue(self, i: int, volumes: dict) -> QWidget:
        m, e = self.m, self.m.etapes[i]
        lg = volumes.get(i)
        if self._reunit_les_voies(i):
            par = m.parallele(m.etapes[i - 1].parallele_id)
            morceaux = []
            for vo in par.voies:
                idx = [k for k, x in enumerate(m.etapes) if x.parallele_id == par.id and x.voie_id == vo.id]
                if idx and idx[-1] in volumes:
                    pris = e.apports.get(vo.id, volumes[idx[-1]].sortie)
                    morceaux.append(f"voie {R.lettre_voie(m, par.id, vo.id)} {fmt_vol(pris)} mL")
            texte = "Reçoit : " + " + ".join(morceaux) + (f" = <b>{fmt_vol(lg.entree)} mL</b>" if lg else "")
        else:
            par = m.parallele(e.parallele_id)
            vo = next(v for v in par.voies if v.id == e.voie_id)
            texte = f"Reçoit <b>{fmt_vol(lg.entree)} mL</b>" if lg else "Matière reçue à saisir"
            if vo.part is not None:
                texte += f" ({fmt_num(vo.part)} {vo.part_unite} de l’étape précédente)"
            ajouts = [f"{x.nom} {x.quantite_complete}".strip() for x in vo.autres if x.nom]
            if ajouts:
                texte += " + " + " + ".join(ajouts)
        return etiquette(texte, secondaire=True, wrap=True)

    def _carte_depart_voie(self, vo, lettre: str) -> QFrame:
        """Départ d'une voie d'un bloc qui ouvre le flux : ses matières de départ et son volume."""
        c = self._carte_flux(f"depart:{vo.id}", None, f"Départ · voie {lettre}")
        for x in vo.autres:
            if x.nom:
                inv = self.ctrl.reglages.reactif(x.nom)
                ident = (inv.scirius if inv and inv.scirius else x.reference) or ""
                c.layout().addWidget(etiquette(f"<b>{x.nom}</b> {x.quantite_complete}" + (f" <span style='color:{theme.P.texte2}'>· {ident}</span>" if ident else ""), wrap=True))
        total = volume_ajoute(vo)
        if len([x for x in vo.autres if x.nom]) != 1 or not total:  # une seule matière : son volume est déjà écrit
            c.layout().addWidget(etiquette(f"{fmt_vol(total)} mL" if total else "matière et volume à saisir", secondaire=True))
        return c

    def _carte_reunion(self, i: int, e, volumes: dict) -> QFrame:
        """Réunion des voies avant l'étape i : volume pris dans chaque voie et volume réuni (un clic ouvre l'étape qui réunit)."""
        reu = reunion_volumes(self.m, i, {k: lg for k, lg in volumes.items()})
        lettres = " + ".join(v["lettre"] for v in reu["voies"])
        c = self._carte_flux(e.id, None, f"RÉUNION · voies {lettres}")
        c.setProperty("sel", False)
        p = theme.P  # vert « succès » : se repère d'un coup d'œil entre les étapes, comme le Départ d'une voie
        c.setStyleSheet(f"QFrame#carteFlux{{background:{p.succes_fond};border:1px solid {p.succes};border-left:4px solid {p.succes};border-radius:8px;}}"
                        f"QFrame#carteFlux:hover{{border-color:{p.succes};}}")
        for v in reu["voies"]:
            c.layout().addWidget(etiquette(f"<b>Voie {v['lettre']}</b> · {fmt_vol(v['volume_ml'])} mL", wrap=True))
        total = etiquette(f"Total {fmt_vol(reu['volume_ml'])} mL" if reu["volume_ml"] is not None else "volume à saisir", wrap=True)
        total.setStyleSheet(f"color:{p.succes};font-weight:700;font-size:11pt;")
        c.layout().addWidget(total)
        return c

    def _carte_flux(self, ident, n, titre) -> QFrame:
        f = QFrame()
        f.setObjectName("carteFlux")
        f.setProperty("sel", self.etape_id == ident)
        f.setCursor(Qt.CursorShape.PointingHandCursor)
        f.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        f.setAccessibleName(f"{'Étape ' + str(n) + ' : ' if n else ''}{titre}")
        v = QVBoxLayout(f)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(5)
        h = QHBoxLayout()
        h.setSpacing(8)
        if n:
            h.addWidget(numero(n), 0, Qt.AlignmentFlag.AlignTop)
        t = TitreAjuste(titre)
        h.addWidget(t, 1)
        v.addLayout(h)
        f.mousePressEvent = lambda _e, ident=ident: self.aller(ident)
        f.keyPressEvent = lambda ev, ident=ident: self.aller(ident) if ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Space, Qt.Key.Key_Enter) else None
        return f

    def aller(self, ident):
        self.etape_id = ident
        self._actualiser()

    def _departs(self) -> list:
        """(bloc, voie) des voies d'un bloc en parallèle qui ouvre le flux : chacune a son propre « Départ » (matière et volume)."""
        par = R.bloc_au_depart(self.m)
        return [(par, v) for v in par.voies] if par is not None else []

    def ordre(self):
        departs = self._departs()
        return ([f"depart:{v.id}" for _, v in departs] if departs else [DEPART]) + [e.id for e in self.m.etapes]

    def precedente(self):
        o = self.ordre()
        i = o.index(self.etape_id) if self.etape_id in o else 0
        if self.mode == "comp" and i > 0:
            self.aller(o[i - 1])

    def suivante(self):
        o = self.ordre()
        i = o.index(self.etape_id) if self.etape_id in o else 0
        if self.mode != "comp":
            return
        if i >= len(o) - 1:
            self.voir_rapport.emit()
        else:
            self.aller(o[i + 1])

    # ------------------------------------------------------------ éditeur de l'étape
    def _editeur(self) -> QWidget:
        m = self.m
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        e = m.etape(self.etape_id)
        avert = [x for x in R.avertissements(m, self.ctrl.manips)]
        depart_voie = next(((par, vo) for par, vo in self._departs() if self.etape_id == f"depart:{vo.id}"), None)
        if e is None and depart_voie is not None:  # flux qui commence par des voies : Départ propre à la voie
            par, vo = depart_voie
            lettre = R.lettre_voie(m, par.id, vo.id)
            lay.addWidget(etiquette(f"Départ · voie {lettre}" + (f" ({vo.nom})" if vo.nom.strip() else ""), "sousTitre"))
            lay.addWidget(self._carte_matiere_voie(par, vo, []))
            lay.addWidget(etiquette("Cette voie démarre avec ces matières ; le volume de départ du flux est la somme des voies.", secondaire=True, wrap=True))
        elif e is None:
            lay.addWidget(etiquette("Départ", "sousTitre"))
            f, cl = carte()
            cl.addWidget(etiquette("Matière de départ", "titreCarte"))
            mat = ChampTexte(m.contexte.matiere)
            mat.modifie.connect(lambda v: (setattr(m.contexte, "matiere", v), self._toucher()))
            sc = ChampTexte(m.contexte.scirius, "à saisir", mono=True)
            sc.modifie.connect(lambda v: (setattr(m.contexte, "scirius", v.strip()), self._toucher()))
            fo = ChampTexte(m.contexte.fournisseur)
            fo.modifie.connect(lambda v: (setattr(m.contexte, "fournisseur", v), self._toucher()))
            em = ChampTexte(m.contexte.emplacement, "ex. chambre froide, étagère 3")
            em.modifie.connect(lambda v: (setattr(m.contexte, "emplacement", v), self._toucher()))
            cl.addWidget(champ("Matière (charge)", mat))
            cl.addWidget(ligne(champ("N° Scirius de la charge", sc), champ("Fournisseur", fo), champ("Emplacement", em)))
            cl.addWidget(ligne(bouton("Chercher la charge dans Scirius…", self._scirius_charge, accent=True,
                                      tip="Remplit le nom, le n° Scirius, le fournisseur et l’emplacement depuis le fichier Scirius de SharePoint"),
                               etiquette("Pas dans le fichier ? Saisis les champs à la main.", secondaire=True), "stretch"))
            lay.addWidget(f)
        else:
            i = m.etapes.index(e)
            g = m.groupe(e.groupe_id)
            if g is not None:
                gl = etiquette(f"{g.nom} · {R.plage(R.numeros_groupe(m, g.id))}", "etiquetteChamp")
                gl.setStyleSheet(f"color:{theme.P.accent};font-weight:700;")
                lay.addWidget(gl)
            lay.addWidget(ligne(numero(i + 1, 28), etiquette(cap(e.operation), "sousTitre"), "stretch"))
            par_e = m.parallele(e.parallele_id)
            if par_e is not None and self._premiere_de_voie(i):  # 1re étape d'une voie : la matière reçue par la voie
                lay.addWidget(self._carte_matiere_voie(par_e, next(v for v in par_e.voies if v.id == e.voie_id), []))
            elif self._reunit_les_voies(i):  # étape qui réunit les voies : quantité prise de chacune
                lay.addWidget(self._panneau_convergence(i))
            lay.addWidget(self._conditions(e))
            lay.addWidget(self._reactifs(e))
        for a in avert:
            lay.addWidget(InfoBar(a))
        lay.addWidget(self._echantillons(e))
        o = self.ordre()
        i = o.index(self.etape_id)
        prec = bouton("←  Étape précédente", self.precedente, tip="Étape précédente (Alt+←)")
        prec.setEnabled(i > 0)
        fin = ("Terminer : voir le rapport" if m.etat == "realisee" else "Terminer : voir le protocole") if self.contexte == "definition" else ""
        suiv = bouton(fin if i >= len(o) - 1 else "Étape suivante  →", self.suivante, accent=True, tip="Étape suivante (Alt+→)")
        suiv.setVisible(bool(suiv.text()))
        nav = ligne(prec, "stretch", suiv)
        nav.setProperty("garder", True)
        lay.addWidget(nav)
        return w

    def _conditions(self, e) -> QWidget:
        x = Expander("1 · Conditions opératoires")
        i = self.m.etapes.index(e)
        if i > 0:
            prec = self.m.etapes[i - 1]
            x.ajouter(ligne(bouton(f"⧉  Reprendre les conditions de l’étape {i} · {cap(prec.operation)}", lambda: self._copier_conditions(e),
                                   tip="Copie température, durée, agitation, membrane, sous vide et autres conditions de l’étape précédente"),
                            "stretch"))
        g = QGridLayout()
        defs = [("temperature_c", "Chauffage", "Température", "°C"),
                ("agitation_trmin", "Vitesse de centrifugation" if est_centrifugation(e.operation) else "Agitation", "Vitesse", "tr/min"),
                ("vide", "Sous vide", "Pression en mbar (facultatif)", "mbar"), ("filtre_um", "Membrane filtrante", "Taille des pores", "µm")]
        for k, (cle, lib, lib_v, unite) in enumerate(defs):
            on = (e.vide is not None) if cle == "vide" else getattr(e, cle) is not None
            val = (e.vide.mbar if e.vide else None) if cle == "vide" else getattr(e, cle)
            choix, extra, u = None, None, unite
            if cle == "agitation_trmin":  # vitesse choisie dans la liste des Réglages ; centrifugation : tr/min ou RCF (g)
                u = e.vitesse_unite if e.vitesse_unite in UNITES_VITESSE else "tr/min"
                choix = self.ctrl.reglages.vitesses_rcf if u == "g" else self.ctrl.reglages.vitesses_agitation
                extra = Liste(list(UNITES_VITESSE), u, vide=None, libelles={"tr/min": "tr/min", "g": "RCF (g)"})  # tr/min ou RCF (g), agitation comme centrifugation
                extra.setMinimumWidth(110)
                extra.setAccessibleName("Unité de la vitesse : tr/min ou RCF (g)")
                extra.choisi.connect(lambda nouv, e=e: self._changer_unite_vitesse(e, nouv))
            g.addWidget(self._condition(lib, on, lambda cle=cle: (R.basculer_condition(e, cle), self._toucher(True)), val, lib_v, u,
                                        lambda v, cle=cle: self._set_cond(e, cle, v), choix, extra), k // 2, k % 2)
        wg = QWidget()
        wg.setLayout(g)
        x.ajouter(wg)
        du = e.duree_unite if e.duree_unite in DUREES else "min"  # durée stockée en minutes, saisie dans l'unité choisie
        duree = NumberBox(None if e.duree_min is None else round(e.duree_min / DUREES[du], 4), "", "ex. 30")
        duree.valeur.connect(lambda v: (setattr(e, "duree_min", None if v is None else v * DUREES[du]), self._toucher()))
        unites_d = Liste([u for u in DUREES if u in self.ctrl.reglages.unites_duree or u == du], du, vide=None)
        unites_d.setMinimumWidth(110)
        unites_d.setAccessibleName("Unité de la durée (liste dans Réglages › Unités de durée)")
        unites_d.choisi.connect(lambda u, e=e: (setattr(e, "duree_unite", u), self._toucher(True)))
        mat = [ChipSupprimable(q, lambda k=k: self._retirer_materiel(e, k)) for k, q in enumerate(e.equipements)]
        proposes = [q for q in self.ctrl.reglages.materiels if q not in e.equipements]
        nouveau = ListeSaisie(proposes, "Choisir ou taper un matériel")
        nouveau.setAccessibleName("Matériel à ajouter")
        nouveau.valide.connect(lambda v: self._ajouter_materiel(e, v))
        mat += [nouveau, bouton("+ Ajouter", lambda: self._ajouter_materiel(e, nouveau.currentText())),
                bouton("Liste du matériel", lambda: self.voir_reglages.emit("materiel"), lien=True)]
        duree.setMaximumWidth(200)
        x.ajouter(ligne(champ("Durée de l’étape", duree), champ("Unité", unites_d), "stretch", espacement=10))
        x.ajouter(champ("Matériel utilisé", flux_widgets(mat)))
        for k, a in enumerate(e.autres):
            n = ChampTexte(a.nom, "ex. pH, atmosphère")
            n.modifie.connect(lambda v, a=a: (setattr(a, "nom", v), self._toucher()))
            v = ChampTexte(a.valeur)
            v.modifie.connect(lambda val, a=a: (setattr(a, "valeur", val), self._toucher()))
            x.ajouter(ligne(champ("Autre condition", n), champ("Valeur", v),
                            icone("✕", "Retirer cette condition", lambda k=k: self._retirer_autre(e, k), danger=True)))
        x.ajouter(ligne(bouton("+ Autre condition", lambda: (e.autres.append(Condition()), self._toucher(True)), ajout=True), "stretch"))
        rem = ChampTexte(e.remarque, "Consigne ou remarque : carte du flux, PDF, et entre parenthèses à la fin de la phrase de l’étape")
        rem.modifie.connect(lambda v: (setattr(e, "remarque", v), self._toucher()))
        x.ajouter(champ("Consignes / remarques (facultatif)", rem))
        return x

    def _changer_unite_vitesse(self, e, unite: str):
        """tr/min <-> RCF (g) : la vitesse repart de la 1re valeur de la liste de la nouvelle unité."""
        r = self.ctrl.reglages
        liste = r.vitesses_rcf if unite == "g" else r.vitesses_agitation
        e.vitesse_unite = unite
        if e.agitation_trmin is not None and liste:
            e.agitation_trmin = liste[0]
        self._toucher(True)

    def _copier_conditions(self, e):
        self.ctrl.memoriser_manip()
        src = R.copier_conditions_precedentes(self.m, e.id)
        if src is not None:
            self._toucher(True)
            self.ctrl.toast.emit(f"Conditions reprises de « {cap(src.operation)} » (Ctrl+Z pour annuler)")

    def _set_cond(self, e, cle, v):
        if cle == "vide":
            if e.vide is not None:
                e.vide.mbar = v
        else:
            setattr(e, cle, v)
        self._toucher()

    def _ajouter_materiel(self, e, v):
        v = v.strip()
        if v and v not in e.equipements:
            e.equipements.append(v)
            r = self.ctrl.reglages
            ajoutees = O.appliquer_conditions_materiel(r, e)  # conditions particulières de ce matériel (Réglages › Conditions par matériel)
            if ajoutees:
                self.ctrl.toast.emit("Conditions ajoutées : " + ", ".join(ajoutees))
            if not any(norm(v) == norm(x) for x in r.materiels):  # tapé à la main : ajouté aux Réglages
                r.materiels.append(v)
                self.ctrl.toucher_reglages()
            self._toucher(True)

    def _retirer_materiel(self, e, k):
        self.ctrl.memoriser_manip()
        e.equipements.pop(k)
        self._toucher(True)

    def _retirer_autre(self, e, k):
        self.ctrl.memoriser_manip()
        e.autres.pop(k)
        self._toucher(True)

    def _reactifs(self, e) -> QWidget:
        n = len(e.reactifs)
        x = Expander("2 · Réactifs", f"{n} dans cette étape" if n else "aucun pour l’instant")
        x.ajouter(self._table_matieres(e.reactifs, "réactif"))
        x.ajouter(flux_widgets([bouton("Gérer la liste des réactifs (Réglages)", lambda: self.voir_reglages.emit("reactifs"), lien=True)]))
        return x

    def _table_matieres(self, liste: list, mot: str = "matière") -> QWidget:
        """Tableau des matières d'une étape (« réactifs ») ou d'une voie : une ligne par matière, choisie dans Scirius ou saisie à la main,
        avec référence, quantité et unité. Autant de lignes que nécessaire."""
        r = self.ctrl.reglages
        noms = [y.nom for y in r.reactifs]
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        for k, re_ in enumerate(liste):
            inv = r.reactif(re_.nom) if re_.nom else None
            sf = QFrame()
            sf.setObjectName("sousCarte")
            lv = QVBoxLayout(sf)
            lv.setContentsMargins(10, 6, 10, 6)
            lv.setSpacing(4)
            origine = etiquette("Scirius" if inv and inv.scirius else "À la main", "etiquetteChamp")
            origine.setFixedWidth(62)
            origine.setToolTip("Scirius : produit avec un n° Scirius. À la main : référence saisie ici.")
            nom = ChampTexte(re_.nom, f"Nom du {mot}", suggestions=noms)
            nom.modifie.connect(lambda val, re_=re_: (setattr(re_, "nom", val), self._toucher()))
            ref = ChampTexte(re_.reference, "référence à la main", mono=True)
            ref.modifie.connect(lambda val, re_=re_: (setattr(re_, "reference", val), self._toucher()))
            q = ChampTexte(re_.quantite, "quantité ou ratio", mono=True)
            q.setMaximumWidth(140)
            q.modifie.connect(lambda val, re_=re_: (setattr(re_, "quantite", val), self._toucher()))
            u = Liste(r.unites_reactifs, re_.unite, vide="—")
            u.setMinimumWidth(80)
            u.setMaximumWidth(100)
            u.setAccessibleName("Unité de la quantité (liste dans Réglages › Unités des réactifs)")
            u.choisi.connect(lambda val, re_=re_: (setattr(re_, "unite", val), self._toucher()))
            lv.addWidget(ligne(origine, nom, icone("🔎", f"Chercher dans Scirius (ligne {k + 1})", lambda re_=re_: self._scirius_reactif(re_)),
                               icone("✕", f"Retirer le {mot} {k + 1}", lambda k=k: (liste.pop(k), self._toucher(True)), danger=True), espacement=6))
            lv.addWidget(ligne(ref, q, u, espacement=6))
            ct = ChampTexte(re_.contact, "temps de contact")
            ct.setMaximumWidth(130)
            ct.modifie.connect(lambda val, re_=re_: (setattr(re_, "contact", val), self._toucher()))
            cu = Liste(r.unites_duree or list(DUREES), re_.contact_unite, vide=None)
            cu.setMinimumWidth(90)
            cu.setMaximumWidth(110)
            cu.setAccessibleName("Unité du temps de contact (liste dans Réglages › Unités de durée)")
            cu.choisi.connect(lambda val, re_=re_: (setattr(re_, "contact_unite", val), self._toucher()))
            cs = ChampTexte(re_.consigne, "consigne du réactif (visible dans le flux et les PDF)")
            cs.setMinimumWidth(280)
            cs.modifie.connect(lambda val, re_=re_: (setattr(re_, "consigne", val), self._toucher()))
            lv.addWidget(ligne(ct, cu, cs, espacement=6))
            sc = ChampTexte(inv.scirius if inv else "", "n° Scirius à saisir", mono=True)
            em = ChampTexte(inv.emplacement if inv else "", "emplacement (armoire, étagère…)")
            fo = ChampTexte(inv.fournisseur if inv else "", "fournisseur")
            for cle, champ_ in (("scirius", sc), ("emplacement", em), ("fournisseur", fo)):  # mémorisés par nom de produit, repris partout
                champ_.setEnabled(bool(re_.nom.strip()))
                champ_.setToolTip("Écris d’abord le nom du produit" if not re_.nom.strip() else "")
                champ_.modifie.connect(lambda val, cle=cle, re_=re_: self._inv_par_nom(re_, cle, val))
            lv.addWidget(ligne(sc, em, fo, espacement=6))

            def nom_saisi(re_=re_, nom=nom, origine=origine, sc=sc, em=em, fo=fo):
                """Nom validé : il rejoint les produits connus (Réglages) et les champs se remplissent avec ce qui est déjà mémorisé."""
                texte = nom.text().strip()
                re_.nom = texte
                if texte and r.reactif(texte) is None:
                    r.assurer_reactif(texte)
                    self.ctrl.toucher_reglages()
                i = r.reactif(texte) if texte else None
                origine.setText("Scirius" if i and i.scirius else "À la main")
                for champ_, val in ((sc, i.scirius if i else ""), (em, i.emplacement if i else ""), (fo, i.fournisseur if i else "")):
                    champ_.setText(val)
                    champ_.setEnabled(bool(texte))
                self._toucher()

            nom.editingFinished.connect(nom_saisi)
            v.addWidget(sf)
        if not liste:
            v.addWidget(etiquette(f"Aucun {mot} pour l’instant.", secondaire=True))
        v.addWidget(flux_widgets([bouton(f"+ {cap(mot)} depuis Scirius…", lambda: self._ajouter_depuis_scirius(liste), ajout=True,
                                         tip="Chercher le produit dans le fichier Scirius : nom, n° Scirius, emplacement et fournisseur sont remplis"),
                                  bouton("+ Référence à la main", lambda: self._ajouter_a_la_main(liste),
                                         tip="Saisir le nom et une référence sans passer par Scirius")]))
        return w

    def _ajouter_a_la_main(self, liste: list):
        liste.append(ReactifEtape(unite=(self.ctrl.reglages.unites_reactifs or [""])[0]))
        self._toucher(True)

    def _ajouter_depuis_scirius(self, liste: list):
        re_ = ReactifEtape(unite=(self.ctrl.reglages.unites_reactifs or [""])[0])
        liste.append(re_)
        self._scirius_reactif(re_)
        if not re_.nom:  # recherche annulée : pas de ligne vide
            liste.remove(re_)
            self._toucher(True)

    def _inv_par_nom(self, re_, cle: str, val: str):
        """N° Scirius, emplacement ou fournisseur saisi sur une ligne : mémorisé pour ce produit (créé si besoin) dans les Réglages."""
        if not re_.nom.strip():
            return
        inv = self.ctrl.reglages.assurer_reactif(re_.nom)
        if inv is not None:
            self._inv(inv, cle, val)

    def _choisir_donneur(self, v):
        m = self.m
        m.contexte.donneur = v
        if R.reference_auto(m, self.ctrl.reglages, self.ctrl.manips):
            self.ctrl.toast.emit(f"Référence : {m.contexte.ref}")
            self._toucher(True)
        else:
            self._toucher()

    def _regenerer_ref(self):
        m = self.m
        if self.ctrl.reglages.personne(m.contexte.donneur) is None:
            self.ctrl.toast.emit("Choisis d’abord le donneur d’ordre")
            return
        if m.contexte.ref.strip() and not R.REF_AUTO.match(m.contexte.ref.strip()):
            from mat_methode.ui.dialogues import confirmer
            if not confirmer(self, "Remplacer la référence ?", f"« {m.contexte.ref} » sera remplacée par une référence automatique.",
                             "Remplacer", danger=False):
                return
        R.reference_auto(m, self.ctrl.reglages, self.ctrl.manips, forcer=True)
        self._toucher(True)

    def _scirius_charge(self):
        from mat_methode.ui.dialogues import chercher_scirius
        c = self.m.contexte
        ln = chercher_scirius(self, self.ctrl.lire_scirius, c.matiere if c.matiere != "Graisse animale" else "", "charge de départ",
                              noms=self.ctrl.reglages.scirius_noms)
        if ln is None:
            return
        from mat_methode.scirius import nom_produit
        c.matiere = nom_produit(ln) or c.matiere
        c.lot = ln.get("batch") or c.lot
        c.scirius = ln.get("stock_item") or c.scirius
        c.fournisseur = ln.get("supplier") or c.fournisseur
        c.emplacement = ln.get("storage") or c.emplacement
        self._toucher(True)
        self.ctrl.toast.emit("Charge remplie depuis Scirius")

    def _scirius_reactif(self, re_):
        from mat_methode.domain import reglages_ops as O
        from mat_methode.ui.dialogues import chercher_scirius
        ln = chercher_scirius(self, self.ctrl.lire_scirius, re_.nom, re_.nom or "réactif", noms=self.ctrl.reglages.scirius_noms)
        if ln is None:
            return
        r = self.ctrl.reglages
        from mat_methode.scirius import nom_produit
        nom = re_.nom or nom_produit(ln)
        if not nom:
            return
        if r.reactif(nom) is None:
            O.ajouter_reactif(r, nom)
        inv = r.reactif(nom)
        inv.scirius = ln.get("stock_item") or inv.scirius
        inv.emplacement = ln.get("storage") or inv.emplacement
        inv.fournisseur = ln.get("supplier") or inv.fournisseur
        inv.lot = ln.get("batch") or inv.lot
        re_.nom = inv.nom
        self.ctrl.toucher_reglages()
        self._toucher(True)
        self.ctrl.toast.emit(f"« {inv.nom} » rempli depuis Scirius")

    def _nouveau_reactif(self, re_):
        """Ajoute un nom de réactif à la liste des Réglages depuis l'étape, et le choisit."""
        from mat_methode.domain import reglages_ops as O
        from mat_methode.ui.dialogues import demander_texte
        nom = demander_texte(self, "Nouveau réactif", "Nom du réactif", "",
                             "Le réactif est ajouté à la liste des Réglages (pour toutes les manips) et choisi pour cette étape. "
                             "Son n° Scirius et son emplacement se renseignent ensuite ici.", bouton_ok="Ajouter")
        if not nom:
            return
        existant = self.ctrl.reglages.reactif(nom)
        if existant is None:
            O.ajouter_reactif(self.ctrl.reglages, nom)
            self.ctrl.toucher_reglages()
            existant = self.ctrl.reglages.reactif(nom)
            self.ctrl.toast.emit(f"« {existant.nom} » ajouté aux Réglages")
        else:
            self.ctrl.toast.emit(f"« {existant.nom} » existait déjà : il est choisi")
        re_.nom = existant.nom
        self._toucher(True)

    def _inv(self, inv, cle, val):
        setattr(inv, cle, val)
        self.ctrl.toucher_reglages()
        self.ctrl.modifie.emit(False)

    def _retirer_reactif(self, e, k):
        self.ctrl.memoriser_manip()
        e.reactifs.pop(k)
        self._toucher(True)

    def _echantillons(self, e) -> QWidget:
        m, r = self.m, self.ctrl.reglages
        lab = etiquettes(m)
        ps = [p for p in echantillons_tries(m) if (p.etape_id == e.id if e else R.numero_etape(m, p) == 0)]
        titre = "3 · Échantillons à prélever" if e else "Échantillons à prélever avant le traitement"
        x = Expander(titre, f"{len(ps)} prévu{'s' if len(ps) > 1 else ''}" if ps else "aucun pour l’instant")
        g = QGridLayout()
        for k, p in enumerate(ps):
            sf = QFrame()
            sf.setObjectName("sousCarte")
            v = QVBoxLayout(sf)
            v.setContentsMargins(12, 10, 12, 10)
            t = etiquette(lab[p.id], "titreCarte")
            t.setStyleSheet(f"color:{theme.P.ambre_texte};")
            v.addWidget(ligne(badge(code_badge(lab[p.id])), t, "stretch",
                              icone("⧉", f"Dupliquer l’échantillon {lab[p.id]} (choix du nombre de copies)", lambda p=p: self._dupliquer_ech(p)),
                              icone("✕", f"Supprimer l’échantillon {lab[p.id]}", lambda p=p: self._supprimer_ech(p), danger=True)))
            if e:
                seg = Segmente([("pendant", "Pendant l’étape"), ("effluent", "À la sortie")], "pendant" if p.moment == "pendant" else "effluent")
                seg.change.connect(lambda val, p=p: (R.changer_moment(p, val), self._toucher(True)))
                v.addWidget(champ("Quand ?", seg))
            ch = []
            if e and p.moment == "pendant":
                tm = NumberBox(p.temps_min, "min", "ex. 10")
                tm.valeur.connect(lambda val, p=p: (setattr(p, "temps_min", val), self._toucher()))
                ch.append(champ("À quelle minute ?", tm))
            vol = ChoixVolume(r.volumes_ml, p.volume_ml)
            vol.choisi.connect(lambda val, p=p: (setattr(p, "volume_ml", val), self._toucher(True)))
            ch.append(champ("Volume prélevé", vol))
            v.addWidget(ligne(*ch))
            labo = Liste([l.nom for l in r.laboratoires], p.labo, vide=None if p.labo else "Choisir…")
            labo.choisi.connect(lambda val, p=p: (R.changer_labo(p, r, val), self._toucher(True)))
            v.addWidget(champ("Laboratoire", labo))
            an = []
            labo_p = r.laboratoire(p.labo)
            possibles = R.analyses_possibles(r, p)
            for a in possibles:
                b = bouton(a, lambda p=p, a=a: (setattr(p, "analyses", R.basculer_analyse(p.analyses, a)), self._toucher()))
                b.setProperty("chip", True)
                b.setCheckable(True)
                b.setChecked(a in p.analyses)
                an.append(b)
            v.addWidget(champ(f"Analyses possibles au {p.labo}" if labo_p and labo_p.analyses else "Analyses demandées",
                              flux_widgets(an) if an else etiquette("Aucune analyse définie pour ce laboratoire (Réglages)", secondaire=True)))
            sc = ChampTexte(p.scirius, "à saisir", mono=True)
            sc.modifie.connect(lambda val, p=p: (setattr(p, "scirius", val.strip()), self._toucher()))
            ar = ChampTexte(p.aramis, "à saisir", mono=True)
            ar.modifie.connect(lambda val, p=p: (setattr(p, "aramis", val.strip()), self._toucher()))
            v.addWidget(ligne(champ("N° Scirius", sc), champ("N° Aramis", ar)))
            com = ChampTexte(p.commentaire, "ex. prélever sous agitation, flacon ambré…")
            com.modifie.connect(lambda val, p=p: (setattr(p, "commentaire", val), self._toucher()))
            v.addWidget(champ("Commentaire", com))
            g.addWidget(sf, k // 2, k % 2, Qt.AlignmentFlag.AlignTop)
        wg = QWidget()
        wg.setLayout(g)
        x.ajouter(wg)
        x.ajouter(flux_widgets([bouton("+ Ajouter un échantillon", lambda: self._ajouter_ech(e), ajout=True),
                                etiquette("Reprend le laboratoire, le volume et les analyses par défaut.", secondaire=True),
                                bouton("Réglages des laboratoires", lambda: self.voir_reglages.emit("laboratoires"), lien=True)]))
        return x

    def _dupliquer_ech(self, p):
        from mat_methode.ui.dialogues import demander_nombre
        lab = etiquettes(self.m)[p.id]
        n = demander_nombre(self, f"Dupliquer l’échantillon {lab}",
                            "Les copies reprennent le moment, le volume, le laboratoire, les analyses et le commentaire, sans les n° Scirius / Aramis. "
                            "Elles prennent les lettres suivantes de l’étape.")
        if not n:
            return
        self.ctrl.memoriser_manip()
        R.dupliquer_echantillon(self.m, p.id, n)
        self._toucher(True)
        self.ctrl.toast.emit(f"{lab} dupliqué {n} fois")

    def _ajouter_ech(self, e):
        R.nouvel_echantillon(self.m, self.ctrl.reglages, e.id if e else None)
        self._toucher(True)
        self.ctrl.toast.emit("Échantillon ajouté")

    def _supprimer_ech(self, p):
        self.ctrl.memoriser_manip()
        self.m.prelevements.remove(p)
        self._toucher(True)
