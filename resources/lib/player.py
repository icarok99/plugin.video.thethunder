# -*- coding: utf-8 -*-

import xbmc
import threading
from resources.lib.upnext import get_upnext_tvshow_service, get_upnext_anime_service
from resources.lib.httpclient import ThunderDatabase

db = ThunderDatabase()


class ThunderPlayer(xbmc.Player):

    def __init__(self):
        super(ThunderPlayer, self).__init__()

        self.tmdb_id = None
        self.mal_id = None
        self.season = None
        self.episode = None

        self._state_lock = threading.Lock()
        self._monitoring = False

        self.upnext_tvshow_service = get_upnext_tvshow_service(self, db)
        self.upnext_anime_service = get_upnext_anime_service(self, db)

    def start_monitoring_tvshow(self, tmdb_id, season, episode):
        with self._state_lock:
            self.tmdb_id = tmdb_id
            self.mal_id = None
            self.season = season
            self.episode = episode
            self._monitoring = True

        monitor = xbmc.Monitor()
        waited = 0
        max_wait = 30

        while waited < max_wait and not monitor.abortRequested():
            if self.isPlayingVideo() and self.getTotalTime() > 30:
                break
            monitor.waitForAbort(0.5)
            waited += 0.5

        if self.isPlayingVideo() and self._monitoring:
            self.upnext_tvshow_service.start_monitoring(self.tmdb_id, self.season, self.episode)

    def start_monitoring_anime(self, mal_id, episode):
        with self._state_lock:
            self.tmdb_id = None
            self.mal_id = mal_id
            self.season = None
            self.episode = episode
            self._monitoring = True

        monitor = xbmc.Monitor()
        waited = 0
        max_wait = 30

        while waited < max_wait and not monitor.abortRequested():
            if self.isPlayingVideo() and self.getTotalTime() > 30:
                break
            monitor.waitForAbort(0.5)
            waited += 0.5

        if self.isPlayingVideo() and self._monitoring:
            self.upnext_anime_service.start_monitoring(self.mal_id, self.episode)

    def onPlayBackStopped(self):
        with self._state_lock:
            self._monitoring = False
            self.tmdb_id = None
            self.mal_id = None
            self.season = None
            self.episode = None

        if self.upnext_tvshow_service:
            self.upnext_tvshow_service.stop_monitoring()
        if self.upnext_anime_service:
            self.upnext_anime_service.stop_monitoring()

    def onPlayBackEnded(self):
        with self._state_lock:
            tmdb_id = self.tmdb_id
            mal_id  = self.mal_id
            season  = self.season
            episode = self.episode
            self._monitoring = False
            self.tmdb_id = None
            self.mal_id = None
            self.season = None
            self.episode = None

        already_marked = (
            (self.upnext_tvshow_service and self.upnext_tvshow_service._watched_marked) or
            (self.upnext_anime_service and self.upnext_anime_service._watched_marked)
        )

        if not already_marked:
            if tmdb_id and season is not None and episode is not None:
                threading.Thread(
                    target=db.mark_tvshow_watched,
                    args=(tmdb_id, season, episode),
                    daemon=True
                ).start()
            elif mal_id and episode is not None:
                threading.Thread(
                    target=db.mark_anime_watched,
                    args=(mal_id, episode),
                    daemon=True
                ).start()

        if self.upnext_tvshow_service:
            self.upnext_tvshow_service.stop_monitoring()
        if self.upnext_anime_service:
            self.upnext_anime_service.stop_monitoring()

    def onPlayBackError(self):
        with self._state_lock:
            self._monitoring = False

        if self.upnext_tvshow_service:
            self.upnext_tvshow_service.stop_monitoring()
        if self.upnext_anime_service:
            self.upnext_anime_service.stop_monitoring()


_global_player = None
_player_lock = threading.Lock()


def get_player():
    global _global_player

    with _player_lock:
        if _global_player is None:
            _global_player = ThunderPlayer()
        return _global_player
