#!/usr/bin/env python
# -*- coding: utf-8 -*-

import HTMLParser
import os
import re
import sys
import urllib
import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin

from resources.lib.pbs import (PBS, PBSSettings)
import constants as c

import web_pdb

class PBSAddon:

    def __init__(self):
        self.settings = None
        self.pbs = None

        self.addon = xbmcaddon.Addon('plugin.video.pbs')
        self.addonName = self.addon.getAddonInfo('name')
        self.l10n = self.addon.getLocalizedString
        self.homeDir = self.addon.getAddonInfo('path').decode(c.UTF8)
        self.addonIcon = xbmc.translatePath(self.addon.getAddonInfo('icon')).decode(c.UTF8)
        self.addonFanart = xbmc.translatePath(self.addon.getAddonInfo('fanart')).decode(c.UTF8)

        self.default_vid_stream = {
            'codec': 'h264',
            'width': 1280,
            'height': 720,
            'aspect': 1.78,
        }
        self.default_aud_stream = {
            'codec': 'aac',
            'language': 'en',
        }
        self.default_sub_stream = {
            'language': 'en',
        }

        self.alpha = True
        self.enable_login = False
        self.username = None
        self.password = None
        self.cj_file = None

        self.get_settings()
        self.start_pbs()
        self.save_settings()

        self.process_addon_event()

        return

    def get_settings(self):
        profile = self.addon.getAddonInfo('profile').decode(c.UTF8)
        pro_dir = xbmc.translatePath(profile).decode(c.UTF8)

        if not os.path.isdir(pro_dir):
            os.makedirs(pro_dir)

        self.cj_file = xbmc.translatePath(os.path.join(profile, 'PBSCookies.dat')).decode(c.UTF8)

        self.alpha = self.addon.getSetting('alpha')
        self.enable_login = self.addon.getSetting('enable_login')
        self.username = self.addon.getSetting('login_name')
        self.password = self.addon.getSetting('login_pass')

        return

    def save_settings(self):
        # save the settings to the addon settings
        return

    def start_pbs(self):
        self.settings = PBSSettings(self.alpha, self.enable_login, self.username, self.password, self.cj_file)
        self.pbs = PBS(self.settings)
        return

    # mode=None
    def get_genre_items(self, _, i_list):
        items = self.pbs.get_genres()

        for item in items.get('items', []):
            i_list = self.add_menu_item(item['title'], 'GS', i_list, '{!s}|0'.format(item['id']))

        return i_list

    # mode = GS
    def get_show_items(self, data, i_list):
        genre, page = data.split('|')
        page = int(page)

        if 'watchlist' == genre:
            return self.get_watchlist_items(1, i_list)

        items = self.pbs.get_shows(genre, page)

        for item in items.get('items', []):
            i_list = self.add_show_items(i_list, item, 'favorites' == genre)

        if items.get('page', 1) < items.get('pages', 1):
            # some of the URLs return 1-indexed pages, and some don't
            # fix any that do here
            # the ones that don't are fixed in the PBS class methods that return the data
            if items.get('page0', False):
                page += 1

            # Next Page
            i_list = self.add_menu_item(self.l10n(30050), 'GS', i_list, '{}|{!s}'.format(genre, page))

        return i_list

    # mode = GY
    def get_season_items(self, data, i_list):
        show_slug = data

        items = self.pbs.get_seasons(show_slug)

        if 1 < len(items.get('items', [])):
            for item in items.get('items', []):
                i_list = self.add_menu_item(item['title'], 'GE', i_list, '{}|{}|0'.format(show_slug, item['cid']))

        else:
            # there may only be specials
            return self.get_specials_items('{}|{!s}'.format(show_slug, 0), i_list)

        return i_list

    # mode = GP
    def get_specials_items(self, data, i_list):
        show_slug, page = data.split('|')
        page = int(page)

        items = self.pbs.get_specials(show_slug, 0)

        # return the episodes (specials)
        for item in items.get('items', []):
            i_list = self.add_video_item(i_list, item)

        if items.get('has_next', False):
            i_list = self.add_menu_item(self.l10n(30050), 'GP', i_list,
                                        '{}|{!s}'.format(show_slug, page + 1))

        return i_list

    # mode = GE
    def get_episode_items(self, data, i_list):
        show_slug, season_cid, page = data.split('|')
        page = int(page)

        items = self.pbs.get_episodes(show_slug, season_cid, page)

        for item in items.get('items', []):
            i_list = self.add_video_item(i_list, item)

        if items.get('has_next', False):
            i_list = self.add_menu_item(self.l10n(30050), 'GE', i_list,
                                        '{}|{}|{!s}'.format(show_slug, season_cid, page + 1))

        return i_list

    # mode = GW
    def get_watchlist_items(self, data, i_list):
        page = int(data)

        items = self.pbs.get_fav_videos(page)

        for item in items.get('items', []):
            i_list = self.add_video_item(i_list, item, remove=True)

        if items.get('has_next', False):
            i_list = self.add_menu_item(self.l10n(30050), 'GW', i_list, str(page + 1))

        return i_list

    # mode = GV
    def start_show(self, video_media_id):
        resp = self.pbs.get_video(video_media_id)

        if resp.get('error', ''):
            xbmc.executebuiltin('XBMC.Notification("{}", "{}", {})'.format(self.addonName, self.l10n(30049), 4000))
            return

        li = xbmcgui.ListItem(path=resp['video_url'])

        if resp.get('subs_url', None) is not None:
            sub_file = self.convert_subtitles(resp['subs_url'])
            li.setSubtitles([sub_file])

        if '.m3u8' in resp.get('video_url'):
            li.setProperty('inputstreamaddon', 'inputstream.adaptive')
            li.setProperty('inputstream.adaptive.manifest_type', 'hls')

        xbmcplugin.setResolvedUrl(int(sys.argv[1]), True, li)

    # mode = DF
    def do_function(self, data):
        func, url = data.split('|')
        add = ('A' == func[1:2])

        msg = 'Not Attempted'
        if 'P' == func[:1]:  # programs ???
            msg = self.pbs.update_fav_program(add, url)
        elif 'S' == func[:1]:  # shows, like Nova or Nature
            msg = self.pbs.update_fav_shows(add, url)
        elif 'V' == func[:1]:  # videos, like individual episodes of shows
            msg = self.pbs.update_fav_videos(add, url)

        xbmc.executebuiltin('XBMC.Notification("%s", "%s", %s)' % (self.addonName, msg, 4000))

    def convert_subtitles(self, sub_url):
        sub_file = ''
        if sub_url != '':
            profile = self.addon.getAddonInfo('profile').decode(c.UTF8)
            pro_dir = xbmc.translatePath(os.path.join(profile))
            if not os.path.isdir(pro_dir):
                os.makedirs(pro_dir)

            pg = self.pbs.get_request(False, sub_url)
            if pg != '':
                try:
                    sub_file = xbmc.translatePath(os.path.join(profile, 'subtitles.srt'))
                    o_file = open(sub_file, 'w+')

                    captions = re.compile('<p begin="(.+?)" end="(.+?)">(.+?)</p>', re.DOTALL).findall(pg)
                    for idx, (c_start, c_end, caption) in list(enumerate(captions, start=1)):
                        c_start = c_start.replace('.', ',')
                        c_end = c_end.replace('.', ',').split('"', 1)[0]
                        caption = caption.replace('<br/>', '\n').strip()

                        try:
                            caption = HTMLParser.HTMLParser().unescape(caption)
                        except:
                            pass

                        caption = caption.replace('&apos;', "'").replace('\n\n', '\n')
                        o_file.write('{}\n{} --> {}\n{}\n\n'.format(idx, c_start, c_end, caption))
                    o_file.close()
                except:
                    sub_file = ''

        return sub_file

    def add_menu_item(self, name, mode, i_list=None, url=None, thumb=None, fanart=None, video_info=None,
                      video_stream=None, audio_stream=None, subtitle_stream=None, cm=None, is_folder=True):
        if i_list is None:
            i_list = []

        if thumb is None:
            thumb = self.addonIcon

        if fanart is None:
            fanart = self.addonFanart

        if video_info is None:
            video_info = {}

        if video_stream is None:
            video_stream = self.default_vid_stream

        if audio_stream is None:
            audio_stream = self.default_aud_stream

        if subtitle_stream is None:
            subtitle_stream = self.default_sub_stream

        liz = xbmcgui.ListItem(name)
        liz.setArt({'thumb': thumb, 'fanart': fanart})
        liz.setInfo('Video', video_info)
        liz.addStreamInfo('video', video_stream)
        liz.addStreamInfo('audio', audio_stream)
        liz.addStreamInfo('subtitle', subtitle_stream)

        if cm is not None:
            liz.addContextMenuItems(cm)

        if not is_folder:
            liz.setProperty('isPlayable', 'true')

        u = '{}?mode={}'.format(sys.argv[0], mode)

        if url is not None:
            u = u + '&url={}'.format(urllib.quote_plus(str(url)))

        i_list.append((u, liz, is_folder))

        return i_list

    def get_addon_params(self):
        try:
            params = dict(arg.split('=') for arg in ((sys.argv[2][1:]).split('&')))
            for key in params:
                try:
                    params[key] = urllib.unquote_plus(params[key]).decode(c.UTF8)
                except:
                    pass
        except:
            params = {}

        return params.get

    def log(self, txt):
        try:
            message = '{}: {}'.format(self.addonName, txt.encode('ascii', 'ignore'))
            xbmc.log(msg=message, level=xbmc.LOGDEBUG)
        except:
            pass

    def process_addon_event(self):
        p = self.get_addon_params()
        mode = p('mode', None)

        if mode is None:
            self.proc_dir(self.get_genre_items, p('url'), 'genres', 'default_view')

        elif mode == 'GS':
            self.proc_dir(self.get_show_items, p('url'), 'tvshows', 'default_view')

        elif mode == 'GY':
            self.proc_dir(self.get_season_items, p('url'), 'seasons', 'default_view')

        elif mode == 'GP':
            self.proc_dir(self.get_specials_items, p('url'), 'tvshows', 'default_view')

        elif mode == 'GE':
            self.proc_dir(self.get_episode_items, p('url'), 'tvshows', 'default_view')

        elif mode == 'GW':
            self.proc_dir(self.get_watchlist_items, p('url'), 'movies', 'default_view')

        elif mode == 'GV':
            self.start_show(p('url'))

        elif mode == 'DF':
            web_pdb.set_trace()
            self.do_function(p('url'))

        return p

    def proc_dir(self, dir_func, url, content_type='files', view_type='default_view', cache=True):
        i_list = []

        xbmcplugin.setContent(int(sys.argv[1]), content_type)
        xbmcplugin.addSortMethod(int(sys.argv[1]), xbmcplugin.SORT_METHOD_UNSORTED)
        xbmcplugin.addSortMethod(int(sys.argv[1]), xbmcplugin.SORT_METHOD_TITLE)
        xbmcplugin.addSortMethod(int(sys.argv[1]), xbmcplugin.SORT_METHOD_EPISODE)

        i_list = dir_func(url, i_list)
        if len(i_list) > 0:
            xbmcplugin.addDirectoryItems(int(sys.argv[1]), i_list, len(i_list))

            if self.addon.getSetting('enable_views') == 'true':
                xbmc.executebuiltin('Container.SetViewMode({})'.format(self.addon.getSetting(view_type)))

            xbmcplugin.endOfDirectory(int(sys.argv[1]), cacheToDisc=cache)

    def add_show_items(self, i_list, item, remove=False):
        info = {
            'TVShowTitle': item['title'],
            'Title': item['title'],
            'Studio': item.get('producer'),
            'Episode': item.get('video_count'),
            'Plot': item.get('description'),
        }
        genres = item.get('genre_titles')
        if genres != [] and genres is not None:
            info['Genre'] = genres[0]

        image = item.get('image', None)

        context_menu = None
        if item.get('cid') is not None:
            cid = item['cid']

            url = 'SR' if remove else 'SA'
            lang = 30006 if remove else 30007
            context_menu = [(self.l10n(lang), 'XBMC.RunPlugin({}?mode=DF&url={}%7C{})'.format(sys.argv[0], url, cid))]

        i_list = self.add_menu_item(item['title'], 'GY', i_list, str(item['slug']), image, image, info, cm=context_menu)

        return i_list

    def add_video_item(self, i_list, item, remove=False):
        if item.get('tp_media_id') is None:
            xbmc.executebuiltin('XBMC.Notification("%s", "%s", %s)' % (self.addonName, self.l10n(30053), 4000))

        description = ''
        if item.get('expire_date', None) is not None:
            description += 'Expires: {}\n'.format(re.compile(r'^(\d{4}-\d{2}-\d{2})')
                                                  .search(item['expire_date']).group(1))
        description += item.get('description', '')

        info = {
            'episode': item.get('episode', ''),
            'season': item.get('season', ''),
            'plot': description,
            'title': item.get('title', ''),
            'duration': item.get('duration', 0),
            'premiered': re.compile(r'^(\d{4}-\d{2}-\d{2})').search(item.get('premiere_date', '')).group(1),
            'tvshowtitle': item.get('show_title', ''),
            'mediatype': item.get('type', ''),
            'year': re.compile(r'^(\d{4})').search(item.get('premiere_date', '')).group(1),
        }

        image = item.get('image', None)

        context_menu = None
        if item.get('cid') is not None:
            cid = item['cid']

            url = 'VR' if remove else 'VA'
            lang = 30009 if remove else 30008
            context_menu = [(self.l10n(lang), 'XBMC.RunPlugin({}?mode=DF&url={}%7C{})'.format(sys.argv[0], url, cid))]

        i_list = self.add_menu_item(item['title'], 'GV', i_list, str(item['tp_media_id']), image, image, info,
                                    cm=context_menu, is_folder=False)

        return i_list

# end
