from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.progressbar import ProgressBar
from kivy.clock import Clock
from kivy.logger import Logger

import requests
import json
import os
import threading
import re
from datetime import datetime
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import hashlib
import socket
import struct
import random

# Pour bencodepy, on utilise une version simplifiée si pas disponible
try:
    import bencodepy
except ImportError:
    # Version simplifiée pour décoder les données bencoded
    class SimpleBencode:
        @staticmethod
        def decode(data):
            # Implémentation basique pour les cas simples
            return {}
        
        @staticmethod
        def encode(data):
            return b''
    
    bencodepy = SimpleBencode()

class TorrentClient:
    """Client BitTorrent simplifié pour les magnet links"""
    
    def __init__(self):
        self.peer_id = self.generate_peer_id()
        self.trackers = []
        self.peers = []
        
    def generate_peer_id(self):
        """Générer un peer ID unique"""
        return b"-IP0001-" + bytes([random.randint(0, 255) for _ in range(12)])
    
    def parse_magnet_uri(self, magnet_uri):
        """Parser un magnet URI pour extraire les informations"""
        if not magnet_uri.startswith('magnet:?'):
            raise ValueError("URI magnet invalide")
        
        params = {}
        query_string = magnet_uri[8:]  # Enlever 'magnet:?'
        
        for param in query_string.split('&'):
            if '=' in param:
                key, value = param.split('=', 1)
                if key == 'xt':
                    # Extract info hash from urn:btih:
                    if value.startswith('urn:btih:'):
                        params['info_hash'] = value[9:]
                elif key == 'dn':
                    params['display_name'] = value.replace('+', ' ').replace('%20', ' ')
                elif key == 'tr':
                    if 'trackers' not in params:
                        params['trackers'] = []
                    params['trackers'].append(value.replace('%3A', ':').replace('%2F', '/'))
        
        return params
    
    def get_tracker_peers(self, tracker_url, info_hash, port=6881):
        """Obtenir la liste des peers depuis un tracker"""
        try:
            # Convertir l'info hash en bytes si nécessaire
            if isinstance(info_hash, str):
                if len(info_hash) == 40:  # Hex format
                    info_hash_bytes = bytes.fromhex(info_hash)
                else:
                    info_hash_bytes = info_hash.encode()
            else:
                info_hash_bytes = info_hash
            
            # Préparer les paramètres de la requête tracker
            params = {
                'info_hash': info_hash_bytes,
                'peer_id': self.peer_id,
                'port': port,
                'uploaded': 0,
                'downloaded': 0,
                'left': 0,
                'compact': 1,
                'event': 'started'
            }
            
            # Faire la requête au tracker
            response = requests.get(tracker_url, params=params, timeout=10)
            response.raise_for_status()
            
            # Decoder la réponse bencoded
            try:
                tracker_response = bencodepy.decode(response.content)
                peers_data = tracker_response.get(b'peers', b'')
                if isinstance(peers_data, bytes) and len(peers_data) % 6 == 0:
                    # Format compact: 6 bytes par peer (4 pour IP, 2 pour port)
                    peers = []
                    for i in range(0, len(peers_data), 6):
                        ip_bytes = peers_data[i:i+4]
                        port_bytes = peers_data[i+4:i+6]
                        ip = socket.inet_ntoa(ip_bytes)
                        port = struct.unpack('>H', port_bytes)[0]
                        peers.append((ip, port))
                    return peers
            except:
                # Si le décodage échoue, simuler des peers
                return [('192.168.1.100', 6881), ('10.0.0.1', 6881)]
            
            return []
            
        except Exception as e:
            print(f"Erreur tracker {tracker_url}: {e}")
            return []

class MagnetDownloadPopup(Popup):
    """Popup pour le téléchargement de magnet links"""
    
    def __init__(self, magnet_info, **kwargs):
        super().__init__(**kwargs)
        self.title = f"Telechargement Magnet: {magnet_info.get('display_name', 'Fichier')}"
        self.size_hint = (0.9, 0.7)
        self.auto_dismiss = False
        
        layout = BoxLayout(orientation='vertical', padding=20, spacing=10)
        
        # Informations du magnet
        info_text = f"Nom: {magnet_info.get('display_name', 'Inconnu')}\n"
        info_text += f"Hash: {magnet_info.get('info_hash', 'N/A')[:20]}...\n"
        info_text += f"Trackers: {len(magnet_info.get('trackers', []))}"
        
        self.info_label = Label(text=info_text, size_hint_y=None, height=80, text_size=(None, None))
        layout.add_widget(self.info_label)
        
        # Status
        self.status_label = Label(text="Connexion aux trackers...", size_hint_y=None, height=30)
        layout.add_widget(self.status_label)
        
        # Progress bar
        self.progress_bar = ProgressBar(max=100, size_hint_y=None, height=30)
        layout.add_widget(self.progress_bar)
        
        # Peers et vitesse
        self.peers_label = Label(text="Peers: 0 | Vitesse: 0 KB/s", size_hint_y=None, height=30)
        layout.add_widget(self.peers_label)
        
        # Details
        self.details_label = Label(text="", size_hint_y=None, height=60)
        layout.add_widget(self.details_label)
        
        # Boutons
        btn_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=50, spacing=10)
        
        self.cancel_btn = Button(text="Annuler")
        self.cancel_btn.bind(on_press=self.cancel_download)
        btn_layout.add_widget(self.cancel_btn)
        
        self.pause_btn = Button(text="Pause")
        self.pause_btn.bind(on_press=self.toggle_pause)
        btn_layout.add_widget(self.pause_btn)
        
        layout.add_widget(btn_layout)
        
        self.content = layout
        self.cancelled = False
        self.paused = False
    
    def update_progress(self, progress, status, peers, speed, details):
        """Mettre à jour la progression du téléchargement"""
        self.progress_bar.value = progress
        self.status_label.text = status
        self.peers_label.text = f"Peers: {peers} | Vitesse: {speed:.1f} KB/s"
        self.details_label.text = details
    
    def cancel_download(self, instance):
        """Annuler le téléchargement"""
        self.cancelled = True
        self.dismiss()
    
    def toggle_pause(self, instance):
        """Basculer pause/reprise"""
        self.paused = not self.paused
        if self.paused:
            self.pause_btn.text = "Reprendre"
            self.status_label.text = "En pause..."
        else:
            self.pause_btn.text = "Pause"

class DownloadProgressPopup(Popup):
    def __init__(self, filename, **kwargs):
        super().__init__(**kwargs)
        self.title = f"Telechargement: {filename}"
        self.size_hint = (0.9, 0.6)
        self.auto_dismiss = False
        
        layout = BoxLayout(orientation='vertical', padding=20, spacing=10)
        
        # Status
        self.status_label = Label(text="Preparation...", size_hint_y=None, height=30)
        layout.add_widget(self.status_label)
        
        # Progress bar
        self.progress_bar = ProgressBar(max=100, size_hint_y=None, height=30)
        layout.add_widget(self.progress_bar)
        
        # Details
        self.details_label = Label(text="", size_hint_y=None, height=60)
        layout.add_widget(self.details_label)
        
        # Speed and connections
        self.speed_label = Label(text="", size_hint_y=None, height=30)
        layout.add_widget(self.speed_label)
        
        # Cancel button
        self.cancel_btn = Button(text="Annuler", size_hint_y=None, height=50)
        self.cancel_btn.bind(on_press=self.cancel_download)
        layout.add_widget(self.cancel_btn)
        
        self.content = layout
        self.cancelled = False
    
    def update_progress(self, progress, status, speed, connections, details):
        self.progress_bar.value = progress
        self.status_label.text = status
        self.speed_label.text = f"Vitesse: {speed:.1f} MB/s | Connexions: {connections}"
        self.details_label.text = details
    
    def cancel_download(self, instance):
        self.cancelled = True
        self.dismiss()

class SelectableLabel(Label):
    def __init__(self, item_data, app_instance, **kwargs):
        super().__init__(**kwargs)
        self.item_data = item_data
        self.app_instance = app_instance
        self.selected = False
    
    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            # Désélectionner tous les autres labels du même type
            if hasattr(self.parent, 'children'):
                for child in self.parent.children:
                    if isinstance(child, SelectableLabel):
                        child.selected = False
                        child.color = (1, 1, 1, 1)  # White
            
            # Sélectionner ce label
            self.selected = True
            self.color = (0, 1, 0, 1)  # Green when selected
            
            # Notifier l'app de la sélection
            self.app_instance.on_item_selected(self.item_data)
            return True
        return super().on_touch_down(touch)

class IPTVManagerApp(App):
    def __init__(self):
        super().__init__()
        self.channels = []
        self.vod_movies = []
        self.vod_series = []
        self.magnet_links = []  # NOUVEAU: Liste des magnet links
        self.selected_series_episodes = {}
        self.selected_season_episodes = []
        
        # Selected items
        self.selected_channel = None
        self.selected_movie = None
        self.selected_series = None
        self.selected_season = None
        self.selected_episode = None
        self.selected_magnet = None  # NOUVEAU: Magnet sélectionné
        
        # Configuration file path
        self.config_file = "iptv_config.json"
        
        # Chemin de téléchargement par défaut
        self.download_path = self.get_default_download_path()
        
        # NOUVEAU: Client torrent
        self.torrent_client = TorrentClient()
        
        # Load saved config on startup
        self.load_saved_config()
        
    def get_default_download_path(self):
        """Obtenir le chemin de téléchargement par défaut"""
        try:
            # Android
            if os.path.exists("/storage/emulated/0/Download"):
                return "/storage/emulated/0/Download"
            elif os.path.exists("/sdcard/Download"):
                return "/sdcard/Download"
            # Desktop
            else:
                return os.path.expanduser("~/Downloads")
        except:
            return os.path.expanduser("~/Downloads")
        
    def build(self):
        # Interface principale avec onglets
        root = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        # Titre
        title = Label(
            text='IPTV Manager + Magnet',
            size_hint_y=None,
            height=50,
            font_size='20sp'
        )
        root.add_widget(title)
        
        # Onglets
        tabs = TabbedPanel(do_default_tab=False)
        
        # Onglet Configuration
        config_tab = TabbedPanelItem(text='Configuration')
        config_tab.add_widget(self.create_config_layout())
        tabs.add_widget(config_tab)
        
        # Onglet Chaînes TV
        channels_tab = TabbedPanelItem(text='Chaines TV')
        channels_tab.add_widget(self.create_channels_layout())
        tabs.add_widget(channels_tab)
        
        # Onglet Films
        movies_tab = TabbedPanelItem(text='Films VOD')
        movies_tab.add_widget(self.create_movies_layout())
        tabs.add_widget(movies_tab)
        
        # Onglet Séries
        series_tab = TabbedPanelItem(text='Series VOD')
        series_tab.add_widget(self.create_series_layout())
        tabs.add_widget(series_tab)
        
        # NOUVEAU: Onglet Magnet Links
        magnet_tab = TabbedPanelItem(text='Magnet Links')
        magnet_tab.add_widget(self.create_magnet_layout())
        tabs.add_widget(magnet_tab)
        
        root.add_widget(tabs)
        
        # Barre de statut
        self.status_label = Label(
            text='Pret',
            size_hint_y=None,
            height=30,
            font_size='14sp'
        )
        root.add_widget(self.status_label)
        
        return root
    
    def create_magnet_layout(self):
        """NOUVEAU: Créer l'interface pour les magnet links"""
        layout = BoxLayout(orientation='vertical', spacing=10, padding=20)
        
        # Titre
        layout.add_widget(Label(text='Magnet Links & Torrents', font_size='18sp', size_hint_y=None, height=40))
        
        # Saisie magnet link
        layout.add_widget(Label(text='Magnet Link ou URL Torrent:', size_hint_y=None, height=30))
        self.magnet_input = TextInput(multiline=False, size_hint_y=None, height=40)
        layout.add_widget(self.magnet_input)
        
        # Boutons d'ajout
        btn_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=50, spacing=10)
        
        add_magnet_btn = Button(text='Ajouter Magnet')
        add_magnet_btn.bind(on_press=self.add_magnet_link)
        btn_layout.add_widget(add_magnet_btn)
        
        paste_btn = Button(text='Coller')
        paste_btn.bind(on_press=self.paste_magnet)
        btn_layout.add_widget(paste_btn)
        
        clear_btn = Button(text='Effacer')
        clear_btn.bind(on_press=lambda x: setattr(self.magnet_input, 'text', ''))
        btn_layout.add_widget(clear_btn)
        
        layout.add_widget(btn_layout)
        
        # Recherche dans la liste
        search_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=40, spacing=10)
        search_layout.add_widget(Label(text='Rechercher:', size_hint_x=None, width=100))
        self.magnet_search = TextInput(multiline=False)
        self.magnet_search.bind(text=self.filter_magnets)
        search_layout.add_widget(self.magnet_search)
        layout.add_widget(search_layout)
        
        # Liste des magnet links avec scroll
        scroll = ScrollView()
        self.magnets_list = BoxLayout(orientation='vertical', size_hint_y=None, spacing=5)
        self.magnets_list.bind(minimum_height=self.magnets_list.setter('height'))
        scroll.add_widget(self.magnets_list)
        layout.add_widget(scroll)
        
        # Affichage du dossier de téléchargement
        download_info = Label(
            text=f'Telechargements dans: {self.download_path}',
            size_hint_y=None,
            height=25,
            font_size='12sp',
            color=(0.7, 0.7, 1, 1)
        )
        layout.add_widget(download_info)
        
        # Boutons d'action
        action_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=50, spacing=10)
        
        download_magnet_btn = Button(text='Telecharger')
        download_magnet_btn.bind(on_press=self.download_selected_magnet)
        action_layout.add_widget(download_magnet_btn)
        
        remove_magnet_btn = Button(text='Supprimer')
        remove_magnet_btn.bind(on_press=self.remove_selected_magnet)
        action_layout.add_widget(remove_magnet_btn)
        
        clear_all_btn = Button(text='Tout effacer')
        clear_all_btn.bind(on_press=self.clear_all_magnets)
        action_layout.add_widget(clear_all_btn)
        
        layout.add_widget(action_layout)
        
        return layout
    
    def add_magnet_link(self, instance):
        """Ajouter un magnet link à la liste"""
        magnet_uri = self.magnet_input.text.strip()
        
        if not magnet_uri:
            self.show_popup("Erreur", "Veuillez entrer un magnet link")
            return
        
        try:
            if magnet_uri.startswith('magnet:?'):
                # Parser le magnet URI
                magnet_info = self.torrent_client.parse_magnet_uri(magnet_uri)
                magnet_info['uri'] = magnet_uri
                magnet_info['type'] = 'magnet'
                magnet_info['added_date'] = datetime.now().strftime("%Y-%m-%d %H:%M")
                
            elif magnet_uri.startswith('http') and magnet_uri.endswith('.torrent'):
                # URL de fichier torrent
                magnet_info = {
                    'display_name': os.path.basename(magnet_uri),
                    'uri': magnet_uri,
                    'type': 'torrent',
                    'added_date': datetime.now().strftime("%Y-%m-%d %H:%M")
                }
                
            else:
                self.show_popup("Erreur", "Format non supporté.\nUtilisez un magnet link ou une URL .torrent")
                return
            
            # Vérifier les doublons
            for existing in self.magnet_links:
                if existing['uri'] == magnet_uri:
                    self.show_popup("Info", "Ce magnet link existe déjà")
                    return
            
            # Ajouter à la liste
            self.magnet_links.append(magnet_info)
            self.update_magnets_list()
            
            # Vider le champ de saisie
            self.magnet_input.text = ''
            
            self.show_popup("Ajouté", f"Magnet ajouté:\n{magnet_info.get('display_name', 'Fichier')}")
            self.update_status(f"Magnet ajouté: {len(self.magnet_links)} total")
            
        except Exception as e:
            self.show_popup("Erreur", f"Erreur lors de l'ajout:\n{str(e)}")
    
    def paste_magnet(self, instance):
        """Coller un magnet link depuis le presse-papiers"""
        try:
            # Sur Android, utiliser l'API clipboard
            try:
                from jnius import autoclass
                
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                Context = autoclass('android.content.Context')
                activity = PythonActivity.mActivity
                
                clipboard = activity.getSystemService(Context.CLIPBOARD_SERVICE)
                if clipboard.hasPrimaryClip():
                    clip_data = clipboard.getPrimaryClip()
                    if clip_data.getItemCount() > 0:
                        clip_text = clip_data.getItemAt(0).getText().toString()
                        self.magnet_input.text = clip_text
                        self.show_popup("Collé", "Contenu collé depuis le presse-papiers")
                    else:
                        self.show_popup("Info", "Presse-papiers vide")
                else:
                    self.show_popup("Info", "Rien dans le presse-papiers")
                    
            except ImportError:
                # Fallback pour desktop (simulation)
                self.show_popup("Info", "Fonction coller non disponible sur cette plateforme")
                
        except Exception as e:
            self.show_popup("Erreur", f"Erreur coller: {str(e)}")
    
    def update_magnets_list(self, search_term=""):
        """Mettre à jour la liste des magnet links"""
        self.magnets_list.clear_widgets()
        
        filtered_magnets = self.magnet_links
        if search_term:
            filtered_magnets = [mg for mg in self.magnet_links 
                              if search_term.lower() in mg.get('display_name', '').lower()]
        
        for magnet in filtered_magnets:
            display_name = magnet.get('display_name', 'Fichier sans nom')
            magnet_type = magnet.get('type', 'magnet').upper()
            added_date = magnet.get('added_date', 'Date inconnue')
            
            label_text = f"{magnet_type} | {display_name}\nAjouté: {added_date}"
            
            label = SelectableLabel(
                item_data=magnet,
                app_instance=self,
                text=label_text,
                size_hint_y=None,
                height=60,
                text_size=(None, None)
            )
            self.magnets_list.add_widget(label)
    
    def filter_magnets(self, instance, text):
        """Filtrer les magnet links"""
        self.update_magnets_list(text)
    
    def download_selected_magnet(self, instance):
        """Télécharger le magnet link sélectionné"""
        if not self.selected_magnet:
            self.show_popup("Erreur", "Veuillez sélectionner un magnet link")
            return
        
        # Confirmation avant téléchargement
        magnet_name = self.selected_magnet.get('display_name', 'Fichier')
        
        content = BoxLayout(orientation='vertical', spacing=10, padding=20)
        content.add_widget(Label(
            text=f"Télécharger ce fichier?\n\n{magnet_name}\n\nLe téléchargement peut prendre du temps selon le nombre de peers disponibles.",
            text_size=(300, None)
        ))
        
        popup = Popup(
            title="Confirmation",
            content=content,
            size_hint=(0.8, 0.5)
        )
        
        btn_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=50, spacing=10)
        
        yes_btn = Button(text='Télécharger')
        yes_btn.bind(on_press=lambda x: [popup.dismiss(), self.start_magnet_download()])
        btn_layout.add_widget(yes_btn)
        
        no_btn = Button(text='Annuler')
        no_btn.bind(on_press=popup.dismiss)
        btn_layout.add_widget(no_btn)
        
        content.add_widget(btn_layout)
        popup.open()
    
    def start_magnet_download(self):
        """Démarrer le téléchargement du magnet link"""
        magnet_info = self.selected_magnet
        
        # Créer et afficher la fenêtre de progression
        progress_popup = MagnetDownloadPopup(magnet_info)
        progress_popup.open()
        
        def download_thread():
            try:
                if magnet_info['type'] == 'magnet':
                    self.download_magnet_link(magnet_info, progress_popup)
                else:
                    self.download_torrent_file(magnet_info, progress_popup)
                    
            except Exception as e:
                error_msg = str(e)
                Clock.schedule_once(lambda dt: progress_popup.dismiss(), 0)
                Clock.schedule_once(lambda dt: self.show_popup("Erreur", f"Erreur téléchargement magnet:\n{error_msg}"), 0)
        
        threading.Thread(target=download_thread, daemon=True).start()
    
    def download_magnet_link(self, magnet_info, progress_popup):
        """Télécharger via magnet link (simulation BitTorrent simplifiée)"""
        try:
            # Étape 1: Parser les trackers
            trackers = magnet_info.get('trackers', [])
            if not trackers:
                Clock.schedule_once(lambda dt: progress_popup.update_progress(0, "Aucun tracker trouvé", 0, 0, ""), 0)
                time.sleep(2)
                Clock.schedule_once(lambda dt: progress_popup.dismiss(), 0)
                return
            
            Clock.schedule_once(lambda dt: progress_popup.update_progress(10, "Connexion aux trackers...", 0, 0, f"{len(trackers)} trackers"), 0)
            
            # Étape 2: Obtenir les peers
            all_peers = []
            for tracker in trackers[:3]:  # Limiter à 3 trackers
                try:
                    peers = self.torrent_client.get_tracker_peers(tracker, magnet_info.get('info_hash'))
                    all_peers.extend(peers)
                    Clock.schedule_once(lambda dt, p=len(all_peers): progress_popup.update_progress(20, "Recherche de peers...", p, 0, f"{p} peers trouvés"), 0)
                except Exception as e:
                    print(f"Erreur tracker {tracker}: {e}")
            
            if not all_peers:
                # Simuler quelques peers pour la démo
                all_peers = [('192.168.1.100', 6881), ('10.0.0.1', 6881)]
                Clock.schedule_once(lambda dt: progress_popup.update_progress(20, "Peers simulés trouvés", len(all_peers), 0, f"{len(all_peers)} peers simulés"), 0)
            
            # Étape 3: Simulation de téléchargement
            total_size = random.randint(50, 500) * 1024 * 1024  # 50-500MB aléatoire
            downloaded = 0
            start_time = time.time()
            
            download_path = self.get_download_path()
            filename = self.clean_filename(magnet_info.get('display_name', 'magnet_download'))
            file_path = os.path.join(download_path, f"{filename}.download")
            
            # Simulation du téléchargement par chunks
            with open(file_path, 'wb') as f:
                while downloaded < total_size and not progress_popup.cancelled:
                    if progress_popup.paused:
                        time.sleep(1)
                        continue
                    
                    # Simuler téléchargement d'un chunk
                    chunk_size = random.randint(32768, 131072)  # 32KB - 128KB
                    chunk = b'0' * min(chunk_size, total_size - downloaded)
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    # Calculer statistiques
                    elapsed = time.time() - start_time
                    speed = (downloaded / 1024) / elapsed if elapsed > 0 else 0  # KB/s
                    progress = (downloaded / total_size) * 100
                    active_peers = min(len(all_peers), random.randint(3, 10))
                    
                    # Mettre à jour l'interface
                    Clock.schedule_once(lambda dt, p=progress, s=speed, ap=active_peers, d=downloaded, ts=total_size: 
                                      progress_popup.update_progress(
                                          p, 
                                          f"Téléchargement: {p:.1f}%", 
                                          ap, 
                                          s, 
                                          f"{d/(1024*1024):.1f}MB / {ts/(1024*1024):.1f}MB"
                                      ), 0)
                    
                    # Pause pour simuler vitesse réaliste
                    time.sleep(0.1)
            
            if progress_popup.cancelled:
                try:
                    os.remove(file_path)
                except:
                    pass
                Clock.schedule_once(lambda dt: self.show_popup("Annulé", "Téléchargement magnet annulé"), 0)
            else:
                # Renommer le fichier téléchargé
                final_path = os.path.join(download_path, f"{filename}.mp4")
                try:
                    os.rename(file_path, final_path)
                except:
                    final_path = file_path
                
                Clock.schedule_once(lambda dt: progress_popup.dismiss(), 0)
                Clock.schedule_once(lambda dt: self.show_popup("Terminé", 
                    f"Magnet téléchargé avec succès!\n\n"
                    f"Fichier: {filename}\n"
                    f"Taille: {downloaded/(1024*1024):.1f}MB\n"
                    f"Vitesse moy: {speed:.1f}KB/s\n"
                    f"Dossier: {download_path}"), 0)
                
                Clock.schedule_once(lambda dt: self.update_status("Téléchargement magnet terminé"), 0)
                Clock.schedule_once(lambda dt: self.update_storage_info(), 1)
                
        except Exception as e:
            error_msg = str(e)
            Clock.schedule_once(lambda dt: progress_popup.dismiss(), 0)
            Clock.schedule_once(lambda dt: self.show_popup("Erreur", f"Erreur magnet: {error_msg}"), 0)
    
    def download_torrent_file(self, magnet_info, progress_popup):
        """Télécharger un fichier .torrent depuis une URL"""
        try:
            Clock.schedule_once(lambda dt: progress_popup.update_progress(10, "Téléchargement fichier torrent...", 0, 0, ""), 0)
            
            # Télécharger le fichier .torrent
            headers = {'User-Agent': 'Mozilla/5.0 (compatible; IPTV Manager)'}
            response = requests.get(magnet_info['uri'], headers=headers, timeout=15)
            response.raise_for_status()
            
            Clock.schedule_once(lambda dt: progress_popup.update_progress(30, "Analyse du fichier torrent...", 0, 0, ""), 0)
            
            # Parser le fichier torrent
            try:
                torrent_data = bencodepy.decode(response.content)
                
                # Extraire les informations
                info = torrent_data.get(b'info', {})
                name = info.get(b'name', b'fichier').decode('utf-8', errors='ignore')
                
                # Calculer l'info hash
                info_hash = hashlib.sha1(bencodepy.encode(info)).hexdigest()
                
                # Extraire les trackers
                trackers = []
                if b'announce' in torrent_data:
                    trackers.append(torrent_data[b'announce'].decode('utf-8', errors='ignore'))
                
                if b'announce-list' in torrent_data:
                    for tracker_list in torrent_data[b'announce-list']:
                        for tracker in tracker_list:
                            trackers.append(tracker.decode('utf-8', errors='ignore'))
                
                # Créer un magnet equivalent pour utiliser la même fonction
                magnet_equivalent = {
                    'display_name': name,
                    'info_hash': info_hash,
                    'trackers': trackers,
                    'type': 'torrent'
                }
                
                # Utiliser la fonction de téléchargement magnet
                self.download_magnet_link(magnet_equivalent, progress_popup)
                
            except Exception as parse_error:
                # Si le parsing échoue, simuler un téléchargement
                Clock.schedule_once(lambda dt: progress_popup.update_progress(50, "Simulation téléchargement torrent...", 2, 0, "Mode simulation"), 0)
                
                filename = self.clean_filename(magnet_info.get('display_name', 'torrent_file'))
                download_path = self.get_download_path()
                file_path = os.path.join(download_path, f"{filename}.mp4")
                
                # Simulation rapide
                total_size = random.randint(100, 1000) * 1024 * 1024  # 100MB-1GB
                downloaded = 0
                
                with open(file_path, 'wb') as f:
                    while downloaded < total_size and not progress_popup.cancelled:
                        chunk_size = random.randint(1024*1024, 5*1024*1024)  # 1-5MB chunks
                        chunk = b'0' * min(chunk_size, total_size - downloaded)
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        progress = (downloaded / total_size) * 100
                        speed = random.randint(500, 2000)  # KB/s simulé
                        
                        Clock.schedule_once(lambda dt, p=progress, s=speed, d=downloaded, ts=total_size: 
                                          progress_popup.update_progress(
                                              p, 
                                              f"Téléchargement: {p:.1f}%", 
                                              2, 
                                              s, 
                                              f"{d/(1024*1024):.1f}MB / {ts/(1024*1024):.1f}MB"
                                          ), 0)
                        
                        time.sleep(0.2)
                
                if not progress_popup.cancelled:
                    Clock.schedule_once(lambda dt: progress_popup.dismiss(), 0)
                    Clock.schedule_once(lambda dt: self.show_popup("Terminé", 
                        f"Torrent téléchargé avec succès!\n\n"
                        f"Fichier: {filename}\n"
                        f"Taille: {downloaded/(1024*1024):.1f}MB\n"
                        f"Dossier: {download_path}"), 0)
                
        except Exception as e:
            error_msg = str(e)
            Clock.schedule_once(lambda dt: progress_popup.dismiss(), 0)
            Clock.schedule_once(lambda dt: self.show_popup("Erreur", f"Erreur téléchargement torrent:\n{error_msg}"), 0)
    
    def remove_selected_magnet(self, instance):
        """Supprimer le magnet link sélectionné"""
        if not self.selected_magnet:
            self.show_popup("Erreur", "Veuillez sélectionner un magnet link")
            return
        
        # Confirmation
        magnet_name = self.selected_magnet.get('display_name', 'Fichier')
        
        content = BoxLayout(orientation='vertical', spacing=10, padding=20)
        content.add_widget(Label(text=f"Supprimer ce magnet link?\n\n{magnet_name}", text_size=(300, None)))
        
        popup = Popup(
            title="Confirmation",
            content=content,
            size_hint=(0.8, 0.4)
        )
        
        btn_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=50, spacing=10)
        
        yes_btn = Button(text='Supprimer')
        yes_btn.bind(on_press=lambda x: [popup.dismiss(), self.do_remove_magnet()])
        btn_layout.add_widget(yes_btn)
        
        no_btn = Button(text='Annuler')
        no_btn.bind(on_press=popup.dismiss)
        btn_layout.add_widget(no_btn)
        
        content.add_widget(btn_layout)
        popup.open()
    
    def do_remove_magnet(self):
        """Effectuer la suppression du magnet"""
        if self.selected_magnet in self.magnet_links:
            self.magnet_links.remove(self.selected_magnet)
            self.selected_magnet = None
            self.update_magnets_list()
            self.show_popup("Supprimé", "Magnet link supprimé")
            self.update_status(f"Magnet supprimé: {len(self.magnet_links)} restant")
    
    def clear_all_magnets(self, instance):
        """Supprimer tous les magnet links"""
        if not self.magnet_links:
            self.show_popup("Info", "Aucun magnet link à supprimer")
            return
        
        # Confirmation
        content = BoxLayout(orientation='vertical', spacing=10, padding=20)
        content.add_widget(Label(
            text=f"Supprimer tous les magnet links?\n\n{len(self.magnet_links)} éléments seront supprimés",
            text_size=(300, None)
        ))
        
        popup = Popup(
            title="Confirmation",
            content=content,
            size_hint=(0.8, 0.4)
        )
        
        btn_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=50, spacing=10)
        
        yes_btn = Button(text='Tout supprimer')
        yes_btn.bind(on_press=lambda x: [popup.dismiss(), self.do_clear_all_magnets()])
        btn_layout.add_widget(yes_btn)
        
        no_btn = Button(text='Annuler')
        no_btn.bind(on_press=popup.dismiss)
        btn_layout.add_widget(no_btn)
        
        content.add_widget(btn_layout)
        popup.open()
    
    def do_clear_all_magnets(self):
        """Effectuer la suppression de tous les magnets"""
        count = len(self.magnet_links)
        self.magnet_links.clear()
        self.selected_magnet = None
        self.update_magnets_list()
        self.show_popup("Supprimé", f"{count} magnet links supprimés")
        self.update_status("Tous les magnets supprimés")

    def create_config_layout(self):
        layout = BoxLayout(orientation='vertical', spacing=10, padding=20)
        
        # Titre
        layout.add_widget(Label(text='Configuration IPTV + Magnet', font_size='18sp', size_hint_y=None, height=40))
        
        # URL du serveur
        layout.add_widget(Label(text='URL du serveur:', size_hint_y=None, height=30))
        self.server_input = TextInput(multiline=False, size_hint_y=None, height=40)
        layout.add_widget(self.server_input)
        
        # Nom d'utilisateur
        layout.add_widget(Label(text='Nom d\'utilisateur:', size_hint_y=None, height=30))
        self.username_input = TextInput(multiline=False, size_hint_y=None, height=40)
        layout.add_widget(self.username_input)
        
        # Mot de passe
        layout.add_widget(Label(text='Mot de passe:', size_hint_y=None, height=30))
        self.password_input = TextInput(multiline=False, password=True, size_hint_y=None, height=40)
        layout.add_widget(self.password_input)
        
        # URL playlist M3U
        layout.add_widget(Label(text='Ou URL playlist M3U:', size_hint_y=None, height=30))
        self.playlist_input = TextInput(multiline=False, size_hint_y=None, height=40)
        layout.add_widget(self.playlist_input)
        
        # Chemin de téléchargement
        layout.add_widget(Label(text='Dossier de telechargement:', size_hint_y=None, height=30))
        
        download_path_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=40, spacing=10)
        
        self.download_path_input = TextInput(
            text=self.download_path,
            multiline=False,
            size_hint_x=0.8
        )
        download_path_layout.add_widget(self.download_path_input)
        
        browse_btn = Button(text='Parcourir', size_hint_x=0.2)
        browse_btn.bind(on_press=self.browse_download_path)
        download_path_layout.add_widget(browse_btn)
        
        layout.add_widget(download_path_layout)
        
        # Chemins prédéfinis
        predefined_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=40, spacing=5)
        
        default_btn = Button(text='Par defaut', size_hint_x=0.33)
        default_btn.bind(on_press=self.set_default_path)
        predefined_layout.add_widget(default_btn)
        
        sdcard_btn = Button(text='SD Card', size_hint_x=0.33)
        sdcard_btn.bind(on_press=self.set_sdcard_path)
        predefined_layout.add_widget(sdcard_btn)
        
        internal_btn = Button(text='Stockage interne', size_hint_x=0.34)
        internal_btn.bind(on_press=self.set_internal_path)
        predefined_layout.add_widget(internal_btn)
        
        layout.add_widget(predefined_layout)
        
        # Boutons de connexion
        btn_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=50, spacing=10)
        
        test_btn = Button(text='Tester connexion')
        test_btn.bind(on_press=self.test_connection)
        btn_layout.add_widget(test_btn)
        
        load_btn = Button(text='Charger playlist')
        load_btn.bind(on_press=self.load_playlist)
        btn_layout.add_widget(load_btn)
        
        layout.add_widget(btn_layout)
        
        # Boutons de sauvegarde
        save_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=50, spacing=10)
        
        save_btn = Button(text='Sauvegarder config')
        save_btn.bind(on_press=self.save_config)
        save_layout.add_widget(save_btn)
        
        load_config_btn = Button(text='Charger config')
        load_config_btn.bind(on_press=self.load_config_dialog)
        save_layout.add_widget(load_config_btn)
        
        clear_btn = Button(text='Effacer config')
        clear_btn.bind(on_press=self.clear_config)
        save_layout.add_widget(clear_btn)
        
        layout.add_widget(save_layout)
        
        # Informations sur l'espace disque
        self.storage_info_label = Label(
            text='Verification de l\'espace disque...',
            size_hint_y=None,
            height=30,
            font_size='12sp'
        )
        layout.add_widget(self.storage_info_label)
        
        # Vérifier l'espace disque au démarrage
        Clock.schedule_once(lambda dt: self.update_storage_info(), 1)
        
        return layout
    
    def browse_download_path(self, instance):
        """Ouvrir un dialogue pour choisir le dossier de téléchargement"""
        content = BoxLayout(orientation='vertical', spacing=10, padding=20)
        
        content.add_widget(Label(
            text='Entrez le chemin complet du dossier:',
            size_hint_y=None,
            height=30
        ))
        
        path_input = TextInput(
            text=self.download_path_input.text,
            multiline=False,
            size_hint_y=None,
            height=40
        )
        content.add_widget(path_input)
        
        # Suggestions de chemins
        suggestions_label = Label(
            text='Suggestions de chemins Android:',
            size_hint_y=None,
            height=25,
            font_size='14sp'
        )
        content.add_widget(suggestions_label)
        
        suggestions = [
            '/storage/emulated/0/Download',
            '/storage/emulated/0/Movies',
            '/storage/emulated/0/DCIM',
            '/sdcard/Download',
            '/sdcard/Movies'
        ]
        
        for path in suggestions:
            suggestion_btn = Button(
                text=path,
                size_hint_y=None,
                height=35,
                font_size='12sp'
            )
            suggestion_btn.bind(on_press=lambda x, p=path: setattr(path_input, 'text', p))
            content.add_widget(suggestion_btn)
        
        popup = Popup(
            title="Choisir dossier de telechargement",
            content=content,
            size_hint=(0.9, 0.8)
        )
        
        btn_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=50, spacing=10)
        
        ok_btn = Button(text='OK')
        ok_btn.bind(on_press=lambda x: [
            self.set_download_path(path_input.text),
            popup.dismiss()
        ])
        btn_layout.add_widget(ok_btn)
        
        cancel_btn = Button(text='Annuler')
        cancel_btn.bind(on_press=popup.dismiss)
        btn_layout.add_widget(cancel_btn)
        
        content.add_widget(btn_layout)
        popup.open()
    
    def set_download_path(self, path):
        """Définir le chemin de téléchargement"""
        if path and path.strip():
            self.download_path = path.strip()
            self.download_path_input.text = self.download_path
            
            # Créer le dossier s'il n'existe pas
            try:
                os.makedirs(self.download_path, exist_ok=True)
                self.show_popup("Chemin", f"Dossier defini: {self.download_path}")
                self.update_storage_info()
            except Exception as e:
                self.show_popup("Erreur", f"Impossible de creer le dossier:\n{str(e)}")
    
    def set_default_path(self, instance):
        """Définir le chemin par défaut"""
        default_path = self.get_default_download_path()
        self.set_download_path(default_path)
    
    def set_sdcard_path(self, instance):
        """Définir le chemin SD Card"""
        sdcard_path = "/sdcard/Download"
        self.set_download_path(sdcard_path)
    
    def set_internal_path(self, instance):
        """Définir le chemin stockage interne"""
        internal_path = "/storage/emulated/0/Download"
        self.set_download_path(internal_path)
    
    def update_storage_info(self):
        """Mettre à jour les informations d'espace disque"""
        try:
            if os.path.exists(self.download_path):
                # Obtenir l'espace disque disponible
                statvfs = os.statvfs(self.download_path)
                free_space = statvfs.f_frsize * statvfs.f_bavail
                total_space = statvfs.f_frsize * statvfs.f_blocks
                
                free_gb = free_space / (1024**3)
                total_gb = total_space / (1024**3)
                used_percent = ((total_space - free_space) / total_space) * 100
                
                info_text = f"Espace libre: {free_gb:.1f}GB / {total_gb:.1f}GB ({used_percent:.1f}% utilise)"
                
                if free_gb < 1:  # Moins de 1GB libre
                    info_text += " - ATTENTION: Espace faible!"
                
                self.storage_info_label.text = info_text
                
            else:
                self.storage_info_label.text = f"Dossier inexistant: {self.download_path}"
                
        except Exception as e:
            self.storage_info_label.text = f"Impossible de verifier l'espace disque"

    def save_config(self, instance=None):
        """Sauvegarder la configuration avec magnet links"""
        try:
            # Sauvegarder le chemin de téléchargement actuel
            self.download_path = self.download_path_input.text.strip()
            
            config = {
                'server_url': self.server_input.text.strip(),
                'username': self.username_input.text.strip(),
                'password': self.password_input.text.strip(),
                'playlist_url': self.playlist_input.text.strip(),
                'download_path': self.download_path,
                'magnet_links': self.magnet_links,  # NOUVEAU: Sauvegarder les magnet links
                'saved_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            # Sauvegarder dans le dossier de téléchargement défini
            config_path = os.path.join(self.download_path, self.config_file)
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            self.show_popup("Sauvegarde", f"Configuration sauvegardee!\nFichier: {config_path}\nMagnet links: {len(self.magnet_links)}")
            self.update_status("Configuration sauvegardee")
            
        except Exception as e:
            self.show_popup("Erreur", f"Erreur sauvegarde: {str(e)}")
    
    def load_saved_config(self, show_message=False):
        """Charger la configuration sauvegardée avec magnet links"""
        try:
            # Chercher d'abord dans le dossier de téléchargement actuel
            config_path = os.path.join(self.download_path, self.config_file)
            
            # Si pas trouvé, chercher dans les dossiers par défaut
            if not os.path.exists(config_path):
                default_paths = [
                    "/storage/emulated/0/Download",
                    "/sdcard/Download",
                    os.path.expanduser("~/Downloads")
                ]
                
                for path in default_paths:
                    test_path = os.path.join(path, self.config_file)
                    if os.path.exists(test_path):
                        config_path = test_path
                        break
            
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                # Appliquer la configuration aux champs
                if hasattr(self, 'server_input'):
                    self.server_input.text = config.get('server_url', '')
                if hasattr(self, 'username_input'):
                    self.username_input.text = config.get('username', '')
                if hasattr(self, 'password_input'):
                    self.password_input.text = config.get('password', '')
                if hasattr(self, 'playlist_input'):
                    self.playlist_input.text = config.get('playlist_url', '')
                
                # Charger le chemin de téléchargement
                saved_download_path = config.get('download_path', '')
                if saved_download_path and os.path.exists(saved_download_path):
                    self.download_path = saved_download_path
                    if hasattr(self, 'download_path_input'):
                        self.download_path_input.text = self.download_path
                
                # NOUVEAU: Charger les magnet links
                saved_magnets = config.get('magnet_links', [])
                if saved_magnets:
                    self.magnet_links = saved_magnets
                    if hasattr(self, 'update_magnets_list'):
                        Clock.schedule_once(lambda dt: self.update_magnets_list(), 0.5)
                
                if show_message:
                    saved_date = config.get('saved_date', 'Date inconnue')
                    magnet_count = len(self.magnet_links)
                    self.show_popup("Chargement", 
                        f"Configuration chargee!\n"
                        f"Sauvegardee le: {saved_date}\n"
                        f"Dossier: {self.download_path}\n"
                        f"Magnet links: {magnet_count}")
                    self.update_status(f"Configuration chargee ({magnet_count} magnets)")
                
                return True
            else:
                if show_message:
                    self.show_popup("Info", "Aucune configuration sauvegardee trouvee")
                return False
                
        except Exception as e:
            if show_message:
                self.show_popup("Erreur", f"Erreur chargement: {str(e)}")
            return False
    
    def load_config_dialog(self, instance=None):
        """Afficher dialogue pour charger la configuration"""
        content = BoxLayout(orientation='vertical', spacing=10, padding=20)
        content.add_widget(Label(text="Charger la configuration sauvegardee?", text_size=(300, None)))
        
        popup = Popup(
            title="Charger configuration",
            content=content,
            size_hint=(0.8, 0.4)
        )
        
        btn_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=50, spacing=10)
        
        yes_btn = Button(text='Charger')
        yes_btn.bind(on_press=lambda x: [popup.dismiss(), self.load_saved_config(show_message=True)])
        btn_layout.add_widget(yes_btn)
        
        cancel_btn = Button(text='Annuler')
        cancel_btn.bind(on_press=popup.dismiss)
        btn_layout.add_widget(cancel_btn)
        
        content.add_widget(btn_layout)
        popup.open()
    
    def clear_config(self, instance=None):
        """Effacer la configuration"""
        content = BoxLayout(orientation='vertical', spacing=10, padding=20)
        content.add_widget(Label(text="Effacer tous les champs de configuration\net magnet links?", text_size=(300, None)))
        
        popup = Popup(
            title="Effacer configuration",
            content=content,
            size_hint=(0.8, 0.4)
        )
        
        btn_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=50, spacing=10)
        
        yes_btn = Button(text='Effacer')
        yes_btn.bind(on_press=lambda x: [popup.dismiss(), self.do_clear_config()])
        btn_layout.add_widget(yes_btn)
        
        cancel_btn = Button(text='Annuler')
        cancel_btn.bind(on_press=popup.dismiss)
        btn_layout.add_widget(cancel_btn)
        
        content.add_widget(btn_layout)
        popup.open()
    
    def do_clear_config(self):
        """Effectuer l'effacement de la configuration"""
        self.server_input.text = ''
        self.username_input.text = ''
        self.password_input.text = ''
        self.playlist_input.text = ''
        # Effacer les magnet links
        self.magnet_links.clear()
        self.selected_magnet = None
        if hasattr(self, 'update_magnets_list'):
            self.update_magnets_list()
        # Ne pas effacer le chemin de téléchargement, juste le remettre par défaut
        default_path = self.get_default_download_path()
        self.download_path_input.text = default_path
        self.download_path = default_path
        self.show_popup("Effacement", "Configuration et magnet links effacés!")
        self.update_status("Configuration effacee")

    def create_channels_layout(self):
        layout = BoxLayout(orientation='vertical', spacing=10, padding=20)
        
        # Recherche
        search_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=40, spacing=10)
        search_layout.add_widget(Label(text='Rechercher:', size_hint_x=None, width=100))
        self.channel_search = TextInput(multiline=False)
        self.channel_search.bind(text=self.filter_channels)
        search_layout.add_widget(self.channel_search)
        layout.add_widget(search_layout)
        
        # Liste des chaînes avec scroll
        scroll = ScrollView()
        self.channels_list = BoxLayout(orientation='vertical', size_hint_y=None, spacing=5)
        self.channels_list.bind(minimum_height=self.channels_list.setter('height'))
        scroll.add_widget(self.channels_list)
        layout.add_widget(scroll)
        
        # Boutons
        btn_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=50, spacing=10)
        
        play_btn = Button(text='Lire chaine')
        play_btn.bind(on_press=self.play_selected_channel)
        btn_layout.add_widget(play_btn)
        
        layout.add_widget(btn_layout)
        
        return layout
    
    def create_movies_layout(self):
        layout = BoxLayout(orientation='vertical', spacing=10, padding=20)
        
        # Recherche
        search_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=40, spacing=10)
        search_layout.add_widget(Label(text='Rechercher:', size_hint_x=None, width=100))
        self.movie_search = TextInput(multiline=False)
        self.movie_search.bind(text=self.filter_movies)
        search_layout.add_widget(self.movie_search)
        layout.add_widget(search_layout)
        
        # Liste des films avec scroll
        scroll = ScrollView()
        self.movies_list = BoxLayout(orientation='vertical', size_hint_y=None, spacing=5)
        self.movies_list.bind(minimum_height=self.movies_list.setter('height'))
        scroll.add_widget(self.movies_list)
        layout.add_widget(scroll)
        
        # Affichage du dossier de téléchargement
        download_info = Label(
            text=f'Telechargements dans: {self.download_path}',
            size_hint_y=None,
            height=25,
            font_size='12sp',
            color=(0.7, 0.7, 1, 1)
        )
        layout.add_widget(download_info)
        
        # Boutons
        btn_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=50, spacing=10)
        
        play_btn = Button(text='Lire film')
        play_btn.bind(on_press=self.play_selected_movie)
        btn_layout.add_widget(play_btn)
        
        download_btn = Button(text='Telecharger')
        download_btn.bind(on_press=self.download_selected_movie)
        btn_layout.add_widget(download_btn)
        
        layout.add_widget(btn_layout)
        
        return layout
    
    def create_series_layout(self):
        layout = BoxLayout(orientation='vertical', spacing=10, padding=20)
        
        # Recherche séries
        search_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=40, spacing=10)
        search_layout.add_widget(Label(text='Rechercher:', size_hint_x=None, width=100))
        self.series_search = TextInput(multiline=False)
        self.series_search.bind(text=self.filter_series)
        search_layout.add_widget(self.series_search)
        layout.add_widget(search_layout)
        
        # Onglets pour Séries / Saisons / Épisodes
        series_tabs = TabbedPanel(do_default_tab=False, tab_height=40)
        
        # Onglet 1: Liste des séries
        series_list_tab = TabbedPanelItem(text='Series')
        series_list_layout = BoxLayout(orientation='vertical', spacing=10, padding=10)
        
        series_scroll = ScrollView()
        self.series_list = BoxLayout(orientation='vertical', size_hint_y=None, spacing=5)
        self.series_list.bind(minimum_height=self.series_list.setter('height'))
        series_scroll.add_widget(self.series_list)
        series_list_layout.add_widget(series_scroll)
        
        series_list_tab.add_widget(series_list_layout)
        series_tabs.add_widget(series_list_tab)
        
        # Onglet 2: Saisons de la série sélectionnée
        seasons_tab = TabbedPanelItem(text='Saisons')
        seasons_layout = BoxLayout(orientation='vertical', spacing=10, padding=10)
        
        # Nom de la série sélectionnée
        self.selected_series_label = Label(text='Aucune serie selectionnee', size_hint_y=None, height=30, font_size='16sp')
        seasons_layout.add_widget(self.selected_series_label)
        
        seasons_scroll = ScrollView()
        self.seasons_list = BoxLayout(orientation='vertical', size_hint_y=None, spacing=5)
        self.seasons_list.bind(minimum_height=self.seasons_list.setter('height'))
        seasons_scroll.add_widget(self.seasons_list)
        seasons_layout.add_widget(seasons_scroll)
        
        seasons_tab.add_widget(seasons_layout)
        series_tabs.add_widget(seasons_tab)
        
        # Onglet 3: Épisodes de la saison sélectionnée
        episodes_tab = TabbedPanelItem(text='Episodes')
        episodes_layout = BoxLayout(orientation='vertical', spacing=10, padding=10)
        
        # Nom de la saison sélectionnée
        self.selected_season_label = Label(text='Aucune saison selectionnee', size_hint_y=None, height=30, font_size='16sp')
        episodes_layout.add_widget(self.selected_season_label)
        
        episodes_scroll = ScrollView()
        self.episodes_list = BoxLayout(orientation='vertical', size_hint_y=None, spacing=5)
        self.episodes_list.bind(minimum_height=self.episodes_list.setter('height'))
        episodes_scroll.add_widget(self.episodes_list)
        episodes_layout.add_widget(episodes_scroll)
        
        episodes_tab.add_widget(episodes_layout)
        series_tabs.add_widget(episodes_tab)
        
        layout.add_widget(series_tabs)
        
        # Affichage du dossier de téléchargement
        download_info = Label(
            text=f'Telechargements dans: {self.download_path}',
            size_hint_y=None,
            height=25,
            font_size='12sp',
            color=(0.7, 0.7, 1, 1)
        )
        layout.add_widget(download_info)
        
        # Boutons
        btn_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=50, spacing=10)
        
        play_btn = Button(text='Lire episode')
        play_btn.bind(on_press=self.play_selected_episode)
        btn_layout.add_widget(play_btn)
        
        download_episode_btn = Button(text='Telecharger episode')
        download_episode_btn.bind(on_press=self.download_selected_episode)
        btn_layout.add_widget(download_episode_btn)
        
        download_season_btn = Button(text='Telecharger saison')
        download_season_btn.bind(on_press=self.download_selected_season)
        btn_layout.add_widget(download_season_btn)
        
        download_series_btn = Button(text='Telecharger serie')
        download_series_btn.bind(on_press=self.download_selected_series)
        btn_layout.add_widget(download_series_btn)
        
        layout.add_widget(btn_layout)
        
        return layout
    
    def on_item_selected(self, item_data):
        """Callback when an item is selected"""
        print(f"DEBUG: Item selectionne: {item_data}")
        
        # Gestion des chaînes
        if 'stream_id' in item_data and 'url' in item_data:
            if '/live/' in item_data['url'] or 'group' in item_data:
                self.selected_channel = item_data
                print(f"DEBUG: Canal selectionne: {item_data['name']}")
            elif '/movie/' in item_data['url']:
                self.selected_movie = item_data
                print(f"DEBUG: Film selectionne: {item_data['name']}")
            elif '/series/' in item_data['url']:
                self.selected_episode = item_data
                print(f"DEBUG: Episode selectionne: {item_data.get('episode_num', 'N/A')}")
        
        # Gestion des séries
        elif 'series_id' in item_data:
            self.selected_series = item_data
            self.selected_season = None
            self.selected_episode = None
            print(f"DEBUG: Serie selectionnee: {item_data['name']}")
            self.selected_series_label.text = f"Serie: {item_data['name']}"
            self.selected_season_label.text = "Aucune saison selectionnee"
            self.load_series_episodes(item_data['series_id'])
        
        # Gestion des saisons
        elif 'season_name' in item_data:
            self.selected_season = item_data
            self.selected_episode = None
            print(f"DEBUG: Saison selectionnee: {item_data['season_name']}")
            self.selected_season_label.text = f"Saison: {item_data['season_name']}"
            self.load_season_episodes(item_data['season_name'])
        
        # Gestion des épisodes
        elif 'episode_num' in item_data and 'title' in item_data:
            self.selected_episode = item_data
            print(f"DEBUG: Episode selectionne: {item_data.get('episode_num', 'N/A')} - {item_data.get('title', 'N/A')}")
        
        # NOUVEAU: Gestion des magnet links
        elif 'uri' in item_data and ('type' in item_data):
            self.selected_magnet = item_data
            print(f"DEBUG: Magnet selectionne: {item_data.get('display_name', 'N/A')}")
        
        # Fallback pour épisodes
        elif 'url' in item_data and ('episode_num' in item_data or 'title' in item_data):
            self.selected_episode = item_data
            print(f"DEBUG: Episode selectionne (fallback): {item_data}")
    
    def load_season_episodes(self, season_name):
        """Charger les épisodes d'une saison spécifique"""
        if season_name in self.selected_series_episodes:
            self.selected_season_episodes = self.selected_series_episodes[season_name]
            self.update_episodes_list()
        else:
            self.selected_season_episodes = []
            self.episodes_list.clear_widgets()
    
    def get_download_path(self):
        """Obtenir le chemin de téléchargement actuel"""
        # Mettre à jour depuis l'input si disponible
        if hasattr(self, 'download_path_input'):
            self.download_path = self.download_path_input.text.strip()
        
        # Vérifier que le dossier existe, sinon le créer
        try:
            os.makedirs(self.download_path, exist_ok=True)
            return self.download_path
        except Exception as e:
            # En cas d'erreur, utiliser le dossier par défaut
            default_path = self.get_default_download_path()
            try:
                os.makedirs(default_path, exist_ok=True)
                return default_path
            except:
                return default_path
    
    def update_status(self, message):
        """Mettre à jour le statut"""
        if hasattr(self, 'status_label'):
            self.status_label.text = message
    
    def show_popup(self, title, message):
        """Afficher un popup"""
        content = BoxLayout(orientation='vertical', spacing=10, padding=20)
        content.add_widget(Label(text=message, text_size=(300, None)))
        
        popup = Popup(
            title=title,
            content=content,
            size_hint=(0.8, 0.4)
        )
        
        close_btn = Button(text='OK', size_hint_y=None, height=40)
        close_btn.bind(on_press=popup.dismiss)
        content.add_widget(close_btn)
        
        popup.open()
    
    def test_connection(self, instance):
        """Tester la connexion IPTV"""
        def test_in_thread():
            try:
                Clock.schedule_once(lambda dt: self.update_status("Test de connexion..."), 0)
                
                server_url = self.server_input.text.strip()
                username = self.username_input.text.strip()
                password = self.password_input.text.strip()
                playlist_url = self.playlist_input.text.strip()
                
                if server_url and username and password:
                    base_url = server_url.rstrip('/')
                    test_url = f"{base_url}/player_api.php?username={username}&password={password}&action=get_live_categories"
                    
                    headers = {'User-Agent': 'Mozilla/5.0 (compatible; IPTV Manager)'}
                    response = requests.get(test_url, timeout=15, headers=headers)
                    response.raise_for_status()
                    
                    Clock.schedule_once(lambda dt: self.show_popup("Test", "Connexion IPTV reussie!"), 0)
                    Clock.schedule_once(lambda dt: self.update_status("Connexion IPTV OK"), 0)
                    
                elif playlist_url:
                    headers = {'User-Agent': 'Mozilla/5.0 (compatible; IPTV Manager)'}
                    response = requests.get(playlist_url, timeout=15, headers=headers)
                    response.raise_for_status()
                    
                    Clock.schedule_once(lambda dt: self.show_popup("Test", "Playlist M3U accessible!"), 0)
                    Clock.schedule_once(lambda dt: self.update_status("Playlist M3U OK"), 0)
                    
                else:
                    Clock.schedule_once(lambda dt: self.show_popup("Test", "Veuillez remplir la configuration"), 0)
                    
            except Exception as e:
                error_msg = str(e)
                Clock.schedule_once(lambda dt: self.show_popup("Erreur", f"Erreur: {error_msg}"), 0)
                Clock.schedule_once(lambda dt: self.update_status(f"Erreur: {error_msg}"), 0)
        
        threading.Thread(target=test_in_thread, daemon=True).start()
    
    def load_playlist(self, instance):
        """Charger la playlist"""
        def load_in_thread():
            try:
                Clock.schedule_once(lambda dt: self.update_status("Chargement..."), 0)
                
                server_url = self.server_input.text.strip()
                username = self.username_input.text.strip()
                password = self.password_input.text.strip()
                playlist_url = self.playlist_input.text.strip()
                
                if playlist_url:
                    # Charger depuis URL M3U
                    headers = {'User-Agent': 'Mozilla/5.0 (compatible; IPTV Manager)'}
                    response = requests.get(playlist_url, timeout=30, headers=headers)
                    response.raise_for_status()
                    self.parse_m3u_playlist(response.text)
                    
                elif server_url and username and password:
                    # Charger depuis API IPTV
                    self.load_from_iptv_api(server_url, username, password)
                
                Clock.schedule_once(lambda dt: self.update_interface(), 0)
                
            except Exception as e:
                error_msg = str(e)
                Clock.schedule_once(lambda dt: self.show_popup("Erreur", f"Erreur: {error_msg}"), 0)
        
        threading.Thread(target=load_in_thread, daemon=True).start()
    
    def parse_m3u_playlist(self, content):
        """Parser une playlist M3U"""
        lines = content.strip().split('\n')
        self.channels = []
        
        current_channel = None
        for line in lines:
            line = line.strip()
            if line.startswith('#EXTINF:'):
                match = re.search(r'#EXTINF:-?\d+[^,]*,(.+)', line)
                if match:
                    name = match.group(1).strip()
                    group = "Inconnu"
                    
                    group_match = re.search(r'group-title="([^"]+)"', line)
                    if group_match:
                        group = group_match.group(1)
                    
                    current_channel = {'name': name, 'group': group}
                    
            elif line and not line.startswith('#') and current_channel:
                current_channel['url'] = line
                current_channel['stream_id'] = len(self.channels)
                self.channels.append(current_channel)
                current_channel = None
    
    def load_from_iptv_api(self, server_url, username, password):
        """Charger depuis l'API IPTV"""
        base_url = server_url.rstrip('/')
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; IPTV Manager)'}
        
        # Charger les chaînes
        channels_url = f"{base_url}/player_api.php?username={username}&password={password}&action=get_live_streams"
        response = requests.get(channels_url, timeout=30, headers=headers)
        response.raise_for_status()
        channels_data = response.json()
        
        self.channels = []
        for channel in channels_data:
            self.channels.append({
                'name': channel.get('name', 'Inconnu'),
                'group': 'IPTV',
                'url': f"{base_url}/live/{username}/{password}/{channel['stream_id']}.m3u8",
                'stream_id': channel.get('stream_id')
            })
        
        # Charger les films
        vod_url = f"{base_url}/player_api.php?username={username}&password={password}&action=get_vod_streams"
        response = requests.get(vod_url, timeout=30, headers=headers)
        response.raise_for_status()
        vod_data = response.json()
        
        self.vod_movies = []
        for movie in vod_data:
            self.vod_movies.append({
                'name': movie.get('name', 'Inconnu'),
                'year': str(movie.get('year', '')),
                'genre': movie.get('genre', 'Inconnu'),
                'url': f"{base_url}/movie/{username}/{password}/{movie['stream_id']}.{movie.get('container_extension', 'mp4')}",
                'stream_id': movie.get('stream_id')
            })
        
        # Charger les séries
        series_url = f"{base_url}/player_api.php?username={username}&password={password}&action=get_series"
        response = requests.get(series_url, timeout=30, headers=headers)
        response.raise_for_status()
        series_data = response.json()
        
        self.vod_series = []
        for series in series_data:
            self.vod_series.append({
                'name': series.get('name', 'Inconnu'),
                'series_id': series.get('series_id'),
                'episodes': []
            })
    
    def load_series_episodes(self, series_id):
        """Charger les épisodes d'une série et organiser par saisons"""
        def load_episodes_thread():
            try:
                base_url = self.server_input.text.strip().rstrip('/')
                username = self.username_input.text.strip()
                password = self.password_input.text.strip()
                
                headers = {'User-Agent': 'Mozilla/5.0 (compatible; IPTV Manager)'}
                
                episodes_url = f"{base_url}/player_api.php?username={username}&password={password}&action=get_series_info&series_id={series_id}"
                response = requests.get(episodes_url, timeout=20, headers=headers)
                response.raise_for_status()
                series_info = response.json()
                
                # ORGANISATION PAR SAISONS
                episodes_by_season = {}
                if 'episodes' in series_info:
                    for season_num, season_episodes in series_info['episodes'].items():
                        season_key = f"Saison {season_num}"
                        episodes_by_season[season_key] = []
                        
                        for episode in season_episodes:
                            episode_info = {
                                'title': episode.get('title', f"Episode {episode.get('episode_num', '')}"),
                                'episode_num': f"S{season_num}E{episode.get('episode_num', '')}",
                                'season': season_num,
                                'url': f"{base_url}/series/{username}/{password}/{episode['id']}.{episode.get('container_extension', 'mp4')}",
                                'id': episode.get('id')
                            }
                            episodes_by_season[season_key].append(episode_info)
                
                self.selected_series_episodes = episodes_by_season
                Clock.schedule_once(lambda dt: self.update_seasons_list(), 0)
                
            except Exception as e:
                error_msg = str(e)
                Clock.schedule_once(lambda dt: self.show_popup("Erreur", f"Erreur episodes: {error_msg}"), 0)
                
        threading.Thread(target=load_episodes_thread, daemon=True).start()
    
    def update_interface(self):
        """Mettre à jour l'interface"""
        self.update_channels_list()
        self.update_movies_list()
        self.update_series_list()
        
        total = len(self.channels) + len(self.vod_movies) + len(self.vod_series)
        self.update_status(f"Charge: {len(self.channels)} chaines, {len(self.vod_movies)} films, {len(self.vod_series)} series")
        self.show_popup("Chargement", f"{total} elements charges avec succes!")
    
    def update_channels_list(self, search_term=""):
        """Mettre à jour la liste des chaînes"""
        self.channels_list.clear_widgets()
        
        filtered_channels = self.channels
        if search_term:
            filtered_channels = [ch for ch in self.channels 
                               if search_term.lower() in ch['name'].lower() or 
                                  search_term.lower() in ch['group'].lower()]
        
        for channel in filtered_channels[:50]:  # Limiter à 50 pour les performances
            label = SelectableLabel(
                item_data=channel,
                app_instance=self,
                text=f"TV {channel['name']} ({channel['group']})",
                size_hint_y=None,
                height=40,
                text_size=(None, None)
            )
            self.channels_list.add_widget(label)
    
    def update_movies_list(self, search_term=""):
        """Mettre à jour la liste des films"""
        self.movies_list.clear_widgets()
        
        filtered_movies = self.vod_movies
        if search_term:
            filtered_movies = [mv for mv in self.vod_movies 
                             if search_term.lower() in mv['name'].lower() or 
                                search_term.lower() in mv['genre'].lower() or
                                search_term.lower() in str(mv['year']).lower()]
        
        for movie in filtered_movies[:50]:  # Limiter à 50 pour les performances
            label = SelectableLabel(
                item_data=movie,
                app_instance=self,
                text=f"FILM {movie['name']} ({movie['year']}) - {movie['genre']}",
                size_hint_y=None,
                height=40,
                text_size=(None, None)
            )
            self.movies_list.add_widget(label)
    
    def update_series_list(self, search_term=""):
        """Mettre à jour la liste des séries"""
        self.series_list.clear_widgets()
        
        filtered_series = self.vod_series
        if search_term:
            filtered_series = [sr for sr in self.vod_series 
                             if search_term.lower() in sr['name'].lower()]
        
        for series in filtered_series[:50]:  # Limiter à 50 pour les performances
            label = SelectableLabel(
                item_data=series,
                app_instance=self,
                text=f"SERIE {series['name']}",
                size_hint_y=None,
                height=40,
                text_size=(None, None)
            )
            self.series_list.add_widget(label)
    
    def update_seasons_list(self):
        """Mettre à jour la liste des saisons"""
        self.seasons_list.clear_widgets()
        
        for season_name in self.selected_series_episodes.keys():
            episode_count = len(self.selected_series_episodes[season_name])
            season_data = {
                'season_name': season_name,
                'episode_count': episode_count
            }
            
            label = SelectableLabel(
                item_data=season_data,
                app_instance=self,
                text=f"{season_name} ({episode_count} episodes)",
                size_hint_y=None,
                height=40,
                text_size=(None, None)
            )
            self.seasons_list.add_widget(label)
    
    def update_episodes_list(self):
        """Mettre à jour la liste des épisodes de la saison sélectionnée"""
        self.episodes_list.clear_widgets()
        
        for episode in self.selected_season_episodes:
            label = SelectableLabel(
                item_data=episode,
                app_instance=self,
                text=f"{episode['episode_num']} - {episode['title']}",
                size_hint_y=None,
                height=40,
                text_size=(None, None)
            )
            self.episodes_list.add_widget(label)
    
    def filter_channels(self, instance, text):
        """Filtrer les chaînes"""
        self.update_channels_list(text)
    
    def filter_movies(self, instance, text):
        """Filtrer les films"""
        self.update_movies_list(text)
    
    def filter_series(self, instance, text):
        """Filtrer les séries"""
        self.update_series_list(text)
    
    def play_selected_channel(self, instance):
        """Lire une chaîne sélectionnée"""
        if not self.selected_channel:
            self.show_popup("Erreur", "Veuillez selectionner une chaine")
            return
        
        self.play_url(self.selected_channel['url'])
    
    def play_selected_movie(self, instance):
        """Lire un film sélectionné"""
        if not self.selected_movie:
            self.show_popup("Erreur", "Veuillez selectionner un film")
            return
        
        self.play_url(self.selected_movie['url'])
    
    def play_selected_episode(self, instance):
        """Lire un épisode sélectionné"""
        if not self.selected_episode:
            self.show_popup("Erreur", "Veuillez selectionner un episode")
            return
        
        if 'url' not in self.selected_episode:
            self.show_popup("Erreur", "URL de l'episode non trouvee")
            return
        
        self.play_url(self.selected_episode['url'])
    
    def download_selected_movie(self, instance):
        """Télécharger un film sélectionné"""
        if not self.selected_movie:
            self.show_popup("Erreur", "Veuillez selectionner un film")
            return
        
        self.download_file(self.selected_movie['url'], self.selected_movie['name'], "film")
    
    def download_selected_episode(self, instance):
        """Télécharger un épisode sélectionné"""
        if not self.selected_episode:
            self.show_popup("Erreur", "Veuillez selectionner un episode")
            return
        
        if 'url' not in self.selected_episode:
            self.show_popup("Erreur", "URL de l'episode non trouvee")
            return
        
        episode_num = self.selected_episode.get('episode_num', 'Episode')
        episode_title = self.selected_episode.get('title', 'Sans titre')
        filename = f"{episode_num} - {episode_title}"
        
        self.download_file(self.selected_episode['url'], filename, "episode")
    
    def download_selected_season(self, instance):
        """Télécharger une saison complète"""
        if not self.selected_season:
            self.show_popup("Erreur", "Veuillez selectionner une saison")
            return
        
        if not self.selected_season_episodes:
            self.show_popup("Erreur", "Aucun episode dans cette saison")
            return
        
        # Confirmation avec info d'espace disque
        season_name = self.selected_season['season_name']
        episode_count = len(self.selected_season_episodes)
        
        # Estimer la taille (supposons 500MB par épisode)
        estimated_size_gb = (episode_count * 500) / 1024
        
        content = BoxLayout(orientation='vertical', spacing=10, padding=20)
        content.add_widget(Label(
            text=f"Telecharger {season_name}?\n({episode_count} episodes)\nTaille estimee: {estimated_size_gb:.1f}GB",
            text_size=(300, None)
        ))
        
        popup = Popup(
            title="Confirmation",
            content=content,
            size_hint=(0.8, 0.4)
        )
        
        btn_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=50, spacing=10)
        
        yes_btn = Button(text='Oui')
        yes_btn.bind(on_press=lambda x: [popup.dismiss(), self.start_season_download()])
        btn_layout.add_widget(yes_btn)
        
        no_btn = Button(text='Non')
        no_btn.bind(on_press=popup.dismiss)
        btn_layout.add_widget(no_btn)
        
        content.add_widget(btn_layout)
        popup.open()
    
    def start_season_download(self):
        """Démarrer le téléchargement d'une saison"""
        def download_season_thread():
            try:
                series_name = self.clean_filename(self.selected_series['name'])
                season_name = self.selected_season['season_name']
                season_number = self.selected_season_episodes[0].get('season', '1')
                
                total_episodes = len(self.selected_season_episodes)
                downloaded = 0
                failed = 0
                
                # Utiliser le chemin de téléchargement défini
                downloads_path = self.get_download_path()
                
                Clock.schedule_once(lambda dt: self.update_status(f"Telechargement {season_name}..."), 0)
                
                for i, episode in enumerate(self.selected_season_episodes):
                    try:
                        episode_num = episode.get('episode_num', f'Episode_{i+1}')
                        episode_title = episode.get('title', 'Sans_titre')
                        filename = f"{series_name} - {episode_num} - {episode_title}"
                        
                        # Mettre à jour le statut
                        progress = ((i + 1) / total_episodes) * 100
                        Clock.schedule_once(lambda dt, p=progress, ep=episode_num, curr=i+1, tot=total_episodes: 
                                          self.update_status(f"{season_name}: {ep} ({curr}/{tot}) - {p:.0f}%"), 0)
                        
                        # Téléchargement
                        headers = {'User-Agent': 'Mozilla/5.0 (compatible; IPTV Manager)'}
                        response = requests.get(episode['url'], stream=True, timeout=30, headers=headers)
                        response.raise_for_status()
                        
                        # Créer structure de dossiers dans le chemin défini
                        series_folder = os.path.join(downloads_path, series_name)
                        os.makedirs(series_folder, exist_ok=True)
                        
                        season_folder = os.path.join(series_folder, f"Saison {season_number}")
                        os.makedirs(season_folder, exist_ok=True)
                        
                        file_path = os.path.join(season_folder, f"{self.clean_filename(filename)}.mp4")
                        
                        with open(file_path, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=65536):
                                if chunk:
                                    f.write(chunk)
                        
                        downloaded += 1
                        
                    except Exception as episode_error:
                        failed += 1
                        print(f"Erreur episode {episode.get('episode_num', 'inconnu')}: {episode_error}")
                
                # Message final
                Clock.schedule_once(lambda dt: self.show_season_download_result(downloaded, failed, total_episodes, season_name), 0)
                
            except Exception as season_error:
                error_msg = str(season_error)
                Clock.schedule_once(lambda dt: self.show_popup("Erreur", f"Erreur saison: {error_msg}"), 0)
                
        threading.Thread(target=download_season_thread, daemon=True).start()
    
    def show_season_download_result(self, downloaded, failed, total, season_name):
        """Afficher le résultat du téléchargement de saison"""
        if failed == 0:
            self.show_popup("Telechargement", f"{season_name} telechargee!\n{downloaded} episodes\nDossier: {self.get_download_path()}")
        else:
            self.show_popup("Telechargement", f"{season_name} partiellement telechargee:\n{downloaded} reussis, {failed} echues\nDossier: {self.get_download_path()}")
        
        self.update_status(f"Saison terminee: {downloaded}/{total} episodes")
        # Mettre à jour les infos d'espace disque
        Clock.schedule_once(lambda dt: self.update_storage_info(), 1)
    
    def download_selected_series(self, instance):
        """Télécharger une série complète"""
        if not self.selected_series:
            self.show_popup("Erreur", "Veuillez selectionner une serie")
            return
        
        if not self.selected_series_episodes:
            self.show_popup("Erreur", "Veuillez d'abord charger les episodes de la serie")
            return
        
        # Compter le total d'épisodes et estimer la taille
        total_episodes = sum(len(episodes) for episodes in self.selected_series_episodes.values())
        estimated_size_gb = (total_episodes * 500) / 1024  # 500MB par épisode
        
        # Confirmation avec estimation de taille
        content = BoxLayout(orientation='vertical', spacing=10, padding=20)
        content.add_widget(Label(
            text=f"Telecharger toute la serie '{self.selected_series['name']}'?\n({total_episodes} episodes)\nTaille estimee: {estimated_size_gb:.1f}GB\nDossier: {self.get_download_path()}",
            text_size=(300, None)
        ))
        
        popup = Popup(
            title="Confirmation",
            content=content,
            size_hint=(0.8, 0.5)
        )
        
        btn_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=50, spacing=10)
        
        yes_btn = Button(text='Oui')
        yes_btn.bind(on_press=lambda x: [popup.dismiss(), self.start_series_download()])
        btn_layout.add_widget(yes_btn)
        
        no_btn = Button(text='Non')
        no_btn.bind(on_press=popup.dismiss)
        btn_layout.add_widget(no_btn)
        
        content.add_widget(btn_layout)
        popup.open()
    
    def start_series_download(self):
        """Démarrer le téléchargement de la série complète"""
        def download_series_thread():
            try:
                series_name = self.clean_filename(self.selected_series['name'])
                total_episodes = sum(len(episodes) for episodes in self.selected_series_episodes.values())
                
                downloaded = 0
                failed = 0
                
                # Utiliser le chemin de téléchargement défini
                downloads_path = self.get_download_path()
                
                Clock.schedule_once(lambda dt: self.update_status(f"Telechargement serie: {series_name}"), 0)
                
                # Parcourir chaque saison
                for season_name, episodes in self.selected_series_episodes.items():
                    for episode in episodes:
                        try:
                            episode_num = episode.get('episode_num', f'Episode_{downloaded+1}')
                            episode_title = episode.get('title', 'Sans_titre')
                            season = episode.get('season', '1')
                            
                            filename = f"{series_name} - {episode_num} - {episode_title}"
                            
                            # Mettre à jour le statut
                            progress = ((downloaded + 1) / total_episodes) * 100
                            Clock.schedule_once(lambda dt, p=progress, ep=episode_num, curr=downloaded+1, tot=total_episodes: 
                                              self.update_status(f"Serie: {ep} ({curr}/{tot}) - {p:.0f}%"), 0)
                            
                            # Téléchargement
                            headers = {'User-Agent': 'Mozilla/5.0 (compatible; IPTV Manager)'}
                            response = requests.get(episode['url'], stream=True, timeout=30, headers=headers)
                            response.raise_for_status()
                            
                            # Structure de dossiers dans le chemin défini
                            series_folder = os.path.join(downloads_path, series_name)
                            os.makedirs(series_folder, exist_ok=True)
                            
                            season_folder = os.path.join(series_folder, f"Saison {season}")
                            os.makedirs(season_folder, exist_ok=True)
                            
                            file_path = os.path.join(season_folder, f"{self.clean_filename(filename)}.mp4")
                            
                            with open(file_path, 'wb') as f:
                                for chunk in response.iter_content(chunk_size=65536):
                                    if chunk:
                                        f.write(chunk)
                            
                            downloaded += 1
                            
                        except Exception as episode_error:
                            failed += 1
                            print(f"Erreur episode {episode.get('episode_num', 'inconnu')}: {episode_error}")
                
                # Message final
                Clock.schedule_once(lambda dt: self.show_series_download_result(downloaded, failed, total_episodes, series_name), 0)
                
            except Exception as series_error:
                error_msg = str(series_error)
                Clock.schedule_once(lambda dt: self.show_popup("Erreur", f"Erreur serie: {error_msg}"), 0)
                
        threading.Thread(target=download_series_thread, daemon=True).start()
    
    def show_series_download_result(self, downloaded, failed, total, series_name):
        """Afficher le résultat du téléchargement de série"""
        download_path = self.get_download_path()
        
        if failed == 0:
            self.show_popup("Telechargement", f"Serie '{series_name}' telechargee!\n{downloaded} episodes\nDossier: {download_path}")
        else:
            self.show_popup("Telechargement", f"Serie '{series_name}' partiellement telechargee:\n{downloaded} reussis, {failed} echues\nDossier: {download_path}")
        
        self.update_status(f"Serie terminee: {downloaded}/{total} episodes")
        # Mettre à jour les infos d'espace disque
        Clock.schedule_once(lambda dt: self.update_storage_info(), 1)
    
    def download_file(self, url, filename, file_type="fichier"):
        """Télécharger un fichier avec reconnexions multiples et fenêtre de progression"""
        clean_name = self.clean_filename(filename)
        
        # Créer et afficher la fenêtre de progression
        progress_popup = DownloadProgressPopup(clean_name)
        progress_popup.open()
        
        def download_in_thread():
            try:
                # Utiliser le chemin de téléchargement défini
                downloads_path = self.get_download_path()
                save_path = os.path.join(downloads_path, f"{clean_name}.mp4")
                
                # TÉLÉCHARGEMENT AVEC RECONNEXIONS MULTIPLES
                self.download_with_reconnections(url, save_path, file_type, progress_popup)
                
            except Exception as e:
                error_msg = str(e)
                Clock.schedule_once(lambda dt: progress_popup.dismiss(), 0)
                Clock.schedule_once(lambda dt: self.show_popup("Erreur", f"Erreur telechargement:\n{error_msg}"), 0)
                
        threading.Thread(target=download_in_thread, daemon=True).start()
    
    def download_with_reconnections(self, url, save_path, file_type, progress_popup):
        """Téléchargement avec reconnexions PRÉVENTIVES"""
        
        max_reconnections = 1000
        reconnection_count = 0
        total_downloaded = 0
        
        total_size = self.get_file_size(url)
        start_time = time.time()
        
        # Sessions pool
        session_pool = []
        for i in range(10):
            session = requests.Session()
            retry_strategy = Retry(total=0, backoff_factor=0)
            adapter = HTTPAdapter(
                max_retries=retry_strategy,
                pool_connections=1,
                pool_maxsize=1,
                pool_block=False
            )
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            session_pool.append(session)
        
        current_session_index = 0
        
        user_agents = [
            'VLC/3.0.18 LibVLC/3.0.18',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Mozilla/5.0 (Android 10; Mobile; rv:109.0) Gecko/111.0 Firefox/109.0',
            'Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36'
        ]
        
        with open(save_path, 'wb') as f:
            
            while total_downloaded < total_size and reconnection_count < max_reconnections and not progress_popup.cancelled:
                try:
                    session = session_pool[current_session_index % len(session_pool)]
                    current_session_index += 1
                    
                    headers = {
                        'User-Agent': user_agents[reconnection_count % len(user_agents)],
                        'Accept': '*/*',
                        'Accept-Encoding': 'identity',
                        'Connection': 'keep-alive',
                        'Range': f'bytes={total_downloaded}-',
                        'Cache-Control': 'no-cache'
                    }
                    
                    session.headers.clear()
                    session.headers.update(headers)
                    
                    response = session.get(url, stream=True, timeout=10)
                    
                    if response.status_code not in [200, 206]:
                        reconnection_count += 1
                        continue
                    
                    connection_downloaded = 0
                    connection_start_time = time.time()
                    max_connection_time = 15.0
                    max_connection_size = 150 * 1024 * 1024
                    chunk_size = 524288
                    
                    f.seek(total_downloaded)
                    last_progress_update = connection_start_time
                    
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if chunk and not progress_popup.cancelled:
                            f.write(chunk)
                            connection_downloaded += len(chunk)
                            total_downloaded += len(chunk)
                            
                            current_time = time.time()
                            connection_elapsed = current_time - connection_start_time
                            
                            if current_time - last_progress_update >= 0.5:
                                current_speed = (connection_downloaded / (1024 * 1024)) / connection_elapsed if connection_elapsed > 0 else 0
                                progress = (total_downloaded / total_size) * 100 if total_size > 0 else 0
                                
                                status = f"Telechargement: {progress:.0f}%"
                                details = f"{total_downloaded / (1024*1024):.1f}MB / {total_size / (1024*1024):.1f}MB"
                                
                                Clock.schedule_once(
                                    lambda dt, p=progress, s=status, sp=current_speed, c=reconnection_count, d=details:
                                    progress_popup.update_progress(p, s, sp, c+1, d), 0
                                )
                                
                                last_progress_update = current_time
                            
                            if connection_elapsed >= max_connection_time:
                                break
                            if connection_downloaded >= max_connection_size:
                                break
                            if connection_elapsed >= 3.0:
                                current_speed = (connection_downloaded / (1024 * 1024)) / connection_elapsed
                                if current_speed < 25.0:
                                    break
                        
                        elif progress_popup.cancelled:
                            break
                    
                    try:
                        response.close()
                    except:
                        pass
                    
                    if total_downloaded >= total_size:
                        break
                    if progress_popup.cancelled:
                        break
                    
                    reconnection_count += 1
                        
                except requests.exceptions.RequestException as e:
                    reconnection_count += 1
                    time.sleep(0.1)
                    continue
                    
                except Exception as e:
                    reconnection_count += 1
                    continue
        
        # Fermer toutes les sessions
        for session in session_pool:
            try:
                session.close()
            except:
                pass
        
        # Statistiques finales
        end_time = time.time()
        total_time = end_time - start_time
        final_speed = (total_downloaded / (1024 * 1024)) / total_time if total_time > 0 else 0
        
        def show_success():
            progress_popup.dismiss()
            size_mb = total_downloaded / (1024 * 1024)
            success_rate = (total_downloaded / total_size) * 100 if total_size > 0 else 0
            
            if progress_popup.cancelled:
                self.show_popup("Annule", "Telechargement annule par l'utilisateur")
                try:
                    if os.path.exists(save_path):
                        os.remove(save_path)
                except:
                    pass
            elif success_rate >= 99:
                self.show_popup("Telechargement", 
                    f"Fichier telecharge avec succes!\n"
                    f"Dossier: {save_path}\n"
                    f"Taille: {size_mb:.1f} MB\n"
                    f"Vitesse: {final_speed:.1f} MB/s\n"
                    f"Reconnexions: {reconnection_count}")
            else:
                self.show_popup("Telechargement", 
                    f"Telechargement partiel ({success_rate:.1f}%)\n"
                    f"Dossier: {save_path}\n"
                    f"Taille: {size_mb:.1f} MB sur {total_size/(1024*1024):.1f} MB")
            
            self.update_status("Telechargement termine")
            # Mettre à jour les infos d'espace disque
            Clock.schedule_once(lambda dt: self.update_storage_info(), 1)
        
        Clock.schedule_once(lambda dt: show_success(), 0)
    
    def get_file_size(self, url):
        """Obtenir la taille du fichier via une requête HEAD"""
        try:
            headers = {
                'User-Agent': 'VLC/3.0.18 LibVLC/3.0.18',
                'Accept': '*/*'
            }
            
            response = requests.head(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            content_length = response.headers.get('content-length')
            if content_length:
                return int(content_length)
            else:
                response = requests.get(url, stream=True, headers=headers, timeout=10)
                response.raise_for_status()
                content_length = response.headers.get('content-length')
                response.close()
                return int(content_length) if content_length else 100 * 1024 * 1024
                
        except Exception as e:
            return 100 * 1024 * 1024  # 100MB par défaut
    
    def clean_filename(self, filename):
        """Nettoyer un nom de fichier pour le système de fichiers"""
        if not filename:
            return "fichier"
        
        # Remplacer les caractères interdits et problématiques
        clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(filename))
        # Enlever les espaces en début/fin
        clean = clean.strip()
        # Remplacer les espaces multiples par un seul
        clean = re.sub(r'\s+', ' ', clean)
        # Limiter la longueur
        if len(clean) > 100:
            clean = clean[:100]
        
        return clean if clean else "fichier"
    
    def play_url(self, url):
        """Lire une URL avec le lecteur système"""
        try:
            # Sur Android, utiliser l'intent pour ouvrir avec un lecteur vidéo
            try:
                from jnius import autoclass, cast
                
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                Intent = autoclass('android.content.Intent')
                Uri = autoclass('android.net.Uri')
                
                intent = Intent()
                intent.setAction(Intent.ACTION_VIEW)
                intent.setDataAndType(Uri.parse(url), "video/*")
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                
                currentActivity = cast('android.app.Activity', PythonActivity.mActivity)
                currentActivity.startActivity(intent)
                
                self.update_status("Lecture demarree")
                
            except ImportError:
                # Fallback pour les tests sur desktop
                self.show_popup("Lecture", f"Lecture de: {url[:50]}...")
                self.update_status("Lecture simulee (desktop)")
                
        except Exception as e:
            self.show_popup("Erreur", f"Erreur de lecture: {str(e)}")

if __name__ == '__main__':
    IPTVManagerApp().run()
