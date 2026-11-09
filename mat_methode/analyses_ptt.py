"""Résultats d'analyses des échantillons, lus dans le classeur d'ana explorer (PTT Analysis Explorer).

Le classeur « Récapitulatif Analyses PTT.xlsm », onglet « Suivi analyses », a une ligne par échantillon et par
laboratoire (CRES, TRTG, BV Inspectorate…). Un échantillon de Mat & Méthode est retrouvé par son n° Aramis
(sinon par son n° Scirius exact) ; les lignes des différents labos sont réunies, comme dans ana explorer.

Ordre des sources, le classeur est ouvert en lecture seule :
  1. fichier choisi à la main (Réglages › Résultats d'analyses, préférence propre à chaque poste) ;
  2. fichier utilisé par ana explorer sur ce poste (%LOCALAPPDATA%\\PTTAnalysisExplorer\\settings.json) ;
  3. fichier trouvé dans les dossiers OneDrive / SharePoint synchronisés.
Les résultats lus sont gardés dans donnees\\cache\\Cache_Analyses_PTT.json tant que le classeur n'a pas changé.
"""
from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Optional

from mat_methode.scirius import cle_entete, racines_onedrive

FICHIER = "Récapitulatif Analyses PTT.xlsm"
FEUILLE = "Suivi analyses"
CACHE = "Cache_Analyses_PTT.json"
VERSION_CACHE = 1

# analyses principales d'ana explorer : libellé affiché -> nom de la colonne du classeur (même ordre)
PRINCIPALES = {
    "Phosphore": "Phosphore", "Σ Métaux hors P": "Somme des Métaux hors P", "Azote": "Azote", "Chlore total": "Chlore total",
    "FFA": "FFA Exprimé en acide oléique", "Teneur en eau": "Teneur en eau", "Calcium": "Calcium", "Fer": "Fer",
    "Magnésium": "Magnésium", "Potassium": "Potassium", "Silicium": "Silicium", "Sodium": "Sodium", "Nickel": "Nickel",
    "Vanadium": "Vanadium", "Aluminium": "Aluminium", "Cuivre": "Cuivre", "Plomb": "Plomb", "Vitesse filtration": "Vitesse moyenne",
}
UNITES_DEFAUT = {**{k: "ppm" for k in PRINCIPALES}, "FFA": "%", "Teneur en eau": "%", "Vitesse filtration": "mL/s"}
# colonnes où BV Inspectorate écrit ses résultats (utilisées quand la colonne principale est vide), comme dans ana explorer
REMPLACEMENTS = {
    "Phosphore": ["Phosphore2"], "Azote": ["Azote2", "Nitrogen"], "Teneur en eau": ["Teneur en eau2"], "FFA": ["FFA as oleic acid"],
    "Chlore total": ["Chlore, Total"], "Calcium": ["Calcium2"], "Fer": ["Fer2"], "Magnésium": ["Magnesium"], "Potassium": ["Potassium2"],
    "Silicium": ["Silicium2"], "Sodium": ["Sodium2"], "Nickel": ["Nickel2"], "Vanadium": ["Vanadium2"], "Aluminium": ["Aluminium2"],
    "Cuivre": ["Cuivre2"], "Plomb": ["Plomb2"], "Arsenic": ["Arsenic2"],
}
IDENTIFIANTS = ("N° ARAMIS", "N° SCIRIUS", "Labo", "Date", "Type expérience", "N° expérience", "Produit")
# mots qui montrent qu'une colonne n'est pas une analyse (identifiants, textes, specs, abattements…)
MOTS_EXCLUS = ("date", "n°", "commentaire", "remarque", "observation", "lien", "statut", "demandeur", "pilote", "labo",
               "référence", "reference", "usine", "pays", "produit", "contexte", "type", "spec", "abat", "∆", "delta",
               "écart", "ecart", "unnamed", "aramis", "scirius", "expérience", "experience", "échantillon", "echantillon",
               "étape", "etape", "heure", "jour")
ARAMIS_VIDES = {"", "-", "NO", "N/A", "NA", "NAN", "NONE", "NULL"}
UNITE = re.compile(r"^(mg/kg|mg/l|µg/g|ppm|%|%\s*\(m/m\)|%\s*m/m|ml/s|°c|kg/l|mm²/s|meq\s*ao/kg|mg\s*koh/g|g/100g)$", re.I)


def texte(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        if math.isnan(v):
            return ""
        if v.is_integer():
            return str(int(v))
    if isinstance(v, datetime):
        return v.strftime("%d/%m/%Y")
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")
    t = str(v)
    for ch in ("\xa0", "​", "‌", "‍", "⁠", "﻿", "\r", "\n", "\t"):
        t = t.replace(ch, " ")
    return " ".join(t.split())


def cle_aramis(v) -> str:
    """« 2026-001234 », « 2026001234.0 »… -> clé comparable (majuscules, sans espaces) ; vide si absent."""
    t = texte(v).upper().replace(" ", "")
    return "" if t in ARAMIS_VIDES else t


def nombre(v) -> Optional[float]:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return None if isinstance(v, float) and math.isnan(v) else float(v)
    t = texte(v).replace(" ", "").replace(",", ".")
    if not t or t[0] in "<>":
        return None
    try:
        return float(t)
    except ValueError:
        return None


def valeur_affichee(v) -> str:
    """Valeur du classeur telle qu'on l'écrit dans un document : 12,5 · 1 250 · <LQ · <5."""
    t = texte(v)
    if not t:
        return ""
    if t[0] in "<>":
        return t
    n = nombre(v)
    if n is None:
        return t
    if abs(n) >= 1000:
        return f"{n:,.0f}".replace(",", " ")
    return f"{n:.4g}".replace(".", ",")


def unite_normale(u) -> str:
    k = texte(u).casefold().replace(" ", "")
    return {"mg/kg": "ppm", "ppm": "ppm", "%": "%", "%(m/m)": "%", "%m/m": "%", "ml/s": "mL/s", "mg/l": "mg/L"}.get(k, texte(u))


def nom_analyse_refuse(nom: str) -> bool:
    low = texte(nom).casefold()
    return (not low or low.startswith(("_", "nom")) or len(low) > 60 or any(m in low for m in MOTS_EXCLUS))


# ------------------------------------------------------------------ lecture du classeur
def lire_classeur(chemin: Path, etape: Callable[[str], None] = lambda t: None) -> dict:
    """{"analyses": [libellés, dans l'ordre], "unites": {libellé: unité}, "lignes": [{"aramis", "scirius", "labo", "date",
    "valeurs": {libellé: valeur brute en texte}}]} — seules les lignes qui ont un n° Aramis ou Scirius et un résultat."""
    from openpyxl import load_workbook
    etape(f"Ouverture de {Path(chemin).name} en lecture seule…")
    wb = load_workbook(chemin, read_only=True, data_only=True, keep_links=False)
    try:
        feuille = next((n for n in wb.sheetnames if cle_entete(n) == cle_entete(FEUILLE)), None)
        if feuille is None:
            raise ValueError(f"onglet « {FEUILLE} » introuvable")
        ws = wb[feuille]
        entete, haut = None, []
        for valeurs in ws.iter_rows(min_row=1, max_row=15, values_only=True):
            vals = [texte(x) for x in valeurs]
            if "N° expérience" in vals and "Produit" in vals:
                entete = vals
                break
            haut.append(vals)
        if entete is None:
            raise ValueError("ligne d'en-têtes introuvable (colonnes « N° expérience » et « Produit »)")
        # unités : la ligne au-dessus de l'en-tête qui en contient le plus
        ligne_u = max(haut[-6:], key=lambda r: sum(1 for x in r if UNITE.match(x)), default=[])
        if sum(1 for x in ligne_u if UNITE.match(x)) < 4:
            ligne_u = []
        pos: dict[str, int] = {}
        for i, h in enumerate(entete):
            if h and h not in pos:
                pos[h] = i
        principales_col = {c: lib for lib, c in PRINCIPALES.items()}
        secours = {c: lib for lib, cs in REMPLACEMENTS.items() for c in cs}
        colonnes: list[tuple[str, int, str]] = []  # (libellé, position, rôle : principale / secours / autre)
        for h, i in pos.items():
            if h in IDENTIFIANTS:
                continue
            if h in principales_col:
                colonnes.append((principales_col[h], i, "principale"))
            elif h in secours:
                colonnes.append((h, i, "secours"))
            elif not nom_analyse_refuse(h):
                colonnes.append((h, i, "autre"))
        idx = {k: pos.get(k) for k in ("N° ARAMIS", "N° SCIRIUS", "Labo", "Date")}
        brutes, n = [], 0
        for valeurs in ws.iter_rows(min_row=len(haut) + 2, values_only=True):
            n += 1
            if n % 500 == 0:
                etape(f"Lecture des résultats : ligne {n}…")

            def v(i):
                return valeurs[i] if i is not None and i < len(valeurs) else None
            ar, sc = cle_aramis(v(idx["N° ARAMIS"])), texte(v(idx["N° SCIRIUS"]))
            if not ar and not sc:
                continue
            vals = {lib: texte(v(i)) for lib, i, _ in colonnes if texte(v(i))}
            if vals:
                brutes.append({"aramis": ar, "scirius": sc, "labo": texte(v(idx["Labo"])), "date": texte(v(idx["Date"])), "valeurs": vals})
    finally:
        wb.close()
    # une colonne « autre » n'est gardée que si elle est surtout numérique (comme dans ana explorer)
    gardees = []
    for lib, i, role in colonnes:
        if role != "autre":
            gardees.append((lib, i, role))
            continue
        vals = [ln["valeurs"][lib] for ln in brutes if lib in ln["valeurs"]]
        if vals and sum(1 for x in vals if nombre(x) is not None or x[:1] in "<>") >= 0.6 * len(vals):
            gardees.append((lib, i, role))
    noms = {lib for lib, _, _ in gardees}
    for ln in brutes:
        ln["valeurs"] = {k: x for k, x in ln["valeurs"].items() if k in noms}
    lignes = [ln for ln in brutes if ln["valeurs"]]
    ordre = [lib for lib in PRINCIPALES if lib in noms] + [lib for lib, _, r in gardees if r == "autre"]
    unites = {}
    for lib, i, role in gardees:
        u = unite_normale(ligne_u[i]) if i < len(ligne_u) and UNITE.match(ligne_u[i]) else ""
        cible = secours.get(lib, lib) if role == "secours" else lib
        if u and cible not in unites:
            unites[cible] = u
    for lib, u in UNITES_DEFAUT.items():
        unites.setdefault(lib, u)
    etape(f"{len(lignes)} lignes de résultats lues")
    return {"analyses": ordre, "unites": unites, "lignes": lignes}


# ------------------------------------------------------------------ résultats d'un échantillon
def consolider(lignes: list[dict], analyses: list[str]) -> tuple[dict[str, str], dict[str, str], list[str]]:
    """Lignes d'un même échantillon (un labo par ligne) -> (valeurs, labo de chaque valeur, labos).
    Le chlore vient d'ATCO quand ATCO l'a rendu ; une colonne principale vide prend la valeur de la colonne BV."""
    valeurs, sources, labos = {}, {}, []
    for ln in lignes:
        if ln.get("labo") and ln["labo"] not in labos:
            labos.append(ln["labo"])
    remplacantes = {c for cs in REMPLACEMENTS.values() for c in cs}
    for lib in analyses:
        if lib in remplacantes:
            continue
        src = lignes
        if lib == "Chlore total":
            atco = [ln for ln in lignes if ln.get("labo") == "ATCO" and ln["valeurs"].get(lib)]
            src = atco or lignes
        for cols in ([lib], REMPLACEMENTS.get(lib, [])):
            trouve = next(((ln["valeurs"][c], ln.get("labo", "")) for c in cols for ln in src if ln["valeurs"].get(c)), None)
            if trouve:
                valeurs[lib], sources[lib] = trouve
                break
    for lib, cs in REMPLACEMENTS.items():  # colonne BV sans colonne principale dans le classeur
        if lib not in valeurs:
            trouve = next(((ln["valeurs"][c], ln.get("labo", "")) for c in cs for ln in lignes if ln["valeurs"].get(c)), None)
            if trouve:
                valeurs[lib], sources[lib] = trouve
    return valeurs, sources, labos


@dataclass
class Resultats:
    """Résultats lus : index par n° Aramis et par n° Scirius."""
    analyses: list[str] = field(default_factory=list)
    unites: dict[str, str] = field(default_factory=dict)
    par_aramis: dict[str, list[dict]] = field(default_factory=dict)
    par_scirius: dict[str, list[dict]] = field(default_factory=dict)
    origine: str = ""
    ecartes: list[str] = field(default_factory=list)

    @classmethod
    def depuis(cls, d: dict, origine: str = "") -> "Resultats":
        r = cls(analyses=list(d.get("analyses", [])), unites=dict(d.get("unites", {})), origine=origine)
        for ln in d.get("lignes", []):
            if ln.get("aramis"):
                r.par_aramis.setdefault(ln["aramis"], []).append(ln)
            if ln.get("scirius"):
                r.par_scirius.setdefault(texte(ln["scirius"]).upper().replace(" ", ""), []).append(ln)
        return r

    @property
    def vide(self) -> bool:
        return not self.par_aramis and not self.par_scirius

    def lignes_de(self, aramis: str | None, scirius: str | None) -> list[dict]:
        if aramis and cle_aramis(aramis) in self.par_aramis:
            return self.par_aramis[cle_aramis(aramis)]
        if scirius:
            return self.par_scirius.get(texte(scirius).upper().replace(" ", ""), [])
        return []

    def pour_export(self, prelevements: list[dict]) -> dict | None:
        """Bloc « resultats » du JSON d'échange (PDF, Word, protocole) ; None si aucun échantillon n'a de résultat."""
        echs, utilisees = [], set()
        for p in prelevements:
            lignes = self.lignes_de(p.get("aramis"), p.get("scirius"))
            if not lignes:
                continue
            valeurs, sources, labos = consolider(lignes, self.analyses)
            if not valeurs:
                continue
            utilisees |= set(valeurs)
            dates = [ln["date"] for ln in lignes if ln.get("date")]
            echs.append({"id": p["id"], "aramis": p.get("aramis") or "", "labos": labos, "date": dates[0] if dates else "",
                         "valeurs": {k: valeur_affichee(v) for k, v in valeurs.items()}, "sources": sources})
        if not echs:
            return None
        ordre = [a for a in self.analyses if a in utilisees] + sorted(utilisees - set(self.analyses))
        return {"source": self.origine, "analyses": [{"nom": a, "unite": self.unites.get(a, "")} for a in ordre], "echantillons": echs}


def libelle(a: dict) -> str:
    """« Phosphore (ppm) »."""
    return f"{a['nom']} ({a['unite']})" if a.get("unite") else a["nom"]


def resume_echantillon(res: dict | None, ident: str, limite: int = 0) -> str:
    """« Phosphore 12 ppm · Azote 300 ppm … » pour un échantillon (vide s'il n'a pas de résultat)."""
    if not res:
        return ""
    e = next((x for x in res.get("echantillons", []) if x["id"] == ident), None)
    if e is None:
        return ""
    morceaux = [f"{a['nom']} {e['valeurs'][a['nom']]}{' ' + a['unite'] if a.get('unite') and e['valeurs'][a['nom']][:1] not in '<>' else ''}"
                for a in res["analyses"] if a["nom"] in e["valeurs"]]
    if limite and len(morceaux) > limite:
        morceaux = morceaux[:limite] + [f"… (+{len(morceaux) - limite})"]
    return " · ".join(morceaux)


def tableaux(res: dict, par_tableau: int = 7) -> list[tuple[list[str], list[list[str]]]]:
    """Tableaux « une ligne par échantillon, une colonne par analyse » (en-têtes, lignes), coupés toutes les `par_tableau` analyses.
    1re colonne : « S2 », puis le n° Aramis et les labos sur les lignes suivantes (séparés par « \n »)."""
    out = []
    echs, analyses = res.get("echantillons", []), res.get("analyses", [])
    for k in range(0, max(len(analyses), 1), par_tableau):
        part = analyses[k:k + par_tableau]
        entetes = ["Échantillon"] + [libelle(a) for a in part]
        lignes = [["\n".join(x for x in (e["id"], e.get("aramis") or "", ", ".join(e.get("labos", []))) if x)]
                  + [e["valeurs"].get(a["nom"], "—") for a in part] for e in echs]
        out.append((entetes, lignes))
    return out


# ------------------------------------------------------------------ recherche du classeur et cache
def chemin_ana_explorer() -> Optional[Path]:
    """Classeur utilisé par ana explorer sur ce poste (son fichier de réglages local)."""
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        return None
    try:
        d = json.loads((Path(base) / "PTTAnalysisExplorer" / "settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    p = texte(d.get("workbook")) if isinstance(d, dict) else ""
    return Path(p) if p else None


def fichiers_synchronises(racines: list[Path] | None = None, profondeur: int = 6) -> list[Path]:
    trouves = []
    for racine in racines if racines is not None else racines_onedrive():
        base = len(racine.parts)
        for courant, dossiers, fichiers in os.walk(racine):
            if len(Path(courant).parts) - base >= profondeur:
                dossiers[:] = []
            dossiers[:] = [d for d in dossiers if not d.startswith((".", "~"))]
            trouves += [Path(courant) / f for f in fichiers if cle_entete(f) == cle_entete(FICHIER)]
    return sorted(dict.fromkeys(trouves), key=lambda p: -p.stat().st_mtime if p.exists() else 0)


class SourceAnalyses:
    """Trouve et lit le classeur des analyses ; garde les résultats dans le dossier cache partagé."""

    def __init__(self, cache: Path, fichier_choisi: str = "", racines: list[Path] | None = None,
                 ana_explorer: Callable[[], Optional[Path]] = chemin_ana_explorer):
        self.cache = Path(cache)
        self.fichier_choisi = fichier_choisi
        self.racines = racines
        self.ana_explorer = ana_explorer

    @property
    def f_cache(self) -> Path:
        return self.cache / CACHE

    @staticmethod
    def _signature(p) -> list | None:
        try:
            st = Path(p).stat()
            return [st.st_mtime, st.st_size]
        except (OSError, TypeError):
            return None

    def candidats(self) -> list[tuple[Path, str]]:
        out = []
        if self.fichier_choisi:
            out.append((Path(self.fichier_choisi), "fichier choisi dans les Réglages"))
        p = self.ana_explorer()
        if p is not None:
            out.append((p, "fichier d’ana explorer"))
        out += [(f, "fichier synchronisé") for f in fichiers_synchronises(self.racines)]
        vus, res = set(), []
        for p, o in out:
            if str(p).lower() not in vus and p.name and not p.name.startswith("~$"):
                vus.add(str(p).lower())
                res.append((p, o))
        return res

    def _lire_cache(self) -> Optional[dict]:
        try:
            d = json.loads(self.f_cache.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return d if isinstance(d, dict) and d.get("version") == VERSION_CACHE and d.get("lignes") is not None else None

    def _ecrire_cache(self, d: dict) -> None:
        try:
            self.cache.mkdir(parents=True, exist_ok=True)
            tmp = self.f_cache.with_name(self.f_cache.name + f".{os.getpid()}.tmp")
            tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.f_cache)
        except OSError:
            pass

    def lire(self, forcer: bool = False, etape: Callable[[str], None] = lambda t: None) -> Resultats:
        ecartes = []
        cache = self._lire_cache()
        etape("Recherche du classeur des analyses…")
        for chemin, origine in self.candidats():
            sig = self._signature(chemin)
            if sig is None:
                continue
            if not forcer and cache and cache.get("source") == str(chemin) and cache.get("signature") == sig:
                return Resultats.depuis(cache, f"{chemin.name} ({origine}), lu le {datetime.fromtimestamp(cache['lu_le']):%d/%m à %H:%M}")
            try:
                d = lire_classeur(chemin, etape)
            except Exception as ex:  # fichier verrouillé, autre classeur…
                ecartes.append(f"{chemin} : {ex}")
                continue
            d.update(version=VERSION_CACHE, source=str(chemin), signature=sig, lu_le=datetime.now().timestamp())
            self._ecrire_cache(d)
            return Resultats.depuis(d, f"{chemin.name} ({origine}), lu le {datetime.now():%d/%m à %H:%M}")
        if cache:  # classeur inaccessible sur ce poste : dernière lecture partagée
            r = Resultats.depuis(cache, f"dernière lecture du {datetime.fromtimestamp(cache['lu_le']):%d/%m/%Y à %H:%M} ({Path(cache['source']).name})")
            r.ecartes = ecartes
            return r
        r = Resultats()
        r.ecartes = ecartes or [f"« {FICHIER} » introuvable (ni choisi, ni ouvert par ana explorer sur ce poste, ni dans OneDrive)"]
        return r


__all__ = ["FICHIER", "Resultats", "SourceAnalyses", "lire_classeur", "consolider", "resume_echantillon", "tableaux", "libelle"]
