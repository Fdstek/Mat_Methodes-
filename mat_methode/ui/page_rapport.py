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
from mat_methode.domain.models import ARCHIVEE, NON_REALISEE
from mat_methode.domain.texte import fmt_dt, fmt_vol
from mat_methode.report.rapport import REPERE, construire, markdown, mention_modifiee
from mat_methode.ui import theme
from mat_methode.ui.controleur import Controleur
from mat_methode.ui.widgets import InfoBar, Liste, badge, bouton, carte, etiquette, ligne, numero, pastille, vider


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


class PageRapport(QWidget):
    exporter_pdf = Signal()
    exporter_word = Signal()
    autres_formats = Signal()
    journal = Signal()

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
        etats = [e.id for e in r.etats] + [NON_REALISEE] + ([ARCHIVEE] if m.etat == ARCHIVEE else [])
        etat = Liste(etats, m.etat, vide=None, libelles={**{e.id: e.nom for e in r.etats}, ARCHIVEE: "Archivée", NON_REALISEE: "Non réalisée"})
        etat.setAccessibleName("État de la manip")
        etat.choisi.connect(lambda v: (setattr(m, "etat", v), self.ctrl.toucher(m)))
        etat.setEnabled(not self.ctrl.lecture_seule)
        self.lay.addWidget(ligne(bouton("Exporter en PDF", self.exporter_pdf.emit, accent=True, tip="Exporter en PDF (Ctrl+E pour les autres formats)"),
                                 bouton("Exporter en Word", self.exporter_word.emit, accent=True),
                                 bouton("Copier le texte", self._copier), bouton("Autres formats…", self.autres_formats.emit),
                                 "stretch", etiquette("État de la manip", secondaire=True), etat))
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
            t = QLabel(texte_riche(s.texte))
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
                                          f"<span style='color:{theme.P.texte2}'>n° Scirius</span> {a_saisir(x.scirius)} · "
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

