#!/usr/bin/env python3
"""
Resolution des flux et lecture des metadonnees ICY.

VLC lit parfaitement les flux mais n'expose pas le StreamTitle ICY : ni
get_meta(NowPlaying) ni l'evenement MediaMetaChanged ne remontent quoi que
ce soit, verification faite sur plusieurs stations qui l'emettent pourtant.
On ouvre donc une seconde connexion, en lecture seule, dediee aux
metadonnees. Cela double le trafic d'une station (environ 16 Ko/s), ce qui
reste negligeable, et c'est le prix d'un affichage fiable du morceau en cours.
"""

import re
import threading
import time

import requests

RG_ECOUTE = "https://radio.garden/api/ara/content/listen/{}/channel.mp3"
UA = "RadioShare-Player/1.0"
TIMEOUT = 15

RE_TITRE = re.compile(r"StreamTitle=(?:'(.*?)'|\"(.*?)\")\s*;", re.DOTALL)
NUMERIQUE = re.compile(r"^[\d\s\-_.]+$")
NON_TITRES = {"live", "unknown", "n/a", "-", "--", "...", "no title",
              "default", "stream", "radio", "music", "advert", "advertisement"}


def url_ecoute(channel_id):
    return RG_ECOUTE.format(channel_id)


def resoudre(channel_id, session=None):
    """
    L'endpoint d'ecoute repond 302 vers le flux reel.

    VLC sait suivre la redirection tout seul, mais on la resout ici pour que
    le lecteur audio et le lecteur de metadonnees visent la meme adresse.
    """
    s = session or requests.Session()
    try:
        r = s.get(url_ecoute(channel_id), allow_redirects=False, stream=True,
                  timeout=TIMEOUT, headers={"User-Agent": UA})
        r.close()
        return r.headers.get("Location")
    except requests.RequestException:
        return None


def titre_utilisable(titre, nom_station=None):
    if not titre or len(titre) < 3:
        return False
    if NUMERIQUE.match(titre):
        return False
    bas = titre.casefold().strip()
    if bas in NON_TITRES:
        return False
    return not (nom_station and bas == nom_station.casefold().strip())


def _lire_exact(brut, n):
    """L'alignement sur metaint doit etre exact, sinon on lit du bruit."""
    morceaux = bytearray()
    while len(morceaux) < n:
        bloc = brut.read(n - len(morceaux))
        if not bloc:
            return None
        morceaux.extend(bloc)
    return bytes(morceaux)


class SuiveurTitres(threading.Thread):
    """
    Lit en continu les titres annonces par une station.

    Appelle rappel(titre) a chaque nouveau morceau. S'arrete proprement via
    stop(), y compris pendant une lecture bloquante, car le socket est ferme.
    """

    def __init__(self, url, rappel, nom_station=None, rappel_erreur=None):
        super().__init__(daemon=True)
        self.url = url
        self.rappel = rappel
        self.rappel_erreur = rappel_erreur
        self.nom_station = nom_station
        self._arret = threading.Event()
        self._reponse = None

    def stop(self):
        self._arret.set()
        if self._reponse is not None:
            try:
                self._reponse.close()
            except Exception:
                pass

    def run(self):
        dernier = None
        echecs = 0
        while not self._arret.is_set() and echecs <= 3:
            try:
                s = requests.Session()
                s.headers.update({"User-Agent": UA, "Icy-MetaData": "1"})
                self._reponse = s.get(self.url, stream=True, timeout=TIMEOUT)
                metaint = self._reponse.headers.get("icy-metaint")
                if not metaint:
                    if self.rappel_erreur:
                        self.rappel_erreur("cette station ne publie pas ses titres")
                    return
                metaint = int(metaint)
                echecs = 0

                while not self._arret.is_set():
                    if _lire_exact(self._reponse.raw, metaint) is None:
                        raise ConnectionError("flux interrompu")
                    longueur = self._reponse.raw.read(1)
                    if not longueur:
                        raise ConnectionError("flux interrompu")
                    taille = longueur[0] * 16
                    if taille == 0:
                        continue
                    donnees = _lire_exact(self._reponse.raw, taille)
                    if donnees is None:
                        raise ConnectionError("flux interrompu")
                    m = RE_TITRE.search(donnees.decode("utf-8", "replace"))
                    if not m:
                        continue
                    titre = (m.group(1) or m.group(2) or "").strip()
                    if titre_utilisable(titre, self.nom_station) and titre != dernier:
                        dernier = titre
                        self.rappel(titre)

            except Exception:
                if self._arret.is_set():
                    return
                echecs += 1
                time.sleep(2)
            finally:
                if self._reponse is not None:
                    try:
                        self._reponse.close()
                    except Exception:
                        pass
