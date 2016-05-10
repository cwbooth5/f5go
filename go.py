#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""This is the Go Redirector. It uses short mnemonics as redirects to otherwise
long URLs. Few remember how to write in cursive, most people don't remember
common phone numbers, and just about everyone needs a way around bookmarks.
"""

import os
import os.path
import pwd
import socket
import time
import sys
import urllib
import ConfigParser
import cherrypy
import jinja2
import random
import logging
from optparse import OptionParser

from core import ListOfLinks, Link, MYGLOBALS, InvalidKeyword
import tools

__author__ = "Saul Pwanson <saul@pwanson.com>"
__credits__ = "Bill Booth, Bryce Bockman, treebird"

config = ConfigParser.ConfigParser()
config.read('go.cfg')

MYGLOBALS.cfg_urlFavicon = config.get('goconfig', 'cfg_urlFavicon')

try:
    MYGLOBALS.cfg_hostname = config.get('goconfig', 'cfg_hostname')
except ConfigParser.NoOptionError:
    MYGLOBALS.cfg_hostname = socket.gethostbyname(socket.gethostname())

MYGLOBALS.cfg_urlSSO = config.get('goconfig', 'cfg_urlSSO')
MYGLOBALS.cfg_urlEditBase = "https://" + MYGLOBALS.cfg_hostname
MYGLOBALS.cfg_listenPort = int(config.get('goconfig', 'cfg_listenPort'))

LOG = logging.getLogger(__name__)
LOGDB = logging.getLogger('db')

LOG_CONF = {
    'version': 1,

    'formatters': {
        'void': {
            'format': ''
        },
        'standard': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        },
    },
    'handlers': {
        'default': {
            'level':'INFO',
            'class':'logging.StreamHandler',
            'formatter': 'standard',
            'stream': 'ext://sys.stdout'
        },
        'cherrypy_console': {
            'level':'INFO',
            'class':'logging.StreamHandler',
            'formatter': 'void',
            'stream': 'ext://sys.stdout'
        },
        'cherrypy_access': {
            'level':'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'formatter': 'void',
            'filename': 'access.log',
            'maxBytes': 10485760,
            'backupCount': 20,
            'encoding': 'utf8'
        },
        'cherrypy_error': {
            'level':'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'formatter': 'void',
            'filename': 'errors.log',
            'maxBytes': 10485760,
            'backupCount': 20,
            'encoding': 'utf8'
        },
    },
    'loggers': {
        '': {
            'handlers': ['default'],
            'level': 'DEBUG'
        },
        'db': {
            'handlers': ['default'],
            'level': 'DEBUG' ,
            'propagate': False
        },
        'cherrypy.access': {
            'handlers': ['cherrypy_access'],
            'level': 'INFO',
            'propagate': False
        },
        'cherrypy.error': {
            'handlers': ['cherrypy_console', 'cherrypy_error'],
            'level': 'INFO',
            'propagate': False
        },
    }
}
logging.config.dictConfig(LOG_CONF)

def config_jinja():
    """Construct a jinja environment, provide filters and globals
    to templates.
    """
    env = jinja2.Environment(loader=jinja2.FileSystemLoader("."))
    env.filters['time_t'] = tools.prettytime
    env.filters['int'] = int
    env.filters['escapekeyword'] = tools.escapekeyword
    env.globals["enumerate"] = enumerate
    env.globals["sample"] = random.sample
    env.globals["len"] = len
    env.globals["min"] = min
    env.globals["str"] = str
    env.globals["list"] = tools.makeList
    env.globals.update(globals())
    return env


class Root(object):
    env = config_jinja()
    def redirect(self, url, status=307):
        """HTTP 307 redirect to another URL."""
        cherrypy.response.status = status
        cherrypy.response.headers["Location"] = url

    def undirect(self):
        raise cherrypy.HTTPRedirect(cherrypy.request.headers.get("Referer", "/"))

    def notfound(self, msg):
        return env.get_template("notfound.html").render(message=msg)

    def redirectIfNotFullHostname(self, scheme=None):
        if scheme is None:
            scheme = cherrypy.request.scheme

        # redirect to our full hostname to get the user's cookies
        if cherrypy.request.scheme != scheme or cherrypy.request.base.find(MYGLOBALS.cfg_hostname) < 0:
            fqurl = scheme + "://" + MYGLOBALS.cfg_hostname
            fqurl += cherrypy.request.path_info
            if cherrypy.request.query_string:
                fqurl += "?" + cherrypy.request.query_string
            raise cherrypy.HTTPRedirect(fqurl)

    def redirectToEditLink(self, **kwargs):
        if "linkid" in kwargs:
            url = "/_edit_/%s" % kwargs["linkid"]
            del kwargs["linkid"]
        else:
            url = "/_add_"

        return self.redirect(url + "?" + urllib.urlencode(kwargs))

    def redirectToEditList(self, listname, **kwargs):
        baseurl = "/_editlist_/%s?" % tools.escapekeyword(listname)
        return self.redirect(baseurl + urllib.urlencode(kwargs))

    @cherrypy.expose
    def robots_txt(self):
        return file("robots.txt").read()

    @cherrypy.expose
    def favicon_ico(self):
        cherrypy.response.headers["Cache-control"] = "max-age=172800"
        return self.redirect(MYGLOBALS.cfg_urlFavicon, status=301)

    @cherrypy.expose
    def bootstrap_css(self):
        cherrypy.response.headers["Cache-control"] = "max-age=172800"
        cherrypy.response.headers["Content-Type"] = "text/css"
        return file("bootstrap.min.css").read()

    @cherrypy.expose
    def lucky(self):
        luckylink = random.choice(MYGLOBALS.g_db.getNonFolders())
        luckylink.clicked()
        return self.redirect(tools.deampify(luckylink.url()))

    @cherrypy.expose
    def index(self, **kwargs):
        self.redirectIfNotFullHostname()

        if "keyword" in kwargs:
            return self.redirect("/" + kwargs["keyword"])

        return env.get_template('index.html').render(now=tools.today())

    @cherrypy.expose
    def default(self, requestedlink):
        # log.debug('in /default, rest=%s, kwargs=%s' % (rest, kwargs))

        # uncomment this when we want to start using cookies again.
        # self.redirectIfNotFullHostname()

        # possible inputs:
        # seek
        # seek/name
        keyword_raw, _, remainder = requestedlink.partition('/')

        forceListDisplay = False
        # action = kwargs.get("action", "list")

        if requestedlink[0] == ".":  # force list page instead of redirect
            forcelistdisplay = True
            keyword = keyword_raw[1:]
        else:
            keyword = keyword_raw
            # return a edit template here. TODO

        #TODO this is where we would sanitize whatever they entered in the box.
        # check to see if it's an existing link.
        with tools.redisconn() as r:
            if r.keys('godb|list|%s' % keyword):
                # already exists.
                ourlink = tools.getlink(linkname=keyword)
                listmeta = r.hgetall('godb|listmeta|%s' % keyword)  # list metadata behavior/clicks
                tmplList = env.get_template('list.html')
                return tmplList.render(linkobj=ourlink, listmeta=listmeta, keyword=keyword)
            else:
                # not found, so send to add page.
                # This 307 redirects back to /<theirkeyword> (goes back to cherrypy)
                 # return self.redirect(tools.deampify('www.google.com'))

                
                tmplList = env.get_template('list.html')
                return tmplList.render(linkobj=None, listmeta=None, keyword=keyword)
                # return tmplList.render(linkobj=ourlink, listmeta=listmeta, keyword=keyword)


    @cherrypy.expose
    def special(self):
        LOG.debug('in /special...')
        LL = ListOfLinks(linkid=-1)
        LL.name = "Smart Keywords"
        LL.links = MYGLOBALS.g_db.getSpecialLinks()

        env.globals['MYGLOBALS.g_db'] = MYGLOBALS.g_db
        return env.get_template('list.html').render(L=LL, keyword="special")

    @cherrypy.expose
    def _login_(self, redirect=""):
        tools.getSSOUsername(redirect)
        if redirect:
            return self.redirect(redirect)
        return self.undirect()

    @cherrypy.expose
    def _link_(self, linkid):
        LOG.debug('in /_link_, linkid=%d' % linkid)
        link = MYGLOBALS.g_db.getLink(linkid)
        if link:
            link.clicked()
            return self.redirect(link.url(), status=301)

        cherrypy.response.status = 404
        return self.notfound("Link %s does not exist" % linkid)

    @cherrypy.expose
    def _add_(self, *args, **kwargs):
        LOG.debug('in /_add_, args=%s, kwargs=%s' % (args, kwargs))
        # _add_/tag1/tag2/tag3
        # TODO: move all the add code here from /default
        # This is the attachment to the list of links.
        keyword = args[0]
        with tools.redisconn() as r:
            # create the new list in redis. Metadata first.
            listmeta = {'behavior': 'freshest',
                        'clicks': 0}
            r.hmset('godb|listmeta|%s' % keyword, listmeta)

            # create a link at a new ID.
            new_id = tools.nextlinkid()
            boilerplate = {'name': keyword,
                           'title': None,
                           'url': None,
                           'owner': 'usergo',
                           'clicks': 0}
            r.hmset('godb|link|%s' % new_id, boilerplate)

            # Mark that link as being edited by the current user.
            epoch_time = float(time.time())
            r.zadd('godb|edits|%s' % new_id, 'usergo', epoch_time)

            # now add the link ID to this new list.
            r.sadd('godb|list|%s' % keyword, new_id)

        # This link is now created. It's not added to the list until
        # after the user inputs everything to annotate the link.
        ourlink = tools.getlink(linkname=keyword)
        assert ourlink is not None


        # take in a keyword, find the link ID for that keyword, add that ID to the list.
        # with tools.redisconn() as r:
        #     link_id = tools.getlink(args[0]).linkid
        #     r.sadd('godb|list|%s' % args[0], link_id)

        # ourlink = tools.getlink(linkname=args[0])

        return env.get_template("editlink.html").render(linkobj=ourlink, returnto=(args and args[0] or None), **kwargs)

    @cherrypy.expose
    def _edit_(self, linkid, **kwargs):
        LOG.debug('in /_edit_, linkid=%s, kwargs=%s' % (linkid, kwargs))
        # link = MYGLOBALS.g_db.getLink(linkid)
        # if link:
        #     return env.get_template("editlink.html").render(L=link, **kwargs)

        # # edit new link
        # return env.get_template("editlink.html").render(L=Link(), **kwargs)

    @cherrypy.expose
    def _editlist_(self, keyword, **kwargs):
        LOG.debug('in /_editlist_, keyword=%s, kwargs=%s' % (keyword, kwargs))
        ourlink = tools.getlink(linkname=keyword)
        with tools.redisconn() as r:
            listmeta = r.hgetall('godb|listmeta|%s' % keyword)
        return env.get_template("list.html").render(linkobj=ourlink, 
                                                    keyword=keyword,
                                                    listmeta=listmeta)

    @cherrypy.expose
    def _setbehavior_(self, keyword, **kwargs):
        LOG.debug('in /_setbehavior_, keyword=%s, kwargs=%s' % (keyword, kwargs))     
        if "behavior" in kwargs:
            with tools.redisconn() as r:
                r.hset(name='godb|listmeta|%s' % keyword,
                       key='behavior',
                       value=kwargs.get('behavior'))
        return self.redirectToEditList(keyword)

    @cherrypy.expose
    def _delete_(self, linkid, returnto=""):
        # username = getSSOUsername()
        LOG.debug('in /_delete_, linkid=%s, returnto=%s' % (linkid, returnto))
        with tools.redisconn() as r:
            # remove the link ID from any lists it's in.
            for listname in tools.getlistmembership(linkid):
                r.srem('godb|list|%s' % listname, linkid)

                # remove the listmeta for this list name, but only if it's empty now.
                # if r.scard('godb|list|%s' % listname):
                if not r.keys('godb|list|%s' % listname):
                    r.delete('godb|listmeta|%s' % listname)

            # remove all the edit history.
            r.delete('godb|edits|%s' % linkid)

            # remove the link itself.
            r.delete('godb|link|%s' % linkid)
        return self.redirect("/." + returnto)

    @cherrypy.expose
    def _modify_(self, **kwargs):
        LOG.debug('in /_modify_, kwargs=%s' % kwargs)
        

        username = tools.getSSOUsername()

        linkid = kwargs.get("linkid", "")
        title = tools.escapeascii(kwargs.get("title", ""))
        lists = kwargs.get("lists", [])
        url = kwargs.get("url", "")

        # supposed to be space-delimited, TODO, need more boxes.
        otherlists = kwargs.get("otherlists", "")

        returnto = kwargs.get("returnto", "")

        # remove any whitespace/newlines in url
        url = "".join(url.split())
        tools.editlink(linkid, username, title=title, url=url,
                       otherlists=otherlists)
        # if type(lists) not in [tuple, list]:
        #     lists = [lists]

        # lists.extend(otherlists.split())

        # if linkid:
        #     link = MYGLOBALS.g_db.getLink(linkid)
        #     if link._url != url:
        #         MYGLOBALS.g_db._changeLinkUrl(link, url)
        #     link.title = title

        #     newlistset = []
        #     for listname in lists:
        #         if "{*}" in url:
        #             if listname[-1] != "/":
        #                 listname += "/"
        #         try:
        #             newlistset.append(MYGLOBALS.g_db.getList(listname, create=True))
        #         except:
        #             return self.redirectToEditLink(error="invalid keyword '%s'" % listname, **kwargs)

        #     for LL in newlistset:
        #         if LL not in link.lists:
        #             LL.addLink(link)

        #     for LL in [x for x in link.lists]:
        #         if LL not in newlistset:
        #             LL.removeLink(link)
        #             if not LL.links:
        #                 MYGLOBALS.g_db.deleteList(LL)

        #     link.lists = newlistset

        #     link.editedBy(username)

        #     MYGLOBALS.g_db.save()

        #     return self.redirect("/." + returnto)

        # if not lists:
        #     return self.redirectToEditLink(error="delete links that have no lists", **kwargs)

        # if not url:
        #     return self.redirectToEditLink(error="URL required", **kwargs)

        # # if url already exists, redirect to that link's edit page
        # if url in MYGLOBALS.g_db.linksByUrl:
        #     link = MYGLOBALS.g_db.linksByUrl[url]

        #     # only modify lists; other fields will only be set if there
        #     # is no original

        #     combinedlists = set([x.name for x in link.lists]) | set(lists)

        #     fields = {'title': link.title or title,
        #               'lists': " ".join(combinedlists),
        #               'linkid': str(link.linkid)
        #               }

        #     return self.redirectToEditLink(error="found identical existing URL; confirm changes and re-submit", **fields)

        # link = MYGLOBALS.g_db.addLink(lists, url, title, username)

        # MYGLOBALS.g_db.save()
        return self.redirect("/." + returnto)

    @cherrypy.expose
    def _internal_(self, *args, **kwargs):
        LOG.debug('in /_internal_, args=%s, kwargs=%s' % (args, kwargs))
        # check, toplinks, special, dumplist
        return env.get_template(args[0] + ".html").render(**kwargs)

    @cherrypy.expose
    def toplinks(self, n="100"):
        LOG.info('In /toplinks...')
        return env.get_template("toplinks.html").render(n=int(n))

    @cherrypy.expose
    def variables(self):
        return env.get_template("variables.html").render()

    @cherrypy.expose
    def help(self):
        return env.get_template("help.html").render()

    @cherrypy.expose
    def _override_vars_(self, **kwargs):
        LOG.debug('in /_override_vars_, kwargs=%s' % kwargs)
        cherrypy.response.cookie["variables"] = urllib.urlencode(kwargs)
        cherrypy.response.cookie["variables"]["max-age"] = 10 * 365 * 24 * 3600

        return self.redirect("/variables")

    @cherrypy.expose
    def _set_variable_(self, varname="", value=""):
        LOG.debug('in /_set_variable_, varname=%s, value=%s' % (varname,  value))
        if varname and value:
            MYGLOBALS.g_db.variables[varname] = value
            MYGLOBALS.g_db.save()

        return self.redirect("/variables")


def main(opts):

    cherrypy.config.update({'server.socket_host': '::',
                            'server.socket_port': MYGLOBALS.cfg_listenPort,
                            'request.query_string_encoding': "latin1",
                            'log.access_file': 'access.log',
                            'log.error_file': 'error.log',
                            'log.screen': False
                            })
    cherrypy.engine.unsubscribe('graceful', cherrypy.log.reopen_files)
    
    # cherrypy.https = s = cherrypy._cpserver.Server()
    # s.socket_host = '::'
    # s.socket_port = 443
    # s.ssl_module = 'pyopenssl'
    # s.ssl_certificate = 'go.crt'
    # s.ssl_private_key = 'go.key'
    # s.ssl_certificate_chain = 'gd_bundle.crt'
    # s.subscribe()

    # checkpoint the database every 60 seconds
    # cherrypy.process.plugins.BackgroundTask(60, lambda: MYGLOBALS.g_db.save()).start()
    file_path = os.getcwd().replace("\\", "/")
    conf = {'/images': {"tools.staticdir.on": True, "tools.staticdir.dir": file_path + "/images"}}
    LOG.debug("Cherrypy conf: %s" % conf)

    if opts.runas:
        # Check for requested user, raises KeyError if they don't exist.
        pwent = pwd.getpwnam(opts.runas)
        # Drop privs to requested user, raises OSError if not privileged.
        cherrypy.process.plugins.DropPrivileges(
            cherrypy.engine, uid=pwent.pw_uid, gid=pwent.pw_gid).subscribe()
    cherrypy.config.update(conf)  # hack? TODO
    cherrypy.quickstart(Root(), "/", config=conf)

env = config_jinja()

if __name__ == "__main__":
    
    parser = OptionParser()
    parser.add_option("-i", dest="importfile", action="store",
                      help="Import a link database from a file.")
    parser.add_option("-e", action="store", dest="exportfile",
                      help="Export a link database to a file.")
    parser.add_option("--dump", dest="dump", action="store_true",
                      help="Dump the db to stdout.")
    parser.add_option("--runas", dest="runas",
                      help="Run as the provided user.")
    (opts, args) = parser.parse_args()
    if opts.importfile:
        MYGLOBALS.g_db._import(opts.importfile)
    elif opts.exportfile:
        MYGLOBALS.g_db._export(opts.exportfile)
    elif opts.dump:
        MYGLOBALS.g_db._dump(sys.stdout)
    else:
        env = config_jinja()
        main(opts)
