#!/usr/bin/env python3
"""
Taxonomie de genres, deduite du nom des stations.

Radio Garden n'expose aucun champ de genre : le nom de la station, son site
web et son slug d'URL sont les seuls indices disponibles. Une station qui ne
declare pas son genre dans son nom restera donc introuvable par ce biais.
C'est une limite de la source, pas du classement.

Chaque genre liste ses mots declencheurs. Les accents et la casse sont
ignores, et le mot doit commencer sur une frontiere de mot : sans cela "rock"
ressortirait dans "Rockford" et "rio" dans "Arion".
"""

import re
import unicodedata

GENRES = {
    "Rock": ["rock", "rocks", "hard rock", "classic rock"],
    "Metal": ["metal", "heavy", "hardcore", "punk"],
    "Pop": ["pop", "hits", "top 40", "chart", "hit radio"],
    "Jazz": ["jazz", "swing", "bebop", "big band"],
    "Blues": ["blues", "rhythm and blues"],
    "Soul / Funk": ["soul", "funk", "motown", "disco", "groove"],
    "Reggae": ["reggae", "ragga", "dub", "ska", "dancehall"],
    "Hip-hop / Rap": ["hip hop", "hiphop", "rap", "urban", "trap"],
    "Electro / Dance": ["electro", "techno", "house", "trance", "dance",
                        "edm", "dj", "club", "trip hop", "drum and bass",
                        "dnb", "ambient", "chill", "lounge", "lofi", "lo fi"],
    "Classique": ["classic", "classique", "classica", "klassik", "clasica",
                  "opera", "symphon", "philharmon", "baroque"],
    "Country / Folk": ["country", "folk", "bluegrass", "americana"],
    "Latino": ["latino", "latina", "salsa", "bachata", "merengue", "cumbia",
               "reggaeton", "tango", "vallenato", "ranchera", "banda",
               "sertanejo", "forro", "samba", "bossa", "mpb"],
    "Chanson francaise": ["chanson", "francais", "francophone", "variete"],
    "Oldies": ["oldies", "gold", "retro", "nostalgi", "vintage", "years",
               "60s", "70s", "80s", "90s", "souvenirs"],
    "Religieux": ["gospel", "christian", "catholic", "cristian", "cristia",
                  "islam", "quran", "coran", "maria", "jesus", "bible",
                  "evangel", "worship"],
    "Monde / Traditionnel": ["world", "traditional", "folklore", "celtic",
                             "afro", "arab", "bollywood", "k-pop", "kpop",
                             "j-pop", "jpop", "anime"],
    "Actualites / Parole": ["news", "info", "talk", "sport", "actualit",
                            "parole", "debat"],
}


def _normaliser(texte):
    if not texte:
        return ""
    d = unicodedata.normalize("NFKD", texte)
    d = "".join(c for c in d if not unicodedata.combining(c))
    return d.casefold()


# Un motif compile par genre, ancre sur un debut de mot. Le cote droit reste
# libre pour que "reggae" attrape aussi "reggaeton".
_MOTIFS = {
    genre: re.compile("|".join(r"\b" + re.escape(_normaliser(m)) for m in mots))
    for genre, mots in GENRES.items()
}


def _slug(chemin):
    parties = [p for p in (chemin or "").split("/") if p]
    # le dernier segment est un identifiant aleatoire, il produirait
    # des correspondances fantomes
    return parties[-2].replace("-", " ") if len(parties) >= 2 else ""


def genres_de(station):
    """Genres detectes pour une station, du plus au moins probable."""
    champs = " ".join((
        _normaliser(station.get("titre")),
        _normaliser(station.get("site_web")),
        _normaliser(_slug(station.get("chemin"))),
    ))
    return [g for g, motif in _MOTIFS.items() if motif.search(champs)]


def tous_les_genres():
    return sorted(GENRES)
