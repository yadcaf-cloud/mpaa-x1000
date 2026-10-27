
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MPAA X1000 FUSION — TESTS AUTOMATIQUES M1 À M5

Fichier : tests/test_analyse_moteurs.py

Exécution :
python -m unittest discover -s tests -p "test_*.py" -v

Tests sans connexion PMU et sans paris réels.
"""

import importlib.util
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


# Trouver automatiquement la racine du dépôt GitHub.
RACINE = Path(__file__).resolve().parents[1]

FICHIER_ANALYSE = RACINE / "scripts" / "analyse_moteurs.py"

if not FICHIER_ANALYSE.is_file():
    raise FileNotFoundError(
        f"Script introuvable : {FICHIER_ANALYSE}"
    )

spec = importlib.util.spec_from_file_location(
    "analyse_moteurs", FICHIER_ANALYSE
)

analyse = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analyse)


class TestMoteursX1000(unittest.TestCase):

    def setUp(self):
        self.maintenant = datetime(
            2026, 10, 27, 8, 0,
            tzinfo=ZoneInfo("Europe/Paris")
        )

        depart = self.maintenant + timedelta(hours=2)

        self.course = {
            "id": "R1C1",
            "reunion": 1,
            "course": 1,
            "hippodrome": "SIMULATION",
            "discipline": "ATTELE",
            "participants_verifies": True,
            "heure_depart_timestamp": int(
                depart.timestamp() * 1000
            ),
            "statut": "PROGRAMMEE",
            "participants": [
                {
                    "numero": i,
                    "nom": f"CHEVAL TEST {i}",
                    "non_partant": False
                }
                for i in range(1, 7)
            ]
        }

    def analyser(self):
        return analyse.analyser_course(
            self.course,
            self.maintenant,
            self.maintenant.date().isoformat()
        )

    def test_01_sans_donnees_aucune_selection(self):
        resultat = self.analyser()

        selections = sum(
            moteur["validation"]
            for moteur in resultat["moteurs"]
        )

        self.assertEqual(selections, 0)

    def test_02_cinq_moteurs_selectionnent(self):
        for cheval in self.course["participants"]:
            for configuration in analyse.MOTEURS.values():
                for champ in configuration[1]:
                    cheval[champ] = (
                        90 - cheval["numero"] * 5
                    )

        resultat = self.analyser()

        moteurs = resultat["moteurs"]

        self.assertEqual(
            sum(m["validation"] for m in moteurs),
            5
        )

        for moteur in moteurs:
            self.assertEqual(
                moteur["ordre_arrivee_espere"][0],
                1
            )

            self.assertFalse(moteur["fige"])

    def test_03_depart_passe_interdit(self):
        depart_passe = (
            self.maintenant - timedelta(minutes=1)
        )

        self.course["heure_depart_timestamp"] = int(
            depart_passe.timestamp() * 1000
        )

        resultat = self.analyser()

        for moteur in resultat["moteurs"]:
            self.assertFalse(moteur["validation"])

    def test_04_donnees_incompletes(self):
        self.course["participants"][0][
            "score_forme"
        ] = 99

        resultat = self.analyser()

        self.assertFalse(
            resultat["moteurs"][0]["validation"]
        )

    def test_05_egalite_des_scores(self):
        for cheval in self.course["participants"]:
            cheval["score_forme"] = 50
            cheval["score_performances"] = 50

        resultat = self.analyser()

        self.assertFalse(
            resultat["moteurs"][0]["validation"]
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
