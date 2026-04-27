# -*- coding: utf-8 -*-

import xbmc
import threading
from resources.lib.upnext import get_upnext_tvshow_service, get_upnext_anime_service
from resources.lib.skipservice import get_skip_tvshow_service, get_skip_anime_service
from resources.lib.httpclient import ThunderDatabase

db = ThunderDatabase()

_skip_tvshow = get_skip_tvshow_service(db)
_skip_anime = get_skip_anime_service(db)

class ThunderPlayer(xbmc.Player):

    def __init__(self):
        super(ThunderPlayer, self).__init__()

        self.tmdb_id = None
        self.mal_id = None
        self.season = None
        self.episode = None

        self._state_lock = threading.Lock()
        self._monitoring = False
        self._watched_marked = False
        self._last_time = 0.0
        self._total_time = 0.0

        self.upnext_tvshow_service = get_upnext_tvshow_service(self, db, _skip_tvshow)
        self.upnext_anime_service = get_upnext_anime_service(self, db, _skip_anime)

    def start_monitoring_tvshow(self, tmdb_id, season, episode):
        with self._state_lock:
            self.tmdb_id = tmdb_id
            self.mal_id = None
            self.season = season
            self.episode = episode
            self._monitoring = True
            self._watched_marked = False
            self._last_time = 0.0
            self._total_time = 0.0

        monitor = xbmc.Monitor()
        waited = 0
        while waited < 30 and not monitor.abortRequested():
            if self.isPlayingVideo() and self.getTotalTime() > 60:
                break
            monitor.waitForAbort(0.5)
            waited += 0.5

        if not self.isPlayingVideo():
            with self._state_lock:
                self._monitoring = False
            return

        self.upnext_tvshow_service.start_monitoring(tmdb_id, season, episode)

        threading.Thread(
            target=self._monitoring_loop_tvshow,
            args=(tmdb_id, season, episode),
            daemon=True,
        ).start()

    def start_monitoring_anime(self, mal_id, episode):
        with self._state_lock:
            self.tmdb_id = None
            self.mal_id = mal_id
            self.season = None
            self.episode = episode
            self._monitoring = True
            self._watched_marked = False
            self._last_time = 0.0
            self._total_time = 0.0

        monitor = xbmc.Monitor()
        waited = 0
        while waited < 30 and not monitor.abortRequested():
            if self.isPlayingVideo() and self.getTotalTime() > 60:
                break
            monitor.waitForAbort(0.5)
            waited += 0.5

        if not self.isPlayingVideo():
            with self._state_lock:
                self._monitoring = False
            return

        self.upnext_anime_service.start_monitoring(mal_id, episode)

        threading.Thread(
            target=self._monitoring_loop_anime,
            args=(mal_id, episode),
            daemon=True,
        ).start()

    def _monitoring_loop_tvshow(self, tmdb_id, season, episode):
        self._run_monitoring_loop(is_anime=False)

    def _monitoring_loop_anime(self, mal_id, episode):
        self._run_monitoring_loop(is_anime=True)

    def _run_monitoring_loop(self, is_anime=False):
        monitor = xbmc.Monitor()

        total_time = 0
        for _ in range(60):
            with self._state_lock:
                if not self._monitoring:
                    return
            try:
                total_time = self.getTotalTime()
                if total_time > 60:
                    break
            except Exception:
                pass
            monitor.waitForAbort(0.5)

        if total_time <= 60:
            with self._state_lock:
                self._monitoring = False
            return

        with self._state_lock:
            self._total_time = total_time

        watched_at = total_time * 0.9

        while self.isPlayingVideo():
            with self._state_lock:
                if not self._monitoring:
                    break
            if monitor.abortRequested():
                break

            try:
                ct = self.getTime()
            except Exception:
                monitor.waitForAbort(0.5)
                continue

            with self._state_lock:
                self._last_time = ct

            if not self._watched_marked and ct >= watched_at:
                self._watched_marked = True
                if is_anime and self.mal_id:
                    threading.Thread(
                        target=db.mark_anime_watched,
                        args=(self.mal_id, self.episode),
                        daemon=True,
                    ).start()
                elif not is_anime and self.tmdb_id and self.season is not None:
                    threading.Thread(
                        target=db.mark_tvshow_watched,
                        args=(self.tmdb_id, self.season, self.episode),
                        daemon=True,
                    ).start()

            monitor.waitForAbort(0.5)

        with self._state_lock:
            self._monitoring = False

    def onPlayBackStopped(self):
        with self._state_lock:
            self._monitoring = False
            tmdb_id = self.tmdb_id
            mal_id = self.mal_id
            season = self.season
            episode = self.episode
            last_time = self._last_time
            total_time = self._total_time
            already_marked = self._watched_marked
            self._watched_marked = False
            self.tmdb_id = None
            self.mal_id = None
            self.season = None
            self.episode = None
            self._last_time = 0.0
            self._total_time = 0.0

        if not already_marked and total_time > 60 and last_time >= total_time * 0.9:
            if tmdb_id and season is not None and episode is not None:
                threading.Thread(
                    target=db.mark_tvshow_watched,
                    args=(tmdb_id, season, episode),
                    daemon=True,
                ).start()
            elif mal_id and episode is not None:
                threading.Thread(
                    target=db.mark_anime_watched,
                    args=(mal_id, episode),
                    daemon=True,
                ).start()

        if self.upnext_tvshow_service:
            self.upnext_tvshow_service.stop_monitoring()
        if self.upnext_anime_service:
            self.upnext_anime_service.stop_monitoring()

    def onPlayBackEnded(self):
        with self._state_lock:
            tmdb_id = self.tmdb_id
            mal_id = self.mal_id
            season = self.season
            episode = self.episode
            already_marked = self._watched_marked
            self._monitoring = False
            self._watched_marked = False
            self.tmdb_id = None
            self.mal_id = None
            self.season = None
            self.episode = None
            self._last_time = 0.0
            self._total_time = 0.0

        if not already_marked:
            if tmdb_id and season is not None and episode is not None:
                threading.Thread(
                    target=db.mark_tvshow_watched,
                    args=(tmdb_id, season, episode),
                    daemon=True,
                ).start()
            elif mal_id and episode is not None:
                threading.Thread(
                    target=db.mark_anime_watched,
                    args=(mal_id, episode),
                    daemon=True,
                ).start()

        if self.upnext_tvshow_service:
            self.upnext_tvshow_service.stop_monitoring()
        if self.upnext_anime_service:
            self.upnext_anime_service.stop_monitoring()

    def onPlayBackError(self):
        with self._state_lock:
            self._monitoring = False
            self._watched_marked = False
            self.tmdb_id = None
            self.mal_id = None
            self.season = None
            self.episode = None
            self._last_time = 0.0
            self._total_time = 0.0

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