"""Catalogue des opérations proposées dans « Définir le flux »."""
from __future__ import annotations

# opération -> participe passé utilisé dans le texte 2.3
OPERATIONS: dict[str, str] = {
    "chauffage": "chauffé",
    "filtration": "filtré",
    "désacidification": "désacidifié",
    "décantation": "décanté",
    "séchage": "séché",
    "centrifugation": "centrifugé",
    "lavage": "lavé",
    "broyage": "broyé",
    "extraction par solvant": "extrait",
}

# valeurs proposées à l'activation d'une condition (§6.3)
DEFAUTS_CONDITIONS = {"temperature_c": 60, "agitation_trmin": 300, "filtre_um": 5}


def participe(operation: str) -> str:
    return OPERATIONS.get(operation, f"traité ({operation})")


def est_centrifugation(operation: str) -> bool:
    return operation == "centrifugation"
