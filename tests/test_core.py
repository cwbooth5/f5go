"""unit tests for core.py"""

import pytest
import sys
import os

sys.path.append(os.path.dirname(os.path.realpath(__file__)) + "/../")

import go
import core


def test_malformed_linkdatabase():
    # pytest.set_trace()
    with pytest.raises(EOFError):
        core.LinkDatabase().load(db='tests/garbage.pickle')
