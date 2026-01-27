# -*- coding: utf-8 -*-
import os
import re
import sys
import xbmc
import xbmcgui
import xbmcvfs
import xbmcaddon
import xbmcplugin
from datetime import datetime
from kodi_helper import myAddon
from resources.lib import httpclient, sources
from urllib.parse import urlparse, unquote, parse_qs
from resources.lib.autotranslate import AutoTranslate

KODI_VERSION = xbmc.getInfoLabel("System.BuildVersion")
KODI_MAJOR = int(KODI_VERSION.split('.')[0])

def set_listitem_info(li, title, plot=None, tvshowtitle=None, mediatype='video'):
    if KODI_MAJOR >= 20:
        info_tag = li.getVideoInfoTag()
        info_tag.setTitle(title)
        info_tag.setPlot(plot or '')
        info_tag.setMediaType(mediatype)
        if tvshowtitle:
            info_tag.setTvShowTitle(tvshowtitle)
    else:
        info = {'title': title, 'plot': plot or ''}
        if tvshowtitle:
            info['tvshowtitle'] = tvshowtitle
        if mediatype == 'episode':
            info['mediatype'] = 'episode'
        elif mediatype == 'movie':
            info['mediatype'] = 'movie'
        li.setInfo('video', info)

class Donate(xbmcgui.WindowDialog):
    def __init__(self):
        super().__init__()
        addon_id = re.search(r'plugin://(.+?)/', str(sys.argv[0])).group(1)
        addon = myAddon(addon_id)
        translate = addon.translate
        home_dir = addon.homeDir
        pix_image = translate(os.path.join(home_dir, 'resources', 'images', 'qrcode-pix.png'))
        self.image = xbmcgui.ControlImage(440, 145, 400, 400, pix_image)
        self.text = xbmcgui.ControlLabel(
            x=455, y=570, width=1280, height=25,
            label=AutoTranslate.language('If you like this add-on, support via PIX above'),
            textColor='white'
        )
        self.text2 = xbmcgui.ControlLabel(
            x=535, y=600, width=1280, height=25,
            label=AutoTranslate.language('Press BACK to exit'),
            textColor='white'
        )
        self.addControl(self.image)
        self.addControl(self.text)
        self.addControl(self.text2)

class thunder(myAddon):
    def icon(self, image_name):
        return self.translate(os.path.join(self.homeDir, 'resources', 'images', f'{image_name}.png'))

    def notify_invalid_search(self):
        self.notify(AutoTranslate.language("Please enter a valid search term"))

    def notify_no_sources(self):
        self.notify(AutoTranslate.language("No sources available"))

    def notify_stream_unavailable(self):
        self.notify(AutoTranslate.language("Stream unavailable"))

    def get_preferred_language(self):
        try:
            addon = xbmcaddon.Addon()
            valor = addon.getSetting("preferred_language")
            if valor == "0":
                return AutoTranslate.language("Portuguese")
            else:
                return AutoTranslate.language("English")
        except Exception:
            return AutoTranslate.language("Portuguese")

    def stop_if_playing(self):
        try:
            player = xbmc.Player()
            if player.isPlaying():
                player.stop()
        except Exception:
            pass

    def play(self, url, title, iconimage, fanart, description, subtitles=None):
        try:
            self.stop_if_playing()
            li = xbmcgui.ListItem(label=title)
            li.setArt({'icon': iconimage, 'thumb': iconimage, 'fanart': fanart})
            set_listitem_info(li, title, description, mediatype='video')
            li.setContentLookup(False)
            if subtitles:
                li.setSubtitles([subtitles])
            li.setPath(url)
            xbmc.Player().play(url, li)
        except Exception:
            self.notify(AutoTranslate.language('Error trying to play'))

    def is_auto_play_enabled(self):
        try:
            return xbmcaddon.Addon().getSetting("auto_play_enabled") == "true"
        except Exception:
            return False

    def try_resolve_with_fallback(self, menus_links, season=None, episode=None):
        if not menus_links:
            return None, None
        preferred_lang = self.get_preferred_language().upper()
        TOP_HOSTS = ["DOODSTREAM", "STREAMTAPE", "MIXDROP", "FILEMOON"]

        def get_priority_score(label, url=""):
            label_u = (label or "").upper()
            score = 0
            if "DUBLADO" in preferred_lang or "PORTUGUÊS" in preferred_lang:
                if any(x in label_u for x in ["DUBLADO", "DUB", "PT-BR", "PORTUGUÊS", "PTBR"]):
                    score += 1000
            else:
                if any(x in label_u for x in ["LEGENDADO", "LEG", "SUB", "INGLÊS", "ENGLISH", "SUBTITLED"]):
                    score += 1000
            url_lower = url.lower() if url else ""
            for i, host in enumerate(TOP_HOSTS):
                if host in label_u or host.lower() in url_lower:
                    score += (len(TOP_HOSTS) - i) * 10
                    break
            return score

        sorted_links = sorted(menus_links, key=lambda x: get_priority_score(x[0], x[1]), reverse=True)
        tried = set()
        for name, url in sorted_links:
            try:
                decoded = unquote(url)
                parsed = urlparse(decoded)
                qs = parse_qs(parsed.query)
                final_url = qs.get('url', [decoded])[0] or qs.get('u', [decoded])[0] or decoded
                if final_url in tried:
                    continue
                tried.add(final_url)
                stream, sub = sources.select_resolver(final_url, season, episode)
                if stream:
                    return stream, sub
            except Exception:
                continue
        return None, None

    def auto_play_preferred_language(self, imdb, mal_id, year, season_num, episode_num, video_title, genre, iconimage, fanart, description, is_anime='false', movie_name='', serie_name='', anime_name='', original_name=''):
        try:
            if is_anime == 'true':
                menus_links = sources.show_content_anime(mal_id, year, season_num, episode_num)
            else:
                menus_links = sources.show_content(imdb, year, season_num, episode_num)
            if not menus_links:
                self.notify_no_sources()
                return False
            stream, sub = self.try_resolve_with_fallback(menus_links, season_num, episode_num)
            if not stream:
                self.notify_stream_unavailable()
                return False

            self.stop_if_playing()

            showtitle = episode_title = video_title
            if season_num and episode_num:
                if " - " in video_title:
                    showtitle, episode_title = video_title.split(" - ", 1)
                else:
                    episode_title = f"{AutoTranslate.language('Episode')} {episode_num}"
            li = xbmcgui.ListItem(label=episode_title if season_num and episode_num else video_title)
            li.setArt({'thumb': iconimage, 'icon': iconimage, 'fanart': fanart})
            if season_num and episode_num:
                set_listitem_info(li, episode_title, description, showtitle, 'episode')
            else:
                set_listitem_info(li, video_title, description, mediatype='movie')
            if sub:
                li.setSubtitles([sub])
            li.setPath(stream)
            xbmc.Player().play(stream, li)
            return True
        except Exception:
            self.notify(AutoTranslate.language('Error trying to auto-play'))
            return False

    def home(self):
        self.setcontent('videos')
        menus = [
            ('Movies', 'movies', 'movies'),
            ('Tv shows', 'tv_shows', 'tvshows'),
            ('Animes', 'animes', 'animes'),
            ('donation', 'donate', 'donate'),
            ('settings', 'settings', 'settings'),
        ]
        for label, action, icon in menus:
            self.addMenuItem({'name': '[B]' + AutoTranslate.language(label) + '[/B]', 'action': action, 'mediatype': 'video', 'iconimage': self.icon(icon)}, folder=(action != 'settings'))
        self.end()

    def movies(self):
        self.setcontent('videos')
        menus = [
            ('New movies', 'premiere_movies'),
            ('Trending movies', 'trending_movies'),
            ('Popular movies', 'popular_movies'),
            ('Search movies', 'search_movies'),
        ]
        for label, action in menus:
            self.addMenuItem({'name': '[B]' + AutoTranslate.language(label) + '[/B]', 'action': action, 'mediatype': 'movies', 'iconimage': self.icon(action.split('_')[0])})
        self.end()

    def tv_shows(self):
        self.setcontent('videos')
        menus = [
            ('New tv shows', 'premiere_tv_shows'),
            ('Trending tv shows', 'trending_tv_shows'),
            ('Popular tv shows', 'popular_tv_shows'),
            ('Search tv shows', 'search_tv_shows'),
        ]
        for label, action in menus:
            self.addMenuItem({'name': '[B]' + AutoTranslate.language(label) + '[/B]', 'action': action, 'mediatype': 'tvshow', 'iconimage': self.icon(action.split('_')[0])})
        self.end()

    def animes(self):
        self.setcontent('videos')
        menus = [
            ('Popular animes', 'popular_animes', 'popular'),
            ('Season animes', 'airing_animes', 'airing'),
            ('Animes by year of release', 'animes_by_year', 'animes'),
            ('Search animes', 'search_animes', 'search'),
        ]
        for label, action, icon in menus:
            self.addMenuItem({'name': '[B]' + AutoTranslate.language(label) + '[/B]', 'action': action, 'mediatype': 'tvshow', 'iconimage': self.icon(icon)})
        self.end()

    def animes_by_year(self, year=None):
        self.setcontent('videos')
        if not year:
            current_year = datetime.now().year
            years = list(range(current_year - 45, current_year + 1))
            for y in reversed(years):
                self.addMenuItem({
                    'name': f'[B]{y}[/B]',
                    'action': 'animes_by_year',
                    'anime_year': str(y),
                    'iconimage': self.icon('premiere')
                }, folder=True)
            self.end()
            return
        seasons = ['winter', 'spring', 'summer', 'fall']
        season_names = {
            'winter': AutoTranslate.language('Winter'),
            'spring': AutoTranslate.language('Spring'),
            'summer': AutoTranslate.language('Summer'),
            'fall': AutoTranslate.language('Fall')
        }
        for s in seasons:
            self.addMenuItem({
                'name': f'[B]{season_names.get(s, s.capitalize())} {year}[/B]',
                'action': 'animes_by_season',
                'anime_year': year,
                'anime_season': s,
                'iconimage': self.icon('premiere')
            }, folder=True)
        self.end()

    def pagination_animes_by_season(self, year, season, page):
        self._pagination_anime(lambda p: httpclient.animes_by_season_api(year, season, p), page, 'tvshow', 'animes_by_season', self.icon('animes'), extra_params={'anime_year': year, 'anime_season': season})

    def pagination_movies_popular(self, page):
        self._pagination_generic(httpclient.movies_popular_api, page, 'movie', 'popular_movies', self.icon('movies'))

    def pagination_movies_premiere(self, page):
        self._pagination_generic(lambda p: httpclient.movies_api(p, 'premiere'), page, 'movie', 'premiere_movies', self.icon('movies'))

    def pagination_movies_trending(self, page):
        self._pagination_generic(lambda p: httpclient.movies_api(p, 'trending'), page, 'movie', 'trending_movies', self.icon('movies'))

    def pagination_tv_shows_popular(self, page):
        self._pagination_generic(httpclient.tv_shows_popular_api, page, 'tvshow', 'popular_tv_shows', self.icon('series'))

    def pagination_tv_shows_premiere(self, page):
        self._pagination_generic(httpclient.tv_shows_premiere_api, page, 'tvshow', 'premiere_tv_shows', self.icon('series'))

    def pagination_tv_shows_trending(self, page):
        self._pagination_generic(httpclient.tv_shows_trending_api, page, 'tvshow', 'trending_tv_shows', self.icon('series'))

    def pagination_animes_popular(self, page):
        self._pagination_anime(httpclient.animes_popular_api, page, 'tvshow', 'popular_animes', self.icon('animes'))

    def pagination_animes_airing(self, page):
        self._pagination_anime(httpclient.animes_airing_api, page, 'tvshow', 'airing_animes', self.icon('animes'))

    def search_movies(self, search=None, page=1):
        if not search:
            search = self.input_text(AutoTranslate.language('Search movies'))
        if search:
            self.pagination_search_movies(search, page)
        else:
            self.notify_invalid_search()

    def pagination_search_movies(self, search, page):
        self._pagination_search_generic(search, page, 'movie', 'search_movies', self.icon('movies'))

    def search_tv_shows(self, search=None, page=1):
        if not search:
            search = self.input_text(AutoTranslate.language('Search tv shows'))
        if search:
            self.pagination_search_tv_shows(search, page)
        else:
            self.notify_invalid_search()

    def pagination_search_tv_shows(self, search, page):
        self._pagination_search_generic(search, page, 'tv', 'search_tv_shows', self.icon('series'))

    def search_animes(self, search=None, page=1):
        if not search:
            search = self.input_text(AutoTranslate.language('Search animes'))
        if search:
            self._pagination_search_anime(search, page)
        else:
            self.notify_invalid_search()

    def _pagination_generic(self, api_func, page, mediatype, action, default_icon):
        self.setcontent(mediatype + 's')
        total_pages, results = api_func(page)
        for item in results:
            title = item.get('title') or item.get('name')
            year = item.get('release_date', '')[:4] or item.get('first_air_date', '')[:4]
            fullname = f"{title} ({year})" if year else title
            icon = f"https://image.tmdb.org/t/p/w500{item.get('poster_path')}" if item.get('poster_path') else default_icon
            fanart = f"https://image.tmdb.org/t/p/original{item.get('backdrop_path')}" if item.get('backdrop_path') else ''
            description = item.get('overview', '')
            original_title = item.get('original_title') or item.get('original_name') or title
            
            params = {
                'name': fullname,
                'action': 'details',
                'video_id': str(item['id']),
                'year': year,
                'iconimage': icon,
                'fanart': fanart,
                'description': description,
                'mediatype': mediatype,
                'original_name': original_title
            }
            
            if mediatype == 'movie':
                params['movie_name'] = title
            else:
                params['serie_name'] = title
            
            self.addMenuItem(params, folder=True)
        
        if int(page) + 1 <= total_pages:
            self.addMenuItem({'name': f"[B]{AutoTranslate.language('Page')}{int(page)+1}{AutoTranslate.language('of')}{total_pages}[/B]", 'action': action, 'page': str(int(page) + 1), 'iconimage': self.icon('next'), 'mediatype': mediatype})
        self.end()

    def _pagination_anime(self, api_func, page, mediatype, action, default_icon, extra_params=None):
        self.setcontent(mediatype + 's')
        total_pages, results = api_func(page)
        for item in results:
            title = item.get('title_english') or item.get('title')
            year = item.get('year')
            year = str(year) if year is not None else '0'

            fullname = f"{title} ({year})" if year and year != '0' else title
            icon = item.get('images', {}).get('jpg', {}).get('large_image_url') if item.get('images') else default_icon
            fanart = item.get('images', {}).get('jpg', {}).get('large_image_url') if item.get('images') else ''
            description = item.get('synopsis', '')
            mediatype_item = 'movie' if item.get('type') == 'Movie' else 'tvshow'
            
            params = {
                'name': fullname,
                'action': 'details',
                'video_id': str(item['mal_id']),
                'year': year,
                'iconimage': icon,
                'fanart': fanart,
                'description': description,
                'mediatype': mediatype_item,
                'is_anime': 'true',
                'anime_name': title
            }
            
            self.addMenuItem(params, folder=True)
        
        if int(page) + 1 <= total_pages:
            next_params = {
                'name': '[B]' + AutoTranslate.language('Page') + f"{int(page)+1}" + AutoTranslate.language('of') + f"{total_pages}" + '[/B]',
                'action': action,
                'page': str(int(page) + 1),
                'iconimage': self.icon('next'),
                'mediatype': 'tvshow'
            }
            if extra_params:
                next_params.update(extra_params)
            self.addMenuItem(next_params)
        self.end()

    def _pagination_search_anime(self, search, page):
        self.setcontent('tvshows')
        total_pages, results = httpclient.search_animes_api(search, page)
        for item in results:
            title = item.get('title_english') or item.get('title')
            year = item.get('year')
            year = str(year) if year is not None else '0'
            fullname = f"{title} ({year})" if year and year != '0' else title
            icon = item.get('images', {}).get('jpg', {}).get('large_image_url') if item.get('images') else self.icon('animes')
            fanart = item.get('images', {}).get('jpg', {}).get('large_image_url') if item.get('images') else ''
            description = item.get('synopsis', '')
            mediatype = 'movie' if item.get('type') == 'Movie' else 'tvshow'
            
            params = {
                'name': fullname,
                'action': 'details',
                'video_id': str(item['mal_id']),
                'year': year,
                'iconimage': icon,
                'fanart': fanart,
                'description': description,
                'mediatype': mediatype,
                'is_anime': 'true',
                'anime_name': title
            }
            
            self.addMenuItem(params, folder=True)
        
        if int(page) + 1 <= total_pages:
            self.addMenuItem({'name': '[B]' + AutoTranslate.language('Page') + f"{int(page)+1}" + AutoTranslate.language('of') + f"{total_pages}" + '[/B]', 'action': 'search_animes', 'page': str(int(page) + 1), 'search': search, 'iconimage': self.icon('next'), 'mediatype': 'tvshow'})
        self.end()

    def _pagination_search_generic(self, search, page, filter_type, action, default_icon):
        self.setcontent('tvshows' if filter_type == 'tv' else 'movies')
        total_pages, results = httpclient.search_movies_api(search, page)
        for item in results:
            if item.get('media_type') != filter_type:
                continue
            title = item.get('title') or item.get('name')
            year = item.get('release_date', '')[:4] or item.get('first_air_date', '')[:4]
            fullname = f"{title} ({year})" if year else title
            icon = f"https://image.tmdb.org/t/p/w500{item.get('poster_path')}" if item.get('poster_path') else default_icon
            fanart = f"https://image.tmdb.org/t/p/original{item.get('backdrop_path')}" if item.get('backdrop_path') else ''
            description = item.get('overview', '')
            original_title = item.get('original_title') or item.get('original_name') or title
            
            params = {
                'name': fullname,
                'action': 'details',
                'video_id': str(item['id']),
                'year': year,
                'iconimage': icon,
                'fanart': fanart,
                'description': description,
                'mediatype': 'movie' if filter_type == 'movie' else 'tvshow',
                'original_name': original_title
            }
            
            if filter_type == 'movie':
                params['movie_name'] = title
            else:
                params['serie_name'] = title
            
            self.addMenuItem(params, folder=True)
        
        if int(page) + 1 <= total_pages:
            self.addMenuItem({'name': '[B]' + AutoTranslate.language('Page') + f"{int(page)+1}" + AutoTranslate.language('of') + f"{total_pages}" + '[/B]', 'action': action, 'page': str(int(page) + 1), 'search': search, 'iconimage': self.icon('next'), 'mediatype': 'movie' if filter_type == 'movie' else 'tvshow'})
        self.end()

    def extract_season_number(self, anime_data):
        texts = []
        texts.append(anime_data.get('title', ''))
        texts.append(anime_data.get('title_english', ''))
        for t in anime_data.get('titles', []):
            texts.append(t.get('title', ''))
        for text in texts:
            if not text:
                continue
            m = re.search(r'(?:season|temporada)\s*(\d+)', text, re.I)
            if m:
                return int(m.group(1))
            m = re.search(r'(\d+)(?:st|nd|rd|th)\s+season', text, re.I)
            if m:
                return int(m.group(1))
            m = re.search(r'\b(\d+)$', text)
            if m:
                return int(m.group(1))
        return 1

    def details(self, video_id, year, iconimage, fanart, description, mediatype, is_anime='false', movie_name='', serie_name='', anime_name='', original_name=''):
        if not all([video_id, year, iconimage, fanart, description, mediatype]):
            self.notify(AutoTranslate.language("invalid_params"))
            return
        try:
            if is_anime == 'true':
                show_src = httpclient.open_anime_api(video_id)
                if not show_src or 'data' not in show_src:
                    raise Exception("Nenhum dado retornado da Jikan API")
                show_src = show_src['data']
                mal_id = str(show_src['mal_id'])
                title = anime_name or show_src.get('title_english') or show_src.get('title')
                description = show_src.get('synopsis', description)
                anime_type = show_src.get('type')
                year = str(show_src.get('year') or year)
                genre_list = [g['name'] for g in show_src.get('genres', [])]
                genre = ', '.join(genre_list)
                season_number = self.extract_season_number(show_src)

                if self.is_auto_play_enabled() and anime_type == 'Movie':
                    success = self.auto_play_preferred_language(None, mal_id, year, None, None, title, genre, iconimage, fanart, description, is_anime='true', anime_name=title, original_name=original_name)
                    if success:
                        return
                if anime_type == 'Movie':
                    menus_links = sources.show_content_anime(mal_id, year)
                    if not menus_links:
                        raise Exception("No menu links found")
                    self.setcontent('videos')
                    for name2, page_href in menus_links:
                        self.addMenuItem({
                            'name': name2,
                            'action': 'play_resolve',
                            'video_title': title,
                            'url': page_href,
                            'iconimage': iconimage,
                            'fanart': fanart,
                            'playable': 'false',
                            'description': description,
                            'mal_id': mal_id,
                            'year': year,
                            'mediatype': 'video',
                            'is_anime': 'true',
                            'anime_name': title,
                            'original_name': original_name
                        }, folder=False)
                    self.end()
                else:
                    episodes = httpclient.open_anime_episodes_api(video_id)
                    self.setcontent('episodes')
                    today = datetime.today().date()
                    for episode in episodes:
                        aired = episode.get('aired')
                        if aired:
                            try:
                                air_date_obj = datetime.strptime(aired.split('T')[0], "%Y-%m-%d").date()
                                if air_date_obj > today:
                                    continue
                            except Exception:
                                pass
                        epnum = episode.get('mal_id')
                        ep_name = episode.get('title') or f"{title} {epnum}"
                        icon = episode.get('images', {}).get('jpg', {}).get('image_url') or iconimage
                        description = episode.get('synopsis') or show_src.get('synopsis', '')
                        name = f"{int(epnum):02d} - {ep_name}"
                        if episode.get('filler'):
                            name += " [COLOR yellow](Filler)[/COLOR]"
                        self.addMenuItem({
                            'name': name,
                            'action': 'provider',
                            'mal_id': mal_id,
                            'year': year,
                            'season_num': str(season_number),
                            'episode_num': str(epnum),
                            'iconimage': icon,
                            'fanart': fanart,
                            'description': description,
                            'video_title': f"{title} - {ep_name}",
                            'mediatype': 'episode',
                            'genre': genre,
                            'is_anime': 'true',
                            'anime_name': title,
                            'original_name': original_name
                        }, folder=True)
                    self.end()
            else:
                if mediatype == 'movie':
                    show_src = httpclient.open_movie_api(video_id)
                    imdb_id = show_src.get('imdb_id')
                    external_ids = show_src.get('external_ids')
                    if external_ids:
                        imdb_external = external_ids.get('imdb_id')
                    else:
                        imdb_external = ''
                    if imdb_id:
                        imdb = imdb_id
                    else:
                        imdb = imdb_external
                else:
                    show_src = httpclient.open_season_api(video_id)
                    external_ids = show_src.get('external_ids')
                    if external_ids:
                        imdb = external_ids.get('imdb_id')
                    else:
                        imdb = ''
                        
                if not show_src:
                    raise Exception("Nenhum dado retornado da API")
                    
                title = movie_name or serie_name or show_src.get('name') or show_src.get('title') or ''
                if not original_name:
                    original_name = show_src.get('original_title') or show_src.get('original_name') or title
                genre_list = [g['name'] for g in show_src.get('genres', [])]
                genre = ', '.join(genre_list)
                if self.is_auto_play_enabled() and mediatype == 'movie' and imdb:
                    success = self.auto_play_preferred_language(imdb, None, year, None, None, title, genre, iconimage, fanart, description, movie_name=title, original_name=original_name)
                    if success:
                        return
                if mediatype == 'movie':
                    if imdb:
                        menus_links = sources.show_content(imdb, year, None, None)
                        if not menus_links:
                            raise Exception("No menu links found")
                        self.setcontent('videos')
                        for name2, page_href in menus_links:
                            self.addMenuItem({
                                'name': name2,
                                'action': 'play_resolve',
                                'video_title': title,
                                'url': page_href,
                                'iconimage': iconimage,
                                'fanart': fanart,
                                'playable': 'false',
                                'description': description,
                                'imdb': imdb,
                                'year': year,
                                'mediatype': 'video',
                                'movie_name': title,
                                'original_name': original_name
                            }, folder=False)
                        self.end()
                    else:
                        self.notify(AutoTranslate.language("IMDb not found"))
                else:
                    seasons = show_src.get('seasons', [])
                    self.setcontent('seasons')
                    for season in seasons:
                        season_number = season['season_number']
                        if season_number == 0:
                            season_name = AutoTranslate.language("Specials")
                        else:
                            season_name = f"{season_number}ª {AutoTranslate.language('Season')}"
                        icon = f"https://image.tmdb.org/t/p/w500{season.get('poster_path')}" if season.get('poster_path') else iconimage
                        self.addMenuItem({
                            'name': season_name,
                            'action': 'season_tvshow',
                            'video_id': video_id,
                            'imdb': imdb,
                            'year': year,
                            'iconimage': icon,
                            'fanart': fanart,
                            'description': season.get('overview', ''),
                            'season_num': str(season['season_number']),
                            'mediatype': 'season',
                            'serie_name': title,
                            'original_name': original_name
                        }, folder=True)
                    self.end()
        except Exception:
            self.notify(AutoTranslate.language("Failed to load details"))

    def season_tvshow(self, video_id, year, season_num, original_name='', imdb='', serie_name=''):
        if not video_id or season_num is None:
            self.notify(AutoTranslate.language("invalid_params"))
            return
        try:
            if not imdb:
                show_src = httpclient.open_season_api(video_id)
                external_ids = show_src.get('external_ids')
                if external_ids:
                    imdb = external_ids.get('imdb_id')
                else:
                    imdb = ''
                title_show = serie_name or show_src.get('name') or show_src.get('title') or ''
                if not original_name:
                    original_name = show_src.get('original_name') or show_src.get('original_title') or title_show
            else:
                title_show = serie_name or ''
        except Exception:
            title_show = serie_name or ''
        src = httpclient.show_episode_api(video_id, season_num)
        self.setcontent('episodes')
        today = datetime.today().date()
        for episode in src.get('episodes', []) or []:
            air_date = episode.get('air_date')
            if air_date:
                try:
                    air_date_obj = datetime.strptime(air_date, "%Y-%m-%d").date()
                    if air_date_obj > today:
                        continue
                except Exception:
                    pass
            epnum = episode.get('episode_number')
            ep_name = episode.get('name') or f"{title_show} {epnum}"
            icon = f"https://image.tmdb.org/t/p/w500{episode.get('still_path')}" if episode.get('still_path') else self.icon('series')
            fanart = f"https://image.tmdb.org/t/p/original{episode.get('backdrop_path')}" if episode.get('backdrop_path') else ''
            description = episode.get('overview') or title_show
            self.addMenuItem({
                'name': f"{int(season_num)}x{int(epnum):02d} - {ep_name}",
                'action': 'provider',
                'imdb': imdb,
                'year': year,
                'season_num': str(season_num),
                'episode_num': str(epnum),
                'iconimage': icon,
                'fanart': fanart,
                'description': description,
                'video_title': f"{title_show} - {ep_name}",
                'mediatype': 'episode',
                'serie_name': title_show,
                'genre': '',
                'original_name': original_name
            }, folder=True)
        self.end()

    def list_server_links(self, imdb, mal_id, year, season_num, episode_num, name, video_title, genre, iconimage, fanart, description, is_anime='false', movie_name='', serie_name='', anime_name='', original_name=''):
        if is_anime == 'true':
            menus_links = sources.show_content_anime(mal_id, year, season_num, episode_num)
        else:
            menus_links = sources.show_content(imdb, year, season_num, episode_num)
        if self.is_auto_play_enabled() and menus_links:
            success = self.auto_play_preferred_language(imdb, mal_id, year, season_num, episode_num, video_title, genre, iconimage, fanart, description, is_anime=is_anime, movie_name=movie_name, serie_name=serie_name, anime_name=anime_name, original_name=original_name)
            if success:
                return
        if menus_links:
            self.setcontent('videos')
            for name2, page_href in menus_links:
                link_params = {
                    'name': name2,
                    'action': 'play_resolve',
                    'video_title': video_title,
                    'url': page_href,
                    'iconimage': iconimage,
                    'fanart': fanart,
                    'playable': 'false',
                    'description': description,
                    'season_num': str(season_num) if season_num is not None else '',
                    'episode_num': str(episode_num) if episode_num is not None else '',
                    'genre': genre,
                    'year': str(year) if year is not None else '',
                    'is_anime': is_anime,
                    'original_name': original_name
                }
                
                if is_anime == 'true':
                    link_params['mal_id'] = mal_id
                    link_params['anime_name'] = anime_name or video_title
                elif season_num and episode_num:
                    link_params['imdb'] = imdb
                    link_params['serie_name'] = serie_name or video_title.split(' - ')[0] if ' - ' in video_title else video_title
                else:
                    link_params['imdb'] = imdb
                    link_params['movie_name'] = movie_name or video_title
                
                self.addMenuItem(link_params, folder=False)
            self.end()
        else:
            self.notify_no_sources()

    def resolve_links(self, url, video_title, imdb, mal_id, year, season_num, episode_num, genre, iconimage, fanart, description, playable, is_anime='false', movie_name='', serie_name='', anime_name='', original_name=''):
        try:
            if season_num and episode_num:
                try:
                    if is_anime == 'true':
                        episode_src = httpclient.open_anime_episode_api(mal_id, episode_num)
                        description = episode_src.get('synopsis', description)
                    else:
                        find_src = httpclient.find_tv_show_api(imdb)
                        tmdb_id = find_src.get('tv_results', [{}])[0].get('id')
                        if tmdb_id:
                            episode_src = httpclient.open_episode_api(tmdb_id, season_num, episode_num)
                            description = episode_src.get('overview', description)
                except Exception:
                    pass
            elif not season_num and not episode_num:
                try:
                    if is_anime == 'true':
                        show_src = httpclient.open_anime_api(mal_id).get('data', {})
                        description = show_src.get('synopsis', description)
                    else:
                        find_src = httpclient.find_movie_api(imdb)
                        tmdb_id = find_src.get('movie_results', [{}])[0].get('id')
                        if tmdb_id:
                            movie_src = httpclient.open_movie_api(tmdb_id)
                            description = movie_src.get('overview', description)
                except Exception:
                    pass

            self.stop_if_playing()

            showtitle = video_title
            episode_title = video_title
            if season_num and episode_num:
                if " - " in video_title:
                    showtitle, episode_title = video_title.split(" - ", 1)
                else:
                    showtitle = video_title
                    episode_title = f"{AutoTranslate.language('Episode')} {episode_num}"
            try:
                stream, sub = sources.select_resolver(url, season_num, episode_num)
            except Exception:
                self.notify(AutoTranslate.language('Failed to resolve link'))
                return
            if not stream:
                self.notify_no_sources()
                return
            list_item = xbmcgui.ListItem(label=episode_title if season_num and episode_num else video_title)
            list_item.setArt({'thumb': iconimage, 'icon': iconimage, 'fanart': fanart})
            if season_num and episode_num:
                set_listitem_info(list_item, episode_title, description, showtitle, 'episode')
            else:
                set_listitem_info(list_item, episode_title, description, mediatype='movie')
            list_item.setContentLookup(False)
            if sub:
                list_item.setSubtitles([sub])
            list_item.setPath(stream)
            xbmc.Player().play(stream, list_item)
        except Exception:
            self.notify(AutoTranslate.language('Error trying to play'))
