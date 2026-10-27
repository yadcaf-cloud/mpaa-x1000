import argparse, hashlib, json, os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
MOTEURS = ("M1", "M2", "M3", "M4", "M5")

def convertir_heure(valeur):
    d = datetime.fromisoformat(valeur.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("Fuseau horaire obligatoire")
    return d.astimezone(timezone.utc)

def empreinte(objet):
    texte = json.dumps(objet, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()

def verifier(fichier):
    document = json.loads(Path(fichier).read_text(encoding="utf-8"))
    p = document["payload"]
    if empreinte(p) != document["sha256"]:
        raise ValueError("Empreinte SHA-256 incorrecte : " + str(fichier))
    if convertir_heure(p["heure_fige_utc"]) >= convertir_heure(p["depart_paris"]):
        raise ValueError("FIGÉ après départ : " + str(fichier))
    if convertir_heure(p["heure_fige_utc"]) != convertir_heure(p["heure_fige_paris"]):
        raise ValueError("Horodatages incohérents")
    if p["id"] != Path(fichier).stem:
        raise ValueError("Identifiant incohérent")
    return p

def audit(dossier):
    vus = set()
    for fichier in Path(dossier).glob("*/*.json"):
        p = verifier(fichier)
        if p["id"] in vus:
            raise ValueError("FIGÉ dupliqué")
        vus.add(p["id"])
    return len(vus)

def archiver(donnees, dossier):
    maintenant = datetime.now(timezone.utc)
    if donnees["date"] != maintenant.astimezone(PARIS).date().isoformat():
        raise ValueError("Programme périmé")
    total = 0
    for course in donnees["courses"]:
        for moteur in course["moteurs"]:
            ordre = moteur.get("ordre_arrivee_espere")
            if not (
                moteur.get("moteur") in MOTEURS
                and moteur.get("validation") is True
                and isinstance(ordre, list)
                and len(ordre) >= 2
                and len(set(map(str, ordre))) == len(ordre)
                and moteur.get("gagnant_espere") == ordre[0]
                and moteur.get("pari_retenu")
            ):
                continue
            if (convertir_heure(course["depart_paris"]) - maintenant).total_seconds() <= 120:
                continue
            identifiant = f"{donnees['date']}-{course['id']}-{moteur['moteur']}"
            fichier = Path(dossier) / donnees["date"] / (identifiant + ".json")
            if fichier.exists():
                verifier(fichier)
                continue
            p = {
                "id": identifiant,
                "course_id": course["id"],
                "moteur": moteur["moteur"],
                "depart_paris": course["depart_paris"],
                "heure_fige_utc": maintenant.isoformat(),
                "heure_fige_paris": maintenant.astimezone(PARIS).isoformat(),
                "gagnant_espere": moteur["gagnant_espere"],
                "meilleur_place": moteur.get("meilleur_place"),
                "ordre_arrivee_espere": ordre,
                "pari_retenu": moteur["pari_retenu"],
                "source_programme": donnees.get("source_programme")
            }
            fichier.parent.mkdir(parents=True, exist_ok=True)
            try:
                fd = os.open(fichier, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            except FileExistsError:
                verifier(fichier)
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as sortie:
                json.dump({"payload": p, "sha256": empreinte(p)}, sortie, ensure_ascii=False, indent=2)
            total += 1
    return total

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["archive", "audit"])
    parser.add_argument("--root", default="archives/figes")
    parser.add_argument("--input", default="data/analyses_moteurs.json")
    args = parser.parse_args()
    if args.mode == "archive":
        donnees = json.loads(Path(args.input).read_text(encoding="utf-8"))
        print("Nouveaux FIGÉS :", archiver(donnees, args.root))
    print("Archives vérifiées :", audit(args.root))
