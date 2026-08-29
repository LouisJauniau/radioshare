# RadioShare — Lecteur

Application de bureau pour ecouter les radios du monde. On clique sur un pays,
une ville ou un genre, et une station est tiree au hasard dans la selection.

## Lancer

    python app.py

## Construire l'executable

    python construire.py

Le resultat est dans `dist/RadioShare/`. **Tout le dossier doit etre
distribue**, pas seulement `RadioShare.exe` : le reste des fichiers vit dans
`_internal/`.

VLC n'est pas embarque. `python-vlc` n'est qu'une liaison vers `libvlc`, et
empaqueter la DLL avec ses greffons de decodage ajouterait plus de cent
megaoctets pour une fiabilite mediocre. La machine cible doit donc avoir VLC
installe ; l'application le verifie au demarrage et affiche un message
explicite si il manque, plutot que de rester muette.

Les favoris et les reglages sont ecrits dans `%APPDATA%/RadioShare`, et non a
cote du programme : un executable peut se trouver dans un dossier en lecture
seule. Les favoris crees avec la version lancee depuis les sources sont
repris automatiquement au premier lancement de l'executable.

## Regenerer le catalogue

Le catalogue est construit a partir du projet `../V0.1` :

    python preparer_donnees.py

37 063 stations, 225 pays, 12 014 villes. Les 1 201 flux qui n'avaient pas
repondu lors du sondage de V0.1 sont ecartes.

## Fichiers

| Fichier | Role |
|---|---|
| `app.py` | interface PyQt5 et pilotage de VLC |
| `donnees/favoris.json` | favoris, stockes par identifiant de station |
| `donnees/reglages.json` | niveau de volume, retenu d'une session a l'autre |
| `exclues.json` | stations ecartees, dans %APPDATA%/RadioShare |
| `flux.py` | resolution des URL et lecture des metadonnees ICY |
| `genres.py` | detection du genre a partir du nom des stations |
| `preparer_donnees.py` | construction de `donnees/stations.json` |

## Dependances

- **PyQt5** pour l'interface
- **python-vlc** et **VLC** installe sur la machine, pour l'audio

VLC decode tous les formats de flux radio, y compris AAC et HLS, la ou les
codecs Windows par defaut echouent silencieusement sur certains d'entre eux.

## Favoris

Le bouton **Favori** marque la station en cours ; le mode **Favoris** de la
liste les rassemble. Ils sont enregistres par identifiant de station, pas par
nom : un identifiant Radio Garden est stable, alors qu'un nom peut changer ou
etre porte par plusieurs stations. Un identifiant absent du catalogue apres
une regeneration est ignore sans bruit.

## Stations ecartees

Le bouton **Pas interesse** retire la station en cours de tous les tirages :
pays, ville, genre, tirage mondial et recherche par nom. Le lecteur enchaine
aussitot sur une autre station, puisque cliquer revient a dire "pas celle-ci".

Le mode **Ecartees** de la liste permet de revenir sur sa decision. Sans cette
vue, la mise a l'ecart serait irreversible : la station disparaissant aussi de
la recherche, plus rien ne permettrait de la retrouver.

Ecarter une station la retire des favoris, et la mettre en favori annule son
ecartement : les deux etats s'excluent.

## Deux limites assumees

**Les genres viennent du nom des stations.** Radio Garden n'expose aucun champ
de genre : seuls le nom, le site web et le slug d'URL sont exploitables. Environ
14 % des stations sont donc etiquetees. Une station de reggae qui ne le dit pas
dans son nom reste introuvable par ce biais. Pour de vrais genres il faudrait
rescraper Radio Browser, qui les publie.

**Les titres passent par une seconde connexion.** VLC lit les flux mais
n'expose pas le StreamTitle ICY : ni `get_meta(NowPlaying)` ni l'evenement
`MediaMetaChanged` ne remontent quoi que ce soit, verification faite sur
plusieurs stations qui l'emettent pourtant. Un fil dedie ouvre donc sa propre
connexion en lecture seule. Cela double le trafic d'une station, environ
16 Ko/s, ce qui reste negligeable.
