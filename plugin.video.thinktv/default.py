# -*- coding: utf-8 -*-
# KodiAddon 
#
from resources.lib.scraper import MyAddon
import re
import sys

# Start of Module

addonName = re.search(r'plugin://plugin.video.(.+?)/', str(sys.argv[0])).group(1)
ma = MyAddon(addonName)
ma.process_addon_event()

