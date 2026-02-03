# -*- coding: utf-8 -*-
import os
import sys
import re

# Importar apenas o necessário do helper
try:
    from kodi_six import xbmcvfs as xbmcvfs_
    xbmcvfs = xbmcvfs_
except:
    xbmcvfs = None

try:
    from resources.lib.helper import requests
except:
    import requests as requests

# Obter o addon ID do sys.argv
try:
    addonId = re.search('plugin://(.+?)/', str(sys.argv[0])).group(1)
except:
    addonId = 'plugin.video.thethunder'

# Definir o profile diretamente
try:
    if xbmcvfs:
        translate = xbmcvfs.translatePath
        profile = translate(f'special://profile/addon_data/{addonId}')
    else:
        profile = ''
except:
    profile = ''

# Criar diretório do profile se não existir
if profile and xbmcvfs:
    try:
        if not xbmcvfs.exists(profile):
            xbmcvfs.mkdir(profile)
    except:
        pass

cache_country = os.path.join(profile, 'country.txt') if profile else ''
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36'

def get_country():
    if cache_country and xbmcvfs and xbmcvfs.exists(cache_country):
        country = ''
        try:
            with open(cache_country, 'r') as f:
                country = f.read()
            return country
        except:
            pass
    
    try:
        ip = requests.get('https://api.ipify.org/', headers={'User-Agent': USER_AGENT}).text
        country = requests.get(
            f'https://ipinfo.io/widget/demo/{ip}',
            headers={'User-Agent': USER_AGENT, 'Referer': 'https://ipinfo.io/'}
        ).json().get('data', {}).get('country', '')
        
        if country and cache_country:
            try:
                with open(cache_country, 'w') as f:
                    f.write(country)
            except:
                pass
        else:
            country = 'unknow'
    except:
        country = 'unknow'
    
    return country


class AutoTranslate:
    country = get_country()

    @classmethod
    def language(cls, key):
        # BRASIL
        if cls.country == 'BR':
            return {
                'lang-api': 'pt-BR',
                'Movies': 'Filmes',
                'Tv shows': 'Séries',
                'Animes': 'Animes',
                'New movies': 'Novos filmes',
                'New tv shows': 'Novas séries',
                'Trending movies': 'Filmes em alta',
                'Trending tv shows': 'Séries em alta',
                'Popular movies': 'Filmes populares',
                'Popular tv shows': 'Séries populares',
                'Popular animes': 'Animes populares',
                'Season animes': 'Animes da temporada',
                'Animes by year of release': 'Animes por ano de lançamento',
                'Search': 'Pesquisar',
                'Search movies': 'Pesquisar filme',
                'Search tv shows': 'Pesquisar série',
                'Search animes': 'Pesquisar anime',
                'Page': 'Página ',
                'of': ' de ',
                'Portuguese': 'DUBLADO',
                'Portuguese2': 'Dublado',
                'English': 'LEGENDADO',
                'English2': 'Legendado',
                'Select a player': 'Selecione um reprodutor',
                'Please wait...': 'Por favor aguarde...',
                'find_source': 'Procurando nas fontes',
                'settings': 'Configurações',
                'donation': 'Doação',
                'Please enter a valid search term': 'Por favor insira um termo de pesquisa válido',
                'No sources available': 'Nenhuma fonte disponível',
                'Stream unavailable': 'Stream indisponível',
                'invalid_params': 'Parâmetros inválidos',
                'IMDb not found': 'IMDb não encontrado',
                'Failed to resolve link': 'Falha ao resolver link',
                'If you like this add-on, support via PIX above': 'Se você gostou deste add-on, apoie via PIX acima',
                'Press BACK to exit': 'Pressione VOLTAR para sair',
                'Error playing': 'Erro ao reproduzir',
                'Error trying to play': 'Erro ao tentar reproduzir',
                'Failed to load details': 'Falha ao carregar detalhes',
                'Specials': 'Especiais',
                'Season': 'Temporada',
                'Episode': 'Episódio',
                'Animes by year and season': 'Animes por ano e temporada',
                'Winter': 'Inverno',
                'Spring': 'Primavera',
                'Summer': 'Verão',
                'Fall': 'Outono',
            }.get(key, 'Unknow')

        # PORTUGAL
        elif cls.country == 'PT':
            return {
                'lang-api': 'pt-PT',
                'Movies': 'Filmes',
                'Tv shows': 'Séries',
                'Animes': 'Animes',
                'New movies': 'Novos filmes',
                'New tv shows': 'Novas séries',
                'Trending movies': 'Filmes em alta',
                'Trending tv shows': 'Séries em alta',
                'Popular movies': 'Filmes populares',
                'Popular tv shows': 'Séries populares',
                'Popular animes': 'Animes populares',
                'Season animes': 'Animes da temporada',
                'Animes by year of release': 'Animes por ano de lançamento',
                'Search': 'Pesquisar',
                'Search movies': 'Pesquisar filme',
                'Search tv shows': 'Pesquisar série',
                'Search animes': 'Pesquisar anime',
                'Page': 'Página ',
                'of': ' de ',
                'Portuguese': 'DUBLADO',
                'Portuguese2': 'Dublado',
                'English': 'LEGENDADO',
                'English2': 'Legendado',
                'Select a player': 'Selecione um reprodutor',
                'Please wait...': 'Por favor aguarde...',
                'find_source': 'Procurando nas fontes',
                'settings': 'Configurações',
                'donation': 'Doação',
                'Please enter a valid search term': 'Por favor insira um termo de pesquisa válido',
                'No sources available': 'Nenhuma fonte disponível',
                'Stream unavailable': 'Stream indisponível',
                'invalid_params': 'Parâmetros inválidos',
                'IMDb not found': 'IMDb não encontrado',
                'Failed to resolve link': 'Falha ao resolver link',
                'If you like this add-on, support via PIX above': 'Se você gostou deste add-on, apoie via PIX acima',
                'Press BACK to exit': 'Pressione VOLTAR para sair',
                'Error playing': 'Erro ao reproduzir',
                'Error trying to play': 'Erro ao tentar reproduzir',
                'Failed to load details': 'Falha ao carregar detalhes',
                'Specials': 'Especiais',
                'Season': 'Temporada',
                'Episode': 'Episódio',
                'Animes by year and season': 'Animes por ano e temporada',
                'Winter': 'Inverno',
                'Spring': 'Primavera',
                'Summer': 'Verão',
                'Fall': 'Outono',
            }.get(key, 'Unknow')

        # OUTROS PAÍSES → INGLÊS
        else:
            return {
                'lang-api': 'en-US',
                'Movies': 'Movies',
                'Tv shows': 'Tv shows',
                'Animes': 'Animes',
                'New movies': 'New movies',
                'New tv shows': 'New tv shows',
                'Trending movies': 'Trending movies',
                'Trending tv shows': 'Trending tv shows',
                'Popular movies': 'Popular movies',
                'Popular tv shows': 'Popular tv shows',
                'Popular animes': 'Popular animes',
                'Season animes': 'Season animes',
                'Animes by year of release': 'Animes by year of release',
                'Search': 'Search',
                'Search movies': 'Search movies',
                'Search tv shows': 'Search tv shows',
                'Search animes': 'Search anime',
                'Page': 'Page ',
                'of': ' of ',
                'Portuguese': 'PORTUGUESE',
                'Portuguese2': 'Portuguese',
                'English': 'ENGLISH',
                'English2': 'English',
                'Select a player': 'Select a player',
                'Please wait...': 'Please wait...',
                'find_source': 'Searching the sources',
                'settings': 'Settings',
                'donation': 'Donation',
                'Please enter a valid search term': 'Please enter a valid search term',
                'No sources available': 'No sources available',
                'Stream unavailable': 'Stream unavailable',
                'invalid_params': 'Invalid parameters',
                'IMDb not found': 'IMDb not found',
                'Failed to resolve link': 'Failed to resolve link',
                'If you like this add-on, support via PIX above': 'If you like this add-on, support via PIX above',
                'Press BACK to exit': 'Press BACK to exit',
                'Error playing': 'Error playing',
                'Error trying to play': 'Error trying to play',
                'Failed to load details': 'Failed to load details',
                'Specials': 'Specials',
                'Season': 'Season',
                'Episode': 'Episode',
                'Animes by year and season': 'Animes by year and season',
                'Winter': 'Winter',
                'Spring': 'Spring',
                'Summer': 'Summer',
                'Fall': 'Fall',
            }.get(key, 'Unknow')