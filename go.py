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
import sys
import urllib
import ConfigParser
import cherrypy
import jinja2
import random
from optparse import OptionParser

from core import ListOfLinks, Link, MYGLOBALS, InvalidKeyword, log
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
        # Specifically for the internal GSA
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
    def default(self, *rest, **kwargs):
        log.debug('in /default, rest=%s, kwargs=%s' % (rest, kwargs))
        self.redirectIfNotFullHostname()

        keyword = rest[0]
        rest = rest[1:]

        forceListDisplay = False
        # action = kwargs.get("action", "list")

        if keyword[0] == ".":  # force list page instead of redirect
            forceListDisplay = True
            keyword = keyword[1:]

        if rest:
            keyword += "/"
        elif forceListDisplay and cherrypy.request.path_info[-1] == "/":
            # allow go/keyword/ to redirect to go/keyword but go/.keyword/
            #  to go to the keyword/ index
            keyword += "/"

        # try it as a list
        try:
            ll = MYGLOBALS.g_db.getList(keyword, create=False)
        except InvalidKeyword as e:
            return self.notfound(str(e))

        if not ll:  # nonexistent list
            # check against all special cases
            matches = []
            for R in MYGLOBALS.g_db.regexes.values():
                matches.extend([(R, L, genL) for L, genL in R.matches(keyword)])

            if not matches:
                kw = tools.sanitary(keyword)
                if not kw:
                    return self.notfound("No match found for '%s'" % keyword)

                # serve up empty fake list
                return env.get_template('list.html').render(L=ListOfLinks(linkid=0), keyword=kw)
            elif len(matches) == 1:
                R, L, genL = matches[0]  # actual regex, generated link
                R.clicked()
                L.clicked()
                return self.redirect(tools.deampify(genL.url()))
            else:  # len(matches) > 1
                LL = ListOfLinks(linkid=-1)  # -1 means non-editable
                LL.links = [genL for R, L, genL in matches]
                return env.get_template('list.html').render(L=LL, keyword=keyword)

        listtarget = ll.getDefaultLink()

        if listtarget and not forceListDisplay:
            ll.clicked()
            listtarget.clicked()
            return self.redirect(tools.deampify(listtarget.url()))

        tmplList = env.get_template('list.html')
        return tmplList.render(L=ll, keyword=keyword)

    @cherrypy.expose
    def special(self):
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
        log.debug('in /_link_, linkid=%d' % linkid)
        link = MYGLOBALS.g_db.getLink(linkid)
        if link:
            link.clicked()
            return self.redirect(link.url(), status=301)

        cherrypy.response.status = 404
        return self.notfound("Link %s does not exist" % linkid)

    @cherrypy.expose
    def _add_(self, *args, **kwargs):
        log.debug('in /_add_, args=%s, kwargs=%s' % (args, kwargs))
        # _add_/tag1/tag2/tag3
        link = Link()
        link.lists = [MYGLOBALS.g_db.getList(listname, create=False) or ListOfLinks(linkid=0, name=listname) for listname in args]
        return env.get_template("editlink.html").render(L=link, returnto=(args and args[0] or None), **kwargs)

    @cherrypy.expose
    def _edit_(self, linkid, **kwargs):
        log.debug('in /_edit_, linkid=%s, kwargs=%s' % (linkid, kwargs))
        link = MYGLOBALS.g_db.getLink(linkid)
        if link:
            return env.get_template("editlink.html").render(L=link, **kwargs)

        # edit new link
        return env.get_template("editlink.html").render(L=Link(), **kwargs)

    @cherrypy.expose
    def _editlist_(self, keyword, **kwargs):
        log.debug('in /_editlist_, keyword=%s, kwargs=%s' % (keyword, kwargs))
        K = MYGLOBALS.g_db.getList(keyword, create=False)
        if not K:
            K = ListOfLinks()
        return env.get_template("list.html").render(L=K, keyword=keyword)

    @cherrypy.expose
    def _setbehavior_(self, keyword, **kwargs):
        log.debug('in /_setbehavior_, keyword=%s, kwargs=%s'(keyword, kwargs))
        K = MYGLOBALS.g_db.getList(keyword, create=False)

        if "behavior" in kwargs:
            K._url = kwargs["behavior"]

        return self.redirectToEditList(keyword)

    @cherrypy.expose
    def _delete_(self, linkid, returnto=""):
        # username = getSSOUsername()
        log.debug('in /_delete_, linkid=%s, returnto=%s' % (linkid, returnto))
        MYGLOBALS.g_db.deleteLink(MYGLOBALS.g_db.getLink(linkid))

        return self.redirect("/." + returnto)

    @cherrypy.expose
    def _modify_(self, **kwargs):
        log.debug('in /_modify_, kwargs=%s' % kwargs)

        username = tools.getSSOUsername()

        linkid = kwargs.get("linkid", "")
        title = tools.escapeascii(kwargs.get("title", ""))
        lists = kwargs.get("lists", [])
        url = kwargs.get("url", "")
        otherlists = kwargs.get("otherlists", "")

        returnto = kwargs.get("returnto", "")

        # remove any whitespace/newlines in url
        url = "".join(url.split())

        if type(lists) not in [tuple, list]:
            lists = [lists]

        lists.extend(otherlists.split())

        if linkid:
            link = MYGLOBALS.g_db.getLink(linkid)
            if link._url != url:
                MYGLOBALS.g_db._changeLinkUrl(link, url)
            link.title = title

            newlistset = []
            for listname in lists:
                if "{*}" in url:
                    if listname[-1] != "/":
                        listname += "/"
                try:
                    newlistset.append(MYGLOBALS.g_db.getList(listname, create=True))
                except:
                    return self.redirectToEditLink(error="invalid keyword '%s'" % listname, **kwargs)

            for LL in newlistset:
                if LL not in link.lists:
                    LL.addLink(link)

            for LL in [x for x in link.lists]:
                if LL not in newlistset:
                    LL.removeLink(link)
                    if not LL.links:
                        MYGLOBALS.g_db.deleteList(LL)

            link.lists = newlistset

            link.editedBy(username)

            MYGLOBALS.g_db.save()

            return self.redirect("/." + returnto)

        if not lists:
            return self.redirectToEditLink(error="delete links that have no lists", **kwargs)

        if not url:
            return self.redirectToEditLink(error="URL required", **kwargs)

        # if url already exists, redirect to that link's edit page
        if url in MYGLOBALS.g_db.linksByUrl:
            link = MYGLOBALS.g_db.linksByUrl[url]

            # only modify lists; other fields will only be set if there
            # is no original

            combinedlists = set([x.name for x in link.lists]) | set(lists)

            fields = {'title': link.title or title,
                      'lists': " ".join(combinedlists),
                      'linkid': str(link.linkid)
                      }

            return self.redirectToEditLink(error="found identical existing URL; confirm changes and re-submit", **fields)

        link = MYGLOBALS.g_db.addLink(lists, url, title, username)

        MYGLOBALS.g_db.save()
        return self.redirect("/." + returnto)

    @cherrypy.expose
    def _internal_(self, *args, **kwargs):
        log.debug('in /_internal_, args=%s, kwargs=%s' % (args, kwargs))
        # check, toplinks, special, dumplist
        return env.get_template(args[0] + ".html").render(**kwargs)

    @cherrypy.expose
    def toplinks(self, n="100"):
        return env.get_template("toplinks.html").render(n=int(n))

    @cherrypy.expose
    def variables(self):
        return env.get_template("variables.html").render()

    @cherrypy.expose
    def help(self):
        return env.get_template("help.html").render()

    @cherrypy.expose
    def _override_vars_(self, **kwargs):
        log.debug('in /_override_vars_, kwargs=%s' % kwargs)
        cherrypy.response.cookie["variables"] = urllib.urlencode(kwargs)
        cherrypy.response.cookie["variables"]["max-age"] = 10 * 365 * 24 * 3600

        return self.redirect("/variables")

    @cherrypy.expose
    def _set_variable_(self, varname="", value=""):
        log.debug('in /_set_variable_, varname=%s, value=%s' % (varname,  value))
        if varname and value:
            MYGLOBALS.g_db.variables[varname] = value
            MYGLOBALS.g_db.save()

        return self.redirect("/variables")


def main(opts):
    cherrypy.config.update({'server.socket_host': '::',
                            'server.socket_port': MYGLOBALS.cfg_listenPort,
                            'request.query_string_encoding': "latin1",
                            })

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
    print "Cherrypy conf: %s" % conf

    if opts.runas:
        # Check for requested user, raises KeyError if they don't exist.
        pwent = pwd.getpwnam(opts.runas)
        # Drop privs to requested user, raises OSError if not privileged.
        cherrypy.process.plugins.DropPrivileges(
            cherrypy.engine, uid=pwent.pw_uid, gid=pwent.pw_gid).subscribe()
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
