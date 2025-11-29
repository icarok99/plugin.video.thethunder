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

TRANSLATE = xbmcvfs.translatePath

def log(msg):
    xbmc.log(f"[THUNDER ADDON] {msg}", level=xbmc.LOGINFO)

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

    # CORREÇÃO DEFINITIVA DO IDIOMA (funciona em qualquer dispositivo)
    def get_preferred_language(self):
        try:
            addon = xbmcaddon.Addon()
            valor = addon.getSetting("preferred_language")
            log(f"[IDIOMA] Valor lido do settings.xml → '{valor}' (tipo: {type(valor)})")
            if valor == "0":
                result = AutoTranslate.language("Portuguese")   # DUBLADO
                log("[IDIOMA] Interpretação final: DUBLADO")
                return result
            else:
                result = AutoTranslate.language("English")      # LEGENDADO
                log("[IDIOMA] Interpretação final: LEGENDADO")
                return result
        except Exception as e:
            log(f"[IDIOMA] ERRO ao ler preferência: {e} → usando DUBLADO como padrão")
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
            info_tag = li.getVideoInfoTag()
            info_tag.setTitle(title)
            info_tag.setPlot(description)
            info_tag.setMediaType('video')
            li.setContentLookup(False)
            if subtitles:
                li.setSubtitles([subtitles])
            li.setPath(url)
            xbmc.Player().play(url, li)
        except Exception as e:
            self.notify(f"{AutoTranslate.language('Error trying to play')}: {e}")

    def is_auto_play_enabled(self):
        try:
            return xbmcaddon.Addon().getSetting("auto_play_enabled") == "true"
        except Exception:
            return False

    # SISTEMA DE PONTUAÇÃO + DEBUG (nunca mais escolhe idioma errado)
    def try_resolve_with_fallback(self, menus_links, season=None, episode=None):
        if not menus_links:
            log("Nenhum link encontrado pelo scraper")
            return None, None

        preferred_lang = self.get_preferred_language().upper()
        log(f"Preferência de idioma configurada: {preferred_lang}")

        def get_priority_score(label):
            if not label:
                return 0
            u = label.upper()
            if preferred_lang == "DUBLADO":
                if any(x in u for x in ["DUBLADO", "DUB", "PT-BR", "PORTUGUÊS", "PTBR"]):
                    return 100
            else:  # LEGENDADO
                if any(x in u for x in ["LEGENDADO", "LEG", "SUB", "INGLÊS", "ENGLISH", "SUBTITLED"]):
                    return 100
            return 0

        sorted_links = sorted(menus_links, key=lambda x: get_priority_score(x[0]), reverse=True)

        log(f"Total de links encontrados: {len(menus_links)}")
        for i, (name, url) in enumerate(sorted_links):
            score = get_priority_score(name)
            status = "IDIOMA PREFERIDO" if score == 100 else "idioma alternativo"
            log(f"  [{i+1}] {name}  →  Score: {score} ({status})")

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

                log(f"Tentando resolver: {name} → {final_url[:80]}...")
                stream, sub = sources.select_resolver(final_url, season, episode)
                if stream:
                    log(f"SUCESSO! Reproduzindo: {name}")
                    return stream, sub
                else:
                    log(f"Falhou ao resolver: {name}")
            except Exception as e:
                log(f"Erro ao tentar resolver {name}: {str(e)}")
                continue

        log("Nenhum link conseguiu ser resolvido")
        return None, None

    def auto_play_preferred_language(self, imdb, year, season, episode, video_title, genre, iconimage, fanart, description):
        log(f"=== INICIANDO AUTOPLAY ===")
        log(f"Título: {video_title} | IMDb: {imdb} | S{season}E{episode if season else ''}")

        try:
            menus_links = sources.show_content(imdb, year, season, episode)
            if not menus_links:
                log("show_content() retornou vazio")
                self.notify_no_sources()
                return False

            stream, sub = self.try_resolve_with_fallback(menus_links, season, episode)
            if not stream:
                log("Nenhum stream válido após todas as tentativas")
                self.notify_stream_unavailable()
                return False

            self.stop_if_playing()

            showtitle = episode_title = video_title
            if season and episode:
                if " - " in video_title:
                    showtitle, episode_title = video_title.split(" - ", 1)
                else:
                    episode_title = f"{AutoTranslate.language('Episode')} {episode}"

            list_item = xbmcgui.ListItem(label=episode_title if season and episode else video_title)
            list_item.setArt({'thumb': iconimage, 'icon': iconimage, 'fanart': fanart})
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

            if sub:
                list_item.setSubtitles([sub])

            list_item.setPath(stream)
            xbmc.Player().play(stream, list_item)
            log("Reprodução iniciada com sucesso!")
            return True

        except Exception as e:
            log(f"Erro crítico no autoplay: {str(e)}")
            self.notify(f"{AutoTranslate.language('Error trying to auto-play')}: {e}")
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
            ('Trending', 'trending_movies'),
            ('Popular', 'popular_movies'),
            ('Search', 'search_movies'),
        ]
        for label, action in menus:
            self.addMenuItem({'name': '[B]' + AutoTranslate.language(label) + '[/B]', 'action': action, 'mediatype': 'movies', 'iconimage': self.icon(action.split('_')[0])})
        self.end()

    def tv_shows(self):
        self.setcontent('videos')
        menus = [
            ('New tv shows', 'premiere_tv_shows'),
            ('Trending', 'trending_tv_shows'),
            ('Popular', 'popular_tv_shows'),
            ('Search', 'search_tv_shows'),
        ]
        for label, action in menus:
            self.addMenuItem({'name': '[B]' + AutoTranslate.language(label) + '[/B]', 'action': action, 'mediatype': 'tvshow', 'iconimage': self.icon(action.split('_')[0])})
        self.end()

    def animes(self):
        self.setcontent('videos')
        menus = [
            ('New animes', 'premiere_animes'),
            ('Popular', 'popular_animes'),
            ('Airing', 'airing_animes'),
            ('Search', 'search_animes'),
        ]
        for label, action in menus:
            self.addMenuItem({'name': '[B]' + AutoTranslate.language(label) + '[/B]', 'action': action, 'mediatype': 'tvshow', 'iconimage': self.icon(action.split('_')[0])})
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
            self.addMenuItem({'name': fullname, 'action': 'details', 'video_id': str(item['id']), 'year': year, 'iconimage': icon, 'fanart': fanart, 'description': description, 'mediatype': mediatype}, folder=True)
        if int(page) + 1 <= total_pages:
            self.addMenuItem({'name': f"[B]{AutoTranslate.language('Page')}{int(page)+1}{AutoTranslate.language('of')}{total_pages}[/B]", 'action': action, 'page': str(int(page) + 1), 'iconimage': self.icon('next'), 'mediatype': mediatype})
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
            self.addMenuItem({'name': fullname, 'action': 'details', 'video_id': str(item['id']), 'year': year, 'iconimage': icon, 'fanart': fanart, 'description': description, 'mediatype': 'movie' if filter_type == 'movie' else 'tvshow'}, folder=True)
        if int(page) + 1 <= total_pages:
            self.addMenuItem({'name': '[B]' + AutoTranslate.language('Page') + f"{int(page)+1}" + AutoTranslate.language('of') + f"{total_pages}" + '[/B]', 'action': action, 'page': str(int(page) + 1), 'search': search, 'iconimage': self.icon('next'), 'mediatype': 'movie' if filter_type == 'movie' else 'tvshow'})
        self.end()

    def details(self, video_id, year, iconimage, fanart, description, mediatype):
        if not all([video_id, year, iconimage, fanart, description, mediatype]):
            self.notify(AutoTranslate.language("invalid_params"))
            return
        try:
            if mediatype == 'movie':
                show_src = httpclient.open_movie_api(video_id)
            else:
                show_src = httpclient.open_season_api(video_id)
            if not show_src:
                raise Exception("Nenhum dado retornado da API")
            imdb = show_src.get('external_ids', {}).get('imdb_id', '') or ''
            title = show_src.get('name') or show_src.get('title') or ''
            if self.is_auto_play_enabled() and mediatype == 'movie' and imdb:
                genre = show_src.get('genres', [{}])[0].get('name', '')
                success = self.auto_play_preferred_language(
                    imdb=imdb,
                    year=year,
                    season=None,
                    episode=None,
                    video_title=title,
                    genre=genre,
                    iconimage=iconimage,
                    fanart=fanart,
                    description=description
                )
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
                    if season_number == 0:
                        season_name = AutoTranslate.language("Specials")
                    else:
                        season_name = f"{season_number}ª {AutoTranslate.language('Season')}"
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
        except Exception:
            self.notify(AutoTranslate.language("Failed to load details"))

    def season_tvshow(self, video_id, year, season):
        if not video_id or season is None:
            self.notify(AutoTranslate.language("invalid_params"))
            return
        try:
            show_src = httpclient.open_season_api(video_id)
            imdb = show_src.get('external_ids', {}).get('imdb_id', '') or ''
            title_show = show_src.get('name') or show_src.get('title') or ''
        except Exception:
            imdb = ''
            title_show = ''
        src = httpclient.show_episode_api(video_id, season)
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
                except Exception:
                    pass
            self.stop_if_playing()
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
            except Exception:
                self.notify(AutoTranslate.language('Failed to resolve link'))
                return
            if not stream:
                self.notify_no_sources()
                return
            list_item = xbmcgui.ListItem(label=episode_title if season and episode else video_title)
            list_item.setArt({'thumb': iconimage, 'icon': iconimage, 'fanart': fanart})
            info_tag = list_item.getVideoInfoTag()
            if season and episode:
                info_tag.setTitle(episode_title)
                info_tag.setTvShowTitle(showtitle)
                info_tag.setMediaType('episode')
                info_tag.setPlot(description)
            else:
                info_tag.setTitle(episode_title)
                info_tag.setPlot(description)
                info_tag.setMediaType('movie')
                info_tag.setOriginalTitle(episode_title)
            list_item.setContentLookup(False)
            if sub:
                list_item.setSubtitles([sub])
            list_item.setPath(stream)
            xbmc.Player().play(stream, list_item)
        except Exception as e:
            self.notify(f"{AutoTranslate.language('Error trying to play')}: {e}")
