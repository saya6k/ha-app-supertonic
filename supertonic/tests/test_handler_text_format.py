"""Handler-level wiring for wyoming 1.10's `text_format`.

test_ssml.py covers the stripping helpers in isolation; these tests check
that the Synthesize / SynthesizeStart / SynthesizeChunk branches actually
route text through them.
"""

import argparse
import asyncio

import pytest
from wyoming.tts import (
    Synthesize,
    SynthesizeChunk,
    SynthesizeStart,
    SynthesizeStop,
    SynthesizeTextFormat,
)

from wyoming_supertonic.handler import SupertonicEventHandler


class _FakeInfo:
    def event(self):
        return None


def _make_handler():
    """Handler with synthesis stubbed out, recording the text it would speak."""
    cli_args = argparse.Namespace(
        no_streaming=False,
        no_text_normalization=True,
        auto_punctuation="",
        debug=False,
    )
    handler = SupertonicEventHandler(
        _FakeInfo(),
        cli_args,
        engine=object(),
        normalizer=object(),
        reader=None,
        writer=None,
    )

    spoken = []

    async def _capture(synthesize, send_start=True, send_stop=True):
        spoken.append(synthesize.text)
        return True

    handler._handle_synthesize = _capture  # type: ignore[assignment]
    handler.write_event = _capture_noop  # type: ignore[assignment]
    return handler, spoken


async def _capture_noop(*args, **kwargs):
    return None


def _run(coro):
    return asyncio.run(coro)


def test_plain_synthesize_is_untouched():
    handler, spoken = _make_handler()
    event = Synthesize(text="Hello world.").event()

    _run(handler.handle_event(event))

    assert " ".join(spoken) == "Hello world."


def test_synthesize_ssml_is_stripped():
    handler, spoken = _make_handler()
    event = Synthesize(
        text="<speak>Hello world.</speak>",
        text_format=SynthesizeTextFormat.SSML,
    ).event()

    _run(handler.handle_event(event))

    joined = " ".join(spoken)
    assert "speak" not in joined
    assert "Hello world." in joined


def test_ssml_markup_would_otherwise_be_spoken():
    """Without text_format handling the tags reach the engine verbatim."""
    handler, spoken = _make_handler()
    # Same markup, but the client did not declare it as SSML.
    event = Synthesize(text="<speak>Hello world.</speak>").event()

    _run(handler.handle_event(event))

    assert "speak" in " ".join(spoken)


def test_streaming_ssml_tag_split_across_chunks():
    handler, spoken = _make_handler()

    async def drive():
        await handler.handle_event(
            SynthesizeStart(text_format=SynthesizeTextFormat.SSML).event()
        )
        await handler.handle_event(SynthesizeChunk(text="<speak>Hello <emph").event())
        await handler.handle_event(
            SynthesizeChunk(text="asis>world</emphasis>.</speak>").event()
        )
        await handler.handle_event(SynthesizeStop().event())

    _run(drive())

    joined = " ".join(spoken)
    assert "asis" not in joined
    assert "emph" not in joined
    assert "Hello" in joined and "world" in joined


def test_streaming_plain_text_is_untouched():
    handler, spoken = _make_handler()

    async def drive():
        await handler.handle_event(SynthesizeStart().event())
        await handler.handle_event(SynthesizeChunk(text="Hello world.").event())
        await handler.handle_event(SynthesizeStop().event())

    _run(drive())

    assert "Hello world." in " ".join(spoken)


def test_unterminated_tag_at_stream_end_is_not_dropped():
    handler, spoken = _make_handler()

    async def drive():
        await handler.handle_event(
            SynthesizeStart(text_format=SynthesizeTextFormat.SSML).event()
        )
        await handler.handle_event(SynthesizeChunk(text="Hello <bro").event())
        await handler.handle_event(SynthesizeStop().event())

    _run(drive())

    assert "Hello" in " ".join(spoken)


def test_unknown_text_format_treated_as_plain_text(caplog):
    handler, spoken = _make_handler()
    event = Synthesize(text="Hello world.", text_format="other-format").event()

    _run(handler.handle_event(event))

    assert "Hello world." in " ".join(spoken)
    assert any("Unknown text_format" in r.message for r in caplog.records)


@pytest.mark.parametrize("fmt", [None, SynthesizeTextFormat.TEXT, "text"])
def test_no_warning_for_known_plain_formats(fmt, caplog):
    handler, _ = _make_handler()
    event = Synthesize(text="Hi.", text_format=fmt).event()

    _run(handler.handle_event(event))

    assert not any("Unknown text_format" in r.message for r in caplog.records)
