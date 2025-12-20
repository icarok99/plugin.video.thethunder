# -*- coding: utf-8 -*-
WEBSITE = 'NETCINE'

import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin
import re
import difflib
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from resources.lib.resolver import Resolver

session = requests.Session()
session.verify = False
session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Referer": "https://netcinept.lat/"
})

def _get_host():
    try:
        r = session.get("https://raw.githack.com/zoreu/dns_ntc/main/dns.txt", timeout=8)
        h = r.text.strip()
        if h.startswith("http"):
            return h.rstrip("/") + "/"
    except:
        pass
    return "https://netcinept.lat/"

HOST = _get_host()

def clean_title(title):
    return re.sub(r'[:\-–]', ' ', title).strip()

class source:
    __site_url__ = [HOST]

    @classmethod
    def find_title(cls, imdb):
        url = "https://m.imdb.com/pt/title/" + imdb + "/"
        try:
            r = session.get(url, timeout=20)
            if r.status_code != 200:
                return '', '', ''
            soup = BeautifulSoup(r.text, 'html.parser')
            title_pt = ''
            hero = soup.find('h1', {'data-testid': 'hero__pageTitle'})
            if hero:
                span = hero.find('span')
                title_pt = span.get_text(strip=True) if span else hero.get_text(strip=True)
            original_title = ''
            orig = soup.find('div', string=lambda t: t and 'Título original' in t)
            if orig:
                next_div = orig.find_next('div')
                if next_div:
                    original_title = next_div.get_text(strip=True)
            year = ''
            y = soup.find('a', href=re.compile(r'/releaseinfo'))
            if y:
                m = re.search(r'\d{4}', y.get_text())
                if m:
                    year = m.group(0)
            return title_pt, original_title, year
        except:
            return '', '', ''

    @classmethod
    def search_movies(cls, imdb, year):
        title_pt, original_title, imdb_year = cls.find_title(imdb)
        if not title_pt or not imdb_year:
            return []
        search_title = clean_title(title_pt)
        try:
            r = session.get(HOST + "?s=" + quote_plus(search_title), timeout=20)
            if r.status_code != 200:
                return []
            soup = BeautifulSoup(r.text, 'html.parser')
            items = soup.select("#box_movies .movie")
            for item in items:
                a = item.select_one(".imagen a")
                if not a or "/tvshows/" in a["href"]:
                    continue
                href = urljoin(HOST, a["href"])
                page_title = item.select_one("h2").get_text(strip=True)
                year_span = item.select_one("span.year")
                page_year = year_span.get_text(strip=True) if year_span else ""
                if page_year != imdb_year:
                    continue
                clean_page = re.sub(r'(?i)\s*(dublado|legendado|hd|4k|1080p|720p|cam|ts).*', '', page_title).strip()
                sim_pt = difflib.SequenceMatcher(None, title_pt.lower(), clean_page.lower()).ratio()
                sim_orig = difflib.SequenceMatcher(None, original_title.lower(), clean_page.lower()).ratio() if original_title else 0
                if max(sim_pt, sim_orig) >= 0.5:
                    return cls._get_players(href)
            return []
        except:
            return []

    @classmethod
    def _get_players(cls, page_url):
        links = []
        try:
            r = session.get(page_url, timeout=20)
            soup = BeautifulSoup(r.text, 'html.parser')
            for tab in soup.select("#player-container .player-menu li a"):
                text = tab.get_text(strip=True).upper()
                tab_id = tab["href"].lstrip("#")
                iframe = soup.select_one("#" + tab_id + " iframe")
                if iframe and iframe.get("src"):
                    src = iframe["src"]
                    if src.startswith("//"):
                        src = "https:" + src
                    elif not src.startswith("http"):
                        src = urljoin(HOST, src)
                    lang = "DUBLADO" if any(x in text for x in ["DUBLAD","DUB","ÁUDIO"]) else "LEGENDADO"
                    links.append((WEBSITE + " • " + lang, src))
        except:
            pass
        return links

    @classmethod
    def resolve_movies(cls, url):
        streams = []
        if not url:
            return streams
        try:
            resolver = Resolver()
            resolved, sub = resolver.resolverurls(url)
            if resolved:
                streams.append((resolved, sub or '', USER_AGENT))
        except:
            pass
        return streams

    @classmethod
    def resolve_tvshows(cls, url):
        return cls.resolve_movies(url)