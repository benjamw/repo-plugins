import time
import datetime

from addon import language
import hof

"""
color: a hex color string (RRGGBB or #RRGGBB) or None
"""


def colorize(text, color):
    if not color:
        return text
    if color.startswith('#'):
        color = color[1:]
    return '[COLOR ff' + color + ']' + text + '[/COLOR]'


def format_title_and_subtitle(title, subtitle=None):
    label = u'[B]{title}[/B]'.format(title=title)
    # suffixes
    if subtitle:
        label += u' - {subtitle}'.format(subtitle=subtitle)
    return label


def parse_date(datestr):
    # remove timezone info
    datestr = datestr[0:25]
    date = None
    # workaround for datetime.strptime not working (NoneType ???)
    try:
        date = datetime.datetime.strptime(datestr, '%a, %d %b %Y %H:%M:%S')
    except TypeError:
        date = datetime.datetime.fromtimestamp(time.mktime(
            time.strptime(datestr, '%a, %d %b %Y %H:%M:%S')))
    return date


def past_week():
    today = datetime.date.today()
    one_day = datetime.timedelta(days=1)

    for i in xrange(0, 8):  # TODO: find better interval
        yield today - (one_day * i)