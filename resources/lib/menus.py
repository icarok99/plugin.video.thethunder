# -*- coding: utf-8 -*-

import os
import re
import sys
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs
from urllib.parse import urlparse, unquote, parse_qs, quote, urlencode
from resources.lib import httpclient, sources
from resources.lib.autotranslate import AutoTranslate
from kodi_helper import myAddon
from datetime import datetime, date

TRANSLATE = xbmcvfs.translatePath

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
            lang_pref = self.getSetting("preferred_language")
            return "DUBLADO" if lang_pref == "0" else "LEGENDADO"
        except:
            return "DUBLADO"

    def play(self, url, title, iconimage, fanart, description, subtitles=None):
        try:
            li = xbmcgui.ListItem(label=title)
            li.setArt({'icon': iconimage, 'thumb': iconimage, 'fanart': fanart})
            if self.kversion >= 20:
                info_tag = li.getVideoInfoTag()
                info_tag.setTitle(title)
                info_tag.setPlot(description)
                info_tag.setMediaType('video')
            else:
                li.setInfo('video', {'title': title, 'plot': description, 'mediatype': 'video'})
            if subtitles:
                li.setSubtitles([subtitles])
            xbmc.Player().play(url, li)
        except:
            self.notify(AutoTranslate.language('Error playing'))

    def is_auto_play_enabled(self):
        try:
            addon = xbmcaddon.Addon()
            return addon.getSetting("auto_play_enabled") == "true"
        except:
            return False

    def try_resolve_with_fallback(self, menus_links, season, episode):
        try:
            if not menus_links:
                return None, None
            preferred_lang = self.get_preferred_language().upper()
            preferred_links = [link for link in menus_links if preferred_lang in link[0].upper()]
            other_links = [link for link in menus_links if preferred_lang not in link[0].upper()]
            url_cache = {}

            def normalize_links(links):
                normalized = []
                for lbl, url in links:
                    if not url:
                        continue
                    if url in url_cache:
                        parsed = url_cache[url]
                    else:
                        decoded = unquote(url)
                        parsed = urlparse(decoded)
                        url_cache[url] = parsed
                    try:
                        qs = parse_qs(parsed.query)
                        inner = qs.get('url', [None])[0] or qs.get('u', [None])[0]
                        if inner:
                            decoded = unquote(inner)
                            if decoded in url_cache:
                                parsed = url_cache[decoded]
                            else:
                                parsed = urlparse(decoded)
                                url_cache[decoded] = parsed
                    except:
                        pass
                    hostname = parsed.hostname.upper() if parsed.hostname else ""
                    normalized.append({'label': lbl, 'url': url, 'decoded_url': decoded, 'hostname': hostname})
                return normalized

            norm_pref = normalize_links(preferred_links)
            norm_other = normalize_links(other_links)
            providers = ["MIXDROP", "WAREZCDN"]

            def attempt_list(links):
                tried_urls = set()
                for provider in providers:
                    candidates = [n for n in links if provider in n['label'].upper() or provider in n['hostname']]
                    for c in candidates:
                        decoded = c['decoded_url']
                        if decoded in tried_urls:
                            continue
                        tried_urls.add(decoded)
                        try:
                            stream, sub = sources.select_resolver(decoded, season, episode)
                            if stream:
                                return stream, sub
                        except:
                            continue
                for c in links:
                    decoded = c['decoded_url']
                    if decoded in tried_urls:
                        continue
                    tried_urls.add(decoded)
                    try:
                        stream, sub = sources.select_resolver(decoded, season, episode)
                        if stream:
                            return stream, sub
                    except:
                        continue
                return None, None

            stream, sub = attempt_list(norm_pref)
            if stream:
                return stream, sub
            return attempt_list(norm_other)
        except:
            return None, None

    def auto_play_preferred_language(self, imdb, year, season, episode, video_title, genre, iconimage, fanart, description):
        try:
            menus_links = sources.show_content(imdb, year, season, episode)
            if not menus_links:
                return False
            stream, sub = self.try_resolve_with_fallback(menus_links, season, episode)
            if not stream:
                return False
            showtitle = video_title
            episode_title = video_title
            if season and episode:
                if " - " in video_title:
                    showtitle, episode_title = video_title.split(" - ", 1)
                else:
                    showtitle = video_title
                    episode_title = f"{AutoTranslate.language('Episode')} {episode}"
            li = xbmcgui.ListItem(label=episode_title if season and episode else video_title)
            li.setArt({'thumb': iconimage, 'icon': iconimage, 'fanart': fanart})
            if self.kversion >= 20:
                info_tag = li.getVideoInfoTag()
                if season and episode:
                    info_tag.setTitle(episode_title)
                    info_tag.setTvShowTitle(showtitle)
                    info_tag.setMediaType('episode')
                    info_tag.setPlot(description)
                else:
                    info_tag.setTitle(video_title)
                    info_tag.setPlot(description)
                    info_tag.setMediaType('movie')
            else:
                li.setInfo('video', {
                    'title': episode_title if season and episode else video_title,
                    'plot': description,
                    'mediatype': 'episode' if season and episode else 'movie',
                    'tvshowtitle': showtitle if season and episode else '',
                    'season': int(season) if season else None,
                    'episode': int(episode) if episode else None
                })
            if sub:
                li.setSubtitles([sub])
            xbmc.Player().play(stream, li)
            return True
        except:
            return False

    def home(self):
        self.setcontent('videos')
        menus = [
            ('Movies', 'movies', 'movies'),
            ('Tv shows', 'tv_shows', 'tvshows'),
            ('Animes', 'animes', 'animes'),
            ('donation', 'donate', 'donate'),
            ('settings', 'settings', 'settings')
        ]
        for label, action, icon in menus:
            self.addMenuItem({
                'name': '[B]' + AutoTranslate.language(label) + '[/B]',
                'action': action,
                'mediatype': 'video',
                'iconimage': self.icon(icon)
            }, folder=(action != 'settings'))
        self.end()

    def movies(self):
        self.setcontent('videos')
        menus = [
            ('New movies', 'premiere_movies'),
            ('Trending', 'trending_movies'),
            ('Popular', 'popular_movies'),
            ('Search', 'search_movies')
        ]
        for label, action in menus:
            self.addMenuItem({
                'name': '[B]' + AutoTranslate.language(label) + '[/B]',
                'action': action,
                'mediatype': 'movies',
                'iconimage': self.icon(action.split('_')[0])
            })
        self.end()

    def tv_shows(self):
        self.setcontent('videos')
        menus = [
            ('New tv shows', 'premiere_tv_shows'),
            ('Trending', 'trending_tv_shows'),
            ('Popular', 'popular_tv_shows'),
            ('Search', 'search_tv_shows')
        ]
        for label, action in menus:
            self.addMenuItem({
                'name': '[B]' + AutoTranslate.language(label) + '[/B]',
                'action': action,
                'mediatype': 'tvshow',
                'iconimage': self.icon(action.split('_')[0])
            })
        self.end()

    def animes(self):
        self.setcontent('videos')
        menus = [
            ('New animes', 'premiere_animes'),
            ('Popular', 'popular_animes'),
            ('Airing', 'airing_animes'),
            ('Search', 'search_animes')
        ]
        for label, action in menus:
            self.addMenuItem({
                'name': '[B]' + AutoTranslate.language(label) + '[/B]',
                'action': action,
                'mediatype': 'tvshow',
                'iconimage': self.icon(action.split('_')[0])
            })
        self.end()

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
        self._pagination_generic(httpclient.animes_popular_api, page, 'tvshow', 'popular_animes', self.icon('animes'))

    def pagination_animes_premiere(self, page):
        self._pagination_generic(httpclient.animes_premiere_api, page, 'tvshow', 'premiere_animes', self.icon('animes'))

    def pagination_animes_airing(self, page):
        self._pagination_generic(httpclient.animes_airing_api, page, 'tvshow', 'airing_animes', self.icon('animes'))

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
            self.addMenuItem({
                'name': fullname,
                'action': 'details',
                'video_id': str(item['id']),
                'year': year,
                'iconimage': icon,
                'fanart': fanart,
                'description': description,
                'mediatype': mediatype
            }, folder=True)
        if int(page) + 1 <= total_pages:
            self.addMenuItem({
                'name': f"[B]{AutoTranslate.language('Page')}{int(page)+1}{AutoTranslate.language('of')}{total_pages}[/B]",
                'action': action,
                'page': str(int(page) + 1),
                'iconimage': self.icon('next'),
                'mediatype': mediatype
            })
        self.end()

    def search_movies(self, search=None, page=1):
        if not search:
            search = self.input_text(AutoTranslate.language('Search'))
        if search:
            self.pagination_search_movies(search, page)
        else:
            self.notify_invalid_search()

    def pagination_search_movies(self, search, page):
        self._pagination_search_generic(search, page, 'movie', 'search_movies', self.icon('movies'))

    def search_tv_shows(self, search=None, page=1):
        if not search:
            search = self.input_text(AutoTranslate.language('Search'))
        if search:
            self.pagination_search_tv_shows(search, page)
        else:
            self.notify_invalid_search()

    def pagination_search_tv_shows(self, search, page):
        self._pagination_search_generic(search, page, 'tv', 'search_tv_shows', self.icon('series'))

    def search_animes(self, search=None, page=1):
        if not search:
            search = self.input_text(AutoTranslate.language('Search'))
        if search:
            self.pagination_search_animes(search, page)
        else:
            self.notify_invalid_search()

    def pagination_search_animes(self, search, page):
        self._pagination_search_generic(search, page, 'tv', 'search_animes', self.icon('animes'))

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
            self.addMenuItem({
                'name': fullname,
                'action': 'details',
                'video_id': str(item['id']),
                'year': year,
                'iconimage': icon,
                'fanart': fanart,
                'description': description,
                'mediatype': 'movie' if filter_type == 'movie' else 'tvshow'
            }, folder=True)
        if int(page) + 1 <= total_pages:
            self.addMenuItem({
                'name': f"[B]{AutoTranslate.language('Page')}{int(page)+1}{AutoTranslate.language('of')}{total_pages}[/B]",
                'action': action,
                'page': str(int(page) + 1),
                'search': search,
                'iconimage': self.icon('next'),
                'mediatype': 'movie' if filter_type == 'movie' else 'tvshow'
            })
        self.end()

    def details(self, video_id, year, iconimage, fanart, description, mediatype):
        if not video_id or not year or not iconimage or not fanart or not description or not mediatype:
            self.notify(AutoTranslate.language("Invalid parameters"))
            return
        try:
            if mediatype == 'movie':
                show_src = httpclient.open_movie_api(video_id)
            else:
                show_src = httpclient.open_season_api(video_id)
            if not show_src:
                raise Exception("No data returned from API")
            imdb = show_src.get('external_ids', {}).get('imdb_id', '') or ''
            title = show_src.get('name') or show_src.get('title') or ''
            if self.is_auto_play_enabled() and mediatype == 'movie' and imdb:
                genre = show_src.get('genres', [{}])[0].get('name', '')
                success = self.auto_play_preferred_language(imdb=imdb, year=year, season=None, episode=None, video_title=title, genre=genre, iconimage=iconimage, fanart=fanart, description=description)
                if success:
                    return
            if mediatype == 'movie':
                if imdb:
                    menus_links = sources.show_content(imdb, year, None, None)
                    if not menus_links:
                        self.notify_no_sources()
                        return
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
                            'imdbnumber': imdb,
                            'year': year,
                            'mediatype': 'video'
                        }, folder=False)
                    self.end()
                else:
                    self.notify(AutoTranslate.language("IMDb not found"))
            else:
                seasons = show_src.get('seasons', [])
                self.setcontent('seasons')
                for season in seasons:
                    season_number = season['season_number']
                    season_name = AutoTranslate.language('Specials') if season_number == 0 else f"{season_number} {AutoTranslate.language('Season')}"
                    icon = f"https://image.tmdb.org/t/p/w500{season.get('poster_path')}" if season.get('poster_path') else iconimage
                    self.addMenuItem({
                        'name': season_name,
                        'action': 'season_tvshow',
                        'video_id': video_id,
                        'year': year,
                        'iconimage': icon,
                        'fanart': fanart,
                        'description': season.get('overview', ''),
                        'season': str(season['season_number']),
                        'mediatype': 'season'
                    }, folder=True)
                self.end()
        except:
            self.notify(AutoTranslate.language("Failed to load details"))

    def season_tvshow(self, video_id, year, season):
        if not video_id or season is None:
            self.notify(AutoTranslate.language("Invalid parameters"))
            return
        try:
            show_src = httpclient.open_season_api(video_id)
            imdb = show_src.get('external_ids', {}).get('imdb_id', '') or ''
            title_show = show_src.get('name') or show_src.get('title') or ''
        except:
            imdb = ''
            title_show = ''
        src = httpclient.show_episode_api(video_id, season)
        self.setcontent('episodes')

        today = date.today()

        for episode in src.get('episodes', []) or []:
            air_date = episode.get('air_date')
            if air_date:
                try:
                    air_date_obj = datetime.strptime(air_date, "%Y-%m-%d").date()
                    if air_date_obj > today:
                        continue  # não mostrar episódios futuros
                except:
                    pass

            epnum = episode.get('episode_number')
            ep_name = episode.get('name') or f"{AutoTranslate.language('Episode')} {epnum}"
            icon = f"https://image.tmdb.org/t/p/w500{episode.get('still_path')}" if episode.get('still_path') else self.icon('series')
            fanart = f"https://image.tmdb.org/t/p/original{episode.get('backdrop_path')}" if episode.get('backdrop_path') else ''
            description = episode.get('overview') or show_src.get('overview', '') or title_show
            self.addMenuItem({
                'name': f"{int(season)}x{int(epnum):02d} - {ep_name}",
                'action': 'provider',
                'video_id': video_id,
                'year': year,
                'season': str(season),
                'episode': str(epnum),
                'iconimage': icon,
                'fanart': fanart,
                'description': description,
                'imdbnumber': imdb,
                'title': title_show,
                'video_title': f"{title_show} - {ep_name}",
                'mediatype': 'episode'
            }, folder=True)
        self.end()

    def list_server_links(self, imdb, year, season, episode, name, video_title, genre, iconimage, fanart, description):
        menus_links = sources.show_content(imdb, year, season, episode)
        if self.is_auto_play_enabled() and menus_links:
            success = self.auto_play_preferred_language(imdb=imdb, year=year, season=season, episode=episode, video_title=video_title, genre=genre, iconimage=iconimage, fanart=fanart, description=description)
            if success:
                return
        if menus_links:
            self.setcontent('videos')
            for name2, page_href in menus_links:
                self.addMenuItem({
                    'name': name2,
                    'action': 'play_resolve',
                    'video_title': video_title,
                    'url': page_href,
                    'iconimage': iconimage,
                    'fanart': fanart,
                    'playable': 'false',
                    'description': description,
                    'imdbnumber': imdb,
                    'season': str(season) if season is not None else '',
                    'episode': str(episode) if episode is not None else '',
                    'genre': genre,
                    'year': str(year) if year is not None else ''
                }, folder=False)
            self.end()
        else:
            self.notify_no_sources()

    def resolve_links(self, url, video_title, imdb, year, season, episode, genre, iconimage, fanart, description, playable):
        try:
            if imdb:
                try:
                    if season and episode:
                        show_src = httpclient.open_season_api(imdb)
                        description = show_src.get('overview', description) or description
                    else:
                        show_src = httpclient.open_movie_api(imdb)
                        description = show_src.get('overview', description) or description
                except:
                    pass
            showtitle = video_title
            episode_title = video_title
            if season and episode:
                if " - " in video_title:
                    showtitle, episode_title = video_title.split(" - ", 1)
                else:
                    showtitle = video_title
                    episode_title = f"{AutoTranslate.language('Episode')} {episode}"
            try:
                stream, sub = sources.select_resolver(url, season, episode)
            except:
                self.notify(AutoTranslate.language('Failed to resolve link'))
                return
            if not stream:
                self.notify_no_sources()
                return
            list_item = xbmcgui.ListItem(label=episode_title if season and episode else video_title)
            list_item.setArt({'thumb': iconimage, 'icon': iconimage, 'fanart': fanart})
            if self.kversion >= 20:
                info_tag = list_item.getVideoInfoTag()
                if season and episode:
                    info_tag.setTitle(episode_title)
                    info_tag.setTvShowTitle(showtitle)
                    info_tag.setMediaType('episode')
                    info_tag.setPlot(description)
                else:
                    info_tag.setTitle(video_title)
                    info_tag.setPlot(description)
                    info_tag.setMediaType('movie')
            else:
                list_item.setInfo('video', {
                    'title': episode_title if season and episode else video_title,
                    'plot': description,
                    'mediatype': 'episode' if season and episode else 'movie',
                    'tvshowtitle': showtitle if season and episode else '',
                    'season': int(season) if season else None,
                    'episode': int(episode) if episode else None
                })
            if sub:
                list_item.setSubtitles([sub])
            xbmc.Player().play(stream, list_item)
        except:
            self.notify(AutoTranslate.language('Error playing'))