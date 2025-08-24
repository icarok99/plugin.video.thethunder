# -*- coding: utf-8 -*-

WEBSITE = 'CDN'

import re
import os
import sys
import json
import urllib.parse
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
    @classmethod
    def warezcdn_servers(cls, imdb, season=False, episode=False):
        links = []
        if season and episode:
            referer_url = 'https://embed.warezcdn.link/serie/%s' % (str(imdb))
            data = requests.get(referer_url).text
            season_url = re.compile(r"var cachedSeasons\s*=\s*(?P<url>'(?:[^\']+)'|\"([^\"]+)\")", re.MULTILINE | re.DOTALL | re.IGNORECASE).findall(data)[0][1]
            season_url = 'https://embed.warezcdn.link/' + season_url
            seasons_info = requests.get(season_url, headers={'Referer': referer_url}).json()['seasons']
            episode_info = {}
            for key in seasons_info.keys():
                season_dict = seasons_info[key]
                if season_dict['name'] == str(season):
                    for key in season_dict['episodes'].keys():
                        episode_dict = season_dict['episodes'][key]
                        if episode_dict['name'] == str(episode):
                            episode_info = episode_dict
                            break
            
            request_url = 'https://embed.warezcdn.link/core/ajax.php?audios=%s' % episode_dict['id']
            audio_ids = requests.get(request_url, headers={'Referer': referer_url}).json()
            audio_ids = json.loads(audio_ids)
                        
            if audio_ids:
                for audio in audio_ids:
                    if int(audio['audio']) == 1:
                        lg = english
                    elif int(audio['audio']) == 2:
                        lg = portuguese
                    servers = ['warezcdn', 'mixdrop']
                    for server in servers:
                        if server in audio['servers']:
                            embed_referer_url = 'https://embed.warezcdn.link/getEmbed.php?id=%s&sv=%s&lang=%s' % (audio['id'], server, audio['audio'])
                            play_url = 'https://embed.warezcdn.link/getPlay.php?id=%s&sv=%s' % (audio['id'], server)
                            requests.get(referer_url)
                            requests.get(embed_referer_url, headers={'Referer': referer_url})
                            play_response = requests.get(play_url, headers={'Referer': embed_referer_url}).text
                            video_url = re.compile(r"window.location.href = (?:\'|\")(.+)(?:\'|\")").findall(play_response)[0]
                            name = server.upper() + ' - ' + lg
                            links.append((name, video_url))

        else:
            referer_url = 'https://embed.warezcdn.link/filme/%s' % imdb
            data = requests.get(referer_url).text
            audio_ids = re.compile(r"let data = (?:\'|\")(\[.+\])(?:\'|\")").findall(data)
            audio_ids = json.loads(audio_ids[0])
            
            if audio_ids:
                for audio in audio_ids:
                    if int(audio['audio']) == 1:
                        lg = english
                    elif int(audio['audio']) == 2:
                        lg = portuguese
                    servers = ['warezcdn', 'mixdrop']
                    for server in servers:
                        if server in audio['servers']:
                            embed_referer_url = 'https://embed.warezcdn.link/getEmbed.php?id=%s&sv=%s&lang=%s' % (audio['id'], server, audio['audio'])
                            play_url = 'https://embed.warezcdn.link/getPlay.php?id=%s&sv=%s' % (audio['id'], server)
                            requests.get(referer_url)
                            requests.get(embed_referer_url, headers={'Referer': referer_url})
                            play_response = requests.get(play_url, headers={'Referer': embed_referer_url}).text
                            video_url = re.compile(r"window.location.href = (?:\'|\")(.+)(?:\'|\")").findall(play_response)[0]
                            name = server.upper() + ' - ' + lg
                            links.append((name, video_url))

        return links
    
    @classmethod
    def extract_hls_streams(cls, master_url, headers=None):
        streams = []
        if not headers:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
                'Referer': 'https://embed.warezcdn.link/',
                'Origin': 'https://basseqwevewcewcewecwcw.xyz'
            }
        
        try:
            response = requests.get(master_url, headers=headers, timeout=10)
            response.raise_for_status()
            master_content = response.text
            lines = master_content.split('\n')
            base_url = master_url.rsplit('/', 1)[0] + '/'
            
            for i, line in enumerate(lines):
                line = line.strip()
                if line and not line.startswith('#'):
                    stream_url = line if line.startswith('http') else base_url + line
                    stream_url = urllib.parse.quote(stream_url, safe=':/?&=%')
                    quality = 'Auto'
                    if i > 0 and lines[i-1].startswith('#EXT-X-STREAM-INF:'):
                        resolution_match = re.search(r'RESOLUTION=(\d+)x(\d+)', lines[i-1])
                        if resolution_match:
                            quality = f"{resolution_match.group(1)}p"
                    streams.append((quality, stream_url))
                    
        except:
            streams.append(('Auto', urllib.parse.quote(master_url, safe=':/?&=%')))
        
        return streams
    
    @classmethod
    def search_movies(cls, imdb, year):
        try:
            return cls.warezcdn_servers(imdb, False, False)
        except:
            return []      
    
    @classmethod
    def resolve_movies(cls, url):
        streams = []
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0"
        origin_url = 'https://basseqwevewcewcewecwcw.xyz/'
        
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
            
            if 'master.txt' in stream or '.m3u8' in stream:
                hls_streams = cls.extract_hls_streams(stream)
                for quality, hls_url in hls_streams:
                    final_url = f"{hls_url}|User-Agent={user_agent}&Referer=https://embed.warezcdn.link/&Origin={origin_url.rstrip('/')}"
                    streams.append((final_url, sub, user_agent))
                return streams
            
            if 'mixdrop' in url:
                try:
                    video_html_response = requests.get(url, headers={"User-Agent": user_agent}).text
                    js_matches = re.compile(r"eval\((.+)\)").findall(video_html_response)
                    for packed_js in js_matches:
                        if 'delivery' in packed_js:
                            mdcore = jsunpack.unpack(packed_js)
                    stream = 'https:' + re.compile(r"MDCore.wurl=\"(.+?)\"").findall(mdcore)[0] + '|user-agent=%s' % user_agent
                    streams.append((stream, sub, user_agent))
                except:
                    pass

            else:
                try:
                    if 'player/index.php' in stream:
                        video_id_match = re.search(r'data=([a-f0-9]+)', stream)
                        if video_id_match:
                            video_id = video_id_match.group(1)
                            host_url = re.match(r'https?://([^/]+)', stream).group(0) + '/'
                            master_request_url = stream
                            master_response = requests.post(
                                master_request_url,
                                data={'hash': video_id, 'r': ''},
                                headers={
                                    'X-Requested-With': 'XMLHttpRequest',
                                    'Referer': 'https://embed.warezcdn.link/',
                                    'User-Agent': user_agent,
                                    'Origin': origin_url.rstrip('/')
                                },
                                allow_redirects=True
                            )
                            if master_response.status_code == 200:
                                master_data = master_response.json()
                                if 'securedLink' in master_data and master_data['securedLink']:
                                    final_url = f"{master_data['securedLink']}|User-Agent={user_agent}&Referer=https://embed.warezcdn.link/&Origin={origin_url.rstrip('/')}"
                                    streams.append((final_url, sub, user_agent))
                                    return streams
                                elif 'videoSource' in master_data:
                                    master_m3u8_url = master_data['videoSource']
                                    hls_streams = cls.extract_hls_streams(master_m3u8_url)
                                    for quality, hls_url in hls_streams:
                                        final_url = f"{hls_url}|User-Agent={user_agent}&Referer=https://embed.warezcdn.link/&Origin={origin_url.rstrip('/')}"
                                        streams.append((final_url, sub, user_agent))
                                    return streams
                    
                    else:
                        stream_data = re.compile(r"(https://.+/)video/(.+)").findall(stream)
                        if stream_data:
                            host_url, video_id = stream_data[0]
                            master_request_url = f'{host_url}player/index.php?data={video_id}&do=getVideo'
                            master_response = requests.post(
                                master_request_url,
                                data={'hash': video_id, 'r': ''},
                                headers={
                                    'X-Requested-With': 'XMLHttpRequest', 
                                    'Referer': 'https://embed.warezcdn.link/',
                                    'User-Agent': user_agent,
                                    'Origin': origin_url.rstrip('/')
                                },
                                allow_redirects=True
                            )
                            if master_response.status_code == 200:
                                master_data = master_response.json()
                                if 'securedLink' in master_data and master_data['securedLink']:
                                    final_url = f"{master_data['securedLink']}|User-Agent={user_agent}&Referer=https://embed.warezcdn.link/&Origin={origin_url.rstrip('/')}"
                                    streams.append((final_url, sub, user_agent))
                                    return streams
                                elif 'videoSource' in master_data:
                                    master_m3u8_url = master_data['videoSource']
                                    hls_streams = cls.extract_hls_streams(master_m3u8_url)
                                    for quality, hls_url in hls_streams:
                                        final_url = f"{hls_url}|User-Agent={user_agent}&Referer=https://embed.warezcdn.link/&Origin={origin_url.rstrip('/')}"
                                        streams.append((final_url, sub, user_agent))
                                    return streams
                            
                except:
                    final_url = f"{urllib.parse.quote(stream, safe=':/?&=%')}|User-Agent={user_agent}&Referer=https://embed.warezcdn.link/&Origin={origin_url.rstrip('/')}"
                    streams.append((final_url, sub, user_agent))

            if not streams:
                final_url = f"{urllib.parse.quote(stream, safe=':/?&=%')}|User-Agent={user_agent}&Referer=https://embed.warezcdn.link/&Origin={origin_url.rstrip('/')}"
                streams.append((final_url, sub, user_agent))

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
        origin_url = 'https://basseqwevewcewcewecwcw.xyz/'
        
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
                    video_html_response = requests.get(url, headers={"User-Agent": user_agent}).text
                    js_matches = re.compile(r"eval\((.+)\)").findall(video_html_response)
                    for packed_js in js_matches:
                        if 'delivery' in packed_js:
                            mdcore = jsunpack.unpack(packed_js)
                    stream = 'https:' + re.compile(r"MDCore.wurl=\"(.+?)\"").findall(mdcore)[0] + '|user-agent=%s' % user_agent
                    streams.append((stream, sub, user_agent))
                except:
                    pass

            else:
                try:
                    if 'player/index.php' in stream:
                        video_id_match = re.search(r'data=([a-f0-9]+)', stream)
                        if video_id_match:
                            video_id = video_id_match.group(1)
                            host_url = re.match(r'https?://([^/]+)', stream).group(0) + '/'
                            master_request_url = stream
                            master_response = requests.post(
                                master_request_url,
                                data={'hash': video_id, 'r': ''},
                                headers={
                                    'X-Requested-With': 'XMLHttpRequest',
                                    'Referer': 'https://embed.warezcdn.link/',
                                    'User-Agent': user_agent,
                                    'Origin': origin_url.rstrip('/')
                                },
                                allow_redirects=True
                            )
                            if master_response.status_code == 200:
                                master_data = master_response.json()
                                if 'securedLink' in master_data and master_data['securedLink']:
                                    final_url = f"{master_data['securedLink']}|User-Agent={user_agent}&Referer=https://embed.warezcdn.link/&Origin={origin_url.rstrip('/')}"
                                    streams.append((final_url, sub, user_agent))
                                    return streams
                                elif 'videoSource' in master_data:
                                    master_m3u8_url = master_data['videoSource']
                                    hls_streams = cls.extract_hls_streams(master_m3u8_url)
                                    for quality, hls_url in hls_streams:
                                        final_url = f"{hls_url}|User-Agent={user_agent}&Referer=https://embed.warezcdn.link/&Origin={origin_url.rstrip('/')}"
                                        streams.append((final_url, sub, user_agent))
                                    return streams
                    
                    else:
                        stream_data = re.compile(r"(https://.+/)video/(.+)").findall(stream)
                        if stream_data:
                            host_url, video_id = stream_data[0]
                            master_request_url = f'{host_url}player/index.php?data={video_id}&do=getVideo'
                            master_response = requests.post(
                                master_request_url,
                                data={'hash': video_id, 'r': ''},
                                headers={
                                    'X-Requested-With': 'XMLHttpRequest',
                                    'Referer': 'https://embed.warezcdn.link/',
                                    'User-Agent': user_agent,
                                    'Origin': origin_url.rstrip('/')
                                },
                                allow_redirects=True
                            )
                            if master_response.status_code == 200:
                                master_data = master_response.json()
                                if 'securedLink' in master_data and master_data['securedLink']:
                                    final_url = f"{master_data['securedLink']}|User-Agent={user_agent}&Referer=https://embed.warezcdn.link/&Origin={origin_url.rstrip('/')}"
                                    streams.append((final_url, sub, user_agent))
                                    return streams
                                elif 'videoSource' in master_data:
                                    master_m3u8_url = master_data['videoSource']
                                    hls_streams = cls.extract_hls_streams(master_m3u8_url)
                                    for quality, hls_url in hls_streams:
                                        final_url = f"{hls_url}|User-Agent={user_agent}&Referer=https://embed.warezcdn.link/&Origin={origin_url.rstrip('/')}"
                                        streams.append((final_url, sub, user_agent))
                                    return streams
                            
                except:
                    final_url = f"{urllib.parse.quote(stream, safe=':/?&=%')}|User-Agent={user_agent}&Referer=https://embed.warezcdn.link/&Origin={origin_url.rstrip('/')}"
                    streams.append((final_url, sub, user_agent))

            if not streams:
                final_url = f"{urllib.parse.quote(stream, safe=':/?&=%')}|User-Agent={user_agent}&Referer=https://embed.warezcdn.link/&Origin={origin_url.rstrip('/')}"
                streams.append((final_url, sub, user_agent))

        return streams