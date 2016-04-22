import ConfigParser
import pickle
import os
import shutil
import tempfile
import sys

from tools import *

config = ConfigParser.ConfigParser()
config.read('go.cfg')

cfg_fnDatabase = config.get('goconfig', 'cfg_fnDatabase')


class LinkDatabase:
    def __init__(self):
        self.regexes = {}        # regex -> RegexList
        self.lists = {}          # listname -> ListOfLinks
        self.variables = {}      # varname -> value
        self.linksById = {}      # link.linkid -> Link
        self.linksByUrl = {}     # link._url -> Link
        self._nextlinkid = 1

    def __repr__(self):
        return '%s(regexes=%s, lists=%s, vars=%s, byId=%s, byUrl=%s)' % (self.__class__.__name__,
                                                                         self.regexes, self.lists,
                                                                         self.variables,
                                                                         self.linksById,
                                                                         self.linksByUrl)

    @staticmethod
    def load(db=cfg_fnDatabase):
        """Attempt to load the database defined at cfg_fnDatabase. Create a
        new one if the database doesn't already exist.
        """
        try:
            print "Loading DB from %s" % db
            return pickle.load(file(db))
        except IOError:
            print sys.exc_info()[1]
            print "Creating new database..."
            return LinkDatabase()

    def save(self):
        BACKUPS = 5
        dbdir = os.path.dirname(cfg_fnDatabase)
        (fd, tmpname) = tempfile.mkstemp(dir=dbdir)
        f = os.fdopen(fd, "w")
        pickle.dump(self, f)
        f.flush()
        f.close()
        for i in reversed(range(BACKUPS - 1)):
            fromfile = "%s-%s" % (cfg_fnDatabase, i)
            tofile = "%s-%s" % (cfg_fnDatabase, i + 1)
            if os.path.exists(fromfile):
                shutil.move(fromfile, tofile)
        if os.path.exists(cfg_fnDatabase):
            shutil.move(cfg_fnDatabase, cfg_fnDatabase + "-0")
        shutil.move(tmpname, cfg_fnDatabase)

    def nextlinkid(self):
        r = self._nextlinkid
        self._nextlinkid += 1
        return r

    def addRegexList(self, regex=None, url=None, desc=None, owner=""):
        r = RegexList(self.nextlinkid(), regex)
        r._url = url
        self._addRegexList(r, owner)

    def _addRegexList(self, r, owner):
        self.regexes[r.regex] = r
        self._addList(r)     # add to all indexes

    def addLink(self, lists, url, title, owner=""):
        if url in self.linksByUrl:
            raise RuntimeError("existing url")

        if type(lists) == str:
            lists = lists.split()

        link = Link(self.nextlinkid(), url, title)

        for kw in lists:
            self.getList(kw, create=True).addLink(link)

        self._addLink(link, owner)

        return link

    def _addLink(self, link, editor=None):
        if editor:
            link.editedBy(editor)

        self.linksById[link.linkid] = link
        self.linksByUrl[link._url] = link

    def _changeLinkUrl(self, link, newurl):
        if link._url in self.linksByUrl:
            del self.linksByUrl[link._url]
        link._url = newurl
        self.linksByUrl[newurl] = link

    def _addList(self, LL):
        self.lists[LL.name] = LL

    def deleteLink(self, link):
        for LL in list(link.lists):
            LL.removeLink(link)
            if not LL.links:  # auto-delete lists with no links
                self.deleteList(LL)

        self._removeLinkFromUrls(link._url)

        if link.linkid in self.linksById:
            del self.linksById[link.linkid]

        if isinstance(link, RegexList):
            del self.regexes[link.regex]

        return "deleted go/%s" % link.linkid

    def _removeLinkFromUrls(self, url):
        if url in self.linksByUrl:
            del self.linksByUrl[url]

    def deleteList(self, LL):
        for link in list(LL.links):
            L.removeLink(link)

        del self.lists[LL.name]
        self.deleteLink(LL)
        return "deleted go/%s" % LL.name

    def getLink(self, linkid):
        return self.linksById.get(int(linkid), None)

    def getAllLists(self):
        return byClicks(self.lists.values())

    def getSpecialLinks(self):
        links = set()
        # TODO, do we have to check the database here??
        for R in self.load().regexes.values():
            links.update(R.links)

        links.update(self.getFolders())

        return list(links)

    def getFolders(self):
        return [x for x in self.linksById.values() if x.isGenerative()]

    def getNonFolders(self):
        return [x for x in self.linksById.values() if not x.isGenerative()]

    def getList(self, listname, create=False):
        if "\\" in listname:  # is a regex
            return self.getRegex(listname, create)

        sanelistname = sanitary(listname)

        if not sanelistname:
            raise InvalidKeyword("keyword '%s' not sanitary" % listname)

        if sanelistname not in self.lists:
            if not create:
                return None
            self._addList(ListOfLinks(self.nextlinkid(), sanelistname, redirect="freshest"))

        return self.lists[sanelistname]

    def getRegex(self, listname, create=False):
        try:
            re.compile(listname)
        except:
            raise InvalidKeyword(listname)

        if listname not in self.regexes:
            if not create:
                return None
            self._addRegexList(RegexList(self.nextlinkid(), listname), "")

        return self.regexes[listname]

    def renameList(self, LL, newname):
        assert newname not in self.lists
        oldname = LL.name
        self.lists[newname] = self.lists[oldname]
        del self.lists[oldname]
        LL.name = newname
        return "renamed go/%s to go/%s" % (oldname, LL.name)

    def _export(self, fn):
        print "exporting to %s" % fn
        with file(fn, "w") as f:
            for k, v in self.variables.items():
                f.write("variable %s %s\n" % (k, v))

            for L in self.linksById.values():
                f.write(L._export() + "\n")

            for LL in self.lists.values():
                f.write(LL._export() + "\n")

    # for the tsv dumper
    def _dump(self, fh):
        for link in self.linksById.values():
            fh.write(link._dump() + "\n")

    def _import(self, fn):
        print "importing from %s" % fn
        with file(fn, "r") as f:
            for l in f.readlines():
                if not l.strip(): continue
                print l.strip()
                a, b = string.split(l, " ", 1)
                if a == "regex":
                    R = RegexList(self.nextlinkid())
                    R._import(b)
                elif a == "link":
                    L = Link(self.nextlinkid())
                    L._import(b)
                    self._addLink(L)
                elif a == "list":
                    listname, rest = string.split(b, " ", 1)
                    if listname in self.lists:
                        LL = self.lists[listname]
                    else:
                        LL = ListOfLinks(self.nextlinkid())
                    LL._import(b)
                elif a == "variable":
                    k, v = b.split(" ", 1)
                    self.variables[k] = v.strip()

        assert self._nextlinkid == max(self.linksById.keys()) + 1

        self.save()

class Clickable:
    def __init__(self):
        self.archivedClicks = 0
        self.clickData = {}

    def __repr__(self):
        return '%s(archivedClicks=%s, clickData=%s)' % (self.__class__.__name__,
                                                        self.archivedClicks,
                                                        self.clickData)

    def clickinfo(self):
        return "%s recent clicks (%s total); last visited %s" % (self.recentClicks, self.totalClicks, prettyday(self.lastClickDay))

    def __getattr__(self, attrname):
        if attrname == "totalClicks":
            return self.archivedClicks + sum(self.clickData.values())
        elif attrname == "recentClicks":
            return sum(self.clickData.values())
        elif attrname == "lastClickTime":
            if not self.clickData:
                return 0
            maxk = max(self.clickData.keys())
            return time.mktime(datetime.date.fromordinal(maxk).timetuple())
        elif attrname == "lastClickDay":
            if not self.clickData:
                return 0
            return max(self.clickData.keys())
        else:
            raise AttributeError(attrname)

    def clicked(self, n=1):
        todayord = today()
        if todayord not in self.clickData:
            # partition clickdata around 30 days ago
            archival = []
            recent = []
            for od, nclicks in self.clickData.items():
                if todayord - 30 > od:
                    archival.append((od, nclicks))
                else:
                    recent.append((od, nclicks))

            # archive older samples
            if archival:
                self.archivedClicks += sum(nclicks for od, nclicks in archival)

            # recent will have at least one sample if it was ever clicked
            recent.append((todayord, n))
            self.clickData = dict(recent)
        else:
            self.clickData[todayord] += n

    def _export(self):
        return "%d,%s" % (self.archivedClicks, "".join(str(self.clickData).split()))

    def _import(self, s):
        archivedClicks, clickdict = s.split(",", 1)
        self.archivedClicks = int(archivedClicks)
        self.clickData = eval(clickdict)
        return self


class Link(Clickable):
    def __init__(self, linkid=0, url="", title=""):
        Clickable.__init__(self)

        self.linkid = linkid
        self._url = canonicalUrl(url)
        self.title = title

        self.edits = []    # (edittime, editorname); [-1] is most recent
        self.lists = []    # List() instances

    def __repr__(self):
        return '%s(linkid=%s, url=%s, title=%s, edits=%s, lists=%s)' % (self.__class__.__name__,
                                                                        self.linkid, self._url,
                                                                        self.title, self.edits,
                                                                        self.lists)

    def isGenerative(self):
        return any([K.isGenerative() for K in self.lists])

    def listnames(self):
        return [x.name for x in self.lists]

    def _export(self):
        a = "+".join(self._url.split())
        b = "||".join([x.name for x in self.lists]) or "None"
        c = Clickable._export(self)
        d = ",".join(["%d/%s" % x for x in self.edits]) or "None"
        e = self.title

        return "link %s %s %s %s %s" % (a, b, c, d, e)

    def _dump(self):
        a = "|".join([x.name for x in self.lists]) or "None"
        b = self.title
        c = self._url

        return "%s\t%s\t%s" % (a, b, c)

    def _import(self, line):
        self._url, lists, clickdata, edits, title = line.split(" ", 4)
        print ">>", line
        print self._url
        if self._url in MYGLOBALS.g_db.linksByUrl:
            self._url = MYGLOBALS.g_db.linksByUrl[self._url].linkid
            print "XYZ", self._url

        if lists != "None":
            for listname in lists.split("||"):
                if "{*}" in self._url:
                    if listname[-1] != "/":
                        listname += "/"
                MYGLOBALS.g_db.getList(listname, create=True).addLink(self)

        self.title = title.strip()

        Clickable._import(self, clickdata)

        if edits != "None":
            edits = [x.split("/") for x in edits.split(",")]
            self.edits = [(float(x[0]), x[1]) for x in edits]

    def editedBy(self, editor):
        self.edits.append((time.time(), editor))

    def lastEdit(self):
        if not self.edits:
            return (0, "")

        return self.edits[-1]

    def href(self):
        if self.isGenerative():
            kw = self.mainKeyword()
            if kw:
                return "/.%s" % escapekeyword(kw.name)
            else:
                return ""
        else:
            if self.linkid > 0:
                return "/_link_/%s" % self.linkid
            else:
                return self._url

    def url(self, keyword=None, args=None):
        remainingPath = (keyword or cherrypy.request.path_info).split("/")[2:]
        d = {"*": "/".join(remainingPath), "0": keyword}
        d.update(MYGLOBALS.g_db.variables)
        d.update(getDictFromCookie("variables"))

        while True:
            try:
                return string.Formatter().vformat(self._url, args or remainingPath, d)
            except KeyError as e:
                missingKey = e.args[0]
                d[missingKey] = "{%s}" % missingKey
            except IndexError as e:
                return None

    def mainKeyword(self):
        goesStraightThere = [LL for LL in self.lists if LL.goesDirectlyTo(self)]

        if not goesStraightThere:
            return None

        return byClicks(goesStraightThere)[0]

    def usage(self):
        kw = self.mainKeyword()
        if kw is None:
            return ""
        return kw.usage()

    def opacity(self, todayord):
        """goes from 1.0 (today) to 0.2 (a month ago)"""
        dtDays = todayord - self.lastClickDay
        c = min(1.0, max(0.2, (30.0 - dtDays) / 30))
        return "%.02f" % c


class ListOfLinks(Link):
    # for convenience, inherits from Link.  most things that apply
    # to Link applies to a ListOfLinks too
    def __init__(self, linkid=0, name="", redirect="freshest"):
        Link.__init__(self, linkid)
        self.name = name
        self._url = redirect  # list | freshest | top | random
        self.links = []

    def __repr__(self):
        return '%s(linkid=%s, name=%s, redirect=%s, links=%s)' % (self.__class__.__name__,
                                                                  self.linkid, self.name,
                                                                  self._url, self.links)


    def isGenerative(self):
        return self.name[-1] == "/"

    def usage(self):
        if self.isGenerative():  # any([ L.isGenerative() for L in self.links ]):
            return "%s..." % self.name

        return self.name

    def addLink(self, link):
        if link not in self.links:
            self.links.insert(0, link)
            link.lists.append(self)

    def removeLink(self, link):
        if link in self.links:
            self.links.remove(link)
        if self in link.lists:
            link.lists.remove(self)

    def getRecentLinks(self):
        return self.links

    def getPopularLinks(self):
        return byClicks(self.links)

    def getLinks(self, nDaysOfRecentEdits=1):
        earliestRecentEdit = time.time() - nDaysOfRecentEdits * 24 * 3600

        recent = [x for x in self.links if x.lastEdit()[0] > earliestRecentEdit]
        popular = self.getPopularLinks()

        for L in recent:
            popular.remove(L)

        return recent, popular

    def getDefaultLink(self):
        if not self._url or self._url == "list":
            return None
        elif self._url == "top":
            return self.getPopularLinks()[0]
        elif self._url == "random":
            return random.choice(self.links)
        elif self._url == "freshest":
            return self.getRecentLinks()[0]
        else:
            return MYGLOBALS.g_db.getLink(self._url)

    def url(self, keyword=None, args=None):
        if not self._url or self._url == "list":
            return None
        elif self._url == "top":
            return self.getPopularLinks()[0].url(keyword, args)
        elif self._url == "random":
            return random.choice(self.links).url(keyword, args)
        elif self._url == "freshest":
            return self.getRecentLinks()[0].url(keyword, args)
        else:  # should be a linkid
            return "/_link_/" + self._url

    def goesDirectlyTo(self, link):
        return self._url == str(link.linkid) or self.url() == link.url()

    def _export(self):
        if is_int(self._url): # linkid needs to be converted for export
            L = MYGLOBALS.g_db.getLink(self._url)
            if L and L in self.links:
                print L
                self._url = L._url
            else:
                print "fixing unknown dest linkid for", self.name
                self._url = "list"

        return ("list %s " % self.name) + Link._export(self)

    def _import(self, line):
        self.name, _, rest = line.split(" ", 2)
        assert _ == "link"
        MYGLOBALS.g_db._addList(self)
        Link._import(self, rest)


class RegexList(ListOfLinks):
    def __init__(self, linkid=0, regex=""):
        ListOfLinks.__init__(self, linkid, regex)

        self.regex = regex

    def __repr__(self):
        return '%s(linkid=%s, regex=%s)' % (self.__class__.__name__,
                                            self.linkid, self.regex)

    def usage(self):
        return self.regex

    def isGenerative(self):
        return True

    def matches(self, kw=None):
        if kw is None:
            kw = cherrypy.request.path_info.split("/")[1]

        ret = []

        m = re.match(self.regex, kw, re.IGNORECASE)
        if m:
            deflink = self.getDefaultLink()
            for L in deflink and [deflink] or self.links:
                url = L.url(keyword=kw, args=(m.group(0)) + m.groups())
                ret.append((L, Link(0, url, L.title)))

        return ret

    def url(self, kw=None):

        if kw is None:
            kw = cherrypy.request.path_info.split("/")[1]

        m = re.match(self.regex, kw, re.IGNORECASE)
        if not m:
            return None

        return ListOfLinks.url(self, keyword=kw, args=(m.group(0)) + m.groups())

    def _export(self):
        return ("regex %s " % self.regex) + ListOfLinks._export(self)

    def _import(self, line):
        self.regex, _, rest = line.split(" ", 2)
        assert _ == "list"
        ListOfLinks._import(self, rest)