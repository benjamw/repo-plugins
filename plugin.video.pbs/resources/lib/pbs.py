#!/usr/bin/env python
# -*- coding: utf-8 -*-

import cookielib
import HTMLParser
import json
import re
import urllib
import urllib2
import zlib

from os import path

try:
    from urllib import quote  # Python 2.X
except ImportError:
    from urllib.parse import quote  # Python 3+

import constants as c

h = HTMLParser.HTMLParser()


class PBS:

    def __init__(self, settings=None):
        self.username = None
        self.password = None
        self.sessionId = None

        self.station = None
        self.stationId = None
        self.stationExtended = None
        self.pbsUid = None
        self.commonName = None

        self.genres = None
        self.sources = None
        self.sort_orders = None

        self.all_genres = None
        self.all_sources = None
        self.local_source = None

        self.alpha = True
        self.enableLogin = False

        self.cjFile = ''
        self.cj = cookielib.LWPCookieJar()
        self.opener = None

        self.cookieFileExists = False
        self.loggingIn = False

        self.defaultHeaders = c.httpHeaders

        self.set_data(settings)

        return

    def set_data(self, settings=None):
        if settings is None:
            return

        self.alpha = settings.alpha
        self.enableLogin = settings.enableLogin

        if self.enableLogin:
            self.username = settings.username
            self.password = settings.password

        self.cjFile = settings.cjFile

        self.startup()

    def startup(self):
        if self.cjFile is not None or '' != self.cjFile:
            self.cj = cookielib.LWPCookieJar(self.cjFile)

            if path.exists(self.cjFile):
                self.cookieFileExists = True
                try:
                    self.cj.load()
                except (ValueError, IOError, cookielib.LoadError):
                    pass

        # opener for requests with redirects
        self.opener = urllib2.build_opener(NoRedirection, urllib2.HTTPCookieProcessor(self.cj))

        # opener for normal requests
        urllib2.install_opener(urllib2.build_opener(urllib2.HTTPCookieProcessor(self.cj)))

        self.get_cookie()
        self.get_data()

    def get_cookie(self):
        if self.sessionId is None or self.sessionId == '':
            for cookie in self.cj:
                if c.SESSION_COOKIE_NAME == cookie.name and 'www.pbs.org' == cookie.domain and not cookie.is_expired():
                    self.sessionId = cookie.value

                if c.USER_ID_COOKIE_NAME == cookie.name:
                    self.pbsUid = cookie.value

        if self.sessionId is None or self.sessionId == '':
            if not self.loggingIn:
                self.login()

        cookie_out = ''

        if self.sessionId is not None:
            cookie_out += r'{}={}; '.format(c.SESSION_COOKIE_NAME, self.sessionId)

        if self.pbsUid is not None:
            cookie_out += r'{}={}; '.format(c.USER_ID_COOKIE_NAME, self.pbsUid)

        # use commonName here because everything else has to be set for this to be set
        if self.commonName is not None and self.commonName != '':
            cookie_out += c.COOKIE_FORMAT.format(ext=quote(self.stationExtended), sta=self.station, id=self.stationId,
                                               name=self.commonName)
        else:
            reg = re.compile(r"""\["(.+?)"\]""").search

            data = self.get_request(True, c.COOKIE_URL)  # don't use self.get_headers() here or feel the wrath of the infinite loop
            self.stationExtended = data.get('cookie', '')
            cook_data = data.get('cookie', '').split('#')
            for val in cook_data:
                if -1 != val.find('s='):
                    self.station = reg(val).group(1)
                elif -1 != val.find('sid='):
                    self.stationId = reg(val).group(1)

            cs_data = self.get_request(True, c.CALLSIGN_URL.format(self.station))  # don't use self.get_headers() here or feel the wrath of the infinite loop
            self.commonName = cs_data.get('station', {}).get('common_name', '')

            cookie_out += c.COOKIE_FORMAT.format(ext=quote(self.stationExtended), sta=self.station, id=self.stationId,
                                               name=self.commonName)

        return cookie_out

    def get_data(self):
        html = self.get_request(False, c.DATA_JS_URL, self.get_headers())
        data = re.compile(c.DATA_REGEX).search(html).groups()

        self.genres = json.loads(data[0].replace('labelText', '"labelText"').replace('name', '"name"'))
        self.sources = json.loads(data[1].replace('labelText', '"labelText"').replace('name', '"name"')
                                  .replace(r'"Only ".concat(e," Shows")', u'"Local ' + self.station + ' Only"'))
        self.sort_orders = json.loads(data[2].replace('labelText', '"labelText"').replace('name', '"name"'))

        for genre in self.genres:
            if -1 != genre['name'].find('all'):
                self.all_genres = genre['name']
                break

        for source in self.sources:
            if -1 != source['name'].find('all'):
                self.all_sources = source['name']
            elif -1 != source['name'].find('station'):
                self.local_source = source['name']
            elif -1 != source['name'].find('only'):
                self.local_source = source['name']

        return

    def login(self):
        if not self.enableLogin:
            return

        self.loggingIn = True

        bad_cookie = True
        for cookie in self.cj:
            if cookie.name == c.SESSION_COOKIE_NAME:
                bad_cookie = cookie.is_expired()

        if not self.cookieFileExists:
            bad_cookie = True

        if bad_cookie:
            # grab the client_id from a basic URL
            html = self.get_request(False, c.SHOWS_URL)
            client_id = re.compile(c.CLIENT_ID_REGEX).search(html).group(1)

            headers = self.get_headers(False)
            headers['Host'] = r'account.pbs.org'
            headers['Connection'] = r'keep-alive'
            headers['Accept'] = r'*/*'

            # start the logging in process by hitting the AUTH_CLIENT_URL
            resp = self.get_redirect(c.AUTH_CLIENT_URL.format(client_id), headers)

            # the response should have a Location header to the login page
            headers['Origin'] = c.ACCOUNT_URL
            headers['Referer'] = c.AUTH_CLIENT_URL
            headers['Accept'] = r'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3'
            loc = resp.headers['Location']

            # hit the login page to get the csrf token cookie and form data
            html = self.get_request(False, c.ACCOUNT_URL[:-1] + loc, headers)
            login_regex = r"{}.+?{}.+?{}".format(c.ACTION_REGEX, c.CSRF_TOKEN_REGEX, c.LOGIN_NEXT_REGEX)
            groups = re.compile(login_regex, re.DOTALL).search(html).groups()

            # add the csrf token to the cookie list, since it doesn't get properly added later
            self.cj.save()
            for cookie in self.cj:
                if c.CSRF_COOKIE_NAME == cookie.name:
                    headers['Cookie'] += r'{}={}; '.format(cookie.name, cookie.value)

            csrf_token = ''
            login_next = ''
            action = ''
            for var in range(len(groups)):
                if groups[var] is not None:
                    if var == 0:
                        action = h.unescape(groups[var])
                    elif var < 3:
                        csrf_token = h.unescape(groups[var])
                    else:
                        login_next = h.unescape(groups[var])

            if self.username != '' and self.password != '':
                headers['Referer'] = c.ACCOUNT_URL[:-1] + loc
                headers['Content-Type'] = r'application/x-www-form-urlencoded'
                form_data = urllib.urlencode({
                    'csrfmiddlewaretoken': csrf_token,
                    'next': login_next,
                    'email': self.username,
                    'password': self.password,
                    'keep_logged_in': 'on',
                    'station': '',
                })

                # send the login form data
                resp = self.get_redirect(c.ACCOUNT_URL[:-1] + action, headers, form_data)

                # add the account session cookie to the cookie list, since it doesn't get properly added later
                self.cj.save()
                for cookie in self.cj:
                    if c.SESSION_COOKIE_NAME == cookie.name:
                        headers['Cookie'] += r'{}={}; '.format(cookie.name, cookie.value)

                # get the final auth URL
                headers['Referer'] = c.ACCOUNT_URL[:-1] + action
                del headers['Content-Type']
                loc = resp.headers['Location']

                resp = self.get_redirect(c.ACCOUNT_URL[:-1] + loc, headers)

                # and the final www.pbs.org URL with the session cookie we need
                headers['Referer'] = c.ACCOUNT_URL[:-1] + loc
                loc = resp.headers['Location']

                self.get_request(False, loc, headers)

                # now all the cookies should be in the cookie jar
                for cookie in self.cj:
                    if cookie.name == 'pbs_uid':
                        self.pbsUid = cookie.value

                try:
                    self.cj.save()
                    self.cookieFileExists = True
                except ValueError:
                    pass

        self.loggingIn = False

        return

    def clear_cookies(self):
        try:
            self.cj.clear()
            self.cj.save()
        except ValueError:
            pass

    def get_genres(self):
        items = []

        url = c.SHOWS_JSON_URL.format(0, self.stationId, self.all_genres, '', self.all_sources, self.alpha)
        data = self.get_request(True, url, self.get_headers())

        for genre in self.genres:
            items.append({u'id': genre['name'], u'title': genre['labelText']})

        if 0 < len(data.get('results', {}).get('content', {})):
            items.append({u'id': u'localpbs', u'title': u'Local ' + self.station})

        data = self.get_request(True, c.PERSONAL_URL, self.get_headers(True), '{"videoSlug":null}')

        if 0 < len(data.get('favorite_shows', {}).get('content', {})) \
                or 0 < len(data.get('favorite_videos', {}).get('content', {})):
            items.insert(0, {u'id': u'favorites', u'title': u'Favorite Shows'})

        data = self.get_request(True, c.FAV_VIDEOS_URL.format(1), self.get_headers(True))

        if 0 < len(data.get('videos', [])):
            items.insert(0, {u'id': u'watchlist', u'title': u'My Watch List'})

        # items.append({u'id': u'search', u'title': u'Search'})

        return {
            u'items': items,
        }

    def get_shows(self, genre='all', page=0):
        page = int(page)

        if 'localpbs' == genre:
            return self.get_local(page)

        if 'search' == genre:
            return self.get_search(page)

        if 'favorites' == genre:
            return self.get_fav_shows(page)

        if 'watchlist' == genre:
            return self.get_watchlist(page)

        items = []

        url = c.SHOWS_JSON_URL.format(page, self.stationId, genre, '', self.all_sources, self.alpha)
        data = self.get_request(True, url, self.get_headers())
        pages = data.get('results', {}).get('totalPages', 0)
        page = data.get('results', {}).get('pageNumber', page)

        for item in data.get('results', {}).get('content', {}):
            items.append({
                u'title': item['title'],
                u'slug': item['slug'],
                u'cid': item['cid'],
                u'description': item['description_long'],
                u'image': item['image'],
            })

        return {
            u'items': items,
            u'page': page + 1,  # fix 0-index pages
            u'pages': pages,
            u'page0': True,
        }

    def get_local(self, page=0):
        page = int(page)
        items = []

        url = c.SHOWS_JSON_URL.format(page, self.stationId, self.all_genres, '', self.local_source, self.alpha)
        data = self.get_request(True, url, self.get_headers())
        pages = data.get('results', {}).get('totalPages', 0)
        page = data.get('results', {}).get('pageNumber', page)

        for item in data.get('results', {}).get('content', {}):
            items.append({
                u'title': item['title'],
                u'slug': item['slug'],
                u'cid': item['cid'],
                u'description': item['description_long'],
                u'image': item['image'],
            })

        return {
            u'items': items,
            u'page': page + 1,  # fix 0-index pages
            u'pages': pages,
            u'page0': True,
        }

    def get_search(self, page=0, search=''):
        page = int(page)
        return

    def get_fav_shows(self, page=1):
        page = int(page)
        if 0 >= page:
            page = 1

        items = []

        data = self.get_request(True, c.FAV_SHOWS_URL.format(page), self.get_headers())
        for item in data.get('content', []):
            items.append({
                u'title': item['title'],
                u'slug': item['id'],
                u'cid': '',
                u'description': item['title'],
                u'image': item['image'],
            })

        return {
            u'items': items,
            u'page': data.get('pageNumber', page),
            u'pages': data.get('totalPages', 1),
            u'page0': False,
        }

    def get_watchlist(self, page=1):
        page = int(page)
        if 0 >= page:
            page = 1

        items = []

        data = self.get_request(True, c.FAV_VIDEOS_URL.format(page), self.get_headers())
        for item in data.get('content', []):
            if 'available' != item.get('availability', ''):
                continue

            items.append(self.process_video_item(item))

        return {
            u'items': items,
            u'page': data.get('pageNumber', page),
            u'pages': data.get('totalPages', 1),
            u'page0': False,
        }

    def get_seasons(self, show_slug=''):
        items = []

        data = self.get_request(True, c.SEASONS_LIST_URL.format(show_slug), self.get_headers())

        items.append({
            u'title': u'All Seasons',
            u'cid': u'all',
        })

        for item in data.get('content', {}):
            if item.get('flags', {}).get('has_episodes', False):
                items.append({
                    u'title': u'Season ' + str(item['ordinal']),
                    u'cid': item['cid'],
                })

        return {
            u'items': items,
        }

    def get_specials(self, show_slug='', page=0):
        page = int(page)
        items = []

        url = c.SHOW_SPECIALS_LIST_URL.format(show_slug, page * c.showsPerPage, c.showsPerPage)
        data = self.get_request(True, url, self.get_headers())

        for item in data.get('content', []):
            if 'available' != item.get('availability', ''):
                continue

            items.append(self.process_video_item(item))

        return {
            u'items': items,
            u'has_next': data.get('has_next', False),
        }

    def get_extra(self, show=''):
        return

    def get_episodes(self, show_slug='', season_cid='', page=0):
        page = int(page)
        items = []

        if 'all' == season_cid:
            url = c.ALL_EPISODES_LIST_URL.format(show_slug, page * c.showsPerPage, c.showsPerPage)
        else:
            url = c.EPISODES_LIST_URL.format(show_slug, season_cid, page * c.showsPerPage, c.showsPerPage)

        # if no shows were found in the previous URLs, it may be a special
        data = self.get_request(True, url, self.get_headers())
        if 0 == len(data.get('content', [])):
            url = c.SHOW_SPECIALS_LIST_URL.format(show_slug, page * c.showsPerPage, c.showsPerPage)
            data = self.get_request(True, url, self.get_headers())

        for item in data.get('content', []):
            if 'available' != item.get('availability', ''):
                continue

            items.append(self.process_video_item(item))

        return {
            u'items': items,
            u'has_next': data.get('has_next', False),
        }

    def get_video(self, video_media_id=''):
        url = c.PLAYER_URL.format(video_media_id, self.pbsUid)
        html = self.get_request(False, url, self.get_headers(True))
        js = re.compile(c.PLAYER_REDIRECT_REGEX).search(html).group(1)
        data = json.loads(js)

        if data is None:
            return {
                u'error': 'Video not found',
            }

        loc = ''
        if len(data.get('encodings', [])):
            for url in data.get('encodings', []):
                resp = self.get_request(True, url + '?format=json', self.get_headers())
                loc = resp.get('url', '')

                if loc.endswith('.m3u8'):
                    break

        subs = data.get('cc', {}).get('SRT', '')

        return {
            u'video_url': loc,
            u'subs_url': subs,
        }

    def get_fav_videos(self, page=1):
        page = int(page)

        items = []

        url = c.FAV_VIDEOS_URL.format(page)
        data = self.get_request(True, url, self.get_headers(True))

        for item in data.get('videos', []):
            if 'available' != item.get('availability', ''):
                continue

            items.append(self.process_video_item(item))

        return {
            u'items': items,
            u'has_next': data.get('has_next', False),
        }

    def update_fav_shows(self, add=True, show_cid=''):
        url = c.ADD_FAV_SHOW.format(show_cid)
        if not add:
            url = c.REMOVE_FAV_SHOW.format(show_cid)

        data = self.get_request(True, url, self.get_headers(), {})

        return data.get('errorMessage', 'FAILED')

    def update_fav_videos(self, add=True, video_cid=''):
        url = c.ADD_FAV_VIDEO.format(video_cid)
        if not add:
            url = c.REMOVE_FAV_VIDEO.format(video_cid)

        data = self.get_request(True, url, self.get_headers(), {})

        return data.get('errorMessage', 'FAILED')

    def update_fav_program(self, add=True, program_cid=''):
        url = c.ADD_FAV_PROGRAM.format(program_cid)
        if not add:
            url = c.REMOVE_FAV_PROGRAM.format(program_cid)

        data = self.get_request(True, url, self.get_headers(), {})

        return data.get('errorMessage', 'FAILED')

    def get_headers(self, is_json=True, referer=None):
        if referer is None:
            referer = c.SHOWS_HTML_URL.format('all', self.station)

        headers = self.defaultHeaders.copy()
        headers['Referer'] = referer
        headers['Cookie'] = self.get_cookie()

        if is_json:
            headers['Content-Type'] = 'application/json; charset=UTF-8'
            headers['X-Requested-With'] = 'XMLHttpRequest'

        return headers

    def get_redirect(self, url, headers=None, data=None):
        """
        Send an HTTP request and get the response object without following any redirects

        :param url: string The URL to request
        :param headers: dict The headers to send with the request
        :param data: string The data to pass in with the request formatted via urllib.urlencode
        :return: response object
        """

        try:
            req = urllib2.Request(url.encode(c.UTF8), data, headers)

            # this uses a raw opener so the request can be accessed directly to get the Location
            # header without urllib2 trying to follow the redirect itself
            resp = self.opener.open(req)

        except IOError:
            resp = False

        return resp

    def get_request(self, is_json, url, headers=None, data=None, attempted=False):
        """
        Send an HTTP request and get the response

        :param is_json: bool Return the response as a JSON parsed object
        :param url: string The URL to request
        :param headers: dict The headers to send with the request
        :param data: string The data to pass in with the request formatted via urllib.urlencode
        :param attempted: bool Has this request been attempted already
        :return: string|dict The response for the request
        """
        if headers is None:
            headers = c.httpHeaders

        c.log('REQUEST: {}'.format(url))
        req = urllib2.Request(url.encode(c.UTF8), data, headers)

        page = ''
        try:
            response = urllib2.urlopen(req, timeout=60)

            page = response.read()

            if 'gzip' == response.info().getheader('Content-Encoding'):
                page = zlib.decompress(page, zlib.MAX_WBITS + 16)

        except urllib2.HTTPError:
            if not attempted:
                self.clear_cookies()
                return self.get_request(is_json, url, self.get_headers(), data, attempted=True)

        except ValueError:
            page = ''

        if is_json:
            if '' != page:
                return json.loads(page)
            else:
                return {}

        return page

    def process_video_item(self, item):
        duration = item.get('duration', '')
        try:
            duration += 0
        except TypeError:
            matches = re.compile(r'(?:(\d+)h)?\s*(?:(\d+)m)?\s*(?:(\d+)s)?').search(duration).groups()
            duration = 0
            if '' != matches[0] and matches[0] is not None:
                duration += (60 * 60 * int(matches[0]))
            if '' != matches[1] and matches[1] is not None:
                duration += (60 * int(matches[1]))
            if '' != matches[2] and matches[2] is not None:
                duration += (int(matches[2]))

        return {
            u'title': item.get('title', ''),
            u'show_title': item.get('show', {}).get('title', ''),
            u'cid': item.get('cid', ''),
            u'image': item.get('image', ''),
            u'duration': int(duration),
            u'description': item.get('description_long', ''),
            u'type': item.get('item_type', ''),
            u'availability': item.get('availability', ''),
            u'premiere_date': item.get('premiere_date', ''),
            u'expire_date': item.get('expire_date', ''),
            u'episode': item.get('show', {}).get('episode', ''),
            u'season': item.get('show', {}).get('season', ''),
            u'summary': item.get('summary', ''),
            u'tp_media_id': item.get('legacy_tp_media_id', ''),
        }

# end


class PBSSettings:
    """
    The settings object for easily passing the settings into the PBS class

    :param alpha: bool Sort results alphabetically (vs. by Popular)
    :param enable_login: bool Enable login to PBS
    :param username: string The username for the PBS account
    :param password: string The password for the PBS account
    :param cj_file: string The path to the cookie jar file used to store the returned cookies
    """

    def __init__(self, alpha=True, enable_login=False, username=None, password=None, cj_file=''):
        self.alpha = alpha
        self.enableLogin = enable_login

        if self.enableLogin:
            self.username = username
            self.password = password

        self.cjFile = cj_file

# end


class NoRedirection(urllib2.HTTPErrorProcessor):

    def http_response(self, request, response):
        return response

    https_response = http_response

# end


class PBSError(Exception):
    def __init__(self, message, f, l):
        super(PBSError, self).__init__(message)

        self.file = f
        self.line = l

# end
