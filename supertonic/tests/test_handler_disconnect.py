"""Abrupt client disconnects must not surface as tracebacks.

A client that vanishes mid-event makes wyoming's `async_read_event` raise out
of `AsyncEventHandler.run()` — verified against a real socket: a clean FIN
gives IncompleteReadError, an RST gives ConnectionResetError. Unhandled,
asyncio reports "Task exception was never retrieved" with a traceback, which
reads like an add-on crash in the HA log.
"""

import argparse
import asyncio
import logging

import pytest
from wyoming.server import AsyncEventHandler

from wyoming_supertonic.handler import SupertonicEventHandler


class _FakeInfo:
    def event(self):
        return None


def _make_handler():
    cli_args = argparse.Namespace(
        no_streaming=False,
        no_text_normalization=True,
        auto_punctuation="",
        debug=False,
    )
    return SupertonicEventHandler(
        _FakeInfo(),
        cli_args,
        engine=object(),
        normalizer=object(),
        reader=None,
        writer=None,
    )


@pytest.mark.parametrize(
    "exc",
    [
        asyncio.IncompleteReadError(b"partial", 500),
        ConnectionResetError(54, "Connection reset by peer"),
    ],
)
def test_disconnect_is_swallowed(exc, monkeypatch, caplog):
    async def _raise(self):
        raise exc

    monkeypatch.setattr(AsyncEventHandler, "run", _raise)
    handler = _make_handler()

    with caplog.at_level(logging.DEBUG):
        asyncio.run(handler.run())  # must not raise

    assert any("disconnected" in r.message.lower() for r in caplog.records)


def test_unexpected_errors_still_propagate():
    """Only disconnects are swallowed — real bugs must stay visible."""

    async def _raise(self):
        raise RuntimeError("engine exploded")

    original = AsyncEventHandler.run
    AsyncEventHandler.run = _raise  # type: ignore[assignment]
    try:
        handler = _make_handler()
        with pytest.raises(RuntimeError, match="engine exploded"):
            asyncio.run(handler.run())
    finally:
        AsyncEventHandler.run = original  # type: ignore[assignment]
