# -*- coding: utf-8 -*-
# KodiAddon PBS ThinkTV
#
import time
import sys
import os
import re
import xbmc
import xbmcgui
import xbmcaddon
import xbmcplugin
import urllib
import urllib2
import zlib
import json
import HTMLParser
import cookielib

try:
    from urllib import quote  # Python 2.X
except ImportError:
    from urllib.parse import quote  # Python 3+

import web_pdb

h = HTMLParser.HTMLParser()
UTF8 = 'utf-8'
showsPerPage = 30  # number of shows returned per page by PBS

httpHeaders = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 6.3; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2272.101 Safari/537.36',
    'Accept': 'application/json,text/javascript,text/html,*/*',
    'Accept-Encoding': 'gzip,deflate,sdch',
    'Accept-Language': 'en-US,en;q=0.8',
}

'''
URL CONSTANTS
'''

#
# HTML PAGES
#

ROOT_URL = r'http://www.pbs.org'
# The PBS root URL (non-secure)

ROOTS_URL = r'https://www.pbs.org'
# The PBS root URL (secure)

SHOWS_URL = ROOT_URL + r'/shows'
# A user-facing page (for collecting tokens)

PATH_URL = ROOTS_URL + r'%s'
# A generic URL (for dynamically creating URLs)
# @param string path the rest of the URL

ACCOUNT_URL = r'https://account.pbs.org'
# The root PBS account URL

OAUTH_LOGIN_URL = ACCOUNT_URL + r'/oauth2/login/'
# The OAuth login URL

AUTH_CLIENT_URL = ACCOUNT_URL + r'/oauth2/authorize/?scope=account+vvpa&redirect_uri=' \
                  + ROOTS_URL + r'/login/&response_type=code&client_id=%s&confirmed=1'
# The OAuth response URL
# @param client_id the client id

SHOWS_HTML_URL = ROOTS_URL + r'/shows/?genre=%s&title=&station=%s&alphabetically=true&layout=grid'  # (genre, pbsol)
# The user-facing shows URL (for referer)
# @param string genre from the genre block of the SHOWS_JSON_URL response
# @param string pbsol the pbsol.station value from the COOKIE_URL response

#
# JSON PAGES
#

COOKIE_URL = r'https://localization.services.pbs.org/localize/auto/cookie/'
# returns the cookie data needed for a proper station

SHOWS_JSON_URL = ROOTS_URL + r'/shows-page/%s/?stationId=%s&genre=%s&title=%s&source=%s&alphabetically=%s'
# Returns the list of shows with the given filters
# @param int page the page number (0-indexed)
# @param string station_id the pbsol.station_id value from the COOKIE_URL response
# @param string genre from the genre block of the SHOWS_JSON_URL response
# @param string title query for searching in titles
# @param string source (all, local-only, passport-library)
# @param string alpha alphabetize the list, or sort by most popular (true=alpha | false=popular)

PERSONAL_URL = ROOTS_URL + r'/personal'
# Returns personal data about the current user

STATION_SEARCH = ROOTS_URL + r'/search-videos/?page=%s&q=%s&rank=relevance&station_id=%s'
# Run a generic search for shows
# @param int page the page number (1-indexed)
# @param string query the string to search for
# @param string station_id the pbsol.station_id value from the COOKIE_URL response

ADD_FAV_VIDEO = ROOTS_URL + r'/profile/addFavoriteVideo/%s/'
REMOVE_FAV_VIDEO = ROOTS_URL + r'/profile/removeFavoriteVideo/%s/'
# Add or remove a single video to the fav list
# @param string video_cid the cid from the SHOWS_JSON_URL response

ADD_FAV_SHOW = ROOTS_URL + r'/profile/addFavoriteShow/%s/'
REMOVE_FAV_SHOW = ROOTS_URL + r'/profile/removeFavoriteShow/%s/'
# Add or remove a whole show to the fav list
# @param string show_cid the cid from the SHOWS_JSON_URL response

ADD_FAV_PROGRAM = ROOTS_URL + r'/profile/addFavoriteProgram/%s/'
REMOVE_FAV_PROGRAM = ROOTS_URL + r'/profile/removeFavoriteProgram/%s/'
# Add or remove a program to the fav list
# @param string program_cid the cid from the SHOWS_JSON_URL response

PLAYER_URL = r'https://player.pbs.org/viralplayer/%s/?uid=%s'
# ???

FAV_SHOWS_URL = ROOTS_URL + r'/favorite-shows-page/%s/'
# The list of favorite shows
# @param int page the page number (1-indexed)

FAV_VIDEOS_URL = ROOTS_URL + r'/watchlist/page/%s/'
# The list of favorite videos
# @param int page the page number (1-indexed)

SEASONS_LIST_URL = ROOTS_URL + r'/show/%s/seasons-list/'
# The list of seasons that a given show has
# @param string the show slug from the SHOWS_JSON_URL response

EPISODES_LIST_URL = ROOTS_URL + r'/show/%s/seasons/%s/episodes/?start=0&limit=24'
# The list of episodes that a given show has in a given season
# @param string the show slug from the SEASONS_LIST_URL response
# @param string the season cid from the SEASONS_LIST_URL response

VIDEO_URL = ROOTS_URL + r'/video/%s/'  # (the episode slug)


# The video URL where the .m3u8 file is found
# @param string the episode slug from the EPISODES_LIST_URL response

class MyAddon(object):

    def __init__(self, aName):
        self.addon = xbmcaddon.Addon('plugin.video.%s' % aName)
        self.addonName = self.addon.getAddonInfo('name')
        self.localLang = self.addon.getLocalizedString
        self.homeDir = self.addon.getAddonInfo('path').decode(UTF8)
        self.addonIcon = xbmc.translatePath(os.path.join(self.homeDir, 'icon.png'))
        self.addonFanart = xbmc.translatePath(os.path.join(self.homeDir, 'fanart.jpg'))
        self.metafile = ''

        self.defaultHeaders = httpHeaders
        self.defaultVidStream = {
            'codec': 'h264',
            'width': 1280,
            'height': 720,
            'aspect': 1.78,
        }

        self.defaultAudStream = {'codec': 'aac', 'language': 'en'}
        self.defaultSubStream = {'language': 'en'}

        self.cj = cookielib.LWPCookieJar()
        self.session_id = None

    def do_pbs_login(self):
        if self.addon.getSetting('enable_login') != 'true':
            return

        profile = self.addon.getAddonInfo('profile').decode(UTF8)
        pdir = xbmc.translatePath(profile).decode(UTF8)

        if not os.path.isdir(pdir):
            os.makedirs(pdir)

        cj_file = ''
        if not hasattr(self, 'cj'):
            cj_file = xbmc.translatePath(os.path.join(profile, 'PBSCookies.dat')).decode(UTF8)
            self.cj = cookielib.LWPCookieJar()

            try:
                self.cj.load(cj_file)
            except BaseException as err:
                self.log('something broke: %s' % err)
                self.cj = []

        bad_cookie = True
        for cookie in self.cj:
            if cookie.name == 'sessionid':
                bad_cookie = cookie.is_expired()

        if self.addon.getSetting('first_run_done') != 'true':
            bad_cookie = True

        if bad_cookie:
            self.cj = cookielib.LWPCookieJar(cj_file)
            opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(self.cj))
            urllib2.install_opener(opener)

            html = self.get_request(PATH_URL + r'/shows/')
            client_id = re.compile(r'id="signInServiceList".+?client_id=(.+?)"', re.DOTALL).search(html).group(1)

            html = self.get_request(OAUTH_LOGIN_URL)
            lcsr, lnext = re.compile(r"name='csrfmiddlewaretoken'.+?value='(.+?)'.+?" + 'name="next".+?value="(.+?)"',
                                     re.DOTALL).search(html).groups()

            username = self.addon.getSetting('login_name')
            password = self.addon.getSetting('login_pass')

            if username != '' and password != '':
                url1 = OAUTH_LOGIN_URL
                xheaders = self.defaultHeaders.copy()
                xheaders['Referer'] = OAUTH_LOGIN_URL
                xheaders['Host'] = r'account.pbs.org'
                xheaders['Origin'] = ACCOUNT_URL
                xheaders['Connection'] = r'keep-alive'
                xheaders['Accept'] = r'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
                xheaders['Content-Type'] = r'application/x-www-form-urlencoded'
                udata = urllib.urlencode(
                    {'csrfmiddlewaretoken': lcsr, 'next': lnext, 'email': username, 'password': password})

                self.get_request(url1, udata, xheaders)
                self.get_request(AUTH_CLIENT_URL % client_id)

                for cookie in self.cj:
                    if cookie.name == 'pbsol.station':
                        self.addon.setSetting('pbsol', cookie.value)
                    elif cookie.name == 'pbs_uid':
                        self.addon.setSetting('pbs_uid', cookie.value)
                    elif cookie.name == 'sessionid':
                        cookie.expires = time.time() + (60 * 60 * 24 * 7)  # one week
                        cookie.discard = False

                self.addon.setSetting('first_run_done', 'true')
                self.cj.save()

        else:
            opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(self.cj))
            urllib2.install_opener(opener)

        return

    def get_pbs_cookie(self):
        self.do_pbs_login()

        cookie = ''

        if self.session_id is None:
            for cookie in self.cj:
                if cookie.name == 'sessionid':
                    self.session_id = cookie.value

        if self.session_id is not None:
            cookie += 'sessionid=%s; ' % self.session_id

        if self.addon.getSetting('station_id') != '':
            cookie += 'pbsol.sta_extended=%s; pbsol.station=%s; pbsol.station_id=%s; pbskids.localized=%s; ' % (
                self.addon.getSetting('sta_extended'), self.addon.getSetting('station'),
                self.addon.getSetting('station_id'), self.addon.getSetting('station'))

        else:
            html = self.get_request(COOKIE_URL)
            a = json.loads(html)
            a = a['cookie']
            b = re.compile(r'\["(.+?)".+?\["(.+?)"', re.DOTALL).search(a)
            if b is not None:
                station, station_id = b.groups()
                self.addon.setSetting('pbsol', station)
                self.addon.setSetting('station_id', station_id)
                self.addon.setSetting('sta_extended', quote(a))
                cookie += 'pbsol.sta_extended=%s; pbsol.station=%s; pbsol.station_id=%s; pbskids.localized=%s; ' % (
                    quote(a), station, station_id, station)

            else:
                cookie += ''

        return cookie

    def get_addon_menu(self, url, ilist):
        web_pdb.set_trace()

        addon_language = self.addon.getLocalizedString

        xheaders = self.defaultHeaders.copy()
        xheaders['Referer'] = SHOWS_HTML_URL
        xheaders['X-Requested-With'] = 'XMLHttpRequest'
        xheaders['Cookie'] = self.get_pbs_cookie()

        html = self.get_request(
            SHOWS_JSON_URL % (0, self.addon.getSetting('station_id'), '', '', 'all', self.addon.getSetting('alpha')),
            None, xheaders)
        a = json.loads(html)

        for b in a['genres'][1:]:
            ilist = self.add_menu_item(b['title'], 'GS', ilist, str(b['id']) + '|0', self.addonIcon, self.addonFanart,
                                       None, is_folder=True)

        if self.addon.getSetting('enable_login') == 'true':
            station_id = self.addon.getSetting('station_id')

            if station_id != '':
                xheaders = self.defaultHeaders.copy()
                xheaders['X-Requested-With'] = 'XMLHttpRequest'
                xheaders['Cookie'] = self.get_pbs_cookie()

                html = self.get_request(SHOWS_JSON_URL % (0, station_id, '', '', 'all', self.addon.getSetting('alpha')),
                                        None, xheaders)

                if len(html) > 0:
                    a = json.loads(html)

                    if len(a['results']['content']) > 0:
                        ilist = self.add_menu_item(addon_language(30048), 'GS', ilist, 'localpbs', self.addonIcon,
                                                   self.addonFanart, None, is_folder=True)

        xheaders['Cookie'] = self.get_pbs_cookie()

        html = self.get_request(PERSONAL_URL)
        if len(html) > 0:
            a = json.loads(html)
            if len(a['favorite_shows']['content'] or []) > 0:
                ilist = self.add_menu_item(addon_language(30004), 'GS', ilist, 'favorites', self.addonIcon,
                                           self.addonFanart, None, is_folder=True)

        xheaders = self.defaultHeaders.copy()
        xheaders['X-Requested-With'] = 'XMLHttpRequest'
        xheaders['Cookie'] = self.get_pbs_cookie()

        html = self.get_request(FAV_VIDEOS_URL % 1, None, xheaders)
        if len(html) > 0:
            a = json.loads(html)
            if a.get('videos') is not None:
                if len(a['videos']) > 0:
                    ilist = self.add_menu_item(addon_language(30005), 'GM', ilist, 'pbswatchlist', self.addonIcon,
                                               self.addonFanart, None, is_folder=True)

        ilist = self.add_menu_item(addon_language(30051), 'GS', ilist, 'pbssearch', self.addonIcon, self.addonFanart,
                                   None, is_folder=True)

        return ilist

    def get_addon_shows(self, url, ilist):
        web_pdb.set_trace()

        pg_num = ''
        addon_language = self.addon.getLocalizedString
        pbsid = self.addon.getSetting('station_id')
        alpha = self.addon.getSetting('alpha')

        gsurl = url
        genre_url = ''
        answer = ''
        xheaders = self.defaultHeaders.copy()
        if gsurl == 'favorites':
            xheaders['Cookie'] = self.get_pbs_cookie()

            html = self.get_request(FAV_SHOWS_URL % 1)
            a = json.loads(html)

            cats = a['content']

        elif gsurl == 'localpbs':
            xheaders['X-Requested-With'] = 'XMLHttpRequest'
            xheaders['Cookie'] = self.get_pbs_cookie()

            html = self.get_request(SHOWS_JSON_URL % (0, pbsid, '', '', 'local-only', self.addon.getSetting('alpha')),
                                    None, xheaders)
            a = json.loads(html)

            cats = a['results']['content']

        elif gsurl == 'pbssearch':
            keyb = xbmc.Keyboard(self.addon.getSetting('last_search'), addon_language(30051))
            keyb.doModal()
            if keyb.isConfirmed():
                answer = keyb.getText()
                if len(answer) == 0:
                    return ilist

            self.addon.setSetting('last_search', answer)
            answer = answer.replace(' ', '+')

            xheaders['X-Requested-With'] = 'XMLHttpRequest'
            xheaders['Cookie'] = self.get_pbs_cookie()

            html = self.get_request(STATION_SEARCH % (1, answer, pbsid), None, xheaders)
            a = json.loads(html)

            cats = a['results']['articles']

        else:
            genre_url, pg_num = url.split('|', 1)

            xheaders = self.defaultHeaders.copy()
            xheaders['X-Requested-With'] = 'XMLHttpRequest'
            xheaders['Cookie'] = self.get_pbs_cookie()

            html = self.get_request(SHOWS_JSON_URL % (pg_num, pbsid, genre_url, '', 'all', alpha), None, xheaders)
            a = json.loads(html)

            cats = a['results']['content']

        for i, (b) in list(enumerate(cats, start=1)):
            if gsurl == 'pbssearch':
                url = b['url']
            else:
                url = b.get('url')
                if url is None:
                    url = b['id']

            name = b['title']
            thumb = b['image']
            if thumb is not None:
                thumb = self.addonIcon

            fanart = b['image']
            if fanart is None:
                fanart = self.addonFanart

            info_list = {
                'TVShowTitle': name,
                'Title': name,
                'Studio': b.get('producer')
            }

            genres = b.get('genre_titles')
            if genres != [] and genres is not None:
                info_list['Genre'] = genres[0]

            info_list['Episode'] = b.get('video_count')
            info_list['Plot'] = b.get('description')

            if self.addon.getSetting('enable_login') == 'true':
                if gsurl == 'favorites':
                    context_menu = [
                        (addon_language(30006), 'XBMC.Container.Update(%s?mode=DF&url=RF%s)' % (sys.argv[0], url))]
                else:
                    context_menu = [(addon_language(30007), 'XBMC.RunPlugin(%s?mode=DF&url=AF%s)' % (sys.argv[0], url))]
            else:
                context_menu = None

            if gsurl == 'pbssearch':
                info_list['mediatype'] = 'episode'
                ilist = self.add_menu_item(name, 'GV', ilist, url, thumb, fanart, info_list, is_folder=False)
            else:
                info_list['mediatype'] = 'tvshow'
                ilist = self.add_menu_item(name, 'GC', ilist, url, thumb, fanart, info_list, is_folder=True,
                                           cm=context_menu)

        if pg_num != '':
            ilist = self.add_menu_item('[COLOR blue]%s[/COLOR]' % addon_language(30050), 'GS', ilist,
                                       genre_url + '|' + str(int(pg_num) + 1), self.addonIcon, self.addonFanart, None,
                                       is_folder=True)

        return ilist

    def get_addon_cats(self, url, ilist):
        web_pdb.set_trace()

        addon_language = self.addon.getLocalizedString

        thumb = xbmc.getInfoLabel('ListItem.Art(thumb)')
        fanart = xbmc.getInfoLabel('ListItem.Art(fanart)')

        info_list = {
            'TVShowTitle': xbmc.getInfoLabel('ListItem.TVShowTitle'),
            'Title': xbmc.getInfoLabel('ListItem.TVShowTitle'),
            'mediatype': 'tvshow'
        }

        xheaders = self.defaultHeaders.copy()
        xheaders['Cookie'] = self.get_pbs_cookie()

        html = self.get_request('http://www.pbs.org/show/%s' % url, None, xheaders)
        seasons = re.compile('data-content-type="episodes">(.+?)</select>', re.DOTALL).search(html)

        if seasons is not None:
            seasons = seasons.group(1)
            seasons = re.compile('data-season-url="(.+?)".+?>(.+?)<', re.DOTALL).findall(seasons)

        if seasons is None:
            ilist = self.add_menu_item('%s' % (addon_language(30045)), 'GE', ilist, '%s|%s|1' % (url, 'episodes'), thumb,
                                       fanart, info_list, is_folder=True)
        else:
            for surl, season in seasons:
                season = season.strip()
                surl = surl.split('episodes/', 1)[1]
                surl = 'episodes/' + surl.rstrip('/')
                ilist = self.add_menu_item('%s %s' % (season, addon_language(30045)), 'GE', ilist,
                                         '%s|%s|1' % (url, surl), thumb, fanart, info_list, is_folder=True)

        ilist = self.add_menu_item('%s' % (addon_language(30046)), 'GE', ilist, '%s|%s|1' % (url, 'clips'), thumb, fanart,
                                   info_list, is_folder=True)
        ilist = self.add_menu_item('%s' % (addon_language(30047)), 'GE', ilist, '%s|%s|1' % (url, 'previews'), thumb,
                                   fanart, info_list, is_folder=True)

        return ilist

    def get_addon_episodes(self, url, ilist):
        web_pdb.set_trace()

        addon_language = self.addon.getLocalizedString
        url, stype, page_num = url.split('|', 2)
        sname = url

        xheaders = self.defaultHeaders.copy()
        xheaders['Cookie'] = self.get_pbs_cookie()

        html = self.get_request('http://www.pbs.org/show/%s/%s/?page=%s' % (url, stype, page_num), None, xheaders)
        epis = re.compile(
            r'<article class="video-summary">.+?data-srcset="(.+?)".+?alt="(.+?)".+?class="description">(.+?)<.+?data-video-slug="(.+?)"',
            re.DOTALL).findall(html)

        if len(epis) == 0:
            epis = re.compile(
                r'<div class="video-summary".+?data-srcset="(.+?)".+?alt="(.+?)".+?class="description">(.+?)<.+?data-video-slug="(.+?)"',
                re.DOTALL).findall(html)

        for i, (imgs, name, plot, url) in list(enumerate(epis, start=1)):
            name = h.unescape(name.decode(UTF8))
            name = name.replace('Video thumbnail: ', '', 1)
            plot = plot.strip()
            info_list = {}
            imgs = imgs.split(',')
            thumb = '%s.jpg' % (imgs[2].split('.jpg', 1)[0].strip())
            fanart = '%s.jpg' % (imgs[len(imgs) - 1].split('.jpg', 1)[0].strip())
            info_list['Title'] = name
            info_list['Plot'] = h.unescape(plot.decode(UTF8))
            info_list['mediatype'] = 'episode'
            info_list['TVShowTitle'] = xbmc.getInfoLabel('ListItem.TVShowTitle')

            if self.addon.getSetting('enable_login') == 'true':
                context_menu = [(addon_language(30008), 'XBMC.RunPlugin(%s?mode=DF&url=AW%s)' % (sys.argv[0], url))]
            else:
                context_menu = None

            ilist = self.add_menu_item(name, 'GV', ilist, url, thumb, fanart, info_list, is_folder=False, cm=context_menu)

            if i >= showsPerPage:
                ilist = self.add_menu_item('[COLOR blue]%s[/COLOR]' % addon_language(30050), 'GE', ilist,
                                         '%s|%s|%s' % (sname, stype, str(int(page_num) + 1)), self.addonIcon,
                                           self.addonFanart, None, is_folder=True)

        return ilist

    def get_addon_movies(self, url, ilist):
        web_pdb.set_trace()

        addon_language = self.addon.getLocalizedString
        xbmcplugin.setContent(int(sys.argv[1]), 'episodes')

        xheaders = self.defaultHeaders.copy()
        xheaders['X-Requested-With'] = 'XMLHttpRequest'
        xheaders['Cookie'] = self.get_pbs_cookie()

        html = self.get_request('https://www.pbs.org/watchlist/page/1/', None, xheaders)
        a = json.loads(html)

        epis = a['videos']

        for i, b in list(enumerate(epis, start=1)):
            info_list = {}
            name = b['title']
            plot = b['description']
            duration = b['duration']
            t = 0

            for dur in duration.split(':'):
                if dur.strip().isdigit():
                    t = t * 60 + int(dur.strip())

            if t != 0:
                info_list['duration'] = t

            thumb = b['image']
            fanart = b['image']
            info_list['TVShowTitle'] = b['show']['title']
            info_list['Title'] = name
            info_list['Plot'] = plot
            info_list['mediatype'] = 'episode'
            url = str(b['id'])
            context_menu = [(addon_language(30009), 'XBMC.Container.Update(%s?mode=DF&url=RW%s)' % (sys.argv[0], url))]
            ilist = self.add_menu_item(name, 'GV', ilist, url, thumb, fanart, info_list, is_folder=False, cm=context_menu)

        return ilist

    def do_function(self, url):
        web_pdb.set_trace()

        func = url[0:2]
        url = url[2:]

        xheaders = self.defaultHeaders.copy()
        xheaders['Cookie'] = self.get_pbs_cookie()

        html = ''
        if func == 'AW':
            html = self.get_request('http://www.pbs.org/profile/addFavoriteVideo/%s/' % url)
        elif func == 'AF':
            html = self.get_request('http://www.pbs.org/profile/addFavoriteProgram/%s/' % url)
        elif func == 'RW':
            html = self.get_request('http://www.pbs.org/profile/removeFavoriteVideo/%s/' % url)
        elif func == 'RF':
            html = self.get_request('http://www.pbs.org/profile/removeFavoriteProgram/%s/' % url)

        try:
            a = json.loads(html)
            xbmc.executebuiltin('XBMC.Notification("%s", "%s", %s)' % (self.addonName, a['errorMessage'], 4000))
        except BaseException as err:
            self.log('something broke: %s' % err)
            pass

    def get_addon_video(self, url):
        web_pdb.set_trace()

        xheaders = self.defaultHeaders.copy()
        xheaders['X-Requested-With'] = 'XMLHttpRequest'
        xheaders['Cookie'] = self.get_pbs_cookie()

        if not url.startswith('/video'):
            html = self.get_request('http://www.pbs.org/video/%s/' % url, None, xheaders)
        else:
            html = self.get_request('http://www.pbs.org/%s' % url, None, xheaders)

        url = re.compile("id: '(.+?)'", re.DOTALL).search(html).group(1)
        addon_language = self.addon.getLocalizedString
        pbs_uid = self.addon.getSetting('pbs_uid')
        pg = self.get_request('https://player.pbs.org/viralplayer/%s/?uid=%s' % (url, pbs_uid))
        pg = re.compile('window.videoBridge = (.+?);\n', re.DOTALL).search(pg).group(1)
        a = json.loads(pg)

        if a is not None:
            suburl = a['cc'].get('SRT')
            urls = a['encodings']
            url = ''

            for xurl in urls:
                pg = self.get_request('%s?format=json' % xurl)
                xurl = json.loads(pg)['url']
                if xurl.endswith('.m3u8'):
                    if url.endswith('800k.m3u8') or url.endswith('.mp4'):
                        url = xurl
                        break
                    else:
                        url = xurl
                else:
                    if not url.endswith('.m3u8'):
                        url = xurl
        else:
            xbmc.executebuiltin('XBMC.Notification("%s", "%s", %s)' % (self.addonName, addon_language(30049), 4000))
            return

        liz = xbmcgui.ListItem(path=url)

        if suburl is not None:
            subfile = self.proc_convert_subtitles(suburl)
            liz.setSubtitles([subfile])

        if '.m3u8' in url:
            liz.setProperty('inputstreamaddon', 'inputstream.adaptive')
            liz.setProperty('inputstream.adaptive.manifest_type', 'hls')

        xbmcplugin.setResolvedUrl(int(sys.argv[1]), True, liz)

    #
    # helper functions
    #

    def log(self, txt):
        try:
            message = '%s: %s' % (self.addonName, txt.encode('ascii', 'ignore'))
            xbmc.log(msg=message, level=xbmc.LOGDEBUG)
        except BaseException as err:
            self.log('something broke: %s' % err)
            pass

    def get_request(self, url, udata=None, headers=httpHeaders, dopost=False, rmethod=None):
        web_pdb.set_trace()

        self.log("get_request URL:" + str(url))
        req = urllib2.Request(url.encode(UTF8), udata, headers)

        if dopost:
            rmethod = "POST"

        if rmethod is not None:
            req.get_method = lambda: rmethod

        try:
            response = urllib2.urlopen(req, timeout=60)
            page = response.read()

            if response.info().getheader('Content-Encoding') == 'gzip':
                self.log("Content Encoding == gzip")
                page = zlib.decompress(page, zlib.MAX_WBITS + 16)
        except BaseException as err:
            self.log('something broke: %s' % err)
            page = ""

        return page

    def get_addon_meta(self):
        web_pdb.set_trace()

        if self.addon.getSetting('enable_meta') != 'true':
            return {}

        profile = self.addon.getAddonInfo('profile').decode(UTF8)
        pdir = xbmc.translatePath(os.path.join(profile))

        if not os.path.isdir(pdir):
            os.makedirs(pdir)

        self.metafile = xbmc.translatePath(os.path.join(profile, 'meta.json'))

        meta = {}
        if self.addon.getSetting('init_meta') != 'true':
            try:
                with open(self.metafile) as infile:
                    meta = json.load(infile)
            except BaseException as err:
                self.log('something broke: %s' % err)
                pass

        return meta

    def update_addon_meta(self, meta):
        web_pdb.set_trace()

        if self.addon.getSetting('enable_meta') != 'true':
            return

        with open(self.metafile, 'w') as outfile:
            json.dump(meta, outfile)

        outfile.close()

        self.addon.setSetting(id='init_meta', value='false')

    def add_menu_item(self, name, mode, ilist=None, url=None, thumb=None, fanart=None,
                      video_info=None, video_stream=None, audio_stream=None,
                      subtitle_stream=None, cm=None, is_folder=True):

        web_pdb.set_trace()

        if ilist is None:
            ilist = []

        if video_info is None:
            video_info = {}

        video_stream = self.defaultVidStream
        audio_stream = self.defaultAudStream
        subtitle_stream = self.defaultSubStream

        liz = xbmcgui.ListItem(name)
        liz.setArt({'thumb': thumb, 'fanart': fanart})
        liz.setInfo('Video', video_info)
        liz.addStreamInfo('video', video_stream)
        liz.addStreamInfo('audio', audio_stream)
        liz.addStreamInfo('subtitle', subtitle_stream)

        if cm is not None:
            liz.addContextMenuItems(cm)

        if not is_folder:
            liz.setProperty('IsPlayable', 'true')

        u = '%s?mode=%s' % (sys.argv[0], mode)

        if url is not None:
            u = u + '&url=%s' % urllib.quote_plus(url)

        ilist.append((u, liz, is_folder))

        return ilist

    # internal functions for views, cache and directory management

    def proc_dir(self, dir_func, url, content_type='files', view_type='default_view', cache_to_disc=True):
        web_pdb.set_trace()

        ilist = []

        xbmcplugin.setContent(int(sys.argv[1]), content_type)
        xbmcplugin.addSortMethod(int(sys.argv[1]), xbmcplugin.SORT_METHOD_UNSORTED)
        xbmcplugin.addSortMethod(int(sys.argv[1]), xbmcplugin.SORT_METHOD_TITLE)
        xbmcplugin.addSortMethod(int(sys.argv[1]), xbmcplugin.SORT_METHOD_EPISODE)

        ilist = dir_func(url, ilist)
        if len(ilist) > 0:
            xbmcplugin.addDirectoryItems(int(sys.argv[1]), ilist, len(ilist))

            if self.addon.getSetting('enable_views') == 'true':
                xbmc.executebuiltin("Container.SetViewMode(%s)" % self.addon.getSetting(view_type))

            xbmcplugin.endOfDirectory(int(sys.argv[1]), cacheToDisc=cache_to_disc)

    def get_video(self, url):
        web_pdb.set_trace()

        self.get_addon_video(url)

    def do_resolve(self, liz, subtitles=None):
        web_pdb.set_trace()

        if subtitles is None:
            subtitles = []

        info_list = {
            'mediatype': xbmc.getInfoLabel('ListItem.DBTYPE'),
            'Title': xbmc.getInfoLabel('ListItem.Title'),
            'TVShowTitle': xbmc.getInfoLabel('ListItem.TVShowTitle'),
            'Year': xbmc.getInfoLabel('ListItem.Year'),
            'Premiered': xbmc.getInfoLabel('Premiered'),
            'Plot': xbmc.getInfoLabel('ListItem.Plot'),
            'Studio': xbmc.getInfoLabel('ListItem.Studio'),
            'Genre': xbmc.getInfoLabel('ListItem.Genre'),
            'Duration': xbmc.getInfoLabel('ListItem.Duration'),
            'MPAA': xbmc.getInfoLabel('ListItem.Mpaa'),
            'Aired': xbmc.getInfoLabel('ListItem.Aired'),
            'Season': xbmc.getInfoLabel('ListItem.Season'),
            'Episode': xbmc.getInfoLabel('ListItem.Episode')
        }

        liz.setInfo('video', info_list)
        liz.setSubtitles(subtitles)

        xbmcplugin.setResolvedUrl(int(sys.argv[1]), True, liz)

    def proc_convert_subtitles(self, suburl):
        web_pdb.set_trace()

        subfile = ""
        if suburl != "":
            profile = self.addon.getAddonInfo('profile').decode(UTF8)
            prodir = xbmc.translatePath(os.path.join(profile))
            if not os.path.isdir(prodir):
                os.makedirs(prodir)

            pg = self.get_request(suburl)
            if pg != "":
                try:
                    subfile = xbmc.translatePath(os.path.join(profile, 'subtitles.srt'))
                    ofile = open(subfile, 'w+')

                    captions = re.compile('<p begin="(.+?)" end="(.+?)">(.+?)</p>', re.DOTALL).findall(pg)
                    for idx, (cstart, cend, caption) in list(enumerate(captions, start=1)):
                        cstart = cstart.replace('.', ',')
                        cend = cend.replace('.', ',').split('"', 1)[0]
                        caption = caption.replace('<br/>', '\n').strip()

                        try:
                            caption = HTMLParser.HTMLParser().unescape(caption)
                        except BaseException as err:
                            self.log('something broke: %s' % err)
                            pass

                        caption = caption.replace('&apos;', "'").replace('\n\n', '\n')
                        ofile.write('%s\n%s --> %s\n%s\n\n' % (idx, cstart, cend, caption))
                    ofile.close()
                except BaseException as err:
                    self.log('something broke: %s' % err)
                    subfile = ""

        return subfile

    def get_addon_parms(self):
        web_pdb.set_trace()

        try:
            parms = dict(arg.split("=") for arg in ((sys.argv[2][1:]).split("&")))
            for key in parms:
                try:
                    parms[key] = urllib.unquote_plus(parms[key]).decode(UTF8)
                except BaseException as err:
                    self.log('something broke: %s' % err)
                    pass

        except BaseException as err:
            self.log('something broke: %s' % err)
            parms = {}

        return parms.get

    def process_addon_event(self):
        web_pdb.set_trace()

        p = self.get_addon_parms()
        mode = p('mode', None)

        if mode is None:
            self.proc_dir(self.get_addon_menu, p('url'), 'files', 'default_view')
        elif mode == 'GC':
            self.proc_dir(self.get_addon_cats, p('url'), 'files', 'default_view')
        elif mode == 'GM':
            self.proc_dir(self.get_addon_movies, p('url'), 'movies', 'movie_view')
        elif mode == 'GS':
            self.proc_dir(self.get_addon_shows, p('url'), 'tvshows', 'show_view')
        elif mode == 'GE':
            self.proc_dir(self.get_addon_episodes, p('url'), 'episodes', 'episode_view')
        elif mode == 'GV':
            self.get_video(p('url'))
        elif mode == 'DF':
            self.do_function(p('url'))

        return p

# end
