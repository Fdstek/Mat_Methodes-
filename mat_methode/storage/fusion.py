"""Fusion automatique des Réglages partagés en cas de modification simultanée (§9.1).

Fusion à trois voies : `base` (ce que j'avais lu), `mien` (mes modifications), `leur` (le disque).
- ce que l'autre a ajouté est gardé, ce que j'ai ajouté aussi (union) ;
- une suppression n'est appliquée que si l'entrée n'a pas été modifiée par l'autre ;
- si j'ai modifié une entrée, ma version l'emporte.
"""
from __future__ import annotations

from mat_methode.domain.models import Reglages

LISTES = {  # liste -> clé d'identité (None = chaîne)
    "laboratoires": "nom", "analyses": None, "personnes": "nom", "types_demande": None, "etats": "id", "reactifs": "nom", "grandes_etapes": None, "operations": "nom", "volumes_ml": None,
}


def _cle(x, k):
    return x if k is None else x[k]


def fusion_liste(base: list, mien: list, leur: list, k) -> list:
    ib = {_cle(x, k): x for x in base}
    im = {_cle(x, k): x for x in mien}
    il = {_cle(x, k): x for x in leur}
    out = []
    for c, x in il.items():
        if c in ib and c not in im:  # je l'ai supprimée
            if x == ib[c]:
                continue  # l'autre ne l'a pas modifiée : suppression appliquée
            out.append(x)
        elif c in im and c in ib and im[c] != ib[c]:
            out.append(im[c])  # je l'ai modifiée
        else:
            out.append(x)
    for c, x in im.items():
        if c not in il and c not in ib:  # ajoutée par moi
            out.append(x)
    return out


def fusionner(base: Reglages, mien: Reglages, leur: Reglages) -> Reglages:
    b, m, l = base.to_json(), mien.to_json(), leur.to_json()
    res = dict(l)
    for nom, k in LISTES.items():
        res[nom] = fusion_liste(b.get(nom, []), m.get(nom, []), l.get(nom, []), k)
    if not res["etats"]:
        res["etats"] = l["etats"] or m["etats"]
    return Reglages.model_validate(res)
