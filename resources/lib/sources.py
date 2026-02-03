import os
import sys
import re

try:
    from resources.lib.autotranslate import AutoTranslate
except:
    pass

try:
    from resources.lib.helper import progress_six
    progress = progress_six
except:
    progress = None

try:
    addonId = re.search('plugin://(.+?)/', str(sys.argv[0])).group(1)
except:
    addonId = 'plugin.video.thethunder'

try:
    from kodi_six import xbmcvfs
    translate = xbmcvfs.translatePath
    scrapers = translate(f'special://home/addons/{addonId}/resources/lib/scrapers/')
except:
    dir_path = os.path.dirname(os.path.realpath(__file__))
    scrapers = os.path.join(dir_path, "scrapers")

try:
    import xbmcaddon
    addon_instance = xbmcaddon.Addon(id=addonId)
except:
    addon_instance = None

def import_scripts(pasta):
    scripts = [f[:-3] for f in os.listdir(pasta) if f.endswith(".py") and f != "__init__.py"]
    modulos = []
    sys.path.append(pasta)  

    for script in scripts:
        source_enabled = True
        if addon_instance:
            try:
                if script == 'assistirbiz' and addon_instance.getSetting('source_assistirbiz') != 'true':
                    source_enabled = False
                elif script == 'animesup' and addon_instance.getSetting('source_animesup') != 'true':
                    source_enabled = False
                elif script == 'animesdigital' and addon_instance.getSetting('source_animesdigital') != 'true':
                    source_enabled = False
                elif script == 'cinevibehd' and addon_instance.getSetting('source_cinevibehd') != 'true':
                    source_enabled = False
                elif script == 'goflix' and addon_instance.getSetting('source_goflix') != 'true':
                    source_enabled = False
                elif script == 'hinatasoul' and addon_instance.getSetting('source_hinatasoul') != 'true':
                    source_enabled = False
                elif script == 'netcine' and addon_instance.getSetting('source_netcine') != 'true':
                    source_enabled = False
                elif script == 'overflix' and addon_instance.getSetting('source_overflix') != 'true':
                    source_enabled = False
            except:
                pass

        if source_enabled:
            try:
                if sys.version_info.major == 3:
                    import importlib
                    modulo = importlib.import_module(script)  
                else:
                    modulo = __import__(script)
                modulos.append(modulo)
            except Exception as e:
                pass

    return modulos

modules_import = import_scripts(scrapers) if scrapers else []

ANIME_SOURCES = ['animesup', 'animesdigital', 'hinatasoul']
NON_ANIME_SOURCES = ['assistirbiz', 'cinevibehd', 'goflix', 'netcine', 'overflix']

def get_anime_scrapers():
    return [m for m in modules_import if m.__name__ in ANIME_SOURCES]

def get_non_anime_scrapers():
    return [m for m in modules_import if m.__name__ in NON_ANIME_SOURCES]

def search_movies(imdb, year):
    dp = None
    try:
        if progress:
            dp = progress()
            dp.create(AutoTranslate.language('Please wait...'), AutoTranslate.language('find_source'))
    except:
        pass    
    
    stream_movies = []
    non_anime_scrapers = get_non_anime_scrapers()
    
    for n, modulo in enumerate(non_anime_scrapers):
        try:
            count = n + 1
            update = int(count / len(non_anime_scrapers) * 100) if non_anime_scrapers else 0
            result = modulo.source.search_movies(imdb, year)
            if result:
                stream_movies.append(result)
            
            if dp:
                try:
                    dp.update(update, str(modulo.WEBSITE))
                except:
                    pass
        except:
            continue
    
    streams_final = []
    if stream_movies:
        for streams in stream_movies:
            if streams:
                for s in streams:
                    name, page = s
                    streams_final.append((name, page))
    
    if dp:
        try:
            dp.close()
        except:
            pass
    
    return streams_final

def search_tvshows(imdb, year, season, episode):
    dp = None
    try:
        if progress:
            dp = progress()
            dp.create(AutoTranslate.language('Please wait...'), AutoTranslate.language('find_source'))
    except:
        pass
    
    stream_tvshows = []
    non_anime_scrapers = get_non_anime_scrapers()
    
    for n, modulo in enumerate(non_anime_scrapers):
        try:
            count = n + 1
            update = int(count / len(non_anime_scrapers) * 100) if non_anime_scrapers else 0
            result = modulo.source.search_tvshows(imdb, year, season, episode)
            if result:
                stream_tvshows.append(result)
            
            if dp:
                try:
                    dp.update(update, str(modulo.WEBSITE))
                except:
                    pass
        except:
            continue
    
    streams_final = []
    if stream_tvshows:
        for streams in stream_tvshows:
            if streams:
                for s in streams:
                    name, page = s
                    streams_final.append((name, page))
    
    if dp:
        try:
            dp.close()
        except:
            pass
    
    return streams_final

def movie_content(imdb, year):
    return search_movies(imdb, year)

def show_content(imdb, year, season, episode):
    return search_tvshows(imdb, year, season, episode)

def search_anime_episodes(mal_id, episode):
    """Busca episódios de anime"""
    dp = None
    try:
        if progress:
            dp = progress()
            dp.create(AutoTranslate.language('Please wait...'), AutoTranslate.language('find_source'))
    except:
        pass
    
    stream_animes = []
    anime_scrapers = get_anime_scrapers()
    
    for n, modulo in enumerate(anime_scrapers):
        try:
            count = n + 1
            update = int(count / len(anime_scrapers) * 100) if anime_scrapers else 0
            
            if hasattr(modulo.source, 'search_animes'):
                result = modulo.source.search_animes(mal_id, episode)
                if result:
                    stream_animes.append(result)
            
            if dp:
                try:
                    dp.update(update, str(modulo.WEBSITE))
                except:
                    pass
        except:
            continue
    
    streams_final = []
    for streams in stream_animes:
        if streams:
            for s in streams:
                name, page = s
                streams_final.append((name, page))
    
    if dp:
        try:
            dp.close()
        except:
            pass
    
    return streams_final

def search_anime_movies(mal_id):
    """Busca filmes de anime"""
    dp = None
    try:
        if progress:
            dp = progress()
            dp.create(AutoTranslate.language('Please wait...'), AutoTranslate.language('find_source'))
    except:
        pass
    
    stream_animes = []
    anime_scrapers = get_anime_scrapers()
    
    for n, modulo in enumerate(anime_scrapers):
        try:
            count = n + 1
            update = int(count / len(anime_scrapers) * 100) if anime_scrapers else 0
            
            if hasattr(modulo.source, 'search_animes'):
                result = modulo.source.search_animes(mal_id, None)
                if result:
                    stream_animes.append(result)
            
            if dp:
                try:
                    dp.update(update, str(modulo.WEBSITE))
                except:
                    pass
        except:
            continue
    
    streams_final = []
    for streams in stream_animes:
        if streams:
            for s in streams:
                name, page = s
                streams_final.append((name, page))
    
    if dp:
        try:
            dp.close()
        except:
            pass
    
    return streams_final

def search_animes(mal_id, episode):
    """
    Busca animes (episódios ou filmes) baseado no mal_id.
    Se episode é None, busca filme de anime.
    Se episode é especificado, busca episódio de anime.
    """
    if episode is None:
        return search_anime_movies(mal_id)
    else:
        return search_anime_episodes(mal_id, episode)

def show_content_anime(mal_id, episode):
    """Busca episódios de anime"""
    return search_anime_episodes(mal_id, episode)

def movie_content_anime(mal_id):
    """Busca filmes de anime"""
    return search_anime_movies(mal_id)

def resolve_movies(url):
    stream = ''
    sub = ''
    for modulo in get_non_anime_scrapers():
        if not stream:
            try:
                source = modulo.source.resolve_movies(url)
                if len(source) > 0:
                    stream = source[0][0]
                    sub = source[0][1]
                    break
            except:
                continue
    return stream, sub

def resolve_tvshows(url):
    stream = ''
    sub = ''
    for modulo in get_non_anime_scrapers():
        if not stream:
            try:
                source = modulo.source.resolve_tvshows(url)
                if len(source) > 0:
                    stream = source[0][0]
                    sub = source[0][1]
                    break
            except:
                continue
    return stream, sub

def resolve_animes(url):
    stream = ''
    sub = ''
    for modulo in get_anime_scrapers():
        if not stream:
            try:
                if hasattr(modulo.source, 'resolve_animes'):
                    source = modulo.source.resolve_animes(url)
                    if len(source) > 0:
                        stream = source[0][0]
                        sub = source[0][1]
                        break
            except:
                continue
    return stream, sub

def resolve_anime_movies(url):
    stream = ''
    sub = ''
    for modulo in get_anime_scrapers():
        if not stream:
            try:
                if hasattr(modulo.source, 'resolve_animes_movies'):
                    source = modulo.source.resolve_animes_movies(url)
                    if len(source) > 0:
                        stream = source[0][0]
                        sub = source[0][1]
                        break
            except:
                continue
    return stream, sub

def select_resolver_movie(url):
    return resolve_movies(url)

def select_resolver_tvshow(url, season, episode):
    return resolve_tvshows(url)

def select_resolver_anime(url, episode):
    return resolve_animes(url)

def select_resolver_anime_movie(url):
    return resolve_anime_movies(url)