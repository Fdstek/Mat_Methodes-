"""Page « Rapport » (§6.4, maquette W04)."""
from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mat_methode.domain import regles as R
from mat_methode.domain.reglages_ops import auteur, nom_auteur, nom_etat, texte_statut
from mat_methode.domain.texte import fmt_dt, fmt_vol
from mat_methode.report.rapport import REPERE, construire, markdown, mention_modifiee
from mat_methode.ui import theme
from mat_methode.ui.controleur import Controleur
from mat_methode.ui.widgets import InfoBar, badge, bouton, carte, etiquette, ligne, numero, pastille, vider


def texte_riche(s: str) -> str:
    p = theme.P
    out, pos = [], 0
    for mt in REPERE.finditer(s):
        out.append(escape(s[pos:mt.start()]))
        out.append(f"<span style='background:{p.ambre_fond};color:{p.ambre_texte};'>&nbsp;{escape(mt.group(1))} à saisir&nbsp;</span>")
        pos = mt.end()
    out.append(escape(s[pos:]))
    return "".join(out)


def a_saisir(v) -> str:
    p = theme.P
    return escape(str(v)) if v else f"<span style='background:{p.ambre_fond};color:{p.ambre_texte};'>&nbsp;à saisir&nbsp;</span>"


def table(entetes: list[str], lignes: list[list[str]]) -> QTableWidget:
    t = QTableWidget(len(lignes), len(entetes))
    t.setHorizontalHeaderLabels([h.upper() for h in entetes])
    t.verticalHeader().hide()
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setFocusPolicy(Qt.FocusPolicy.TabFocus)
    t.setWordWrap(True)
    for i, ln in enumerate(lignes):
        for k, v in enumerate(ln):
            it = QTableWidgetItem(v if v else "à saisir")
            if not v:
                it.setForeground(Qt.GlobalColor.darkYellow if not theme.P.sombre else Qt.GlobalColor.yellow)
            t.setItem(i, k, it)
    t.resizeColumnsToContents()
    t.horizontalHeader().setSectionResizeMode(len(entetes) - 1, QHeaderView.ResizeMode.Stretch)
    t.resizeRowsToContents()
    t.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    t.setFixedHeight(t.horizontalHeader().height() + sum(t.rowHeight(i) for i in range(len(lignes))) + 4)
    return t


LIBELLES_EMIS = {"rapport": "Rapport", "protocole": "Protocole", "ordre": "Protocole"}  # « ordre » : ancien nom du protocole


def ligne_emis(m, types: tuple[str, ...], ouvrir, fin: list, vide: str = "Aucun document émis pour l’instant.") -> QWidget:
    """« Ouvrir le dernier … émis » + menu « Tous » des documents émis de ces types (le plus récent d'abord)."""
    from PySide6.QtWidgets import QMenu
    emis = [r for r in reversed(m.rapports) if r.type in types]
    if not emis:
        return ligne(etiquette(vide, secondaire=True), "stretch", *fin)
    d = emis[0]
    quoi = LIBELLES_EMIS.get(d.type, d.type).lower()
    dernier = bouton(f"Ouvrir le dernier {quoi} émis", lambda: ouvrir(d.chemin), tip=d.chemin)
    tous = bouton("Tous  ▾", tip="Documents émis pour cette manip")
    menu = QMenu(tous)
    for r in emis[:15]:
        menu.addAction(f"{LIBELLES_EMIS.get(r.type, r.type)} {r.fmt.upper()} · {fmt_dt(r.le)} · {r.par}", lambda c=r.chemin: ouvrir(c))
    tous.setMenu(menu)
    tous.setStyleSheet("QPushButton::menu-indicator{width:0;}")
    info = etiquette(f"{d.fmt.upper()} · {fmt_dt(d.le)[:10]} · {d.par}", secondaire=True)
    info.setToolTip(f"{LIBELLES_EMIS.get(d.type, d.type)} {d.fmt.upper()} émis le {fmt_dt(d.le)} par {d.par}")
    return ligne(dernier, tous, info, "stretch", *fin)


def prelevements_manip(m) -> list[dict]:
    """Échantillons de la manip (étiquette, n° Aramis, n° Scirius), dans l'ordre du flux."""
    lab = R.etiquettes(m)
    return [{"id": lab[p.id], "aramis": p.aramis, "scirius": p.scirius} for p in R.echantillons_tries(m)]


def carte_resultats(ctrl: Controleur, m, rafraichir, ouvert: bool = True) -> QWidget | None:
    """Carte « Résultats d'analyses » : résultats des échantillons retrouvés dans ana explorer par leur n° Aramis.
    Rien quand aucun échantillon n'a de n° ; lecture lancée en arrière-plan si les résultats ne sont pas encore chargés."""
    from mat_methode.analyses_ptt import libelle
    from mat_methode.ui.widgets import Expander
    pre = prelevements_manip(m)
    if not any(p["aramis"] or p["scirius"] for p in pre):
        return None
    x = Expander("Résultats d’analyses", "(ana explorer)", ouvert=ouvert)

    def actualiser():
        from PySide6.QtWidgets import QApplication
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            ctrl.lire_analyses(forcer=True)
        finally:
            QApplication.restoreOverrideCursor()
        rafraichir()

    lu = ctrl._analyses
    if lu is None:
        ctrl.precharger_analyses()
        x.ajouter(ligne(etiquette("Lecture du classeur des analyses en cours…", secondaire=True), "stretch",
                        bouton("Lire maintenant", actualiser)))
        return x
    res = lu.pour_export(pre)
    if not res:
        txt = ("Aucun résultat pour l’instant dans ana explorer pour les n° Aramis de cette manip." if not lu.vide else
               "Classeur des analyses introuvable : " + (" | ".join(lu.ecartes[:2]) or "aucune source") + " (Réglages › Résultats d’analyses).")
        x.ajouter(ligne(etiquette(txt, secondaire=True, wrap=True), "stretch", bouton("Actualiser", actualiser)))
        return x
    n, total = len(res["echantillons"]), sum(1 for p in pre if p["aramis"] or p["scirius"])
    x.changer_note(f"{n} / {total} échantillon{'s' if total > 1 else ''}")
    x.ajouter(ligne(etiquette(f"Retrouvés par le n° Aramis · {lu.origine}. Repris dans le PDF du rapport, le Word et le Protocole.",
                              secondaire=True, wrap=True), "stretch", bouton("Actualiser", actualiser, tip="Relire le classeur des analyses")))
    echs, analyses = res["echantillons"], res["analyses"]
    entetes = ["Éch.", "N° Aramis", "Labos"] + [libelle(a) for a in analyses]
    lignes = [[e["id"], e.get("aramis") or "", ", ".join(e.get("labos", [])) or "—"] + [e["valeurs"].get(a["nom"], "—") for a in analyses]
              for e in echs]
    t = table(entetes, lignes)
    t.horizontalHeader().setSectionResizeMode(len(entetes) - 1, QHeaderView.ResizeMode.ResizeToContents)
    t.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)  # beaucoup d'analyses : défilement horizontal
    t.setFixedHeight(t.height() + t.horizontalScrollBar().sizeHint().height())
    for i, e in enumerate(echs):
        for k, a in enumerate(analyses):
            it = t.item(i, k + 3)
            if it is not None and e["sources"].get(a["nom"]):
                it.setToolTip(f"{a['nom']} : {e['valeurs'].get(a['nom'], '')} {a.get('unite', '')} — {e['sources'][a['nom']]}")
    x.ajouter(t)
    return x


def carte_figures(ctrl: Controleur, m, rafraichir, ouvrir_fichier, ouvert: bool = True) -> QWidget | None:
    """Carte « Tableaux et graphiques d'ana explorer » : images envoyées par le bouton « → Mat & Méthode » d'ana explorer,
    reprises dans le PDF du rapport, le Word et le Protocole. Rien tant qu'aucune image n'a été envoyée."""
    from PySide6.QtGui import QPixmap

    from mat_methode import lien_ana
    from mat_methode.ui import dialogues as D
    from mat_methode.ui.widgets import Expander
    figs = ctrl.figures_ana(m)
    if not figs:
        return None
    x = Expander("Tableaux et graphiques d’ana explorer", f"{len(figs)}", ouvert=ouvert)
    x.ajouter(etiquette("Envoyés depuis ana explorer (bouton « → Mat & Méthode »). Repris dans le PDF du rapport, le Word et le Protocole.",
                        secondaire=True, wrap=True))

    def retirer(f):
        if D.confirmer(x, "Retirer cette image ?", f"« {f['libelle']} » du {f['le']} ne sera plus dans les documents "
                       "(elle est rangée dans le dossier « retirees », pas effacée).", "Retirer"):
            lien_ana.retirer(f["chemin"])
            rafraichir()

    for f in figs:
        img = QLabel()
        pm = QPixmap(f["chemin"])
        if not pm.isNull():
            img.setPixmap(pm.scaledToWidth(min(760, pm.width()), Qt.TransformationMode.SmoothTransformation))
        img.setToolTip(f["chemin"])
        titre = f"<b>{escape(f['libelle'])}</b>" + (f" · {escape(f['titre'])}" if f["titre"] else "")
        info = etiquette(f"{titre}<br><span style='color:{theme.P.texte2}'>{escape(f['le'])}" + (f" · {escape(auteur(ctrl.reglages, f['par']))}" if f["par"] else "") + "</span>",
                         wrap=True)
        x.ajouter(ligne(info, "stretch", bouton("Ouvrir", lambda c=f["chemin"]: ouvrir_fichier(c), tip="Ouvrir l’image en grand"),
                        bouton("Retirer", lambda f=f: retirer(f), tip="Ne plus mettre cette image dans les documents")))
        x.ajouter(img)
    return x


def vignette(fichier: str, cote: int = 170) -> QLabel:
    """Miniature d'une photo (lecture réduite : rapide même pour une photo 4K)."""
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QImageReader, QPixmap
    lab = QLabel()
    r = QImageReader(fichier)
    r.setAutoTransform(True)
    t = r.size()
    if t.isValid() and t.width() > 0:
        k = cote / max(t.width(), t.height())
        r.setScaledSize(QSize(max(1, int(t.width() * k)), max(1, int(t.height() * k))))
    img = r.read()
    if not img.isNull():
        lab.setPixmap(QPixmap.fromImage(img))
    else:
        lab.setText("photo illisible")
    lab.setFixedSize(cote, cote)
    lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lab.setStyleSheet(f"QLabel{{background:{theme.P.fond};border-radius:6px;}}")
    return lab


def carte_photos(ctrl: Controleur, m, ouvrir_fichier, ouvert: bool = True) -> QWidget | None:
    """Carte « Photos des échantillons (SamplesTEK) » : photos prises avec SamplesTEK, retrouvées par le n° Aramis de chaque
    échantillon. Un clic sur une photo l'ouvre en grand. Rien quand aucun échantillon n'a de n° Aramis."""
    from mat_methode.ui.widgets import Expander, flux_widgets
    pre = prelevements_manip(m)
    if not any(p["aramis"] for p in pre):
        return None
    bloc, lu = ctrl.photos_samplestek(pre)
    n = sum(len(e["photos"]) for e in bloc)
    x = Expander("Photos des échantillons (SamplesTEK)", f"{n} photo{'s' if n > 1 else ''}" if n else "", ouvert=ouvert and bool(n))
    if not bloc:
        x.ajouter(etiquette("Aucune photo SamplesTEK pour les n° Aramis de cette manip." if not lu.erreur else
                            f"{lu.erreur} (Réglages › Photos SamplesTEK).", secondaire=True, wrap=True))
        return x
    x.ajouter(etiquette(f"Retrouvées par le n° Aramis dans {lu.dossier}. Clique une photo pour l’ouvrir en grand. "
                        "Reprises dans le PDF du rapport, le Word et le Protocole.", secondaire=True, wrap=True))
    for e in bloc:
        x.ajouter(etiquette(f"<b>{escape(e['id'])}</b> · n° Aramis {escape(e['aramis'])} · {len(e['photos'])} photo{'s' if len(e['photos']) > 1 else ''}",
                            "titreCarte"))
        cases = []
        for ph in e["photos"]:
            w = QWidget()
            v = QVBoxLayout(w)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(2)
            img = vignette(ph["fichier"])
            img.setCursor(Qt.CursorShape.PointingHandCursor)
            img.setToolTip(ph["fichier"] + (f"\n{ph['commentaire']}" if ph["commentaire"] else ""))
            img.mousePressEvent = lambda _e, c=ph["fichier"]: ouvrir_fichier(c)
            v.addWidget(img)
            # légende sur des lignes courtes (température et culot / incident, date, commentaire) : jamais coupée
            morceaux = ph["legende"].split(" · ")
            quand = next((x for x in morceaux if "/" in x and ":" in x), "")
            haut = " · ".join(x for x in morceaux if x != quand)
            lignes_leg = [(t, i) for t, i in ((haut, False), (quand, False), (ph["commentaire"], True)) if t]
            for txt, ital in lignes_leg:
                lg = etiquette(f"<i>{escape(txt)}</i>" if ital else escape(txt), secondaire=True)
                lg.setFixedWidth(170)
                lg.setToolTip(txt)
                v.addWidget(lg)
            v.addStretch(1)
            # taille explicite : la rangée de photos est mesurée avant que la police (feuille de style) soit appliquée
            w.setFixedSize(170, 170 + 4 + len(lignes_leg) * (img.fontMetrics().height() + 6))
            cases.append(w)
        x.ajouter(flux_widgets(cases))
    return x


class PageRapport(QWidget):
    exporter_pdf = Signal()
    exporter_word = Signal()
    autres_formats = Signal()
    journal = Signal()
    ouvrir_fichier = Signal(str)
    ouvrir_dossier = Signal()

    def __init__(self, ctrl: Controleur):
        super().__init__()
        self.ctrl = ctrl
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(14)
        ctrl.analyses_pretes.connect(lambda _: self.isVisible() and self.rafraichir())  # résultats lus en arrière-plan
        ctrl.figures_changees.connect(lambda: self.isVisible() and self.rafraichir())  # envoi d'ana explorer

    def rafraichir(self, structure=True):
        m, r = self.ctrl.courante, self.ctrl.reglages
        if m is None:
            return
        vider(self.lay)
        rap = construire(m, r)
        self.lay.addWidget(ligne(bouton("Exporter en PDF", self.exporter_pdf.emit, accent=True, tip="Exporter en PDF (Ctrl+E pour les autres formats)"),
                                 bouton("Exporter en Word", self.exporter_word.emit, accent=True),
                                 bouton("Copier le texte", self._copier), bouton("Autres formats…", self.autres_formats.emit),
                                 "stretch", bouton("Dossier des rapports", self.ouvrir_dossier.emit, lien=True,
                                                   tip="Ouvrir le dossier partagé des rapports (donnees\\exports\\Rapports)")))
        self.lay.addWidget(ligne_emis(m, ("rapport",), self.ouvrir_fichier.emit, [], "Aucun rapport émis pour l’instant."))
        v = f"Version {m.rev} · enregistrée automatiquement le {fmt_dt(m.maj)}"
        if m.lancee:
            v += f" · lancée le {fmt_dt(m.lancee.le)} par {auteur(r, m.lancee.par)}"
        self.lay.addWidget(etiquette(v, secondaire=True))
        if m.statuts:  # dans l'application seulement (pas dans les documents)
            self.lay.addWidget(etiquette("Statut : " + texte_statut(r, m.statuts[-1]), wrap=True))
        if mention_modifiee(m):
            self.lay.addWidget(InfoBar("Détail en bas du rapport.", titre=mention_modifiee(m),
                                       actions=[bouton("Voir le journal", self.journal.emit)]))
        reste = [t for t in m.a_faire if not t.fait]
        if reste:
            self.lay.addWidget(InfoBar(" ; ".join(f"{t.categorie} : {t.texte}" for t in reste[:5]) + (" …" if len(reste) > 5 else ""),
                                       niveau="info", titre=f"{len(reste)} point{'s' if len(reste) > 1 else ''} à faire non coché{'s' if len(reste) > 1 else ''} (repris dans les PDF et le Word)"))
        n = R.numeros_a_saisir(m)
        manque = sum(len(REPERE.findall(s.texte)) for s in rap.sections)
        if n or manque:
            morceaux = []
            if n:
                morceaux.append(f"{n} numéro{'s' if n > 1 else ''} Scirius / Aramis")
            if manque:
                morceaux.append(f"{manque} information{'s' if manque > 1 else ''} du texte")
            self.lay.addWidget(InfoBar("Les valeurs manquantes sont signalées « à saisir » ; rien n’est inventé.",
                                       titre=f"{' et '.join(morceaux)} reste{'nt' if (n + manque) > 1 else ''} à saisir"))
        f, cl = carte()
        cl.addWidget(etiquette("2. Matériel et méthodes", "sousTitre"))
        for s in rap.sections:
            cl.addWidget(etiquette(s.titre, "titreCarte"))
            t = QLabel("<br><br>".join(texte_riche(x) for x in s.texte.split("\n")))
            t.setWordWrap(True)
            t.setTextFormat(Qt.TextFormat.RichText)
            t.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
            t.setStyleSheet("line-height:150%;")
            cl.addWidget(t)
        self.lay.addWidget(f)

        self.lay.addWidget(etiquette("Détail par phase du flux", "sousTitre"))
        for ph in rap.phases:
            if ph.debut_groupe:
                gt = etiquette(f"Grande étape : {ph.groupe} ({ph.groupe_plage})", "titreCarte")
                gt.setStyleSheet(f"color:{theme.P.accent};")
                self.lay.addWidget(gt)
            f, cl = carte()
            tete = [numero(ph.n)] if ph.n else []
            tete += [etiquette(ph.titre.split(" · ", 1)[-1], "titreCarte")]
            if ph.conditions:
                tete += [etiquette(ph.conditions, "conditions")]
            cl.addWidget(ligne(*tete, "stretch"))
            if ph.materiel:
                cl.addWidget(etiquette("Matériel : " + " · ".join(ph.materiel), secondaire=True, wrap=True))
            g = QGridLayout()
            g.setColumnStretch(0, 1)
            g.setColumnStretch(1, 1)
            col_r = QVBoxLayout()
            col_r.addWidget(etiquette("Réactifs", "etiquetteChamp"))
            if ph.n == 0:
                col_r.addWidget(etiquette("Sans objet au départ", secondaire=True))
            elif not ph.reactifs:
                col_r.addWidget(etiquette("aucun", secondaire=True))
            for x in ph.reactifs:
                col_r.addWidget(etiquette(f"<b>{escape(x.nom)}</b>{' · ' + escape(x.quantite) if x.quantite else ''}<br>"
                                          f"<span style='color:{theme.P.texte2}'>n° Scirius</span> {a_saisir(x.scirius)} · "
                                          f"<span style='color:{theme.P.texte2}'>emplacement</span> {a_saisir(x.emplacement)}<br>"
                                          f"<span style='color:{theme.P.texte2}'>fournisseur</span> {a_saisir(x.fournisseur)}", wrap=True))
            col_r.addStretch(1)
            col_e = QVBoxLayout()
            col_e.addWidget(etiquette("Échantillons", "etiquetteChamp"))
            if not ph.echantillons:
                col_e.addWidget(etiquette("aucun", secondaire=True))
            for x in ph.echantillons:
                col_e.addWidget(ligne(badge(R.code_badge(x.id)), etiquette(f"<b style='color:{theme.P.ambre_texte}'>{x.id}</b> "
                                                                           f"{fmt_vol(x.volume or 0)} mL · {escape(x.moment)}"), "stretch"))
                col_e.addWidget(etiquette(f"{escape(x.labo)} · {escape(', '.join(x.analyses) or 'aucune analyse')}<br>"
                                          + (f"<i>{escape(x.commentaire)}</i><br>" if x.commentaire else "")
                                          + f"<span style='color:{theme.P.texte2}'>n° Scirius</span> {a_saisir(x.scirius)} · "
                                          f"<span style='color:{theme.P.texte2}'>n° Aramis</span> {a_saisir(x.aramis)}", wrap=True))
            col_e.addStretch(1)
            g.addLayout(col_r, 0, 0)
            g.addLayout(col_e, 0, 1)
            cl.addLayout(g)
            self.lay.addWidget(f)

        if rap.reactifs:
            self.lay.addWidget(etiquette("Réactifs", "sousTitre"))
            self.lay.addWidget(table(["Réactif", "N° Scirius", "Emplacement", "Fournisseur", "Étape"],
                                     [[x.nom, x.scirius, x.emplacement, x.fournisseur, ", ".join(map(str, x.etapes))] for x in rap.reactifs]))
        if rap.echantillons:
            self.lay.addWidget(etiquette("Échantillons", "sousTitre"))
            self.lay.addWidget(table(["Éch.", "Étape", "Moment", "Volume", "N° Scirius", "N° Aramis", "Laboratoire", "Analyses"],
                                     [[x.id, x.etape, x.moment, f"{fmt_vol(x.volume or 0)} mL", x.scirius, x.aramis, x.labo, ", ".join(x.analyses)]
                                      for x in rap.echantillons]))
        res = carte_resultats(self.ctrl, m, self.rafraichir)  # résultats des échantillons (ana explorer)
        if res is not None:
            self.lay.addWidget(res)
        figs = carte_figures(self.ctrl, m, self.rafraichir, self.ouvrir_fichier.emit)  # tableau / graphiques envoyés par ana explorer
        if figs is not None:
            self.lay.addWidget(figs)
        photos = carte_photos(self.ctrl, m, self.ouvrir_fichier.emit)  # photos SamplesTEK (n° Aramis)
        if photos is not None:
            self.lay.addWidget(photos)
        if m.statuts:
            self.lay.addWidget(etiquette("Historique des statuts", "sousTitre"))
            self.lay.addWidget(table(["Date et heure", "Par", "Changement de statut"],
                                     [[fmt_dt(c.t), nom_auteur(r, c.par), f"{nom_etat(r, c.de)[0]} → {nom_etat(r, c.vers)[0]}"] for c in m.statuts]))
        if m.lancee:
            self.lay.addWidget(etiquette("Modifications après lancement", "sousTitre"))
            if m.journal:
                self.lay.addWidget(table(["Date et heure", "Par", "Modification"], [[fmt_dt(j.t), auteur(r, j.par), j.txt] for j in m.journal]))
            else:
                self.lay.addWidget(pastille("Aucune modification depuis le lancement", "ok"))
        self.lay.addStretch(1)

    def _copier(self):
        m = self.ctrl.courante
        QGuiApplication.clipboard().setText(markdown(m, self.ctrl.reglages))
        self.ctrl.toast.emit("Texte copié (Markdown)")

