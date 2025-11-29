# -*- coding: utf-8 -*-

WEBSITE = 'ASSISTIRBIZ'

try:
    from resources.lib.ClientScraper import cfscraper, USER_AGENT
except Exception:
    from ClientScraper import cfscraper, USER_AGENT

import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urlparse, urljoin
import os
import sys
import re
import difflib
import base64
import json
import unicodedata

try:
    from kodi_helper import myAddon
    addonId = re.search('plugin://(.+?)/', str(sys.argv[0])).group(1)
    addon = myAddon(addonId)
    select = addon.select
except ImportError:
    pass

try:
    from resources.lib import resolveurl
except ImportError:
    local_path = os.path.dirname(os.path.realpath(__file__))
    lib_path = local_path.replace('scrapers', '')
    sys.path.append(lib_path)
    from resolvers import resolveurl


def remover_acentos(texto):
    return ''.join(c for c in unicodedata.normalize('NFD', texto)
                   if unicodedata.category(c) != 'Mn').lower()


class source:
    __site_url__ = ['https://assistir.biz/']

    @classmethod
    def find_title(cls, imdb):
        url = f'https://m.imdb.com/pt/title/{imdb}'
        try:
            r = cfscraper.get(url)
            if not r or r.status_code != 200:
                return '', '', ''
            soup = BeautifulSoup(r.text, 'html.parser')
            title = ''
            h1 = soup.find('h1', {'data-testid': 'hero__pageTitle'})
            if h1:
                span = h1.find('span')
                title = span.text.strip() if span else h1.text.strip()
            original_title = ''
            original_tag = soup.find(lambda tag: tag.name == 'div' and 'Título original' in tag.get_text())
            if original_tag:
                original_title = original_tag.get_text(strip=True).replace('Título original:', '').strip()
            year = ''
            try:
                year_element = soup.find('a', {'class': re.compile(r'ipc-link.*titleYear')})
                if year_element:
                    ym = re.search(r'\d{4}', year_element.text)
                    if ym:
                        year = ym.group(0)
            except Exception:
                pass
            if not year:
                release_element = soup.find('a', {'data-testid': re.compile(r'release-date-item|title-details-releasedate')})
                if release_element:
                    ym = re.search(r'\d{4}', release_element.text)
                    if ym:
                        year = ym.group(0)
            return title, original_title, year
        except Exception:
            return '', '', ''

    @classmethod
    def _get_video_data(cls, vid_id, vid_token, referer=None):
        if not referer:
            referer = cls.__site_url__[-1]
        headers = {'User-Agent': USER_AGENT, 'Referer': referer, 'X-Requested-With': 'XMLHttpRequest'}
        ajax_url = urljoin(cls.__site_url__[-1], '/getepisodio')
        data = {'id': vid_id, 'token': vid_token}
        try:
            r_ajax = cfscraper.post(ajax_url, data=data, headers=headers)
        except Exception:
            return None
        if not r_ajax or r_ajax.status_code != 200:
            return None
        try:
            json_data = json.loads(r_ajax.text)
            if isinstance(json_data, dict) and json_data.get('error'):
                return None
            return json_data
        except Exception:
            return None

    @classmethod
    def _construct_player_url(cls, json_data):
        if not json_data:
            return None
        hls = str(json_data.get('hls', '0'))
        hd = str(json_data.get('hd', '0'))
        dir_path = json_data.get('dir_path', '') or ''
        serie_ep = json_data.get('serie_ep', '') or ''
        vid_id = str(json_data.get('id', '')) or ''
        token = json_data.get('token', '') or ''
        host = urlparse(cls.__site_url__[-1]).netloc

        if hd == '1' and hls == '0':
            return f"https://{host}/playserie/{vid_id}/{token}"

        try:
            enc_dir = base64.b64encode(dir_path.encode()).decode()
            enc_serie = base64.b64encode(serie_ep.encode()).decode()
            enc_id = base64.b64encode(vid_id.encode()).decode()
            enc_token = base64.b64encode(token.encode()).decode()
        except Exception:
            enc_dir = base64.b64encode(dir_path.encode('utf-8', 'ignore')).decode()
            enc_serie = base64.b64encode(serie_ep.encode('utf-8', 'ignore')).decode()
            enc_id = base64.b64encode(vid_id.encode('utf-8', 'ignore')).decode()
            enc_token = base64.b64encode(token.encode('utf-8', 'ignore')).decode()

        return f"https://{host}/selector?q=hls&dir={enc_dir}&serie={enc_serie}&id={enc_id}&token={enc_token}"

    @classmethod
    def _extract_players_from_page(cls, url):
        headers = {'User-Agent': USER_AGENT, 'Referer': url}
        try:
            r = cfscraper.get(url, headers=headers)
        except Exception:
            return None
        if not r or r.status_code != 200:
            return None

        html = r.text
        soup = BeautifulSoup(html, 'html.parser')

        best_url = None
        best_score = -1

        # Pontuação por qualidade (maior = melhor)
        quality_score = {'1080': 1080, '720': 720, '480': 480, '360': 360, 'hd': 720, 'sd': 360}

        # 1. <source> com size (ex: size="720")
        for source in soup.find_all('source'):
            src = source.get('src')
            size = source.get('size', '').strip().lower()
            if src and size.isdigit():
                score = int(size)
                if score > best_score:
                    best_score = score
                    best_url = src if src.startswith('http') else ('https:' + src if src.startswith('//') else urljoin(url, src))

        # 2. Links do tipo selector?q=hd ou q=sd
        selector_links = re.findall(r'(//[^"\']*selector\?[^"\']*q=(hd|sd)[^"\']*)', html, re.I)
        for link, q in selector_links:
            score = quality_score.get(q.lower(), 0)
            if score > best_score:
                best_score = score
                best_url = 'https:' + link

        # 3. Fallback: qualquer source ou mp4/m3u8 direto (prioriza o primeiro com "hd" no link)
        if not best_url:
            fallback = re.search(r'<source[^>]+src=["\']([^"\']+)["\']', html, re.I)
            if not fallback:
                fallback = re.search(r'["\'](https?://[^"\']+\.(mp4|m3u8)[^"\']*)["\']', html, re.I)
            if fallback:
                candidate = fallback.group(1)
                if candidate.startswith('//'):
                    candidate = 'https:' + candidate
                elif not candidate.startswith('http'):
                    candidate = urljoin(url, candidate)
                # Prioriza se tiver "hd" no link
                score = 720 if 'hd' in candidate.lower() else 360
                if score > best_score:
                    best_url = candidate

        return best_url

    @classmethod
    def search_movies(cls, imdb, year):
        links = []
        title, original_title, imdb_year = cls.find_title(imdb)
        if not title and not original_title:
            return links
        try:
            titulo_busca = remover_acentos(title)
            query = quote_plus(titulo_busca)
            search_url = cls.__site_url__[-1].rstrip('/') + f'/busca?q={query}'
            r = cfscraper.get(search_url)
            if not r or r.status_code != 200:
                return links
            soup = BeautifulSoup(r.text, 'html.parser')
            cards = soup.find_all('div', class_='card')
            movie_url = None
            for card in cards:
                a = card.find('a', href=re.compile(r'/filme/'))
                if not a:
                    continue
                href = urljoin(cls.__site_url__[-1], a.get('href'))
                found_title = card.find('h3', class_='card__title').text.strip() if card.find('h3', class_='card__title') else ''
                found_year = card.find('span', class_='span-year').text.strip() if card.find('span', class_='span-year') else ''
                sim = difflib.SequenceMatcher(None, titulo_busca, remover_acentos(found_title)).ratio()
                if sim >= 0.60 and (not imdb_year or found_year == imdb_year):
                    movie_url = href
                    break
            if not movie_url:
                return links
            r_movie = cfscraper.get(movie_url)
            if not r_movie or r_movie.status_code != 200:
                return links
            html = r_movie.text
            soup_movie = BeautifulSoup(html, 'html.parser')
            iframes = soup_movie.find_all('iframe', class_='iframe-fix')
            for i, iframe in enumerate(iframes):
                iframe_url = iframe.get('src') or ''
                if not iframe_url:
                    continue
                iframe_url = iframe_url if iframe_url.startswith('http') else urljoin(cls.__site_url__[-1], iframe_url)
                vid_url = cls._extract_players_from_page(iframe_url)
                if vid_url:
                    links.append((f"{WEBSITE} - PLAYER {i+1}", vid_url))
                else:
                    links.append((f"{WEBSITE} - PLAYER {i+1}", iframe_url))
            if not links:
                id_match = re.search(r'reloadVideo(?:Serie|Filme)\(\s*[\'"]([^\'"]+)[\'"]\s*,\s*[\'"]([^\'"]+)[\'"]\s*\)', html)
                if id_match:
                    vid_id, vid_token = id_match.groups()
                    json_data = cls._get_video_data(vid_id, vid_token, referer=movie_url)
                    player_url = cls._construct_player_url(json_data)
                    if player_url:
                        vid_url = cls._extract_players_from_page(player_url)
                        if vid_url:
                            links.append((f"{WEBSITE} - Português", vid_url))
                        else:
                            links.append((f"{WEBSITE} - Português", player_url))
            return links
        except Exception:
            return links

    @classmethod
    def search_tvshows(cls, imdb, year, season, episode):
        links = []
        title, original_title, imdb_year = cls.find_title(imdb)
        if not title and not original_title:
            return links
        try:
            titulo_busca = remover_acentos(title or original_title)
            query = quote_plus(titulo_busca)
            search_url = cls.__site_url__[-1].rstrip('/') + f'/busca?q={query}'
            r = cfscraper.get(search_url)
            if not r or r.status_code != 200:
                return links
            soup = BeautifulSoup(r.text, 'html.parser')
            cards = soup.find_all('div', class_='card')
            series_url = None
            for card in cards:
                a = card.find('a', href=re.compile(r'/serie/'))
                if not a:
                    continue
                href = urljoin(cls.__site_url__[-1], a.get('href'))
                found_title = card.find('h3', class_='card__title').text.strip() if card.find('h3', class_='card__title') else ''
                found_year = card.find('span', class_='span-year').text.strip() if card.find('span', class_='span-year') else ''
                sim = difflib.SequenceMatcher(None, titulo_busca, remover_acentos(found_title)).ratio()
                if sim >= 0.60 and (not imdb_year or found_year == imdb_year):
                    series_url = href
                    break
            if not series_url:
                return links
            season_url = f"{series_url}/temporada-{season}"
            r_season = cfscraper.get(season_url)
            if not r_season or r_season.status_code != 200:
                return links
            soup_season = BeautifulSoup(r_season.text, 'html.parser')
            episode_table = soup_season.find('table', class_='accordion__list')
            if episode_table:
                tbody = episode_table.find('tbody')
                if tbody:
                    rows = tbody.find_all('tr')
                    for row in rows:
                        ths = row.find_all('th')
                        if not ths:
                            continue
                        ep_str = ths[0].get_text(strip=True)
                        try:
                            found_ep = int(re.search(r'\d+', ep_str).group(0))
                        except Exception:
                            continue
                        if found_ep != int(episode):
                            continue
                        onclick = row.get('onclick') or ''
                        id_match = re.search(r'reloadVideoSerie\(\s*[\'"]?([^\'"\)]+)[\'"]?\s*,\s*[\'"]([^\'"]+)[\'"]\s*\)', onclick)
                        if id_match:
                            vid_id, vid_token = id_match.groups()
                            json_data = cls._get_video_data(vid_id, vid_token, referer=season_url)
                            if json_data:
                                player_url = cls._construct_player_url(json_data)
                                if player_url:
                                    links.append((f"{WEBSITE} - Português", player_url))
                            break
            else:
                html = r_season.text
                id_match = re.search(r'reloadVideoSerie\(\s*[\'"]([^\'"]+)[\'"]\s*,\s*[\'"]([^\'"]+)[\'"]\s*\)', html)
                if id_match:
                    vid_id, vid_token = id_match.groups()
                    json_data = cls._get_video_data(vid_id, vid_token, referer=season_url)
                    if json_data:
                        player_url = cls._construct_player_url(json_data)
                        if player_url:
                            links.append((f"{WEBSITE} - Português", player_url))
            return links
        except Exception:
            return links

    @classmethod
    def resolve_movies(cls, url):
        streams = []
        if not url or not url.startswith('http'):
            return streams

        full_url = url.strip()

        sub = ''
        m_sub = re.search(r'([&#])(https?://[^\s\'\"]+)', url)
        if m_sub and '.srt' in m_sub.group(2):
            sub = m_sub.group(2)

        try:
            resolved, sub_res = resolveurl(full_url, referer='https://assistir.biz/')
            if resolved and resolved != full_url:
                final_sub = sub or sub_res or ''
                streams.append((resolved, final_sub, USER_AGENT))
            else:
                if any(x in full_url for x in ['mediafire.com', 'mv.astr.digital', 'hls.astr.digital']):
                    headers = f"|User-Agent={USER_AGENT}&Referer=https://assistir.biz/"
                    streams.append((full_url + headers, sub, USER_AGENT))
        except Exception:
            pass

        return streams

    @classmethod
    def resolve_tvshows(cls, url):
        return cls.resolve_movies(url)