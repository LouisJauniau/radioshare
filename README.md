# RadioShare

Deux programmes construits autour d'un catalogue de **37 063 stations de radio
en ligne**, décrites par pays, ville, genre, coordonnées géographiques et titre
en cours de diffusion.

| Dossier | Programme |
|---|---|
| [`RadioPlayer/`](RadioPlayer/) | lecteur de bureau : recherche, filtres, favoris, lecture |
| [`DiscordBot/`](DiscordBot/) | bot Discord qui diffuse une station dans un salon vocal |

## Le catalogue

`stations.json` contient 37 063 entrées normalisées à partir de sources
publiques. Chaque station porte un identifiant, un nom, une ville, un pays, un
site, un hébergeur, des genres, un compteur de titres, un indicateur musical et
une paire latitude/longitude. `preparer_donnees.py` produit ce fichier :
déduplication, normalisation des pays et des villes, et déduction du genre
depuis le nom de la station quand il n'est pas renseigné.

## Problèmes intéressants

**L'autocomplétion doit répondre en moins de trois secondes.** C'est la limite
imposée par Discord. Les replis sans accent des 37 000 noms sont donc calculés
une fois au chargement plutôt qu'à chaque frappe : les suggestions sortent en 5
à 11 ms.

**Les correspondances en début de nom passent devant.** En tapant `fran` on
cherche la France, pas `Radio Franco de Bogota`.

**Le tirage entre pays est uniforme, pas pondéré par le nombre de stations.**
Sinon la commande `/hasard` ramènerait sans cesse aux États-Unis et au Brésil,
qui pèsent à eux seuls un tiers du catalogue.

**Les titres viennent d'une seconde connexion au flux**, pas de FFmpeg, car
FFmpeg consomme le flux audio sans exposer les métadonnées ICY. Le fil qui lit
cette seconde connexion n'est pas celui d'asyncio : l'envoi des messages est
donc replanifié sur la boucle du bot, sans quoi rien ne partirait.

**Discord n'accepte que de l'Opus.** FFmpeg transcode le flux radio à la volée.

## Mise en route

Chaque dossier a son propre README avec les dépendances et la procédure :

- [`RadioPlayer/README.md`](RadioPlayer/README.md)
- [`DiscordBot/README.md`](DiscordBot/README.md)

Le bot Discord a besoin d'un jeton dans un fichier `.env`, jamais versionné.
Copiez `DiscordBot/.env.exemple` et remplissez-le.

## Voir aussi

[spotisim](https://github.com/LouisJauniau/spotisim) — construction de playlists
par similarité, dépôt séparé.
