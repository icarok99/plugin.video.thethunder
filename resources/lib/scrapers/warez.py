# -*- coding: utf-8 -*-

WEBSITE = 'CDN'

import re
import os
import sys
import json
import requests
import resources.lib.jsunpack as jsunpack
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
    from resources.lib import resolveurl
except ImportError:
    local_path = os.path.dirname(os.path.realpath(__file__))
    lib_path = local_path.replace('scrapers', '')
    sys.path.append(lib_path)
    from resolvers import resolveurl


class source:

    # ===============================
    # Funções auxiliares internas
    # ===============================

    @classmethod
    def _get_audio_ids_series(cls, session, imdb, season, episode, timeout=10):
        referer_url = f"https://embed.warezcdn.link/serie/{imdb}"
        data = session.get(referer_url, timeout=timeout).text

        match = re.search(r"var cachedSeasons\s*=\s*['\"]([^'\"]+)['\"]", data)
        if not match:
            return [], referer_url

        season_url = f"https://embed.warezcdn.link/{match.group(1)}"
        seasons_info = session.get(season_url, headers={'Referer': referer_url}, timeout=timeout).json().get("seasons", {})

        episode_info = next(
            (ep for s in seasons_info.values() if s["name"] == str(season)
             for ep in s["episodes"].values() if ep["name"] == str(episode)),
            None
        )
        if not episode_info:
            return [], referer_url

        audio_ids = session.get(
            f"https://embed.warezcdn.link/core/ajax.php?audios={episode_info['id']}",
            headers={'Referer': referer_url},
            timeout=timeout
        ).json()
        return json.loads(audio_ids), referer_url

    @classmethod
    def _get_audio_ids_movie(cls, session, imdb, timeout=10):
        referer_url = f"https://embed.warezcdn.link/filme/{imdb}"
        data = session.get(referer_url, timeout=timeout).text

        match = re.search(r"let data = ['\"](\[.+\])['\"]", data)
        if not match:
            return [], referer_url

        return json.loads(match.group(1)), referer_url

    @classmethod
    def _extract_links(cls, session, audio_ids, referer_url, timeout=10):
        links = []
        LANG_MAP = {1: english, 2: portuguese}
        SERVERS = ['warezcdn', 'mixdrop']

        for audio in audio_ids:
            lg = LANG_MAP.get(int(audio['audio']), 'UNKNOWN')
            for server in SERVERS:
                if server not in audio['servers']:
                    continue

                embed_referer_url = f"https://embed.warezcdn.link/getEmbed.php?id={audio['id']}&sv={server}&lang={audio['audio']}"
                play_url = f"https://embed.warezcdn.link/getPlay.php?id={audio['id']}&sv={server}"

                # simular navegação
                session.get(referer_url, timeout=timeout)
                session.get(embed_referer_url, headers={'Referer': referer_url}, timeout=timeout)
                play_response = session.get(play_url, headers={'Referer': embed_referer_url}, timeout=timeout).text

                match = re.search(r"window.location.href\s*=\s*['\"](.+?)['\"]", play_response)
                if match:
                    video_url = match.group(1)
                    links.append((f"{server.upper()} - {lg}", video_url))
        return links

    # ===============================
    # Funções principais
    # ===============================

    @classmethod
    def warezcdn_servers(cls, imdb, season=False, episode=False):
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0"})
        timeout = 10

        try:
            if season and episode:
                audio_ids, referer_url = cls._get_audio_ids_series(session, imdb, season, episode, timeout)
            else:
                audio_ids, referer_url = cls._get_audio_ids_movie(session, imdb, timeout)

            return cls._extract_links(session, audio_ids, referer_url, timeout)

        except Exception as e:
            print(f"[warezcdn_servers] Erro: {e}")
            return []

    @classmethod
    def search_movies(cls, imdb, year):
        try:
            return cls.warezcdn_servers(imdb, False, False)
        except:
            return []

    @classmethod
    def resolve_movies(cls, url):
        streams = []
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0"
        if url:
            # extract subtitles url
            try:
                sub = url.split('http')[2]
                sub = 'http%s' % sub
                try:
                    sub = sub.split('&')[0]
                except:
                    pass
                if not '.srt' in sub:
                    sub = ''
            except:
                sub = ''

            # extract video src
            try:
                stream = url.split('?')[0]
            except:
                try:
                    stream = url.split('#')[0]
                except:
                    pass

            # extract mp4 link from mixdrop
            if 'mixdrop' in url:
                try:
                    video_html_response = requests.get(
                        url,
                        headers={"User-Agent": user_agent}
                    )
                    video_html_response = video_html_response.text
                    js_matches = re.compile(r"eval\((.+)\)").findall(video_html_response)
                    for packed_js in js_matches:
                        if 'delivery' in packed_js:
                            mdcore = jsunpack.unpack(packed_js)

                    stream = 'https:' + re.compile(r"MDCore.wurl=\"(.+?)\"").findall(mdcore)[0] + f'|user-agent={user_agent}'
                except:
                    pass

            # extract m3u8 links from warezcdn
            else:
                try:
                    stream_data = re.compile(r"(https://.+/)video/(.+)").findall(stream)[0]
                    host_url, video_id = stream_data
                    master_request_url = f'{host_url}player/index.php?data={video_id}&do=getVideo'

                    master_m3u8_url = requests.post(
                        master_request_url,
                        data={'hash': video_id, 'r': ''},
                        headers={'X-Requested-With': 'XMLHttpRequest', 'Referer': 'https://embed.warezcdn.link/'},
                        allow_redirects=True
                    )
                    master_m3u8_url = json.loads(master_m3u8_url.text)['videoSource']

                    master_m3u8 = requests.get(master_m3u8_url, headers={'Referer': 'https://embed.warezcdn.link/'}).text
                    for line in master_m3u8.split('\n'):
                        matches = re.compile(r"https?://[a-zA-Z0-9.-]+(?:\.[a-zA-Z]{2,})(:\d+)?(/[^\s]*)?").match(line)
                        if matches:
                            stream = matches[0]
                            break
                except:
                    pass

            streams.append((stream, sub, user_agent))
        return streams

    @classmethod
    def search_tvshows(cls, imdb, year, season, episode):
        try:
            return cls.warezcdn_servers(imdb, season, episode)
        except:
            return []

    @classmethod
    def resolve_tvshows(cls, url):
        streams = []
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0"
        if url:
            try:
                sub = url.split('http')[2]
                sub = 'http%s' % sub
                try:
                    sub = sub.split('&')[0]
                except:
                    pass
                if not '.srt' in sub:
                    sub = ''
            except:
                sub = ''

            try:
                stream = url.split('?')[0]
            except:
                try:
                    stream = url.split('#')[0]
                except:
                    pass

            if 'mixdrop' in url:
                try:
                    video_html_response = requests.get(
                        url,
                        headers={"User-Agent": user_agent}
                    )
                    video_html_response = video_html_response.text
                    js_matches = re.compile(r"eval\((.+)\)").findall(video_html_response)
                    for packed_js in js_matches:
                        if 'delivery' in packed_js:
                            mdcore = jsunpack.unpack(packed_js)

                    stream = 'https:' + re.compile(r"MDCore.wurl=\"(.+?)\"").findall(mdcore)[0] + f'|user-agent={user_agent}'
                except:
                    pass
            else:
                try:
                    stream_data = re.compile(r"(https://.+/)video/(.+)").findall(stream)[0]
                    host_url, video_id = stream_data
                    master_request_url = f'{host_url}player/index.php?data={video_id}&do=getVideo'

                    master_m3u8_url = requests.post(
                        master_request_url,
                        data={'hash': video_id, 'r': ''},
                        headers={'X-Requested-With': 'XMLHttpRequest', 'Referer': 'https://embed.warezcdn.link/'},
                        allow_redirects=True
                    )
                    master_m3u8_url = json.loads(master_m3u8_url.text)['videoSource']

                    master_m3u8 = requests.get(master_m3u8_url, headers={'Referer': 'https://embed.warezcdn.link/'}).text
                    for line in master_m3u8.split('\n'):
                        matches = re.compile(r"https?://[a-zA-Z0-9.-]+(?:\.[a-zA-Z]{2,})(:\d+)?(/[^\s]*)?").match(line)
                        if matches:
                            stream = matches[0]
                            break
                except:
                    pass

            streams.append((stream, sub, user_agent))
        return streams