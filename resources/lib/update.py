# resources/lib/update.py
# -*- coding: utf-8 -*-
'''
Atualização automática baseada em last_update.txt
Formato da data: DD/MM/YYYY
Arquivo local: .update
'''

import os
import json
import xbmc
import xbmcvfs
import xbmcaddon
from urllib.request import urlopen, Request
from contextlib import closing

ADDON = xbmcaddon.Addon()
ADDON_PATH = ADDON.getAddonInfo("path")
SCRAPERS_PATH = xbmcvfs.translatePath(os.path.join(ADDON_PATH, "resources", "lib", "scrapers"))

# Arquivo local com a data instalada
LOCAL_VERSION = os.path.join(SCRAPERS_PATH, ".update")

# Arquivo remoto com a data disponível
REMOTE_VERSION_URL = "https://raw.githubusercontent.com/icarok99/plugin.video.thethunder/refs/heads/main/last_update.txt"

# API para listar arquivos da pasta scrapers no repositório
REMOTE_TREE_URL = "https://api.github.com/repos/icarok99/plugin.video.thethunder/git/trees/main?recursive=1"

# Base para baixar os scrapers
RAW_BASE = "https://raw.githubusercontent.com/icarok99/plugin.video.thethunder/main/resources/lib/scrapers"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

def log(msg):
    xbmc.log(f"[TheThunder AutoUpdate] {msg}", xbmc.LOGINFO)

# -------------------------------
# Download HTTP
# -------------------------------
def http_get(url, binary=False):
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT})
        with closing(urlopen(req)) as r:
            data = r.read()
            return data if binary else data.decode("utf-8").strip()
    except Exception as e:
        log(f"Erro ao baixar {url}: {e}")
        return None

# -------------------------------
# Versão local
# -------------------------------
def get_local_version():
    if not xbmcvfs.exists(LOCAL_VERSION):
        return None
    try:
        with open(LOCAL_VERSION, "r") as f:
            return f.read().strip()
    except:
        return None

def save_local_version(ver):
    try:
        with open(LOCAL_VERSION, "w") as f:
            f.write(ver)
    except:
        pass

# -------------------------------
# Versão remota
# -------------------------------
def get_remote_version():
    return http_get(REMOTE_VERSION_URL)

# -------------------------------
# Lista arquivos remotos na pasta scrapers
# -------------------------------
def list_remote_scrapers():
    tree = http_get(REMOTE_TREE_URL)
    if not tree:
        return None

    try:
        data = json.loads(tree)
        files = []

        for item in data.get("tree", []):
            if item["path"].startswith("resources/lib/scrapers/") and item["type"] == "blob":
                fname = item["path"].split("/")[-1]
                # Ignorar arquivos que não devem ser atualizados
                if fname not in ["__init__.py", ".update"]:
                    files.append(fname)

        return files

    except Exception as e:
        log(f"Erro ao processar lista de arquivos: {e}")
        return None

# -------------------------------
# Atualização principal
# -------------------------------
def auto_update():
    remote_version = get_remote_version()
    if not remote_version:
        log("Falha ao obter versão remota")
        return False

    local_version = get_local_version()

    if local_version == remote_version:
        log("Scrapers já estão atualizados")
        return False

    log(f"Nova atualização encontrada: {remote_version}")

    files = list_remote_scrapers()
    if not files:
        log("Não foi possível listar os scrapers remotos")
        return False

    updated = 0

    for fname in files:
        url = f"{RAW_BASE}/{fname}"
        content = http_get(url, binary=True)

        if content:
            dest = os.path.join(SCRAPERS_PATH, fname)
            try:
                with open(dest, "wb") as f:
                    f.write(content)
                updated += 1
            except Exception as e:
                log(f"Erro ao salvar {fname}: {e}")

    if updated > 0:
        save_local_version(remote_version)
        log(f"{updated} scrapers atualizados para a versão {remote_version}")
    else:
        log("Nenhum scraper foi atualizado")

    return True
