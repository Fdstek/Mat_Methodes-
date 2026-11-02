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
from mat_methode.domain.models import REALISEE
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

    def rafraichir(self, structure=True):
        m, r = self.ctrl.courante, self.ctrl.reglages
        if m is None:
            return
        vider(self.lay)
        rap = construire(m, r)
        self.lay.addWidget(ligne(bouton("Exporter en PDF", self.exporter_pdf.emit, accent=True, tip="Exporter en PDF (Ctrl+E pour les autres formats)"),
                                 bouton("Exporter en Word", self.exporter_word.emit, accent=True),
                                 bouton("Copier le texte", self._copier), bouton("Autres formats…", self.autres_formats.emit),
                                 "stretch", bouton("Dossier de mes rapports", self.ouvrir_dossier.emit, lien=True)))
        self.lay.addWidget(ligne_emis(m, ("rapport",), self.ouvrir_fichier.emit, [], "Aucun rapport émis pour l’instant."))
        if m.etat != REALISEE:
            self.lay.addWidget(InfoBar("Le rapport reste consultable ; la manip apparaîtra dans la liste Rapport quand son protocole "
                                       "sera passé à « Réalisée » (Protocole).", niveau="info", titre="Manip pas encore réalisée"))
        v = f"Version {m.rev} · enregistrée automatiquement le {fmt_dt(m.maj)}"
        if m.lancee:
            v += f" · lancée le {fmt_dt(m.lancee.le)} par {m.lancee.par}"
        self.lay.addWidget(etiquette(v, secondaire=True))
        if mention_modifiee(m):
            self.lay.addWidget(InfoBar("Détail en bas du rapport.", titre=mention_modifiee(m),
                                       actions=[bouton("Voir le journal", self.journal.emit)]))
        reste = [t for t in m.a_faire if not t.fait]
        if reste:
            self.lay.addWidget(InfoBar(" ; ".join(f"{t.categorie} : {t.texte}" for t in reste[:5]) + (" …" if len(reste) > 5 else ""),
                                       niveau="info", titre=f"{len(reste)} point{'s' if len(reste) > 1 else ''} à faire (non repris dans le rapport)"))
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
                                          f"<span style='color:{theme.P.texte2}'>fournisseur</span> {a_saisir(x.fournisseur)} · "
                                          f"<span style='color:{theme.P.texte2}'>lot</span> {a_saisir(x.lot)}", wrap=True))
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
            self.lay.addWidget(table(["Réactif", "N° Scirius", "Emplacement", "Fournisseur", "Lot", "Étape"],
                                     [[x.nom, x.scirius, x.emplacement, x.fournisseur, x.lot, ", ".join(map(str, x.etapes))] for x in rap.reactifs]))
        if rap.echantillons:
            self.lay.addWidget(etiquette("Échantillons", "sousTitre"))
            self.lay.addWidget(table(["Éch.", "Étape", "Moment", "Volume", "N° Scirius", "N° Aramis", "Laboratoire", "Analyses"],
                                     [[x.id, x.etape, x.moment, f"{fmt_vol(x.volume or 0)} mL", x.scirius, x.aramis, x.labo, ", ".join(x.analyses)]
                                      for x in rap.echantillons]))
        if m.lancee:
            self.lay.addWidget(etiquette("Modifications après lancement", "sousTitre"))
            if m.journal:
                self.lay.addWidget(table(["Date et heure", "Par", "Modification"], [[fmt_dt(j.t), j.par, j.txt] for j in m.journal]))
            else:
                self.lay.addWidget(pastille("Aucune modification depuis le lancement", "ok"))
        self.lay.addStretch(1)

    def _copier(self):
        m = self.ctrl.courante
        QGuiApplication.clipboard().setText(markdown(m, self.ctrl.reglages))
        self.ctrl.toast.emit("Texte copié (Markdown)")

