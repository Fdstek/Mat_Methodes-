"""Page « Flux » (§6.2, §6.3 ; maquettes W02, W03, W06) : Ma demande, lancement, définir le flux,
compléter les étapes (maître-détail)."""
from __future__ import annotations

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from mat_methode.domain import journal as J
from mat_methode.domain import regles as R
from mat_methode.domain.catalogue import est_centrifugation
from mat_methode.domain.models import Condition, ReactifEtape
from mat_methode.domain.regles import code_badge, echantillons_tries, etiquettes
from mat_methode.domain.texte import cap, fmt_dt, fmt_dur, fmt_vol
from mat_methode.report.rapport import autres_conditions, resume_conditions
from mat_methode.ui import theme
from mat_methode.ui.controleur import Controleur
from mat_methode.ui.widgets import (
    ChampTexte,
    ChipSupprimable,
    ChoixVolume,
    Expander,
    InfoBar,
    Liste,
    NumberBox,
    Segmente,
    ToggleSwitch,
    ambre,
    badge,
    bouton,
    carte,
    champ,
    etiquette,
    flux_widgets,
    icone,
    ligne,
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
    voir_reglages = Signal()
    dupliquer = Signal(str)

    def __init__(self, ctrl: Controleur):
        super().__init__()
        self.ctrl = ctrl
        self.mode = "def"
        self.etape_id = DEPART
        self.inserer_apres: int | None = None
        self.groupe_cible: str | None = None  # grande étape où vont les étapes ajoutées
        self.remplacer = False
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(14)
        self._bilan = None
        self._lancement = None
        self._colonne = None

    @property
    def m(self):
        return self.ctrl.courante

    def ouvrir(self, mode: str):
        self.mode = mode
        self.etape_id = DEPART
        self.inserer_apres = None
        self.groupe_cible = None

    # ------------------------------------------------------------ rendu
    def rafraichir(self, structure: bool = True):
        m = self.m
        if m is None:
            return
        if self.etape_id != DEPART and not m.etape(self.etape_id):
            self.etape_id = DEPART
        if not m.etapes:
            self.mode = "def"
        if not structure:
            self._maj_legere()
            return
        vider(self.lay)
        if self.ctrl.lecture_seule:
            v = self.ctrl.verrou_autre
            self.lay.addWidget(InfoBar(f"Ouverte en lecture seule (depuis {fmt_dt(v.depuis)[-5:]}).",
                                       titre=f"Modifiée en ce moment par {v.utilisateur}",
                                       niveau="info", actions=[bouton("Dupliquer pour travailler dessus", lambda: self.dupliquer.emit(m.id))]))
        self._lancement = QWidget()
        QVBoxLayout(self._lancement).setContentsMargins(0, 0, 0, 0)
        self.lay.addWidget(self._lancement)
        self._remplir_lancement()
        demande = self._demande()
        self.lay.addWidget(demande)
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
        corps = self._definir() if self.mode == "def" else self._completer()
        self.lay.addWidget(corps)
        self.lay.addStretch(1)
        for x in (demande, corps):
            x.setEnabled(not self.ctrl.lecture_seule)

    def _maj_legere(self):
        """Après une frappe : bilan, lancement, cartes du flux ; jamais les champs en cours de saisie."""
        if self._bilan is not None:
            self._remplir_bilan()
        if self._lancement is not None:
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
        lay = self._lancement.layout()
        vider(lay)
        m = self.m
        f = QFrame()
        f.setObjectName("lancement")
        f.setProperty("lancee", m.lancee is not None)
        h = QHBoxLayout(f)
        h.setContentsMargins(16, 10, 16, 10)
        if not m.lancee:
            col = QVBoxLayout()
            col.addWidget(etiquette("<b>Manip pas encore lancée</b>"))
            col.addWidget(etiquette("Quand elle démarre, lance-la : chaque modification sera ensuite notée avec la date, l’heure et ton nom.", secondaire=True, wrap=True))
            h.addLayout(col, 1)
            b = bouton("▶  Lancer la manip", self._lancer, accent=True)
            b.setEnabled(not self.ctrl.lecture_seule)
            h.addWidget(b)
        else:
            col = QVBoxLayout()
            col.addWidget(etiquette(f"<b>Manip lancée le {fmt_dt(m.lancee.le)} par {m.lancee.par}</b>"))
            n = len(m.journal)
            if n:
                row = ligne(pastille(f"⚠ Modifiée après lancement · {n} modification{'s' if n > 1 else ''}", "warn"),
                            bouton("Voir le journal", self._journal), "stretch")
            else:
                ann = bouton("Annuler le lancement", self._annuler_lancement)
                ann.setEnabled(not self.ctrl.lecture_seule)
                row = ligne(pastille("Aucune modification depuis le lancement", "ok"), ann, "stretch")
            col.addWidget(row)
            h.addLayout(col, 1)
        lay.addWidget(f)

    def _lancer(self):
        from mat_methode.ui.dialogues import confirmer
        if confirmer(self, "Lancer la manip ?", "À partir de maintenant, chaque modification (étapes, conditions, réactifs, échantillons, "
                     "demande) sera notée avec la date, l’heure et ton nom, et signalée dans le rapport.", "Lancer", danger=False):
            J.lancer(self.m, par=self.ctrl.operateur(self.m))
            self._toucher(True)
            self.ctrl.toast.emit("Manip lancée")

    def _annuler_lancement(self):
        if J.annuler_lancement(self.m):
            self._toucher(True)
            self.ctrl.toast.emit("Lancement annulé")

    def _journal(self):
        from mat_methode.ui.dialogues import journal
        self.ctrl.journaliser()
        journal(self, self.m)

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
        donneur = Liste(r.donneurs_ordre, c.donneur)
        donneur.choisi.connect(lambda v: (setattr(c, "donneur", v), self._toucher()))
        g.addWidget(champ("Donneur d’ordre", donneur), 1, 0)
        ref = ChampTexte(c.ref, "n° ?", mono=True)
        ref.modifie.connect(lambda v: (setattr(c, "ref", v), self._toucher()))
        g.addWidget(champ("Référence de la demande", ref), 1, 1)
        vol = NumberBox(c.volume_depart_ml, "mL")
        vol.valeur.connect(lambda v: (setattr(c, "volume_depart_ml", v), self._toucher()))
        g.addWidget(champ("Volume de départ", vol), 1, 2)
        typ = Liste(r.types_demande, c.type)
        typ.choisi.connect(lambda v: (setattr(c, "type", v), self._toucher(structure=R.est_test(v) != bool(self._idee))))
        g.addWidget(champ("Type de demande", typ), 2, 0)
        op = ChampTexte(c.operateur, "Nom d’utilisateur Windows")
        op.modifie.connect(lambda v: (setattr(c, "operateur", v), self._toucher()))
        g.addWidget(champ("Opérateur (nom d’utilisateur Windows)", op), 2, 1, 1, 2)
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
        tags = [ChipSupprimable(f"#{t}", lambda t=t: self._retirer_tag(t), f"Retirer le tag {t}") for t in m.tags]
        sugg = [t for t in R.tous_les_tags(self.ctrl.manips) if not any(t.lower() == x.lower() for x in m.tags)]
        self._tag = ChampTexte("", "Ajouter un tag (Entrée)", suggestions=sugg)
        self._tag.setMaximumWidth(260)
        self._tag.returnPressed.connect(self._ajouter_tag)
        tags += [self._tag, bouton("Ajouter", self._ajouter_tag)]
        lay.addWidget(champ("Tags", flux_widgets(tags)))
        self._bilan = QWidget()
        QHBoxLayout(self._bilan).setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._bilan)
        self._remplir_bilan()
        return f

    def _ajouter_tag(self):
        if R.ajouter_tags(self.m, self._tag.text(), R.tous_les_tags(self.ctrl.manips)):
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
        lay.addWidget(pastille(f"{fmt_vol(b.depart)} mL au départ"))
        lay.addWidget(pastille(f"{fmt_vol(b.preleve)} mL prélevés ({b.n} éch.)"))
        lay.addWidget(pastille(f"dépassement de {fmt_vol(-b.restant)} mL" if b.depassement else f"{fmt_vol(b.restant)} mL restants",
                               "warn" if b.depassement else "ok"))
        if b.numeros_a_saisir:
            lay.addWidget(pastille(f"{b.numeros_a_saisir} numéro{'s' if b.numeros_a_saisir > 1 else ''} à saisir", "warn"))
        lay.addStretch(1)

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
        else:
            cl.addWidget(etiquette("Aucune étape pour l’instant.", secondaire=True))
        catalogue = [o.nom for o in self.ctrl.reglages.operations]
        groupes_vus = set()
        for g, idx in R.blocs(m):
            if g is None:
                for i in idx:
                    cl.addWidget(self._ligne_etape(i, catalogue))
                continue
            groupes_vus.add(g.id)
            cl.addWidget(self._bloc_groupe(g, idx, catalogue))
        for g in m.groupes:  # grande étape encore vide
            if g.id not in groupes_vus:
                cl.addWidget(self._bloc_groupe(g, [], catalogue))
        ia, gc = self.inserer_apres, m.groupe(self.groupe_cible)
        if gc is None:
            self.groupe_cible = None
        if gc is not None:
            nums = R.numeros_groupe(m, gc.id)
            q = f"{gc.nom} · étape {(nums[-1] + 1) if nums else len(m.etapes) + 1} : que fais-tu dans cette grande étape ?"
        elif ia is not None:
            q = f"Insérer {'au début' if ia < 0 else f'après l’étape {ia + 1}'} : que fais-tu ?"
        else:
            q = f"Étape {len(m.etapes) + 1} : que fais-tu {'ensuite' if m.etapes else 'en premier'} ?"
        cl.addWidget(etiquette(q, "titreCarte"))
        if gc is not None:
            cl.addWidget(ligne(bouton(f"Terminer « {gc.nom} »", self._finir_groupe), "stretch"))
        elif ia is not None:
            cl.addWidget(ligne(bouton("Annuler l’insertion", lambda: self._inserer(None)), "stretch"))
        grille = QGridLayout()
        for k, o in enumerate(catalogue):
            grille.addWidget(bouton(cap(o), lambda o=o: self._ajouter_etape(o)), k // 5, k % 5)
        cl.addLayout(grille)
        autre = ChampTexte("", "Ex. neutralisation")
        autre.returnPressed.connect(lambda: self._ajouter_etape(autre.text()))
        cl.addWidget(ligne(champ("Autre étape", autre), bouton("Ajouter", lambda: self._ajouter_etape(autre.text())), "stretch"))
        # grandes étapes (Degumming…)
        grand = Liste(self.ctrl.reglages.grandes_etapes, "", vide="Choisir…")
        grand.setAccessibleName("Grande étape à commencer")
        autre_g = ChampTexte("", "ou un autre nom")
        autre_g.setMaximumWidth(200)
        commencer = lambda: self._commencer_groupe(autre_g.text().strip() or grand.currentData() or "")
        autre_g.returnPressed.connect(commencer)
        cl.addWidget(ligne(champ("Grande étape (regroupe plusieurs étapes, ex. Degumming)", grand), autre_g,
                           bouton("+ Commencer une grande étape", commencer), "stretch"))
        lay.addWidget(f)
        lay.addWidget(self._communes())
        b = bouton("Mon flux est prêt : compléter les étapes  →", self._vers_completer, accent=True)
        b.setEnabled(bool(m.etapes))
        lay.addWidget(ligne(b, "stretch"))
        return w

    def _ligne_etape(self, i: int, catalogue: list[str], dans_groupe: bool = False) -> QWidget:
        m, e = self.m, self.m.etapes[i]
        sf = QFrame()
        sf.setObjectName("sousCarte")
        h = QHBoxLayout(sf)
        h.setContentsMargins(10, 6, 10, 6)
        h.addWidget(numero(i + 1))
        op = Liste(catalogue, e.operation, vide=None, libelles={o: cap(o) for o in catalogue + [e.operation]})
        op.setAccessibleName(f"Opération de l’étape {i + 1}")
        op.choisi.connect(lambda v, e=e: (setattr(e, "operation", v), self._toucher(True)))
        h.addWidget(op, 1)
        if m.groupes:  # ranger l'étape dans une grande étape
            choix = {g.id: f"{g.nom} ({R.plage(R.numeros_groupe(m, g.id))})" for g in m.groupes}
            gr = Liste(list(choix), e.groupe_id or "", vide="Hors grande étape", libelles=choix)
            gr.setAccessibleName(f"Grande étape de l’étape {i + 1}")
            gr.setMaximumWidth(230)
            gr.choisi.connect(lambda v, e=e: (R.placer_dans_groupe(m, e.id, v or None), self._toucher(True)))
            h.addWidget(gr)
        haut = icone("↑", f"Monter l’étape {i + 1}", lambda e=e: self._deplacer(e, -1))
        haut.setEnabled(i > 0)
        bas = icone("↓", f"Descendre l’étape {i + 1}", lambda e=e: self._deplacer(e, 1))
        bas.setEnabled(i < len(m.etapes) - 1)
        h.addWidget(haut)
        h.addWidget(bas)
        h.addWidget(icone("⧉", f"Dupliquer l’étape {i + 1}", lambda e=e: self._dupliquer_etape(e)))
        h.addWidget(bouton("+ Insérer après", lambda i=i: self._inserer(i)))
        h.addWidget(icone("✕", f"Supprimer l’étape {i + 1}", lambda e=e: self._supprimer_etape(e), danger=True))
        return sf

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
        v.addWidget(ligne(titre, nom, "stretch", haut, bas,
                          bouton("+ Ajouter une sous-étape", lambda: self._viser_groupe(g.id)),
                          bouton("Défaire", lambda: self._defaire_groupe(g), tip=f"Défaire la grande étape {g.nom} (ses étapes restent dans le flux)")))
        for i in idx:
            v.addWidget(self._ligne_etape(i, catalogue, dans_groupe=True))
        if not idx:
            v.addWidget(etiquette("Aucune sous-étape : choisis une opération ci-dessous.", secondaire=True))
        return f

    def _commencer_groupe(self, nom: str):
        if not nom:
            self.ctrl.toast.emit("Choisis le nom de la grande étape")
            return
        if nom not in self.ctrl.reglages.grandes_etapes:
            self.ctrl.reglages.grandes_etapes.append(nom)
            self.ctrl.toucher_reglages()
        g = R.creer_groupe(self.m, nom)
        self.groupe_cible, self.inserer_apres = g.id, None
        self._toucher(True)
        self.ctrl.toast.emit(f"Grande étape « {nom} » : ajoute ses sous-étapes")

    def _viser_groupe(self, gid):
        self.groupe_cible, self.inserer_apres = gid, None
        self.rafraichir()

    def _finir_groupe(self):
        self.groupe_cible = None
        self.rafraichir()

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
            on = (c.vide is not None) if cle == "vide" else getattr(c, cle) is not None
            g.addWidget(self._condition(lib, on, lambda cle=cle: (R.basculer_commune(m, cle), self._toucher(True)),
                                        (c.vide.mbar if c.vide else None) if cle == "vide" else getattr(c, cle), lib_v, unite,
                                        lambda v, cle=cle: self._set_commune(cle, v)), 0, k)
        cl.addLayout(g)
        rem = ToggleSwitch("Remplacer aussi les valeurs déjà saisies", self.remplacer)
        rem.toggled.connect(lambda v: setattr(self, "remplacer", v))
        cl.addWidget(rem)
        ap = bouton(f"Appliquer à toutes les étapes ({len(m.etapes)})", self._appliquer, accent=True)
        ap.setEnabled(bool(m.etapes))
        cl.addWidget(ligne(ap, "stretch"))
        cl.addWidget(etiquette("Les étapes que tu ajouteras ensuite reprennent ces conditions automatiquement.", secondaire=True))
        return f

    def _set_commune(self, cle, v):
        c = self.m.communes
        if cle == "vide":
            if c.vide is not None:
                c.vide.mbar = v
        elif v is not None:
            setattr(c, cle, v)
        self._toucher()

    def _condition(self, libelle, on, basculer, valeur, lib_v, unite, changer) -> QWidget:
        sf = QFrame()
        sf.setObjectName("sousCarte")
        v = QVBoxLayout(sf)
        v.setContentsMargins(12, 10, 12, 10)
        t = ToggleSwitch(libelle, on)
        t.toggled.connect(lambda *_: basculer())
        v.addWidget(t)
        if on:
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
        if gc is not None:  # ajout dans la grande étape en cours, après sa dernière sous-étape
            nums = R.numeros_groupe(self.m, gc.id)
            R.ajouter_etape(self.m, op, nums[-1] - 1 if nums else None, groupe_id=gc.id)
        else:
            R.ajouter_etape(self.m, op, self.inserer_apres)
            if self.inserer_apres is not None:
                self.inserer_apres += 1
        self._toucher(True)

    def _inserer(self, i):
        self.inserer_apres = i
        self.groupe_cible = None
        self.rafraichir()

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
        cl = QVBoxLayout(self._colonne)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(8)
        gl.addWidget(self._colonne)
        gl.addWidget(etiquette("Badge : la place sur la frise donne le moment du prélèvement ; le bord droit est la sortie de l’étape.",
                               secondaire=True, wrap=True))
        gl.addStretch(1)
        gauche.setFixedWidth(340)
        self._remplir_colonne()
        h.addWidget(gauche, 0, Qt.AlignmentFlag.AlignTop)
        h.addWidget(self._editeur(), 1, Qt.AlignmentFlag.AlignTop)
        return w

    def _remplir_colonne(self):
        m, lay = self.m, self._colonne.layout()
        vider(lay)
        lab, ech = etiquettes(m), echantillons_tries(m)

        def pill(p):
            n = R.numero_etape(m, p)
            q = "avant" if n == 0 else (f"à {fmt_dur(p.temps_min)}" if p.temps_min is not None else "à ?") if p.moment == "pendant" else "sortie"
            return ambre(f"{lab[p.id]} · {fmt_vol(p.volume_ml or 0)} mL {q}", code_badge(lab[p.id]))

        dep = [p for p in ech if R.numero_etape(m, p) == 0]
        c = self._carte_flux(DEPART, None, "Départ")
        c.layout().addWidget(etiquette(f"{m.contexte.matiere or 'matière ?'}" + (f" · {fmt_vol(m.contexte.volume_depart_ml)} mL"
                                                                                 if m.contexte.volume_depart_ml is not None else ""), secondaire=True))
        for p in dep:
            c.layout().addWidget(pill(p))
        lay.addWidget(c)
        cible, cadre = lay, None
        for i, e in enumerate(m.etapes):
            g = m.groupe(e.groupe_id)
            debut = g is not None and (i == 0 or m.etapes[i - 1].groupe_id != g.id)
            if g is None:
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
            c = self._carte_flux(e.id, i + 1, cap(e.operation))
            cl = c.layout()
            for r in e.reactifs:
                if r.nom:
                    cl.addWidget(etiquette(f"<b>{r.nom}</b> <span style='color:{theme.P.texte2}'>{r.quantite}</span>", wrap=True))
            cond = " · ".join(x for x in [resume_conditions(e)] + autres_conditions(e) if x)
            cl.addWidget(etiquette(cond, "conditions", wrap=True) if cond else etiquette("conditions à compléter", "aCompleter"))
            if e.equipements:
                cl.addWidget(etiquette(" · ".join(e.equipements), secondaire=True, wrap=True))
            ps = [p for p in ech if p.etape_id == e.id]
            if e.duree_min or ps:
                cl.addWidget(Frise(e.duree_min, [(position(p, e), code_badge(lab[p.id])) for p in ps]))
            for p in ps:
                cl.addWidget(pill(p))
            cible.addWidget(c)

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
        self.rafraichir()

    def ordre(self):
        return [DEPART] + [e.id for e in self.m.etapes]

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
        if e is None:
            lay.addWidget(etiquette("Départ", "sousTitre"))
            f, cl = carte()
            cl.addWidget(etiquette("Matière de départ", "titreCarte"))
            mat = ChampTexte(m.contexte.matiere)
            mat.modifie.connect(lambda v: (setattr(m.contexte, "matiere", v), self._toucher()))
            lot = ChampTexte(m.contexte.lot, "lot ?", mono=True)
            lot.modifie.connect(lambda v: (setattr(m.contexte, "lot", v), self._toucher()))
            cl.addWidget(ligne(champ("Matière", mat), champ("Lot", lot)))
            lay.addWidget(f)
        else:
            i = m.etapes.index(e)
            g = m.groupe(e.groupe_id)
            if g is not None:
                gl = etiquette(f"{g.nom} · {R.plage(R.numeros_groupe(m, g.id))}", "etiquetteChamp")
                gl.setStyleSheet(f"color:{theme.P.accent};font-weight:700;")
                lay.addWidget(gl)
            lay.addWidget(ligne(numero(i + 1, 28), etiquette(cap(e.operation), "sousTitre"), "stretch"))
            lay.addWidget(self._conditions(e))
            lay.addWidget(self._reactifs(e))
        for a in avert:
            lay.addWidget(InfoBar(a))
        lay.addWidget(self._echantillons(e))
        o = self.ordre()
        i = o.index(self.etape_id)
        prec = bouton("←  Étape précédente", self.precedente, tip="Étape précédente (Alt+←)")
        prec.setEnabled(i > 0)
        suiv = bouton("Terminer : voir le rapport" if i >= len(o) - 1 else "Étape suivante  →", self.suivante, accent=True,
                      tip="Étape suivante (Alt+→)")
        lay.addWidget(ligne(prec, "stretch", suiv))
        return w

    def _conditions(self, e) -> QWidget:
        x = Expander("1 · Conditions opératoires")
        g = QGridLayout()
        defs = [("temperature_c", "Chauffage", "Température", "°C"),
                ("agitation_trmin", "Vitesse de centrifugation" if est_centrifugation(e.operation) else "Agitation", "Vitesse", "tr/min"),
                ("vide", "Sous vide", "Pression en mbar (facultatif)", "mbar"), ("filtre_um", "Membrane filtrante", "Taille des pores", "µm")]
        for k, (cle, lib, lib_v, unite) in enumerate(defs):
            on = (e.vide is not None) if cle == "vide" else getattr(e, cle) is not None
            val = (e.vide.mbar if e.vide else None) if cle == "vide" else getattr(e, cle)
            g.addWidget(self._condition(lib, on, lambda cle=cle: (R.basculer_condition(e, cle), self._toucher(True)), val, lib_v, unite,
                                        lambda v, cle=cle: self._set_cond(e, cle, v)), k // 2, k % 2)
        wg = QWidget()
        wg.setLayout(g)
        x.ajouter(wg)
        duree = NumberBox(e.duree_min, "min", "ex. 30")
        duree.valeur.connect(lambda v: (setattr(e, "duree_min", v), self._toucher()))
        mat = [ChipSupprimable(q, lambda k=k: self._retirer_materiel(e, k)) for k, q in enumerate(e.equipements)]
        sugg = sorted({q for mm in self.ctrl.manips for ee in mm.etapes for q in ee.equipements})
        nouveau = ChampTexte("", "Ex. plaque chauffante agitatrice", suggestions=sugg)
        nouveau.setMinimumWidth(240)
        nouveau.returnPressed.connect(lambda: self._ajouter_materiel(e, nouveau.text()))
        mat += [nouveau, bouton("+ Ajouter", lambda: self._ajouter_materiel(e, nouveau.text()))]
        duree.setMaximumWidth(200)
        x.ajouter(champ("Durée de l’étape", duree))
        x.ajouter(champ("Matériel utilisé", flux_widgets(mat)))
        for k, a in enumerate(e.autres):
            n = ChampTexte(a.nom, "ex. pH, atmosphère")
            n.modifie.connect(lambda v, a=a: (setattr(a, "nom", v), self._toucher()))
            v = ChampTexte(a.valeur)
            v.modifie.connect(lambda val, a=a: (setattr(a, "valeur", val), self._toucher()))
            x.ajouter(ligne(champ("Autre condition", n), champ("Valeur", v),
                            icone("✕", "Retirer cette condition", lambda k=k: self._retirer_autre(e, k), danger=True)))
        x.ajouter(ligne(bouton("+ Autre condition", lambda: (e.autres.append(Condition()), self._toucher(True)), ajout=True), "stretch"))
        rem = ChampTexte(e.remarque, "Apparaît entre parenthèses à la fin de la phrase de l’étape")
        rem.modifie.connect(lambda v: (setattr(e, "remarque", v), self._toucher()))
        x.ajouter(champ("Remarque (facultatif)", rem))
        return x

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
        r = self.ctrl.reglages
        n = len(e.reactifs)
        x = Expander("2 · Réactifs", f"{n} dans cette étape" if n else "aucun pour l’instant")
        g = QGridLayout()
        noms = [y.nom for y in r.reactifs]
        for k, re_ in enumerate(e.reactifs):
            sf = QFrame()
            sf.setObjectName("sousCarte")
            v = QVBoxLayout(sf)
            v.setContentsMargins(12, 10, 12, 10)
            v.addWidget(ligne(etiquette(f"Réactif {k + 1}", "titreCarte"), "stretch",
                              icone("✕", f"Retirer le réactif {k + 1}", lambda k=k: self._retirer_reactif(e, k), danger=True)))
            nom = Liste(noms, re_.nom)
            nom.choisi.connect(lambda val, re_=re_: (setattr(re_, "nom", val), self._toucher(True)))
            nouveau = bouton("+ Nouveau réactif…", lambda re_=re_: self._nouveau_reactif(re_), lien=True,
                             tip="Ajouter un réactif à la liste des Réglages et le choisir ici")
            v.addWidget(champ("Réactif", nom))
            v.addWidget(nouveau)
            q = ChampTexte(re_.quantite, "ex. 1 : 1 (v/v)", mono=True)
            q.modifie.connect(lambda val, re_=re_: (setattr(re_, "quantite", val), self._toucher()))
            v.addWidget(champ("Quantité ou ratio", q))
            inv = r.reactif(re_.nom) if re_.nom else None
            if inv is not None:  # mémorisé par nom de réactif, repris partout
                sc = ChampTexte(inv.scirius, "à saisir", mono=True)
                sc.modifie.connect(lambda val, inv=inv: self._inv(inv, "scirius", val))
                em = ChampTexte(inv.emplacement, "ex. armoire 1, étagère 2")
                em.modifie.connect(lambda val, inv=inv: self._inv(inv, "emplacement", val))
                v.addWidget(ligne(champ("N° Scirius", sc), champ("Emplacement", em)))
                plus = Expander("Fournisseur et lot", ouvert=bool(inv.fournisseur or inv.lot))
                plus.setObjectName("")
                plus.layout().setContentsMargins(0, 0, 0, 0)
                fo = ChampTexte(inv.fournisseur)
                fo.modifie.connect(lambda val, inv=inv: self._inv(inv, "fournisseur", val))
                lo = ChampTexte(inv.lot, mono=True)
                lo.modifie.connect(lambda val, inv=inv: self._inv(inv, "lot", val))
                plus.ajouter(ligne(champ("Fournisseur", fo), champ("Lot", lo)))
                v.addWidget(plus)
            g.addWidget(sf, k // 2, k % 2, Qt.AlignmentFlag.AlignTop)
        wg = QWidget()
        wg.setLayout(g)
        x.ajouter(wg)
        x.ajouter(flux_widgets([bouton("+ Ajouter un réactif à cette étape", lambda: (e.reactifs.append(ReactifEtape()), self._toucher(True)), ajout=True),
                                bouton("Un réactif manque ? Ajoute-le dans les Réglages.", self.voir_reglages.emit, lien=True)]))
        return x

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
            for a in list(r.analyses) + [a for a in p.analyses if a not in r.analyses]:
                b = bouton(a, lambda p=p, a=a: (setattr(p, "analyses", R.basculer_analyse(p.analyses, a)), self._toucher()))
                b.setProperty("chip", True)
                b.setCheckable(True)
                b.setChecked(a in p.analyses)
                an.append(b)
            v.addWidget(champ("Analyses demandées", flux_widgets(an)))
            sc = ChampTexte(p.scirius, "à saisir", mono=True)
            sc.modifie.connect(lambda val, p=p: (setattr(p, "scirius", val.strip()), self._toucher()))
            ar = ChampTexte(p.aramis, "à saisir", mono=True)
            ar.modifie.connect(lambda val, p=p: (setattr(p, "aramis", val.strip()), self._toucher()))
            v.addWidget(ligne(champ("N° Scirius", sc), champ("N° Aramis", ar)))
            g.addWidget(sf, k // 2, k % 2, Qt.AlignmentFlag.AlignTop)
        wg = QWidget()
        wg.setLayout(g)
        x.ajouter(wg)
        x.ajouter(flux_widgets([bouton("+ Ajouter un échantillon", lambda: self._ajouter_ech(e), ajout=True),
                                etiquette("Reprend le laboratoire, le volume et les analyses par défaut.", secondaire=True),
                                bouton("Réglages des laboratoires", self.voir_reglages.emit, lien=True)]))
        return x

    def _ajouter_ech(self, e):
        R.nouvel_echantillon(self.m, self.ctrl.reglages, e.id if e else None)
        self._toucher(True)
        self.ctrl.toast.emit("Échantillon ajouté")

    def _supprimer_ech(self, p):
        self.ctrl.memoriser_manip()
        self.m.prelevements.remove(p)
        self._toucher(True)
