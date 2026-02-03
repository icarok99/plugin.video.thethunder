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
from resources.lib.helper import *
from resources.lib import httpclient, sources
from urllib.parse import urlparse, unquote, parse_qs
from resources.lib.autotranslate import AutoTranslate

# AUTO UPDATE (silencioso) - branch main
try:
    from resources.lib import update
    update.auto_update()
except:
    pass

KODI_VERSION = xbmc.getInfoLabel("System.BuildVersion")
KODI_MAJOR = int(KODI_VERSION.split('.')[0])

class Donate(xbmcgui.WindowDialog):
    def __init__(self):
        super().__init__()
        addon = xbmcaddon.Addon()
        home_dir = addon.getAddonInfo('path')
        translate = xbmcvfs.translatePath
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

def get_icon(image_name):
    addon = xbmcaddon.Addon()
    home_dir = addon.getAddonInfo('path')
    translate = xbmcvfs.translatePath
    return translate(os.path.join(home_dir, 'resources', 'images', f'{image_name}.png'))

def stop_player():
    try:
        player = xbmc.Player()
        if player.isPlaying():
            player.stop()
            xbmc.sleep(300)
    except:
        pass

def get_preferred_language():
    try:
        addon = xbmcaddon.Addon()
        valor = addon.getSetting("preferred_language")
        if valor == "0":
            return AutoTranslate.language("Portuguese")
        else:
            return AutoTranslate.language("English")
    except:
        return AutoTranslate.language("Portuguese")

def is_auto_play_enabled():
    try:
        return xbmcaddon.Addon().getSetting("auto_play_enabled") == "true"
    except:
        return False

def try_resolve_with_fallback(menus_links, season=None, episode=None, is_anime=False):
    if not menus_links:
        return None, None
    preferred_lang = get_preferred_language().upper()
    TOP_HOSTS = ["FILEMOON", "DOODSTREAM", "STREAMTAPE", "MIXDROP", "WAREZCDN"]
    
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
            
            if is_anime:
                if season is None and episode is None:
                    stream, sub = sources.select_resolver_anime_movie(final_url)
                else:
                    stream, sub = sources.select_resolver_anime(final_url, episode)
            else:
                if season is None and episode is None:
                    stream, sub = sources.select_resolver_movie(final_url)
                else:
                    stream, sub = sources.select_resolver_tvshow(final_url, season, episode)
            
            if stream:
                return stream, sub
        except:
            continue
    return None, None

def auto_play_preferred_language(mal_id, imdb, year, season, episode, video_title, iconimage, fanart, description, is_anime='false'):
    try:
        if is_anime == 'true':
            if episode is None:
                menus_links = sources.movie_content_anime(mal_id)
            else:
                menus_links = sources.show_content_anime(mal_id, episode)
        elif season is None and episode is None:
            menus_links = sources.movie_content(imdb, year)
        else:
            menus_links = sources.show_content(imdb, year, season, episode)
        
        if not menus_links:
            notify(AutoTranslate.language("No sources available"))
            return False
        
        stream, sub = try_resolve_with_fallback(
            menus_links, 
            season, 
            episode, 
            is_anime=(is_anime == 'true')
        )
        
        if not stream:
            notify(AutoTranslate.language("Stream unavailable"))
            return False
        stop_player()
        
        play_item = xbmcgui.ListItem(path=stream)
        play_item.setArt({'thumb': iconimage, 'icon': iconimage, 'fanart': fanart})
        
        if season and episode:
            showtitle = video_title.split(" - ")[0] if " - " in video_title else video_title
            episode_title = video_title.split(" - ")[1] if " - " in video_title else f"{AutoTranslate.language('Episode')} {episode}"
            
            if KODI_MAJOR >= 20:
                info_tag = play_item.getVideoInfoTag()
                info_tag.setTitle(episode_title)
                info_tag.setTvShowTitle(showtitle)
                info_tag.setPlot(description)
                info_tag.setMediaType('episode')
            else:
                play_item.setInfo('video', {
                    'title': episode_title,
                    'tvshowtitle': showtitle,
                    'plot': description,
                    'mediatype': 'episode'
                })
        else:
            if KODI_MAJOR >= 20:
                info_tag = play_item.getVideoInfoTag()
                info_tag.setTitle(video_title)
                info_tag.setPlot(description)
                info_tag.setMediaType('movie')
                if year:
                    info_tag.setYear(int(year))
            else:
                info_dict = {
                    'title': video_title,
                    'plot': description,
                    'mediatype': 'movie'
                }
                if year:
                    info_dict['year'] = int(year)
                play_item.setInfo('video', info_dict)
        
        if sub:
            play_item.setSubtitles([sub])
        xbmcplugin.setResolvedUrl(int(sys.argv[1]), True, play_item)
        return True
    except:
        return False

@route('/')
def index():
    addMenuItem({'name': AutoTranslate.language('Movies'), 'description': '', 'iconimage': get_icon('movies')}, destiny='/movies')
    addMenuItem({'name': AutoTranslate.language('Tv shows'), 'description': '', 'iconimage': get_icon('tvshows')}, destiny='/tvshows')
    addMenuItem({'name': AutoTranslate.language('Animes'), 'description': '', 'iconimage': get_icon('animes')}, destiny='/anime')
    addMenuItem({'name': AutoTranslate.language('donation'), 'description': '', 'iconimage': get_icon('donate')}, destiny='/donate', folder=False)
    addMenuItem({'name': AutoTranslate.language('settings'), 'description': '', 'iconimage': get_icon('settings')}, destiny='/settings', folder=False)
    end()
    setview('WideList')

@route('/donate')
def donate():
    try:
        donate_window = Donate()
        donate_window.doModal()
        del donate_window
    except:
        pass

@route('/settings')
def settings():
    addon = xbmcaddon.Addon()
    addon.openSettings()

@route('/movies')
def movies():
    addMenuItem({'name': AutoTranslate.language('New movies'), 'description': '', 'iconimage': get_icon('premiere')}, destiny='/premiere_movies')
    addMenuItem({'name': AutoTranslate.language('Trending movies'), 'description': '', 'iconimage': get_icon('trending')}, destiny='/trending_movies')
    addMenuItem({'name': AutoTranslate.language('Popular movies'), 'description': '', 'iconimage': get_icon('popular')}, destiny='/popular_movies')
    addMenuItem({'name': AutoTranslate.language('Search movies'), 'description': '', 'iconimage': get_icon('search')}, destiny='/search_movies')
    end()
    setview('WideList')

@route('/tvshows')
def tvshows():
    addMenuItem({'name': AutoTranslate.language('New tv shows'), 'description': '', 'iconimage': get_icon('premiere')}, destiny='/premiere_tvshows')
    addMenuItem({'name': AutoTranslate.language('Trending tv shows'), 'description': '', 'iconimage': get_icon('trending')}, destiny='/trending_tvshows')
    addMenuItem({'name': AutoTranslate.language('Popular tv shows'), 'description': '', 'iconimage': get_icon('popular')}, destiny='/popular_tvshows')
    addMenuItem({'name': AutoTranslate.language('Search tv shows'), 'description': '', 'iconimage': get_icon('search')}, destiny='/search_tvshows')
    end()
    setview('WideList')

@route('/anime')
def anime():
    addMenuItem({'name': AutoTranslate.language('Popular animes'), 'description': '', 'iconimage': get_icon('popular')}, destiny='/popular_anime')
    addMenuItem({'name': AutoTranslate.language('Season animes'), 'description': '', 'iconimage': get_icon('airing')}, destiny='/airing_anime')
    addMenuItem({'name': AutoTranslate.language('Animes by year of release'), 'description': '', 'iconimage': get_icon('premiere')}, destiny='/animes_by_year')
    addMenuItem({'name': AutoTranslate.language('Search animes'), 'description': '', 'iconimage': get_icon('search')}, destiny='/search_anime')
    end()
    setview('WideList')

@route('/search_movies')
def search_movies(param=None):
    param = param or {}
    search = param.get('search') if 'search' in param else input_text(heading=AutoTranslate.language('Search movies'))
    if not search:
        return
    page = int(param.get('page', 1))
    total_pages, results = httpclient.search_movie_api(search, page)
    setcontent('movies')
    for movie in results:
        title = movie.get('title') or movie.get('name')
        year = movie.get('release_date', '')[:4] or movie.get('first_air_date', '')[:4]
        display_name = f"{title} ({year})" if year else title
        icon = f"https://image.tmdb.org/t/p/w500{movie.get('poster_path')}" if movie.get('poster_path') else get_icon('movies')
        fanart = f"https://image.tmdb.org/t/p/original{movie.get('backdrop_path')}" if movie.get('backdrop_path') else ''
        description = movie.get('overview', '')
        original_name = movie.get('original_title', '')
        
        addMenuItem({
            'name': display_name,
            'video_id': str(movie['id']),
            'year': year,
            'iconimage': icon,
            'fanart': fanart,
            'description': description,
            'movie_name': title,
            'original_name': original_name,
            'playable': 'true'
        }, destiny='/play_resolve_movies', folder=False)
    if page < total_pages:
        addMenuItem({
            'name': f"[B]{AutoTranslate.language('Page')} {page+1} {AutoTranslate.language('of')} {total_pages}[/B]",
            'iconimage': get_icon('next'),
            'search': search,
            'page': str(page + 1)
        }, destiny='/search_movies')
    end()
    setview('List')

@route('/search_tvshows')
def search_tvshows(param=None):
    param = param or {}
    search = param.get('search') if 'search' in param else input_text(heading=AutoTranslate.language('Search tv shows'))
    if not search:
        return
    page = int(param.get('page', 1))
    total_pages, results = httpclient.search_tvshow_api(search, page)
    setcontent('tvshows')
    for show in results:
        title = show.get('title') or show.get('name')
        year = show.get('release_date', '')[:4] or show.get('first_air_date', '')[:4]
        display_name = f"{title} ({year})" if year else title
        icon = f"https://image.tmdb.org/t/p/w500{show.get('poster_path')}" if show.get('poster_path') else get_icon('series')
        fanart = f"https://image.tmdb.org/t/p/original{show.get('backdrop_path')}" if show.get('backdrop_path') else ''
        description = show.get('overview', '')
        original_name = show.get('original_name', '')
        addMenuItem({
            'name': display_name,
            'video_id': str(show['id']),
            'iconimage': icon,
            'fanart': fanart,
            'description': description,
            'serie_name': title,
            'original_name': original_name
        }, destiny='/tvshow_season')
    if page < total_pages:
        addMenuItem({
            'name': f"[B]{AutoTranslate.language('Page')} {page+1} {AutoTranslate.language('of')} {total_pages}[/B]",
            'iconimage': get_icon('next'),
            'search': search,
            'page': str(page + 1)
        }, destiny='/search_tvshows')
    end()
    setview('List')

@route('/search_anime')
def search_anime(param=None):
    param = param or {}
    search = param.get('search') if 'search' in param else input_text(heading=AutoTranslate.language('Search animes'))
    if not search:
        return
    page = int(param.get('page', 1))
    total_pages, results = httpclient.search_anime_api(search, page)
    setcontent('tvshows')
    for anime in results:
        title = anime.get('title_english') or anime.get('title')
        year = str(anime.get('year') or '')
        display_name = f"{title} ({year})" if year else title
        icon = anime.get('images', {}).get('jpg', {}).get('large_image_url') or get_icon('animes')
        fanart = icon
        description = anime.get('synopsis', '')
        addMenuItem({
            'name': display_name,
            'mal_id': str(anime['mal_id']),
            'iconimage': icon,
            'fanart': fanart,
            'description': description,
            'is_anime': 'true',
            'anime_name': title
        }, destiny='/anime_episodes')
    if page < total_pages:
        addMenuItem({
            'name': f"[B]{AutoTranslate.language('Page')} {page+1} {AutoTranslate.language('of')} {total_pages}[/B]",
            'iconimage': get_icon('next'),
            'search': search,
            'page': str(page + 1)
        }, destiny='/search_anime')
    end()
    setview('List')

@route('/popular_movies')
def popular_movies(param=None):
    param = param or {}
    page = int(param.get('page', 1))
    total_pages, results = httpclient.movies_popular_api(page)
    if results:
        setcontent('movies')
        for movie in results:
            title = movie.get('title') or movie.get('name')
            year = movie.get('release_date', '')[:4] or movie.get('first_air_date', '')[:4]
            icon = f"https://image.tmdb.org/t/p/w500{movie.get('poster_path')}" if movie.get('poster_path') else get_icon('movies')
            fanart = f"https://image.tmdb.org/t/p/original{movie.get('backdrop_path')}" if movie.get('backdrop_path') else ''
            description = movie.get('overview', '')
            original_name = movie.get('original_title', '')
            video_id = str(movie['id'])
            
            addMenuItem({
                'name': title,
                'video_id': video_id,
                'year': year,
                'iconimage': icon,
                'fanart': fanart,
                'description': description,
                'movie_name': title,
                'original_name': original_name,
                
                'playable': 'true'
            }, destiny='/play_resolve_movies', folder=False)
        if page < total_pages:
            addMenuItem({
                'name': f"[B]{AutoTranslate.language('Page')} {page+1} {AutoTranslate.language('of')} {total_pages}[/B]",
                'iconimage': get_icon('next'),
                'page': str(page + 1)
            }, destiny='/popular_movies')
        end()
        setview('List')

@route('/trending_movies')
def trending_movies(param=None):
    param = param or {}
    page = int(param.get('page', 1))
    total_pages, results = httpclient.movies_api(page, 'trending')
    if results:
        setcontent('movies')
        for movie in results:
            title = movie.get('title') or movie.get('name')
            year = movie.get('release_date', '')[:4] or movie.get('first_air_date', '')[:4]
            icon = f"https://image.tmdb.org/t/p/w500{movie.get('poster_path')}" if movie.get('poster_path') else get_icon('movies')
            fanart = f"https://image.tmdb.org/t/p/original{movie.get('backdrop_path')}" if movie.get('backdrop_path') else ''
            description = movie.get('overview', '')
            original_name = movie.get('original_title', '')
            video_id = str(movie['id'])
            
            addMenuItem({
                'name': title,
                'video_id': video_id,
                'year': year,
                'iconimage': icon,
                'fanart': fanart,
                'description': description,
                'movie_name': title,
                'original_name': original_name,
                
                'playable': 'true'
            }, destiny='/play_resolve_movies', folder=False)
        if page < total_pages:
            addMenuItem({
                'name': f"[B]{AutoTranslate.language('Page')} {page+1} {AutoTranslate.language('of')} {total_pages}[/B]",
                'iconimage': get_icon('next'),
                'page': str(page + 1)
            }, destiny='/trending_movies')
        end()
        setview('List')

@route('/premiere_movies')
def premiere_movies(param=None):
    param = param or {}
    page = int(param.get('page', 1))
    total_pages, results = httpclient.movies_api(page, 'premiere')
    if results:
        setcontent('movies')
        for movie in results:
            title = movie.get('title') or movie.get('name')
            year = movie.get('release_date', '')[:4] or movie.get('first_air_date', '')[:4]
            icon = f"https://image.tmdb.org/t/p/w500{movie.get('poster_path')}" if movie.get('poster_path') else get_icon('movies')
            fanart = f"https://image.tmdb.org/t/p/original{movie.get('backdrop_path')}" if movie.get('backdrop_path') else ''
            description = movie.get('overview', '')
            original_name = movie.get('original_title', '')
            video_id = str(movie['id'])
            
            addMenuItem({
                'name': title,
                'video_id': video_id,
                'year': year,
                'iconimage': icon,
                'fanart': fanart,
                'description': description,
                'movie_name': title,
                'original_name': original_name,
                
                'playable': 'true'
            }, destiny='/play_resolve_movies', folder=False)
        if page < total_pages:
            addMenuItem({
                'name': f"[B]{AutoTranslate.language('Page')} {page+1} {AutoTranslate.language('of')} {total_pages}[/B]",
                'iconimage': get_icon('next'),
                'page': str(page + 1)
            }, destiny='/premiere_movies')
        end()
        setview('List')

@route('/popular_tvshows')
def popular_tvshows(param=None):
    param = param or {}
    page = int(param.get('page', 1))
    total_pages, results = httpclient.tv_shows_popular_api(page)
    if results:
        setcontent('tvshows')
        for show in results:
            title = show.get('title') or show.get('name')
            year = show.get('release_date', '')[:4] or show.get('first_air_date', '')[:4]
            icon = f"https://image.tmdb.org/t/p/w500{show.get('poster_path')}" if show.get('poster_path') else get_icon('series')
            fanart = f"https://image.tmdb.org/t/p/original{show.get('backdrop_path')}" if show.get('backdrop_path') else ''
            description = show.get('overview', '')
            original_name = show.get('original_name', '')
            addMenuItem({
                'name': title,
                'video_id': str(show['id']),
                'year': year,
                'iconimage': icon,
                'fanart': fanart,
                'description': description,
                'serie_name': title,
                'original_name': original_name,
                
            }, destiny='/tvshow_season')
        if page < total_pages:
            addMenuItem({
                'name': f"[B]{AutoTranslate.language('Page')} {page+1} {AutoTranslate.language('of')} {total_pages}[/B]",
                'iconimage': get_icon('next'),
                'page': str(page + 1)
            }, destiny='/popular_tvshows')
        end()
        setview('List')

@route('/trending_tvshows')
def trending_tvshows(param=None):
    param = param or {}
    page = int(param.get('page', 1))
    total_pages, results = httpclient.tv_shows_trending_api(page)
    if results:
        setcontent('tvshows')
        for show in results:
            title = show.get('title') or show.get('name')
            year = show.get('release_date', '')[:4] or show.get('first_air_date', '')[:4]
            icon = f"https://image.tmdb.org/t/p/w500{show.get('poster_path')}" if show.get('poster_path') else get_icon('series')
            fanart = f"https://image.tmdb.org/t/p/original{show.get('backdrop_path')}" if show.get('backdrop_path') else ''
            description = show.get('overview', '')
            original_name = show.get('original_name', '')
            addMenuItem({
                'name': title,
                'video_id': str(show['id']),
                'year': year,
                'iconimage': icon,
                'fanart': fanart,
                'description': description,
                'serie_name': title,
                'original_name': original_name,
                
            }, destiny='/tvshow_season')
        if page < total_pages:
            addMenuItem({
                'name': f"[B]{AutoTranslate.language('Page')} {page+1} {AutoTranslate.language('of')} {total_pages}[/B]",
                'iconimage': get_icon('next'),
                'page': str(page + 1)
            }, destiny='/trending_tvshows')
        end()
        setview('List')

@route('/premiere_tvshows')
def premiere_tvshows(param=None):
    param = param or {}
    page = int(param.get('page', 1))
    total_pages, results = httpclient.tv_shows_premiere_api(page)
    if results:
        setcontent('tvshows')
        for show in results:
            title = show.get('title') or show.get('name')
            year = show.get('release_date', '')[:4] or show.get('first_air_date', '')[:4]
            icon = f"https://image.tmdb.org/t/p/w500{show.get('poster_path')}" if show.get('poster_path') else get_icon('series')
            fanart = f"https://image.tmdb.org/t/p/original{show.get('backdrop_path')}" if show.get('backdrop_path') else ''
            description = show.get('overview', '')
            original_name = show.get('original_name', '')
            addMenuItem({
                'name': title,
                'video_id': str(show['id']),
                'year': year,
                'iconimage': icon,
                'fanart': fanart,
                'description': description,
                'serie_name': title,
                'original_name': original_name,
                
            }, destiny='/tvshow_season')
        if page < total_pages:
            addMenuItem({
                'name': f"[B]{AutoTranslate.language('Page')} {page+1} {AutoTranslate.language('of')} {total_pages}[/B]",
                'iconimage': get_icon('next'),
                'page': str(page + 1)
            }, destiny='/premiere_tvshows')
        end()
        setview('List')

@route('/popular_anime')
def popular_anime(param=None):
    param = param or {}
    page = int(param.get('page', 1))
    total_pages, results = httpclient.animes_popular_api(page)
    setcontent('tvshows')
    for anime in results:
        title = anime.get('title_english') or anime.get('title')
        year = str(anime.get('year') or '')
        icon = anime.get('images', {}).get('jpg', {}).get('large_image_url') or get_icon('animes')
        fanart = icon
        description = anime.get('synopsis', '')
        addMenuItem({
            'name': title,
            'mal_id': str(anime['mal_id']),
            'year': year,
            'iconimage': icon,
            'fanart': fanart,
            'description': description,
            'is_anime': 'true',
            'anime_name': title
        }, destiny='/anime_episodes')
    if page < total_pages:
        addMenuItem({
            'name': f"[B]{AutoTranslate.language('Page')} {page+1} {AutoTranslate.language('of')} {total_pages}[/B]",
            'iconimage': get_icon('next'),
            'page': str(page + 1)
        }, destiny='/popular_anime')
    end()
    setview('List')

@route('/airing_anime')
def airing_anime(param=None):
    param = param or {}
    page = int(param.get('page', 1))
    total_pages, results = httpclient.animes_airing_api(page)
    setcontent('tvshows')
    for anime in results:
        title = anime.get('title_english') or anime.get('title')
        year = str(anime.get('year') or '')
        icon = anime.get('images', {}).get('jpg', {}).get('large_image_url') or get_icon('animes')
        fanart = icon
        description = anime.get('synopsis', '')
        addMenuItem({
            'name': title,
            'mal_id': str(anime['mal_id']),
            'year': year,
            'iconimage': icon,
            'fanart': fanart,
            'description': description,
            'is_anime': 'true',
            'anime_name': title
        }, destiny='/anime_episodes')
    if page < total_pages:
        addMenuItem({
            'name': f"[B]{AutoTranslate.language('Page')} {page+1} {AutoTranslate.language('of')} {total_pages}[/B]",
            'iconimage': get_icon('next'),
            'page': str(page + 1)
        }, destiny='/airing_anime')
    end()
    setview('List')

@route('/animes_by_year')
def animes_by_year(param=None):
    param = param or {}
    current_year = datetime.now().year
    setcontent('videos')
    for year in range(current_year, 1962, -1):
        addMenuItem({
            'name': str(year),
            'iconimage': get_icon('premiere'),
            'year': str(year)
        }, destiny='/animes_seasons')
    end()
    setview('WideList')

@route('/animes_seasons')
def animes_seasons(param):
    param = param or {}
    year = param.get('year', '')
    seasons = [
        ('winter', AutoTranslate.language('Winter')),
        ('spring', AutoTranslate.language('Spring')),
        ('summer', AutoTranslate.language('Summer')),
        ('fall', AutoTranslate.language('Fall'))
    ]
    setcontent('videos')
    for season_key, season_name in seasons:
        addMenuItem({
            'name': f'{season_name} {year}',
            'iconimage': get_icon('animes'),
            'anime_season': season_key,
            'year': year
        }, destiny='/animes_by_season')
    end()
    setview('WideList')

@route('/animes_by_season')
def animes_by_season(param):
    param = param or {}
    anime_season = param.get('anime_season', '')
    year = param.get('year', '')
    page = int(param.get('page', 1))
    
    try:
        total_pages, results = httpclient.animes_by_season_api(year, anime_season, page)
        setcontent('tvshows')
        
        for anime in results:
            title = anime.get('title_english') or anime.get('title')
            year_anime = str(anime.get('year') or '')
            icon = anime.get('images', {}).get('jpg', {}).get('large_image_url') or get_icon('animes')
            fanart = icon
            description = anime.get('synopsis', '')
            
            addMenuItem({
                'name': title,
                'mal_id': str(anime['mal_id']),
                'year': year_anime,
                'iconimage': icon,
                'fanart': fanart,
                'description': description,
                'is_anime': 'true',
                'anime_name': title
            }, destiny='/anime_episodes')

        if page < total_pages:
            addMenuItem({
                'name': f"[B]{AutoTranslate.language('Page')} {page+1} {AutoTranslate.language('of')} {total_pages}[/B]",
                'iconimage': get_icon('next'),
                'anime_season': anime_season,
                'year': year,
                'page': str(page + 1)
            }, destiny='/animes_by_season')

        addMenuItem({
            'name': f'[COLOR grey][ {AutoTranslate.language("Voltar às estações")} ][/COLOR]',
            'iconimage': get_icon('back'),
            'year': year,
        }, destiny='/animes_seasons')

        end()
        setview('List')
        
    except:
        pass

@route('/play_resolve_movies')
def play_resolve_movies(param):
    param = param or {}
    video_id = param.get('video_id', '')
    year = param.get('year', '')
    movie_name = param.get('movie_name', '')
    iconimage = param.get('iconimage', get_icon('movies'))
    fanart = param.get('fanart', '')
    description = param.get('description', '')
    
    try:
        show_src = httpclient.open_movie_api(video_id)
        if not movie_name:
            movie_name = show_src.get('title', '')
        imdb = show_src.get('external_ids', {}).get('imdb_id', '')
        original_name = show_src.get('original_title', '')
        
        menus_links = sources.movie_content(imdb, year)
        
        if not menus_links:
            notify(AutoTranslate.language("No sources available"))
            return
        
        if is_auto_play_enabled():
            success = auto_play_preferred_language(
                None, imdb, year, None, None, 
                movie_name, iconimage, fanart, description
            )
            if success:
                return
        
        items_options = [option for option, link in menus_links]
        
        op2 = xbmcgui.Dialog().select(
            AutoTranslate.language('Select a player'), 
            items_options
        )
        
        if op2 >= 0:
            selected_url = menus_links[op2][1]
            
            try:
                decoded = unquote(selected_url)
                parsed = urlparse(decoded)
                qs = parse_qs(parsed.query)
                final_url = qs.get('url', [decoded])[0] or qs.get('u', [decoded])[0] or decoded
                
                stream, sub = sources.select_resolver_movie(final_url)
                
                if not stream:
                    notify(AutoTranslate.language("Stream unavailable"))
                    return
                
                stop_player()
                
                play_item = xbmcgui.ListItem(path=stream)
                play_item.setArt({'thumb': iconimage, 'icon': iconimage, 'fanart': fanart})
                play_item.setContentLookup(False)
                
                if KODI_MAJOR >= 20:
                    info_tag = play_item.getVideoInfoTag()
                    info_tag.setTitle(movie_name)
                    info_tag.setPlot(description)
                    info_tag.setMediaType('movie')
                    if year:
                        info_tag.setYear(int(year))
                    if original_name:
                        info_tag.setOriginalTitle(original_name)
                else:
                    info_dict = {
                        'title': movie_name,
                        'plot': description,
                        'mediatype': 'movie'
                    }
                    if imdb:
                        info_dict['imdbnumber'] = imdb
                    if year:
                        info_dict['year'] = int(year)
                    if original_name:
                        info_dict['originaltitle'] = original_name
                    play_item.setInfo('video', info_dict)
                
                if sub:
                    play_item.setSubtitles([sub])
                
                xbmcplugin.setResolvedUrl(int(sys.argv[1]), True, play_item)
            except:
                notify(AutoTranslate.language('Error trying to play'))
    except:
        notify(AutoTranslate.language('Error'))

@route('/tvshow_season')
def tvshow_season(param):
    param = param or {}
    video_id = param.get('video_id', '')
    year = param.get('year', '')
    serie_name = param.get('serie_name', '')
    
    try:
        show_src = httpclient.open_season_api(video_id)
        if not serie_name:
            serie_name = show_src.get('name', '')
        iconimage = f"https://image.tmdb.org/t/p/w500{show_src.get('poster_path')}" if show_src.get('poster_path') else get_icon('series')
        fanart = f"https://image.tmdb.org/t/p/original{show_src.get('backdrop_path')}" if show_src.get('backdrop_path') else ''
        imdb = show_src.get('external_ids', {}).get('imdb_id', '')
        original_name = show_src.get('original_name', '')
        
        seasons = show_src.get('seasons', [])
        setcontent('tvshows')
        for season in seasons:
            season_num = season.get('season_number')
            if season_num == 0:
                continue
            season_name = f"{season_num}ª {AutoTranslate.language('Season')}"
            season_icon = f"https://image.tmdb.org/t/p/w500{season.get('poster_path')}" if season.get('poster_path') else iconimage
            
            addMenuItem({
                'name': season_name,
                'iconimage': season_icon,
                'fanart': fanart,
                'description': season.get('overview', ''),
                'video_id': video_id,
                'season_num': str(season_num),
                'year': year,
                'serie_name': serie_name,
                'imdbnumber': imdb,
                'original_name': original_name
            }, destiny='/open_episodes')
        end()
        setview('List')
    except:
        pass

@route('/anime_episodes')
def anime_episodes(param):
    param = param or {}
    mal_id = param.get('mal_id', '')
    year = param.get('year', '')
    anime_name = param.get('anime_name', '')
    iconimage = param.get('iconimage', get_icon('animes'))
    is_anime = param.get('is_anime', 'true')

    try:
        show_src = httpclient.open_anime_api(mal_id).get('data', {})
        if not anime_name:
            anime_name = show_src.get('title_english') or show_src.get('title', '')
        description = show_src.get('synopsis', '')
        episodes = httpclient.open_anime_episodes_api(mal_id)
        anime_type = show_src.get('type', '')
        fanart = iconimage

        if anime_type == 'Movie':
            setcontent('movies')
            addMenuItem({
                'name': anime_name,
                'mal_id': mal_id,
                'video_title': anime_name,
                'iconimage': iconimage,
                'fanart': fanart,
                'description': description,
                'year': year,
                'is_anime': is_anime,
                'playable': 'true'
            }, destiny='/play_resolve_anime_movies', folder=False)
            end()
            return

        setcontent('episodes')
        today = datetime.today().date()
        for episode in episodes:
            aired = episode.get('aired')
            if aired:
                try:
                    air_date_obj = datetime.strptime(aired.split('T')[0], "%Y-%m-%d").date()
                    if air_date_obj > today:
                        continue
                except:
                    pass
            epnum = episode.get('mal_id')
            ep_name = episode.get('title') or f"{anime_name} {epnum}"
            icon = episode.get('images', {}).get('jpg', {}).get('image_url') or iconimage
            name = f"{int(epnum):02d} - {ep_name}"
            addMenuItem({
                'name': name,
                'description': episode.get('synopsis') or description,
                'iconimage': icon,
                'fanart': fanart,
                'mal_id': mal_id,
                'year': year,
                'episode_num': str(epnum),
                'video_title': f"{anime_name} - {ep_name}",
                'is_anime': is_anime,
                'playable': 'true'
            }, destiny='/play_resolve_animes', folder=False)
        end()
    except:
        notify(AutoTranslate.language("Failed to load details"))

@route('/open_episodes')
def open_episodes(param):
    param = param or {}
    video_id = param.get('video_id', '')
    season_num = param.get('season_num', '')
    year = param.get('year', '')
    serie_name = param.get('serie_name', '')
    imdb = param.get('imdbnumber', '')
    original_name = param.get('original_name', '')
    
    try:
        show_src = httpclient.open_season_api(video_id)
        if not serie_name:
            serie_name = show_src.get('name', '')
        if not imdb:
            imdb = show_src.get('external_ids', {}).get('imdb_id', '')
        
        src = httpclient.show_episode_api(video_id, season_num)
        
        iconimage = f"https://image.tmdb.org/t/p/w500{show_src.get('poster_path')}" if show_src.get('poster_path') else get_icon('series')
        
        today = datetime.now().date()
        
        setcontent('episodes')
        for episode in src.get('episodes', []):
            air_date = episode.get('air_date')
            if air_date:
                try:
                    air_date_obj = datetime.strptime(air_date, "%Y-%m-%d").date()
                    if air_date_obj > today:
                        continue
                except:
                    pass
            
            episode_num = str(episode.get('episode_number'))
            ep_name = episode.get('name', f"{serie_name} {episode_num}")
            icon = f"https://image.tmdb.org/t/p/w500{episode.get('still_path')}" if episode.get('still_path') else get_icon('series')
            fanart = f"https://image.tmdb.org/t/p/original{episode.get('backdrop_path')}" if episode.get('backdrop_path') else ''
            description = episode.get('overview', show_src.get('overview', ''))
            
            addMenuItem({
                'name': f"{int(season_num)}x{int(episode_num):02d} - {ep_name}",
                'description': description,
                'iconimage': icon,
                'fanart': fanart,
                'video_id': video_id,
                'year': year,
                'season_num': season_num,
                'episode_num': episode_num,
                'imdbnumber': imdb,
                'serie_name': serie_name,
                'original_name': original_name,
                'episode_title': ep_name,
                'video_title': f"{serie_name} - {ep_name}",
                
                'playable': 'true'
            }, destiny='/play_resolve_tvshows', folder=False)
        end()
    except:
        pass

@route('/play_resolve_tvshows')
def play_resolve_tvshows(param):
    param = param or {}
    imdb = param.get('imdbnumber', '')
    year = param.get('year', '')
    season_num = param.get('season_num', '')
    episode_num = param.get('episode_num', '')
    video_title = param.get('video_title', '')
    iconimage = param.get('iconimage', '')
    fanart = param.get('fanart', '')
    description = param.get('description', '')
    serie_name = param.get('serie_name', '')
    original_name = param.get('original_name', '')
    
    if is_auto_play_enabled():
        success = auto_play_preferred_language(
                None, imdb, year, season_num, episode_num, 
                video_title, iconimage, fanart, description
            )
        if success:
            return
    
    menus_links = sources.show_content(imdb, year, season_num, episode_num)
    
    if not menus_links:
        notify(AutoTranslate.language("No sources available"))
        return
    
    items_options = [option for option, link in menus_links]
    
    op2 = xbmcgui.Dialog().select(
        AutoTranslate.language('Select a player'), 
        items_options
    )
    
    if op2 >= 0:
        selected_url = menus_links[op2][1]
        
        try:
            decoded = unquote(selected_url)
            parsed = urlparse(decoded)
            qs = parse_qs(parsed.query)
            final_url = qs.get('url', [decoded])[0] or qs.get('u', [decoded])[0] or decoded
            
            stream, sub = sources.select_resolver_tvshow(final_url, season_num, episode_num)
            
            if not stream:
                notify(AutoTranslate.language("Stream unavailable"))
                return
            
            stop_player()
            
            showtitle = video_title.split(" - ")[0] if " - " in video_title else (serie_name or video_title)
            episode_title = video_title.split(" - ")[1] if " - " in video_title else video_title
            
            play_item = xbmcgui.ListItem(path=stream)
            play_item.setArt({'thumb': iconimage, 'icon': iconimage, 'fanart': fanart})
            play_item.setContentLookup(False)
            
            if KODI_MAJOR >= 20:
                info_tag = play_item.getVideoInfoTag()
                info_tag.setTitle(episode_title)
                info_tag.setTvShowTitle(showtitle)
                info_tag.setPlot(description)
                info_tag.setMediaType('episode')
            else:
                info_dict = {
                    'title': episode_title,
                    'tvshowtitle': showtitle,
                    'plot': description,
                    'mediatype': 'episode'
                }
                if imdb:
                    info_dict['imdbnumber'] = imdb
                if original_name:
                    info_dict['originaltitle'] = original_name
                play_item.setInfo('video', info_dict)
            
            if sub:
                play_item.setSubtitles([sub])
            
            xbmcplugin.setResolvedUrl(int(sys.argv[1]), True, play_item)
        except:
            notify(AutoTranslate.language('Error trying to play'))

@route('/play_resolve_animes')
def play_resolve_animes(param):
    param = param or {}
    mal_id = param.get('mal_id', '')
    year = param.get('year', '')
    episode_num = param.get('episode_num', '')
    video_title = param.get('video_title', '')
    iconimage = param.get('iconimage', '')
    fanart = param.get('fanart', iconimage)
    description = param.get('description', '')
    is_anime = param.get('is_anime', 'true')
    
    if not mal_id or not episode_num:
        notify(AutoTranslate.language("Missing required parameters"))
        return
    
    try:
        episode_num = int(episode_num)
    except:
        notify(AutoTranslate.language("Invalid episode number"))
        return
    
    if is_auto_play_enabled():
        success = auto_play_preferred_language(
            mal_id, None, year, None, episode_num, 
            video_title, iconimage, fanart, description, 
            is_anime=is_anime
        )
        if success:
            return
    
    menus_links = sources.show_content_anime(mal_id, episode_num)
    
    if not menus_links:
        notify(AutoTranslate.language("No sources available"))
        return
    
    items_options = [option for option, link in menus_links]
    
    op2 = xbmcgui.Dialog().select(
        AutoTranslate.language('Select a player'), 
        items_options
    )
    
    if op2 >= 0:
        selected_url = menus_links[op2][1]
        
        try:
            decoded = unquote(selected_url)
            parsed = urlparse(decoded)
            qs = parse_qs(parsed.query)
            final_url = qs.get('url', [decoded])[0] or qs.get('u', [decoded])[0] or decoded
            
            stream, sub = sources.select_resolver_anime(final_url, episode_num)
            
            if not stream:
                notify(AutoTranslate.language("Stream unavailable"))
                return
            
            stop_player()
            
            showtitle = video_title.split(" - ")[0] if " - " in video_title else video_title
            episode_title = video_title.split(" - ")[1] if " - " in video_title else f"{AutoTranslate.language('Episode')} {episode_num}"
            
            play_item = xbmcgui.ListItem(path=stream)
            play_item.setArt({'thumb': iconimage, 'icon': iconimage, 'fanart': fanart})
            play_item.setContentLookup(False)
            
            if KODI_MAJOR >= 20:
                info_tag = play_item.getVideoInfoTag()
                info_tag.setTitle(episode_title)
                info_tag.setTvShowTitle(showtitle)
                info_tag.setPlot(description)
                info_tag.setMediaType('episode')
            else:
                info_dict = {
                    'title': episode_title,
                    'tvshowtitle': showtitle,
                    'plot': description,
                    'mediatype': 'episode'
                }
                play_item.setInfo('video', info_dict)
            
            if sub:
                play_item.setSubtitles([sub])
            
            xbmcplugin.setResolvedUrl(int(sys.argv[1]), True, play_item)
        except:
            notify(AutoTranslate.language('Error trying to play'))

@route('/play_resolve_anime_movies')
def play_resolve_anime_movies(param):
    param = param or {}
    mal_id = param.get('mal_id', '')
    year = param.get('year', '')
    video_title = param.get('video_title', '')
    iconimage = param.get('iconimage', '')
    fanart = param.get('fanart', iconimage)
    description = param.get('description', '')
    is_anime = param.get('is_anime', 'true')

    if is_auto_play_enabled():
        auto_play_preferred_language(
            mal_id, None, year, None, None,
            video_title, iconimage, fanart, description,
            is_anime=is_anime
        )
        return

    menus_links = sources.movie_content_anime(mal_id)
    if not menus_links:
        return

    items = [i[0] for i in menus_links]
    op = xbmcgui.Dialog().select(AutoTranslate.language('Select a player'), items)
    if op < 0:
        return

    url = menus_links[op][1]
    decoded = unquote(url)
    parsed = urlparse(decoded)
    qs = parse_qs(parsed.query)
    final_url = qs.get('url', [decoded])[0] or qs.get('u', [decoded])[0] or decoded

    stream, sub = sources.select_resolver_anime_movie(final_url)
    if not stream:
        return

    stop_player()
    item = xbmcgui.ListItem(path=stream)
    item.setArt({'thumb': iconimage, 'icon': iconimage, 'fanart': fanart})

    if KODI_MAJOR >= 20:
        tag = item.getVideoInfoTag()
        tag.setTitle(video_title)
        tag.setPlot(description)
        tag.setMediaType('movie')
        if year:
            tag.setYear(int(year))
    else:
        item.setInfo('video', {
            'title': video_title,
            'plot': description,
            'mediatype': 'movie',
            'year': int(year) if year else None
        })

    if sub:
        item.setSubtitles([sub])

    xbmcplugin.setResolvedUrl(int(sys.argv[1]), True, item)