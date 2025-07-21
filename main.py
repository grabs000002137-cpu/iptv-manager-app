#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IPTV Manager Android - Version Finale
Application IPTV complète pour Android
"""

import os
import json
import requests
import threading
import time
import re
from datetime import datetime
from urllib.parse import quote

# Kivy imports
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar
from kivy.uix.spinner import Spinner
from kivy.clock import Clock
from kivy.logger import Logger
from kivy.utils import platform
from kivy.metrics import dp

# Android-specific imports
if platform == 'android':
    try:
        from android.permissions import request_permissions, Permission
        from jnius import autoclass, cast
        
        # Android classes
        Intent = autoclass('android.content.Intent')
        Uri = autoclass('android.net.Uri')
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        Context = autoclass('android.content.Context')
        Environment = autoclass('android.os.Environment')
        ComponentName = autoclass('android.content.ComponentName')
    except ImportError:
        Logger.warning("Android modules not available")

class SimpleProgressPopup(Popup):
    """Popup de progression simple"""
    
    def __init__(self, filename, **kwargs):
        super().__init__(**kwargs)
        self.title = f'Téléchargement: {filename[:25]}...'
        self.size_hint = (0.9, 0.4)
        self.auto_dismiss = False
        
        layout = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(15))
        
        self.status_label = Label(
            text='Préparation...',
            size_hint_y=None,
            height=dp(40)
        )
        layout.add_widget(self.status_label)
        
        self.progress_bar = ProgressBar(
            max=100,
            value=0,
            size_hint_y=None,
            height=dp(20)
        )
        layout.add_widget(self.progress_bar)
        
        self.info_label = Label(
            text='0%',
            size_hint_y=None,
            height=dp(30)
        )
        layout.add_widget(self.info_label)
        
        close_btn = Button(
            text='Fermer',
            size_hint_y=None,
            height=dp(40),
            background_color=(0.8, 0.2, 0.2, 1)
        )
        close_btn.bind(on_press=self.dismiss)
        layout.add_widget(close_btn)
        
        self.content = layout
    
    def update_progress(self, percent, status=""):
        """Mettre à jour la progression"""
        def update_ui(dt):
            self.progress_bar.value = min(percent, 100)
            if status:
                self.status_label.text = status
            self.info_label.text = f'{percent:.1f}%'
        
        Clock.schedule_once(update_ui, 0)

class ConfigScreen(Screen):
    """Écran de configuration"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = 'config'
        
        main_layout = BoxLayout(orientation='vertical', padding=dp(20), spacing=dp(15))
        
        # Titre
        title = Label(
            text='Configuration IPTV Manager',
            size_hint_y=None,
            height=dp(50),
            font_size=dp(20),
            bold=True
        )
        main_layout.add_widget(title)
        
        # Formulaire
        form_layout = BoxLayout(orientation='vertical', spacing=dp(10))
        
        form_layout.add_widget(Label(text='Serveur IPTV:', size_hint_y=None, height=dp(30)))
        self.server_url = TextInput(
            hint_text='http://votre-serveur.com:8080',
            size_hint_y=None,
            height=dp(40),
            multiline=False
        )
        form_layout.add_widget(self.server_url)
        
        form_layout.add_widget(Label(text='Nom d\'utilisateur:', size_hint_y=None, height=dp(30)))
        self.username = TextInput(
            hint_text='Votre nom d\'utilisateur',
            size_hint_y=None,
            height=dp(40),
            multiline=False
        )
        form_layout.add_widget(self.username)
        
        form_layout.add_widget(Label(text='Mot de passe:', size_hint_y=None, height=dp(30)))
        self.password = TextInput(
            hint_text='Votre mot de passe',
            size_hint_y=None,
            height=dp(40),
            multiline=False,
            password=True
        )
        form_layout.add_widget(self.password)
        
        form_layout.add_widget(Label(text='Ou URL playlist M3U:', size_hint_y=None, height=dp(30)))
        self.playlist_url = TextInput(
            hint_text='http://exemple.com/playlist.m3u',
            size_hint_y=None,
            height=dp(40),
            multiline=False
        )
        form_layout.add_widget(self.playlist_url)
        
        main_layout.add_widget(form_layout)
        
        # Boutons
        btn_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(60), spacing=dp(10))
        
        test_btn = Button(text='TESTER', background_color=(0.2, 0.6, 1, 1))
        test_btn.bind(on_press=self.test_connection)
        btn_layout.add_widget(test_btn)
        
        load_btn = Button(text='CHARGER', background_color=(0.2, 0.8, 0.2, 1))
        load_btn.bind(on_press=self.load_playlist)
        btn_layout.add_widget(load_btn)
        
        save_btn = Button(text='SAUVER', background_color=(0.8, 0.6, 0.2, 1))
        save_btn.bind(on_press=self.save_config)
        btn_layout.add_widget(save_btn)
        
        main_layout.add_widget(btn_layout)
        
        # Status
        self.status_label = Label(
            text='Pret - Configurez votre IPTV',
            size_hint_y=None,
            height=dp(40),
            color=(0.7, 0.7, 0.7, 1)
        )
        main_layout.add_widget(self.status_label)
        
        self.add_widget(main_layout)
        
        Clock.schedule_once(self.load_saved_config, 1)
    
    def load_saved_config(self, dt):
        """Charger config sauvegardée"""
        try:
            app = App.get_running_app()
            if hasattr(app, 'config_data') and app.config_data:
                self.server_url.text = app.config_data.get('server_url', '')
                self.username.text = app.config_data.get('username', '')
                self.password.text = app.config_data.get('password', '')
                self.playlist_url.text = app.config_data.get('playlist_url', '')
        except Exception as e:
            Logger.warning(f'Erreur config: {e}')
    
    def test_connection(self, instance):
        """Tester connexion"""
        def test_thread():
            try:
                Clock.schedule_once(lambda dt: setattr(self.status_label, 'text', 'Test...'), 0)
                
                if self.server_url.text and self.username.text and self.password.text:
                    base_url = self.server_url.text.rstrip('/')
                    test_url = f"{base_url}/player_api.php?username={self.username.text}&password={self.password.text}&action=get_live_categories"
                    
                    response = requests.get(test_url, timeout=10)
                    response.raise_for_status()
                    
                    Clock.schedule_once(lambda dt: self.show_popup('Succès', 'Connexion OK!'), 0)
                    Clock.schedule_once(lambda dt: setattr(self.status_label, 'text', 'Connexion OK'), 0)
                    
                elif self.playlist_url.text:
                    response = requests.get(self.playlist_url.text, timeout=10)
                    response.raise_for_status()
                    
                    Clock.schedule_once(lambda dt: self.show_popup('Succès', 'Playlist OK!'), 0)
                else:
                    Clock.schedule_once(lambda dt: self.show_popup('Attention', 'Remplissez la config'), 0)
                    
            except Exception as e:
                Clock.schedule_once(lambda dt: self.show_popup('Erreur', f'Erreur: {str(e)}'), 0)
                
        threading.Thread(target=test_thread, daemon=True).start()
    
    def load_playlist(self, instance):
        """Charger playlist"""
        app = App.get_running_app()
        
        def load_thread():
            try:
                Clock.schedule_once(lambda dt: setattr(self.status_label, 'text', 'Chargement...'), 0)
                
                if self.playlist_url.text:
                    response = requests.get(self.playlist_url.text, timeout=30)
                    response.raise_for_status()
                    app.parse_m3u_playlist(response.text)
                elif self.server_url.text and self.username.text and self.password.text:
                    app.load_from_iptv_api(self.server_url.text, self.username.text, self.password.text)
                else:
                    Clock.schedule_once(lambda dt: self.show_popup('Attention', 'Config requise'), 0)
                    return
                
                app.config_data = {
                    'server_url': self.server_url.text,
                    'username': self.username.text,
                    'password': self.password.text,
                    'playlist_url': self.playlist_url.text
                }
                app.save_config()
                
                Clock.schedule_once(lambda dt: self.show_popup('Succès', 
                    f'Chargé: {len(app.channels)} chaînes, {len(app.movies)} films'), 0)
                Clock.schedule_once(lambda dt: setattr(self.status_label, 'text', 
                    f'{len(app.channels)} chaînes, {len(app.movies)} films'), 0)
                
                Clock.schedule_once(lambda dt: app.update_all_screens(), 0)
                
            except Exception as e:
                Clock.schedule_once(lambda dt: self.show_popup('Erreur', f'Erreur: {str(e)}'), 0)
                
        threading.Thread(target=load_thread, daemon=True).start()
    
    def save_config(self, instance):
        """Sauvegarder config"""
        try:
            app = App.get_running_app()
            app.config_data = {
                'server_url': self.server_url.text,
                'username': self.username.text,
                'password': self.password.text,
                'playlist_url': self.playlist_url.text
            }
            app.save_config()
            self.show_popup('Sauvegarde', 'Config sauvegardée!')
        except Exception as e:
            self.show_popup('Erreur', f'Erreur: {str(e)}')
    
    def show_popup(self, title, message):
        """Afficher popup"""
        app = App.get_running_app()
        app.show_popup(title, message)

class ChannelsScreen(Screen):
    """Écran chaînes TV"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = 'channels'
        
        main_layout = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(10))
        
        header_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(50))
        
        title_label = Label(text='Chaînes TV', size_hint_x=0.4, bold=True)
        header_layout.add_widget(title_label)
        
        self.search_input = TextInput(
            hint_text='Rechercher...',
            size_hint_x=0.6,
            multiline=False
        )
        self.search_input.bind(text=self.filter_channels)
        header_layout.add_widget(self.search_input)
        
        main_layout.add_widget(header_layout)
        
        self.counter_label = Label(
            text='0 chaînes',
            size_hint_y=None,
            height=dp(25),
            color=(0.7, 0.7, 0.7, 1)
        )
        main_layout.add_widget(self.counter_label)
        
        scroll = ScrollView()
        self.channels_layout = BoxLayout(orientation='vertical', spacing=dp(5), size_hint_y=None)
        self.channels_layout.bind(minimum_height=self.channels_layout.setter('height'))
        scroll.add_widget(self.channels_layout)
        main_layout.add_widget(scroll)
        
        self.add_widget(main_layout)
    
    def update_channels_list(self, dt=None):
        """Mettre à jour chaînes"""
        app = App.get_running_app()
        self.channels_layout.clear_widgets()
        
        count = 0
        for channel in app.channels[:100]:  # Limiter pour performance
            channel_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(60))
            
            info_layout = BoxLayout(orientation='vertical', size_hint_x=0.7)
            
            name_label = Label(
                text=channel['name'][:40],
                size_hint_y=0.7,
                bold=True,
                halign='left'
            )
            info_layout.add_widget(name_label)
            
            group_label = Label(
                text=f"Groupe: {channel['group']}",
                size_hint_y=0.3,
                color=(0.7, 0.7, 0.7, 1),
                halign='left'
            )
            info_layout.add_widget(group_label)
            
            channel_layout.add_widget(info_layout)
            
            btn_layout = BoxLayout(orientation='horizontal', size_hint_x=0.3)
            
            play_btn = Button(text='LIRE', background_color=(0.2, 0.8, 0.2, 1))
            play_btn.bind(on_press=lambda x, ch=channel: self.play_channel(ch))
            btn_layout.add_widget(play_btn)
            
            channel_layout.add_widget(btn_layout)
            self.channels_layout.add_widget(channel_layout)
            count += 1
        
        self.counter_label.text = f'{count} chaînes'
    
    def filter_channels(self, instance, text):
        """Filtrer chaînes"""
        app = App.get_running_app()
        self.channels_layout.clear_widgets()
        
        search_term = text.lower()
        count = 0
        
        for channel in app.channels:
            if search_term in channel['name'].lower():
                if count >= 50:
                    break
                    
                channel_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(60))
                
                info_layout = BoxLayout(orientation='vertical', size_hint_x=0.7)
                
                name_label = Label(
                    text=channel['name'][:40],
                    size_hint_y=0.7,
                    bold=True,
                    halign='left'
                )
                info_layout.add_widget(name_label)
                
                group_label = Label(
                    text=f"Groupe: {channel['group']}",
                    size_hint_y=0.3,
                    color=(0.7, 0.7, 0.7, 1),
                    halign='left'
                )
                info_layout.add_widget(group_label)
                
                channel_layout.add_widget(info_layout)
                
                play_btn = Button(text='LIRE', background_color=(0.2, 0.8, 0.2, 1), size_hint_x=0.3)
                play_btn.bind(on_press=lambda x, ch=channel: self.play_channel(ch))
                channel_layout.add_widget(play_btn)
                
                self.channels_layout.add_widget(channel_layout)
                count += 1
        
        self.counter_label.text = f'{count} chaînes'
    
    def play_channel(self, channel):
        """Lire chaîne"""
        app = App.get_running_app()
        app.play_video(channel['url'], channel['name'])

class MoviesScreen(Screen):
    """Écran films"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.name = 'movies'
        
        main_layout = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(10))
        
        header_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(50))
        
        title_label = Label(text='Films VOD', size_hint_x=0.4, bold=True)
        header_layout.add_widget(title_label)
        
        self.search_input = TextInput(
            hint_text='Rechercher film...',
            size_hint_x=0.6,
            multiline=False
        )
        self.search_input.bind(text=self.filter_movies)
        header_layout.add_widget(self.search_input)
        
        main_layout.add_widget(header_layout)
        
        self.counter_label = Label(
            text='0 films',
            size_hint_y=None,
            height=dp(25),
            color=(0.7, 0.7, 0.7, 1)
        )
        main_layout.add_widget(self.counter_label)
        
        scroll = ScrollView()
        self.movies_layout = BoxLayout(orientation='vertical', spacing=dp(5), size_hint_y=None)
        self.movies_layout.bind(minimum_height=self.movies_layout.setter('height'))
        scroll.add_widget(self.movies_layout)
        main_layout.add_widget(scroll)
        
        self.add_widget(main_layout)
    
    def update_movies_list(self, dt=None):
        """Mettre à jour films"""
        app = App.get_running_app()
        self.movies_layout.clear_widgets()
        
        count = 0
        for movie in app.movies[:100]:
            movie_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(70))
            
            info_layout = BoxLayout(orientation='vertical', size_hint_x=0.6)
            
            title_label = Label(
                text=movie['name'][:35],
                size_hint_y=0.6,
                bold=True,
                halign='left'
            )
            info_layout.add_widget(title_label)
            
            details_label = Label(
                text=f"{movie.get('year', '')} | {movie.get('genre', '')[:15]}",
                size_hint_y=0.4,
                color=(0.7, 0.7, 0.7, 1),
                halign='left'
            )
            info_layout.add_widget(details_label)
            
            movie_layout.add_widget(info_layout)
            
            btn_layout = BoxLayout(orientation='vertical', size_hint_x=0.4)
            
            play_btn = Button(text='LIRE', background_color=(0.2, 0.8, 0.2, 1))
            play_btn.bind(on_press=lambda x, mv=movie: self.play_movie(mv))
            btn_layout.add_widget(play_btn)
            
            download_btn = Button(text='TELECHARGER', background_color=(0.2, 0.6, 1, 1))
            download_btn.bind(on_press=lambda x, mv=movie: self.download_movie(mv))
            btn_layout.add_widget(download_btn)
            
            movie_layout.add_widget(btn_layout)
            self.movies_layout.add_widget(movie_layout)
            count += 1
        
        self.counter_label.text = f'{count} films'
    
    def filter_movies(self, instance, text):
        """Filtrer films"""
        app = App.get_running_app()
        self.movies_layout.clear_widgets()
        
        search_term = text.lower()
        count = 0
        
        for movie in app.movies:
            if search_term in movie['name'].lower():
                if count >= 50:
                    break
                    
                movie_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(70))
                
                info_layout = BoxLayout(orientation='vertical', size_hint_x=0.6)
                
                title_label = Label(
                    text=movie['name'][:35],
                    size_hint_y=0.6,
                    bold=True,
                    halign='left'
                )
                info_layout.add_widget(title_label)
                
                details_label = Label(
                    text=f"{movie.get('year', '')} | {movie.get('genre', '')[:15]}",
                    size_hint_y=0.4,
                    color=(0.7, 0.7, 0.7, 1),
                    halign='left'
                )
                info_layout.add_widget(details_label)
                
                movie_layout.add_widget(info_layout)
                
                btn_layout = BoxLayout(orientation='vertical', size_hint_x=0.4)
                
                play_btn = Button(text='LIRE', background_color=(0.2, 0.8, 0.2, 1))
                play_btn.bind(on_press=lambda x, mv=movie: self.play_movie(mv))
                btn_layout.add_widget(play_btn)
                
                download_btn = Button(text='TELECHARGER', background_color=(0.2, 0.6, 1, 1))
                download_btn.bind(on_press=lambda x, mv=movie: self.download_movie(mv))
                btn_layout.add_widget(download_btn)
                
                movie_layout.add_widget(btn_layout)
                self.movies_layout.add_widget(movie_layout)
                count += 1
        
        self.counter_label.text = f'{count} films'
    
    def play_movie(self, movie):
        """Lire film"""
        app = App.get_running_app()
        app.play_video(movie['url'], movie['name'])
    
    def download_movie(self, movie):
        """Télécharger film"""
        app = App.get_running_app()
        app.download_file_simple(movie['url'], movie['name'], 'film')

class IPTVApp(App):
    """Application principale"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.channels = []
        self.movies = []
        self.series = []
        self.config_data = {}
    
    def build(self):
        """Construire interface"""
        if platform == 'android':
            self.request_android_permissions()
        
        sm = ScreenManager()
        
        self.config_screen = ConfigScreen()
        self.channels_screen = ChannelsScreen()
        self.movies_screen = MoviesScreen()
        
        sm.add_widget(self.config_screen)
        sm.add_widget(self.channels_screen)
        sm.add_widget(self.movies_screen)
        
        root_layout = BoxLayout(orientation='vertical')
        root_layout.add_widget(sm)
        
        nav_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(60))
        
        nav_buttons = [
            ('CONFIG', 'config', (0.3, 0.3, 0.8, 1)),
            ('TV', 'channels', (0.2, 0.8, 0.2, 1)),
            ('FILMS', 'movies', (0.8, 0.2, 0.2, 1))
        ]
        
        for text, screen_name, color in nav_buttons:
            nav_btn = Button(text=text, background_color=color)
            nav_btn.bind(on_press=lambda x, screen=screen_name: setattr(sm, 'current', screen))
            nav_layout.add_widget(nav_btn)
        
        root_layout.add_widget(nav_layout)
        
        Clock.schedule_once(self.load_saved_config, 1)
        
        return root_layout
    
    def request_android_permissions(self):
        """Demander permissions"""
        try:
            permissions = [
                Permission.INTERNET,
                Permission.WRITE_EXTERNAL_STORAGE,
                Permission.READ_EXTERNAL_STORAGE,
                Permission.ACCESS_NETWORK_STATE
            ]
            request_permissions(permissions)
        except Exception as e:
            Logger.warning(f'Permissions: {e}')
    
    def load_saved_config(self, dt):
        """Charger config"""
        try:
            if platform == 'android':
                app_dir = PythonActivity.mActivity.getFilesDir().getAbsolutePath()
                config_path = os.path.join(app_dir, 'iptv_config.json')
            else:
                config_path = 'iptv_config.json'
            
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    self.config_data = json.load(f)
        except Exception as e:
            self.config_data = {}
    
    def save_config(self):
        """Sauvegarder config"""
        try:
            if platform == 'android':
                app_dir = PythonActivity.mActivity.getFilesDir().getAbsolutePath()
                config_path = os.path.join(app_dir, 'iptv_config.json')
            else:
                config_path = 'iptv_config.json'
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config_data, f, indent=2)
        except Exception as e:
            Logger.error(f'Erreur sauvegarde: {e}')
    
    def update_all_screens(self):
        """Mettre à jour écrans"""
        try:
            self.channels_screen.update_channels_list()
            self.movies_screen.update_movies_list()
        except Exception as e:
            Logger.error(f'Erreur mise à jour: {e}')
    
    def parse_m3u_playlist(self, content):
        """Parser playlist M3U"""
        lines = content.strip().split('\n')
        self.channels = []
        self.movies = []
        
        current_item = None
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
                    
                    current_item = {'name': name, 'group': group}
                    
            elif line and not line.startswith('#') and current_item:
                current_item['url'] = line
                
                if any(keyword in current_item['group'].lower() for keyword in ['movie', 'film']):
                    self.movies.append({
                        'name': current_item['name'],
                        'year': '',
                        'genre': current_item['group'],
                        'url': current_item['url']
                    })
                else:
                    self.channels.append(current_item)
                
                current_item = None
    
    def load_from_iptv_api(self, server_url, username, password):
        """Charger depuis API IPTV"""
        base_url = server_url.rstrip('/')
        headers = {'User-Agent': 'IPTV Manager Android/1.0'}
        
        try:
            # Chaînes
            channels_url = f"{base_url}/player_api.php?username={username}&password={password}&action=get_live_streams"
            response = requests.get(channels_url, timeout=30, headers=headers)
            response.raise_for_status()
            channels_data = response.json()
            
            self.channels = []
            for channel in channels_data:
                self.channels.append({
                    'name': channel.get('name', 'Inconnu'),
                    'group': channel.get('category_name', 'Inconnu'),
                    'url': f"{base_url}/live/{username}/{password}/{channel['stream_id']}.m3u8"
                })
            
            # Films
            vod_url = f"{base_url}/player_api.php?username={username}&password={password}&action=get_vod_streams"
            response = requests.get(vod_url, timeout=30, headers=headers)
            response.raise_for_status()
            vod_data = response.json()
            
            self.movies = []
            for movie in vod_data:
                self.movies.append({
                    'name': movie.get('name', 'Inconnu'),
                    'year': str(movie.get('year', '')),
                    'genre': movie.get('genre', 'Inconnu'),
                    'url': f"{base_url}/movie/{username}/{password}/{movie['stream_id']}.{movie.get('container_extension', 'mp4')}"
                })
            
        except Exception as e:
            raise Exception(f"Erreur API: {str(e)}")
    
    def play_video(self, url, title="Vidéo"):
        """Lire vidéo"""
        if platform == 'android':
            try:
                intent = Intent()
                intent.setAction(Intent.ACTION_VIEW)
                intent.setDataAndType(Uri.parse(url), "video/*")
                intent.putExtra(Intent.EXTRA_TITLE, title)
                intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                
                current_activity = cast('android.app.Activity', PythonActivity.mActivity)
                current_activity.startActivity(intent)
                
                self.show_popup('Lecture', f'Ouverture de {title[:30]}...')
                
            except Exception as e:
                self.show_popup('Erreur', f'Impossible de lire: {str(e)}')
        else:
            import webbrowser
            webbrowser.open(url)
            self.show_popup('Lecture', f'Ouverture de {title}')
    
    def download_file_simple(self, url, filename, file_type="fichier"):
        """Téléchargement simple"""
        def download_thread():
            progress_popup = None
            try:
                clean_name = self.clean_filename(filename)
                progress_popup = SimpleProgressPopup(clean_name)
                Clock.schedule_once(lambda dt: progress_popup.open(), 0)
                
                if platform == 'android':
                    try:
                        DownloadManager = autoclass('android.app.DownloadManager')
                        Uri = autoclass('android.net.Uri')
                        Environment = autoclass('android.os.Environment')
                        
                        if not clean_name.endswith('.mp4'):
                            clean_name += '.mp4'
                        
                        request = DownloadManager.Request(Uri.parse(url))
                        request.setTitle(f"IPTV - {file_type}")
                        request.setDescription(clean_name)
                        request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, clean_name)
                        request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
                        request.setAllowedOverMetered(True)
                        
                        download_manager = PythonActivity.mActivity.getSystemService(Context.DOWNLOAD_SERVICE)
                        download_id = download_manager.enqueue(request)
                        
                        Clock.schedule_once(lambda dt: progress_popup.dismiss(), 1)
                        Clock.schedule_once(lambda dt: self.show_popup('Téléchargement', 
                            f'Téléchargement démarré!\nVérifiez les notifications.'), 1.5)
                        
                    except Exception as e:
                        Clock.schedule_once(lambda dt: progress_popup.dismiss(), 0)
                        Clock.schedule_once(lambda dt: self.show_popup('Erreur', f'Erreur: {str(e)}'), 0)
                        
                else:
                    try:
                        if not clean_name.endswith('.mp4'):
                            clean_name += '.mp4'
                        
                        Clock.schedule_once(lambda dt: progress_popup.update_progress(10, "Connexion..."), 0)
                        
                        response = requests.get(url, stream=True, timeout=30)
                        response.raise_for_status()
                        
                        total_size = int(response.headers.get('content-length', 0))
                        downloaded = 0
                        
                        with open(clean_name, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                                    downloaded += len(chunk)
                                    
                                    if total_size > 0:
                                        percent = min((downloaded / total_size) * 100, 95)
                                        Clock.schedule_once(lambda dt, p=percent: progress_popup.update_progress(p), 0)
                        
                        Clock.schedule_once(lambda dt: progress_popup.update_progress(100, "Terminé!"), 0)
                        Clock.schedule_once(lambda dt: progress_popup.dismiss(), 2)
                        Clock.schedule_once(lambda dt: self.show_popup('Succès', f'Fichier téléchargé: {clean_name}'), 2.5)
                        
                    except Exception as e:
                        Clock.schedule_once(lambda dt: progress_popup.dismiss(), 0)
                        Clock.schedule_once(lambda dt: self.show_popup('Erreur', f'Erreur: {str(e)}'), 0)
                        
            except Exception as e:
                if progress_popup:
                    Clock.schedule_once(lambda dt: progress_popup.dismiss(), 0)
                Clock.schedule_once(lambda dt: self.show_popup('Erreur', f'Erreur: {str(e)}'), 0)
                
        threading.Thread(target=download_thread, daemon=True).start()
    
    def clean_filename(self, filename):
        """Nettoyer nom fichier"""
        if not filename:
            return "fichier"
        
        clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(filename))
        clean = clean.strip()
        
        if len(clean) > 80:
            clean = clean[:80]
        
        return clean if clean else "fichier"
    
    def show_popup(self, title, message):
        """Afficher popup"""
        content = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(15))
        
        message_label = Label(
            text=message,
            text_size=(dp(300), None),
            halign='center'
        )
        content.add_widget(message_label)
        
        ok_btn = Button(
            text='OK',
            size_hint_y=None,
            height=dp(40),
            background_color=(0.2, 0.8, 0.2, 1)
        )
        content.add_widget(ok_btn)
        
        popup = Popup(
            title=title,
            content=content,
            size_hint=(0.8, 0.5),
            auto_dismiss=False
        )
        
        ok_btn.bind(on_press=popup.dismiss)
        popup.open()
        
        if any(keyword in title.lower() for keyword in ['succès', 'lecture']):
            Clock.schedule_once(lambda dt: popup.dismiss() if popup.content else None, 3)

if __name__ == '__main__':
    IPTVApp().run()
