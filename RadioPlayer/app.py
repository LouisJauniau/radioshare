#!/usr/bin/env python3
"""
RadioShare — lecteur de radios du monde.

Choisir un pays, une ville ou un genre dans la liste : le lecteur tire une
station au hasard dans la selection et la joue. Le morceau en cours s'affiche
quand la station le publie.

    python app.py

Le catalogue est produit par preparer_donnees.py a partir du projet V0.1.
"""

import json
import random
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

from PyQt5.QtCore import Qt, QObject, QThread, pyqtSignal
from PyQt5.QtWidgets import (QApplication, QComboBox, QFrame, QHBoxLayout,
                             QLabel, QLineEdit, QListWidget, QListWidgetItem,
                             QMainWindow, QPushButton, QSlider, QVBoxLayout,
                             QWidget)

import chemins
import flux

# Le catalogue est livre avec le programme ; favoris et reglages doivent
# rester inscriptibles, donc a part.
CATALOGUE = chemins.ressource("donnees/stations.json")
FAVORIS = chemins.fichier_utilisateur("favoris.json")
EXCLUES = chemins.fichier_utilisateur("exclues.json")
REGLAGES = chemins.fichier_utilisateur("reglages.json")

try:
    import vlc
except (ImportError, OSError) as erreur:      # libvlc absente du systeme
    vlc = None
    ERREUR_VLC = str(erreur)
else:
    ERREUR_VLC = None

STYLE = """
QMainWindow, QWidget { background: #16161a; color: #e8e8ea; }
QLabel#titreStation { font-size: 21px; font-weight: 600; color: #ffffff; }
QLabel#lieuStation  { font-size: 13px; color: #9a9aa2; }
QLabel#morceau      { font-size: 16px; color: #7ee0b8; }
QLabel#etat         { font-size: 12px; color: #9a9aa2; }
QLabel#section      { font-size: 11px; color: #8a8a94; letter-spacing: 1px; }
QListWidget { background: #1e1e24; border: 1px solid #2c2c34;
              border-radius: 6px; padding: 4px; outline: none; }
QListWidget::item { padding: 7px 8px; border-radius: 4px; }
QListWidget::item:selected { background: #2f6f57; color: #ffffff; }
QListWidget::item:hover { background: #26262e; }
QLineEdit, QComboBox { background: #1e1e24; border: 1px solid #2c2c34;
                       border-radius: 6px; padding: 7px; color: #e8e8ea; }
QPushButton { background: #2f6f57; border: none; border-radius: 6px;
              padding: 10px 16px; color: #ffffff; font-weight: 600; }
QPushButton:hover { background: #3a8a6b; }
QPushButton:disabled { background: #2c2c34; color: #6a6a72; }
QPushButton#secondaire { background: #2c2c34; }
QPushButton#secondaire:hover { background: #3a3a44; }
QFrame#carte { background: #1e1e24; border: 1px solid #2c2c34;
               border-radius: 8px; }
QPushButton#sourdine { background: transparent; border: 1px solid #2c2c34;
                       border-radius: 6px; padding: 6px 10px;
                       color: #cfcfd6; font-weight: 500; min-width: 74px; }
QPushButton#sourdine:hover { background: #26262e; }
QLabel#valeurVolume { color: #9a9aa2; font-size: 12px; min-width: 38px; }
QSlider::groove:horizontal { height: 6px; background: #2c2c34;
                             border-radius: 3px; }
QSlider::sub-page:horizontal { background: #2f6f57; border-radius: 3px; }
QSlider::handle:horizontal { background: #e8e8ea; width: 15px; height: 15px;
                             margin: -5px 0; border-radius: 8px; }
QSlider::handle:horizontal:hover { background: #ffffff; }
QSlider:disabled::sub-page:horizontal { background: #3a3a44; }
"""


class BarreVolume(QSlider):
    """
    Curseur de volume plus docile que celui de Qt.

    Par defaut, un clic dans la rainure avance d'un cran au lieu d'aller a
    l'endroit clique, ce qui oblige a attraper la poignee. Ici le clic
    positionne directement, le glisser suit, et la molette regle par pas de 5.
    """

    def __init__(self):
        super().__init__(Qt.Horizontal)
        self.setRange(0, 100)
        self.setSingleStep(5)
        self.setPageStep(10)

    def _valeur_au_point(self, x):
        largeur = max(self.width(), 1)
        return round(self.minimum()
                     + (self.maximum() - self.minimum()) * x / largeur)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.setValue(self._valeur_au_point(ev.x()))
            ev.accept()
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if ev.buttons() & Qt.LeftButton:
            self.setValue(self._valeur_au_point(ev.x()))
            ev.accept()
        super().mouseMoveEvent(ev)

    def wheelEvent(self, ev):
        cran = 5 if ev.angleDelta().y() > 0 else -5
        self.setValue(max(0, min(100, self.value() + cran)))
        ev.accept()


def normaliser(texte):
    """
    Repli sans accent ni casse, pour que "radio tropical" trouve
    "Rádio Tropical" : les noms de stations sont majoritairement accentues.
    """
    if not texte:
        return ""
    d = unicodedata.normalize("NFKD", texte)
    return "".join(c for c in d if not unicodedata.combining(c)).casefold().strip()


class Resolveur(QThread):
    """
    Resout l'URL du flux hors du fil graphique.

    La redirection 302 de Radio Garden prend parfois plusieurs secondes ;
    la faire dans le fil principal figerait la fenetre a chaque changement
    de station.
    """

    resolu = pyqtSignal(dict, str)
    echoue = pyqtSignal(dict)

    def __init__(self, station):
        super().__init__()
        self.station = station

    def run(self):
        url = flux.resoudre(self.station["id"])
        if url:
            self.resolu.emit(self.station, url)
        else:
            self.echoue.emit(self.station)


class PontTitres(QObject):
    """Fait passer les titres du fil de lecture ICY vers le fil graphique."""

    nouveau = pyqtSignal(str)
    erreur = pyqtSignal(str)


class Fenetre(QMainWindow):

    def __init__(self, stations):
        super().__init__()
        self.stations = stations
        self.par_id = {s["id"]: s for s in stations}
        self.favoris = self._charger_favoris()
        self.exclues = self._charger_exclues()
        self.niveau = self._charger_reglages()
        self.resultats = []
        self.groupes = {}
        self.selection = []
        self.origine = None             # d'ou vient le tirage courant
        self.station = None
        self.suiveur = None
        self.resolveur = None
        self.url_courante = None
        self.en_pause = False

        self.vlc = vlc.Instance("--no-video", "--quiet", "--network-caching=3000")
        self.lecteur = self.vlc.media_player_new()
        self.pont = PontTitres()
        self.pont.nouveau.connect(self.afficher_morceau)
        self.pont.erreur.connect(self.afficher_avertissement)

        self.setWindowTitle("RadioShare — Lecteur")
        self.resize(1000, 620)
        self._construire()
        self.changer_mode("Pays")

    # -------------------------------------------------------------- volume

    def _charger_reglages(self):
        p = REGLAGES
        if not p.exists():
            return 80
        try:
            niveau = json.loads(p.read_text(encoding="utf-8")).get("volume", 80)
        except (json.JSONDecodeError, OSError):
            return 80
        return max(0, min(100, int(niveau)))

    def _sauver_reglages(self):
        p = REGLAGES
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            p.write_text(json.dumps({"volume": self.volume.value()}),
                         encoding="utf-8")
        except OSError:
            pass                        # un reglage perdu ne doit rien casser

    def regler_volume(self, niveau):
        self.lecteur.audio_set_volume(niveau)
        self.valeur_volume.setText("%d %%" % niveau)
        # Bouger le curseur sort de la sourdine : c'est le geste naturel
        # pour reprendre le son, plus direct que de rechercher le bouton.
        self.b_sourdine.setText("Muet" if niveau == 0 else "Son")

    def basculer_sourdine(self):
        if self.volume.value() > 0:
            self.niveau_avant_sourdine = self.volume.value()
            self.volume.setValue(0)
        else:
            self.volume.setValue(getattr(self, "niveau_avant_sourdine", 80) or 80)
        self._sauver_reglages()

    # ------------------------------------------------------------ exclusions

    def _charger_exclues(self):
        p = EXCLUES
        if not p.exists():
            return set()
        try:
            return {i for i in json.loads(p.read_text(encoding="utf-8"))
                    if i in self.par_id}
        except (json.JSONDecodeError, OSError, TypeError):
            return set()

    def _sauver_exclues(self):
        try:
            EXCLUES.write_text(json.dumps(sorted(self.exclues), ensure_ascii=False),
                               encoding="utf-8")
        except OSError:
            pass

    def stations_utilisables(self):
        """
        Catalogue prive des stations ecartees.

        Point de passage unique : tous les regroupements et tous les tirages
        s'appuient dessus, pour qu'une station ecartee le reste partout et
        non seulement dans le mode ou l'on a clique.
        """
        if not self.exclues:
            return self.stations
        return [s for s in self.stations if s["id"] not in self.exclues]

    def basculer_exclusion(self):
        """
        Ecarte la station en cours, ou la reintegre.

        Ecarter revient a dire "pas celle-ci" : on enchaine donc aussitot sur
        une autre station, plutot que de laisser jouer celle qu'on refuse.
        """
        if not self.station:
            return
        cid = self.station["id"]
        if cid in self.exclues:
            self.exclues.discard(cid)
            self._sauver_exclues()
            self._maj_boutons_station()
            self.changer_mode(self.mode.currentText())
            return

        self.exclues.add(cid)
        # Une station ecartee n'a plus rien a faire dans les favoris.
        if cid in self.favoris:
            self.favoris.remove(cid)
            self._sauver_favoris()
        self._sauver_exclues()

        self.selection = [s for s in self.selection if s["id"] not in self.exclues]
        self.changer_mode(self.mode.currentText())
        self._maj_boutons_station()
        if self.selection:
            self.tirer_station()
        else:
            self.arreter()
            self.etat.setText("station ecartee, plus rien dans cette selection")

    def _maj_boutons_station(self):
        actif = self.station is not None
        self.b_favori.setEnabled(actif)
        self.b_ecarter.setEnabled(actif)
        ecartee = actif and self.station["id"] in self.exclues
        self.b_ecarter.setText("Reintegrer" if ecartee else "Pas interesse")
        if actif and self.station["id"] in self.favoris:
            self.b_favori.setText("Retirer des favoris")
        else:
            self.b_favori.setText("Favori")

    # ------------------------------------------------------------- favoris

    def _charger_favoris(self):
        """
        Favoris stockes par identifiant, pas par nom.

        Un identifiant Radio Garden est stable, alors qu'une station peut
        etre renommee ou exister en plusieurs exemplaires homonymes.
        """
        p = FAVORIS
        if not p.exists():
            return []
        try:
            ids = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        # Un identifiant absent du catalogue est ignore sans bruit : cela
        # arrive apres une regeneration ou nettoyage des donnees.
        return [i for i in ids if i in self.par_id]

    def _sauver_favoris(self):
        p = FAVORIS
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.favoris, ensure_ascii=False), encoding="utf-8")

    def basculer_favori(self):
        if not self.station:
            return
        cid = self.station["id"]
        if cid in self.favoris:
            self.favoris.remove(cid)
        else:
            self.favoris.append(cid)
            # Mettre en favori annule un ecartement precedent.
            if cid in self.exclues:
                self.exclues.discard(cid)
                self._sauver_exclues()
        self._sauver_favoris()
        self._maj_boutons_station()
        if self.mode.currentText() == "Favoris":
            self.appliquer_filtre(self.filtre.text())

    # ------------------------------------------------------------ interface

    def _construire(self):
        gauche = QVBoxLayout()
        gauche.setSpacing(8)

        self.b_monde = QPushButton("Au hasard dans le monde")
        self.b_monde.clicked.connect(self.tirer_partout)
        gauche.addWidget(self.b_monde)

        self.mode = QComboBox()
        self.mode.addItems(["Pays", "Villes", "Genres", "Stations",
                            "Favoris", "Ecartees"])
        self.mode.currentTextChanged.connect(self.changer_mode)

        self.filtre = QLineEdit()
        self.filtre.setPlaceholderText("Filtrer...")
        self.filtre.textChanged.connect(self.appliquer_filtre)

        self.liste = QListWidget()
        self.liste.itemClicked.connect(self.choisir_groupe)

        gauche.addWidget(self.mode)
        gauche.addWidget(self.filtre)
        gauche.addWidget(self.liste, 1)

        cadre = QFrame()
        cadre.setObjectName("carte")
        droite = QVBoxLayout(cadre)
        droite.setContentsMargins(22, 22, 22, 22)
        droite.setSpacing(10)

        self.titre = QLabel("Choisis un pays, une ville ou un genre")
        self.titre.setObjectName("titreStation")
        self.titre.setWordWrap(True)
        self.lieu = QLabel("")
        self.lieu.setObjectName("lieuStation")
        self.morceau = QLabel("")
        self.morceau.setObjectName("morceau")
        self.morceau.setWordWrap(True)
        self.etat = QLabel("")
        self.etat.setObjectName("etat")

        boutons = QHBoxLayout()
        self.b_favori = QPushButton("Favori")
        self.b_favori.setObjectName("secondaire")
        self.b_favori.clicked.connect(self.basculer_favori)
        self.b_favori.setEnabled(False)
        self.b_ecarter = QPushButton("Pas interesse")
        self.b_ecarter.setObjectName("secondaire")
        self.b_ecarter.clicked.connect(self.basculer_exclusion)
        self.b_ecarter.setEnabled(False)
        self.b_pause = QPushButton("Pause")
        self.b_pause.clicked.connect(self.basculer_pause)
        self.b_pause.setEnabled(False)
        self.b_autre = QPushButton("Une autre station")
        self.b_autre.setObjectName("secondaire")
        self.b_autre.clicked.connect(self.tirer_station)
        self.b_autre.setEnabled(False)
        self.b_stop = QPushButton("Arreter")
        self.b_stop.setObjectName("secondaire")
        self.b_stop.clicked.connect(self.arreter)
        self.b_stop.setEnabled(False)
        boutons.addWidget(self.b_pause)
        boutons.addWidget(self.b_autre)
        boutons.addWidget(self.b_favori)
        boutons.addWidget(self.b_ecarter)
        boutons.addWidget(self.b_stop)
        boutons.addStretch()

        vol = QHBoxLayout()
        vol.setSpacing(10)
        self.b_sourdine = QPushButton("Son")
        self.b_sourdine.setObjectName("sourdine")
        self.b_sourdine.clicked.connect(self.basculer_sourdine)

        self.volume = BarreVolume()
        self.volume.setValue(self.niveau)
        self.volume.valueChanged.connect(self.regler_volume)
        self.volume.sliderReleased.connect(self._sauver_reglages)

        self.valeur_volume = QLabel("%d %%" % self.niveau)
        self.valeur_volume.setObjectName("valeurVolume")
        self.valeur_volume.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        vol.addWidget(self.b_sourdine)
        vol.addWidget(self.volume, 1)
        vol.addWidget(self.valeur_volume)
        self.regler_volume(self.niveau)

        histo = QLabel("MORCEAUX ENTENDUS")
        histo.setObjectName("section")
        self.historique = QListWidget()

        droite.addWidget(self.titre)
        droite.addWidget(self.lieu)
        droite.addSpacing(6)
        droite.addWidget(self.morceau)
        droite.addWidget(self.etat)
        droite.addSpacing(10)
        droite.addLayout(boutons)
        droite.addLayout(vol)
        droite.addSpacing(10)
        droite.addWidget(histo)
        droite.addWidget(self.historique, 1)

        principal = QHBoxLayout()
        principal.setContentsMargins(14, 14, 14, 14)
        principal.setSpacing(14)
        conteneur_gauche = QWidget()
        conteneur_gauche.setLayout(gauche)
        conteneur_gauche.setFixedWidth(330)
        principal.addWidget(conteneur_gauche)
        principal.addWidget(cadre, 1)

        centre = QWidget()
        centre.setLayout(principal)
        self.setCentralWidget(centre)

    # -------------------------------------------------------------- groupes

    def changer_mode(self, mode):
        if mode in ("Stations", "Favoris", "Ecartees"):
            # Pas de regroupement : la liste montre les stations elles-memes.
            self.groupes = {}
            self.filtre.setPlaceholderText(
                {"Stations": "Nom de station...",
                 "Favoris": "Filtrer les favoris...",
                 "Ecartees": "Filtrer les stations ecartees..."}[mode])
            self.appliquer_filtre(self.filtre.text())
            return

        self.filtre.setPlaceholderText("Filtrer...")
        groupes = defaultdict(list)
        utilisables = self.stations_utilisables()
        if mode == "Pays":
            for s in utilisables:
                groupes[s["pays"]].append(s)
        elif mode == "Villes":
            for s in utilisables:
                groupes["%s, %s" % (s["ville"], s["pays"])].append(s)
        else:
            for s in utilisables:
                for g in s["genres"]:
                    groupes[g].append(s)

        self.groupes = dict(groupes)
        self.appliquer_filtre(self.filtre.text())

    def appliquer_filtre(self, texte):
        texte = normaliser(texte)
        mode = self.mode.currentText()
        if mode == "Stations":
            self._lister_stations(texte)
            return
        if mode == "Favoris":
            self._lister_favoris(texte)
            return
        if mode == "Ecartees":
            self._lister_ecartees(texte)
            return

        noms = [n for n in self.groupes if texte in normaliser(n)]
        # Les plus fournies d'abord : 12 000 villes triees alphabetiquement
        # noieraient ce que l'on cherche en general.
        noms.sort(key=lambda n: (-len(self.groupes[n]), n.casefold()))

        self.liste.clear()
        for nom in noms[:600]:
            item = QListWidgetItem("%s   -   %d" % (nom, len(self.groupes[nom])))
            item.setData(Qt.UserRole, nom)
            self.liste.addItem(item)

    def _lister_stations(self, texte):
        """
        Liste les stations dont le nom contient le texte cherche.

        On exige deux caracteres : sur 37 000 stations, une seule lettre
        renvoie surtout du bruit et rend la liste illisible.
        """
        self.liste.clear()
        self.resultats = []
        if len(texte) < 2:
            attente = QListWidgetItem("Tape au moins deux lettres")
            attente.setFlags(Qt.NoItemFlags)
            self.liste.addItem(attente)
            return

        self.resultats = [s for s in self.stations_utilisables()
                          if texte in normaliser(s["nom"])]
        for s in self.resultats[:600]:
            item = QListWidgetItem("%s   -   %s, %s"
                                   % (s["nom"], s["ville"], s["pays"]))
            item.setData(Qt.UserRole, s)
            self.liste.addItem(item)

        if not self.resultats:
            vide = QListWidgetItem("Aucune station de ce nom")
            vide.setFlags(Qt.NoItemFlags)
            self.liste.addItem(vide)

    def _lister_favoris(self, texte):
        """Les favoris, dans l'ordre ou ils ont ete ajoutes."""
        self.liste.clear()
        self.resultats = [self.par_id[i] for i in self.favoris
                          if i in self.par_id
                          and (not texte or texte in normaliser(self.par_id[i]["nom"]))]

        if not self.resultats:
            message = ("Aucun favori pour l'instant : lance une station et "
                       "clique sur Favori" if not self.favoris
                       else "Aucun favori de ce nom")
            vide = QListWidgetItem(message)
            vide.setFlags(Qt.NoItemFlags)
            self.liste.addItem(vide)
            return

        for s in self.resultats:
            item = QListWidgetItem("%s   -   %s, %s"
                                   % (s["nom"], s["ville"], s["pays"]))
            item.setData(Qt.UserRole, s)
            self.liste.addItem(item)

    def _lister_ecartees(self, texte):
        """
        Les stations mises de cote, pour pouvoir revenir sur sa decision.

        Sans cette vue, ecarter serait irreversible : la station disparait
        des tirages et de la recherche, donc plus rien ne permettrait de la
        retrouver pour la reintegrer.
        """
        self.liste.clear()
        self.resultats = [self.par_id[i] for i in sorted(self.exclues)
                          if i in self.par_id
                          and (not texte or texte in normaliser(self.par_id[i]["nom"]))]

        if not self.resultats:
            message = ("Aucune station ecartee" if not self.exclues
                       else "Aucune station ecartee de ce nom")
            vide = QListWidgetItem(message)
            vide.setFlags(Qt.NoItemFlags)
            self.liste.addItem(vide)
            return

        for s in self.resultats:
            item = QListWidgetItem("%s   -   %s, %s"
                                   % (s["nom"], s["ville"], s["pays"]))
            item.setData(Qt.UserRole, s)
            self.liste.addItem(item)

    def choisir_groupe(self, item):
        donnee = item.data(Qt.UserRole)
        if donnee is None:
            return                      # ligne d'information, non cliquable

        # En mode Stations la donnee est la station elle-meme : on la joue
        # telle quelle. "Une autre station" continuera alors de piocher
        # parmi les resultats de la recherche.
        if isinstance(donnee, dict):
            self.selection = list(self.resultats)
            if self.mode.currentText() == "Favoris":
                self.origine = "les favoris"
            elif self.mode.currentText() == "Ecartees":
                self.origine = "les stations ecartees"
            else:
                self.origine = 'la recherche "%s"' % self.filtre.text().strip()
            self.b_autre.setEnabled(len(self.selection) > 1)
            self.jouer(donnee)
            return

        self.selection = list(self.groupes.get(donnee, []))
        self.origine = donnee
        self.b_autre.setEnabled(bool(self.selection))
        self.tirer_station()

    def tirer_partout(self):
        """
        Tire parmi tout le catalogue, sans passer par un groupe.

        La selection courante devient le catalogue entier : "Une autre
        station" continue donc de piocher dans le monde entier tant qu'aucun
        pays, ville ou genre n'est choisi ensuite.
        """
        self.selection = self.stations_utilisables()
        self.origine = "le monde entier"
        self.liste.clearSelection()
        self.b_autre.setEnabled(True)
        self.tirer_station()

    # -------------------------------------------------------------- lecture

    def tirer_station(self):
        if not self.selection:
            return
        restantes = [s for s in self.selection if s is not self.station]
        if not restantes:
            restantes = self.selection
        self.jouer(random.choice(restantes))

    def jouer(self, station):
        """Joue une station precise. Le tirage au sort passe aussi par ici."""
        self.station = station
        self._maj_boutons_station()

        self.titre.setText(self.station["nom"] or "sans nom")
        self.lieu.setText("%s, %s" % (self.station["ville"], self.station["pays"]))
        self.morceau.setText("")
        self.etat.setText("connexion au flux...")
        self.b_autre.setEnabled(False)

        self.arreter_suiveur()
        self.resolveur = Resolveur(self.station)
        self.resolveur.resolu.connect(self.demarrer)
        self.resolveur.echoue.connect(self.echec)
        self.resolveur.start()

    def demarrer(self, station, url):
        if station is not self.station:
            return                      # l'utilisateur a change entre-temps
        self.url_courante = url
        self._lancer(url, station)

    def _lancer(self, url, station):
        """Ouvre le flux et demarre le suivi des titres."""
        self.lecteur.set_media(self.vlc.media_new(url))
        self.lecteur.play()
        self.en_pause = False
        self.b_pause.setText("Pause")
        self.b_pause.setEnabled(True)
        self.b_stop.setEnabled(True)
        self.b_autre.setEnabled(True)
        self._afficher_etat(station)

        self.arreter_suiveur()
        self.suiveur = flux.SuiveurTitres(
            url,
            lambda t: self.pont.nouveau.emit(t),
            station["nom"],
            lambda m: self.pont.erreur.emit(m),
        )
        self.suiveur.start()

    def basculer_pause(self):
        """
        Coupe ou reprend l'ecoute.

        Sur un flux en direct, une vraie pause ferait deriver la lecture
        derriere l'antenne : au bout de quelques minutes on entendrait un
        morceau different de celui affiche. La reprise se reconnecte donc
        au direct plutot que de repartir du tampon.
        """
        if not self.station or not self.url_courante:
            return
        if self.en_pause:
            self._lancer(self.url_courante, self.station)
            return
        self.lecteur.stop()
        self.arreter_suiveur()
        self.en_pause = True
        self.b_pause.setText("Reprendre")
        self.etat.setText("en pause   -   la reprise repartira du direct")

    def _afficher_etat(self, station):
        # Rappeler la source du tirage : sans cela, apres un clic sur "Au
        # hasard dans le monde", plus rien n'indique dans quel ensemble
        # "Une autre station" va piocher.
        parties = ["en lecture"]
        if self.origine:
            parties.append("tire dans %s (%d stations)"
                           % (self.origine, len(self.selection)))
        if not station["titres"]:
            parties.append("ne publie pas ses titres")
        self.etat.setText("   -   ".join(parties))

    def echec(self, station):
        if station is not self.station:
            return
        self.etat.setText("flux injoignable, nouveau tirage...")
        # Une station morte ne doit pas bloquer la decouverte : on la retire
        # de la selection courante et on retire aussitot.
        self.selection = [s for s in self.selection if s is not station]
        self.b_autre.setEnabled(bool(self.selection))
        if self.selection:
            self.tirer_station()

    def afficher_morceau(self, titre):
        self.morceau.setText(titre)
        nom = self.station["nom"] if self.station else ""
        self.historique.insertItem(0, "%s   -   %s" % (titre, nom))
        if self.historique.count() > 200:
            self.historique.takeItem(self.historique.count() - 1)

    def afficher_avertissement(self, message):
        if not self.morceau.text():
            self.morceau.setText("- %s -" % message)

    def arreter_suiveur(self):
        if self.suiveur is not None:
            self.suiveur.stop()
            self.suiveur = None

    def arreter(self):
        self.lecteur.stop()
        self.arreter_suiveur()
        self.en_pause = False
        self.etat.setText("arrete")
        self.morceau.setText("")
        self.b_stop.setEnabled(False)
        self.b_pause.setText("Pause")
        self.b_pause.setEnabled(False)

    def closeEvent(self, ev):
        self._sauver_reglages()
        self.arreter_suiveur()
        self.lecteur.stop()
        super().closeEvent(ev)


def verifier_vlc():
    """
    VLC doit etre installe : python-vlc n'est qu'une liaison vers libvlc.

    Sans ce controle, la fenetre s'ouvrirait et resterait muette sans que
    rien n'explique pourquoi.
    """
    if vlc is not None:
        return
    sys.exit(
        "VLC est introuvable sur cette machine.\n"
        "Ce lecteur s'appuie sur VLC pour decoder les flux radio.\n"
        "Installer VLC 64 bits depuis https://www.videolan.org, puis relancer.\n"
        "Detail technique : " + str(ERREUR_VLC))


def main():
    verifier_vlc()
    if not CATALOGUE.exists():
        sys.exit("catalogue introuvable : " + str(CATALOGUE)
                 + "\nlancer d'abord : python preparer_donnees.py")
    stations = json.loads(CATALOGUE.read_text(encoding="utf-8"))

    # Recupere les favoris laisses par la version lancee depuis les sources.
    chemins.reprendre_anciennes_donnees(["favoris.json", "reglages.json"])

    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    fenetre = Fenetre(stations)
    fenetre.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
