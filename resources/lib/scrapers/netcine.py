# -*- coding: utf-8 -*-
WEBSITE = 'NETCINE'

import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin
import re
import difflib
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from resources.lib.resolver import Resolver

try:
    import xbmcaddon
    addon = xbmcaddon.Addon()
    DUBBED = addon.getLocalizedString(30200)
    SUBTITLED = addon.getLocalizedString(30202)
except:
    DUBBED = 'DUBLADO'
    SUBTITLED = 'LEGENDADO'

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"

session = requests.Session()
session.verify = False
session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Referer": "https://netcinett.lat/"
})

tmdb_session = requests.Session()
tmdb_session.verify = False
tmdb_session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})

TMDB_BASE = "https://www.themoviedb.org"

def get_last_base(original_url):
    try:
        r = session.get(original_url, allow_redirects=True, timeout=10)
        final_url = r.url.rstrip('/')
        if "netcine" in final_url.lower():
            return final_url + "/"
    except:
        pass
    return original_url.rstrip('/') + "/"

ORIGINAL_BASE = "https://netcinett.lat"
HOST = get_last_base(ORIGINAL_BASE)

def clean_title(title):
    return re.sub(r'[:\-—]', ' ', title).strip()

def _scrape_tmdb_page(media_type, tmdb_id, language=None):
    url = "{}/{}/{}".format(TMDB_BASE, media_type, tmdb_id)
    params = {"language": language} if language else {}
    try:
        r = tmdb_session.get(url, params=params, timeout=10)
        if r.status_code != 200:
            return '', ''
        soup = BeautifulSoup(r.text, 'html.parser')
        og_title = soup.find('meta', property='og:title')
        title = og_title['content'].strip() if og_title and og_title.get('content') else ''
        year = ''
        page_title_tag = soup.find('title')
        if page_title_tag:
            m = re.search(r'\((?:TV Series )?(\d{4})', page_title_tag.get_text())
            if m:
                year = m.group(1)
        return title, year
    except:
        return '', ''

class source:
    __site_url__ = [HOST]

    @classmethod
    def find_title(cls, tmdb_id, media_type='movie'):
        title_pt, year = _scrape_tmdb_page(media_type, tmdb_id, language='pt-BR')
        original_title, year_orig = _scrape_tmdb_page(media_type, tmdb_id, language=None)
        if not title_pt:
            title_pt = original_title
        if not year:
            year = year_orig
        return title_pt, original_title, year

    @classmethod
    def search_movies(cls, tmdb_id, year):
        title_pt, original_title, tmdb_year = cls.find_title(tmdb_id, media_type='movie')
        if not tmdb_year:
            return []
        search_titles = []
        if title_pt:
            search_titles.append((title_pt, True))
        if original_title and original_title != title_pt:
            search_titles.append((original_title, False))
        for search_title, is_pt in search_titles:
            clean_search = clean_title(search_title)
            search_url = HOST + "?s=" + quote_plus(clean_search)
            try:
                r = session.get(search_url, timeout=15)
                if r.status_code != 200:
                    continue
                soup = BeautifulSoup(r.text, 'html.parser')
                items = soup.select("#box_movies .movie")
                for item in items:
                    a = item.select_one(".imagen a")
                    if not a:
                        continue
                    href = urljoin(HOST, a["href"])
                    if "/tvshows/" in href:
                        continue
                    page_title = item.select_one("h2").get_text(strip=True)
                    year_span = item.select_one("span.year")
                    page_year_raw = year_span.get_text(strip=True) if year_span else ""
                    page_year_match = re.search(r'\d{4}', page_year_raw)
                    page_year = page_year_match.group(0) if page_year_match else page_year_raw
                    if page_year != tmdb_year:
                        continue
                    clean_page = re.sub(r'(?i)\s*(dublado|legendado|hd|4k|1080p|720p|cam|ts).*', '', page_title).strip()
                    sim = difflib.SequenceMatcher(None, search_title.lower(), clean_page.lower()).ratio()
                    if sim >= 0.5:
                        return cls._get_players(href)
            except:
                pass
        return []

    @classmethod
    def search_tvshows(cls, tmdb_id, season, episode):
        title_pt, original_title, tmdb_year = cls.find_title(tmdb_id, media_type='tv')
        if not tmdb_year:
            return []
        search_titles = []
        if title_pt:
            search_titles.append((title_pt, True))
        if original_title and original_title != title_pt:
            search_titles.append((original_title, False))
        for search_title, is_pt in search_titles:
            clean_search = clean_title(search_title)
            search_url = HOST + "?s=" + quote_plus(clean_search)
            try:
                r = session.get(search_url, timeout=15)
                if r.status_code != 200:
                    continue
                soup = BeautifulSoup(r.text, 'html.parser')
                items = soup.select("#box_movies .movie")
                series_href = None
                for item in items:
                    a = item.select_one(".imagen a")
                    if not a or "/tvshows/" not in a["href"]:
                        continue
                    href = urljoin(HOST, a["href"])
                    page_title = item.select_one("h2").get_text(strip=True)
                    year_span = item.select_one("span.year")
                    page_year_raw = year_span.get_text(strip=True) if year_span else ""
                    page_year_match = re.search(r'\d{4}', page_year_raw)
                    page_year = page_year_match.group(0) if page_year_match else page_year_raw
                    if page_year != tmdb_year:
                        continue
                    clean_page = re.sub(r'(?i)\s*(dublado|legendado|hd|4k|1080p|720p|cam|ts).*', '', page_title).strip()
                    sim = difflib.SequenceMatcher(None, search_title.lower(), clean_page.lower()).ratio()
                    if sim >= 0.5:
                        series_href = href
                        break
                if not series_href:
                    continue
                r_series = session.get(series_href, timeout=15)
                soup_series = BeautifulSoup(r_series.text, 'html.parser')
                episode_links = soup_series.select('a[href*="/episode/"]')
                episode_url = None
                season_int = int(season)
                episode_int = int(episode)
                patterns = [
                    f"{season_int} - {episode_int}",
                    f"{season_int} - {episode_int:02d}",
                    f"{season_int}x{episode_int:02d}",
                    f"{season_int}x{episode_int}",
                ]
                for link in episode_links:
                    link_text = link.get_text(strip=True)
                    for pattern in patterns:
                        if pattern in link_text:
                            episode_url = urljoin(HOST, link["href"])
                            break
                    if episode_url:
                        break
                if episode_url:
                    return cls._get_players(episode_url)
            except:
                pass
        return []

    @classmethod
    def _get_players(cls, page_url):
        links = []
        try:
            r = session.get(page_url, timeout=15)
            soup = BeautifulSoup(r.text, 'html.parser')
            tabs = soup.select("#player-container .player-menu li a")
            for tab in tabs:
                text = tab.get_text(strip=True).upper()
                tab_id = tab["href"].lstrip("#")
                iframe = soup.select_one("#" + tab_id + " iframe")
                if iframe and iframe.get("src"):
                    src = iframe["src"]
                    if src.startswith("//"):
                        src = "https:" + src
                    elif not src.startswith("http"):
                        src = urljoin(HOST, src)
                    lang = DUBBED if any(x in text for x in ["DUBLAD", "DUB", "ÁUDIO"]) else SUBTITLED
                    links.append((f"{WEBSITE} • {lang}", src))
        except:
            pass
        return links

    @classmethod
    def resolve_movies(cls, url):
        streams = []
        if not url:
            return streams
        try:
            resolver = Resolver()
            resolved, sub = resolver.resolverurls(url)
            if resolved:
                streams.append((resolved, sub or '', USER_AGENT))
        except:
            pass
        return streams

    @classmethod
    def resolve_tvshows(cls, url):
        return cls.resolve_movies(url)
