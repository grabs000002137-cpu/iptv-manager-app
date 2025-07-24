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
