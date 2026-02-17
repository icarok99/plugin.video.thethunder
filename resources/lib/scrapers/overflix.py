# -*- coding: utf-8 -*-

WEBSITE = 'OVERFLIX'

import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urlparse, urljoin
import os
import sys
import re
import difflib

session = requests.Session()
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'
session.headers.update({
    'User-Agent': USER_AGENT,
    'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept': '*/*',
    'Referer': 'https://www.overflixtv.bar/',
})

try:
    import xbmcaddon
    addon = xbmcaddon.Addon()
    DUBBED = addon.getLocalizedString(30200)
    SUBTITLED = addon.getLocalizedString(30202)
except:
    DUBBED = 'DUBLADO'
    SUBTITLED = 'LEGENDADO'

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

    domain = [
        'https://www.overflixtv.bar/',
    ]

    @classmethod
    def get_active_domain(cls):
        for seed in cls.domain:
            try:
                r = session.get(seed, timeout=10, allow_redirects=True)
                if r.status_code not in (200, 301, 302):
                    continue

                final_url = r.url.rstrip('/')
                html = r.text

                match = re.search(
                    r'🔴\s*(?:<i>)?\s*(?:<b[^>]*>)?\s*(?:NOVO LINK|NOVO LINK)\s*(?:</b>)?\s*(?:</i>)?\s*»?\s*(?:<b[^>]*>)?\s*<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>',
                    html,
                    re.IGNORECASE | re.DOTALL | re.MULTILINE
                )

                if not match:
                    match = re.search(
                        r'(novo\s*link|novo\s*dom[íi]nio)\s*»?\s*<[^>]*href=["\']([^"\']+)["\']',
                        html,
                        re.IGNORECASE | re.DOTALL
                    )

                if not match:
                    match = re.search(
                        r'(novo|atual)\b[^<]{0,100}?(https?://www\.overflixtv\.[a-z]{2,6}/?)[^<]*',
                        html,
                        re.IGNORECASE | re.DOTALL
                    )

                if match:
                    candidate = next((g for g in match.groups() if g and g.startswith('http')), None)
                    if candidate:
                        candidate = urljoin(seed, candidate).rstrip('/')
                        try:
                            head = session.head(candidate, timeout=6, allow_redirects=True)
                            if head.status_code in (200, 301, 302):
                                return candidate
                        except:
                            pass

            except:
                continue

        return cls.domain[-1].rstrip('/')

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

        except:
            return '', '', ''

    @classmethod
    def _extract_embeds_from_page(cls, html):
        embeds = []
        soup = BeautifulSoup(html, 'html.parser')

        append_match = re.search(r'append\(\'<iframe src="([^"]+?)/e/getembed\.php', html)
        embed_base = append_match.group(1) if append_match else "https://www.overflixtv.bar"

        token = '56f50bf220c22eb9ddab'
        token_append_match = re.search(r'append\(\'<iframe src="[^"]+?/e/getembed\.php\?[^"]*token=([a-f0-9]{20,})[^"]*\'', html)
        if token_append_match:
            token = token_append_match.group(1)
        else:
            token_match_var = re.search(r'token\s*=\s*["\']([a-f0-9]{20,})["\']', html)
            if token_match_var:
                token = token_match_var.group(1)
            else:
                token_match_any = re.search(r'&token=([a-f0-9]{20,})', html)
                if token_match_any:
                    token = token_match_any.group(1)

        player_divs = soup.find_all('div', class_='item', onclick=re.compile(r'C_Video\([^)]+\)'))
        for div in player_divs:
            onclick = div.get('onclick', '')
            match = re.search(r"C_Video\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"](?:\s*,\s*['\"][^'\"]*['\"])?\s*\)", onclick)
            if not match:
                continue
            player_id, server = match.groups()
            getembed = f"{embed_base}/e/getembed.php?sv={server}&id={player_id}&token={token}"
            server_name = server.upper()
            embeds.append((server_name, getembed, {'id': player_id, 'sv': server, 'token': token}))
        return embeds

    @classmethod
    def _get_play_url(cls, referer_url, getembed_url, meta):
        parsed = urlparse(getembed_url)
        base_url = parsed.scheme + '://' + parsed.netloc

        id_ = meta.get('id')
        sv = meta.get('sv')
        play_url = f"{base_url}/e/getplay.php?id={id_}&sv={sv}"

        headers = {
            'Referer': getembed_url
        }
        try:
            r2 = session.get(play_url, headers=headers, allow_redirects=True, timeout=10)
            if r2.status_code != 200:
                return None
            if r2.history:
                return r2.url
            html = r2.text
            patterns = [
                r'window\.location\.href\s*=\s*[\'"](https?://(?:filemoon|dood|doodstream|mixdrop|streamtape)\.[a-z0-9.-]+/[^\s"\']+)[\'"]',
                r'<iframe[^>]+src=[\'"](https?://(?:filemoon|dood|doodstream|mixdrop|streamtape)\.[a-z0-9.-]+/[^\s"\']+)[\'"]',
                r'(?:href|src)=[\'"](https?://(?:filemoon|dood|doodstream|mixdrop|streamtape)\.[a-z0-9.-]+/[^\s"\']+)[\'"]',
                r'var\s+videoUrl\s*=\s*[\'"](https?://(?:filemoon|dood|doodstream|mixdrop|streamtape)\.[a-z0-9.-]+/[^\s"\']+)[\'"]'
            ]
            final_video = None
            for pattern in patterns:
                match = re.search(pattern, html, re.I)
                if match:
                    final_video = match.group(1)
                    break
            if not final_video:
                if sv == 'doodstream':
                    redirect = re.search(r'window\.location\.href\s*=\s*[\'"](https?://dsvplay\.com/[^\s"\']+)[\'"]', html, re.I)
                    if redirect:
                        final_video = redirect.group(1)
                elif sv == 'filemoon':
                    iframe = re.search(r'<iframe[^>]+src=[\'"](https?://filemoon\.[a-z0-9.-]+/[^\s"\']+)[\'"]', html, re.I)
                    if iframe:
                        final_video = iframe.group(1)
                elif sv == 'mixdrop':
                    mixdrop = re.search(r'(?:window\.location\.href|var\s+videoUrl)\s*=\s*[\'"](https?://mixdrop\.[a-z0-9.-]+/[^\s"\']+)[\'"]', html, re.I)
                    if mixdrop:
                        final_video = mixdrop.group(1)
            return final_video
        except:
            return None

    @classmethod
    def search_movies(cls, imdb, year):
        site_url = cls.get_active_domain()
        links = []
        title, original_title, imdb_year = cls.find_title(imdb)
        if not title and not original_title:
            return links

        title = cls.normalize_title(title)
        original_title = cls.normalize_title(original_title or title)

        try:
            def perform_search(search_title):
                try:
                    query = quote_plus(search_title)
                    search_url = site_url.rstrip('/') + '/pesquisar/?p=' + query
                    r = session.get(search_url)
                    if not r or r.status_code != 200 or "captcha" in r.text.lower():
                        return {}, None
                    soup = BeautifulSoup(r.text, 'html.parser')
                    results = soup.find_all('a', href=re.compile(r'/assistir-.*-\d{4}-[^/]+'))
                    movie_urls = {}
                    for item in results:
                        href = urljoin(site_url, item['href'])
                        found_title = None
                        caption_div = item.find('div', class_='caption')
                        if caption_div:
                            found_title = caption_div.find(text=True, recursive=False)
                            if found_title:
                                found_title = found_title.strip()
                        if not found_title:
                            for tag in ['span', 'h2', 'div', 'p']:
                                title_element = item.find(tag, class_=re.compile(r'title|name|movie-title|text', re.I))
                                if title_element:
                                    found_title = title_element.get_text(strip=True)
                                    break
                        if not found_title:
                            found_title = item.get_text(strip=True)
                        found_title_cleaned = re.sub(r'(?i)(dublado|legendado|\d{4}\d+min$)', '', found_title).strip()
                        y_match = re.search(r'-(\d{4})-([^/]+)/?$', href)
                        found_year = y_match.group(1) if y_match else None
                        title_similarity = difflib.SequenceMatcher(None, title, found_title_cleaned).ratio() * 100
                        original_title_similarity = difflib.SequenceMatcher(None, original_title, found_title_cleaned).ratio() * 100 if original_title else 0
                        max_similarity = max(title_similarity, original_title_similarity)
                        if max_similarity >= 50 and found_year and int(year) == int(found_year):
                            if not imdb_year or (imdb_year and found_year == imdb_year):
                                if 'dublado' in href.lower():
                                    movie_urls['dublado'] = href
                                elif 'legendado' in href.lower():
                                    movie_urls['legendado'] = href
                    return movie_urls, r
                except:
                    return {}, None

            movie_urls, r = perform_search(title)

            if (not movie_urls or len(movie_urls) == 0) and original_title.lower() != title.lower():
                movie_urls, r = perform_search(original_title)

            if not movie_urls:
                return links

            r = session.get(f"{movie_urls.get('dublado', movie_urls.get('legendado', ''))}?area=online", headers={'Referer': site_url})
            if not r or r.status_code != 200 or "captcha" in r.text.lower():
                return links
            embeds_final = []
            soup0 = BeautifulSoup(r.text, 'html.parser')
            audio_tabs = soup0.find('span', class_='tab_order')
            languages = ['dublado', 'legendado'] if audio_tabs else ['dublado']
            for lang in languages:
                lang_label = DUBBED if lang == 'dublado' else SUBTITLED
                lang_url = movie_urls.get(lang)
                if lang_url:
                    if 'area=online' not in lang_url:
                        sep = '&' if '?' in lang_url else '?'
                        lang_url = lang_url + sep + 'area=online'
                else:
                    lang_url = None

                if not lang_url:
                    continue

                rlang = session.get(lang_url, headers={'Referer': site_url})
                if not rlang or rlang.status_code != 200 or "captcha" in rlang.text.lower():
                    continue
                embeds = cls._extract_embeds_from_page(rlang.text)
                if not embeds:
                    continue
                for server_name, getembed_url, meta in embeds:
                    final_video = cls._get_play_url(referer_url=lang_url, getembed_url=getembed_url, meta=meta)
                    if final_video:
                        name = f"{server_name} - {lang_label}"
                        embeds_final.append((name, final_video))
            return embeds_final
        except:
            return links

    @classmethod
    def search_tvshows(cls, imdb, season, episode):
        site_url = cls.get_active_domain()
        links = []
        title, original_title, imdb_year = cls.find_title(imdb)
        if not title:
            return links

        title = cls.normalize_title(title)
        original_title = cls.normalize_title(original_title or title)

        try:
            def perform_search(search_title):
                try:
                    query = quote_plus(search_title)
                    search_url = site_url.rstrip('/') + '/pesquisar/?p=' + query
                    r = session.get(search_url)
                    if not r or r.status_code != 200 or "captcha" in r.text.lower():
                        return {}, None
                    soup = BeautifulSoup(r.text, 'html.parser')
                    results = soup.find_all('a', href=re.compile(r'/assistir-.*-\d{4}-[^/]+'))
                    series_urls = {}
                    for item in results:
                        href = urljoin(site_url, item['href'])
                        found_title = None
                        caption_div = item.find('div', class_='caption')
                        if caption_div:
                            found_title = caption_div.find(text=True, recursive=False)
                            if found_title:
                                found_title = found_title.strip()
                        if not found_title:
                            for tag in ['span', 'h2', 'div', 'p']:
                                title_element = item.find(tag, class_=re.compile(r'title|name|movie-title|text', re.I))
                                if title_element:
                                    found_title = title_element.get_text(strip=True)
                                    break
                        if not found_title:
                            found_title = item.get_text(strip=True)
                        found_title_cleaned = re.sub(r'(?i)(dublado|legendado|\d{4}\d+min$)', '', found_title).strip()
                        y_match = re.search(r'-(\d{4})-([^/]+)/?$', href)
                        found_year = y_match.group(1) if y_match else None
                        title_similarity = difflib.SequenceMatcher(None, title, found_title_cleaned).ratio() * 100
                        original_title_similarity = difflib.SequenceMatcher(None, original_title, found_title_cleaned).ratio() * 100 if original_title else 0
                        max_similarity = max(title_similarity, original_title_similarity)
                        if max_similarity >= 50 and found_year:
                            if not imdb_year or (imdb_year and found_year == imdb_year):
                                if 'dublado' in href.lower():
                                    series_urls['dublado'] = href
                                elif 'legendado' in href.lower():
                                    series_urls['legendado'] = href
                    return series_urls, r
                except:
                    return {}, None

            series_urls, r = perform_search(title)

            if (not series_urls or len(series_urls) == 0) and original_title.lower() != title.lower():
                series_urls, r = perform_search(original_title)

            if not series_urls:
                return links

            embeds_final = []
            languages = ['dublado', 'legendado']
            for lang in languages:
                series_url = series_urls.get(lang)

                if not series_url:
                    continue

                r = session.get(series_url, headers={'Referer': site_url})
                if not r or r.status_code != 200 or "captcha" in r.text.lower():
                    continue
                soup = BeautifulSoup(r.text, 'html.parser')
                episode_links = soup.find_all('a', href=re.compile(r'/assistir-.*-(\d+)x(\d+)-([a-z]+)(?:-[a-z0-9]+)?-\d+/?$'))
                episode_url = None
                for item in episode_links:
                    href = urljoin(site_url, item['href'])
                    ep_match = re.search(r'-(\d+)x(\d+)-([a-z]+)(?:-[a-z0-9]+)?-(\d+)/?$', href, re.I)
                    if ep_match:
                        found_season = int(ep_match.group(1))
                        found_episode = int(ep_match.group(2))
                        found_lang_in_url = ep_match.group(3).lower()
                        lang_variations = [lang, 'leg'] if lang == 'legendado' else [lang]
                        if (found_season == int(season) and found_episode == int(episode) and 
                            found_lang_in_url in lang_variations):
                            episode_url = href
                            break

                if not episode_url:
                    season_url = f"{series_url.rstrip('/')}?temporada={season}"
                    r_season = session.get(season_url, headers={'Referer': site_url})
                    if r_season and r_season.status_code == 200 and "captcha" not in r_season.text.lower():
                        soup_season = BeautifulSoup(r_season.text, 'html.parser')
                        episode_links = soup_season.find_all('a', href=re.compile(r'/assistir-.*-(\d+)x(\d+)-([a-z]+)(?:-[a-z0-9]+)?-\d+/?$'))
                        for item in episode_links:
                            href = urljoin(site_url, item['href'])
                            ep_match = re.search(r'-(\d+)x(\d+)-([a-z]+)(?:-[a-z0-9]+)?-(\d+)/?$', href, re.I)
                            if ep_match:
                                found_season = int(ep_match.group(1))
                                found_episode = int(ep_match.group(2))
                                found_lang_in_url = ep_match.group(3).lower()
                                lang_variations = [lang, 'leg'] if lang == 'legendado' else [lang]
                                if (found_season == int(season) and found_episode == int(episode) and 
                                    found_lang_in_url in lang_variations):
                                    episode_url = href
                                    break

                if not episode_url:
                    continue

                lang_label = DUBBED if lang == 'dublado' else SUBTITLED
                lang_url = episode_url

                rlang = session.get(lang_url, headers={'Referer': site_url})
                if not rlang or rlang.status_code != 200 or "captcha" in rlang.text.lower():
                    continue
                embeds = cls._extract_embeds_from_page(rlang.text)
                if not embeds:
                    continue
                for server_name, getembed_url, meta in embeds:
                    final_video = cls._get_play_url(referer_url=lang_url, getembed_url=getembed_url, meta=meta)
                    if final_video:
                        name = f"{server_name} - {lang_label}"
                        embeds_final.append((name, final_video))
            return embeds_final
        except:
            return links

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
