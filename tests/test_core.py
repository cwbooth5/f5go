"""unit tests for core.py"""

import pytest
import sys
import os

sys.path.append(os.path.dirname(os.path.realpath(__file__)) + "/../")

import go
import core


def test_nextlinkid():
    """The link ID should come back as a number higher than zero."""
    mydb = core.LinkDatabase()
    assert mydb._nextlinkid > 0
