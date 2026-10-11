from urllib.parse import unquote

import pytest

from agentshield.config import Settings


def make(**kw):
    return Settings(_env_file=None, **kw)


def test_full_uri_wins():
    s = make(mongodb_uri="mongodb+srv://u:p@h/", mongodb_host="other")
    assert s.resolved_mongodb_uri() == "mongodb+srv://u:p@h/"


def test_assembles_from_parts_and_escapes_password():
    s = make(mongodb_host="cluster0.abc.mongodb.net", mongodb_user="me", mongodb_password="p@ss:w/rd")
    uri = s.resolved_mongodb_uri()
    assert uri.startswith("mongodb+srv://me:")
    assert "@cluster0.abc.mongodb.net/" in uri
    creds = uri.split("//", 1)[1].rsplit("@", 1)[0]
    assert unquote(creds.split(":", 1)[1]) == "p@ss:w/rd"
    assert creds.count("@") == 0


def test_missing_parts_raises_clear_error():
    with pytest.raises(ValueError, match="MONGODB_HOST"):
        make(mongodb_user="me", mongodb_password="x").resolved_mongodb_uri()
