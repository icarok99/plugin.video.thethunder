import xbmc
import xbmcgui
import xbmcvfs
import xbmcaddon
import os
import sys
import urllib.request
import zipfile
import shutil

# Inicializar addon de forma robusta
try:
    _addon = xbmcaddon.Addon()
except RuntimeError:
    # Se falhar (executado fora do contexto normal), usar ID explícito
    _addon = xbmcaddon.Addon('plugin.video.thethunder')

def getString(string_id):
    try:
        return _addon.getLocalizedString(string_id)
    except:
        # Fallback para strings em inglês caso as localizadas não estejam disponíveis
        strings = {
            30802: 'Downloading',
            30803: 'Extracting',
            30804: 'Installation complete',
            30805: 'Error',
            30806: 'Installation failed',
            30807: 'ResolveURL has been successfully installed. Please restart Kodi.',
            30808: 'ResolveURL Installer'
        }
        return strings.get(string_id, '')

def download_and_install(url, name):
    dialog = xbmcgui.DialogProgress()
    dialog.create(getString(30808), '{} {}...'.format(getString(30802), name))
    
    xbmc.log(f"ResolveURL Installer: Starting download from {url}", xbmc.LOGINFO)

    addon_path = xbmcvfs.translatePath('special://home/addons/')
    temp_zip = os.path.join(addon_path, 'temp_resolveurl.zip')

    correct_path = os.path.join(addon_path, 'script.module.resolveurl.fork')
    wrong_path = os.path.join(addon_path, 'script.module.resolveurl-main')

    try:
        # Download do arquivo
        xbmc.log(f"ResolveURL Installer: Downloading to {temp_zip}", xbmc.LOGINFO)
        urllib.request.urlretrieve(url, temp_zip)
        dialog.update(50, getString(30803))
        xbmc.log("ResolveURL Installer: Download complete, extracting...", xbmc.LOGINFO)

        # Remover instalações antigas
        if os.path.exists(correct_path):
            xbmc.log(f"ResolveURL Installer: Removing old installation at {correct_path}", xbmc.LOGINFO)
            shutil.rmtree(correct_path)

        if os.path.exists(wrong_path):
            xbmc.log(f"ResolveURL Installer: Removing old installation at {wrong_path}", xbmc.LOGINFO)
            shutil.rmtree(wrong_path)

        # Extrair arquivo
        with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
            zip_ref.extractall(addon_path)
        xbmc.log("ResolveURL Installer: Extraction complete", xbmc.LOGINFO)

        # Renomear se necessário
        if os.path.exists(wrong_path):
            xbmc.log(f"ResolveURL Installer: Renaming {wrong_path} to {correct_path}", xbmc.LOGINFO)
            os.rename(wrong_path, correct_path)

        # Limpar arquivo temporário
        if os.path.exists(temp_zip):
            os.remove(temp_zip)
            xbmc.log("ResolveURL Installer: Temporary file removed", xbmc.LOGINFO)

        dialog.update(100, getString(30804))
        xbmc.log("ResolveURL Installer: Installation successful", xbmc.LOGINFO)
        
        xbmcgui.Dialog().ok(
            getString(30808),
            getString(30807)
        )

    except Exception as e:
        error_msg = str(e)
        xbmc.log(f"ResolveURL Installer ERROR: {error_msg}", xbmc.LOGERROR)
        import traceback
        xbmc.log(traceback.format_exc(), xbmc.LOGERROR)
        
        xbmcgui.Dialog().ok(getString(30805), '{}:\n{}'.format(getString(30806), error_msg))

    finally:
        dialog.close()

def update():
    url = 'https://github.com/icarok99/script.module.resolveurl/archive/refs/heads/main.zip'
    xbmc.log(f"ResolveURL Installer: update() called with URL: {url}", xbmc.LOGINFO)
    download_and_install(url, 'ResolveURL')

if __name__ == '__main__':
    xbmc.log(f"ResolveURL Installer: Script started with args: {sys.argv}", xbmc.LOGINFO)
    
    if len(sys.argv) > 1:
        action = sys.argv[1]
        xbmc.log(f"ResolveURL Installer: Action requested: {action}", xbmc.LOGINFO)
        
        if action == 'update':
            update()
        else:
            xbmc.log(f"ResolveURL Installer: Unknown action: {action}", xbmc.LOGWARNING)
    else:
        xbmc.log("ResolveURL Installer: No action specified, defaulting to update", xbmc.LOGINFO)
        update()