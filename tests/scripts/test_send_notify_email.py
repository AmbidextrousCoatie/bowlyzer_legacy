"""send_notify_email helpers."""

from __future__ import annotations

import pytest

from scripts.send_notify_email import _split_recipients


def test_split_recipients() -> None:
    assert _split_recipients("a@x.com") == ["a@x.com"]
    assert _split_recipients("a@x.com, b@y.com") == ["a@x.com", "b@y.com"]
    assert _split_recipients("a@x.com; b@y.com") == ["a@x.com", "b@y.com"]
