import os
import time
from pathlib import Path

import pytest

os.environ["TZ"] = "Europe/Paris"  # les références sont en heure de Paris (§10)
if hasattr(time, "tzset"):  # absent sous Windows : on y suppose un PC réglé sur l'heure de Paris
    time.tzset()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

EXEMPLES = Path(__file__).resolve().parents[1] / "docs" / "cahier_des_charges" / "exemples"


@pytest.fixture
def exemples():
    from mat_methode.domain.prototype import exemples as ex
    return ex()


@pytest.fixture
def reglages(exemples):
    return exemples[0]


@pytest.fixture
def ethanol(exemples):
    """La manip d'exemple « Désacidification éthanol »."""
    return exemples[1][0]
