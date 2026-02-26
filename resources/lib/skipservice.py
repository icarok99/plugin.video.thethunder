# -*- coding: utf-8 -*-

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import xbmc
import xbmcgui
import xbmcaddon

try:
    from resources.lib.helper import requests
except Exception:
    import requests

_addon = xbmcaddon.Addon()

INTRODB_URL = 'https://api.introdb.app/segments'
ANISKIP_URL = 'https://api.aniskip.com/v2/skip-times'

try:
    from resources.lib.httpclient import get_anime_skip_prefetch_window as _get_anime_prefetch_window
except Exception:
    def _get_anime_prefetch_window():
        try:
            value = int(_addon.getSetting('anime_skip_prefetch_limit') or '10')
            return max(10, min(20, value))
        except Exception:
            return 10

def _str(string_id):
    return _addon.getLocalizedString(string_id)

class SkipDialog(xbmcgui.WindowXMLDialog):

    BUTTON_SKIP = 4001
    BUTTON_CANCEL = 4002
    PROGRESS_BAR = 4004
    LABEL_EP = 4006
    IMAGE_THUMB = 4007

    def __init__(self, *args, **kwargs):
        self.seek_to = kwargs.get('seek_to', 0.0)
        self.countdown_seconds = kwargs.get('countdown_seconds', 5)
        self.episode_label = kwargs.get('episode_label', '')
        self.thumbnail = kwargs.get('thumbnail', '')
        self._stop_countdown = False
        self._countdown_thread = None
        self._player = xbmc.Player()

    def _do_seek(self):
        try:
            self._player.seekTime(self.seek_to)
        except Exception:
            pass

    def onInit(self):
        try:
            self.getControl(self.BUTTON_SKIP).setLabel(_str(32202).format(self.countdown_seconds))
            if self.episode_label:
                try:
                    self.getControl(self.LABEL_EP).setLabel(self.episode_label)
                except Exception:
                    pass
            if self.thumbnail:
                try:
                    self.getControl(self.IMAGE_THUMB).setImage(self.thumbnail)
                except Exception:
                    pass
            try:
                self.setFocusId(self.BUTTON_SKIP)
            except Exception:
                pass
            self._start_countdown()
        except Exception:
            pass

    def _start_countdown(self):
        self._stop_countdown = False
        self._countdown_thread = threading.Thread(target=self._countdown_loop, daemon=True)
        self._countdown_thread.start()

    def _countdown_loop(self):
        remaining = self.countdown_seconds
        while remaining > 0 and not self._stop_countdown:
            try:
                progress = int((remaining / float(self.countdown_seconds)) * 100)
                self.getControl(self.PROGRESS_BAR).setPercent(progress)
                self.getControl(self.BUTTON_SKIP).setLabel(_str(32202).format(remaining))
            except Exception:
                break
            time.sleep(1)
            remaining -= 1
        if not self._stop_countdown and remaining == 0:
            self._do_seek()
            self.close()

    def onClick(self, controlId):
        if controlId == self.BUTTON_SKIP:
            self._stop_countdown = True
            self._do_seek()
            self.close()
        elif controlId == self.BUTTON_CANCEL:
            self._stop_countdown = True
            self.close()

    def onAction(self, action):
        action_id = action.getId()
        if action_id in (xbmcgui.ACTION_SELECT_ITEM, xbmcgui.ACTION_PLAYER_PLAY):
            try:
                focused = self.getFocusId()
                if focused == self.BUTTON_SKIP:
                    self._stop_countdown = True
                    self._do_seek()
                    self.close()
                elif focused == self.BUTTON_CANCEL:
                    self._stop_countdown = True
                    self.close()
            except Exception:
                pass
        elif action_id in (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU,
                           xbmcgui.ACTION_STOP):
            self._stop_countdown = True
            self.close()

class SkipTVShowService:

    def __init__(self, database):
        self.db = database
        addon = xbmcaddon.Addon()
        self.enabled = self._get_bool(addon, 'skip_intro_enabled', True)
        self.auto_skip = self._get_bool(addon, 'skip_auto_skip', False)
        self.countdown_seconds = self._get_int(addon, 'skip_countdown_seconds', 5)
        self.tolerance = 2.0

    @staticmethod
    def _get_bool(addon, key, default):
        try:
            return addon.getSettingBool(key)
        except Exception:
            val = addon.getSetting(key)
            return default if val == '' else val.lower() == 'true'

    @staticmethod
    def _get_int(addon, key, default):
        try:
            v = addon.getSettingInt(key)
            return v if v > 0 else default
        except Exception:
            try:
                return int(addon.getSetting(key)) or default
            except Exception:
                return default

    def load(self, tmdb_id, season, episode):
        if not self.enabled:
            return {}
        imdb_id = self.db.get_tvshow_imdb_id(tmdb_id, season, episode)
        if not imdb_id:
            return {}
        skip_info = self._resolve_timestamps(imdb_id, season, episode)
        if skip_info:
            ep_label, thumbnail = self._resolve_episode_info(tmdb_id, season, episode)
            skip_info['_ep_label'] = ep_label
            skip_info['_thumbnail'] = thumbnail
        return skip_info or {}

    def prefetch_season(self, tmdb_id, season):
        try:
            episodes = self.db.get_tvshow_season_episodes(tmdb_id, season)
            if not episodes:
                return
            imdb_id = next(
                (ep.get('imdb_id') for ep in episodes if ep.get('imdb_id')),
                None
            )
            if imdb_id:
                prefetch_tvshow_skip_timestamps(imdb_id, season, len(episodes), self.db)
        except Exception:
            pass

    def _resolve_episode_info(self, tmdb_id, season, episode):
        try:
            meta = self.db.get_tvshow_episode(tmdb_id, int(season), int(episode))
            if meta:
                title = meta.get('episode_title') or ''
                thumbnail = meta.get('thumbnail') or ''
                ep_label = (
                    '{}x{:02d} - {}'.format(int(season), int(episode), title)
                    if title
                    else '{}x{:02d}'.format(int(season), int(episode))
                )
                return ep_label, thumbnail
        except Exception:
            pass
        return '', ''

    def _resolve_timestamps(self, imdb_id, season, episode):
        try:
            cached = self.db.get_tvshow_skip_timestamps(imdb_id, season, episode)
            if cached:
                return cached
            url = '{}?imdb_id={}&season={}&episode={}'.format(
                INTRODB_URL, imdb_id, season, episode)
            response = requests.get(url, timeout=6)
            if response.status_code == 200:
                data = response.json()
                seg = data.get('intro')
                if seg:
                    ts = {
                        'intro_start': float(seg.get('start_sec', 0)),
                        'intro_end':   float(seg.get('end_sec', 0)),
                        'source':      'api',
                    }
                    self.db.save_tvshow_skip_timestamps(imdb_id, season, episode, **ts)
                    return ts
            self.db.save_tvshow_skip_timestamps(imdb_id, season, episode, source='api')
        except Exception:
            pass
        return {}

    def show_dialog(self, seek_to, episode_label='', thumbnail=''):
        try:
            addon = xbmcaddon.Addon()
            dialog = SkipDialog(
                'skip-dialog.xml',
                addon.getAddonInfo('path'),
                'default', '1080i',
                seek_to=seek_to,
                countdown_seconds=self.countdown_seconds,
                episode_label=episode_label,
                thumbnail=thumbnail,
            )
            dialog.doModal()
            del dialog
        except Exception:
            pass

class SkipAnimeService:

    def __init__(self, database):
        self.db = database
        addon = xbmcaddon.Addon()
        self.enabled = self._get_bool(addon, 'skip_intro_enabled', True)
        self.auto_skip = self._get_bool(addon, 'skip_auto_skip', False)
        self.countdown_seconds = self._get_int(addon, 'skip_countdown_seconds', 5)
        self.tolerance = 2.0

        import xbmcvfs, os
        home_dir = addon.getAddonInfo('path')
        self.default_icon = xbmcvfs.translatePath(
            os.path.join(home_dir, 'resources', 'images', 'thunder.png')
        )

    @staticmethod
    def _get_bool(addon, key, default):
        try:
            return addon.getSettingBool(key)
        except Exception:
            val = addon.getSetting(key)
            return default if val == '' else val.lower() == 'true'

    @staticmethod
    def _get_int(addon, key, default):
        try:
            v = addon.getSettingInt(key)
            return v if v > 0 else default
        except Exception:
            try:
                return int(addon.getSetting(key)) or default
            except Exception:
                return default

    def load(self, mal_id, episode):
        if not self.enabled:
            return {}
        skip_info = self._resolve_timestamps(str(mal_id), int(episode))
        if skip_info:
            ep_label, thumbnail = self._resolve_episode_info(mal_id, episode)
            skip_info['_ep_label'] = ep_label
            skip_info['_thumbnail'] = thumbnail
        return skip_info or {}

    def prefetch_anime(self, mal_id, episode_count):
        try:
            prefetch_anime_skip_timestamps(str(mal_id), int(episode_count), self.db)
        except Exception:
            pass

    def _resolve_episode_info(self, mal_id, episode):
        try:
            meta = self.db.get_anime_episode(str(mal_id), int(episode))
            if meta:
                title = meta.get('episode_title') or ''
                thumbnail = self.default_icon
                ep_label = (
                    'Ep {:02d} - {}'.format(int(episode), title)
                    if title
                    else 'Ep {:02d}'.format(int(episode))
                )
                return ep_label, thumbnail
        except Exception:
            pass
        return '', self.default_icon

    def _resolve_timestamps(self, mal_id, episode):
        try:
            cached = self.db.get_anime_skip_timestamps(mal_id, episode)
            if cached:
                return cached
            url = '{}/{}/{}?types=op&episodeLength=0'.format(ANISKIP_URL, mal_id, episode)
            response = requests.get(url, timeout=6)
            if response.status_code == 200:
                data = response.json()
                results = data.get('results', [])
                ts = {}
                for result in results:
                    skip_type = result.get('skipType', '')
                    interval = result.get('interval', {})
                    if skip_type == 'op':
                        ts = {
                            'intro_start': float(interval.get('startTime', 0)),
                            'intro_end':   float(interval.get('endTime', 0)),
                            'source':      'api',
                        }
                        break
                if ts:
                    self.db.save_anime_skip_timestamps(mal_id, episode, **ts)
                    return ts
            self.db.save_anime_skip_timestamps(mal_id, episode, source='api')
        except Exception:
            pass
        return {}

    def show_dialog(self, seek_to, episode_label='', thumbnail=''):
        try:
            addon = xbmcaddon.Addon()
            dialog = SkipDialog(
                'skip-dialog.xml',
                addon.getAddonInfo('path'),
                'default', '1080i',
                seek_to=seek_to,
                countdown_seconds=self.countdown_seconds,
                episode_label=episode_label,
                thumbnail=thumbnail,
            )
            dialog.doModal()
            del dialog
        except Exception:
            pass

MAX_WORKERS = 5

_prefetched_tvshow = set()
_prefetched_tvshow_lock = threading.Lock()
_pftvshow_running = set()
_pftvshow_running_lock = threading.Lock()

def prefetch_tvshow_skip_timestamps(imdb_id, season, episode_count, database):
    if not imdb_id or not season:
        return
    key = (imdb_id, int(season))
    with _prefetched_tvshow_lock:
        if key in _prefetched_tvshow:
            return
    with _pftvshow_running_lock:
        if key in _pftvshow_running:
            return
        _pftvshow_running.add(key)
    threading.Thread(
        target=_prefetch_tvshow_worker,
        args=(imdb_id, int(season), int(episode_count), database),
        daemon=True,
    ).start()

def _fetch_tvshow_episode(imdb_id, season, ep):
    for attempt in range(3):
        try:
            url = '{}?imdb_id={}&season={}&episode={}'.format(INTRODB_URL, imdb_id, season, ep)
            response = requests.get(url, timeout=8)
            if response.status_code == 429:
                time.sleep(10 * (attempt + 1))
                continue
            if response.status_code == 200:
                data = response.json()
                seg = data.get('intro')
                if seg:
                    return (ep, float(seg.get('start_sec', 0)), float(seg.get('end_sec', 0)))
                return (ep, None, None)
            return (ep, None, None)
        except Exception:
            time.sleep(2)
    return (ep, None, None)

def _prefetch_tvshow_worker(imdb_id, season, episode_count, database):
    key = (imdb_id, season)
    try:
        candidates = list(range(1, episode_count + 1)) if episode_count > 0 else []
        if not candidates:
            return
        pending = [ep for ep in candidates
                   if not database.tvshow_skip_checked(imdb_id, season, ep)]
        if not pending:
            return
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(_fetch_tvshow_episode, imdb_id, season, ep): ep
                for ep in pending
            }
            for future in as_completed(futures):
                try:
                    ep, intro_start, intro_end = future.result()
                except Exception:
                    continue
                try:
                    database.save_tvshow_skip_timestamps(
                        imdb_id, season, ep,
                        intro_start=intro_start,
                        intro_end=intro_end,
                        source='api',
                    )
                except Exception:
                    pass
        with _prefetched_tvshow_lock:
            _prefetched_tvshow.add(key)
    finally:
        with _pftvshow_running_lock:
            _pftvshow_running.discard(key)

_prefetched_anime = set()
_prefetched_anime_lock = threading.Lock()
_pfanime_running = set()
_pfanime_running_lock = threading.Lock()

def prefetch_anime_skip_timestamps(mal_id, episode_count, database):
    if not mal_id:
        return
    key = str(mal_id)
    with _prefetched_anime_lock:
        if key in _prefetched_anime:
            return
    with _pfanime_running_lock:
        if key in _pfanime_running:
            return
        _pfanime_running.add(key)
    threading.Thread(
        target=_prefetch_anime_worker,
        args=(str(mal_id), int(episode_count), database),
        daemon=True,
    ).start()

def _fetch_anime_episode(mal_id, ep):
    for attempt in range(3):
        try:
            url = '{}/{}/{}?types=op&episodeLength=0'.format(ANISKIP_URL, mal_id, ep)
            response = requests.get(url, timeout=8)
            if response.status_code == 429:
                time.sleep(10 * (attempt + 1))
                continue
            if response.status_code == 200:
                data = response.json()
                results = data.get('results', [])
                for result in results:
                    skip_type = result.get('skipType', '')
                    interval = result.get('interval', {})
                    if skip_type == 'op':
                        return (ep,
                                float(interval.get('startTime', 0)),
                                float(interval.get('endTime', 0)))
                return (ep, None, None)
            return (ep, None, None)
        except Exception:
            time.sleep(2)
    return (ep, None, None)

def _prefetch_anime_worker(mal_id, episode_count, database):
    key = mal_id
    try:
        if episode_count <= 0:
            return

        # Janela absoluta: sempre cobre episódios 1..window.
        # Não usa janela deslizante para evitar buscas ilimitadas entre sessões.
        window = _get_anime_prefetch_window()
        window_end = min(episode_count, window)

        candidates = list(range(1, window_end + 1))
        pending = [ep for ep in candidates
                      if not database.anime_skip_checked(mal_id, ep)]
        if not pending:
            return
        for i, ep in enumerate(pending):
            if i > 0:
                time.sleep(0.5)
            try:
                ep_result, intro_start, intro_end = _fetch_anime_episode(mal_id, ep)
                database.save_anime_skip_timestamps(
                    mal_id, ep_result,
                    intro_start=intro_start,
                    intro_end=intro_end,
                    source='api',
                )
            except Exception:
                pass
        with _prefetched_anime_lock:
            _prefetched_anime.add(key)
    finally:
        with _pfanime_running_lock:
            _pfanime_running.discard(key)

_skip_tvshow_service = None
_skip_anime_service = None
_skip_lock = threading.Lock()

def get_skip_tvshow_service(database):
    global _skip_tvshow_service
    with _skip_lock:
        if _skip_tvshow_service is None:
            _skip_tvshow_service = SkipTVShowService(database)
        return _skip_tvshow_service

def get_skip_anime_service(database):
    global _skip_anime_service
    with _skip_lock:
        if _skip_anime_service is None:
            _skip_anime_service = SkipAnimeService(database)
        return _skip_anime_service