#!/usr/bin/env python3
"""
Acces au catalogue de stations : regroupements, recherche, autocompletion.

Le fichier donnees/stations.json vient du projet RadioPlayer, lui-meme
construit a partir du corpus de V0.1. Il est charge une fois au demarrage
et reste en memoire : 37 000 entrees tiennent largement, et l'autocompletion
de Discord exige une reponse en moins de trois secondes.
"""

import json
import random
import unicodedata
from collections import defaultdict
from pathlib import Path

CATALOGUE = Path(__file__).resolve().parent / "donnees" / "stations.json"


def normaliser(texte):
    """Repli sans accent ni casse : "sao paulo" doit trouver "São Paulo SP"."""
    if not texte:
        return ""
    d = unicodedata.normalize("NFKD", texte)
    return "".join(c for c in d if not unicodedata.combining(c)).casefold().strip()


class Catalogue:

    def __init__(self, chemin=CATALOGUE):
        if not chemin.exists():
            raise SystemExit(
                "catalogue introuvable : %s\n"
                "copier donnees/stations.json depuis le projet RadioPlayer" % chemin)
        self.stations = json.loads(chemin.read_text(encoding="utf-8"))

        self.par_pays = defaultdict(list)
        self.par_ville = defaultdict(list)
        self.par_genre = defaultdict(list)
        for s in self.stations:
            self.par_pays[s["pays"]].append(s)
            self.par_ville["%s, %s" % (s["ville"], s["pays"])].append(s)
            for g in s["genres"]:
                self.par_genre[g].append(s)

        # Index normalises, calcules une fois : refaire le repli sans accent
        # a chaque frappe sur 37 000 stations serait trop lent pour Discord.
        self._pays_norm = {n: normaliser(n) for n in self.par_pays}
        self._villes_norm = {n: normaliser(n) for n in self.par_ville}
        self._stations_norm = [(normaliser(s["nom"]), s) for s in self.stations]

    # ------------------------------------------------------------ recherche

    def _suggerer(self, index, texte, limite=25):
        """
        Propositions pour l'autocompletion.

        Les correspondances en debut de nom passent devant : quand on tape
        "fran", on cherche la France, pas "Radio Franco de Bogota".
        """
        cible = normaliser(texte)
        if not cible:
            return sorted(index, key=lambda n: -len(self._groupe(n)))[:limite]
        debuts, milieux = [], []
        for nom, norm in index.items():
            if norm.startswith(cible):
                debuts.append(nom)
            elif cible in norm:
                milieux.append(nom)
        debuts.sort()
        milieux.sort()
        return (debuts + milieux)[:limite]

    def _groupe(self, nom):
        return (self.par_pays.get(nom) or self.par_ville.get(nom)
                or self.par_genre.get(nom) or [])

    def suggerer_pays(self, texte):
        return self._suggerer(self._pays_norm, texte)

    def suggerer_villes(self, texte):
        return self._suggerer(self._villes_norm, texte)

    def suggerer_genres(self, texte):
        cible = normaliser(texte)
        return sorted(g for g in self.par_genre if cible in normaliser(g))[:25]

    def suggerer_stations(self, texte, limite=25):
        cible = normaliser(texte)
        if len(cible) < 2:
            return []
        debuts, milieux = [], []
        for norm, s in self._stations_norm:
            if norm.startswith(cible):
                debuts.append(s)
            elif cible in norm:
                milieux.append(s)
            if len(debuts) >= limite:
                break
        return (debuts + milieux)[:limite]

    # -------------------------------------------------------------- tirages

    def stations_de(self, categorie, nom):
        table = {"pays": self.par_pays, "ville": self.par_ville,
                 "genre": self.par_genre}[categorie]
        return list(table.get(nom, []))

    def station_par_id(self, identifiant):
        for s in self.stations:
            if s["id"] == identifiant:
                return s
        return None

    def pays_au_hasard(self):
        """
        Tirage uniforme entre pays, pas pondere par le nombre de stations.

        Une ponderation ramenerait sans cesse aux Etats-Unis et au Bresil,
        qui pesent a eux seuls un tiers du catalogue.
        """
        pays = random.choice(list(self.par_pays))
        return pays, list(self.par_pays[pays])

    def resume(self):
        return "%d stations, %d pays, %d villes, %d genres" % (
            len(self.stations), len(self.par_pays),
            len(self.par_ville), len(self.par_genre))
