# -*- coding: utf-8 -*-

import xbmc
import xbmcgui
import threading
import time

import xbmcaddon as _xbmcaddon
_addon = _xbmcaddon.Addon()

def getString(string_id):
    return _addon.getLocalizedString(string_id)


class UpNextDialog(xbmcgui.WindowXMLDialog):
    
    BUTTON_PLAY_NOW = 3001
    BUTTON_CANCEL = 3002
    LABEL_NEXT_EPISODE = 3003
    IMAGE_THUMBNAIL = 3004
    PROGRESS_BAR = 3005
    
    def __init__(self, *args, **kwargs):
        self.next_episode_info = kwargs.get('next_episode_info', {})
        self.countdown_seconds = kwargs.get('countdown_seconds', 10)
        self.is_anime = kwargs.get('is_anime', False)
        self.auto_play = False
        self.cancelled = False
        self.countdown_thread = None
        self._stop_countdown = False
        self.player = xbmc.Player()
        
    def onInit(self):
        try:
            serie_name = self.next_episode_info.get('serie_name', '')
            next_season = self.next_episode_info.get('next_season', 0)
            next_episode = self.next_episode_info.get('next_episode', 0)
            episode_title = self.next_episode_info.get('episode_title', '')
            thumbnail = self.next_episode_info.get('thumbnail', '')
            
            if self.is_anime:
                # Para animes, apenas mostra o episódio
                if episode_title:
                    next_text = 'Ep {} - {}'.format(next_episode, episode_title)
                else:
                    next_text = 'Ep {}'.format(next_episode)
            else:
                # Para séries, mostra season e episode
                if episode_title:
                    next_text = '{}x{:02d} {}'.format(next_season, next_episode, episode_title)
                else:
                    next_text = '{}x{:02d}'.format(next_season, next_episode)
            
            self.getControl(self.LABEL_NEXT_EPISODE).setLabel(next_text)
            
            if thumbnail:
                self.getControl(self.IMAGE_THUMBNAIL).setImage(thumbnail)
            
            try:
                self.setFocusId(self.BUTTON_PLAY_NOW)
            except:
                pass
            
            self._start_countdown()
            
        except Exception:
            pass
    
    def _start_countdown(self):
        self._stop_countdown = False
        self.countdown_thread = threading.Thread(target=self._countdown_loop)
        self.countdown_thread.daemon = True
        self.countdown_thread.start()
    
    def _countdown_loop(self):
        remaining = self.countdown_seconds
        
        while remaining > 0 and not self._stop_countdown:
            try:
                progress = int((remaining / float(self.countdown_seconds)) * 100)
                self.getControl(self.PROGRESS_BAR).setPercent(progress)
                
                self.getControl(self.BUTTON_PLAY_NOW).setLabel(getString(32108).format(remaining))
                
                time.sleep(1)
                remaining -= 1
                
            except Exception:
                break
        
        if not self._stop_countdown and remaining == 0:
            self.auto_play = True
            self.close()
    
    def onClick(self, controlId):
        if controlId == self.BUTTON_PLAY_NOW:
            try:
                total_time = self.player.getTotalTime()
                self.player.seekTime(total_time - 1)
            except:
                pass
            self.auto_play = True
            self._stop_countdown = True
            self.close()
            
        elif controlId == self.BUTTON_CANCEL:
            self.cancelled = True
            self._stop_countdown = True
            self.close()
    
    def onAction(self, action):
        action_id = action.getId()
        
        if action_id in (xbmcgui.ACTION_SELECT_ITEM, xbmcgui.ACTION_PLAYER_PLAY):
            try:
                focused_control = self.getFocusId()
                
                if focused_control == self.BUTTON_PLAY_NOW:
                    try:
                        total_time = self.player.getTotalTime()
                        self.player.seekTime(total_time - 1)
                    except:
                        pass
                    self.auto_play = True
                    self._stop_countdown = True
                    self.close()
                    return
                    
                elif focused_control == self.BUTTON_CANCEL:
                    self.cancelled = True
                    self._stop_countdown = True
                    self.close()
                    return
            except Exception:
                pass
        
        elif action_id in (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_STOP):
            self.cancelled = True
            self._stop_countdown = True
            self.close()
            return
        
        elif action_id in (xbmcgui.ACTION_MOVE_LEFT, xbmcgui.ACTION_MOVE_RIGHT, 
                          xbmcgui.ACTION_MOVE_UP, xbmcgui.ACTION_MOVE_DOWN):
            pass
        
        elif action_id == xbmcgui.ACTION_PLAYER_PLAY:
            try:
                total_time = self.player.getTotalTime()
                self.player.seekTime(total_time - 1)
            except:
                pass
            self.auto_play = True
            self._stop_countdown = True
            self.close()
            return


class UpNextTVShowService:
    
    def __init__(self, player, database):
        self.player = player
        self.db = database
        
        import xbmcaddon
        addon = xbmcaddon.Addon()
        
        self.enabled = addon.getSettingBool('upnext_enabled') if hasattr(addon, 'getSettingBool') else True
        self.countdown_seconds = addon.getSettingInt('upnext_countdown_seconds') if hasattr(addon, 'getSettingInt') else 10
        self.trigger_seconds = addon.getSettingInt('upnext_trigger_seconds') if hasattr(addon, 'getSettingInt') else 30
        
        if self.countdown_seconds == 0:
            self.countdown_seconds = 10
        if self.trigger_seconds == 0:
            self.trigger_seconds = 30
            
        self.monitoring = False
        self.monitor_thread = None
        self._stop_monitoring = False
        self._monitor_lock = threading.Lock()
        
        self._dialog_shown = False
        self._dialog_lock = threading.Lock()
        
    def _parse_episode_format(self, text):
        import re
        if not text:
            return None, None, None
        match = re.match(r'^(\d+)x(\d+)\s*(.*)', text)
        if match:
            season = int(match.group(1))
            episode = int(match.group(2))
            title = match.group(3).strip()
            return season, episode, title
        return None, None, None

    def _get_next_from_playlist(self):
        try:
            playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
            current_position = playlist.getposition()
            if current_position >= (playlist.size() - 1):
                return None
            next_item = playlist[current_position + 1]
            if hasattr(next_item, 'getVideoInfoTag'):
                info_tag = next_item.getVideoInfoTag()
                episode_title = info_tag.getTitle() if hasattr(info_tag, 'getTitle') else ''
                season = info_tag.getSeason() if hasattr(info_tag, 'getSeason') else 0
                episode = info_tag.getEpisode() if hasattr(info_tag, 'getEpisode') else 0
                if not season or not episode:
                    label = next_item.getLabel()
                    season_p, episode_p, title_p = self._parse_episode_format(label)
                    season = season_p if season_p else season
                    episode = episode_p if episode_p else episode
                    if not episode_title and title_p:
                        episode_title = title_p
                return {
                    'serie_name': info_tag.getTVShowTitle() if hasattr(info_tag, 'getTVShowTitle') else '',
                    'original_name': info_tag.getOriginalTitle() if hasattr(info_tag, 'getOriginalTitle') else '',
                    'next_season': season if season else 0,
                    'next_episode': episode if episode else 0,
                    'episode_title': episode_title,
                    'thumbnail': next_item.getArt('thumb'),
                    'fanart': next_item.getArt('fanart'),
                    'description': info_tag.getPlot() if hasattr(info_tag, 'getPlot') else ''
                }
            else:
                label = next_item.getLabel()
                season, episode, episode_title = self._parse_episode_format(label)
                return {
                    'serie_name': '',
                    'next_season': season if season else 0,
                    'next_episode': episode if episode else 0,
                    'episode_title': episode_title if episode_title else label,
                    'thumbnail': next_item.getArt('thumb'),
                    'fanart': next_item.getArt('fanart'),
                    'description': ''
                }
        except Exception:
            return None

    def start_monitoring(self, tmdb_id, season, episode):
        if not self.enabled:
            return
        
        with self._dialog_lock:
            self._dialog_shown = False
        
        with self._monitor_lock:
            self._stop_monitoring = True
            self.monitoring = False
        
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=3.0)
        
        playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
        if playlist.size() == 0 or playlist.getposition() >= (playlist.size() - 1):
            return
        
        next_info = self._get_next_from_playlist()
        if not next_info:
            return
        
        with self._monitor_lock:
            self.monitoring = True
            self._stop_monitoring = False
        
        self.monitor_thread = threading.Thread(
            target=self._monitoring_loop,
            args=(next_info,)
        )
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
    
    def _monitoring_loop(self, next_info):
        monitor = xbmc.Monitor()
        
        waited = 0
        max_wait_time = 30
        
        while waited < max_wait_time:
            if not self.player.isPlayingVideo():
                if monitor.waitForAbort(0.5):
                    with self._monitor_lock:
                        self.monitoring = False
                    return
                waited += 0.5
                continue
            else:
                break
        
        if not self.player.isPlayingVideo():
            with self._monitor_lock:
                self.monitoring = False
            return
        
        total_time = 0
        time_attempts = 0
        max_attempts = 60
        
        while time_attempts < max_attempts:
            try:
                total_time = self.player.getTotalTime()
                if total_time > 60:
                    break
            except:
                pass
            
            time_attempts += 1
            
            if self._stop_monitoring:
                with self._monitor_lock:
                    self.monitoring = False
                return
            
            monitor.waitForAbort(0.5)
        
        if total_time <= 60:
            with self._monitor_lock:
                self.monitoring = False
            return
        
        safety_margin = 30
        start_at_90_percent = total_time * 0.9
        start_at_trigger = total_time - self.trigger_seconds - safety_margin
        start_monitoring_at = min(start_at_90_percent, start_at_trigger)
        
        light_check_interval = 1
        
        while self.player.isPlayingVideo() and not self._stop_monitoring:
            try:
                current_time = self.player.getTime()
                
                if current_time >= start_monitoring_at:
                    break
                
                if monitor.waitForAbort(light_check_interval):
                    break
                    
            except Exception:
                break
        
        while self.player.isPlayingVideo() and not self._stop_monitoring:
            try:
                current_time = self.player.getTime()
                remaining_time = total_time - current_time
                
                with self._dialog_lock:
                    dialog_already_shown = self._dialog_shown
                
                if remaining_time <= self.trigger_seconds and not dialog_already_shown:
                    with self._dialog_lock:
                        if not self._dialog_shown:
                            self._dialog_shown = True
                            
                            self._show_upnext_dialog(next_info)
                            break
                        else:
                            break
                
                if monitor.waitForAbort(0.5):
                    break
                    
            except Exception:
                break
        
        with self._monitor_lock:
            self.monitoring = False
    
    def _show_upnext_dialog(self, next_info):
        try:
            import xbmcaddon
            addon = xbmcaddon.Addon()

            tmdb_id = getattr(self.player, 'tmdb_id', None)
            season  = getattr(self.player, 'season', None)
            episode = getattr(self.player, 'episode', None)

            dialog = UpNextDialog(
                'upnext-dialog.xml',
                addon.getAddonInfo('path'),
                'default',
                '1080i',
                next_episode_info=next_info,
                countdown_seconds=self.countdown_seconds,
                is_anime=False
            )
            dialog.doModal()

            if dialog.auto_play and not dialog.cancelled:
                if tmdb_id and season is not None and episode is not None:
                    try:
                        self.db.mark_tvshow_watched(tmdb_id, season, episode)
                    except Exception:
                        pass
                try:
                    total_time = self.player.getTotalTime()
                    if total_time > 0:
                        self.player.seekTime(total_time - 1)
                except Exception:
                    pass

            del dialog

        except Exception:
            pass
    
    def stop_monitoring(self):
        with self._monitor_lock:
            self._stop_monitoring = True
            was_monitoring = self.monitoring
            self.monitoring = False
        
        if was_monitoring and self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=3.0)
        
        with self._dialog_lock:
            self._dialog_shown = False
    
    def is_monitoring(self):
        with self._monitor_lock:
            return self.monitoring


class UpNextAnimeService:
    
    def __init__(self, player, database):
        self.player = player
        self.db = database
        
        import xbmcaddon
        addon = xbmcaddon.Addon()
        
        self.enabled = addon.getSettingBool('upnext_enabled') if hasattr(addon, 'getSettingBool') else True
        self.countdown_seconds = addon.getSettingInt('upnext_countdown_seconds') if hasattr(addon, 'getSettingInt') else 10
        self.trigger_seconds = addon.getSettingInt('upnext_trigger_seconds') if hasattr(addon, 'getSettingInt') else 30
        
        if self.countdown_seconds == 0:
            self.countdown_seconds = 10
        if self.trigger_seconds == 0:
            self.trigger_seconds = 30
        
        import xbmcvfs
        import os
        home_dir = addon.getAddonInfo('path')
        self.default_icon = xbmcvfs.translatePath(os.path.join(home_dir, 'resources', 'images', 'thunder.png'))
            
        self.monitoring = False
        self.monitor_thread = None
        self._stop_monitoring = False
        self._monitor_lock = threading.Lock()
        
        self._dialog_shown = False
        self._dialog_lock = threading.Lock()
    
    def _parse_anime_episode_format(self, text):
        import re
        if not text:
            return None, None
        match = re.match(r'^Ep\s+(\d+)\s*(.*)', text)
        if match:
            episode = int(match.group(1))
            title = match.group(2).strip()
            return episode, title
        return None, None

    def _get_next_from_playlist(self):
        try:
            playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
            current_position = playlist.getposition()
            if current_position >= (playlist.size() - 1):
                return None
            next_item = playlist[current_position + 1]
            if hasattr(next_item, 'getVideoInfoTag'):
                info_tag = next_item.getVideoInfoTag()
                episode_title = info_tag.getTitle() if hasattr(info_tag, 'getTitle') else ''
                episode = info_tag.getEpisode() if hasattr(info_tag, 'getEpisode') else 0
                if not episode:
                    label = next_item.getLabel()
                    ep_p, title_p = self._parse_anime_episode_format(label)
                    episode = ep_p if ep_p else 0
                    if not episode_title and title_p:
                        episode_title = title_p
                return {
                    'serie_name': info_tag.getTVShowTitle() if hasattr(info_tag, 'getTVShowTitle') else '',
                    'original_name': info_tag.getOriginalTitle() if hasattr(info_tag, 'getOriginalTitle') else '',
                    'next_season': None,
                    'next_episode': episode,
                    'episode_title': episode_title,
                    'thumbnail': self.default_icon,
                    'fanart': next_item.getArt('fanart'),
                    'description': info_tag.getPlot() if hasattr(info_tag, 'getPlot') else ''
                }
            else:
                label = next_item.getLabel()
                episode, episode_title = self._parse_anime_episode_format(label)
                return {
                    'serie_name': '',
                    'next_season': None,
                    'next_episode': episode if episode else 0,
                    'episode_title': episode_title if episode_title else label,
                    'thumbnail': self.default_icon,
                    'fanart': next_item.getArt('fanart'),
                    'description': ''
                }
        except Exception:
            return None

    def start_monitoring(self, mal_id, episode):
        if not self.enabled:
            return
        
        with self._dialog_lock:
            self._dialog_shown = False
        
        with self._monitor_lock:
            self._stop_monitoring = True
            self.monitoring = False
        
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=3.0)
        
        playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
        if playlist.size() == 0 or playlist.getposition() >= (playlist.size() - 1):
            return
        
        next_info = self._get_next_from_playlist()
        if not next_info:
            return
        
        with self._monitor_lock:
            self.monitoring = True
            self._stop_monitoring = False
        
        self.monitor_thread = threading.Thread(
            target=self._monitoring_loop,
            args=(next_info,)
        )
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
    
    def _monitoring_loop(self, next_info):
        monitor = xbmc.Monitor()
        
        waited = 0
        max_wait_time = 30
        
        while waited < max_wait_time:
            if not self.player.isPlayingVideo():
                if monitor.waitForAbort(0.5):
                    with self._monitor_lock:
                        self.monitoring = False
                    return
                waited += 0.5
                continue
            else:
                break
        
        if not self.player.isPlayingVideo():
            with self._monitor_lock:
                self.monitoring = False
            return
        
        total_time = 0
        time_attempts = 0
        max_attempts = 60
        
        while time_attempts < max_attempts:
            try:
                total_time = self.player.getTotalTime()
                if total_time > 60:
                    break
            except:
                pass
            
            time_attempts += 1
            
            if self._stop_monitoring:
                with self._monitor_lock:
                    self.monitoring = False
                return
            
            monitor.waitForAbort(0.5)
        
        if total_time <= 60:
            with self._monitor_lock:
                self.monitoring = False
            return
        
        safety_margin = 30
        start_at_90_percent = total_time * 0.9
        start_at_trigger = total_time - self.trigger_seconds - safety_margin
        start_monitoring_at = min(start_at_90_percent, start_at_trigger)
        
        light_check_interval = 1
        
        while self.player.isPlayingVideo() and not self._stop_monitoring:
            try:
                current_time = self.player.getTime()
                
                if current_time >= start_monitoring_at:
                    break
                
                if monitor.waitForAbort(light_check_interval):
                    break
                    
            except Exception:
                break
        
        while self.player.isPlayingVideo() and not self._stop_monitoring:
            try:
                current_time = self.player.getTime()
                remaining_time = total_time - current_time
                
                with self._dialog_lock:
                    dialog_already_shown = self._dialog_shown
                
                if remaining_time <= self.trigger_seconds and not dialog_already_shown:
                    with self._dialog_lock:
                        if not self._dialog_shown:
                            self._dialog_shown = True
                            
                            self._show_upnext_dialog(next_info)
                            break
                        else:
                            break
                
                if monitor.waitForAbort(0.5):
                    break
                    
            except Exception:
                break
        
        with self._monitor_lock:
            self.monitoring = False
    
    def _show_upnext_dialog(self, next_info):
        try:
            import xbmcaddon
            addon = xbmcaddon.Addon()

            mal_id  = getattr(self.player, 'mal_id', None)
            episode = getattr(self.player, 'episode', None)

            dialog = UpNextDialog(
                'upnext-dialog.xml',
                addon.getAddonInfo('path'),
                'default',
                '1080i',
                next_episode_info=next_info,
                countdown_seconds=self.countdown_seconds,
                is_anime=True
            )
            dialog.doModal()

            if dialog.auto_play and not dialog.cancelled:
                if mal_id and episode is not None:
                    try:
                        self.db.mark_anime_watched(mal_id, episode)
                    except Exception:
                        pass
                try:
                    total_time = self.player.getTotalTime()
                    if total_time > 0:
                        self.player.seekTime(total_time - 1)
                except Exception:
                    pass

            del dialog

        except Exception:
            pass
    
    def stop_monitoring(self):
        with self._monitor_lock:
            self._stop_monitoring = True
            was_monitoring = self.monitoring
            self.monitoring = False
        
        if was_monitoring and self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=3.0)
        
        with self._dialog_lock:
            self._dialog_shown = False
    
    def is_monitoring(self):
        with self._monitor_lock:
            return self.monitoring


_upnext_tvshow_service = None
_upnext_anime_service = None
_upnext_lock = threading.Lock()


def get_upnext_tvshow_service(player, database):
    global _upnext_tvshow_service
    
    with _upnext_lock:
        if _upnext_tvshow_service is None:
            _upnext_tvshow_service = UpNextTVShowService(player, database)
        return _upnext_tvshow_service


def get_upnext_anime_service(player, database):
    global _upnext_anime_service
    
    with _upnext_lock:
        if _upnext_anime_service is None:
            _upnext_anime_service = UpNextAnimeService(player, database)
        return _upnext_anime_service
