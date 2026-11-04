"""Journal des bugs et des bonnes idées : une demande par fichier (`donnees\\demandes\\<id>.json`), pièces jointes à côté."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from mat_methode.domain.models import maintenant_iso, nouvel_id
from mat_methode.domain.texte import fmt_dt

TYPES_DEMANDE = ("Bug", "Bonne idée")
STATUTS_DEMANDE = ("Nouvelle", "En cours", "Traitée", "Refusée")


class ChangementDemande(BaseModel):
    model_config = ConfigDict(extra="ignore")
    t: str
    par: str  # IGG
    de: str
    vers: str


class Demande(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=nouvel_id)
    type: str = "Bug"
    titre: str = ""
    texte: str = ""
    statut: str = "Nouvelle"
    auteur: str = ""  # IGG de la personne qui a écrit la demande
    cree: str = Field(default_factory=maintenant_iso)
    maj: str = Field(default_factory=maintenant_iso)
    pieces: list[str] = Field(default_factory=list)  # noms des fichiers joints
    historique: list[ChangementDemande] = Field(default_factory=list)

    def changer_statut(self, statut: str, par: str) -> bool:
        if statut == self.statut or statut not in STATUTS_DEMANDE:
            return False
        self.historique = self.historique + [ChangementDemande(t=maintenant_iso(), par=par, de=self.statut, vers=statut)]
        self.statut, self.maj = statut, maintenant_iso()
        return True


def vers_markdown(demandes: list[Demande], nom_de, version: str = "") -> str:
    """Toutes les demandes en un fichier .md (lisible tel quel et collable dans une conversation)."""
    out = [f"# Bugs et idées — Mat & Méthode{' ' + version if version else ''}", "", f"_{len(demandes)} demande(s)_", ""]
    for d in demandes:
        out += [f"## [{d.statut}] {d.type} : {d.titre or '(sans titre)'}", "",
                f"- Écrite par {nom_de(d.auteur)} le {fmt_dt(d.cree)}", f"- Statut : {d.statut}"]
        if d.pieces:
            out.append("- Pièces jointes : " + ", ".join(d.pieces))
        for c in d.historique:
            out.append(f"- {fmt_dt(c.t)} : {c.de} → {c.vers} par {nom_de(c.par)}")
        out += ["", d.texte.strip() or "_(pas de description)_", ""]
    return "\n".join(out)
