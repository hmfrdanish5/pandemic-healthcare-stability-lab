"""Comment store validation (parameterized SQL, length limits)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pandemic_dashboard.comments_store import (
    MAX_COMMENT_LEN,
    MAX_NAME_LEN,
    add_comment,
    delete_own_comment,
    init_db,
    list_comments,
    update_comment,
)


def test_comment_rejects_empty_and_too_long():
    init_db()
    try:
        add_comment(" ", "hello")
        assert False
    except ValueError:
        pass
    try:
        add_comment("n", "")
        assert False
    except ValueError:
        pass
    try:
        add_comment("n" * (MAX_NAME_LEN + 1), "ok")
        assert False
    except ValueError:
        pass
    try:
        add_comment("n", "x" * (MAX_COMMENT_LEN + 1))
        assert False
    except ValueError:
        pass


def test_comment_owner_token_edit_delete_persists():
    init_db()
    posted = add_comment("lab-tester", "original text")
    assert posted.get("owner_token")
    cid = posted["id"]
    updated = update_comment(cid, posted["owner_token"], "edited text")
    assert updated["comment_text"] == "edited text"
    listed = list_comments()
    match = [c for c in listed if c["id"] == cid]
    assert match and match[0]["comment_text"] == "edited text"
    try:
        update_comment(cid, "wrong-token", "nope")
        assert False
    except PermissionError:
        pass
    assert delete_own_comment(cid, posted["owner_token"]) is True
    assert all(c["id"] != cid for c in list_comments())
