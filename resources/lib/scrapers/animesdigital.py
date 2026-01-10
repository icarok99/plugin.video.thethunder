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
        
        t = re.sub(r'^(?:assistir|ver|online)\b\s*(?:online|hd|fhd|fullhd|dublado|legendado)?\s*', '', t, flags=re.I)
        t = re.sub(r'\s+(?:online|em\s*hd|hd|fhd|fullhd|1080p|720p|completo|dublado|legendado|dub|sub|pt-?br|todos\s+os?\s+epis[oó]dios?|episodios).*$', '', t, flags=re.I)
        t = re.sub(r'\b(?:anime|todos|os|epis[oó]dios?|ep\.?|todos\s+os?|completo|dublado|legendado|online|hd|fhd|fullhd)\b\s*', '', t, flags=re.I)
        t = re.sub(r'[-–—:.,;!?]+', ' ', t)
        t = re.sub(r'[()\[\]{}]', '', t)
        t = re.sub(r'[\"“”\'`´]', '', t)
        t = re.sub(r'\s+', ' ', t).strip()
        t = re.sub(r'\b(?:assistir|ver|online|em|hd|fhd|full|todos)\b\s*', '', t, flags=re.I)
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
    def _similarity_score(cls, base_titles, candidate_title, base_year=None, cand_year=None):
        cand_clean = cls._clean_title(candidate_title)
        stripped_cand = cls._strip_dublado(cand_clean)
        
        best_score = 0.0

        for base in base_titles:
            base_clean = cls._clean_title(base)
            if not base_clean:
                continue

            if stripped_cand != base_clean:
                norm_cand = re.sub(r'\s+', ' ', stripped_cand).strip()
                norm_base = re.sub(r'\s+', ' ', base_clean).strip()
                
                if norm_cand != norm_base:
                    continue

            score = difflib.SequenceMatcher(None, base_clean, stripped_cand).ratio()

            if 'dublado' in candidate_title.lower():
                score += 0.25

            if base_year and cand_year:
                if base_year == cand_year:
                    score += 0.40
                else:
                    score -= 0.55

            best_score = max(best_score, score)

        return best_score

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

        search_title = title_english or title_default
        search_url = f"https://animesdigital.org/?s={quote_plus(search_title)}"

        r = session.get(search_url)
        if not r.ok:
            return []

        soup = BeautifulSoup(r.text, "html.parser")
        anchors = soup.select('div.itemA > a[href*="/anime/a/"]')

        if not anchors:
            return []

        candidates = []
        for a in anchors:
            raw_title = a.get("title") or a.get_text(strip=True)
            anime_url = a["href"]

            cand_year = cls._extract_year(raw_title)
            score = cls._similarity_score(base_titles, raw_title, base_year, cand_year)

            candidates.append({
                "title": raw_title,
                "url": anime_url,
                "score": score,
                "year": cand_year
            })

        candidates.sort(key=lambda x: x["score"], reverse=True)

        results = []
        seen = set()

        for c in candidates[:10]:
            if c["score"] < 0.70:
                continue

            if c["url"] in seen:
                continue
            seen.add(c["url"])

            ep_url = (
                cls._get_movie_episode_url(c["url"])
                if is_movie
                else cls._get_episode_page_url(c["url"], episode)
            )

            if not ep_url:
                continue

            r_ep = session.get(ep_url)
            if not r_ep.ok:
                continue

            available = cls._get_available_qualities(r_ep.text)
            label, url = cls._get_highest_quality_link(r_ep.text, available)
            if not url:
                continue

            prefix = "DUBLADO" if "dublado" in c["title"].lower() else "LEGENDADO"
            final = f"{label} {prefix}"
            results.append((final, url))

        return results

    @classmethod
    def _get_movie_episode_url(cls, anime_url):
        return anime_url

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
                if not a:
                    continue
                title_tag = item.select_one('div.title_anime')
                if not title_tag:
                    continue
                text = title_tag.get_text(strip=True)
                m = re.search(r'Epis[óo]dio\s*(\d+)', text, re.I)
                if m and int(m.group(1)) == episode:
                    return a['href']

            page += 1

        return None

    @classmethod
    def _get_available_qualities(cls, episode_page_text):
        soup = BeautifulSoup(episode_page_text, 'html.parser')
        qualities = []
        for li in soup.select('li[data-tab]'):
            text = li.get_text(strip=True).upper()
            q = 'FULLHD' if 'FHD' in text or 'FULL' in text else 'HD'
            qualities.append(q)
        return qualities or ['HD']

    @classmethod
    def _get_highest_quality_link(cls, episode_page_text, available):
        soup = BeautifulSoup(episode_page_text, 'html.parser')
        players = {}
        for li in soup.select('li[data-tab]'):
            tab_id = li.get('data-tab')
            label = li.get_text(strip=True).upper()
            iframe = soup.select_one(f'{tab_id} iframe')
            if iframe and iframe.get('src'):
                src = iframe['src']
                q = 'FULLHD' if 'FHD' in label or 'FULL' in label else 'HD'
                players[q] = src

        for q in ('FULLHD', 'HD'):
            if q in available and q in players:
                return f"ANIMESDIGITAL -", players[q]

        return None, None

    @classmethod
    def resolve_movies(cls, url):
        resolved, sub = Resolver().resolverurls(url)
        return [(resolved or url, sub or '', USER_AGENT)]

    resolve_tvshows = resolve_movies

    __site_url__ = ['https://animesdigital.org/']
