"""Disposition du schéma du flux (PDF et Word) : lignes de 5 cartes ; un bloc d'étapes en parallèle met chaque voie dans sa colonne,
puis l'étape suivante réunit les voies. Retourne la case de chaque étape et les liens (flèches) à tracer."""
from __future__ import annotations

PAR_LIGNE = 5


def colonnes_voies(nvoies: int, par_ligne: int = PAR_LIGNE) -> list[int]:
    """Colonnes des voies, réparties sur la largeur (2 voies : colonnes 1 et 3 ; 3 voies : 0, 2 et 4 ; 4 voies : 0, 1, 3 et 4)."""
    choix = {1: [2], 2: [1, 3], 3: [0, 2, 4], 4: [0, 1, 3, 4]}.get(nvoies, list(range(par_ligne)))
    return [min(c, par_ligne - 1) for c in choix][:max(nvoies, 1)]


def disposer(etapes: list[dict], par_ligne: int = PAR_LIGNE) -> tuple[list[tuple[int, int]], list[tuple[int, int]], dict[int, str]]:
    """cases[i] = (ligne, colonne) ; liens = [(i, j)] : flèche de l'étape i vers l'étape j ; lettres = {i: « A »} pour la 1re étape de chaque voie."""
    cases: list[tuple[int, int]] = [(0, 0)] * len(etapes)
    liens: list[tuple[int, int]] = []
    lettres: dict[int, str] = {}
    r, k, precedents, i = 0, 0, [], 0
    while i < len(etapes):
        par = etapes[i].get("parallele")
        if not par:
            if k >= par_ligne:
                r, k = r + 1, 0
            cases[i] = (r, k)
            liens += [(p, i) for p in precedents]
            precedents, k, i = [i], k + 1, i + 1
            continue
        fin = i
        while fin + 1 < len(etapes) and (etapes[fin + 1].get("parallele") or {}).get("id") == par["id"]:
            fin += 1
        voies: dict[int, list[int]] = {}
        for j in range(i, fin + 1):
            voies.setdefault(etapes[j]["parallele"]["voie"], []).append(j)
        r0 = r + 1 if k > 0 else r  # le bloc commence sur sa propre ligne
        cols = colonnes_voies(max(len(voies), int(par.get("nvoies") or 1)), par_ligne)
        derniers = []
        for v, (num, idx) in enumerate(sorted(voies.items())):
            col = cols[min(num, len(cols) - 1)]
            lettres[idx[0]] = etapes[idx[0]]["parallele"].get("lettre", "")
            for h, j in enumerate(idx):
                cases[j] = (r0 + h, col)
                liens += [(p, j) for p in precedents] if h == 0 else [(idx[h - 1], j)]
            derniers.append(idx[-1])
        precedents = derniers
        r, k, i = r0 + max(len(v) for v in voies.values()), par_ligne // 2, fin + 1  # l'étape suivante réunit les voies, au centre
    return cases, liens, lettres
