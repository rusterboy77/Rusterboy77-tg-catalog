# -*- coding: utf-8 -*-
import xbmcgui
import xbmcaddon
import xbmc
import os


def _resolve_addon_icon(addon_id=None):
    try:
        if addon_id:
            addon = xbmcaddon.Addon(addon_id)
        else:
            addon = xbmcaddon.Addon()
        # Try common locations inside the addon folder (prefer direct paths)
        addon_path = addon.getAddonInfo('path') or ''
        candidates = [
            os.path.join(addon_path, 'icon.png'),
            os.path.join(addon_path, 'resources', 'media', 'icon.png'),
        ]

        # Also consider addon-declared icon (may be a special path)
        declared_icon = addon.getAddonInfo('icon')
        if declared_icon:
            try:
                tx = xbmc.translatePath(declared_icon)
                candidates.insert(0, tx)
            except Exception:
                candidates.insert(0, declared_icon)

        for p in candidates:
            try:
                if p and os.path.exists(p):
                    return p
            except Exception:
                continue
    except Exception:
        pass
    return ''


def notify(title, message, timeout=3000, icon=None, addon_id=None):
    """Mostrar notificación usando icono del addon por defecto si no se pasa.

    - `timeout` en milisegundos puede aceptarse o pasarse como entero.
    - Si la llamada a xbmcgui falla, intenta una llamada simplificada.
    """
    try:
        if not icon:
            icon = _resolve_addon_icon(addon_id)

        # xbmcgui expects timeout in milliseconds on many Kodi versions
        xbmcgui.Dialog().notification(title, message, icon, int(timeout))
    except Exception:
        try:
            xbmcgui.Dialog().notification(title, message)
        except Exception:
            # Fallback silencioso
            pass
