# -*- coding: utf-8 -*-
WEBSITE = 'ANIMESUP'

import re
import os
import sys
import difflib
from urllib.parse import quote_plus, urljoin
from bs4 import BeautifulSoup
import requests

session = requests.Session()
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'
session.headers.update({
    'User-Agent': USER_AGENT,
    'Accept-Language': 'en-US,en;q=0.9,pt-BR;q=0.8,pt;q=0.7',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Referer': 'https://www.animesup.info/',
})

try:
    from resources.lib.autotranslate import AutoTranslate
    portuguese = AutoTranslate.language('Portuguese')
    english = AutoTranslate.language('English')
except ImportError:
    portuguese = 'DUBLADO'
    english = 'LEGENDADO'

try:
    from kodi_helper import myAddon
    addonId = re.search('plugin://(.+?)/', str(sys.argv[0])).group(1)
    addon = myAddon(addonId)
    select = addon.select
except ImportError:
    local_path = os.path.dirname(os.path.realpath(__file__))
    lib_path = local_path.replace('scrapers', '')
    sys.path.append(lib_path)

from resources.lib.resolver import Resolver


class source:

    @classmethod
    def normalize_title(cls, title):
        if not title:
            return ''
        title = re.sub(r'\s*[:]\s*', ' ', title)
        title = re.sub(r'\s*\(.*?\)\s*', ' ', title)
        title = re.sub(r'\s+dublado\s*', ' ', title, flags=re.I)
        title = re.sub(r'\s+', ' ', title).strip()
        return title.lower()

    @classmethod
    def clean_search_title(cls, title):
        if not title or len(title) <= 80:
            return title.strip()

        ga_match = re.search(r'\s+ga\s+', title, flags=re.I)
        if ga_match:
            pos = ga_match.start()
            after_ga = title[pos:].strip()
            if re.match(r'^ga\s+(Gift|"|de Level|no Nakama|wo Te ni|&)', after_ga, re.I):
                title = title[:pos].strip()

        return title.strip()

    @classmethod
    def get_mal_title(cls, imdb_id):
        imdb_url = f"https://m.imdb.com/title/{imdb_id}/"
        try:
            r = session.get(imdb_url)
            if not r.ok:
                return None

            soup = BeautifulSoup(r.text, 'html.parser')
            hero = soup.find('h1', {'data-testid': 'hero__pageTitle'})
            if hero:
                english_title = hero.get_text(strip=True)
            else:
                h1 = soup.find('h1')
                if h1:
                    english_title = h1.get_text(strip=True)
                else:
                    return None
        except:
            return None

        mal_search_url = f"https://myanimelist.net/anime.php?q={quote_plus(english_title)}&cat=anime"
        try:
            r = session.get(mal_search_url)
            if not r.ok:
                return None

            soup = BeautifulSoup(r.text, 'html.parser')
            title_tag = soup.find('a', class_=re.compile(r'hoverinfo_trigger'))
            if title_tag:
                strong = title_tag.find('strong')
                if strong:
                    mal_title = strong.get_text(strip=True)
                    return cls.clean_search_title(mal_title)

            strong = soup.find('strong')
            if strong:
                mal_title = strong.get_text(strip=True)
                return cls.clean_search_title(mal_title)

            return None
        except:
            return None

    @classmethod
    def _get_available_qualities(cls, episode_page_text):
        soup = BeautifulSoup(episode_page_text, 'html.parser')
        abas_box = soup.find('div', class_=re.compile(r'AbasBox', re.I))
        if not abas_box:
            return ["SD"]

        available = []
        for aba in abas_box.find_all('div', class_=re.compile(r'Aba', re.I)):
            text = aba.get_text(strip=True).upper()
            if text == "SD":
                available.append("SD")
            elif text == "HD":
                available.append("HD")
            elif text in ("FULLHD", "FULL HD", "FHD"):
                available.append("FULLHD")
        return available if available else ["SD"]

    @classmethod
    def _extract_video_urls(cls, episode_page_text):
        videos = {}

        containers = re.split(r'<div class="playerContainer"', episode_page_text)[1:]

        for i, container in enumerate(containers[:3]):
            vid_match = re.search(r"var\s+vid\s*=\s*'([^']+\.mp4)';", container)
            if not vid_match:
                continue

            url = vid_match.group(1).strip()

            if "r2.cloudflarestorage.com" not in url:
                continue

            if i == 0:
                videos['SD'] = url
            elif i == 1:
                videos['HD'] = url
            elif i == 2:
                videos['FULLHD'] = url

        return videos

    @classmethod
    def _get_highest_quality_link(cls, episode_page_text, available_qualities):
        videos = cls._extract_video_urls(episode_page_text)

        for qual in ["FULLHD", "HD", "SD"]:
            if qual in available_qualities and qual in videos:
                return (f"ANIMESUP - {qual}", videos[qual])

        for qual in ["FULLHD", "HD", "SD"]:
            if qual in videos:
                return (f"ANIMESUP - {qual}", videos[qual])

        return ("ANIMESUP - SD", None)

    @classmethod
    def _get_episode_page_url(cls, page_text, episode_num):
        pattern = re.compile(rf'(?:episodio|ep)[\s-]*{episode_num}\b', re.I)
        matches = list(pattern.finditer(page_text))

        if matches:
            for match in matches:
                context = page_text[max(0, match.start()-200):match.end()+500]
                link_match = re.search(r'href=["\'](/episodio/\d+)["\']', context)
                if link_match:
                    return urljoin("https://www.animesup.info/", link_match.group(1))

        fallback_match = re.search(r'href=["\'](/episodio/\d+)["\']', page_text)
        if fallback_match:
            return urljoin("https://www.animesup.info/", fallback_match.group(1))

        return None

    @classmethod
    def search_movies(cls, imdb, year=None):
        mal_title = cls.get_mal_title(imdb)
        if not mal_title:
            return []

        norm_mal = cls.normalize_title(mal_title)

        search_url = f"https://www.animesup.info/busca?busca={quote_plus(mal_title)}"
        r = session.get(search_url)
        if not r.ok:
            return []

        soup = BeautifulSoup(r.text, "html.parser")

        valid_sources = []
        seen_urls = set()

        for a in soup.find_all("a", href=re.compile(r"/(animes|anime-dublado)/[^/]+$")):
            title_text = a.get_text(strip=True)
            clean = cls.normalize_title(title_text)
            ratio = difflib.SequenceMatcher(None, norm_mal, clean).ratio()
            if ratio < 0.75:
                continue

            page_url = urljoin("https://www.animesup.info/", a['href'])
            if page_url in seen_urls:
                continue
            seen_urls.add(page_url)

            r_page = session.get(page_url)
            if not r_page.ok:
                continue

            ep_page_url = cls._get_episode_page_url(r_page.text, 1)
            if not ep_page_url:
                continue

            r_ep = session.get(ep_page_url)
            if not r_ep.ok:
                continue

            available = cls._get_available_qualities(r_ep.text)
            label, url = cls._get_highest_quality_link(r_ep.text, available)

            if not url:
                continue

            label_prefix = "DUBLADO" if "dublado" in page_url.lower() or "dublado" in title_text.lower() else "LEGENDADO"
            valid_sources.append((f"{label} ({label_prefix})", url))

        return valid_sources

    @classmethod
    def search_tvshows(cls, imdb, year, season, episode):
        try:
            season = int(season)
            episode = int(episode)
        except:
            return []

        mal_title = cls.get_mal_title(imdb)
        if not mal_title:
            return []

        norm_mal = cls.normalize_title(mal_title)

        valid_sources = []
        seen_urls = set()

        queries = [mal_title, f"{mal_title} dublado"]
        for query in queries:
            search_url = f"https://www.animesup.info/busca?busca={quote_plus(query)}"
            r = session.get(search_url)
            if not r.ok:
                continue

            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=re.compile(r"/(animes|anime-dublado)/[^/]+$")):
                title_text = a.get_text(strip=True)
                clean = cls.normalize_title(title_text)
                ratio = difflib.SequenceMatcher(None, norm_mal, clean).ratio()
                if ratio < 0.50:
                    continue

                page_url = urljoin("https://www.animesup.info/", a['href'])
                if page_url in seen_urls:
                    continue
                seen_urls.add(page_url)

                r_page = session.get(page_url)
                if not r_page.ok:
                    continue

                ep_page_url = cls._get_episode_page_url(r_page.text, episode)
                if not ep_page_url:
                    continue

                r_ep = session.get(ep_page_url)
                if not r_ep.ok:
                    continue

                available = cls._get_available_qualities(r_ep.text)
                label, url = cls._get_highest_quality_link(r_ep.text, available)

                if not url:
                    continue

                is_dub = ("dublado" in page_url.lower() or 
                          "dublado" in title_text.lower() or 
                          "dublado" in query.lower())
                label_prefix = "DUBLADO" if is_dub else "LEGENDADO"

                valid_sources.append((f"{label} ({label_prefix})", url))

        return valid_sources

    @classmethod
    def resolve_movies(cls, url):
        streams = []
        if not url:
            return streams
        resolver = Resolver()
        resolved, sub = resolver.resolverurls(url)
        resolved = resolved or url
        streams.append((resolved, sub or '', USER_AGENT))
        return streams

    @classmethod
    def resolve_tvshows(cls, url):
        return cls.resolve_movies(url)

    __site_url__ = ['https://www.animesup.info/']