# -*- coding: utf-8 -*-

WEBSITE = 'ASSISTIRBIZ'

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
import socket

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

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36'

class DNSResolver:
    def __init__(self, dns_servers=['1.1.1.1', '1.0.0.1', '8.8.8.8', '8.8.4.4']):
        self.etc_hosts = {}
        self.cache_resolve_dns = {}
        self.dns_servers = dns_servers

    def dns_query_custom(self, hostname):
        query = b'\xaa\xbb\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00' + \
                b''.join(bytes([len(part)]) + part.encode('ascii') for part in hostname.split('.')) + \
                b'\x00\x00\x01\x00\x01'

        for dns_server in self.dns_servers:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(3)
                sock.sendto(query, (dns_server, 53))
                response, _ = sock.recvfrom(1024)
                sock.close()

                i = 12
                qlen = response[i]
                i += 1 + qlen
                while qlen != 0:
                    qlen = response[i]
                    i += 1 + qlen
                i += 4
                i += 10
                rdlen = response[i] * 256 + response[i+1]
                i += 2
                ip_bytes = response[i:i+4]
                return '.'.join(str(b) for b in ip_bytes)
            except Exception:
                continue
        raise Exception("Todos os DNS falharam")

    def _change_dns(self, domain_name, port, ip):
        key = (domain_name, port)
        value = (socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, port))
        self.etc_hosts[key] = [value]

    def change(self, url):
        if not hasattr(socket, '_original_getaddrinfo'):
            socket._original_getaddrinfo = socket.getaddrinfo

        socket.getaddrinfo = self.resolver(socket._original_getaddrinfo)

        parsed_url = urlparse(url)
        port = parsed_url.port or (443 if parsed_url.scheme == 'https' else 80)
        host = parsed_url.hostname

        if 'assistir.biz' not in host:
            return

        if host not in self.cache_resolve_dns:
            try:
                ip_address = self.dns_query_custom(host)
            except Exception:
                try:
                    ip_address = socket.gethostbyname(host)
                except Exception:
                    ip_address = '127.0.0.1'
            self.cache_resolve_dns[host] = ip_address

        self._change_dns(host, port, self.cache_resolve_dns[host])

    def resolver(self, builtin_resolver):
        def wrapper(*args, **kwargs):
            try:
                return self.etc_hosts[args[:2]]
            except KeyError:
                return builtin_resolver(*args, **kwargs)
        return wrapper

dns_resolver = DNSResolver()

def remover_acentos(texto):
    return ''.join(c for c in unicodedata.normalize('NFD', texto)
                   if unicodedata.category(c) != 'Mn').lower()

def get_page(url, referer=None):
    headers = {'User-Agent': USER_AGENT}
    if referer:
        headers['Referer'] = referer
    dns_resolver.change(url)
    try:
        return requests.get(url, headers=headers)
    except Exception:
        return None

def post_page(url, data, referer=None):
    headers = {
        'User-Agent': USER_AGENT,
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': referer or url
    }
    dns_resolver.change(url)
    try:
        return requests.post(url, data=data, headers=headers)
    except Exception:
        return None


class source:
    __site_url__ = ['https://assistir.biz/']

    @classmethod
    def find_title(cls, imdb):
        url = f'https://m.imdb.com/pt/title/{imdb}'
        r = get_page(url)
        try:
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
        ajax_url = urljoin(cls.__site_url__[-1], '/getepisodio')
        data = {'id': vid_id, 'token': vid_token}
        r_ajax = post_page(ajax_url, data, referer=referer)
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
        r = get_page(url, referer=url)
        if not r or r.status_code != 200:
            return None

        html = r.text
        soup = BeautifulSoup(html, 'html.parser')

        best_url = None
        best_score = -1

        quality_score = {'1080': 1080, '720': 720, '480': 480, '360': 360, 'hd': 720, 'sd': 360}

        for source in soup.find_all('source'):
            src = source.get('src')
            size = source.get('size', '').strip().lower()
            if src and size.isdigit():
                score = int(size)
                if score > best_score:
                    best_score = score
                    best_url = src if src.startswith('http') else ('https:' + src if src.startswith('//') else urljoin(url, src))

        selector_links = re.findall(r'(//[^"\']*selector\?[^"\']*q=(hd|sd)[^"\']*)', html, re.I)
        for link, q in selector_links:
            score = quality_score.get(q.lower(), 0)
            if score > best_score:
                best_score = score
                best_url = 'https:' + link

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
            r = get_page(search_url)
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
            r_movie = get_page(movie_url)
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
                            links.append((f"{WEBSITE} - DUBLADO", vid_url))
                        else:
                            links.append((f"{WEBSITE} - DUBLADO", player_url))
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
            r = get_page(search_url)
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
            r_season = get_page(season_url)
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
                                    links.append((f"{WEBSITE} - DUBLADO", player_url))
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
                            links.append((f"{WEBSITE} - DUBLADO", player_url))
            return links
        except Exception:
            return links

    @classmethod
    def resolve_movies(cls, url):
        streams = []
        if not url:
            return streams
        sub = ''
        try:
            if 'http' in url:
                parts = url.split('http')
                if len(parts) > 2:
                    sub_candidate = 'http' + parts[2].split('&')[0]
                    if sub_candidate.endswith('.srt'):
                        sub = sub_candidate
        except Exception:
            pass
        resolver = Resolver()
        try:
            resolved, sub_from_resolver = resolver.resolverurls(url)
            if resolved:
                streams.append((resolved, sub if sub else sub_from_resolver, USER_AGENT))
        except Exception:
            pass
        return streams

    @classmethod
    def resolve_tvshows(cls, url):
        return cls.resolve_movies(url)
