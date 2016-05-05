"""Unit tests for go.py

To run these: run 'tox' in the root project directory.
"""

import pytest
import cherrypy
from cherrypy.test import helper
import sys
import os

sys.path.append(os.path.dirname(os.path.realpath(__file__)) + "/../")

import go

class BasicGoTest(helper.CPWebCase):
    """Test the web service itself."""
    def setup_server():
        """Subclass the Root() class from within go.py."""
        class Root(go.Root):
            """Use a non-standard port, start the server."""
            # cherrypy.config.update({'server.socket_port': 9090})
            cherrypy.config.update({'port': 35900})
        cherrypy.tree.mount(Root())

    setup_server = staticmethod(setup_server)

    def test_index_page(self):
        self.getPage('/')
        # pytest.set_trace()
        self.assertStatus('303 See Other')

    def test_help_page(self):
        """200 OK on help.html, searching for a string in the HTML body"""
        self.getPage('/help')
        self.assertStatus('200 OK')
        self.assertInBody('a mnemonic URL shortener and a link database')

    def test_special_page(self):
        """200 OK on exposed /special, searching for a string in the HTML body"""
        self.getPage('/special')
        self.assertStatus('200 OK')
        self.assertInBody('Smart Keywords')

    def test_add_new_link_statuscode(self):
        """Adding a new link returns a 303."""
        self.getPage('/somenewlink')
        self.assertStatus('303 See Other')

    def test_addpage(self):
        self.getPage('/somenewlink')
        self.assertStatus('303 See Other')  # correct HTTP status
        self.getPage('/_add_/somenewlink')  # direct add link syntax
        self.assertStatus('200 OK')
        self.assertInBody('<title>Add Link</title>')  # it rendered
        # pytest.set_trace()
