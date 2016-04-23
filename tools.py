"""Smaller helper functions and tools for the Go Redirector"""

import cgi
import re
import string
import jinja2
import urllib
import urllib2
import cherrypy
import urlparse
import time
import random
import datetime
import base64
import ConfigParser


config = ConfigParser.ConfigParser()
config.read('go.cfg')

cfg_hostname = config.get('goconfig', 'cfg_hostname')
cfg_urlEditBase = "https://" + cfg_hostname
cfg_urlSSO = config.get('goconfig', 'cfg_urlSSO')


def byClicks(links):
    return sorted(links, key=lambda L: (-L.recentClicks, -L.totalClicks))

sanechars = string.lowercase + string.digits + "-."


def sanitary(s):

    s = string.lower(s)
    for a in s[:-1]:
        if a not in sanechars:
            return None

    if s[-1] not in sanechars and s[-1] != "/":
        return None

    return s


def canonicalUrl(url):
    if url:
        m = re.search(r'href="(.*)"', jinja2.utils.urlize(url))
        if m:
            return m.group(1)
        return url


def deampify(s):
    """Replace '&amp;'' with '&'."""
    return string.replace(s, "&amp;", "&")


def escapeascii(s):
    return cgi.escape(s).encode("ascii", "xmlcharrefreplace")


def randomlink(global_obj):
    """Take in the class of globals and select a random link from the database."""
    return random.choice([x for x in global_obj.g_db.linksById.values() if not x.isGenerative() and x.usage()])


def today():
    return datetime.date.today().toordinal()


def escapekeyword(kw):
    return urllib.quote_plus(kw, safe="/")


def prettyday(d):
    if d < 10:
        return 'never'

    s = today() - d
    if s < 1:
        return 'today'
    elif s < 2:
        return 'yesterday'
    elif s < 60:
        return '%d days ago' % s
    else:
        return '%d months ago' % (s / 30)


def prettytime(t):
    if t < 100000:
        return 'never'

    dt = time.time() - t
    if dt < 24 * 3600:
        return 'today'
    elif dt < 2 * 24 * 3600:
        return 'yesterday'
    elif dt < 60 * 24 * 3600:
        return '%d days ago' % (dt / (24 * 3600))
    else:
        return '%d months ago' % (dt / (30 * 24 * 3600))


def is_int(s):
    try:
        int(s)
        return True
    except:
        return False


def makeList(s):
    if isinstance(s, basestring):
        return [s]
    elif isinstance(s, list):
        return s
    else:
        return list(s)


def getDictFromCookie(cookiename):
    if cookiename not in cherrypy.request.cookie:
        return {}

    cherrypy.request.cookie[cookiename].value
    return dict(urlparse.parse_qsl(cherrypy.request.cookie[cookiename].value))


def getCurrentEditableUrl():
    redurl = cfg_urlEditBase + cherrypy.request.path_info
    if cherrypy.request.query_string:
        redurl += "?" + cherrypy.request.query_string

    return redurl


def getCurrentEditableUrlQuoted():
    return urllib2.quote(getCurrentEditableUrl(), safe=":/")


def getSSOUsername(redirect=True):
    """ """
    return 'testuser'
    if cherrypy.request.base != cfg_urlEditBase:
        if not redirect:
            return None
        if redirect is True:
            redirect = getCurrentEditableUrl()
        elif redirect is False:
            raise cherrypy.HTTPRedirect(redirect)

    if "issosession" not in cherrypy.request.cookie:
        if not redirect:
            return None
        if redirect is True:
            redirect = cherrypy.url(qs=cherrypy.request.query_string)

        raise cherrypy.HTTPRedirect(cfg_urlSSO + urllib2.quote(redirect, safe=":/"))

    sso = urllib2.unquote(cherrypy.request.cookie["issosession"].value)
    session = map(base64.b64decode, string.split(sso, "-"))
    return session[0]
