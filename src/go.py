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
import urllib.request, urllib.parse, urllib.error
import configparser
import cherrypy
import jinja2
import random
import logging
from optparse import OptionParser

from core import ListOfLinks, Link, MYGLOBALS, InvalidKeyword
import tools

__author__ = "Saul Pwanson <saul@pwanson.com>"
__credits__ = "Bill Booth, Bryce Bockman, treebird"

config = configparser.ConfigParser()
config.read('go.cfg')

MYGLOBALS.cfg_urlFavicon = config.get('goconfig', 'cfg_urlFavicon')

try:
    MYGLOBALS.cfg_hostname = config.get('goconfig', 'cfg_hostname')
except configparser.NoOptionError:
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
            fqurl = f'{scheme}://{MYGLOBALS.cfg_hostname}'
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

        return self.redirect(url + "?" + urllib.parse.urlencode(kwargs))

    def redirectToEditList(self, listname, **kwargs):
        baseurl = "/_editlist_/%s?" % tools.escapekeyword(listname)
        return self.redirect(baseurl + urllib.parse.urlencode(kwargs))

    @cherrypy.expose
    def robots_txt(self):
        # only useful if something is crawling this site
        return open("robots.txt").read()


    @cherrypy.expose
    def favicon_ico(self):
        cherrypy.response.headers["Cache-control"] = "max-age=172800"
        return self.redirect(MYGLOBALS.cfg_urlFavicon, status=301)

    @cherrypy.expose
    def bootstrap_css(self):
        cherrypy.response.headers["Cache-control"] = "max-age=172800"
        cherrypy.response.headers["Content-Type"] = "text/css"
        return open("bootstrap.min.css").read()

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

        """User inputs a requested redirect.

        We render link.html and provide the template with:
        thelist == the ListOfLinks object
        keyword == the keyword they tried to create (requestedlink)
        """
        # log.debug('in /default, rest=%s, kwargs=%s' % (rest, kwargs))

        # uncomment this when we want to start using cookies again.
        # self.redirectIfNotFullHostname()

        # possible inputs:
        # seek
        # seek/name

        # TODO, try incrementing the click count on the list.
        tools.registerclick(listname=requestedlink)

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
        thelist = tools.ListOfLinks(keyword)
        tmplList = env.get_template('list.html')
        return tmplList.render(thelist=thelist, keyword=keyword)

        # check to see if it's an existing link.
        # with tools.redisconn() as r:
        #     if r.keys('godb|list|%s' % keyword):
        #         # already exists.
        #         ourlink = tools.getlink(linkname=keyword)
        #         listmeta = r.hgetall('godb|listmeta|%s' % keyword)  # list metadata behavior/clicks
        #         tmplList = env.get_template('list.html')
        #         return tmplList.render(linkobj=ourlink, listmeta=listmeta, keyword=keyword)
        #     else:
        #         # not found, so send to add page.
        #         # This 307 redirects back to /<theirkeyword> (goes back to cherrypy)
        #          # return self.redirect(tools.deampify('www.google.com'))


        #         tmplList = env.get_template('list.html')
        #         return tmplList.render(linkobj=None, listmeta=None, keyword=keyword)
        #         # return tmplList.render(linkobj=ourlink, listmeta=listmeta, keyword=keyword)


    @cherrypy.expose
    def special(self):
        LOG.debug('in /special...')
        LL = ListOfLinks(linkid=-1)
        LL.name = "Smart Keywords"
        LL.links = MYGLOBALS.g_db.getSpecialLinks()

        env.globals['MYGLOBALS.g_db'] = MYGLOBALS.g_db
        return env.get_template('list.html').render(L=LL, keyword="special")

    # @cherrypy.expose
    # def _login_(self, redirect=""):
    #     tools.getSSOUsername(redirect)
    #     if redirect:
    #         return self.redirect(redirect)
    #     return self.undirect()

    # @cherrypy.expose
    # def _link_(self, linkid):
    #     LOG.debug('in /_link_, linkid=%d' % linkid)
    #     link = MYGLOBALS.g_db.getLink(linkid)
    #     if link:
    #         link.clicked()
    #         return self.redirect(link.url(), status=301)

    #     cherrypy.response.status = 404
    #     return self.notfound("Link %s does not exist" % linkid)

    @cherrypy.expose
    def _add_(self, *args, **kwargs):
        """This adds a link ID to a list. The contents of the link
        are created in _modify_
        """
        LOG.debug('in /_add_, args=%s, kwargs=%s' % (args, kwargs))
        # _add_/tag1/tag2/tag3
        keyword = args[0]  # There has to be a better way!

        # make the link now.
        this_lol = tools.ListOfLinks(keyword)

        # This can't attach the ID to the list yet. do that on submit.
        link_id = tools.nextlinkid()

        # Create the link now.
        inputs = {'name': keyword}
        ThisLink = tools.Link(linkid=link_id)
        ThisLink.modify(**inputs)
        ourlink = tools.getlink(linkname=keyword)
        return env.get_template("editlink.html").render(linkobj=ourlink, returnto=(args and args[0] or None), **kwargs)


    @cherrypy.expose
    def _modify_(*args, **kwargs):
        """When someone adds a link to an existing list, this runs.

        The boilerplate link is now populated in the DB with data.
        """

        LOG.debug('in /_modify_, kwargs=%s' % kwargs)

        # Tack it onto the list of links.
        this_lol = tools.ListOfLinks(keyword=kwargs['lists'])

        # Idempotent, doesn't matter if we keep adding the same linkid.
        this_lol.addlink(kwargs['linkid'])

        # Using the form data entered by the user, populate the link.
        the_link = tools.Link(linkid=kwargs['linkid'])
        # import pdb;pdb.set_trace()
        the_link.modify(**kwargs)

        # username = tools.getSSOUsername()
        # linkid = kwargs.get("linkid", "")
        # title = tools.escapeascii(kwargs.get("title", ""))
        # lists = kwargs.get("lists", [])
        # url = kwargs.get("url", "")

        # # supposed to be space-delimited, TODO, need more boxes.
        # otherlists = kwargs.get("otherlists", "")

        returnto = kwargs.get("returnto", "")

        # # remove any whitespace/newlines in url
        # url = "".join(url.split())
        # tools.editlink(linkid, username, title=title, url=url,
        #                otherlists=otherlists)

        return Root().redirect("/." + returnto)


    @cherrypy.expose
    def _edit_(self, linkid, **kwargs):
        """To edit a link, we take in the linkid.

        We return to the template the url, title, and list membership.
        """
        LOG.debug('in /_edit_, linkid=%s, kwargs=%s' % (linkid, kwargs))
        with tools.redisconn() as r:
            ourlink = r.hgetall('godb|link|%s' % linkid)
        return env.get_template("editlink.html").render(linkobj=ourlink, **kwargs)

    @cherrypy.expose
    def _editlist_(self, keyword, **kwargs):
        LOG.debug('in /_editlist_, keyword=%s, kwargs=%s' % (keyword, kwargs))

        this_lol = tools.ListOfLinks(keyword)
        return env.get_template("list.html").render(thelist=this_lol,
                                                    keyword=keyword)

    @cherrypy.expose
    def _setbehavior_(self, keyword, **kwargs):
        LOG.debug('in /_setbehavior_, keyword=%s, kwargs=%s' % (keyword, kwargs))
        if "behavior" in kwargs:
            this_lol = tools.ListOfLinks(keyword)
            this_lol.behavior(desired=kwargs.get('behavior'))
            # import pdb;pdb.set_trace()
        return self.redirectToEditList(keyword)

    @cherrypy.expose
    def _delete_(self, linkid, returnto=""):
        """TODO: fill in"""
        # username = getSSOUsername()
        LOG.debug('in /_delete_, linkid=%s, returnto=%s' % (linkid, returnto))
        # import pdb;pdb.set_trace()
        tools.deletelink(linkid=linkid)
        return self.redirect("/." + returnto)

    @cherrypy.expose
    def _internal_(self, *args, **kwargs):
        LOG.debug('in /_internal_, args=%s, kwargs=%s' % (args, kwargs))
        # check, toplinks, special, dumplist
        return env.get_template(args[0] + ".html").render(**kwargs)

    @cherrypy.expose
    def toplinks(self, n="40"):
        LOG.info('In /toplinks...')
        return env.get_template("toplinks.html").render(numlinks=int(n))

    @cherrypy.expose
    def variables(self):
        return env.get_template("variables.html").render()

    @cherrypy.expose
    def help(self):
        return env.get_template("help.html").render()

    @cherrypy.expose
    def _override_vars_(self, **kwargs):

        LOG.debug('in /_override_vars_, kwargs=%s' % kwargs)
        cherrypy.response.cookie["variables"] = urllib.parse.urlencode(kwargs)
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
    LOG.debug("Cherrypy conf: %s", conf)

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
