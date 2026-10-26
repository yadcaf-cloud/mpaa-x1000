#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MPAA X1000 - Analyse prudente M1 a M5."""

import json
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path("data/programme_pmu.json")
SORTIE = Path("data/analyses_moteurs.json")

MOTEURS = {
    "M1": "Forme et performances",
    "M2": "Aptitudes et conditions",
    "M3": "Engagement et entourage",
    "M4": "Valeur et potentiel",
    "M5": "Regularite et risques",
}


def analyser():
    donnees = json.loads(SOURCE.read_text(encoding="utf-8"))

    resultat = {
        "date": donnees.get("date"),
        "heure_analyse": datetime.now(timezone.utc).isoformat(),
        "source": donnees.get("source"),
        "statut": "EN_ATTENTE_DONNEES_DETAILLEES",
        "moteurs": {},
        "courses": [],
    }

    for code, specialite in MOTEURS.items():
        resultat["moteurs"][code] = {
            "specialite": specialite,
            "statut": "EN_ATTENTE_DONNEES",
            "pronostic": [],
            "fige": False,
        }

    if donnees.get("statut") != "DONNEES_RECUES":
        raise RuntimeError("Programme PMU indisponible")

    for reunion in donnees.get("reunions", []):
        if not isinstance(reunion, dict):
            continue

        hippodrome = reunion.get("hippodrome") or {}
        if not isinstance(hippodrome, dict):
            hippodrome = {}

        for course in reunion.get("courses", []):
            if not isinstance(course, dict):
                continue

            resultat["courses"].append({
                "reunion": reunion.get("numOfficiel"),
                "hippodrome": hippodrome.get("libelleCourt"),
                "course": course.get("numOrdre"),
                "depart": course.get("heureDepart"),
                "partants": course.get("nombreDeclaresPartants"),
                "qualification": "A_ETUDIER",
                "fige": False,
            })

    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_text(
        json.dumps(resultat, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("Courses detectees :", len(resultat["courses"]))
    print("Moteurs prepares :", len(MOTEURS))
    print("Pronostics : attente des donnees cheval par cheval")
    print("Analyse terminee")


if __name__ == "__main__":
    analyser()
  
