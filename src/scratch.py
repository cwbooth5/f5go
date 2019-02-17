#!/usr/bin/env python

import tools
import string
import random
import time


def getlists():
    """Return all lists, sorted by clicks."""
    pass


def editlist(listname, username, prune=None, **kwargs):
    """A list is identified by its name.
    Pass in a dict of keyword arguments, each specifying a field in the hash for that list.
    fields added to the listmeta can be:
    - 'behavior' (str)
    - 'clicks' (int)
    fields added to the list:
    - linkid (int)

    prune = list of link IDs to remove
    """
    # make sure a list exits. redis already does this.

    # bump the edit zset for this list.
    epoch_time = float(time.time())
    with tools.redisconn() as r:
        r.zadd('godb|edits|%s' % listname, username, epoch_time)

    # actually edit to list.
    with tools.redisconn() as r:
        # They added a link to the list.
        if kwargs.get('linkid') and not prune:
            r.lpush(kwargs.get('linkid'), 'godb|list|%s' % listname)
        elif kwargs.get('linkid'):
            # They want to remove the link from the list.
            r.lrem(name='godb|list|%s' % listname, count=0, value=kwargs.get('linkid'))

        # r.hmset('godb|listmeta|')


    # on exit, modify the edit time and last user to edit the list.






def populate_garbage():
    with tools.redisconn() as r:

        # modify some new key in a hash name
        # g = r.keys('godb|link*')
        # import pdb; pdb.set_trace()
        # for name in g:
        #   r.hset(name, 'clicks', 1)

        # make a mock database.
        # blow everything away.

        print('flush database..')
        r.flushall()

        # make new lists, each with a single link.
        username = 'billbo'
        for linkid, name in enumerate(string.ascii_lowercase):
            boilerplate = {'name': name,
                           'title': 'placeholder',
                           'url': 'http://www.%s.com' % name,
                           'owner': username,
                           'clicks': random.choice(range(200))}
            r.hmset('godb|link|%s' % linkid, boilerplate)

            # Mark that link as being edited by the current user.
            epoch_time = float(time.time())
            # import pdb; pdb.set_trace()
            r.zadd('godb|edits|%s' % linkid, username, epoch_time)

            # if a list doesn't already exist for this link, make one. Add this to it.
            existinghash = r.hkeys('godb|listmeta|%s' % name)
            if not existinghash:
                template = {'behavior': 'freshest',
                            'clicks': random.choice(range(200))}
                r.hmset('godb|listmeta|%s' % name, template)

                # now add the link ID to this new list.
                r.sadd('godb|list|%s' % name, linkid)
            # import pdb; pdb.set_trace()
            print("created: %s with ID %s" % (name, linkid))
            print("done.")

        # randomize some stuff within the lists.
        # Add a couple other links to each list.
        # allkeys = r.keys('godb|list|*')
        # import pdb; pdb.set_trace()
        # print 'duh'
        allkeys = r.keys('godb|list|*')
        all_links = r.keys('godb|link|*')
        for listkey in allkeys:
            selection = random.choice(allkeys)
            listid = selection.split('|')[-1]
            print("random list to modify: %s " % listkey)
            for x in range(random.choice(range(15))):
                # push the random number onto the list of links.
                targetkey = random.choice(all_links)
                targetlistid = targetkey.split('|')[-1]
                r.sadd(selection, targetlistid)

# populate_garbage()

with tools.redisconn() as r:
    print('flush database..')
    r.flushall()


# mylink = tools.ListOfLinks(keyword='harp')
# import pdb;pdb.set_trace()