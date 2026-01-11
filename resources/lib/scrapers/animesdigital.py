# -*- coding: utf-8 -*-
WEBSITE = 'ANIMESDIGITAL'

import re
import unicodedata
import difflib
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
import requests

from resources.lib.resolver import Resolver


session = requests.Session()
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'
session.headers.update({
    'User-Agent': USER_AGENT,
    'Accept-Language': 'pt-BR,pt;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Referer': 'https://animesdigital.org/',
})


class source:

    QUOTE_MIN_CHARS = 60
    QUOTE_MIN_WORDS = 8

    @classmethod
    def _normalize(cls, text):
        if not text:
            return ""
        return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")

    @classmethod
    def _clean_title(cls, title):
        if not title:
            return ""
        t = cls._normalize(title.lower())
        t = re.sub(r'^(assistir|ver|online)\b\s*(online|hd|fhd|fullhd|dublado|legendado)?\s*', '', t, flags=re.I)
        t = re.sub(r'\s+(online|em\s*hd|hd|fhd|fullhd|1080p|720p|completo|dublado|legendado|dub|sub|pt-?br|todos\s+os?\s+epis[oó]dios?|episodios|todos).*$', '', t, flags=re.I)
        t = re.sub(r'\b(?:anime|todos|os|ep\.?|epis[oó]dios?|assistir|ver|online|em|hd|fhd|full|todos)\b\s*', '', t, flags=re.I)
        t = re.sub(r'(\s*(?:season|temporada|part|cour|s)\s*\d+).*$', r'\1', t, flags=re.I)
        t = re.sub(r'\b(?:season|temporada|part|cour|s)\b\s*(\d+)', r'\1', t, flags=re.I)
        t = re.sub(r'[-—–:.,;!?]+', ' ', t)
        t = re.sub(r'[()[\]{}]', '', t)
        t = re.sub(r'[\""`´]', '', t)
        t = re.sub(r'\s+', ' ', t).strip()
        return t.strip()

    @classmethod
    def _strip_dublado(cls, text):
        return re.sub(r'\bdublado\b', '', text, flags=re.I).strip()

    @classmethod
    def _extract_year(cls, text):
        if not text:
            return None
        m = re.search(r'\b(19|20)\d{2}\b', text)
        return int(m.group()) if m else None

    @classmethod
    def _roman_to_int(cls, s):
        roman = {'i':1,'ii':2,'iii':3,'iv':4,'v':5,'vi':6,'vii':7,'viii':8,'ix':9,'x':10,
                 'xi':11,'xii':12,'xiii':13,'xiv':14,'xv':15,'xvi':16,'xvii':17,'xviii':18,'xix':19,'xx':20}
        return roman.get(s.lower().strip(), None)

    @classmethod
    def _similarity_score(cls, base_titles, candidate_title, base_year=None, cand_year=None, season=None):
        try:
            season_num = int(season) if season is not None else None
        except (ValueError, TypeError):
            season_num = None

        cand_clean = cls._clean_title(candidate_title)
        stripped_cand = cls._strip_dublado(cand_clean)
        best_score = 0.0
        roman_match = re.search(r'\b(i{1,3}|iv|v|vi{0,3}|ix|x{1,3})\b', candidate_title.lower(), re.I)

        for base in base_titles:
            base_clean = cls._clean_title(base)
            base_super = re.split(r'(?:season|second|part|temporada|:\s*|—\s*).*$', base.lower(), flags=re.I)[0].strip()
            norm_cand = re.sub(r'\s+', ' ', stripped_cand).strip()
            norm_base_super = re.sub(r'\s+', ' ', base_super).strip()

            if norm_cand != norm_base_super:
                season_str = str(season_num) if season_num else ''
                roman_str = roman_match.group(0).lower() if roman_match else ''
                if season_num and season_num > 1 and (season_str in norm_cand or roman_str):
                    if not (norm_cand == norm_base_super + ' ' + season_str or norm_cand == norm_base_super + ' ' + roman_str):
                        continue
                else:
                    continue

            score = difflib.SequenceMatcher(None, base_clean, stripped_cand).ratio()
            if 'dublado' in candidate_title.lower():
                score += 0.25
            if season_num and (str(season_num) in candidate_title or roman_match):
                score += 0.20
            if base_year and cand_year:
                score += 0.40 if base_year == cand_year else -0.55
            best_score = max(best_score, score)

        return best_score

    @classmethod
    def _get_simplified_search_title(cls, title_default, title_english, season):
        try:
            season_num = int(season) if season is not None else None
        except (ValueError, TypeError):
            season_num = None

        if season_num is None or season_num <= 1:
            return title_english or title_default or ""

        base = title_english or title_default or ""
        if not base:
            return ""

        base = re.sub(r'\s*(?:season|part|temporada|cour)\s*\d+.*$', '', base, flags=re.I).strip()
        base = re.sub(r'\s*\d+(?:nd|rd|th)?\s*season.*$', '', base, flags=re.I).strip()
        base = re.sub(r'\s*:\s*.*$', '', base).strip()
        base = re.sub(r'\s*\d{4}$', '', base).strip()
        return f"{base} {season_num}".strip()

    @classmethod
    def search_animes(cls, mal_id, season=None, episode=None):
        is_movie = episode is None
        if not is_movie:
            try:
                episode = int(episode)
            except:
                return []

        r = session.get(f"https://api.jikan.moe/v4/anime/{mal_id}/full")
        if not r.ok:
            return []

        data = r.json().get('data', {})
        title_english = data.get('title_english')
        title_default = data.get('title')
        title_synonyms = data.get('title_synonyms') or []
        base_year = data.get('year')
        base_titles = [t for t in [title_english, title_default] + title_synonyms if t]

        if not base_titles:
            return []

        search_title = cls._get_simplified_search_title(title_default, title_english, season)
        if not search_title:
            search_title = title_english or title_default

        r = session.get(f"https://animesdigital.org/?s={quote_plus(search_title)}")
        anchors = []
        if r.ok:
            soup = BeautifulSoup(r.text, "html.parser")
            anchors = soup.select('div.itemA > a[href*="/anime/a/"]')

        if len(anchors) == 0:
            fallback_title = cls._get_simplified_search_title(title_default, None, season)
            if fallback_title and fallback_title != search_title:
                r = session.get(f"https://animesdigital.org/?s={quote_plus(fallback_title)}")
                if r.ok:
                    soup = BeautifulSoup(r.text, "html.parser")
                    anchors = soup.select('div.itemA > a[href*="/anime/a/"]')

        if not anchors:
            return []

        candidates = []
        for a in anchors:
            raw_title = a.get("title") or a.get_text(strip=True)
            candidates.append({
                "title": raw_title,
                "url": a["href"],
                "score": cls._similarity_score(base_titles, raw_title, base_year, cls._extract_year(raw_title), season),
                "year": cls._extract_year(raw_title)
            })

        candidates.sort(key=lambda x: x["score"], reverse=True)
        results = []
        seen = set()

        for c in candidates[:10]:
            if c["score"] < 0.70 or c["url"] in seen:
                continue
            seen.add(c["url"])

            ep_url = c["url"] if is_movie else cls._get_episode_page_url(c["url"], episode)
            if not ep_url:
                continue

            r_ep = session.get(ep_url)
            if not r_ep.ok:
                continue

            all_players = cls._get_all_players(r_ep.text)
            if not all_players:
                continue

            prefix = "DUBLADO" if "dublado" in c["title"].lower() else "LEGENDADO"
            for idx, (quality, url) in enumerate(all_players, start=1):
                results.append((f"ANIMESDIGITAL - {prefix} {idx}", url))

        return results

    @classmethod
    def _get_episode_page_url(cls, anime_url, episode):
        try:
            episode = int(episode)
        except:
            return None

        base_url = anime_url.split('?')[0].rstrip('/')
        page = 1

        while True:
            url = f"{base_url}?odr=1" if page == 1 else f"{base_url}/page/{page}/?odr=1"
            r = session.get(url)
            if not r.ok:
                break

            soup = BeautifulSoup(r.text, 'html.parser')
            for item in soup.select('div.item_ep'):
                a = item.select_one('a.b_flex[href*="/video/a/"]')
                title_tag = item.select_one('div.title_anime')
                if a and title_tag:
                    m = re.search(r'Epis[óo]dio\s*(\d+)', title_tag.get_text(strip=True), re.I)
                    if m and int(m.group(1)) == episode:
                        return a['href']
            page += 1

        return None

    @classmethod
    def _get_all_players(cls, episode_page_text):
        soup = BeautifulSoup(episode_page_text, 'html.parser')
        players = []
        for li in soup.select('li[data-tab]'):
            iframe = soup.select_one(f'{li.get("data-tab")} iframe')
            if iframe and iframe.get('src'):
                label = li.get_text(strip=True).upper()
                players.append(('FULLHD' if 'FHD' in label or 'FULL' in label else 'HD', iframe['src']))
        return players

    @classmethod
    def resolve_movies(cls, url):
        resolved, sub = Resolver().resolverurls(url)
        return [(resolved or url, sub or '', USER_AGENT)]

    resolve_tvshows = resolve_movies
    __site_url__ = ['https://animesdigital.org/']