#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""MPAA X1000 FUSION — analyse M1 à M5.

Entrée : data/programme_pmu.json
Sortie : data/analyses_moteurs.json

Aucun indicateur sportif inventé.
Aucun FIGÉ rétroactif.
"""

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")

MOTEURS = {
    "M1": ("Forme et performances", [
        ("score_forme", 3),
        ("score_performances", 2),
        ("taux_victoire", 1),
    ]),
    "M2": ("Aptitude et conditions", [
        ("score_aptitude", 3),
        ("score_distance", 2),
        ("score_terrain", 2),
    ]),
    "M3": ("Engagement et compétition", [
        ("score_engagement", 3),
        ("score_competition", 2),
        ("score_classe", 2),
    ]),
    "M4": ("Entourage et potentiel", [
        ("score_jockey", 2),
        ("score_entraineur", 2),
        ("score_entourage", 2),
    ]),
    "M5": ("Régularité et risques", [
        ("score_regularite", 3),
        ("score_fiabilite", 2),
        ("score_forme", 1),
    ]),
}


def lire(chemin):
    def verifier(paires):
        resultat = {}
        for cle, valeur in paires:
            if cle in resultat:
                raise ValueError(
                    "Clé JSON dupliquée : " + cle
                )
            resultat[cle] = valeur
        return resultat

    with open(chemin, encoding="utf-8") as f:
        return json.load(
            f, object_pairs_hook=verifier
        )


def ecrire(chemin, donnees):
    chemin = Path(chemin)
    chemin.parent.mkdir(
        parents=True, exist_ok=True
    )
    temporaire = chemin.with_name(
        chemin.name + ".tmp"
    )
    try:
        with temporaire.open(
            "w", encoding="utf-8"
        ) as f:
            json.dump(
                donnees, f,
                ensure_ascii=False,
                indent=2,
                allow_nan=False
            )
            f.write("\n")
        os.replace(temporaire, chemin)
    finally:
        if temporaire.exists():
            temporaire.unlink()


def depart_paris(valeur):
    if isinstance(valeur, bool) or valeur is None:
        return None
    try:
        if isinstance(valeur, str) and (
            "T" in valeur or "-" in valeur
        ):
            d = datetime.fromisoformat(
                valeur.replace("Z", "+00:00")
            )
            if d.tzinfo is None:
                return None
            return d.astimezone(PARIS)

        n = float(valeur)
        if not math.isfinite(n) or n <= 0:
            return None

        if n > 1e12:
            n /= 1000

        return datetime.fromtimestamp(
            n, timezone.utc
        ).astimezone(PARIS)

    except (
        ValueError, TypeError,
        OverflowError, OSError
    ):
        return None


def numero_positif(valeur):
    if isinstance(valeur, bool):
        return None
    try:
        n = int(valeur)
        if n > 0 and str(valeur).strip() == str(n):
            return n
    except (ValueError, TypeError):
        pass
    return None


def indicateur(cheval, champ):
    valeur = cheval.get(champ)

    if isinstance(valeur, bool) or valeur is None:
        return None

    try:
        n = float(valeur)
        if math.isfinite(n) and 0 <= n <= 100:
            return n
    except (ValueError, TypeError):
        pass

    return None


def analyser_moteur(chevaux, moteur, problemes):
    specialite, criteres = MOTEURS[moteur]

    resultat = {
        "moteur": moteur,
        "specialite": specialite,
        "qualification": (
            "🔴 EXCLU" if problemes
            else "🟡 DONNEES INSUFFISANTES"
        ),
        "validation": False,
        "gagnant_espere": None,
        "meilleur_place": None,
        "ordre_arrivee_espere": [],
        "pari_retenu": None,
        "fige": False,
        "heure_fige": None,
        "raison": (
            "; ".join(problemes)
            if problemes else ""
        ),
    }

    if problemes:
        return resultat

    notes = []

    for cheval in chevaux:
        valeurs = [
            (indicateur(cheval, champ), poids)
            for champ, poids in criteres
        ]

        disponibles = [
            (val, poids)
            for val, poids in valeurs
            if val is not None
        ]

        if len(disponibles) < 2:
            resultat["raison"] = (
                "Moins de deux indicateurs sportifs "
                "pour au moins un partant"
            )
            return resultat

        score = sum(
            val * poids
            for val, poids in disponibles
        ) / sum(
            poids for _, poids in disponibles
        )

        notes.append(
            (cheval["numero"], score)
        )

    notes.sort(
        key=lambda item: (-item[1], item[0])
    )

    if len(notes) < 2:
        resultat["raison"] = (
            "Moins de deux chevaux évaluables"
        )
        return resultat

    if abs(notes[0][1] - notes[1][1]) < 1e-9:
        resultat["raison"] = (
            "Égalité des meilleurs scores"
        )
        return resultat

    ordre = [
        numero for numero, _ in notes[:5]
    ]

    resultat.update({
        "qualification": "🟢 RETENU",
        "validation": True,
        "gagnant_espere": ordre[0],
        "meilleur_place": ordre[1],
        "ordre_arrivee_espere": ordre,
        "pari_retenu": (
            "Simple Gagnant "
            "(proposition non placée)"
        ),
        "scores": [
            {
                "numero": numero,
                "score": round(score, 3)
            }
            for numero, score in notes
        ],
        "raison": (
            "Classement heuristique ; "
            "non validé statistiquement"
        ),
    })

    return resultat


def analyser_course(course, maintenant, date_programme):
    identifiant = str(
        course.get("id") or ""
    ).strip()

    depart = depart_paris(
        course.get("heure_depart_timestamp")
    )

    participants = course.get("participants")
    problemes = []

    if not identifiant:
        problemes.append("Identifiant manquant")

    if not isinstance(participants, list):
        problemes.append(
            "Liste des participants invalide"
        )
        participants = []

    if course.get("participants_verifies") is not True:
        problemes.append(
            "Participants non vérifiés"
        )

    if depart is None:
        problemes.append(
            "Départ non renseigné"
        )
    elif depart.date().isoformat() != date_programme:
        problemes.append(
            "Date de départ incohérente"
        )
    elif depart <= maintenant:
        problemes.append(
            "Départ passé : aucun pronostic rétroactif"
        )

    statuts_exclus = {
        "ANNULEE", "ANNULE",
        "ABANDONNEE", "REPORTEE"
    }

    if str(
        course.get("statut", "")
    ).upper() in statuts_exclus:
        problemes.append(
            "Course annulée ou reportée"
        )

    chevaux = []
    numeros = set()

    for p in participants:
        if not isinstance(p, dict):
            problemes.append(
                "Participant mal formé"
            )
            continue

        numero = numero_positif(
            p.get("numero")
        )

        if numero is None or numero in numeros:
            problemes.append(
                "Numéro invalide ou dupliqué"
            )
            continue

        numeros.add(numero)

        if p.get("non_partant") is True:
            continue

        chevaux.append(
            dict(p, numero=numero)
        )

    annonce = numero_positif(
        course.get("nombre_partants")
    )

    if annonce is not None and annonce != len(chevaux):
        problemes.append(
            "Nombre de partants incohérent"
        )

    if len(chevaux) < 2:
        problemes.append(
            "Moins de deux partants"
        )

    problemes = list(
        dict.fromkeys(problemes)
    )

    moteurs = [
        analyser_moteur(
            chevaux, moteur, problemes
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
        "partants_verifies": len(chevaux),
        "controle": (
            "EXCLU" if problemes
            else "PROGRAMME_VERIFIE"
        ),
        "anomalies": problemes,
        "moteurs": moteurs,
    }


def main():
    parser = argparse.ArgumentParser(
        description=__doc__
    )
    parser.add_argument(
        "--input",
        default="data/programme_pmu.json"
    )
    parser.add_argument(
        "--output",
        default="data/analyses_moteurs.json"
    )
    args = parser.parse_args()

    maintenant = datetime.now(PARIS)

    try:
        donnees = lire(args.input)

        if (
            not isinstance(donnees, dict)
            or not isinstance(
                donnees.get("courses"), list
            )
            or not donnees["courses"]
        ):
            raise ValueError(
                "Programme vide ou invalide"
            )

        date = donnees.get("date")

        if date != maintenant.date().isoformat():
            raise ValueError(
                "Programme hors date de Paris"
            )

        identifiants = [
            c.get("id")
            for c in donnees["courses"]
            if isinstance(c, dict)
        ]

        if (
            len(identifiants) != len(donnees["courses"])
            or any(not x for x in identifiants)
            or len(set(identifiants)) != len(identifiants)
        ):
            raise ValueError(
                "Identifiants invalides ou dupliqués"
            )

        analyses = [
            analyser_course(
                course, maintenant, date
            )
            for course in donnees["courses"]
        ]

        analyses.sort(
            key=lambda c: (
                c["depart_paris"] is None,
                c["depart_paris"] or "",
                c["id"]
            )
        )

        nombre = sum(
            m["validation"]
            for course in analyses
            for m in course["moteurs"]
        )

        resultat = {
            "logiciel": "MPAA X1000 FUSION",
            "schema_version": 2,
            "date": date,
            "analyse_effectuee_paris": (
                maintenant.isoformat()
            ),
            "source_programme": donnees.get("source"),
            "statut": (
                "PRONOSTICS_CALCULES"
                if nombre
                else "ANALYSE_SANS_PRONOSTIC"
            ),
            "explication": (
                "Classements heuristiques disponibles ; "
                "aucun FIGÉ archivé."
                if nombre else
                "Indicateurs sportifs insuffisants ; "
                "aucun pronostic inventé."
            ),
            "nombre_courses": len(analyses),
            "nombre_pronostics": nombre,
            "nombre_figes": 0,
            "courses": analyses,
        }

        ecrire(args.output, resultat)

        print(
            "MPAA X1000 :",
            len(analyses),
            "courses ;",
            nombre,
            "sélections moteur ; 0 FIGÉ archivé"
        )

        return 0

    except (
        OSError, ValueError,
        TypeError, KeyError
    ) as erreur:
        print(
            "ERREUR MPAA X1000 :",
            erreur,
            file=sys.stderr
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
    
