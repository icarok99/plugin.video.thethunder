# -*- coding: utf-8 -*-
import os
import sys
import re
try:
    from resources.lib.autotranslate import AutoTranslate
except:
    pass
try:
    from kodi_helper import myAddon
    addonId = re.search('plugin://(.+?)/',str(sys.argv[0])).group(1)
    addon = myAddon(addonId)
    scrapers = addon.translate('special://home/addons/plugin.video.thethunder/resources/lib/scrapers/')
    progress = addon.progress_six
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
            if script == 'assistirbiz' and addon_instance.getSetting('source_assistirbiz') != 'true':
                source_enabled = False
            elif script == 'animesup' and addon_instance.getSetting('source_animesup') != 'true':
                source_enabled = False
            elif script == 'cinevibehd' and addon_instance.getSetting('source_cinevibehd') != 'true':
                source_enabled = False
            elif script == 'goflix' and addon_instance.getSetting('source_goflix') != 'true':
                source_enabled = False
            elif script == 'netcine' and addon_instance.getSetting('source_netcine') != 'true':
                source_enabled = False
            elif script == 'overflix' and addon_instance.getSetting('source_overflix') != 'true':
                source_enabled = False

        if source_enabled:
            if sys.version_info.major == 3:
                import importlib
                modulo = importlib.import_module(script)  
            else:
                modulo = __import__(script)
            modulos.append(modulo)

    return modulos

modules_import = import_scripts(scrapers)
total_sites = len(modules_import)

# Lista de scrapers que NÃO devem ser usados na busca de animes (são para filmes/séries live-action)
NON_ANIME_SOURCES = ['assistirbiz', 'cinevibehd', 'goflix', 'netcine', 'overflix']

def search_movies(imdb, year):
    try:
        dp = progress()
        dp.create(AutoTranslate.language('wait'), AutoTranslate.language('find_source'))
    except:
        pass    
    stream_movies = []
    for n, modulo in enumerate(modules_import):
        # Pular ANIMESUP em buscas de filmes normais
        if hasattr(modulo, 'WEBSITE') and modulo.WEBSITE == 'ANIMESUP':
            continue

        count = n + 1
        update = int(count / total_sites * 100)
        stream_movies.append(modulo.source.search_movies(imdb, year))
        try:
            dp.update(update, str(modulo.WEBSITE))
        except:
            pass        
    streams_final = []
    if stream_movies:
        for streams in stream_movies:
            if streams:
                for s in streams:
                    name, page = s
                    streams_final.append((name, page))
    return streams_final

def search_tvshows(imdb, year, season, episode):
    try:
        dp = progress()
        dp.create(AutoTranslate.language('wait'), AutoTranslate.language('find_source'))
    except:
        pass
    stream_tvshows = []
    for n, modulo in enumerate(modules_import):
        # Pular ANIMESUP em buscas de séries normais
        if hasattr(modulo, 'WEBSITE') and modulo.WEBSITE == 'ANIMESUP':
            continue

        count = n + 1
        update = int(count / total_sites * 100)
        stream_tvshows.append(modulo.source.search_tvshows(imdb, year, season, episode))
        try:
            dp.update(update, str(modulo.WEBSITE))
        except:
            pass
    streams_final = []
    if stream_tvshows:
        for streams in stream_tvshows:
            if streams:
                for s in streams:
                    name, page = s
                    streams_final.append((name, page))
    return streams_final

def show_content(imdb, year, season, episode):
    if not season and not episode:
        return search_movies(imdb, year)
    elif season and episode:
        return search_tvshows(imdb, year, season, episode)
    return []

def search_animes(mal_id, season=None, episode=None):
    try:
        dp = progress()
        dp.create(AutoTranslate.language('wait'), AutoTranslate.language('find_source'))
    except:
        pass
    
    stream_animes = []
    for n, modulo in enumerate(modules_import):
        # Pular scrapers que são exclusivamente para filmes/séries live-action
        module_name = modulo.__name__
        if module_name in NON_ANIME_SOURCES:
            continue

        count = n + 1
        update = int(count / total_sites * 100)
        
        if hasattr(modulo.source, 'search_animes'):
            result = modulo.source.search_animes(mal_id, season or '1', episode)
        else:
            result = modulo.source.search_tvshows(mal_id, None, season or '1', episode)
        
        stream_animes.append(result or [])
        
        try:
            dp.update(update, str(modulo.WEBSITE))
        except:
            pass
    
    streams_final = []
    for streams in stream_animes:
        if streams:
            for s in streams:
                name, page = s
                streams_final.append((name, page))
    return streams_final

def show_content_anime(mal_id, year, season=None, episode=None):
    return search_animes(mal_id, season, episode)

def resolve_movies(url):
    stream = ''
    sub = ''
    for modulo in modules_import:
        if not stream:
            source = modulo.source.resolve_movies(url)
            if len(source) > 0:
                stream = source[0][0]
                sub = source[0][1]
                break            
    return stream, sub

def resolve_tvshows(url):
    stream = ''
    sub = ''
    for modulo in modules_import:
        if not stream:
            source = modulo.source.resolve_tvshows(url)
            if len(source) > 0:
                stream = source[0][0]
                sub = source[0][1]
                break            
    return stream, sub

def select_resolver(url, season, episode):
    if not season and not episode:
        return resolve_movies(url)
    elif season and episode:
        return resolve_tvshows(url)      
    return None, None