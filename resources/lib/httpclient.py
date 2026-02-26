# -*- coding: utf-8 -*-

import os
import json
import time
import hashlib
import sqlite3
import xbmcvfs
import xbmcaddon
from datetime import datetime
from urllib.parse import quote
from contextlib import contextmanager
from resources.lib.helper import requests
from resources.lib.utils import get_current_date

addon = xbmcaddon.Addon()

def getString(string_id):
    return addon.getLocalizedString(string_id)

TRANSLATE   = xbmcvfs.translatePath
profile_dir = TRANSLATE(addon.getAddonInfo('profile'))
db_file     = os.path.join(profile_dir, 'media.db')

if not xbmcvfs.exists(profile_dir):
    xbmcvfs.mkdirs(profile_dir)

API_KEY    = '92c1507cc18d85290e7a0b96abb37316'
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36'

_ANIME_PREFETCH_MIN = 10
_ANIME_PREFETCH_MAX = 20

def get_anime_skip_prefetch_window():
    try:
        value = int(addon.getSetting('anime_skip_prefetch_limit') or str(_ANIME_PREFETCH_MIN))
        return max(_ANIME_PREFETCH_MIN, min(_ANIME_PREFETCH_MAX, value))
    except Exception:
        return _ANIME_PREFETCH_MIN

_season_cache = {}

_db_initialized = False

def _check_expiry_once():
    from resources.lib.cache_manager import check_auto_expiry
    check_auto_expiry()

_check_expiry_once()

@contextmanager
def get_connection():
    global _db_initialized
    if not _db_initialized:
        _db_initialized = True
        init_db()
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    conn   = sqlite3.connect(db_file)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cache (
                url_hash  TEXT PRIMARY KEY,
                data      TEXT NOT NULL,
                timestamp REAL NOT NULL
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS episodes_tvshows (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                tmdb_id        TEXT    NOT NULL,
                season         INTEGER NOT NULL,
                episode        INTEGER NOT NULL,
                episode_title  TEXT,
                description    TEXT,
                thumbnail      TEXT,
                fanart         TEXT,
                serie_name     TEXT,
                original_name  TEXT,
                imdb_id        TEXT,
                is_last_episode TEXT DEFAULT 'no',
                created_at     TEXT,
                updated_at     TEXT,
                UNIQUE(tmdb_id, season, episode)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS episodes_animes (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                mal_id             TEXT    NOT NULL,
                episode            INTEGER NOT NULL,
                episode_title      TEXT,
                description        TEXT,
                thumbnail          TEXT,
                anime_name         TEXT,
                anime_name_english TEXT,
                is_last_episode    TEXT DEFAULT 'no',
                created_at         TEXT,
                updated_at         TEXT,
                UNIQUE(mal_id, episode)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS watched_episodes (
                content_type TEXT    NOT NULL,
                content_id   TEXT    NOT NULL,
                season       INTEGER,
                episode      INTEGER NOT NULL,
                watched_at   TEXT,
                PRIMARY KEY (content_type, content_id, season, episode)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS skip_timestamps_tvshow (
                imdb_id     TEXT    NOT NULL,
                season      INTEGER NOT NULL,
                episode     INTEGER NOT NULL,
                intro_start REAL,
                intro_end   REAL,
                source      TEXT    DEFAULT 'api',
                updated_at  TEXT,
                PRIMARY KEY (imdb_id, season, episode)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS skip_timestamps_anime (
                mal_id      TEXT    NOT NULL,
                episode     INTEGER NOT NULL,
                intro_start REAL,
                intro_end   REAL,
                source      TEXT    DEFAULT 'api',
                updated_at  TEXT,
                PRIMARY KEY (mal_id, episode)
            )
        ''')

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tvshows_season   ON episodes_tvshows(tmdb_id, season)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_animes_mal       ON episodes_animes(mal_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_skip_tvshow      ON skip_timestamps_tvshow(imdb_id, season)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_skip_anime       ON skip_timestamps_anime(mal_id)')

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def get_config_ttl():
    try:
        days = int(addon.getSetting('cache_ttl_days') or '7')
        return days * 86400 if days > 0 else 0
    except Exception:
        return 7 * 86400

def clean_expired_cache(ttl_seconds):
    if ttl_seconds <= 0:
        return
    current_time = time.time()
    with get_connection() as conn:
        conn.cursor().execute(
            'DELETE FROM cache WHERE timestamp < ?', (current_time - ttl_seconds,)
        )

def save_to_cache(url, data):
    hash_val = hashlib.md5(url.encode()).hexdigest()
    with get_connection() as conn:
        conn.cursor().execute('''
            INSERT OR REPLACE INTO cache (url_hash, data, timestamp)
            VALUES (?, ?, ?)
        ''', (hash_val, json.dumps(data), time.time()))

def get_json(url, ttl=None):
    if ttl is None:
        ttl = get_config_ttl()

    try:
        cache_ttl_days    = int(addon.getSetting('cache_ttl_days') or '7')
        cache_ttl_seconds = cache_ttl_days * 86400 if cache_ttl_days > 0 else 0

        if cache_ttl_days == 0:
            from resources.lib.cache_manager import clear_cache
            clear_cache()
        elif cache_ttl_days > 0:
            clean_expired_cache(cache_ttl_seconds)
    except Exception:
        pass

    hash_val = hashlib.md5(url.encode()).hexdigest()

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT data, timestamp FROM cache WHERE url_hash = ?', (hash_val,))
        row = cursor.fetchone()
        if row:
            cached_data, timestamp = row[0], row[1]
            if time.time() - timestamp < ttl:
                return json.loads(cached_data)

    try:
        r = requests.get(url, headers={'User-Agent': USER_AGENT}, timeout=10)
        r.raise_for_status()
        data = r.json()
        save_to_cache(url, data)
        return data
    except Exception:
        return {}

def save_tvshow_season_episodes(tmdb_id, season, serie_name, original_name,
                                episodes_data, last_episode_num=None, imdb_id=None):
    if not episodes_data:
        return

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if last_episode_num is None:
        last_episode_num = max([int(ep[0]) for ep in episodes_data])

    batch_data = []
    for ep_data in episodes_data:
        episode_num = int(ep_data[0])
        title       = ep_data[1] if len(ep_data) > 1 else ''
        description = ep_data[2] if len(ep_data) > 2 else ''
        thumbnail   = ep_data[3] if len(ep_data) > 3 else ''
        fanart      = ep_data[4] if len(ep_data) > 4 else ''
        is_last     = 'yes' if episode_num == last_episode_num else 'no'
        batch_data.append((
            tmdb_id, season, episode_num, title, description,
            thumbnail, fanart, serie_name, original_name, imdb_id, is_last, now, now
        ))

    with get_connection() as conn:
        conn.executemany('''
            INSERT INTO episodes_tvshows
            (tmdb_id, season, episode, episode_title, description, thumbnail,
             fanart, serie_name, original_name, imdb_id, is_last_episode, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tmdb_id, season, episode)
            DO UPDATE SET
                episode_title   = excluded.episode_title,
                description     = excluded.description,
                thumbnail       = excluded.thumbnail,
                fanart          = excluded.fanart,
                serie_name      = excluded.serie_name,
                original_name   = excluded.original_name,
                imdb_id         = COALESCE(excluded.imdb_id, imdb_id),
                is_last_episode = excluded.is_last_episode,
                updated_at      = excluded.updated_at
        ''', batch_data)

def process_and_save_tvshow_season(tmdb_id, season_data, imdb_id=None):
    if not season_data or 'episodes' not in season_data:
        return False
    try:
        season_number = season_data.get('season_number', 0)
        serie_name    = season_data.get('name', '')
        episodes_list = season_data.get('episodes', [])
        if not episodes_list:
            return False

        episodes_data = []
        for ep in episodes_list:
            thumbnail = ''
            if ep.get('still_path'):
                thumbnail = f"https://image.tmdb.org/t/p/w500{ep['still_path']}"
            episodes_data.append((
                ep.get('episode_number', 0),
                ep.get('name', ''),
                ep.get('overview', ''),
                thumbnail,
                ''
            ))

        save_tvshow_season_episodes(
            tmdb_id=str(tmdb_id),
            season=season_number,
            serie_name=serie_name,
            original_name=serie_name,
            episodes_data=episodes_data,
            imdb_id=imdb_id
        )
        return True
    except Exception:
        return False

def get_tvshow_episode(tmdb_id, season, episode):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM episodes_tvshows
            WHERE tmdb_id = ? AND season = ? AND episode = ?
        ''', (str(tmdb_id), season, episode))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_anime_episode(mal_id, episode):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM episodes_animes
            WHERE mal_id = ? AND episode = ?
        ''', (str(mal_id), episode))
        row = cursor.fetchone()
        return dict(row) if row else None

def search_movie_api(search, page=1):
    url = f'https://api.themoviedb.org/3/search/movie?api_key={API_KEY}&query={quote(search)}&page={page}&language={getString(30700)}'
    src = get_json(url)
    return src.get('total_pages', 0), src.get('results', [])

def search_tvshow_api(search, page=1):
    url = f'https://api.themoviedb.org/3/search/tv?api_key={API_KEY}&query={quote(search)}&page={page}&language={getString(30700)}'
    src = get_json(url)
    return src.get('total_pages', 0), src.get('results', [])

def search_anime_api(search, page=1):
    url = f'https://api.jikan.moe/v4/anime?q={quote(search)}&page={page}'
    src = get_json(url)
    return src.get('pagination', {}).get('last_visible_page', 0), src.get('data', [])

def movies_popular_api(page=1):
    url = f'https://api.themoviedb.org/3/movie/popular?api_key={API_KEY}&page={page}&language={getString(30700)}'
    src = get_json(url)
    return src.get('total_pages', 0), src.get('results', [])

def movies_api(page, t):
    url_map = {
        'premiere': f'https://api.themoviedb.org/3/movie/now_playing?api_key={API_KEY}&page={page}&language={getString(30700)}',
        'trending': f'https://api.themoviedb.org/3/trending/movie/day?api_key={API_KEY}&page={page}&language={getString(30700)}'
    }
    url = url_map.get(t)
    if not url:
        return 0, []
    src = get_json(url)
    return src.get('total_pages', 0), src.get('results', [])

def open_movie_api(id):
    url = f'https://api.themoviedb.org/3/movie/{id}?api_key={API_KEY}&append_to_response=external_ids&language={getString(30700)}'
    return get_json(url)

def tv_shows_popular_api(page=1):
    url = f'https://api.themoviedb.org/3/discover/tv?api_key={API_KEY}&page={page}&language={getString(30700)}&sort_by=popularity.desc&without_keywords=210024&include_adult=false&vote_average.lte=10&vote_count.gte=100'
    src = get_json(url)
    return src.get('total_pages', 0), src.get('results', [])

def tv_shows_trending_api(page=1):
    url = f'https://api.themoviedb.org/3/discover/tv?api_key={API_KEY}&page={page}&language={getString(30700)}&sort_by=popularity.desc&without_keywords=210024,161919&include_adult=false'
    src = get_json(url)
    return src.get('total_pages', 0), src.get('results', [])

def tv_shows_premiere_api(page=1):
    year = get_current_date()[:4]
    url  = f'https://api.themoviedb.org/3/discover/tv?api_key={API_KEY}&sort_by=popularity.desc&first_air_date_year={year}&page={page}&language={getString(30700)}&without_keywords=210024'
    src  = get_json(url)
    return src.get('total_pages', 0), src.get('results', [])

def open_season_api(id):
    url = f'https://api.themoviedb.org/3/tv/{id}?api_key={API_KEY}&append_to_response=external_ids&language={getString(30700)}'
    return get_json(url)

def _update_season_imdb_id(tmdb_id, season, imdb_id):
    with get_connection() as conn:
        conn.cursor().execute('''
            UPDATE episodes_tvshows
            SET imdb_id = ?, updated_at = ?
            WHERE tmdb_id = ? AND season = ?
              AND (imdb_id IS NULL OR imdb_id = '')
        ''', (imdb_id, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), tmdb_id, season))

def show_episode_api(id, season, imdb_id=None):
    cache_key = f'{id}_{season}'

    if not imdb_id:
        try:
            serie_url  = f'https://api.themoviedb.org/3/tv/{id}?api_key={API_KEY}&append_to_response=external_ids'
            serie_data = get_json(serie_url)
            if serie_data:
                imdb_id = serie_data.get('external_ids', {}).get('imdb_id', '') or None
        except Exception:
            pass

    if cache_key in _season_cache:
        if imdb_id:
            try:
                _update_season_imdb_id(str(id), int(season), imdb_id)
            except Exception:
                pass
        return _season_cache[cache_key]

    url  = f'https://api.themoviedb.org/3/tv/{id}/season/{season}?api_key={API_KEY}&language={getString(30700)}'
    data = get_json(url)

    if data and 'episodes' in data:
        try:
            process_and_save_tvshow_season(id, data, imdb_id)
        except Exception:
            pass

    _season_cache[cache_key] = data
    return data

def find_tv_show_api(imdb):
    url = f'https://api.themoviedb.org/3/find/{imdb}?api_key={API_KEY}&external_source=imdb_id&language={getString(30700)}'
    return get_json(url)

def animes_popular_api(page=1):
    url = f'https://api.jikan.moe/v4/top/anime?page={page}&filter=bypopularity'
    src = get_json(url)
    return src.get('pagination', {}).get('last_visible_page', 0), src.get('data', [])

def animes_airing_api(page=1):
    url = f'https://api.jikan.moe/v4/seasons/now?page={page}'
    src = get_json(url)
    return src.get('pagination', {}).get('last_visible_page', 0), src.get('data', [])

def animes_by_season_api(year, season, page=1):
    url = f'https://api.jikan.moe/v4/seasons/{year}/{season}?page={page}'
    src = get_json(url)
    return src.get('pagination', {}).get('last_visible_page', 0), src.get('data', [])

def open_anime_api(id):
    url = f'https://api.jikan.moe/v4/anime/{id}/full'
    return get_json(url)

def open_anime_episodes_api(id):
    cache_url = f'https://cache.jikan.moe/anime/{id}/episodes_full'
    cached    = get_json(cache_url)
    if cached and 'episodes' in cached:
        return cached['episodes']

    all_episodes  = []
    page          = 1
    first_request = True

    while True:
        url      = f'https://api.jikan.moe/v4/anime/{id}/episodes?page={page}'
        src      = get_json(url)
        episodes = src.get('data', [])
        if not episodes:
            break
        all_episodes.extend(episodes)
        if not src.get('pagination', {}).get('has_next_page', False):
            break
        page += 1
        if not first_request:
            time.sleep(0.4)
        first_request = False

    if not all_episodes:
        return all_episodes

    try:
        anime_info         = open_anime_api(id).get('data', {})
        anime_name         = anime_info.get('title', '')
        anime_name_english = anime_info.get('title_english', '')
        now                = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        last_ep            = max(ep.get('mal_id', 0) for ep in all_episodes)

        batch_data = []
        for ep in all_episodes:
            episode_num = ep.get('mal_id', 0)
            title = ep.get('title', '')
            if ep.get('title_english'):
                title = ep.get('title_english')
            elif ep.get('title_romanji'):
                title = ep.get('title_romanji')
            batch_data.append((
                str(id), episode_num,
                title, ep.get('synopsis', '') or '', ep.get('url', ''),
                anime_name, anime_name_english,
                'yes' if episode_num == last_ep else 'no',
                now, now
            ))

        with get_connection() as conn:
            save_to_cache(cache_url, {'episodes': all_episodes})
            conn.executemany('''
                INSERT INTO episodes_animes
                (mal_id, episode, episode_title, description, thumbnail,
                 anime_name, anime_name_english, is_last_episode, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(mal_id, episode)
                DO UPDATE SET
                    episode_title      = excluded.episode_title,
                    description        = excluded.description,
                    thumbnail          = excluded.thumbnail,
                    anime_name         = excluded.anime_name,
                    anime_name_english = excluded.anime_name_english,
                    is_last_episode    = excluded.is_last_episode,
                    updated_at         = excluded.updated_at
            ''', batch_data)
    except Exception:
        pass

    return all_episodes

def cleanhtml(raw_html):
    import re
    return re.sub(re.compile('<.*?>'), '', raw_html)

def get_date():
    src          = get_json('http://worldtimeapi.org/api/timezone/America/New_York')
    datetime_str = src.get('datetime', '')
    if datetime_str:
        return datetime_str.split('-')[0], datetime_str.split('T')[0]
    from datetime import date
    today = date.today()
    return str(today.year), str(today)

class ThunderDatabase:

    def __init__(self):
        pass

    def get_tvshow_episode(self, tmdb_id, season, episode):
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM episodes_tvshows
                WHERE tmdb_id = ? AND season = ? AND episode = ?
            ''', (str(tmdb_id), int(season), int(episode)))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_anime_episode(self, mal_id, episode):
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM episodes_animes
                WHERE mal_id = ? AND episode = ?
            ''', (str(mal_id), int(episode)))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_tvshow_season_episodes(self, tmdb_id, season):
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM episodes_tvshows
                WHERE tmdb_id = ? AND season = ?
                ORDER BY episode
            ''', (str(tmdb_id), int(season)))
            return [dict(row) for row in cursor.fetchall()]

    def get_anime_all_episodes(self, mal_id):
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM episodes_animes
                WHERE mal_id = ?
                ORDER BY episode
            ''', (str(mal_id),))
            return [dict(row) for row in cursor.fetchall()]

    def mark_tvshow_watched(self, tmdb_id, season, episode):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with get_connection() as conn:
            conn.cursor().execute('''
                INSERT OR REPLACE INTO watched_episodes
                    (content_type, content_id, season, episode, watched_at)
                VALUES ('tvshow', ?, ?, ?, ?)
            ''', (str(tmdb_id), int(season), int(episode), now))

    def mark_anime_watched(self, mal_id, episode):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with get_connection() as conn:
            conn.cursor().execute('''
                INSERT OR REPLACE INTO watched_episodes
                    (content_type, content_id, season, episode, watched_at)
                VALUES ('anime', ?, 0, ?, ?)
            ''', (str(mal_id), int(episode), now))

    def get_watched_tvshow_in_season(self, tmdb_id, season):
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT episode FROM watched_episodes
                WHERE content_type = 'tvshow' AND content_id = ? AND season = ?
            ''', (str(tmdb_id), int(season)))
            return {row[0] for row in cursor.fetchall()}

    def get_watched_anime_episodes(self, mal_id):
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT episode FROM watched_episodes
                WHERE content_type = 'anime' AND content_id = ?
            ''', (str(mal_id),))
            return {row[0] for row in cursor.fetchall()}

    def get_tvshow_imdb_id(self, tmdb_id, season, episode):
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT imdb_id FROM episodes_tvshows
                WHERE tmdb_id = ? AND season = ? AND episode = ?
            ''', (str(tmdb_id), int(season), int(episode)))
            row = cursor.fetchone()
            if row and row[0]:
                return row[0]
            cursor.execute('''
                SELECT imdb_id FROM episodes_tvshows
                WHERE tmdb_id = ? AND season = ?
                  AND imdb_id IS NOT NULL AND imdb_id != ''
                LIMIT 1
            ''', (str(tmdb_id), int(season)))
            row = cursor.fetchone()
            return row[0] if row else None

    def get_tvshow_skip_timestamps(self, imdb_id, season, episode):
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT intro_start, intro_end, source
                FROM skip_timestamps_tvshow
                WHERE imdb_id = ? AND season = ? AND episode = ?
            ''', (imdb_id, int(season), int(episode)))
            row = cursor.fetchone()
            if not row:
                return None
            intro_start, intro_end, source = row
            if intro_start is None or intro_end is None:
                return None
            return {'intro_start': intro_start, 'intro_end': intro_end, 'source': source}

    def save_tvshow_skip_timestamps(self, imdb_id, season, episode,
                                    intro_start=None, intro_end=None, source='api'):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with get_connection() as conn:
            conn.cursor().execute('''
                INSERT INTO skip_timestamps_tvshow
                    (imdb_id, season, episode, intro_start, intro_end, source, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(imdb_id, season, episode)
                DO UPDATE SET
                    intro_start = COALESCE(excluded.intro_start, intro_start),
                    intro_end   = COALESCE(excluded.intro_end,   intro_end),
                    source      = excluded.source,
                    updated_at  = excluded.updated_at
            ''', (imdb_id, int(season), int(episode), intro_start, intro_end, source, now))

    def tvshow_skip_checked(self, imdb_id, season, episode):
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT 1 FROM skip_timestamps_tvshow WHERE imdb_id = ? AND season = ? AND episode = ?',
                (imdb_id, int(season), int(episode))
            )
            return cursor.fetchone() is not None

    def get_anime_skip_timestamps(self, mal_id, episode):
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT intro_start, intro_end, source
                FROM skip_timestamps_anime
                WHERE mal_id = ? AND episode = ?
            ''', (str(mal_id), int(episode)))
            row = cursor.fetchone()
            if not row:
                return None
            intro_start, intro_end, source = row
            if intro_start is None or intro_end is None:
                return None
            return {'intro_start': intro_start, 'intro_end': intro_end, 'source': source}

    def save_anime_skip_timestamps(self, mal_id, episode,
                                   intro_start=None, intro_end=None, source='api'):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with get_connection() as conn:
            conn.cursor().execute('''
                INSERT INTO skip_timestamps_anime
                    (mal_id, episode, intro_start, intro_end, source, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(mal_id, episode)
                DO UPDATE SET
                    intro_start = COALESCE(excluded.intro_start, intro_start),
                    intro_end   = COALESCE(excluded.intro_end,   intro_end),
                    source      = excluded.source,
                    updated_at  = excluded.updated_at
            ''', (str(mal_id), int(episode), intro_start, intro_end, source, now))

    def anime_skip_checked(self, mal_id, episode):
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT 1 FROM skip_timestamps_anime WHERE mal_id = ? AND episode = ?',
                (str(mal_id), int(episode))
            )
            return cursor.fetchone() is not None

    def get_anime_skip_checked_count(self, mal_id):
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT MAX(episode) FROM skip_timestamps_anime WHERE mal_id = ?',
                (str(mal_id),)
            )
            row = cursor.fetchone()
            return row[0] if row and row[0] else 0

    def get_next_tvshow_episode_metadata(self, tmdb_id, season, episode):
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM episodes_tvshows
                WHERE tmdb_id = ? AND season = ? AND episode IN (?, ?)
                ORDER BY episode
            ''', (str(tmdb_id), int(season), int(episode), int(episode) + 1))
            rows = cursor.fetchall()
            if not rows:
                return None
            current_ep = None
            next_ep    = None
            for row in rows:
                d = dict(row)
                if d['episode'] == int(episode):
                    current_ep = d
                elif d['episode'] == int(episode) + 1:
                    next_ep = d
            if current_ep and current_ep.get('is_last_episode') == 'yes':
                return None
            return next_ep

    def get_next_anime_episode_metadata(self, mal_id, episode):
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM episodes_animes
                WHERE mal_id = ? AND episode IN (?, ?)
                ORDER BY episode
            ''', (str(mal_id), int(episode), int(episode) + 1))
            rows = cursor.fetchall()
            if not rows:
                return None
            current_ep = None
            next_ep    = None
            for row in rows:
                d = dict(row)
                if d['episode'] == int(episode):
                    current_ep = d
                elif d['episode'] == int(episode) + 1:
                    next_ep = d
            if current_ep and current_ep.get('is_last_episode') == 'yes':
                return None
            return next_ep
