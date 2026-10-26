#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""MPAA X1000 - Test de connexion aux programmes PMU."""

import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
BASE = "https://online.turfinfo.api.pmu.fr/rest/client/7"
SORTIE = Path("data/programme_pmu.json")


def collecter():
    maintenant = datetime.now(PARIS)
    date_pmu = maintenant.strftime("%d%m%Y")
    url = f"{BASE}/programme/{date_pmu}"

    resultat = {
        "date": maintenant.date().isoformat(),
        "heure_collecte": datetime.now(
            timezone.utc
        ).isoformat(),
        "source": url,
        "statut": "INDISPONIBLE",
        "reunions": []
    }

    try:
        requete = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "MPAA-X1000/1.0"
            }
        )

        with urllib.request.urlopen(
            requete, timeout=25
        ) as reponse:
            donnees = json.load(reponse)

        programme = donnees.get("programme", {})
        reunions = programme.get("reunions")

        if not isinstance(reunions, list):
            raise ValueError("Format PMU non reconnu")

        resultat["reunions"] = reunions
        resultat["statut"] = "DONNEES_RECUES"

    except Exception as erreur:
        resultat["erreur"] = str(erreur)
        print("Connexion PMU non valide :", erreur)

    SORTIE.parent.mkdir(
        parents=True, exist_ok=True
    )

    SORTIE.write_text(
        json.dumps(
            resultat,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print("Statut :", resultat["statut"])
    print("Réunions :", len(resultat["reunions"]))

    return resultat["statut"] == "DONNEES_RECUES"


if __name__ == "__main__":
    sys.exit(0 if collecter() else 1)
  
