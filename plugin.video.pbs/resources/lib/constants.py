#!/usr/bin/env python
# -*- coding: utf-8 -*-

import xbmc


UTF8 = 'utf-8'

showsPerPage = 24  # number of shows returned per page by PBS

httpHeaders = {
    'User-Agent': r'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.120 Safari/537.36',
    'Accept': r'application/json,text/javascript,text/html,*/*',
    'Accept-Encoding': r'gzip, deflate, br',
    'Accept-Language': r'en-US,en;q=0.8',
}

SESSION_COOKIE_NAME = 'sessionid'
# The name for the PBS session cookie

CSRF_COOKIE_NAME = 'csrftoken'
# The name for the PBS oauth csrf cookie

USER_ID_COOKIE_NAME = 'pbs_uid'
# The name for the PBS user id cookie

COOKIE_FORMAT = 'pbs.preventOverlays=1; pbs_mvod=[%22{sta}%22]; pbskids.localized={sta}; ' \
                'pbsol.common.name={name}; pbsol.common.name.short={sta}; pbsol.sta_extended={ext}; ' \
                'pbsol.station={sta}; pbsol.station_id={id}; '
# The cookies expected by PBS

'''
URL CONSTANTS
'''

#
# HTML PAGES
#

ROOT_URL = r'https://www.pbs.org/'
# The PBS root URL (secure)

SHOWS_URL = ROOT_URL + r'shows/'
# A user-facing page (for collecting tokens)

PATH_URL = ROOT_URL + r'{}'
# A generic URL (for dynamically creating URLs)
# :param string path the rest of the URL

ACCOUNT_URL = r'https://account.pbs.org/'
# The root PBS account URL

# Authorization begins with a request to the AUTH_CLIENT_URL URL
# That request will send back a Location header that directs to the login URL
# Hitting that URL will send back an HTML page with the form on it as well as a CSRF Token cookie
# Logging in with the same login URL as the previous request will return another Location header
# that redirects back to the AUTH_CLIENT_URL, but with confirmed=1 tacked on the end
# Hitting that URL will send back one more Location header that redirects to a www.pbs.org URL
# that will set a session cookie for www.pbs.org that can then be used with the API

AUTH_CLIENT_URL = ACCOUNT_URL + r'oauth2/authorize/?scope=account+vppa&redirect_uri=' \
                  + ROOT_URL + r'login/&response_type=code&client_id={}'

# The OAuth response URL
# :param string client_id the client id

SHOWS_HTML_URL = ROOT_URL + r'shows/?genre={}&title=&station={}&alphabetically=true&layout=grid'
# The user-facing shows URL (for referer)
# :param string genre from the genre block of the SHOWS_JSON_URL response
# :param string pbsol the pbsol.station value from the COOKIE_URL response

DATA_JS_URL = ROOT_URL + r'static/js/shows-landing.js'
# There is no longer a JSON API for getting the genres
# This file has the genres, sources, and sort orders in it
# See DATA_REGEX

#
# JSON PAGES
#

COOKIE_URL = r'https://localization.services.pbs.org/localize/auto/cookie/'
# returns the cookie data needed for a proper station

CALLSIGN_URL = r'https://jaws.pbs.org/localization/false/?callsign={}'
# returns the data for the selected station

SHOWS_JSON_URL = ROOT_URL + r'shows-page/{!s}/?stationId={}&genre={}&title={}&source={}&alphabetically={}'
# Returns the list of shows with the given filters
# :param int page the page number (0-indexed)
# :param string station_id the pbsol.station_id value from the COOKIE_URL response
# :param string genre from the genre block of the SHOWS_JSON_URL response
# :param string title query for searching in titles
# :param string source (all-sources, station-only, passport-library)
# :param string alpha alphabetize the list, or sort by most popular (true=alpha | false=popular)

PERSONAL_URL = ROOT_URL + r'personal/'
# Returns personal data about the current user

STATION_SEARCH = ROOT_URL + r'search-videos/?page={!s}&q={}&rank=relevance&station_id={}'
# Run a generic search for shows
# :param int page the page number (1-indexed)
# :param string query the string to search for
# :param string station_id the pbsol.station_id value from the COOKIE_URL response

ADD_FAV_VIDEO = ROOT_URL + r'profile/addFavoriteVideo/{}/'
REMOVE_FAV_VIDEO = ROOT_URL + r'profile/removeFavoriteVideo/{}/'
# Add or remove a single video to the fav list
# :param string video_cid the cid from the SHOWS_JSON_URL response

ADD_FAV_SHOW = ROOT_URL + r'profile/addFavoriteShow/{}/'
REMOVE_FAV_SHOW = ROOT_URL + r'profile/removeFavoriteShow/{}/'
# Add or remove a whole show to the fav list
# :param string show_cid the cid from the SHOWS_JSON_URL response

ADD_FAV_PROGRAM = ROOT_URL + r'profile/addFavoriteProgram/{}/'
REMOVE_FAV_PROGRAM = ROOT_URL + r'profile/removeFavoriteProgram/{}/'
# Add or remove a program to the fav list
# :param string program_cid the cid from the SHOWS_JSON_URL response

FAV_SHOWS_URL = ROOT_URL + r'favorite-shows-page/{!s}/'
# The list of favorite shows
# :param int page the page number (1-indexed)

FAV_VIDEOS_URL = ROOT_URL + r'watchlist/page/{!s}/'
# The list of favorite videos
# :param int page the page number (1-indexed)

SEASONS_LIST_URL = ROOT_URL + r'show/{}/seasons-list/'
# The list of seasons that a given show has
# :param string the show slug from the SHOWS_JSON_URL response

EPISODES_LIST_URL = ROOT_URL + r'show/{}/seasons/{}/episodes/?start={!s}&limit={!s}'
# The list of episodes that a given show has in a given season
# :param string the show slug from the SEASONS_LIST_URL response
# :param string the season cid from the SEASONS_LIST_URL response
# :param int the start index (0-indexed)
# :param int the limit (max 24)

ALL_EPISODES_LIST_URL = ROOT_URL + r'show/{}/all-season-episodes/?start={!s}&limit={!s}'
# The full list of episodes that a given show has
# :param string the show slug from the SHOWS_JSON_URL response
# :param int the start index (0-indexed)
# :param int the limit (max 24)

SHOW_SPECIALS_LIST_URL = ROOT_URL + r'show/{}/show-specials/?start={!s}&limit={!s}'
# The full list of specials that a given show has
# :param string the show slug from the SHOWS_JSON_URL response
# :param int the start index (0-indexed)
# :param int the limit (max 24)

PLAYER_URL = r'https://player.pbs.org/portalplayer/{}/?uid={}&unsafePostMessages=true&unsafeDisableUpsellHref=true'
# The player URL that will return the redirect URLs for the .m3u8 or .mp4 format files
# :param string the legacy_tp_media_id from the episode list URLs
# :param string the pbs_uid for the user (self.pbsUid)


'''
REGEX CONSTANTS
'''

BOTH_SIDES = r"<[^>]+?(?:{}|{})"

CLIENT_ID_REGEX = r"client_id=(.+?)\b"
# Get the client ID from any page (SHOWS_URL)

ACTION_REGEX = r"""<form[^>]+?action\s*=\s*['"](.+?)['"][^>]+?method\s*=\s*['"]post['"]"""

CSRF_FRONT = r"""name\s*=\s*['"]csrfmiddlewaretoken\b[^>]+?value\s*=\s*['"](.+?)\b"""
CSRF_BACK = r"""value\s*=\s*['"](.+?)\b[^>]+?name\s*=\s*['"]csrfmiddlewaretoken\b"""
CSRF_TOKEN_REGEX = BOTH_SIDES.format(CSRF_FRONT, CSRF_BACK)
# Get the CSRF Token from the login page

LOGIN_FRONT = r"""name\s*=\s*['"]next\b[^>]+?value\s*=\s*['"](.+?)['"]"""
LOGIN_BACK = r"""value\s*=\s*['"](.+?)['"][^>]+?name\s*=\s*['"]next\b"""
LOGIN_NEXT_REGEX = BOTH_SIDES.format(LOGIN_FRONT, LOGIN_BACK)
# Get the 'next' URL from the login page

PLAYER_REDIRECT_REGEX = r"window.videoBridge\s*=\s*([^\r\n]+);[ \t]*[\r\n<]"
# Get the videoBridge object (JSON)

FUNCTION_REGEX = r"function\s*\(.*?\)\s*{\s*return\s*(\[\{.+?\}\])}\s*;"
DATA_REGEX = r"{0}\s*.*?getGenres.+?{0}\s*.*?getSources.+?{0}\s*.*?getSortMethods".format(FUNCTION_REGEX)
# Grab the data (genres, sources, and sort methods) from a JS file  =/


def log(txt):
    try:
        message = '{}}: {}'.format('plugin.video.pbs', txt.encode('ascii', 'ignore'))
        xbmc.log(msg=message, level=xbmc.LOGDEBUG)
    except:
        pass
