"""Smaller helper functions and tools for the Go Redirector"""

import cgi
from dataclasses import dataclass
from typing import Any
import re
import string
import jinja2
import urllib.request, urllib.parse, urllib.error
import urllib.request, urllib.error, urllib.parse
import cherrypy
import urllib.parse
import time
import random
import datetime
import base64
import configparser
import redis
from contextlib import contextmanager
from collections import namedtuple


# config = ConfigParser.ConfigParser()
# config.read('go.cfg')

# cfg_hostname = config.get('goconfig', 'cfg_hostname')
# cfg_urlEditBase = "https://" + cfg_hostname
# cfg_urlSSO = config.get('goconfig', 'cfg_urlSSO')

class LinkNotAdded(Exception):
    """For some reason, a link was not added to a list."""
    pass

class BehaviorNotModified(Exception):
    """raised when it's not modified"""
    pass

class InsaneInput(Exception):
    """raised when input is completely bonkers."""
    pass

@contextmanager
def redisconn():
    rconn = redis.Redis(host='f5go-redis', port=6379, db=0, encoding='utf-8')
    try:
        yield rconn
    except:
        print("Error connecting to redis backend!")
        raise


def clickstats(linkname):
    pass

def nextlinkid():
    """Look at the attached redis db for a link ID. Initialize with that.
    Otherwise, it needs to be created so initialize it at 1.
    """
    # TODO: change to just incr() since that makes new keys.
    with redisconn() as r:
        nextid = r.get('godb|nextlinkid')
        if nextid is None:
            r.set('godb|nextlinkid', 1)  # Set it at 1, return 1.
            return 1
        r.incr('godb|nextlinkid')
        return int(nextid)

def registerclick(linkid=None, listname=None):
    """Increment the click count for either a link ID or a list name."""
    with redisconn() as rconn:
        if linkid:
            rconn.hincrby(name=f'godb|link|{linkid}', key='clicks')
            return True
        if listname:
            rconn.hincrby(name=f'godb|listmeta|{listname.lstrip(".")}', key='clicks')
            return True
        raise InsaneInput('specify linkid or listname!')


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
            target = target.decode('utf-8')
            if r.hget(target, 'name').decode('utf-8') == linkname:
                vals = r.hgetall(target)  # Grab all keys in the hash.
                vals_cleaned = recode_dict(subject=vals)
                # vals_cleaned = RecodedLink(**vals)
                lid = int(target.split('|')[-1])  # This is the link ID off the end of the hash name.
                ourlink = Link(linkid=lid, url=vals_cleaned['url'], title=vals_cleaned['title'],
                               owner=vals_cleaned['owner'], name=vals_cleaned['name'], clicks=int(vals_cleaned['clicks']), edits=getedits(lid))
                return ourlink
        # return None

@dataclass
class RecodedLink:
    name: str
    title: str
    url: str
    owner: str
    clicks: Any

    def __post_init__(self):
        '''The clicks field needs to be an integer.'''
        cleaned = {}
        for k, v in kwargs.items():
            try:
                key_decoded = k.decode('utf-8')
            except AttributeError:
                key_decoded = k  # already decoded
            try:
                val_decoded = v.decode('utf-8')
            except AttributeError:
                val_decoded = v
            cleaned[key_decoded] = val_decoded
            # if the value needs to be an integer, cast it now.
            try:
                cleaned[key_decoded] = int(val_decoded)
            except ValueError:
                pass
        for k, v in cleaned.items():
            self.k = v


def recode_dict(subject):
    """The datastructure coming back from redis calls encodes everything in byte strings
    so we have to convert dictionary keys back to the types we need.
    """
    cleaned = {}
    for k, v in subject.items():
        try:
            key_decoded = k.decode('utf-8')
        except AttributeError:
            key_decoded = k  # already decoded
        try:
            val_decoded = v.decode('utf-8')
        except AttributeError:
            val_decoded = v
        cleaned[key_decoded] = val_decoded
        # if the value needs to be an integer, cast it now.
        try:
            cleaned[key_decoded] = int(val_decoded)
        except ValueError:
            pass
    return cleaned


def getlistoflinks(linkname):
    """Return a list of link objects for all links in a given list name."""

    results = {}
    with redisconn() as rconn:
        for linkid in rconn.smembers('godb|list|%s' % linkname):
            results[linkid] = rconn.hgetall('godb|link|%s' % linkid)
    return results


def editlink(linkid, username, prune=None, *args, **kwargs):
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
    # registerclick(linkid=linkid)
    # breakpoint()
    with redisconn() as r:
        r.zadd(name=f'godb|edits|{linkid}', mapping={username: epoch_time})

        hashname = 'godb|link|%s' % linkid
        if kwargs.get('title'):
            r.hset(name=hashname, key='title', value=kwargs.get('title'))
        if kwargs.get('url'):
            r.hset(name=hashname, key='url', value=kwargs.get('url'))

        # lists to remove this link from, if they asked for it
        if prune:
            assert isinstance(prune, list), 'A list must be provided here!'
            for listname in prune:
                # list of names is passed in.
                r.srem('godb|list|%s' % listname, linkid)
        # else:
        #     # at least add it to their native list.
        #     r.sadd('godb|list|%s' % listname, linkid)

        # If they filled in a list to add this link to, add it to that list (if it exists)
        if kwargs.get('otherlists'):
            for extralist in kwargs.get('otherlists').split():
                if not r.sismember('godb|list|%s' % extralist, linkid):
                    r.sadd('godb|list|%s' % extralist, linkid)

class Link:
    def __init__(self, linkid):
        self.linkid = int(linkid)
        self.boilerplate = {'name': 'somename',
                            'title': None,
                            'url': None,
                            'owner': 'usergo',
                            'clicks': 0}

    def modify(self, **kwargs):
        """modify a given link

        kwargs could include:
        title (sentence describing it)
        url
        owner (user who initially added the link)
        name
        clicks
        """
        # Any keyword args supplied are set on the link in redis.
        # This could be an add or an update. Works with both.

        # URLs all need to be cleaned up.
        testurl = kwargs.get('url')
        if testurl:
            sanitized = sanitary(testurl)
            if sanitized:
                kwargs['url'] = sanitized
            else:
                raise InsaneInput('Entered URL is insane!')
        # breakpoint()

        with redisconn() as rconn:
            if not rconn.exists('godb|link|%s' % self.linkid):
                # TODO: boilerplate is a dict..and we store as a string??

                for k, v in self.boilerplate.items():
                    #TODO, hack, do this earlier..
                    if v is None:
                        if k in ['url', 'title']:
                            self.boilerplate[k] = ""
                        else:
                            self.boilerplate[k] = "blankness"
                print(self.boilerplate)
                rconn.hmset(f'godb|link|{self.linkid}', self.boilerplate)

            for key, val in kwargs.items():
                # Check if it's a valid field.
                if key in ['name', 'title', 'url', 'owner', 'clicks']:
                    rconn.hset('godb|link|%s' % self.linkid, key, val)
            # TODO, edits need to be on the list of links too.
            # run the edit function
            epoch_time = float(time.time())
            rconn.zadd(name=f'godb|edits|{self.linkid}', mapping={'usergo': epoch_time})


class ListOfLinks(object):
    def __init__(self, keyword):
        self.keyword = keyword
        self.listname = f'godb|list|{self.keyword}'

    def exists(self):
        """Return True if this list of links already exists in the database."""
        with redisconn() as rconn:
            return rconn.exists(self.listname)
            # todo: could check if metadata was there too.

    def init_list(self):
        """Construct a new empty list container and all metadata."""
        # new_id = nextlinkid()  # make a new ID
        with redisconn() as rconn:
            # NOTE the set for this list is created when first link added.
            # create the new list in redis. Metadata first.
            listmeta = {'behavior': 'freshest',
                        'clicks': 0}
            rconn.hmset(f'godb|listmeta|{self.keyword}', listmeta)

            # Mark that link as being edited by the current user.
            # epoch_time = float(time.time())
            # rconn.zadd('godb|edits|%s' % new_id, 'usergo', epoch_time)

    def refresh(self):
        """grab new data out of redis."""
        pass

    def addlink(self, linkid):
        """Add a new link to the current list of links.
        If the list doesn't exist, it is created.

        This is adding a number to a set in redis.

        return the link ID that was added.
        """
        assert isinstance(linkid, int)
        # new_id = nextlinkid()  # make a new ID

        # bring the list into existence if this is the first link.
        if not self.exists():
            self.init_list()

        # if not rconn.sismember(self.listname, linkid):
        with redisconn() as rconn:
            rconn.sadd(self.listname, linkid)

        return linkid

    def removelink(self, linkid):
        """Remove a link from the list.

        If the list is empty after the removal, the list is removed completely.
        """
        # run the edit function on the list. #TODO
        assert isinstance(linkid, int)
        with redisconn() as rconn:
            rconn.srem(self.listname, linkid)

        # If the length of the list is empty, delete the keyword from redis.
        if len(self.members()) == 0:
            with redisconn() as rconn:
                listmetaname = f'godb|listmeta|{self.keyword}'
                rconn.delete(self.listname, listmetaname)

    def behavior(self, desired=None):
        """Using a list name, get the list's behavior.
        If 'desired' is set, set the list's redirect behavior.

        Returns the current behavior.
        Otherwise, returns True if the behavior was changed.
        """
        with redisconn() as rconn:
            listmetaname = f'godb|listmeta|{self.keyword}'
            if desired:
                rconn.hset(listmetaname, 'behavior', desired)
            return rconn.hget(name=listmetaname, key='behavior').decode('utf-8')

    def listmeta(self):
        """return dictionary of list metadata"""
        with redisconn() as rconn:
            return rconn.hgetall(f'godb|listmeta|{self.keyword}')

    def members(self):
        # return all link objects under this keyword/list.
        # use a dictionary of linkid: {link object dict}
        return getlistoflinks(self.keyword)

    def __len__(self):
        """Provides the number of links for a given keyword."""
        return len(self.members())


def deletelink(linkid):
    """Remove all traces of a link using the link ID."""
    with redisconn() as rconn:
        rconn.delete(f'godb|link|{linkid}')
        rconn.delete(f'godb|edits|{linkid}')
        all_keys = rconn.keys('godb|list|*')
        # remove the link from any list it lives within.
        for linklist in all_keys:
            rconn.srem(linklist, linkid)

def addtolist(keyword, link_id):
    """Make this idempotent. Add to a list."""
    with redisconn() as r:
        # now add the link ID to this new list.
        r.sadd(f'godb|list|{keyword}', link_id)
    registerclick(listname=keyword)


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
    print(count)
    blabber = []
    with redisconn() as r:
        for key in [x.decode('utf-8') for x in r.keys('godb|listmeta|*')]:
            # breakpoint()
            listname = key.split('|')[-1]
            listclicks = r.hget(key, 'clicks')
            blabber.append((listname, int(listclicks)))

    if count:
        return sorted(blabber, key=lambda tup: tup[1])[:count]
    return sorted(blabber, key=lambda tup: tup[1])

def toplists(count=None):
    """Return all the top lists by number of members!"""
    pass


def getlistmembership(linkid):
    """Take in a link ID and return all lists which it is a member."""
    results = []
    with redisconn() as r:
        # inefficient, iterating through every list here.. TODO
        all_lists = r.keys('godb|list|*')
        for key in all_lists:
            if str(linkid) in r.smembers(key):
                listname = key.split(b'|')[-1]
                results.append(listname)

    return results




# new stuff up above this line...


def byClicks(links):
    # return sorted(links, key=lambda L: (-L.recentClicks, -L.totalClicks))
    pass


def sanitary(s):
    """Return a sanitized string.

    Lowercase the whole thing.
    All characters must be one of the following:
    - lower case letters.
    - digits
    - minus (-)
    - period (.)

    Returns the sanitized string. Returns None if it couldn't be cleaned.
    """

    s = s.lower()
    sanechars = string.ascii_lowercase + string.digits + "-."
    # Search through everything but the last character.
    for a in s[:-1]:
        if a not in sanechars:
            return None

    # if the final character isn't a slash and is not sane..
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
    # return string.replace(s, "&amp;", "&")
    return s.replace("&amp;", "&")


def escapeascii(s):
    return cgi.escape(s).encode("ascii", "xmlcharrefreplace")


def randomlink(global_obj):
    """Take in the class of globals and select a random link from the database."""
    try:
        selection = random.choice([x for x in list(global_obj.g_db.linksById.values()) if not x.isGenerative() and x.usage()])
    except IndexError:
        # Nothing there yet, just return None and move on.
        return None
    else:
        return selection


def today():
    return datetime.date.today().toordinal()


def escapekeyword(kw):
    return urllib.parse.quote_plus(kw, safe="/")


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
    if isinstance(s, str):
        return [s]
    elif isinstance(s, list):
        return s
    else:
        return list(s)


def getDictFromCookie(cookiename):
    if cookiename not in cherrypy.request.cookie:
        return {}

    cherrypy.request.cookie[cookiename].value
    return dict(urllib.parse.parse_qsl(cherrypy.request.cookie[cookiename].value))


def getCurrentEditableUrl():
    cfg_urlEditBase = "http://"  # hack, TODO
    redurl = cfg_urlEditBase + cherrypy.request.path_info
    if cherrypy.request.query_string:
        redurl += "?" + cherrypy.request.query_string

    return redurl


def getCurrentEditableUrlQuoted():
    return urllib.parse.quote(getCurrentEditableUrl(), safe=":/")


def getSSOUsername(redirect=True):
    """ """
    return 'testuser'
    # if cherrypy.request.base != cfg_urlEditBase:
    #     if not redirect:
    #         return None
    #     if redirect is True:
    #         redirect = getCurrentEditableUrl()
    #     elif redirect is False:
    #         raise cherrypy.HTTPRedirect(redirect)

    # if "issosession" not in cherrypy.request.cookie:
    #     if not redirect:
    #         return None
    #     if redirect is True:
    #         redirect = cherrypy.url(qs=cherrypy.request.query_string)

    #     raise cherrypy.HTTPRedirect(cfg_urlSSO + urllib.parse.quote(redirect, safe=":/"))

    # sso = urllib.parse.unquote(cherrypy.request.cookie["issosession"].value)
    # # session = list(map(base64.b64decode, string.split(sso, "-")))
    # session = list(map(base64.b64decode, sso.split("-")))
    # return session[0]
