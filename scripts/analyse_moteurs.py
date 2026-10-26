#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MPAA X1000 FUSION — ANALYSE UNIFIEE M1 A M5

Entree :
    data/programme_pmu.json

Sortie :
    data/analyses_moteurs.json

Principes :
- Donnees reelles uniquement.
- Aucun score sportif invente.
- Cinq moteurs independants.
- Aucun pronostic retroactif.
- Aucun FIGE automatique dans ce module.
- Aucun pari reellement place.
- Classements indicatifs, non garantis.

Compatible Python 3.12 et GitHub Actions.
"""

import argparse
import json
import math
import os
import re
import sys

from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


PARIS = ZoneInfo("Europe/Paris")

SOURCE = Path("data/programme_pmu.json")
SORTIE = Path("data/analyses_moteurs.json")

MOTEURS = {
    "M1": "Forme recente et performances",
    "M2": "Aptitude distance et discipline",
    "M3": "Engagement et gains",
    "M4": "Entourage et potentiel",
    "M5": "Regularite et fiabilite",
}

# Champs de scores eventuellement disponibles.
# Ils ne sont jamais crees artificiellement.
CRITERES = {
    "M1": [
        ("score_forme", 3),
        ("score_performances", 2),
        ("taux_victoire", 1),
    ],
    "M2": [
        ("score_aptitude", 3),
        ("score_distance", 2),
        ("score_terrain", 2),
    ],
    "M3": [
        ("score_engagement", 3),
        ("score_competition", 2),
        ("score_classe", 2),
    ],
    "M4": [
        ("score_jockey", 2),
        ("score_entraineur", 2),
        ("score_entourage", 2),
    ],
    "M5": [
        ("score_regularite", 3),
        ("score_fiabilite", 2),
        ("score_forme", 1),
    ],
}


def lire_json(chemin):
    """Lecture JSON avec detection des cles dupliquees."""

    def verifier(paires):
        resultat = {}

        for cle, valeur in paires:
            if cle in resultat:
                raise ValueError(
                    "Cle JSON dupliquee : " + cle
                )
            resultat[cle] = valeur

        return resultat

    with open(chemin, encoding="utf-8") as fichier:
        return json.load(
            fichier,
            object_pairs_hook=verifier
        )


def ecrire_json(chemin, donnees):
    """Ecriture atomique du fichier de sortie."""

    chemin = Path(chemin)
    chemin.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    temporaire = chemin.with_name(
        chemin.name + ".tmp"
    )

    try:
        with temporaire.open(
            "w",
            encoding="utf-8"
        ) as fichier:
            json.dump(
                donnees,
                fichier,
                ensure_ascii=False,
                indent=2,
                allow_nan=False
            )
            fichier.write("\n")

        os.replace(temporaire, chemin)

    finally:
        if temporaire.exists():
            temporaire.unlink()


def nombre(valeur):
    """Conversion numerique sans valeur inventee."""

    if isinstance(valeur, bool) or valeur is None:
        return None

    try:
        texte = str(valeur).replace(
            " ", ""
        ).replace(",", ".")

        resultat = float(texte)

        if math.isfinite(resultat):
            return resultat

    except (ValueError, TypeError):
        pass

    return None


def entier_positif(valeur):
    """Numero PMU strictement positif."""

    if isinstance(valeur, bool):
        return None

    try:
        n = int(valeur)

        if n > 0 and str(valeur).strip() == str(n):
            return n

    except (ValueError, TypeError):
        pass

    return None


def depart_paris(valeur):
    """Convertit un depart ISO ou timestamp en heure Paris."""

    try:
        if isinstance(valeur, str) and (
            "T" in valeur or "-" in valeur
        ):
            date = datetime.fromisoformat(
                valeur.replace("Z", "+00:00")
            )

            if date.tzinfo is None:
                return None

            return date.astimezone(PARIS)

        timestamp = nombre(valeur)

        if timestamp is None or timestamp <= 0:
            return None

        if timestamp > 1e12:
            timestamp /= 1000

        return datetime.fromtimestamp(
            timestamp,
            timezone.utc
        ).astimezone(PARIS)

    except (
        ValueError,
        TypeError,
        OverflowError,
        OSError
    ):
        return None


def musique(cheval, discipline=None):
    """
    Extrait des places lisibles dans la musique PMU.

    Exemples :
        1a 3a 2a
        4p 2p 1p
        3m 1m 5m

    Les classements 0, les disqualifications,
    les arrets et les incidents ne sont pas
    transformes en bonnes performances.

    Les historiques incomplets sont signales.
    """

    brute = cheval.get("musique")

    if not isinstance(brute, str):
        return []

    texte = brute.lower().strip()

    # Un classement de 10e ou plus n'est pas
    # interprete comme 1er ou 2e.
    motif = r"(?<![0-9a-z])([1-9]|1[0-9]|20)([apmho])"

    resultats = []

    for correspondance in re.finditer(
        motif,
        texte
    ):
        place = int(correspondance.group(1))
        code = correspondance.group(2)

        resultats.append({
            "place": place,
            "discipline": code
        })

    return resultats


def gains_carriere(cheval):
    """Gains publies, sans estimation."""

    valeur = nombre(
        cheval.get("gains_carriere")
    )

    if valeur is None or valeur < 0:
        return None

    return valeur


def score_documente(cheval, moteur):
    """
    Accepte des scores deja fournis uniquement
    avec une provenance explicite.

    Aucune transformation automatique des noms
    de jockeys ou des conditions de course en score.
    """

    provenance = cheval.get(
        "source_indicateurs"
    )

    if not isinstance(provenance, str):
        return None

    if not provenance.strip():
        return None

    valeurs = []

    for champ, poids in CRITERES[moteur]:
        valeur = nombre(
            cheval.get(champ)
        )

        if valeur is not None and 0 <= valeur <= 100:
            valeurs.append(
                (valeur, poids)
            )

    if len(valeurs) < 2:
        return None

    total_poids = sum(
        poids for _, poids in valeurs
    )

    score = sum(
        valeur * poids
        for valeur, poids in valeurs
    ) / total_poids

    return (
        score,
        "Scores fournis : " + provenance.strip()
    )


def calculer_indicateur(cheval, moteur):
    """
    Retourne (valeur, explication).

    Ne compare pas des scores de provenance
    differente au sein d'une meme course.
    """

    # M1 : trois dernieres places exploitables.
    if moteur == "M1":
        places = musique(cheval)

        if len(places) >= 3:
            trois = [
                x["place"] for x in places[:3]
            ]

            # Plus la moyenne est faible,
            # meilleur est l'indicateur descriptif.
            return (
                -sum(trois) / 3,
                "Moyenne des 3 premieres places lisibles"
            )

    # M5 : cinq places exploitables.
    if moteur == "M5":
        places = musique(cheval)

        if len(places) >= 5:
            cinq = [
                x["place"] for x in places[:5]
            ]

            return (
                -sum(cinq) / 5,
                "Moyenne des 5 premieres places lisibles"
            )

    # M3 : gains de carriere connus.
    if moteur == "M3":
        gains = gains_carriere(cheval)

        if gains is not None:
            return (
                gains,
                "Gains de carriere publies"
            )

    # M2 et M4 ne peuvent pas etre calcules
    # a partir d'une simple distance ou d'un nom.
    return None


def base_moteur(moteur):
    return {
        "moteur": moteur,
        "specialite": MOTEURS[moteur],
        "qualification": "🟡 DONNEES INSUFFISANTES",
        "validation": False,
        "gagnant_espere": None,
        "meilleur_place": None,
        "ordre_arrivee_espere": [],
        "pari_retenu": None,
        "fige": False,
        "heure_fige": None,
        "raison": "",
        "indicateurs": [],
    }


def analyser_moteur(partants, moteur, anomalies):
    resultat = base_moteur(moteur)

    if anomalies:
        resultat["qualification"] = "🔴 EXCLU"
        resultat["raison"] = "; ".join(anomalies)
        return resultat

    notes = []
    methodes = set()

    for cheval in partants:
        indicateur = calculer_indicateur(
            cheval,
            moteur
        )

        if indicateur is None:
            indicateur = score_documente(
                cheval,
                moteur
            )

        if indicateur is None:
            resultat["raison"] = (
                "Indicateurs sportifs insuffisants "
                "pour comparer tous les partants"
            )
            return resultat

        valeur, origine = indicateur

        notes.append({
            "numero": cheval["numero"],
            "valeur": valeur,
            "origine": origine,
        })

        methodes.add(origine)

    # Ne jamais comparer des gains avec des scores,
    # ou des musiques avec des indicateurs differents.
    if len(methodes) != 1:
        resultat["raison"] = (
            "Methodes ou provenances non comparables "
            "entre les partants"
        )
        return resultat

    notes.sort(
        key=lambda item: (
            -item["valeur"],
            item["numero"]
        )
    )

    if len(notes) < 2:
        resultat["raison"] = (
            "Moins de deux chevaux evaluables"
        )
        return resultat

    if math.isclose(
        notes[0]["valeur"],
        notes[1]["valeur"],
        rel_tol=0,
        abs_tol=1e-9
    ):
        resultat["raison"] = (
            "Egalite entre les deux premiers"
        )
        return resultat

    ordre = [
        item["numero"]
        for item in notes[:5]
    ]

    resultat.update({
        "qualification": "🟢 RETENU",
        "validation": True,
        "gagnant_espere": ordre[0],
        "meilleur_place": ordre[1],
        "ordre_arrivee_espere": ordre,
        "pari_retenu": None,
        "fige": False,
        "heure_fige": None,
        "indicateurs": [
            {
                "numero": item["numero"],
                "valeur": round(
                    item["valeur"], 3
                ),
                "origine": item["origine"],
            }
            for item in notes
        ],
        "raison": (
            "Classement indicatif fonde sur "
            + notes[0]["origine"]
            + "; non valide statistiquement; "
            "aucun pari ni FIGE"
        ),
    })

    return resultat


def analyser_course(course, date_programme, maintenant):
    anomalies = []

    identifiant = str(
        course.get("id") or ""
    ).strip()

    if not identifiant:
        anomalies.append(
            "Identifiant manquant"
        )

    depart = depart_paris(
        course.get("heure_depart_timestamp")
    )

    if depart is None:
        anomalies.append(
            "Depart non renseigne"
        )

    elif depart.date().isoformat() != date_programme:
        anomalies.append(
            "Date de depart incoherente"
        )

    elif depart <= maintenant:
        anomalies.append(
            "Depart passe : aucun pronostic retroactif"
        )

    statuts_exclus = {
        "ANNULEE",
        "ANNULE",
        "ABANDONNEE",
        "REPORTEE",
    }

    statut = str(
        course.get("statut", "")
    ).upper()

    if statut in statuts_exclus:
        anomalies.append(
            "Course annulee ou reportee"
        )

    if course.get("participants_verifies") is not True:
        anomalies.append(
            "Participants non verifies"
        )

    participants = course.get("participants")

    if not isinstance(participants, list):
        anomalies.append(
            "Liste des participants invalide"
        )
        participants = []

    if not participants:
        anomalies.append(
            "Participants absents"
        )

    partants = []
    numeros = set()

    for cheval in participants:
        if not isinstance(cheval, dict):
            anomalies.append(
                "Participant mal forme"
            )
            continue

        numero = entier_positif(
            cheval.get("numero")
        )

        if numero is None or numero in numeros:
            anomalies.append(
                "Numero invalide ou duplique"
            )
            continue

        numeros.add(numero)

        if cheval.get("non_partant") is True:
            continue

        partants.append(
            dict(
                cheval,
                numero=numero
            )
        )

    annonce = entier_positif(
        course.get("nombre_partants")
    )

    if annonce is not None:
        if annonce != len(partants):
            anomalies.append(
                "Nombre de partants incoherent"
            )

    if len(partants) < 2:
        anomalies.append(
            "Moins de deux partants"
        )

    anomalies = list(
        dict.fromkeys(anomalies)
    )

    moteurs = [
        analyser_moteur(
            partants,
            moteur,
            anomalies
        )
        for moteur in MOTEURS
    ]

    return {
        "id": identifiant,
        "reunion": course.get("reunion"),
        "course": course.get("course"),
        "hippodrome": course.get("hippodrome"),
        "nom": course.get("nom"),
        "discipline": course.get("discipline"),
        "distance": course.get("distance"),
        "depart_paris": (
            depart.isoformat()
            if depart else None
        ),
        "partants_annonces": annonce,
        "partants_verifies": len(partants),
        "controle": (
            "EXCLU" if anomalies
            else "PROGRAMME_VERIFIE"
        ),
        "anomalies": anomalies,
        "moteurs": moteurs,
    }


def main():
    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--input",
        default=str(SOURCE)
    )

    parser.add_argument(
        "--output",
        default=str(SORTIE)
    )

    args = parser.parse_args()

    maintenant = datetime.now(PARIS)

    try:
        donnees = lire_json(args.input)

        if not isinstance(donnees, dict):
            raise ValueError(
                "Programme JSON invalide"
            )

        date_programme = donnees.get("date")

        if date_programme != maintenant.date().isoformat():
            raise ValueError(
                "Programme hors date de Paris"
            )

        courses = donnees.get("courses")

        if not isinstance(courses, list) or not courses:
            raise ValueError(
                "Liste de courses absente"
            )

        identifiants = [
            course.get("id")
            for course in courses
            if isinstance(course, dict)
        ]

        if len(identifiants) != len(courses):
            raise ValueError(
                "Course mal formee"
            )

        if (
            any(not identifiant for identifiant in identifiants)
            or len(set(identifiants)) != len(identifiants)
        ):
            raise ValueError(
                "Identifiants invalides ou dupliques"
            )

        analyses = [
            analyser_course(
                course,
                date_programme,
                maintenant
            )
            for course in courses
        ]

        analyses.sort(
            key=lambda course: (
                course["depart_paris"] is None,
                course["depart_paris"] or "",
                course["id"]
            )
        )

        total = sum(
            int(moteur["validation"])
            for course in analyses
            for moteur in course["moteurs"]
        )

        resultat = {
            "logiciel": "MPAA X1000 FUSION",
            "schema_version": 2,
            "date": date_programme,
            "analyse_effectuee_paris": (
                maintenant.isoformat()
            ),
            "source_programme": donnees.get("source"),
            "statut": (
                "PRONOSTICS_CALCULES"
                if total > 0
                else "ANALYSE_SANS_PRONOSTIC"
            ),
            "explication": (
                "Classements indicatifs bases sur "
                "les donnees disponibles; "
                "aucun pari et aucun FIGE archive"
            ),
            "nombre_courses": len(analyses),
            "nombre_pronostics": total,
            "nombre_figes": 0,
            "courses": analyses,
        }

        ecrire_json(
            args.output,
            resultat
        )

        print(
            "MPAA X1000 FUSION :",
            len(analyses),
            "courses ;",
            total,
            "classements ;",
            "0 FIGE"
        )

        return 0

    except (
        OSError,
        ValueError,
        TypeError,
        KeyError
    ) as erreur:
        print(
            "ERREUR MPAA X1000 :",
            erreur,
            file=sys.stderr
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
