# resolver.py
import resolveurl
import xbmc  # Para logs (opcional)

class Resolver:
    def resolverurls(self, url, referer=None):
        """
        Resolve a URL usando o módulo resolveurl do Kodi.
        
        :param url: URL que será resolvida para o stream final.
        :param referer: Referência do site (opcional, não usada aqui).
        :return: Tupla (stream_url, subtitles) onde subtitles é None por enquanto.
        """
        try:
            # Chama o resolveurl para tentar resolver o link
            stream_url = resolveurl.resolve(url)
            if stream_url:
                return stream_url, None
            else:
                return None, None
        except Exception as e:
            # Loga o erro no Kodi para facilitar debug
            xbmc.log(f"[resolver.py] Erro ao resolver URL: {str(e)}", xbmc.LOGERROR)
            return None, None
