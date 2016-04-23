"""unit tests for core.py"""

import pytest

import core


def test_malformed_linkdatabase():
    # pytest.set_trace()
    with pytest.raises(EOFError):
        core.LinkDatabase().load(db='tests/garbage.pickle')
