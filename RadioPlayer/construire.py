#!/usr/bin/env python3
"""
Construit l'executable Windows du lecteur.

    python construire.py

Le resultat est dans dist/RadioShare/, avec RadioShare.exe a la racine.
Tout le dossier doit etre distribue ensemble, pas seulement l'exe.

VLC n'est volontairement pas embarque : python-vlc n'est qu'une liaison vers
libvlc, et empaqueter la DLL avec ses greffons de decodage alourdirait le
resultat de plus de cent megaoctets pour une fiabilite mediocre. La machine
cible doit donc avoir VLC installe, ce que l'application verifie au demarrage
avec un message explicite.
"""

import shutil
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent
NOM = "RadioShare"

# Modules tires par PyQt5 mais inutiles ici : les exclure allege nettement.
EXCLUSIONS = [
    "PyQt5.QtWebEngineWidgets", "PyQt5.QtWebEngine", "PyQt5.QtWebEngineCore",
    "PyQt5.QtQml", "PyQt5.QtQuick", "PyQt5.QtQuick3D", "PyQt5.QtMultimedia",
    "PyQt5.QtBluetooth", "PyQt5.QtNfc", "PyQt5.QtPositioning", "PyQt5.QtSql",
    "PyQt5.QtTest", "PyQt5.QtDesigner", "PyQt5.QtHelp", "PyQt5.Qt3DCore",
    "PyQt5.QtCharts", "PyQt5.QtDataVisualization",
    "tkinter", "matplotlib", "numpy", "pandas", "PIL", "scipy",
]


def main():
    catalogue = RACINE / "donnees" / "stations.json"
    if not catalogue.exists():
        sys.exit("catalogue absent, lancer d'abord : python preparer_donnees.py")

    for dossier in ("build", "dist"):
        shutil.rmtree(RACINE / dossier, ignore_errors=True)

    commande = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--name", NOM,
        "--windowed",                       # pas de console derriere la fenetre
        # La destination de --add-data est un DOSSIER : indiquer un chemin
        # de fichier cree un repertoire du meme nom contenant le fichier.
        "--add-data", "%s%sdonnees" % (catalogue, ";"),
        "--collect-submodules", "vlc",
    ]
    for module in EXCLUSIONS:
        commande += ["--exclude-module", module]
    commande.append(str(RACINE / "app.py"))

    print("construction en cours, compter une a deux minutes...\n")
    resultat = subprocess.run(commande, cwd=RACINE)
    if resultat.returncode != 0:
        sys.exit("echec de la construction")

    cible = RACINE / "dist" / NOM
    poids = sum(f.stat().st_size for f in cible.rglob("*") if f.is_file())
    print("\ntermine : %s" % (cible / (NOM + ".exe")))
    print("poids du dossier : %.0f Mo" % (poids / 1e6))


if __name__ == "__main__":
    main()
