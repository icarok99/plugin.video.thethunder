# -*- coding: utf-8 -*-

WEBSITE = 'CINEVIBEHD'

try:
    from resources.lib.ClientScraper import cfscraper, USER_AGENT
except ImportError:
    from ClientScraper import cfscraper, USER_AGENT

import re
import difflib
import sys
import os
from urllib.parse import quote_plus

try:
    from resources.lib.autotranslate import AutoTranslate
    portuguese = AutoTranslate.language('Portuguese')
    english = AutoTranslate.language('English')
    select_option_name = AutoTranslate.language('select_option')
except ImportError:
    portuguese = 'DUBLADO'
    english = 'LEGENDADO'
    select_option_name = 'SELECIONE UMA OPÇÃO ABAIXO:'

try:
    from kodi_helper import myAddon
    addonId = re.search('plugin\://(.+?)/', str(sys.argv[0])).group(1)
    addon = myAddon(addonId)
    select = addon.select
except ImportError:
    local_path = os.path.dirname(os.path.realpath(__file__))
    lib_path = local_path.replace('scrapers', '')
    sys.path.append(lib_path)

# Import the Resolver from resolver.py
from resources.lib.resolver import Resolver


class source:
    __site_url__ = ['https://cinevibehd.com.br/']

    @classmethod
    def find_title(cls, imdb):
        url = f'https://m.imdb.com/pt/title/{imdb}'
        try:
            r = cfscraper.get(url, timeout=20)
            if r.status_code != 200:
                return ''
            title_pt = re.search(r'data-testid="hero__pageTitle"[^>]*><span[^>]*>([^<]+)', r.text)
            title_pt = title_pt.group(1).strip() if title_pt else ''
            if not title_pt:
                title_pt = re.search(r'<title>([^<]+) - IMDb', r.text)
                title_pt = title_pt.group(1).split(' (')[0].strip() if title_pt else ''
            return title_pt
        except:
            return ''

    @classmethod
    def _get_player_urls(cls, post_id, html, season=None, episode=None):
        if not post_id:
            return []

        raw_nume = re.findall(r'data-nume=[\"\'](\d+)[\"\']', html or '')
        nume_list = []
        for n in raw_nume:
            if n not in nume_list and n.lower() != 'trailer':
                nume_list.append(n)

        if not nume_list:
            return []

        players = []
        headers = {
            'User-Agent': USER_AGENT,
            'Referer': cls.__site_url__[-1],
            'Accept': 'application/json, text/javascript, */*; q=0.01'
        }

        for nume in nume_list:
            if season is None or episode is None:
                api = f"https://cinevibehd.com.br/wp-json/dooplayer/v2/{post_id}/movie/{nume}"
            else:
                api = f"https://cinevibehd.com.br/wp-json/dooplayer/v2/{post_id}/tv/{nume}"

            try:
                r = cfscraper.get(api, headers=headers, timeout=20)
            except:
                continue

            if not r or getattr(r, 'status_code', None) != 200:
                continue

            embed = None
            try:
                data = r.json()
                embed = data.get('embed_url') or data.get('embed') or data.get('url') or data.get('player') or data.get('iframe')
            except:
                m_if = re.search(r'<iframe[^>]+src=[\'"]([^\'"]+)[\'"]', r.text, re.I)
                if m_if:
                    embed = m_if.group(1)

            if not embed:
                m = re.search(r'(https?://[^\s\'"]+\.(?:m3u8|mp4)[^\s\'"]*)', r.text)
                if m:
                    embed = m.group(1)

            if not embed:
                continue

            title_match = re.search(rf'data-nume=[\"\']{nume}[\"\'][^>]*>.*?<span[^>]*class=["\']title["\'][^>]*>([^<]+)</span>', html or '', re.I | re.S)
            raw_title = title_match.group(1).strip() if title_match else ""

            is_dub = bool(re.search(r'dub|dublad|dublado', raw_title, re.I))
            lang = portuguese if is_dub else english

            count = sum(1 for existing_name, _ in players if lang in existing_name)
            number = count + 1

            name = f"{WEBSITE} - {lang} {number}"

            players.append((name, embed))

        return players

    @classmethod
    def search_movies(cls, imdb, year):
        title_pt = cls.find_title(imdb)
        if not title_pt:
            return []

        query = quote_plus(title_pt)
        search_url = f"https://cinevibehd.com.br/?s={query}"

        try:
            r = cfscraper.get(search_url, timeout=20)
            if r.status_code != 200:
                return []

            matches = re.findall(r'href=["\'](https://cinevibehd\.com\.br/filmes/[^"\']+)["\'][^>]*>([^<]+)</a>', r.text)
            if not matches:
                return []

            best_url = None
            best_score = 0
            year = str(year) if year else None

            for url, text in matches:
                text_year_match = re.search(r'\b(19|20)\d{2}\b', text)
                text_year = text_year_match.group(0) if text_year_match else None
                clean = re.sub(r'\s*\(\d{4}\).*', '', text, flags=re.I).strip()
                clean = re.sub(r'\b(19|20)\d{2}\b', '', clean).strip()

                ratio = difflib.SequenceMatcher(None, title_pt.lower(), clean.lower()).ratio()
                score = ratio

                if year and text_year and abs(int(year) - int(text_year)) <= 1:
                    score += 0.4
                elif not year and not text_year:
                    score += 0.1

                if score > best_score:
                    best_score = score
                    best_url = url

            if not best_url or best_score < 0.78:
                return []

            film_html_resp = cfscraper.get(best_url, timeout=20)
            if film_html_resp.status_code != 200:
                return []

            post_id_m = re.search(r'data-post=[\"\'](\d+)[\"\']', film_html_resp.text)
            if not post_id_m:
                return []

            post_id = post_id_m.group(1)
            return cls._get_player_urls(post_id, film_html_resp.text, season=None, episode=None)

        except:
            return []

    @classmethod
    def search_tvshows(cls, imdb, year, season, episode):
        title_pt = cls.find_title(imdb)
        if not title_pt:
            return []

        s = str(int(season))
        e = str(int(episode))

        try:
            search_url = f"https://cinevibehd.com.br/?s={quote_plus(title_pt)}"
            r = cfscraper.get(search_url, timeout=20)
            if r.status_code != 200:
                return []

            series_match = re.search(r'href=["\'](https://cinevibehd\.com\.br/series/[^"\']+)["\']', r.text, re.I)
            if not series_match:
                series_match = re.search(r'href=["\'](https://cinevibehd\.com\.br/series/[^"\']+?(?:-2024)?/?)["\']', r.text, re.I)
            if not series_match:
                return []

            series_url = series_match.group(1)
            series_resp = cfscraper.get(series_url, timeout=30)
            if series_resp.status_code != 200:
                return []

            html = series_resp.text
            episode_url = None

            new_pat = re.compile(
                r'<article[^>]+class=["\'][^"\']*cv-ep[^"\']*["\'][^>]*'
                r'(?:data-season=["\'](\d+)["\'][^>]*'
                r'data-epnum=["\'](\d+)["\'][^>]*'
                r'|data-epnum=["\'](\d+)["\'][^>]*'
                r'data-season=["\'](\d+)["\'][^>]*'
                r')>.*?'
                r'href=["\'](https?://cinevibehd\.com\.br/episodios/[^"\']+)["\']',
                re.DOTALL | re.I
            )
            for m in new_pat.finditer(html):
                groups = m.groups()
                sea = groups[0] or groups[3]
                epi = groups[1] or groups[2]
                if sea == s and epi == e:
                    episode_url = m.group(5)
                    break

            if not episode_url:
                old_pat = re.compile(
                    r'<div[^>]+class=["\']numerando["\'][^>]*>\s*{}\s*-\s*{}\s*</div>.*?'
                    r'<a\s+href=["\'](https?://cinevibehd\.com\.br/episodios/[^"\']+)["\']'.format(s, e),
                    re.DOTALL | re.I
                )
                m = old_pat.search(html)
                if m:
                    episode_url = m.group(1)

            if not episode_url:
                fb1 = re.search(rf'href=["\'](https?://cinevibehd\.com\.br/episodios/[^"\']*?-{s}x{e}[^"\']*)["\']', html, re.I)
                if fb1:
                    episode_url = fb1.group(1)
                else:
                    fb2 = re.search(rf'href=["\'](https?://cinevibehd\.com\.br/episodios/[^"\']*?-{s}x{int(e):02d}[^"\']*)["\']', html, re.I)
                    if fb2:
                        episode_url = fb2.group(1)

            if not episode_url:
                return []

            ep_resp = cfscraper.get(episode_url, timeout=30)
            if ep_resp.status_code != 200:
                return []

            post_id = re.search(r'data-post=["\'](\d+)["\']', ep_resp.text)
            if not post_id:
                post_id = re.search(r'data-postid=["\'](\d+)["\']', ep_resp.text)
            if not post_id:
                return []

            return cls._get_player_urls(post_id.group(1), ep_resp.text, season=s, episode=e)

        except Exception:
            return []

    @classmethod
    def resolve_movies(cls, url):
        streams = []
        if not url:
            return streams
        sub = ''
        try:
            sub_part = url.split('http')[2]
            sub = 'http' + sub_part.split('&')[0]
            if '.srt' not in sub:
                sub = ''
        except:
            pass
        stream = url.split('?')[0].split('#')[0]
        resolver = Resolver()
        resolved, sub_from_resolver = resolver.resolverurls(stream)
        if resolved:
            streams.append((resolved, sub if sub else sub_from_resolver, USER_AGENT))
        return streams

    @classmethod
    def resolve_tvshows(cls, url):
        return cls.resolve_movies(url)