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
import redis
from contextlib import contextmanager
from collections import namedtuple


# config = ConfigParser.ConfigParser()
# config.read('go.cfg')

# cfg_hostname = config.get('goconfig', 'cfg_hostname')
# cfg_urlEditBase = "https://" + cfg_hostname
# cfg_urlSSO = config.get('goconfig', 'cfg_urlSSO')


@contextmanager
def redisconn():
    rconn = redis.Redis(host='localhost', port=6379, db=0)
    yield rconn


def clickstats(linkname):
    pass


def getedits(link_id, mostrecent=False):
    """Return a list of tuples for all edits on a given link ID. Return the most recent
    edit if mostrecent == True.
    """
    with redisconn() as r:
        if mostrecent:
            # just one tuple to return
            return r.zrange('godb|edits|%s' % link_id, -1, -1, withscores=True)[0]
        # return the whole list of tuples
        return r.zrange('godb|edits|%s' % link_id, 0, -1, withscores=True)



def getlink(linkname):
    """Snag link data using only the name. Return a named tuple."""

    Link = namedtuple('Link', 'linkid url title owner name clicks edits')

    # TODO: inefficient. need to really target it first, not iterate through everything.
    with redisconn() as r:
        all_links = r.keys('godb|link|*')
        for target in all_links:
            if r.hget(target, 'name') == linkname:
                vals = r.hgetall(target)  # Grab all keys in the hash.
                lid = target.split('|')[-1]  # This is the link ID off the end of the hash name.
                ourlink = Link(linkid=lid, url=vals['url'], title=vals['title'],
                               owner=vals['owner'], name=vals['name'], clicks=vals['clicks'], edits=getedits(lid))
                return ourlink


def editlink(linkid, username, prune=None, **kwargs):
    """Modify a link.
    When a link gets edited, one of many fields can be changed.
    - title
    - url
    - list membership

    Other stuff can change:
    - the link can be deleted.
    - The link can be added to another list.
    - The link can be removed from a list. (uncheck the checkbox)
    """
    epoch_time = float(time.time())
    with tools.redisconn() as r:
        r.zadd('godb|edits|%s' % linkid, username, epoch_time)

        name = 'godb|link|%s' % linkid
        if kwargs.get('title'):
            r.hset(name=name, key='title', value=kwargs.get('title'))
        if kwargs.get('url'):
            r.hset(name=name, key='url', value=kwargs.get('url'))

        # lists to remove this link from, if they asked for it
        if prune:
            assert isinstance(prune, list), 'A list must be provided here!'
            for listname in prune:
                # list of names is passed in.
                r.srem('godb|list|%s' % listname, linkid)

        # If they filled in a list to add this link to, add it to that list (if it exists)
        if not r.sismember('godb|list|%s' % listname, linkid):
            r.sadd('godb|list|%s' % listname, linkid)





def toplinks(count=None):
    """Return a sorted list of all links by number of clicks.
    returns:
    title
    linkid
    url
    memberof lists

    return the number of links they ask for, or everything if they don't specify.
    """
    # list of dicts
    print count
    blabber = []
    with redisconn() as r:
        allkeys = r.keys('godb|listmeta|*')
        for key in allkeys:
            listname = key.split('|')[-1]
            listclicks = r.hget(key, 'clicks')
            blabber.append((listname, int(listclicks)))

    if count:
        return sorted(blabber, key=lambda tup: tup[1])[:count]
    return sorted(blabber, key=lambda tup: tup[1])

print toplinks()



































# new stuff up above this line...


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
    try:
        selection = random.choice([x for x in global_obj.g_db.linksById.values() if not x.isGenerative() and x.usage()])
    except IndexError:
        # Nothing there yet, just return None and move on.
        return None
    else:
        return selection


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
    # dt = time.time()
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
