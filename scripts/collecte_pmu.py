#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""MPAA X1000 FUSION - Collecte réelle des programmes PMU."""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
BASE = "https://online.turfinfo.api.pmu.fr/rest/client/1"
DESTINATION = Path("data/programme_pmu.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 MPAA-X1000/1.0",
    "Accept": "application/json",
    "Referer": "https://www.pmu.fr/",
}


def maintenant():
    return datetime.now(PARIS)


def telecharger(url):
    erreur = None

    for tentative in range(3):
        try:
            requete = urllib.request.Request(
                url, headers=HEADERS
            )
            with urllib.request.urlopen(
                requete, timeout=20
            ) as reponse:
                if reponse.status != 200:
                    raise RuntimeError(
                        f"HTTP {reponse.status}"
                    )
                return json.load(reponse)

        except (
            urllib.error.URLError,
            TimeoutError,
            ValueError,
            RuntimeError,
        ) as exc:
            erreur = str(exc)
            print(
                f"Tentative {tentative + 1}/3 : {erreur}",
                flush=True,
            )
            if tentative < 2:
                time.sleep(3 * (tentative + 1))

    raise RuntimeError(
        f"Connexion PMU impossible : {erreur}"
    )


def liste_reunions(programme):
    if not isinstance(programme, dict):
        raise ValueError("Programme JSON invalide")

    donnees = programme.get("programme", programme)
    reunions = donnees.get("reunions")

    if not isinstance(reunions, list):
        raise ValueError("Liste des réunions absente")

    return reunions


def extraire_courses(reunions):
    courses = []

    for reunion in reunions:
        numero_reunion = reunion.get("numOfficiel")
        hippodrome = reunion.get("hippodrome", {})

        if not isinstance(hippodrome, dict):
            hippodrome = {}

        nom_hippodrome = hippodrome.get(
            "libelleLong",
            hippodrome.get("libelleCourt", "Inconnu")
        )

        for course in reunion.get("courses", []):
            numero_course = course.get("numOrdre")

            if numero_reunion is None or numero_course is None:
                continue

            courses.append({
                "id": f"R{numero_reunion}C{numero_course}",
                "reunion": numero_reunion,
                "course": numero_course,
                "hippodrome": nom_hippodrome,
                "nom": course.get("libelle", ""),
                "discipline": course.get("discipline", ""),
                "distance": course.get("distance"),
                "heure_depart_timestamp": course.get(
                    "heureDepart"
                ),
                "nombre_partants": course.get(
                    "nombrePartants"
                ),
                "statut": course.get("statut", ""),
                "participants": [],
                "participants_verifies": False,
            })

    return courses


def ajouter_participants(courses, date_pmu):
    succes = 0

    for course in courses:
        url = (
            f"{BASE}/programme/{date_pmu}/"
            f"R{course['reunion']}/"
            f"C{course['course']}/participants"
        )

        try:
            resultat = telecharger(url)

            if isinstance(resultat, list):
                participants = resultat
            elif isinstance(resultat, dict):
                participants = resultat.get(
                    "participants", []
                )
            else:
                participants = []

            if not isinstance(participants, list):
                raise ValueError(
                    "Format des participants incorrect"
                )

            course["participants"] = [
                {
                    "numero": p.get("numPmu"),
                    "nom": p.get("nom", ""),
                    "age": p.get("age"),
                    "sexe": p.get("sexe", ""),
                    "jockey": p.get(
                        "driver", p.get("jockey", "")
                    ),
                    "entraineur": p.get(
                        "entraineur", ""
                    ),
                    "non_partant": p.get(
                        "nonPartant", False
                    ),
                }
                for p in participants
                if isinstance(p, dict)
            ]

            course["participants_verifies"] = True
            succes += 1

        except Exception as exc:
            course["erreur_participants"] = str(exc)
            print(
                f"Participants indisponibles "
                f"{course['id']}: {exc}"
            )

        time.sleep(0.2)

    return succes


def enregistrer(donnees):
    DESTINATION.parent.mkdir(
        parents=True, exist_ok=True
    )

    temporaire = DESTINATION.with_suffix(".tmp")
    temporaire.write_text(
        json.dumps(
            donnees,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )
    os.replace(temporaire, DESTINATION)


def main():
    date = maintenant()
    date_pmu = date.strftime("%d%m%Y")

    print("MPAA X1000 - COLLECTE PMU")
    print("Date :", date.isoformat())

    url = f"{BASE}/programme/{date_pmu}"

    try:
        programme = telecharger(url)
        reunions = liste_reunions(programme)
        courses = extraire_courses(reunions)

        if not reunions or not courses:
            raise ValueError(
                "Aucune course exploitable reçue"
            )

        verifiees = ajouter_participants(
            courses, date_pmu
        )

        donnees = {
            "logiciel": "MPAA X1000 FUSION",
            "source": url,
            "date": date.strftime("%Y-%m-%d"),
            "mise_a_jour": maintenant().isoformat(),
            "statut": (
                "OK" if verifiees == len(courses)
                else "PARTIEL"
            ),
            "nombre_reunions": len(reunions),
            "nombre_courses": len(courses),
            "courses_participants_verifies": verifiees,
            "courses": courses,
        }

        enregistrer(donnees)

        print("Réunions :", len(reunions))
        print("Courses :", len(courses))
        print("Participants vérifiés :", verifiees)
        print("Statut :", donnees["statut"])
        print("Fichier :", DESTINATION)

        return 0 if verifiees else 1

    except Exception as exc:
        print("ECHEC COLLECTE PMU :", exc)
        print(
            "Aucune fausse donnée ne sera publiée."
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
        
