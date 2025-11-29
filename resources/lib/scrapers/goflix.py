# -*- coding: utf-8 -*-
WEBSITE = 'GOFLIX'

try:
    from resources.lib.ClientScraper import cfscraper, USER_AGENT
except ImportError:
    from ClientScraper import cfscraper, USER_AGENT

import re
import os
import sys
import difflib
import base64
from urllib.parse import quote_plus, urljoin
from bs4 import BeautifulSoup

try:
    from resources.lib.autotranslate import AutoTranslate
    portuguese = AutoTranslate.language('Portuguese')
    english = AutoTranslate.language('English')
except ImportError:
    portuguese = 'DUBLADO'
    english = 'LEGENDADO'

try:
    from resources.lib import resolveurl
except ImportError:
    local_path = os.path.dirname(os.path.realpath(__file__))
    lib_path = local_path.replace('scrapers', '')
    sys.path.append(lib_path)
    from resolvers import resolveurl


class source:

    @classmethod
    def get_title(cls, imdb):
        try:
            if not imdb.startswith("tt"):
                imdb = "tt" + imdb.lstrip("t0")
            url = f"https://m.imdb.com/title/{imdb}/"
            r = cfscraper.get(url, headers={"User-Agent": USER_AGENT})
            if r.status_code != 200:
                return None, None
            soup = BeautifulSoup(r.text, "html.parser")
            title = soup.find("h1", {"data-testid": "hero__pageTitle"})
            pt = title.get_text(strip=True) if title else None
            orig = pt
            txt = soup.get_text()
            m = re.search(r"Título original[:\s]+([^\n]+)", txt, re.I)
            if m:
                orig = m.group(1).strip()
            return pt or orig, orig
        except:
            return None, None

    @classmethod
    def _resolve_fembed(cls, share_id, lang, cvalue=""):
        try:
            page = f"https://fembed.sx/e/{share_id}/"
            if cvalue:
                page = f"https://fembed.sx/e/{share_id}/{cvalue}"

            r0 = cfscraper.get(page, headers={"User-Agent": USER_AGENT})
            if not r0.ok:
                return None

            html = r0.text
            cookies = r0.cookies

            api_match = re.search(r'api\s*=\s*"([^"]+)"', html)
            api_path = api_match.group(1).replace("\\/", "/") if api_match else f"/api.php?s={share_id}&c={cvalue}"
            api_url = urljoin("https://fembed.sx", api_path)

            pdata = {"action": "getPlayer", "lang": lang, "key": base64.b64encode(b"0").decode()}

            r1 = cfscraper.post(api_url, data=pdata, headers={"Referer": page}, cookies=cookies)
            if not r1.ok:
                return None

            m = re.search(r'src=["\']([^"\']*action=getAds[^"\']*)["\']', r1.text)
            if not m:
                return None
            getads = m.group(1)
            if getads.startswith("//"):
                getads = "https:" + getads
            elif getads.startswith("/"):
                getads = "https://fembed.sx" + getads

            r2 = cfscraper.get(getads,
                               headers={"Referer": page, "X-Requested-With": "XMLHttpRequest"},
                               cookies=cookies)
            if not r2.ok:
                return None

            link = re.search(r'src=["\']([^"\']*filemoon\.[^"\']*)["\']', r2.text, re.I)
            if not link:
                return None

            dirty_url = link.group(1)
            if dirty_url.startswith("//"):
                dirty_url = "https:" + dirty_url

            clean_url = re.sub(r'(/e/[0-9A-Za-z]+).*', r'\1', dirty_url)
            clean_url = clean_url.replace("http://", "https://")
            return clean_url

        except:
            return None

    @classmethod
    def search_movies(cls, imdb, year=None):
        pt, _ = cls.get_title(imdb)
        if not pt:
            return []

        r = cfscraper.get(f"https://goflixy.lol/buscar?q={quote_plus(pt)}", headers={"User-Agent": USER_AGENT})
        if not r.ok:
            return []

        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", class_="card"):
            if "/filme/" not in a.get("href", ""):
                continue
            title = a.find("div", "card-title")
            if not title:
                continue
            clean = re.sub(r"\(\d{4}\)", "", title.get_text(strip=True)).strip()
            if difflib.SequenceMatcher(None, pt.lower(), clean.lower()).ratio() < 0.60:
                continue

            page = urljoin("https://goflixy.lol", a.get("href"))
            r2 = cfscraper.get(page, headers={"User-Agent": USER_AGENT})
            if not r2.ok:
                continue

            iframe = BeautifulSoup(r2.text, "html.parser").find("iframe", id="player")
            if not iframe:
                continue

            src = iframe.get("src", "")
            if src.startswith("//"):
                src = "https:" + src

            m = re.search(r"/e/([0-9A-Za-z]+)", src)
            if not m:
                continue

            ID = m.group(1)
            out = []
            dub = cls._resolve_fembed(ID, "DUB")
            leg = cls._resolve_fembed(ID, "LEG")

            if dub:
                out.append(("FILEMOON - DUBLADO", dub))
            if leg:
                out.append(("FILEMOON - LEGENDADO", leg))

            return out
        return []

    @classmethod
    def search_tvshows(cls, imdb, year, season, episode):
        try:
            season = int(season)
            episode = int(episode)
        except:
            return []

        pt, _ = cls.get_title(imdb)
        if not pt:
            return []

        r = cfscraper.get(f"https://goflixy.lol/buscar?q={quote_plus(pt)}", headers={"User-Agent": USER_AGENT})
        if not r.ok:
            return []

        soup = BeautifulSoup(r.text, "html.parser")
        serie_url = None
        for a in soup.find_all("a", class_="card"):
            href = a.get("href", "")
            if "/serie/" not in href:
                continue
            title = a.find("div", "card-title")
            if title and difflib.SequenceMatcher(None, pt.lower(),
                     re.sub(r"\(\d{4}\)", "", title.get_text(strip=True)).strip().lower()).ratio() >= 0.60:
                serie_url = urljoin("https://goflixy.lol", href)
                break
        if not serie_url:
            return []

        r2 = cfscraper.get(serie_url, headers={"User-Agent": USER_AGENT})
        if not r2.ok:
            return []

        m = re.search(r"const EP = (\{[\s\S]*?\});", r2.text)
        if not m:
            return []

        ep = eval(m.group(1).replace("true", "True").replace("false", "False"))
        skey = str(season)
        if skey not in ep:
            return []

        for e in ep[skey]:
            if str(e.get("n")) == str(episode):
                url = e.get("url", "")
                if url.startswith("//"):
                    url = "https:" + url

                m2 = re.search(r"/e/([0-9A-Za-z]+)/(.+)", url)
                if not m2:
                    continue

                ID = m2.group(1)
                cvalue = m2.group(2)

                out = []
                dub = cls._resolve_fembed(ID, "DUB", cvalue)
                leg = cls._resolve_fembed(ID, "LEG", cvalue)

                if dub:
                    out.append(("FILEMOON - DUBLADO", dub))
                if leg:
                    out.append(("FILEMOON - LEGENDADO", leg))

                return out
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
        try:
            resolved, sub_from_resolver = resolveurl(stream, referer=None)
            if resolved:
                streams.append((resolved, sub if sub else sub_from_resolver, USER_AGENT))
        except:
            pass
        return streams

    @classmethod
    def resolve_tvshows(cls, url):
        return cls.resolve_movies(url)

    __site_url__ = ['https://goflixy.lol/']