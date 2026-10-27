#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MPAA X1000 FUSION — analyse traçable et indépendante M1 à M5.

Entrée : data/programme_pmu.json
Sortie : data/analyses_moteurs.json
Ce script ne crée aucun FIGÉ et ne place aucun pari.
Le verrouillage est exclusivement assuré par figes_secure.py.
Les scores sont heuristiques et ne constituent pas des probabilités calibrées.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import sys
from zoneinfo import ZoneInfo

PARIS = ZoneInfo('Europe/Paris')
MOTEURS = {
    'M1': ('Forme et performances', {'score_forme': 3, 'score_performances': 3, 'taux_victoire': 1}),
    'M2': ('Aptitude et conditions', {'score_aptitude': 3, 'score_distance': 2, 'score_terrain': 2}),
    'M3': ('Engagement et opposition', {'score_engagement': 3, 'score_competition': 2, 'score_classe': 2}),
    'M4': ('Entourage et potentiel', {'score_jockey': 2, 'score_entraineur': 2, 'score_entourage': 2}),
    'M5': ('Régularité et risques', {'score_regularite': 3, 'score_fiabilite': 2, 'score_forme': 1}),
}
EXCLUS = {'ANNULEE', 'ANNULE', 'ABANDONNEE', 'REPORTEE', 'ANNULEE DEFINITIVEMENT'}
MIN_PARTANTS = 3
MIN_COUVERTURE = 0.65
MIN_ECART = 1.0
MIN_AVANCE_SECONDES = 120
MAX_AGE_MINUTES = 180


def lire(path):
    def uniques(paires):
        resultat = {}
        for cle, valeur in paires:
            if cle in resultat:
                raise ValueError(f'Clé JSON dupliquée : {cle}')
            resultat[cle] = valeur
        return resultat
    with open(path, encoding='utf-8') as fichier:
        return json.load(fichier, object_pairs_hook=uniques)


def ecrire(path, contenu):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporaire = path.with_name(path.name + '.tmp')
    try:
        with temporaire.open('w', encoding='utf-8') as fichier:
            json.dump(contenu, fichier, ensure_ascii=False, indent=2, allow_nan=False)
            fichier.write('\n')
        os.replace(temporaire, path)
    finally:
        if temporaire.exists():
            temporaire.unlink()


def depart_paris(valeur):
    if valeur is None or isinstance(valeur, bool):
        return None
    try:
        if isinstance(valeur, str) and ('T' in valeur or '-' in valeur):
            date = datetime.fromisoformat(valeur.replace('Z', '+00:00'))
            return date.astimezone(PARIS) if date.tzinfo else None
        nombre = float(valeur)
        if not math.isfinite(nombre) or nombre <= 0:
            return None
        return datetime.fromtimestamp(
            nombre / 1000 if nombre > 1e12 else nombre, timezone.utc
        ).astimezone(PARIS)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def numero(valeur):
    if isinstance(valeur, bool):
        return None
    try:
        n = int(valeur)
        return n if n > 0 and str(valeur).strip() == str(n) else None
    except (TypeError, ValueError, OverflowError):
        return None


def indicateur(cheval, champ):
    valeur = cheval.get(champ)
    if valeur is None or isinstance(valeur, bool):
        return None
    try:
        n = float(valeur)
        return n if math.isfinite(n) and 0 <= n <= 100 else None
    except (TypeError, ValueError, OverflowError):
        return None


def base_moteur(moteur):
    return {
        'moteur': moteur, 'specialite': MOTEURS[moteur][0],
        'qualification': '🟡 EN ÉTUDE', 'validation': False,
        'gagnant_espere': None, 'meilleur_place': None,
        'ordre_arrivee_espere': [], 'pari_retenu': None,
        'fige': False, 'heure_fige': None, 'phase': 'PREPARATION',
        'confiance_donnees': 0, 'scores': [], 'raison': '',
        'indicateurs_manquants': [], 'robustesse': None,
        'ecart_tete': None, 'alertes': [], 'scenarios': [],
    }


def analyser_moteur(chevaux, moteur, anomalies, delai):
    resultat = base_moteur(moteur)
    if anomalies:
        resultat.update(qualification='🔴 EXCLU', raison='; '.join(anomalies))
        return resultat

    criteres = MOTEURS[moteur][1]
    notes, absents = [], Counter()
    for cheval in chevaux:
        preuves = []
        for champ, poids in criteres.items():
            valeur = indicateur(cheval, champ)
            if valeur is None:
                absents[champ] += 1
            else:
                preuves.append({'indicateur': champ, 'valeur': valeur, 'poids': poids})
        if not preuves:
            continue
        total = sum(p['poids'] for p in preuves)
        couverture = total / sum(criteres.values())
        score = sum(p['valeur'] * p['poids'] for p in preuves) / total
        basse = score * couverture
        notes.append({
            'numero': cheval['numero'], 'score': score,
            'couverture': couverture, 'borne_basse': basse,
            'borne_haute': basse + 100 * (1 - couverture), 'preuves': preuves,
        })

    resultat['indicateurs_manquants'] = [
        {'champ': champ, 'chevaux': nombre} for champ, nombre in sorted(absents.items())
    ]
    if not notes:
        resultat['raison'] = 'Aucun indicateur sportif chiffré disponible'
        return resultat

    resultat['confiance_donnees'] = round(
        100 * sum(n['couverture'] for n in notes) / len(chevaux), 1
    )
    notes.sort(key=lambda n: (-n['score'], n['numero']))
    resultat['scores'] = [{
        'numero': n['numero'], 'score': round(n['score'], 3),
        'couverture': round(n['couverture'], 3),
        'intervalle_donnees': [round(n['borne_basse'], 2), round(n['borne_haute'], 2)],
        'preuves': n['preuves'],
    } for n in notes]

    if len(notes) != len(chevaux) or min(n['couverture'] for n in notes) < MIN_COUVERTURE:
        resultat['raison'] = (
            f'Couverture sportive insuffisante : {len(notes)}/{len(chevaux)} chevaux évaluables'
        )
        return resultat
    if len(notes) < MIN_PARTANTS:
        resultat['raison'] = 'Trop peu de chevaux évaluables'
        return resultat

    ecart = notes[0]['score'] - notes[1]['score']
    resultat['ecart_tete'] = round(ecart, 3)
    gagnant = notes[0]['numero']
    scenarios = []
    for champ in criteres:
        classement = []
        for n in notes:
            preuves = [p for p in n['preuves'] if p['indicateur'] != champ]
            total = sum(p['poids'] for p in preuves)
            if not total:
                classement = []
                break
            score = sum(p['valeur'] * p['poids'] for p in preuves) / total
            classement.append((score, n['numero']))
        if classement:
            classement.sort(key=lambda x: (-x[0], x[1]))
            scenarios.append({
                'sans': champ, 'premier': classement[0][1],
                'stable': classement[0][1] == gagnant,
            })
    resultat['scenarios'] = scenarios
    resultat['robustesse'] = (
        round(100 * sum(s['stable'] for s in scenarios) / len(scenarios), 1)
        if scenarios else None
    )
    if scenarios and not all(s['stable'] for s in scenarios):
        resultat['alertes'].append('Favori sensible au retrait d’un indicateur')
    if any(n['couverture'] < 1 for n in notes):
        resultat['alertes'].append('Indicateurs partiellement manquants')
    if any(notes[0]['borne_basse'] <= n['borne_haute'] for n in notes[1:]):
        resultat['alertes'].append('Leadership incertain avec les données manquantes')

    if ecart < MIN_ECART:
        resultat['raison'] = f'Tête indécise : écart {ecart:.2f}/100'
        return resultat
    if delai <= MIN_AVANCE_SECONDES:
        resultat['raison'] = 'Délai insuffisant pour un FIGÉ avant départ'
        return resultat

    ordre = [n['numero'] for n in notes[:5]]
    resultat.update({
        'qualification': '🟢 RETENU', 'validation': True,
        'gagnant_espere': ordre[0], 'meilleur_place': ordre[1],
        'ordre_arrivee_espere': ordre, 'phase': 'PRE_VERROU',
        'raison': (
            f'Classement heuristique traçable, écart {ecart:.2f}/100 ; '
            'FIGÉ à créer par figes_secure.py'
        ),
    })
    return resultat


def choisir_pari(moteur, offres):
    """Proposer uniquement un type de pari explicitement collecté."""
    if not isinstance(offres, list):
        moteur['alertes'].append('Offres PMU non renseignées')
        return
    options = {o.strip().casefold() for o in offres if isinstance(o, str)}
    if 'simple gagnant' in options:
        moteur['pari_retenu'] = 'Simple Gagnant (proposition non placée)'
    elif 'simple placé' in options:
        moteur['pari_retenu'] = 'Simple Placé (proposition non placée)'
    else:
        moteur['alertes'].append('Aucune offre compatible vérifiée')


def analyser_course(course, maintenant, date_programme):
    identifiant = str(course.get('id') or '').strip()
    valeur_depart = course.get('heure_depart_timestamp')
    if valeur_depart is None:
        valeur_depart = course.get('depart_paris')
    depart = depart_paris(valeur_depart)
    participants = course.get('participants')
    problemes = []
    if not re.fullmatch(r'R\d+C\d+', identifiant):
        problemes.append('Identifiant course invalide')
    if not isinstance(participants, list):
        problemes.append('Liste des participants invalide')
        participants = []
    if course.get('participants_verifies') is not True:
        problemes.append('Participants non vérifiés')
    if depart is None:
        problemes.append('Départ manquant ou fuseau invalide')
    elif depart.date().isoformat() != date_programme:
        problemes.append('Date de départ incohérente')
    elif depart <= maintenant:
        problemes.append('Départ passé : aucun pronostic rétroactif')
    if str(course.get('statut') or '').strip().upper() in EXCLUS:
        problemes.append('Course annulée ou reportée')

    chevaux, numeros = [], set()
    for p in participants:
        if not isinstance(p, dict):
            problemes.append('Participant mal formé')
            continue
        n = numero(p.get('numero'))
        if n is None or n in numeros:
            problemes.append('Numéro de partant invalide ou dupliqué')
            continue
        numeros.add(n)
        if p.get('non_partant') is not True:
            chevaux.append(dict(p, numero=n))
    annonce = numero(course.get('nombre_partants'))
    if annonce is not None and annonce != len(chevaux):
        problemes.append('Nombre de partants incohérent')
    if len(chevaux) < MIN_PARTANTS:
        problemes.append('Moins de trois partants')

    valeur_collecte = course.get('collecte_paris')
    if valeur_collecte is None:
        valeur_collecte = course.get('horodatage_collecte')
    collecte = depart_paris(valeur_collecte)
    if valeur_collecte is not None and collecte is None:
        problemes.append('Horodatage de collecte invalide')
    if collecte is not None:
        age = (maintenant - collecte).total_seconds() / 60
        if age < -5 or age > MAX_AGE_MINUTES:
            problemes.append('Collecte trop ancienne ou datée dans le futur')

    problemes = list(dict.fromkeys(problemes))
    delai = (depart - maintenant).total_seconds() if depart else -1
    moteurs = [analyser_moteur(chevaux, m, problemes, delai) for m in MOTEURS]
    for moteur in moteurs:
        if moteur['validation']:
            choisir_pari(moteur, course.get('paris_disponibles'))

    return {
        'id': identifiant, 'reunion': course.get('reunion'),
        'course': course.get('course'), 'hippodrome': course.get('hippodrome'),
        'nom': course.get('nom'), 'discipline': course.get('discipline'),
        'distance': course.get('distance'),
        'depart_paris': depart.isoformat() if depart else None,
        'partants_annonces': annonce, 'partants_verifies': len(chevaux),
        'controle': 'EXCLU' if problemes else 'PROGRAMME_VERIFIE',
        'collecte_paris': collecte.isoformat() if collecte else None,
        'anomalies': problemes, 'moteurs': moteurs,
    }


def analyser_programme(donnees, maintenant=None):
    maintenant = maintenant or datetime.now(PARIS)
    if maintenant.tzinfo is None:
        raise ValueError('Horodatage de référence sans fuseau')
    maintenant = maintenant.astimezone(PARIS)
    if not isinstance(donnees, dict) or not isinstance(donnees.get('courses'), list) or not donnees['courses']:
        raise ValueError('Programme vide ou invalide')
    date = donnees.get('date')
    if date != maintenant.date().isoformat():
        raise ValueError('Programme hors date de Paris')
    ids = [c.get('id') for c in donnees['courses'] if isinstance(c, dict)]
    if len(ids) != len(donnees['courses']) or any(not isinstance(x, str) or not x for x in ids) or len(set(ids)) != len(ids):
        raise ValueError('Identifiants invalides ou dupliqués')

    analyses = [analyser_course(c, maintenant, date) for c in donnees['courses']]
    analyses.sort(key=lambda c: (c['depart_paris'] is None, c['depart_paris'] or '', c['id']))
    nombre = sum(m['validation'] for c in analyses for m in c['moteurs'])
    motifs = Counter(m['raison'] for c in analyses for m in c['moteurs'] if not m['validation'])
    manquants = Counter()
    for c in analyses:
        for m in c['moteurs']:
            for d in m['indicateurs_manquants']:
                manquants[d['champ']] += d['chevaux']
    return {
        'logiciel': 'MPAA X1000 FUSION', 'schema_version': 3,
        'date': date, 'analyse_effectuee_paris': maintenant.isoformat(),
        'source_programme': donnees.get('source'),
        'statut': 'PRONOSTICS_CALCULES' if nombre else 'ANALYSE_SANS_PRONOSTIC',
        'explication': (
            'Pré-verrous calculés ; aucun FIGÉ créé par ce script.' if nombre
            else 'Aucune sélection validée : consulter diagnostic et collecte sportive.'
        ),
        'nombre_courses': len(analyses), 'nombre_pronostics': nombre,
        'nombre_figes': 0,
        'diagnostic': {
            'refus_par_motif': [{'motif': k, 'nombre': v} for k, v in motifs.most_common(15)],
            'indicateurs_absents': [{'champ': k, 'nombre': v} for k, v in manquants.most_common()],
            'collecte_a_enrichir': nombre == 0 and bool(manquants),
        },
        'courses': analyses,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', default='data/programme_pmu.json')
    parser.add_argument('--output', default='data/analyses_moteurs.json')
    args = parser.parse_args(argv)
    try:
        resultat = analyser_programme(lire(args.input))
        ecrire(args.output, resultat)
        print(
            f'MPAA X1000 : {resultat["nombre_courses"]} courses ; '
            f'{resultat["nombre_pronostics"]} sélections moteur ; '
            'FIGÉS : archivage séparé'
        )
        if not resultat['nombre_pronostics']:
            print('DIAGNOSTIC :', json.dumps(resultat['diagnostic'], ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as erreur:
        print('ERREUR MPAA X1000 :', erreur, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
