# RadioShare — bot Discord

Le bot rejoint ton salon vocal et y diffuse une radio tiree parmi 37 063
stations, filtrable par pays, ville, genre ou nom. Chaque nouveau morceau
est annonce dans le salon texte.

## Commandes

| Commande | Effet |
|---|---|
| `/pays France` | une station au hasard dans un pays |
| `/ville Tokyo, Japan` | une station au hasard dans une ville |
| `/genre Reggae` | une station au hasard dans un genre |
| `/station <nom>` | une station precise |
| `/hasard` | un pays au hasard, puis une station |
| `/suivante` | une autre station de la meme selection |
| `/encours` | rappeler ce qui passe |
| `/stop` | arreter et quitter le vocal |

Les quatre premieres proposent l'autocompletion pendant la frappe.

## Mise en place

1. Creer une application sur https://discord.com/developers/applications
2. Onglet **Bot** : creer le bot, copier son jeton
3. Copier `.env.exemple` en `.env` et y coller le jeton :
   `DISCORD_TOKEN=...`
4. Onglet **OAuth2** : inviter le bot avec les portees `bot` et
   `applications.commands`, permissions **Connect** et **Speak**
5. Installer FFmpeg : `winget install Gyan.FFmpeg`, puis rouvrir le terminal
6. `python bot.py`

Le jeton donne le controle complet du bot. Il ne doit jamais etre partage ni
versionne : `.gitignore` exclut deja `.env`.

## Dependances

- `discord.py[voice]` et `PyNaCl` pour le vocal
- `python-dotenv` pour lire le `.env`
- **FFmpeg**, indispensable : Discord n'accepte que de l'Opus, FFmpeg
  transcode le flux radio a la volee. VLC ne sert pas ici.

## Fichiers

| Fichier | Role |
|---|---|
| `bot.py` | commandes, vocal, annonces |
| `catalogue.py` | regroupements, recherche, autocompletion |
| `flux.py` | resolution des URL et lecture des titres ICY |
| `genres.py` | detection du genre depuis le nom des stations |
| `donnees/stations.json` | catalogue, copie depuis RadioPlayer |

## Notes de conception

**L'autocompletion doit repondre en moins de trois secondes.** Les replis
sans accent sont donc calculees une fois au chargement plutot qu'a chaque
frappe : les suggestions sortent en 5 a 11 ms sur 37 000 stations.

**Les correspondances en debut de nom passent devant.** En tapant `fran` on
cherche la France, pas `Radio Franco de Bogota`.

**Le tirage entre pays est uniforme**, pas pondere par le nombre de stations,
sinon `/hasard` ramenerait sans cesse aux Etats-Unis et au Bresil, qui pesent
a eux seuls un tiers du catalogue.

**Les titres viennent d'une seconde connexion au flux**, pas de FFmpeg. Le fil
qui la lit n'est pas celui d'asyncio : l'envoi des messages est donc
replanifie sur la boucle du bot, sans quoi rien ne partirait.

**Aucune intention privilegiee n'est demandee.** Le bot ne lit jamais le
contenu des messages, il ne repond qu'aux commandes slash.
