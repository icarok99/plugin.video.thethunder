# -*- coding: utf-8 -*-

WEBSITE = 'CINEVIBEHD'

import re
import difflib
import sys
import os
from urllib.parse import quote_plus
import requests
from bs4 import BeautifulSoup

from resources.lib.resolver import Resolver

try:
    import xbmcaddon
    addon = xbmcaddon.Addon()
    DUBBED = addon.getLocalizedString(30200)
    SUBTITLED = addon.getLocalizedString(30202)
except:
    DUBBED = 'DUBLADO'
    SUBTITLED = 'LEGENDADO'

session = requests.Session()
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'
session.headers.update({
    'User-Agent': USER_AGENT,
    'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Referer': 'https://cinevibehd.com/',
})


class source:
    __site_url__ = ['https://cinevibehd.com/']

    @classmethod
    def normalize_title(cls, title):
        if not title:
            return ''
        title = re.sub(r'\s*[:]\s*', ' ', title)
        title = re.sub(r'\s+', ' ', title).strip()
        return title

    @classmethod
    def find_title(cls, imdb):
        url = f'https://m.imdb.com/pt/title/{imdb}/'
        headers = {'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7'}

        try:
            r = session.get(url, headers=headers, timeout=15)
            if not r or r.status_code != 200:
                return '', '', ''

            soup = BeautifulSoup(r.text, 'html.parser')

            title_pt = ''
            hero = soup.find('h1', {'data-testid': 'hero__pageTitle'})
            if hero:
                span = hero.find('span')
                title_pt = (span.text if span else hero.text).strip()

            original_title = ''
            orig_block = soup.find('div', {'data-testid': 'hero-title-block__original-title'})
            if orig_block:
                txt = orig_block.get_text(strip=True)
                original_title = re.sub(r'^(T[íi]tulo original|Original title)[:\s]*', '', txt, flags=re.I).strip()

            if not original_title:
                m = re.search(r'T[íi]tulo original[:\s]*["\']?([^<"\']+)["\']?', r.text, re.I)
                if m:
                    original_title = m.group(1).strip()

            year = ''
            year_link = soup.find('a', href=re.compile(r'/releaseinfo'))
            if year_link:
                y = re.search(r'\d{4}', year_link.text)
                if y:
                    year = y.group(0)

            if not year:
                release_li = soup.find('li', {'data-testid': 'title-details-releasedate'})
                if release_li:
                    y = re.search(r'\d{4}', release_li.get_text())
                    if y:
                        year = y.group(0)

            if not year:
                y = re.search(r'\b(19|20)\d{2}\b', r.text[:6000])
                if y:
                    year = y.group(0)

            return title_pt or original_title, original_title or title_pt, year or ''

        except Exception:
            return '', '', ''

    @classmethod
    def _get_player_urls(cls, post_id, html, season=None, episode=None):
        if not post_id:
            return []

        raw_nume = re.findall(r'data-nume=[\"\'](\d+)[\"\']', html or '')
        nume_list = list(set([n for n in raw_nume if n.lower() != 'trailer']))

        if not nume_list:
            return []

        players = []
        headers = {
            'Referer': cls.__site_url__[-1],
            'Accept': 'application/json, text/javascript, */*; q=0.01'
        }

        for nume in nume_list:
            if season is None or episode is None:
                api = f"https://cinevibehd.com/wp-json/dooplayer/v2/{post_id}/movie/{nume}"
            else:
                api = f"https://cinevibehd.com/wp-json/dooplayer/v2/{post_id}/tv/{nume}"

            try:
                r = session.get(api, headers=headers, timeout=20)
                if not r or r.status_code != 200:
                    continue

                try:
                    data = r.json()
                    embed = data.get('embed_url') or data.get('embed') or data.get('url') or data.get('player') or data.get('iframe')
                except:
                    embed = None

                if not embed:
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
                lang = DUBBED if is_dub else SUBTITLED

                count = sum(1 for existing_name, _ in players if lang in existing_name)
                number = count + 1
                name = f"{WEBSITE} - {lang} {number}"

                players.append((name, embed))

            except:
                continue

        return players

    @classmethod
    def search_movies(cls, imdb, year):
        title_pt, original_title, imdb_year = cls.find_title(imdb)
        if not title_pt:
            return []

        title_pt = cls.normalize_title(title_pt)
        query = quote_plus(title_pt)
        search_url = f"https://cinevibehd.com/?s={query}"

        try:
            r = session.get(search_url, timeout=20)
            if r.status_code != 200:
                return []

            soup = BeautifulSoup(r.text, 'html.parser')
            items = soup.find_all('a', href=re.compile(r'/filmes/[^/]+/$'))

            best_url = None
            best_score = 0

            for a in items:
                href = a['href']
                text = a.get_text(strip=True)

                clean_text = re.sub(r'\(\d{4}\)', '', text).strip()
                text_year = re.search(r'\((\d{4})\)', text)
                text_year = text_year.group(1) if text_year else None

                ratio = difflib.SequenceMatcher(None, title_pt.lower(), clean_text.lower()).ratio()
                score = ratio

                if year and text_year and abs(int(year) - int(text_year)) <= 1:
                    score += 0.4

                if score > best_score and score > 0.78:
                    best_score = score
                    best_url = href

            if not best_url:
                return []

            film_resp = session.get(best_url, timeout=20)
            if film_resp.status_code != 200:
                return []

            post_id_match = re.search(r'data-post=["\'](\d+)["\']', film_resp.text)
            if not post_id_match:
                return []

            post_id = post_id_match.group(1)
            return cls._get_player_urls(post_id, film_resp.text)

        except Exception:
            return []

    @classmethod
    def search_tvshows(cls, imdb, season, episode):
        title_pt, original_title, imdb_year = cls.find_title(imdb)
        if not title_pt:
            return []

        title_pt = cls.normalize_title(title_pt)
        s = str(int(season))
        e = str(int(episode)).zfill(2)

        try:
            search_url = f"https://cinevibehd.com/?s={quote_plus(title_pt)}"
            r = session.get(search_url, timeout=20)
            if r.status_code != 200:
                return []

            soup = BeautifulSoup(r.text, 'html.parser')
            serie_link = soup.find('a', href=re.compile(r'/series/[^/]+/$'))
            if not serie_link:
                return []

            series_url = serie_link['href']
            series_resp = session.get(series_url, timeout=30)
            if series_resp.status_code != 200:
                return []

            html = series_resp.text
            soup_series = BeautifulSoup(html, 'html.parser')

            episode_pattern = re.compile(rf'/episodios/[^/]+-{s}x{e}[^/]*/?$', re.I)
            ep_link = soup_series.find('a', href=episode_pattern)

            if not ep_link:
                fallback_patterns = [
                    rf'{s}x{int(episode)}',
                    rf'{s}x{int(episode):02d}',
                    rf'{int(s):02d}x{int(episode):02d}',
                ]
                for pat in fallback_patterns:
                    ep_link = soup_series.find('a', href=re.compile(rf'/episodios/[^/]+-{pat}[^/]*/?$', re.I))
                    if ep_link:
                        break

            if not ep_link:
                return []

            episode_url = ep_link['href']
            if not episode_url.startswith('http'):
                episode_url = 'https://cinevibehd.com' + episode_url

            ep_resp = session.get(episode_url, timeout=30)
            if ep_resp.status_code != 200:
                return []

            post_id_match = re.search(r'data-post=["\'](\d+)["\']', ep_resp.text)
            if not post_id_match:
                return []

            post_id = post_id_match.group(1)
            return cls._get_player_urls(post_id, ep_resp.text, season=season, episode=episode)

        except Exception:
            return []

    @classmethod
    def resolve_movies(cls, url):
        streams = []
        if not url:
            return streams

        sub = ''
        try:
            if 'http' in url:
                parts = url.split('http')
                sub_candidate = 'http' + parts[-1].split('&')[0]
                if '.srt' in sub_candidate:
                    sub = sub_candidate
        except:
            pass

        stream = url.split('?')[0].split('#')[0]
        resolver = Resolver()
        resolved, sub_from_resolver = resolver.resolverurls(stream)
        if resolved:
            streams.append((resolved, sub or sub_from_resolver, USER_AGENT))

        return streams

    @classmethod
    def resolve_tvshows(cls, url):
        return cls.resolve_movies(url)
