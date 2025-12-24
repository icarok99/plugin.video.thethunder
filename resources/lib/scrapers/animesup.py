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

FRANCHISE_KEYWORDS = {
    "naruto",
    "dragon ball",
    "one piece",
    "bleach",
    "boruto",
    "pokemon",
    "digimon",
    "yugioh",
    "saint seiya"
}

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
    pass

from resources.lib.resolver import Resolver


class source:

    @classmethod
    def normalize_title(cls, title):
        if not title:
            return ''
        title = re.sub(r'\s*[:]\s*', ' ', title)
        title = re.sub(r'\s*\(.*?\)\s*', ' ', title)
        title = re.sub(r'\s+', ' ', title).strip()
        return title.lower()

    @classmethod
    def clean_search_title(cls, title):
        if not title:
            return ''
        title = re.sub(r'^assistir\s+(?:online\s+)?', '', title, flags=re.I)
        title = re.sub(r'\s+online$', '', title, flags=re.I)
        title = re.sub(r'\s*-\s*dublado\s*$', '', title, flags=re.I)
        return title.strip()

    @classmethod
    def is_multi_variant_anime(cls, title):
        t = title.lower()
        return any(k in t for k in FRANCHISE_KEYWORDS)

    @classmethod
    def strict_similarity(cls, mal_title, candidate_title):
        mal_norm = cls.normalize_title(mal_title)
        cand_norm = cls.normalize_title(candidate_title)
        ratio = difflib.SequenceMatcher(None, mal_norm, cand_norm).ratio()
        if cls.is_multi_variant_anime(mal_norm) and mal_norm != cand_norm:
            ratio *= 0.60
        return ratio

    @classmethod
    def prepare_mal_title_for_search(cls, title):
        if not title:
            return ''

        title = cls.clean_search_title(title)

        if len(title) <= 120:
            return title

        match = re.search(r'(ga\s+Gift\s*)["\']', title, flags=re.I)
        if match:
            return title[:match.start(1) + len(match.group(1))].strip()

        if len(title) > 120:
            title = title[:120].rsplit(' ', 1)[0]

        return title

    @classmethod
    def get_mal_title(cls, imdb_id):
        imdb_url = f"https://m.imdb.com/title/{imdb_id}/"
        try:
            r = session.get(imdb_url)
            if not r.ok:
                return None
            soup = BeautifulSoup(r.text, 'html.parser')
            hero = soup.find('h1', {'data-testid': 'hero__pageTitle'})
            english_title = hero.get_text(strip=True) if hero else soup.find('h1').get_text(strip=True)
        except:
            return None

        mal_search_url = f"https://myanimelist.net/anime.php?q={quote_plus(english_title)}&cat=anime"
        try:
            r = session.get(mal_search_url)
            if not r.ok:
                return None

            soup = BeautifulSoup(r.text, 'html.parser')
            titles = []

            for a in soup.find_all('a', class_=re.compile(r'hoverinfo_trigger', re.I)):
                strong = a.find('strong')
                title = strong.get_text(strip=True) if strong else a.get_text(strip=True)
                if not title or len(title) > 200:
                    continue
                titles.append(cls.clean_search_title(title))

            if not titles:
                return None

            if not cls.is_multi_variant_anime(english_title):
                return titles[0]

            best_ratio = 0.0
            best_title = None
            for title in titles:
                ratio = difflib.SequenceMatcher(None, english_title.lower(), title.lower()).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_title = title

            if best_ratio < 0.80:
                return None

            return best_title

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
            if text in ("SD", "HD"):
                available.append(text)
            elif text in ("FULLHD", "FULL HD", "FHD"):
                available.append("FULLHD")
        return available if available else ["SD"]

    @classmethod
    def _extract_video_urls(cls, episode_page_text):
        videos = {}
        containers = re.split(r'<div class="playerContainer"', episode_page_text)[1:]
        for i, container in enumerate(containers[:3]):
            m = re.search(r"var\s+vid\s*=\s*'([^']+\.mp4)';", container)
            if not m:
                continue
            url = m.group(1).strip()
            if "r2.cloudflarestorage.com" not in url:
                continue
            videos[("SD", "HD", "FULLHD")[i]] = url
        return videos

    @classmethod
    def _get_highest_quality_link(cls, episode_page_text, available):
        videos = cls._extract_video_urls(episode_page_text)
        for q in ("FULLHD", "HD", "SD"):
            if q in available and q in videos:
                return f"ANIMESUP - {q}", videos[q]
        return "ANIMESUP - SD", None

    @classmethod
    def _get_episode_page_url(cls, page_text, episode_num):
        pattern = re.compile(rf'(?:episodio|ep)[\s-]*{episode_num}\b', re.I)
        for match in pattern.finditer(page_text):
            context = page_text[max(0, match.start()-200):match.end()+500]
            link = re.search(r'href=["\'](/episodio/\d+)["\']', context)
            if link:
                return urljoin("https://www.animesup.info/", link.group(1))
        link = re.search(r'href=["\'](/episodio/\d+)["\']', page_text)
        return urljoin("https://www.animesup.info/", link.group(1)) if link else None

    @classmethod
    def _get_movie_episode_url(cls, page_text):
        soup = BeautifulSoup(page_text, "html.parser")
        for item in soup.select("div.ultimosEpisodiosHomeItem"):
            if re.search(r'\bfilme\b', item.get_text(" ", strip=True), re.I):
                a = item.find("a", href=True)
                if a:
                    return urljoin("https://www.animesup.info/", a["href"])
        return cls._get_episode_page_url(page_text, 1)

    @classmethod
    def search_movies(cls, imdb, year=None):
        mal_title = cls.get_mal_title(imdb)
        if not mal_title:
            return []

        search_title = cls.prepare_mal_title_for_search(mal_title)

        valid_sources = []
        seen = set()

        search_url = f"https://www.animesup.info/busca?busca={quote_plus(search_title)}"
        r = session.get(search_url)
        if not r.ok:
            return []

        soup = BeautifulSoup(r.text, "html.parser")

        for a in soup.find_all("a", href=re.compile(r"/(animes|anime-dublado)/[^/]+$")):
            raw_title = a.get_text(strip=True)
            title_text = cls.clean_search_title(raw_title)

            if cls.is_multi_variant_anime(mal_title):
                if cls.strict_similarity(mal_title, title_text) < 0.75:
                    continue

            page_url = urljoin("https://www.animesup.info/", a['href'])
            if page_url in seen:
                continue
            seen.add(page_url)

            r_page = session.get(page_url)
            if not r_page.ok:
                continue

            ep_url = cls._get_movie_episode_url(r_page.text)
            if not ep_url:
                continue

            r_ep = session.get(ep_url)
            if not r_ep.ok:
                continue

            available = cls._get_available_qualities(r_ep.text)
            label, url = cls._get_highest_quality_link(r_ep.text, available)
            if not url:
                continue

            prefix = "DUBLADO" if "dublado" in raw_title.lower() else "LEGENDADO"
            valid_sources.append((f"{label} ({prefix})", url))

        return valid_sources

    @classmethod
    def search_tvshows(cls, imdb, year, season, episode):
        try:
            episode = int(episode)
        except:
            return []

        mal_title = cls.get_mal_title(imdb)
        if not mal_title:
            return []

        search_title = cls.prepare_mal_title_for_search(mal_title)

        valid_sources = []
        seen = set()

        search_url = f"https://www.animesup.info/busca?busca={quote_plus(search_title)}"
        r = session.get(search_url)
        if not r.ok:
            return []

        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=re.compile(r"/(animes|anime-dublado)/[^/]+$")):
            raw_title = a.get_text(strip=True)
            title_text = cls.clean_search_title(raw_title)

            ratio = cls.strict_similarity(mal_title, title_text)

            if cls.is_multi_variant_anime(mal_title):
                if ratio < 0.60:
                    continue

            page_url = urljoin("https://www.animesup.info/", a['href'])
            if page_url in seen:
                continue
            seen.add(page_url)

            r_page = session.get(page_url)
            if not r_page.ok:
                continue

            ep_url = cls._get_episode_page_url(r_page.text, episode)
            if not ep_url:
                continue

            r_ep = session.get(ep_url)
            if not r_ep.ok:
                continue

            available = cls._get_available_qualities(r_ep.text)
            label, url = cls._get_highest_quality_link(r_ep.text, available)
            if not url:
                continue

            prefix = "DUBLADO" if "dublado" in raw_title.lower() else "LEGENDADO"
            valid_sources.append((f"{label} ({prefix})", url))

        return valid_sources

    @classmethod
    def resolve_movies(cls, url):
        resolver = Resolver()
        resolved, sub = resolver.resolverurls(url)
        return [(resolved or url, sub or '', USER_AGENT)]

    @classmethod
    def resolve_tvshows(cls, url):
        return cls.resolve_movies(url)

    __site_url__ = ['https://www.animesup.info/']
