# resources/lib/update.py
# -*- coding: utf-8 -*-
'''
Atualização automática do TheThunder - Branch: main
Agora com exclusão automática de scrapers removidos
'''

import os
import json
import glob
import xbmc
import xbmcvfs
import xbmcaddon
from urllib.request import urlopen, Request
from contextlib import closing

ADDON = xbmcaddon.Addon()
ADDON_PATH = ADDON.getAddonInfo("path")
SCRAPERS_PATH = xbmcvfs.translatePath(os.path.join(ADDON_PATH, "resources", "lib", "scrapers"))
LIB_PATH = xbmcvfs.translatePath(os.path.join(ADDON_PATH, "resources", "lib"))
RESOURCES_PATH = xbmcvfs.translatePath(os.path.join(ADDON_PATH, "resources"))

# Arquivo local que guarda a data da última atualização
LOCAL_VERSION = os.path.join(SCRAPERS_PATH, ".update")

# Tudo agora da branch main
BRANCH = "main"
BASE_URL = f"https://raw.githubusercontent.com/icarok99/plugin.video.thethunder/{BRANCH}/"
REMOTE_VERSION_URL = BASE_URL + "last_update.txt"
RAW_SCRAPERS = BASE_URL + "resources/lib/scrapers/"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

def log(msg):
    xbmc.log(f"[TheThunder AutoUpdate - {BRANCH}] {msg}", xbmc.LOGINFO)

def http_get(url, binary=False):
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT})
        with closing(urlopen(req, timeout=15)) as r:
            data = r.read()
            return data if binary else data.decode("utf-8").strip()
    except Exception as e:
        log(f"Erro ao baixar {url}: {e}")
        return None

def get_local_version():
    if not xbmcvfs.exists(LOCAL_VERSION):
        return None
    try:
        with open(LOCAL_VERSION, "r", encoding="utf-8") as f:
            return f.read().strip()
    except:
        return None

def save_local_version(ver):
    try:
        with open(LOCAL_VERSION, "w", encoding="utf-8") as f:
            f.write(ver)
    except:
        pass

def get_remote_version():
    return http_get(REMOTE_VERSION_URL)

def list_remote_scrapers():
    tree_url = f"https://api.github.com/repos/icarok99/plugin.video.thethunder/git/trees/{BRANCH}?recursive=1"
    tree = http_get(tree_url)
    if not tree:
        return []
    try:
        data = json.loads(tree)
        files = []
        for item in data.get("tree", []):
            if item["path"].startswith("resources/lib/scrapers/") and item["type"] == "blob":
                fname = os.path.basename(item["path"])
                if fname not in ["__init__.py", ".update"]:
                    files.append(fname)
        return files
    except Exception as e:
        log(f"Erro ao ler tree do GitHub: {e}")
        return []

# Arquivos extras que sempre serão atualizados
ADDITIONAL_FILES = [
    {"remote": "resources/lib/sources.py",   "local": os.path.join(LIB_PATH, "sources.py")},
    {"remote": "resources/settings.xml",     "local": os.path.join(RESOURCES_PATH, "settings.xml")},
]

def auto_update():
    remote_version = get_remote_version()
    if not remote_version:
        log("Não foi possível obter versão remota")
        return False

    local_version = get_local_version()

    if local_version == remote_version:
        log("Tudo já está atualizado")
        return False

    log(f"Nova versão disponível: {remote_version}")

    updated = 0

    # 1. Scrapers (com exclusão automática dos removidos)
    remote_scrapers = list_remote_scrapers()

    # Lista arquivos locais (só .py na pasta scrapers)
    local_pattern = os.path.join(SCRAPERS_PATH, "*.py")
    local_scrapers = [os.path.basename(f) for f in glob.glob(local_pattern)]
    local_scrapers = [f for f in local_scrapers if f not in ["__init__.py", ".update"]]

    # Baixa/atualiza os que existem no repositório
    for fname in remote_scrapers:
        url = f"{RAW_SCRAPERS}{fname}"
        content = http_get(url, binary=True)
        if content is not None:
            dest = os.path.join(SCRAPERS_PATH, fname)
            try:
                with open(dest, "wb") as f:
                    f.write(content)
                updated += 1
                log(f"Scraper atualizado/adicionado: {fname}")
                if fname in local_scrapers:
                    local_scrapers.remove(fname)
            except Exception as e:
                log(f"Erro ao salvar scraper {fname}: {e}")

    # Remove os que sobraram (foram excluídos do repositório)
    for fname in local_scrapers:
        try:
            os.remove(os.path.join(SCRAPERS_PATH, fname))
            log(f"Scraper removido (não existe mais): {fname}")
            updated += 1
        except Exception as e:
            log(f"Erro ao remover {fname}: {e}")

    # 2. Arquivos adicionais
    for file in ADDITIONAL_FILES:
        url = BASE_URL + file["remote"]
        content = http_get(url, binary=True)
        if content is not None:
            try:
                with open(file["local"], "wb") as f:
                    f.write(content)
                updated += 1
                log(f"Atualizado: {file['remote']}")
            except Exception as e:
                log(f"Erro ao salvar {file['remote']}: {e}")

    # Salva nova versão
    save_local_version(remote_version)
    log(f"Atualização concluída! {updated} alteração(ões) - versão {remote_version}")
    return True

# Executa automaticamente ao importar (ou chame manualmente)
if __name__ == "__main__":
    auto_update()
