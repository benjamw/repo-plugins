#!/usr/bin python2

import os
from pprint import pprint
from resources.lib.pbs import PBS, PBSSettings

alpha = False
enable_login = True
username = 'chelseawelker@gmail.com'
password = 'Nova!8166'
cj_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'PBSCookies.dat')

settings = PBSSettings(alpha, enable_login, username, password, cj_file)

pbs = PBS(settings)

ret = pbs.get_genres()
pprint(ret)
print len(ret['items'])

ret = pbs.get_shows('science-and-nature')  # genre id
pprint(ret)
print len(ret['items'])

ret = pbs.get_seasons('nature')  # show slug
pprint(ret)
print len(ret['items'])

ret = pbs.get_episodes('newshour', 'b953fad6-32ad-45c6-88c2-136d6ed675d7', 1)  # show slug, season cid, page
pprint(ret)
print len(ret['items'])

ret = pbs.get_shows('favorites')
pprint(ret)
print len(ret['items'])

pprint(vars(pbs))


