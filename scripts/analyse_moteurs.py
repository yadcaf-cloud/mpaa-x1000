#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MPAA X1000 FUSION — analyse prudente M1 à M5.

Entrée : data/programme_pmu.json (créé par scripts/collecte_pmu.py)
Sortie : data/analyses_moteurs.json

Aucun résultat sportif ni cote ne sont inventés. Les cinq moteurs sont des
heuristiques explicites, pas des modèles prédictifs validés.
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
MOTEURS = ("M1", "M2", "M3", "M4", "M5")


def charger_json(chemin):
    def sans_doublons(paires):
        objet = {}
        for cle, valeur in paires:
            if cle in objet:
                raise ValueError(f"Clé JSON dupliquée : {cle}")
            objet[cle] = valeur
        return objet

    with chemin.open("r", encoding="utf-8") as fichier:
        return json.load(fichier, object_pairs_hook=sans_doublons)


def sauvegarder(chemin, donnees):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    temporaire = chemin.with_name(chemin.name + ".tmp")
    with temporaire.open("w", encoding="utf-8") as fichier:
        json.dump(donnees, fichier, ensure_ascii=False, indent=2, allow_nan=False)
        fichier.write("\n")
    os.replace(temporaire, chemin)


def entier_positif(valeur):
    if isinstance(valeur, bool):
        return None
    try:
        nombre = int(valeur)
        return nombre if nombre > 0 and str(valeur).strip() == str(nombre) else None
    except (ValueError, TypeError):
        return None


def date_depart(valeur):
    if isinstance(valeur, bool) or valeur is None:
        return None
    try:
        nombre = float(valeur)
        if nombre > 10**12:
            nombre /= 1000
        if nombre <= 0:
            return None
        return datetime.fromtimestamp(nombre, timezone.utc).astimezone(PARIS)
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def texte(valeur):
    return str(valeur or "").strip()


def analyser_course(course, maintenant, date_programme):
    identifiant = texte(course.get("id"))
    depart = date_depart(course.get("heure_depart_timestamp"))
    participants = course.get("participants", [])
    raisons = []
    if not identifiant or not isinstance(participants, list):
        raisons.append("Identifiant ou liste de participants invalide")
        participants = []
    if course.get("participants_verifies") is not True:
        raisons.append("Participants non vérifiés")
    if depart is None:
        raisons.append("Heure de départ absente ou invalide")
    elif depart.date().isoformat() != date_programme:
        raisons.append("Date de départ incohérente avec le programme")
    elif depart <= maintenant:
        raisons.append("Départ déjà passé")
    if texte(course.get("statut")).upper() in {"ANNULEE", "ANNULE", "ABANDONNEE", "REPORTEE"}:
        raisons.append("Course annulée ou reportée")

    chevaux = []
    numeros = set()
    for participant in participants:
        if not isinstance(participant, dict):
            raisons.append("Participant mal formé")
            continue
        numero = entier_positif(participant.get("numero"))
        if numero is None or numero in numeros:
            raisons.append("Numéro de cheval invalide ou dupliqué")
            continue
        numeros.add(numero)
        if participant.get("non_partant") is True:
            continue
        chevaux.append({
            "numero": numero,
            "nom": texte(participant.get("nom")),
            "jockey": texte(participant.get("jockey")),
            "entraineur": texte(participant.get("entraineur")),
            "age": entier_positif(participant.get("age")),
        })

    annonce = course.get("nombre_partants")
    annonce = entier_positif(annonce) if annonce is not None else None
    if annonce is not None and annonce != len(chevaux):
        raisons.append("Nombre de partants incohérent avec la liste vérifiée")
    if len(chevaux) < 2:
        raisons.append("Moins de deux partants vérifiés")

    # Les champs du collecteur ne contiennent ni forme récente, ni performances,
    # ni cotes, ni historique de terrain. Ils ne permettent pas de départager
    # sportivement les chevaux. Aucun classement arbitraire n'est publié.
    specialites = {
        "M1": "Forme récente et performances",
        "M2": "Aptitude distance, piste et terrain",
        "M3": "Engagement et niveau de compétition",
        "M4": "Jockey, entraîneur et entourage",
        "M5": "Régularité et risques",
    }
    moteurs = []
    for moteur in MOTEURS:
        moteurs.append({
            "moteur": moteur,
            "specialite": specialites[moteur],
            "qualification": "🟡 DONNEES INSUFFISANTES" if not raisons else "🔴 EXCLU",
            "validation": False,
            "gagnant_espere": None,
            "meilleur_place": None,
            "ordre_arrivee_espere": [],
            "pari_retenu": None,
            "fige": False,
            "raison": "; ".join(dict.fromkeys(raisons)) if raisons else
                "Historique sportif et critères spécialisés non fournis par la collecte",
        })
    return {
        "id": identifiant,
        "reunion": course.get("reunion"),
        "course": course.get("course"),
        "hippodrome": texte(course.get("hippodrome")),
        "nom": texte(course.get("nom")),
        "discipline": texte(course.get("discipline")),
        "distance": course.get("distance"),
        "depart_paris": depart.isoformat() if depart else None,
        "partants_annonces": annonce,
        "partants_verifies": len(chevaux),
        "chevaux": chevaux,
        "controle": "INCOMPLET" if raisons else "PROGRAMME_VERIFIE",
        "anomalies": list(dict.fromkeys(raisons)),
        "moteurs": moteurs,
    }


def main():
    parseur = argparse.ArgumentParser(description=__doc__)
    parseur.add_argument("--input", default="data/programme_pmu.json")
    parseur.add_argument("--output", default="data/analyses_moteurs.json")
    args = parseur.parse_args()
    entree, sortie = Path(args.input), Path(args.output)
    maintenant = datetime.now(PARIS)
    try:
        donnees = charger_json(entree)
        if not isinstance(donnees, dict) or not isinstance(donnees.get("courses"), list):
            raise ValueError("Champ courses absent ou invalide")
        date_programme = donnees.get("date")
        if not isinstance(date_programme, str) or len(date_programme) != 10:
            raise ValueError("Date de programme absente ou invalide")
        datetime.strptime(date_programme, "%Y-%m-%d")
        if date_programme != maintenant.date().isoformat():
            raise ValueError("Programme périmé : la date n'est pas celle de Paris")
        if not donnees["courses"]:
            raise ValueError("Aucune course dans le programme")
        identifiants = [texte(c.get("id")) for c in donnees["courses"] if isinstance(c, dict)]
        if len(identifiants) != len(donnees["courses"]) or len(set(identifiants)) != len(identifiants):
            raise ValueError("Courses mal formées ou identifiants dupliqués")
        analyses = [analyser_course(c, maintenant, date_programme) for c in donnees["courses"]]
        analyses.sort(key=lambda c: (c["depart_paris"] is None, c["depart_paris"] or "", c["id"]))
        resultat = {
            "logiciel": "MPAA X1000 FUSION",
            "schema_version": 1,
            "date": date_programme,
            "analyse_effectuee_paris": maintenant.isoformat(),
            "source_programme": donnees.get("source"),
            "statut": "ANALYSE_SANS_PRONOSTIC",
            "explication": "Collecte vérifiée mais données sportives insuffisantes pour des pronostics fiables. Aucun FIGÉ inventé.",
            "nombre_courses": len(analyses),
            "nombre_figes": 0,
            "courses": analyses,
        }
        sauvegarder(sortie, resultat)
        print(f"OK : {len(analyses)} courses examinées ; 0 FIGÉ artificiel ; fichier {sortie}")
        return 0
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERREUR ANALYSE : {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
