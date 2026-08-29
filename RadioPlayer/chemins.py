#!/usr/bin/env python3
"""
Emplacements des fichiers, en execution normale comme dans un exe.

Un programme empaquete par PyInstaller ne peut pas ecrire a cote de son
executable : le dossier peut etre en lecture seule, et en mode fichier unique
le contenu est extrait dans un repertoire temporaire efface a la fermeture.
Les donnees modifiables vont donc dans %APPDATA%/RadioShare, tandis que le
catalogue, qui ne change jamais, reste embarque avec le programme.
"""

import os
import shutil
import sys
from pathlib import Path

NOM_APPLICATION = "RadioShare"


def empaquete():
    return getattr(sys, "frozen", False)


def racine_programme():
    """Dossier des fichiers livres avec le programme, en lecture seule."""
    if empaquete():
        # _MEIPASS n'existe qu'en mode fichier unique ; sinon c'est le
        # dossier de l'executable.
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def ressource(chemin_relatif):
    return racine_programme() / chemin_relatif


def dossier_utilisateur():
    """Dossier inscriptible, cree au besoin."""
    base = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME")
    racine = Path(base) if base else Path.home() / ".config"
    dossier = racine / NOM_APPLICATION
    dossier.mkdir(parents=True, exist_ok=True)
    return dossier


def fichier_utilisateur(nom):
    return dossier_utilisateur() / nom


def reprendre_anciennes_donnees(noms):
    """
    Recupere les fichiers laisses par la version lancee depuis les sources.

    Sans cela, passer a l'executable donnerait l'impression d'avoir perdu
    ses favoris, alors qu'ils sont simplement restes dans l'ancien dossier.
    """
    ancien = Path(__file__).resolve().parent / "donnees"
    if not ancien.is_dir():
        return []
    reprises = []
    for nom in noms:
        source, cible = ancien / nom, fichier_utilisateur(nom)
        if source.exists() and not cible.exists():
            try:
                shutil.copy2(source, cible)
                reprises.append(nom)
            except OSError:
                pass
    return reprises
