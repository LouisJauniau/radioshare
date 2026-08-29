#!/usr/bin/env python3
"""
RadioShare — bot Discord.

Rejoint ton salon vocal et y diffuse une radio tiree au hasard parmi un
catalogue de 37 000 stations, filtrable par pays, ville, genre ou nom.
Chaque nouveau morceau est annonce dans le salon texte.

Commandes :
    /pays France          une station au hasard dans un pays
    /ville Tokyo, Japan   une station au hasard dans une ville
    /genre Reggae         une station au hasard dans un genre
    /station <nom>        une station precise
    /hasard               un pays au hasard, puis une station
    /suivante             une autre station de la meme selection
    /encours              rappeler ce qui passe
    /stop                 arreter et quitter le vocal

Mise en place :
    1. creer une application sur https://discord.com/developers/applications
    2. onglet Bot : creer le bot et copier son jeton
    3. ecrire ce jeton dans un fichier .env a cote de ce script :
           DISCORD_TOKEN=colle_ton_jeton_ici
       Ce jeton donne le controle du bot : ne jamais le partager ni le
       versionner. Le fichier .env doit rester hors de tout depot Git.
    4. onglet OAuth2 : inviter le bot avec les portees "bot" et
       "applications.commands", et les permissions Connect + Speak
    5. installer FFmpeg, puis lancer :  python bot.py
"""

import asyncio
import os
import random
import shutil
import sys

import discord
from discord import app_commands
from dotenv import load_dotenv

import catalogue as cat
import flux

# FFmpeg reconnecte tout seul si le flux tombe : une radio coupee quelques
# secondes ne doit pas terminer l'ecoute.
OPTIONS_AVANT = ("-reconnect 1 -reconnect_streamed 1 "
                 "-reconnect_delay_max 5 -nostdin")
# aresample=async=1 absorbe la derive d'horloge entre l'emetteur radio et
# Discord : sans lui, une longue ecoute finit par craqueler.
OPTIONS = "-vn -af aresample=async=1 -loglevel error"

# Un salon vocal non booste plafonne a 64 kbps. Encoder au-dela fait perdre
# des paquets en route, ce qui s'entend comme un gresillement.
DEBIT_MIN, DEBIT_MAX = 32, 128


def debit_pour(client):
    """Debit Opus a viser, cale sur la capacite reelle du salon vocal."""
    salon = getattr(client, "channel", None)
    bits = getattr(salon, "bitrate", None) or 64000
    return max(DEBIT_MIN, min(bits // 1000, DEBIT_MAX))


class Ecoute:
    """Etat d'ecoute d'un serveur : la station, le salon, le suivi des titres."""

    def __init__(self, salon_texte):
        self.salon_texte = salon_texte
        self.station = None
        self.selection = []
        self.origine = ""
        self.suiveur = None
        self.dernier_titre = None

    def arreter_suiveur(self):
        if self.suiveur is not None:
            self.suiveur.stop()
            self.suiveur = None


class RadioBot(discord.Client):

    def __init__(self):
        # Aucune intention privilegiee n'est necessaire : le bot ne lit
        # jamais le contenu des messages, il ne repond qu'aux commandes.
        super().__init__(intents=discord.Intents.default())
        self.arbre = app_commands.CommandTree(self)
        self.catalogue = cat.Catalogue()
        self.ecoutes = {}               # guild_id -> Ecoute

    async def setup_hook(self):
        await self.arbre.sync()

    async def on_ready(self):
        print("connecte comme %s" % self.user)
        print("catalogue : %s" % self.catalogue.resume())
        print("%d serveur(s)" % len(self.guilds))


bot = RadioBot()


# ---------------------------------------------------------------- utilitaires

def ecoute_de(interaction):
    return bot.ecoutes.get(interaction.guild_id)


async def rejoindre(interaction):
    """
    Amene le bot dans le salon vocal de l'utilisateur.

    Renvoie le client vocal, ou None apres avoir explique le refus : c'est
    toujours l'utilisateur qui designe le salon en s'y trouvant.
    """
    voix = getattr(interaction.user, "voice", None)
    if voix is None or voix.channel is None:
        await interaction.followup.send(
            "Rejoins d'abord un salon vocal, puis relance la commande.")
        return None

    salon = voix.channel
    client = interaction.guild.voice_client
    if client is None:
        try:
            return await salon.connect()
        except discord.ClientException:
            return interaction.guild.voice_client
        except asyncio.TimeoutError:
            await interaction.followup.send(
                "Connexion au salon vocal impossible, reessaie.")
            return None
    if client.channel != salon:
        await client.move_to(salon)
    return client


def annoncer_titre(guild_id, titre):
    """
    Publie un titre depuis le fil de lecture ICY.

    Ce fil n'est pas celui d'asyncio : il faut donc replanifier l'envoi sur
    la boucle du bot, sans quoi rien ne partirait.
    """
    ecoute = bot.ecoutes.get(guild_id)
    if ecoute is None or titre == ecoute.dernier_titre:
        return
    ecoute.dernier_titre = titre
    asyncio.run_coroutine_threadsafe(
        ecoute.salon_texte.send("♪  **%s**" % titre), bot.loop)


async def jouer(interaction, station, selection, origine):
    """Resout le flux, le diffuse dans le vocal et suit les titres."""
    client = await rejoindre(interaction)
    if client is None:
        return

    ecoute = bot.ecoutes.setdefault(interaction.guild_id,
                                    Ecoute(interaction.channel))
    ecoute.salon_texte = interaction.channel
    ecoute.selection = selection
    ecoute.origine = origine
    ecoute.arreter_suiveur()
    ecoute.dernier_titre = None

    # La resolution est un appel reseau bloquant : hors de la boucle asyncio,
    # sinon tout le bot se fige pendant plusieurs secondes.
    url = await asyncio.to_thread(flux.resoudre, station["id"])
    if not url:
        await interaction.followup.send(
            "Flux injoignable pour **%s**, essaie `/suivante`." % station["nom"])
        return

    if client.is_playing():
        client.stop()
    try:
        # Surtout pas from_probe : il recopie le debit du flux source, si bien
        # qu'une station en 320 kbps saturait le salon. Il bascule aussi en
        # "copy" quand la source est deja en Opus, ce qui saute le passage
        # obligatoire en 48 kHz.
        source = discord.FFmpegOpusAudio(
            url, bitrate=debit_pour(client),
            before_options=OPTIONS_AVANT, options=OPTIONS)
    except Exception as erreur:
        await interaction.followup.send(
            "Ce flux n'a pas pu etre lu (%s). Essaie `/suivante`."
            % type(erreur).__name__)
        return
    client.play(source)

    ecoute.station = station
    ecoute.suiveur = flux.SuiveurTitres(
        url, lambda t: annoncer_titre(interaction.guild_id, t), station["nom"])
    ecoute.suiveur.start()

    encart = discord.Embed(
        title=station["nom"] or "sans nom",
        description="%s, %s" % (station["ville"], station["pays"]),
        colour=0x2F6F57)
    encart.add_field(name="Tirage", value="%s  ·  %d stations"
                     % (origine, len(selection)))
    if station.get("genres"):
        encart.add_field(name="Genres", value=", ".join(station["genres"]))
    if station.get("site"):
        encart.add_field(name="Site", value=station["site"], inline=False)
    if not station.get("titres"):
        encart.set_footer(text="Cette station ne publie pas ses titres")
    await interaction.followup.send(embed=encart)


async def tirer(interaction, selection, origine, exclue=None):
    if not selection:
        await interaction.followup.send("Aucune station pour cette selection.")
        return
    restantes = [s for s in selection if s is not exclue] or selection
    await jouer(interaction, random.choice(restantes), selection, origine)


# ------------------------------------------------------------------ commandes

async def _auto_pays(interaction, courant):
    return [app_commands.Choice(name=n, value=n)
            for n in bot.catalogue.suggerer_pays(courant)]


async def _auto_ville(interaction, courant):
    return [app_commands.Choice(name=n[:100], value=n[:100])
            for n in bot.catalogue.suggerer_villes(courant)]


async def _auto_genre(interaction, courant):
    return [app_commands.Choice(name=n, value=n)
            for n in bot.catalogue.suggerer_genres(courant)]


async def _auto_station(interaction, courant):
    propositions = []
    for s in bot.catalogue.suggerer_stations(courant):
        etiquette = "%s — %s, %s" % (s["nom"], s["ville"], s["pays"])
        propositions.append(app_commands.Choice(name=etiquette[:100],
                                                value=s["id"]))
    return propositions


@bot.arbre.command(name="pays", description="Une radio au hasard dans un pays")
@app_commands.describe(nom="Nom du pays")
@app_commands.autocomplete(nom=_auto_pays)
async def cmd_pays(interaction, nom: str):
    await interaction.response.defer()
    await tirer(interaction, bot.catalogue.stations_de("pays", nom), nom)


@bot.arbre.command(name="ville", description="Une radio au hasard dans une ville")
@app_commands.describe(nom="Ville, Pays")
@app_commands.autocomplete(nom=_auto_ville)
async def cmd_ville(interaction, nom: str):
    await interaction.response.defer()
    await tirer(interaction, bot.catalogue.stations_de("ville", nom), nom)


@bot.arbre.command(name="genre", description="Une radio au hasard dans un genre")
@app_commands.describe(nom="Genre musical")
@app_commands.autocomplete(nom=_auto_genre)
async def cmd_genre(interaction, nom: str):
    await interaction.response.defer()
    await tirer(interaction, bot.catalogue.stations_de("genre", nom), nom)


@bot.arbre.command(name="station", description="Ecouter une station precise")
@app_commands.describe(nom="Nom de la station")
@app_commands.autocomplete(nom=_auto_station)
async def cmd_station(interaction, nom: str):
    await interaction.response.defer()
    station = bot.catalogue.station_par_id(nom)
    if station is None:
        # L'utilisateur a valide son texte sans choisir dans la liste
        trouvees = bot.catalogue.suggerer_stations(nom, limite=1)
        if not trouvees:
            await interaction.followup.send(
                "Aucune station de ce nom. Choisis une proposition de la liste.")
            return
        station = trouvees[0]
    await jouer(interaction, station, [station], "station choisie")


@bot.arbre.command(name="hasard", description="Un pays au hasard, puis une radio")
async def cmd_hasard(interaction):
    await interaction.response.defer()
    pays, stations = bot.catalogue.pays_au_hasard()
    await tirer(interaction, stations, pays)


@bot.arbre.command(name="suivante",
                   description="Une autre station de la meme selection")
async def cmd_suivante(interaction):
    await interaction.response.defer()
    ecoute = ecoute_de(interaction)
    if ecoute is None or not ecoute.selection:
        await interaction.followup.send("Rien en cours : lance `/hasard` d'abord.")
        return
    await tirer(interaction, ecoute.selection, ecoute.origine, ecoute.station)


@bot.arbre.command(name="encours", description="Ce qui passe en ce moment")
async def cmd_encours(interaction):
    ecoute = ecoute_de(interaction)
    if ecoute is None or ecoute.station is None:
        await interaction.response.send_message("Rien en cours.")
        return
    station = ecoute.station
    texte = "**%s** — %s, %s" % (station["nom"], station["ville"], station["pays"])
    if ecoute.dernier_titre:
        texte += "\n♪  %s" % ecoute.dernier_titre
    elif not station.get("titres"):
        texte += "\nCette station ne publie pas ses titres."
    else:
        texte += "\nAucun titre annonce pour l'instant."
    await interaction.response.send_message(texte)


@bot.arbre.command(name="stop", description="Arreter et quitter le vocal")
async def cmd_stop(interaction):
    ecoute = bot.ecoutes.pop(interaction.guild_id, None)
    if ecoute is not None:
        ecoute.arreter_suiveur()
    client = interaction.guild.voice_client
    if client is not None:
        await client.disconnect()
    await interaction.response.send_message("Ecoute arretee.")


# ---------------------------------------------------------------------- entree

def verifier_ffmpeg():
    """
    FFmpeg est indispensable : Discord n'accepte que de l'Opus, et c'est lui
    qui transcode le flux radio a la volee.
    """
    if shutil.which("ffmpeg"):
        return
    sys.exit(
        "FFmpeg est introuvable dans le PATH.\n"
        "Discord n'accepte que de l'audio Opus : FFmpeg transcode le flux.\n"
        "Installation la plus simple sous Windows :\n"
        "    winget install Gyan.FFmpeg\n"
        "puis rouvrir le terminal et relancer.")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    verifier_ffmpeg()

    load_dotenv()
    jeton = os.environ.get("DISCORD_TOKEN")
    if not jeton:
        sys.exit(
            "jeton Discord absent.\n"
            "Creer un fichier .env a cote de ce script, contenant :\n"
            "    DISCORD_TOKEN=ton_jeton\n"
            "Ce jeton donne le controle du bot : ne jamais le partager "
            "ni l'ajouter a un depot Git.")

    bot.run(jeton)


if __name__ == "__main__":
    main()
