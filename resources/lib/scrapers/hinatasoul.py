# -*- coding: utf-8 -*-
WEBSITE = 'HINATASOUL'

import re
import difflib
import unicodedata
from urllib.parse import quote_plus, urljoin, urlparse, parse_qs, unquote
from bs4 import BeautifulSoup
import requests

session = requests.Session()
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'
session.headers.update({
    'User-Agent': USER_AGENT,
    'Accept-Language': 'en-US,en;q=0.9,pt-BR;q=0.8,pt;q=0.7',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Referer': 'https://www.hinatasoulbr.vip/',
})

from resources.lib.resolver import Resolver


class source:

    QUOTE_MIN_CHARS = 60
    QUOTE_MIN_WORDS = 8

    @classmethod
    def _normalize(cls, text):
        if not text:
            return ""
        normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
        return normalized

    @classmethod
    def _normalize_movie_hyphen(cls, title):
        if not title:
            return title
        normalized = re.sub(
            r'\s*[\u002D\u2010\u2011\u2012\u2013\u2014\u2015-]\s*(the movie\b)',
            r' the movie',
            title,
            flags=re.I
        )
        return normalized

    @classmethod
    def _adjust_base_title(cls, title):
        if not title or '"' not in title:
            return title

        words = title.split()
        if len(title) < cls.QUOTE_MIN_CHARS and len(words) < cls.QUOTE_MIN_WORDS:
            return title

        adjusted = title.split('"', 1)[0].strip()
        return adjusted

    @classmethod
    def _clean_title(cls, title):
        if not title:
            return ""

        t = cls._normalize(title.lower())
        t = re.sub(r'\bassistir\s+online\b', '', t)
        t = re.sub(r'\bonline\b', '', t)
        t = re.sub(r'[\"“”\'`]', '', t)
        t = re.sub(r'[-_:]', ' ', t)
        t = re.sub(r'[()\[\]]', '', t)
        t = re.sub(r'\b(\d+)(?:st|nd|rd|th|ª|º)\b', r'\1', t)
        t = re.sub(r'\s+', ' ', t)
        cleaned = t.strip()
        return cleaned

    @classmethod
    def _strip_dublado(cls, text):
        stripped = re.sub(r'\bdublado\b', '', text).strip()
        return stripped

    @classmethod
    def _has_extra_words(cls, base_clean, cand_clean):
        has_extra = cls._strip_dublado(cand_clean) != base_clean
        return has_extra

    @classmethod
    def _extract_year(cls, text):
        if not text:
            return None
        m = re.search(r'\b(19|20)\d{2}\b', text)
        year = int(m.group()) if m else None
        return year

    @classmethod
    def _extract_season_number(cls, text):
        if not text:
            return None
        text_lower = text.lower()
        patterns = [
            r'\b(\d+)[ªº]?\s*(?:temporada|season|t|temp|s)\b',
            r'\b(temporada|season|t|temp|s)\s*(\d+)\b',
            r'\b(\d+)\s*(?:ª|º|st|nd|rd|th)?\s*(?:temporada|season)\b',
            r'\b(\d+)\b',
        ]
        season = None
        for pattern in patterns:
            m = re.search(pattern, text_lower)
            if m:
                try:
                    num = int(m.group(1))
                    if 1 <= num <= 20:
                        season = num
                        return season
                except:
                    pass
        return season

    @classmethod
    def _similarity_score(cls, base_titles, candidate_title, base_year=None, cand_year=None):
        cand_title = cls._normalize_movie_hyphen(candidate_title)
        cand_clean = cls._clean_title(cand_title)

        best_score = 0.0

        for base_title in base_titles:
            adj_base = cls._adjust_base_title(base_title)
            base_clean = cls._clean_title(adj_base)
            if not base_clean:
                continue

            if cls._has_extra_words(base_clean, cand_clean):
                continue

            score = difflib.SequenceMatcher(
                None,
                base_clean,
                cls._strip_dublado(cand_clean)
            ).ratio()

            if 'dublado' in cand_clean:
                score += 0.25

            if base_year and cand_year:
                score += 0.5 if base_year == cand_year else -0.5

            if score > best_score:
                best_score = score

        return best_score

    @classmethod
    def _extract_episode_links_from_page(cls, page_text):
        soup = BeautifulSoup(page_text, 'html.parser')
        items = soup.find_all('div', class_=re.compile(r'ultimos(?:Animes|Episodios)HomeItem'))
        
        episodes = {}
        for item in items:
            ep_num = None
            
            num_div = item.find('div', class_='ultimosEpisodiosHomeItemInfosNum')
            if num_div:
                text = num_div.get_text(strip=True)
                m = re.search(r'(?:episódio|ep|eps)\s*(\d+)', text, re.I)
                if m:
                    ep_num = int(m.group(1))
            
            if ep_num is None:
                title_div = item.find('div', class_='ultimosAnimesHomeItemInfosNome')
                title_text = title_div.get_text(strip=True) if title_div else ""
                
                patterns = [
                    r'(?:ep|eps|episódio)\s*(\d+)(?:\s|$|[^\d])',
                    r'episódio\s*(\d+)',
                    r'\b(\d{1,3})\b\s*(?:de\s*)?(?:episódio|ep|eps)?',
                    r'\b(\d+)\b'
                ]
                
                for pattern in patterns:
                    m = re.search(pattern, title_text, re.I)
                    if m:
                        ep_num = int(m.group(1))
                        break
            
            a = item.find('a', href=True)
            if a and '/videos/' in a['href'] and ep_num is not None:
                episodes[ep_num] = a['href']

        return episodes

    @classmethod
    def _build_page_url(cls, series_url, page_num):
        base = series_url.rstrip('/')
        if page_num <= 1:
            return base
        page_url = f"{base}/page/{page_num}"
        return page_url

    @classmethod
    def _get_episode_page_url(cls, series_url, episode_num):
        page_num = 1
        while True:
            page_url = cls._build_page_url(series_url, page_num)
            r = session.get(page_url, timeout=15)
            if not r.ok:
                break
            episodes = cls._extract_episode_links_from_page(r.text)
            if not episodes:
                break
            if episode_num in episodes:
                ep_url = urljoin("https://www.hinatasoulbr.vip/", episodes[episode_num])
                return ep_url
            page_num += 1

        r = session.get(series_url, timeout=15)
        if r.ok:
            episodes = cls._extract_episode_links_from_page(r.text)
            if episodes:
                fallback_ep = min(episodes.keys())
                fallback_url = urljoin("https://www.hinatasoulbr.vip/", episodes[fallback_ep])
                return fallback_url
        return None

    @classmethod
    def _get_movie_episode_url(cls, page_text):
        soup = BeautifulSoup(page_text, "html.parser")
        for item in soup.select("div.ultimosAnimesHomeItem"):
            if re.search(r'\bfilme\b', item.get_text(" ", strip=True), re.I):
                a = item.find("a", href=True)
                if a:
                    movie_url = urljoin("https://www.hinatasoulbr.vip/", a["href"])
                    return movie_url
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
        available = available if available else ["SD"]
        return available

    @classmethod
    def _extract_highest_quality_token(cls, episode_page_text):
        soup = BeautifulSoup(episode_page_text, 'html.parser')
        
        abas_box = soup.find('div', class_=re.compile(r'AbasBox', re.I))
        if not abas_box:
            return None, None

        available_qualities = {}
        for aba in abas_box.find_all('div', class_=re.compile(r'Aba', re.I)):
            text = aba.get_text(strip=True).upper()
            aba_type = aba.get('aba-type')
            data_target = aba.get('data-target')
            identifier = aba_type or data_target or str(len(available_qualities))
            
            if text in ("SD", "HD", "FULLHD", "FULL HD", "FHD"):
                norm_quality = "FULLHD" if text in ("FULLHD", "FULL HD", "FHD") else text
                available_qualities[norm_quality] = identifier

        if not available_qualities:
            return None, None

        priority_order = ["FULLHD", "HD", "SD"]
        selected_quality = None
        for q in priority_order:
            if q in available_qualities:
                selected_quality = q
                break

        if not selected_quality:
            selected_quality = next(iter(available_qualities.keys()))

        containers = soup.find_all('div', class_='playerContainer')
        if not containers:
            return None, None

        target_index = int(available_qualities[selected_quality])
        selected_container = None
        
        if target_index < len(containers):
            selected_container = containers[target_index]
        else:
            for container in containers:
                if 'filezt.php?t=' in str(container):
                    selected_container = container
                    break

        if not selected_container:
            return None, None

        soup_cont = BeautifulSoup(str(selected_container), 'html.parser')
        a_tag = soup_cont.find('a', href=re.compile(r'https://foodiesbrazil\.info/filezt\.php\?t='))
        if not a_tag:
            return None, None

        href = a_tag['href']
        if '?t=' not in href:
            return None, None

        token = href.split('?t=', 1)[1].strip()
        return selected_quality, token

    @classmethod
    def _get_direct_mp4_from_token_302(cls, token):
        if not token:
            return None
        
        step1_url = f"https://ondeviajar.online/data5.php?token={token}"
        
        try:
            response = session.get(step1_url, allow_redirects=False, timeout=15)
            redirect_url = None
            
            if response.status_code in [301, 302, 303, 307, 308]:
                redirect_url = response.headers.get('Location')
            
            if not redirect_url and len(response.text) > 0:
                soup = BeautifulSoup(response.text, 'html.parser')
                meta_refresh = soup.find('meta', attrs={'http-equiv': re.compile('refresh', re.I)})
                
                if meta_refresh:
                    content = meta_refresh.get('content', '')
                    patterns = [
                        r'url=(["\']?)([^"\'>\s]+)\1',
                        r'url\s*=\s*(["\']?)([^"\'>\s]+)\1',
                        r';\s*url\s*=\s*(["\']?)([^"\'>\s]+)\1'
                    ]
                    
                    for pattern in patterns:
                        match = re.search(pattern, content, re.I)
                        if match:
                            redirect_url = match.group(2).strip()
                            break
            
            if not redirect_url:
                return None
            
            if not redirect_url.startswith('http'):
                redirect_url = urljoin(step1_url, redirect_url)
            
            carol_response = session.get(redirect_url, allow_redirects=False, timeout=15)
            
            if carol_response.status_code in [301, 302, 303, 307, 308]:
                final_redirect = carol_response.headers.get('Location')
                if final_redirect:
                    carol_response = session.get(final_redirect, allow_redirects=False, timeout=15)
            
            if len(carol_response.text) > 100:
                soup = BeautifulSoup(carol_response.text, 'html.parser')
                player_div = soup.find('div', id='player')
                
                if player_div:
                    iframe = player_div.find('iframe', src=True)
                    
                    if iframe:
                        iframe_src = iframe['src']
                        parsed = urlparse(iframe_src)
                        query_params = parse_qs(parsed.query)
                        
                        if 'url' in query_params:
                            return query_params['url'][0]
                        else:
                            url_match = re.search(r'[&?]url=([^&"\s]+)', iframe_src)
                            if url_match:
                                return unquote(url_match.group(1))
                
                iframes = soup.find_all('iframe', src=True)
                
                for iframe in iframes:
                    iframe_src = iframe.get('src', '')
                    
                    if '.mp4' in iframe_src or 'url=' in iframe_src:
                        parsed = urlparse(iframe_src)
                        query_params = parse_qs(parsed.query)
                        
                        if 'url' in query_params:
                            return query_params['url'][0]
                        
                        url_match = re.search(r'[&?]url=([^&"\s]+)', iframe_src)
                        if url_match:
                            return unquote(url_match.group(1))
                
        except:
            pass

        return None

    @classmethod
    def _get_highest_quality_link(cls, episode_page_text, available):
        quality, token = cls._extract_highest_quality_token(episode_page_text)
        
        if not token:
            return "HINATASOUL - SD", None

        mp4_url = cls._get_direct_mp4_from_token_302(token)
        if mp4_url:
            label = f"HINATASOUL -"
            return label, mp4_url
        
        return "HINATASOUL -", None

    @classmethod
    def search_animes(cls, mal_id, season=None, episode=None):
        is_movie = episode is None

        if not is_movie:
            try:
                episode = int(episode)
            except:
                return []

        r = session.get(f"https://api.jikan.moe/v4/anime/{mal_id}/full", timeout=10)
        if not r.ok:
            return []

        data = r.json().get('data', {})
        title_english = data.get('title_english')
        title_default = data.get('title')
        title_synonyms = data.get('title_synonyms') or []
        base_year = data.get('year')

        base_titles = [t for t in [title_english, title_default] + title_synonyms if t]
        search_title = title_english or title_default
        search_url = f"https://www.hinatasoulbr.vip/busca?busca={quote_plus(search_title)}"

        r = session.get(search_url, timeout=15)
        if not r.ok:
            return []

        soup = BeautifulSoup(r.text, "html.parser")
        items = soup.find_all('div', class_=re.compile(r'ultimosAnimesHomeItem'))
        
        candidates = []
        for item in items:
            name_div = item.find('div', class_='ultimosAnimesHomeItemInfosNome')
            if not name_div:
                continue
                
            raw_title = name_div.get_text(strip=True)
            
            a = item.find('a', href=True)
            if not a or not re.search(r"/(animes|anime-dublado)/[^/]+$", a['href']):
                continue
                
            page_url = urljoin("https://www.hinatasoulbr.vip/", a["href"])
            
            cand_year = cls._extract_year(raw_title)
            score = cls._similarity_score(base_titles, raw_title, base_year, cand_year)
            
            candidates.append({
                "title": raw_title,
                "url": page_url,
                "score": score,
                "year": cand_year,
                "season": cls._extract_season_number(raw_title),
                "clean_title": cls._clean_title(raw_title)
            })

        candidates.sort(key=lambda x: x["score"], reverse=True)

        results = []
        seen = set()

        expected_season = None
        if not is_movie and base_titles:
            for t in base_titles:
                m = re.search(r'(?:season|part|temporada|s)\s*(\d+)', t.lower())
                if m:
                    expected_season = int(m.group(1))
                    break

        base_keywords = set()
        for t in base_titles:
            clean = cls._clean_title(t)
            words = clean.split()
            if len(words) > 1:
                base_keywords.update(words[:3])

        for c in candidates:
            accept = False

            if base_year and c["year"] and base_year == c["year"]:
                accept = True
            elif not is_movie and expected_season and c["season"] and c["season"] == expected_season:
                accept = True
            elif not is_movie and expected_season and c["season"] == expected_season:
                clean_cand = c["clean_title"]
                if any(kw in clean_cand for kw in base_keywords) and str(expected_season) in clean_cand:
                    accept = True
            if not accept:
                min_score = 0.75 if 'dublado' in c["title"].lower() else 0.55
                if c["score"] >= min_score:
                    accept = True

            if not accept:
                continue

            if c["url"] in seen:
                continue
            seen.add(c["url"])

            r_page = session.get(c["url"], timeout=15)
            if not r_page.ok:
                continue

            ep_url = (
                cls._get_movie_episode_url(r_page.text)
                if is_movie
                else cls._get_episode_page_url(c["url"], episode)
            )
            if not ep_url:
                continue

            r_ep = session.get(ep_url, timeout=15)
            if not r_ep.ok:
                continue

            available = cls._get_available_qualities(r_ep.text)
            label, url = cls._get_highest_quality_link(r_ep.text, available)
            if not url:
                continue

            prefix = "DUBLADO" if "dublado" in c["title"].lower() else "LEGENDADO"
            final_label = f"{label} ({prefix})"
            results.append((final_label, url))

        return results

    @classmethod
    def resolve_movies(cls, url):
        resolved, sub = Resolver().resolverurls(url)
        return [(resolved or url, sub or '', USER_AGENT)]

    resolve_tvshows = resolve_movies
    __site_url__ = ['https://www.hinatasoulbr.vip/']
