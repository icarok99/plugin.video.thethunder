import xbmc
import xbmcgui
import xbmcvfs
import os
import sys
import urllib.request
import zipfile
import shutil

def download_and_install(url, name):
    dialog = xbmcgui.DialogProgress()
    dialog.create('TheThunder', 'Baixando atualização do ' + name + '...')

    addon_path = xbmcvfs.translatePath('special://home/addons/')
    temp_zip = os.path.join(addon_path, 'temp_resolveurl.zip')

    correct_path = os.path.join(addon_path, 'script.module.resolveurl')
    wrong_path = os.path.join(addon_path, 'script.module.resolveurl-main')

    try:
        urllib.request.urlretrieve(url, temp_zip)
        dialog.update(50, 'Extraindo arquivos...')

        if os.path.exists(correct_path):
            shutil.rmtree(correct_path)

        if os.path.exists(wrong_path):
            shutil.rmtree(wrong_path)

        with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
            zip_ref.extractall(addon_path)

        if os.path.exists(wrong_path):
            os.rename(wrong_path, correct_path)

        os.remove(temp_zip)
        dialog.update(100, 'Atualização concluída!')
        xbmcgui.Dialog().ok(
            'TheThunder',
            'ResolveURL atualizado com sucesso!'
        )

    except Exception as e:
        xbmcgui.Dialog().ok('Erro', 'Falha ao atualizar ResolveURL:\n' + str(e))

    finally:
        dialog.close()

def update():
    url = 'https://github.com/icarok99/script.module.resolveurl/archive/refs/heads/main.zip'
    download_and_install(url, 'ResolveURL')

if __name__ == '__main__':
    if len(sys.argv) > 1:
        action = sys.argv[1]
        if action == 'update':
            update()
