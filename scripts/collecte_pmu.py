#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MPAA X1000 FUSION
COLLECTEUR PMU UNIFIÉ — M1 À M5

Collecte :
- Programmes et réunions PMU
- Courses, horaires et disciplines
- Partants et non-partants
- Chevaux, jockeys, drivers, entraîneurs
- Musique et performances historiques
- Indicateurs explicables pour M1 à M5

Garanties :
- Aucune donnée hippique inventée
- Sources et dates conservées
- Échecs de collecte signalés
- Écriture JSON atomique
- Compatibilité avec analyse_moteurs.py

Les scores historiques sont des heuristiques,
et non des probabilités de victoire.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


# ============================================================
# CONFIGURATION
# ============================================================

PARIS = ZoneInfo("Europe/Paris")

BASE = (
    "https://online.turfinfo.api.pmu.fr"
    "/rest/client/1"
)

DESTINATION = Path("data/programme_pmu.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 MPAA-X1000/2.0",
    "Accept": "application/json",
    "Referer": "https://www.pmu.fr/",
}

TENTATIVES = 3
TIMEOUT = 20
PAUSE_COURSES = 0.2


# ============================================================
# HORLOGE OFFICIELLE PARIS
# ============================================================

def maintenant():
    return datetime.now(PARIS)


def heure_paris(timestamp):
    if timestamp is None:
        return None

    try:
        valeur = float(timestamp)

        if valeur > 100000000000:
            valeur /= 1000

        return datetime.fromtimestamp(
            valeur, PARIS
        ).isoformat()

    except (ValueError, TypeError, OverflowError, OSError):
        return None


# ============================================================
# TÉLÉCHARGEMENT PMU
# ============================================================

def telecharger(url):
    erreur = None

    for tentative in range(TENTATIVES):
        try:
            requete = urllib.request.Request(
                url,
                headers=HEADERS
            )

            with urllib.request.urlopen(
                requete,
                timeout=TIMEOUT
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
            OSError,
        ) as exc:

            erreur = str(exc)

            print(
                f"PMU tentative "
                f"{tentative + 1}/{TENTATIVES} : "
                f"{erreur}",
                flush=True
            )

            if tentative < TENTATIVES - 1:
                time.sleep(
                    3 * (tentative + 1)
                )

    raise RuntimeError(
        f"Connexion PMU impossible : {erreur}"
    )


# ============================================================
# VALIDATION DES RÉUNIONS
# ============================================================

def liste_reunions(programme):

    if not isinstance(programme, dict):
        raise ValueError(
            "Programme JSON invalide"
        )

    contenu = programme.get(
        "programme",
        programme
    )

    if not isinstance(contenu, dict):
        raise ValueError(
            "Contenu programme invalide"
        )

    reunions = contenu.get("reunions")

    if not isinstance(reunions, list):
        raise ValueError(
            "Liste des réunions absente"
        )

    if not reunions:
        raise ValueError(
            "Aucune réunion PMU disponible"
        )

    return reunions


# ============================================================
# INTELLIGENCE HISTORIQUE
# ============================================================

def notes_musique(valeur):
    """
    Analyse descriptive des huit dernières
    performances lisibles.

    Une musique insuffisante ne produit
    aucun score artificiel.

    Ces indicateurs ne constituent pas
    des probabilités de victoire.
    """

    if not isinstance(valeur, str):
        return {}

    texte = re.sub(
        r"\([^)]*\)",
        " ",
        valeur.lower()
    )

    resultats = re.findall(
        r"(?<!\d)(\d{1,2}|d|a|t)([pamhsc])",
        texte
    )

    positions = []

    for rang, discipline in resultats[:8]:

        if rang.isdigit():
            position = int(rang)

            if position <= 0:
                position = 11

        else:
            position = 11

        positions.append(position)

    if len(positions) < 3:
        return {}

    points = [
        max(0.0, 100 - 10 * (p - 1))
        for p in positions
    ]

    poids = list(
        range(len(points), 0, -1)
    )

    score_forme = (
        sum(
            point * poids_i
            for point, poids_i
            in zip(points, poids)
        )
        / sum(poids)
    )

    nb_courses = len(positions)

    victoires = sum(
        p == 1 for p in positions
    )

    places = sum(
        p <= 3 for p in positions
    )

    performances_valides = sum(
        p < 11 for p in positions
    )

    score_places = (
        100 * places / nb_courses
    )

    taux_victoire = (
        100 * victoires / nb_courses
    )

    score_fiabilite = (
        100 * performances_valides
        / nb_courses
    )

    return {
        "score_forme": round(
            score_forme, 2
        ),
        "score_performances": round(
            score_places, 2
        ),
        "taux_victoire": round(
            taux_victoire, 2
        ),
        "score_regularite": round(
            score_places, 2
        ),
        "score_fiabilite": round(
            score_fiabilite, 2
        ),
        "historique_courses_utilisees":
            nb_courses,
        "source_indicateurs":
            "Musique PMU historique, heuristique",
    }


# ============================================================
# EXTRACTION DES COURSES
# ============================================================

def extraire_courses(reunions):

    courses = []

    for reunion in reunions:

        if not isinstance(reunion, dict):
            continue

        numero_reunion = reunion.get(
            "numOfficiel"
        )

        hippodrome = reunion.get(
            "hippodrome"
        ) or {}

        if not isinstance(hippodrome, dict):
            hippodrome = {}

        nom_hippodrome = (
            hippodrome.get("libelleLong")
            or hippodrome.get("libelleCourt")
            or "Inconnu"
        )

        liste_courses = reunion.get(
            "courses", []
        )

        if not isinstance(liste_courses, list):
            continue

        for course in liste_courses:

            if not isinstance(course, dict):
                continue

            numero_course = course.get(
                "numOrdre"
            )

            if (
                numero_reunion is None
                or numero_course is None
            ):
                continue

            timestamp = course.get(
                "heureDepart"
            )

            courses.append({
                "id": (
                    f"R{numero_reunion}"
                    f"C{numero_course}"
                ),
                "reunion": numero_reunion,
                "course": numero_course,
                "hippodrome": nom_hippodrome,
                "nom": course.get(
                    "libelle", ""
                ),
                "discipline": course.get(
                    "discipline", ""
                ),
                "distance": course.get(
                    "distance"
                ),
                "heure_depart_timestamp":
                    timestamp,
                "heure_depart_paris":
                    heure_paris(timestamp),
                "nombre_partants":
                    course.get(
                        "nombrePartants"
                    ),
                "statut": course.get(
                    "statut", ""
                ),
                "participants": [],
                "participants_verifies": False,
                "non_partants": [],
            })

    return courses


# ============================================================
# COLLECTE DES PARTICIPANTS
# ============================================================

def ajouter_participants(courses, date_pmu):

    succes = 0

    for course in courses:

        url = (
            f"{BASE}/programme/{date_pmu}/"
            f"R{course['reunion']}/"
            f"C{course['course']}/participants"
        )

        course["source_participants"] = url

        try:
            resultat = telecharger(url)

            if isinstance(resultat, list):
                participants = resultat

            elif isinstance(resultat, dict):
                participants = resultat.get(
                    "participants"
                )

            else:
                raise ValueError(
                    "Réponse participants invalide"
                )

            if not isinstance(participants, list):
                raise ValueError(
                    "Format des participants incorrect"
                )

            if not participants:
                raise ValueError(
                    "Liste des participants vide"
                )

            chevaux = []
            non_partants = []

            for p in participants:

                if not isinstance(p, dict):
                    continue

                numero = p.get("numPmu")

                if numero is None:
                    continue

                musique = p.get(
                    "musique", ""
                )

                indicateurs = notes_musique(
                    musique
                )

                non_partant = (
                    p.get("nonPartant") is True
                )

                cheval = {
                    "numero": numero,
                    "nom": p.get(
                        "nom", ""
                    ),
                    "age": p.get(
                        "age"
                    ),
                    "sexe": p.get(
                        "sexe", ""
                    ),
                    "jockey": (
                        p.get("driver")
                        or p.get("jockey")
                        or ""
                    ),
                    "entraineur": p.get(
                        "entraineur", ""
                    ),
                    "non_partant": non_partant,
                    "musique": musique,
                    **indicateurs,
                }

                chevaux.append(cheval)

                if non_partant:
                    non_partants.append(
                        numero
                    )

            if not chevaux:
                raise ValueError(
                    "Aucun cheval exploitable"
                )

            course["participants"] = chevaux

            course["non_partants"] = (
                non_partants
            )

            course["nombre_partants_verifies"] = (
                sum(
                    not p["non_partant"]
                    for p in chevaux
                )
            )

            course["participants_verifies"] = True

            course["mise_a_jour_participants"] = (
                maintenant().isoformat()
            )

            succes += 1

            print(
                f"OK {course['id']} : "
                f"{len(chevaux)} chevaux, "
                f"{len(non_partants)} NP",
                flush=True
            )

        except (
            OSError,
            ValueError,
            RuntimeError,
            TypeError,
        ) as exc:

            course["erreur_participants"] = (
                str(exc)
            )

            print(
                f"Participants indisponibles "
                f"{course['id']} : {exc}",
                flush=True
            )

        time.sleep(PAUSE_COURSES)

    return succes


# ============================================================
# ENREGISTREMENT ATOMIQUE
# ============================================================

def enregistrer(donnees):

    DESTINATION.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    temporaire = DESTINATION.with_suffix(
        ".tmp"
    )

    contenu = json.dumps(
        donnees,
        ensure_ascii=False,
        indent=2,
        allow_nan=False
    ) + "\n"

    try:
        temporaire.write_text(
            contenu,
            encoding="utf-8"
        )

        os.replace(
            temporaire,
            DESTINATION
        )

    finally:
        if temporaire.exists():
            temporaire.unlink()


# ============================================================
# CONTRÔLE QUALITÉ
# ============================================================

def statistiques(courses):

    chevaux = sum(
        len(c["participants"])
        for c in courses
    )

    non_partants = sum(
        len(c["non_partants"])
        for c in courses
    )

    historiques = sum(
        1
        for c in courses
        for p in c["participants"]
        if "score_forme" in p
    )

    courses_historiques = sum(
        any(
            "score_forme" in p
            for p in c["participants"]
        )
        for c in courses
    )

    return {
        "chevaux_collectes": chevaux,
        "non_partants_detectes": non_partants,
        "chevaux_historique_exploitable":
            historiques,
        "courses_historique_exploitable":
            courses_historiques,
    }


# ============================================================
# PROGRAMME PRINCIPAL
# ============================================================

def main():

    date = maintenant()
    date_pmu = date.strftime("%d%m%Y")

    print("=" * 60)
    print("MPAA X1000 FUSION")
    print("COLLECTE PMU AUTOMATIQUE M1 À M5")
    print("=" * 60)

    print(
        "Heure Paris :",
        date.isoformat()
    )

    url = (
        f"{BASE}/programme/{date_pmu}"
    )

    try:
        programme = telecharger(url)

        reunions = liste_reunions(
            programme
        )

        courses = extraire_courses(
            reunions
        )

        if not courses:
            raise ValueError(
                "Aucune course exploitable reçue"
            )

        verifiees = ajouter_participants(
            courses,
            date_pmu
        )

        # Ne pas publier un programme sans
        # aucun participant vérifié.

        if verifiees == 0:
            raise ValueError(
                "Aucun participant vérifié : "
                "publication refusée"
            )

        stats = statistiques(courses)

        statut = (
            "OK"
            if verifiees == len(courses)
            else "PARTIEL"
        )

        donnees = {
            "logiciel":
                "MPAA X1000 FUSION",
            "version_collecteur":
                "2.0",
            "source": url,
            "date": date.strftime(
                "%Y-%m-%d"
            ),
            "mise_a_jour":
                maintenant().isoformat(),
            "fuseau_horaire":
                "Europe/Paris",
            "statut": statut,
            "nombre_reunions":
                len(reunions),
            "nombre_courses":
                len(courses),
            "courses_participants_verifies":
                verifiees,
            "statistiques": stats,
            "courses": courses,
        }

        enregistrer(donnees)

        print("=" * 60)
        print("BILAN COLLECTE PMU")
        print("=" * 60)

        print(
            "Réunions :",
            len(reunions)
        )

        print(
            "Courses :",
            len(courses)
        )

        print(
            "Courses vérifiées :",
            verifiees
        )

        print(
            "Chevaux :",
            stats["chevaux_collectes"]
        )

        print(
            "Non-partants :",
            stats["non_partants_detectes"]
        )

        print(
            "Historiques exploitables :",
            stats[
                "chevaux_historique_exploitable"
            ]
        )

        print(
            "Statut :",
            statut
        )

        print(
            "Fichier :",
            DESTINATION
        )

        print("=" * 60)

        return 0

    except (
        OSError,
        ValueError,
        RuntimeError,
        TypeError,
    ) as exc:

        print(
            "ECHEC COLLECTE PMU :",
            exc,
            file=sys.stderr
        )

        print(
            "Aucune donnée fictive publiée.",
            file=sys.stderr
        )

        return 1


if __name__ == "__main__":
    sys.exit(main())
    
