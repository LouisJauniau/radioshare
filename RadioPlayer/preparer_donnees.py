#!/usr/bin/env python3
"""
Construit le catalogue du lecteur a partir du corpus de RadioShare V0.1.

Le lecteur n'a pas les memes besoins que l'outil de captation : une station
qui ne publie pas ses titres se laisse tres bien ecouter. On garde donc tout
le catalogue, en ecartant seulement les flux qui se sont reveles injoignables
lors du sondage, et on note pour chaque station si elle annonce ses titres.

Usage :
    python preparer_donnees.py
    python preparer_donnees.py --source ../V0.1 --sortie donnees/stations.json
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import genres as G

SOURCE = "../V0.1"
SORTIE = "donnees/stations.json"


def charger_jsonl(chemin, obligatoire=True):
    p = Path(chemin)
    if not p.exists():
        if obligatoire:
            sys.exit(f"introuvable : {p}\nverifier --source")
        return []
    lignes = []
    with p.open(encoding="utf-8") as f:
        for ligne in f:
            ligne = ligne.strip()
            if not ligne:
                continue
            try:
                lignes.append(json.loads(ligne))
            except json.JSONDecodeError:
                continue
    return lignes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=SOURCE, help="dossier du projet V0.1")
    ap.add_argument("--sortie", default=SORTIE)
    ap.add_argument("--garder-injoignables", action="store_true",
                    help="conserver les flux qui n'ont pas repondu au sondage")
    args = ap.parse_args()

    base = Path(args.source)
    corpus = charger_jsonl(base / "data/channels_clean.jsonl")
    sondage = charger_jsonl(base / "data/sondage.jsonl", obligatoire=False)
    classement = charger_jsonl(base / "data/classement.jsonl", obligatoire=False)

    etats = {s["channel_id"]: s.get("etat") for s in sondage}
    verdicts = {c["channel_id"]: c.get("verdict") for c in classement}

    stations, ignorees = [], 0
    compte_genres = Counter()

    for st in corpus:
        cid = st["channel_id"]
        etat = etats.get(cid)
        if etat in ("erreur", "pas_de_flux") and not args.garder_injoignables:
            ignorees += 1
            continue

        g = G.genres_de(st)
        for x in g:
            compte_genres[x] += 1

        stations.append({
            "id": cid,
            "nom": st.get("titre"),
            "ville": st.get("ville"),
            "pays": st.get("pays"),
            "site": st.get("site_web"),
            "hebergeur": st.get("hebergeur_flux"),
            "genres": g,
            "titres": etat == "titre",          # publie ses titres en direct
            "musicale": verdicts.get(cid) == "musique",
            "lat": st.get("lat"),
            "lon": st.get("lon"),
        })

    stations.sort(key=lambda s: ((s["pays"] or "").casefold(),
                                 (s["ville"] or "").casefold(),
                                 (s["nom"] or "").casefold()))

    sortie = Path(args.sortie)
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(json.dumps(stations, ensure_ascii=False), encoding="utf-8")

    pays = {s["pays"] for s in stations}
    villes = {(s["pays"], s["ville"]) for s in stations}
    avec_genre = sum(1 for s in stations if s["genres"])

    print(f"{len(stations)} stations ecrites dans {sortie}")
    print(f"  {len(pays)} pays, {len(villes)} villes")
    print(f"  {ignorees} flux injoignables ecartes")
    print(f"  {avec_genre} stations avec au moins un genre "
          f"({100 * avec_genre / max(len(stations), 1):.0f}%)\n")
    for genre, n in compte_genres.most_common():
        print(f"  {n:6}  {genre}")


if __name__ == "__main__":
    main()
