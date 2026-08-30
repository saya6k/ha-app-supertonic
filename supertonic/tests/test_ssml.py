"""Tests for SSML degradation (wyoming 1.10 `text_format`)."""

import pytest

from wyoming_supertonic.ssml import split_partial_tag, strip_ssml


@pytest.mark.parametrize(
    "markup,expected",
    [
        ("<speak>Hello world</speak>", "Hello world"),
        ("plain text, no markup", "plain text, no markup"),
        ("", ""),
        # Tags become a space so words either side don't weld together.
        ("a<break time='500ms'/>b", "a b"),
        ("<speak>Hi <emphasis level='strong'>there</emphasis>!</speak>", "Hi there !"),
        # Entities are unescaped after tags are removed.
        ("<speak>Tom &amp; Jerry</speak>", "Tom & Jerry"),
        # An escaped angle bracket is text, not a tag.
        ("<speak>5 &lt; 6</speak>", "5 < 6"),
        # Attributes containing ">" are not valid XML; we just need to not crash.
        ("<speak><p>One</p><p>Two</p></speak>", "One Two"),
    ],
)
def test_strip_ssml(markup, expected):
    assert strip_ssml(markup) == expected


def test_strip_ssml_never_raises_on_malformed():
    # SSML arrives unvalidated; tag-stripping must be total.
    for bad in ["<speak>unclosed", "<<>>", "a < b > c", "<", ">"]:
        assert isinstance(strip_ssml(bad), str)


@pytest.mark.parametrize(
    "text,safe,carry",
    [
        ("no tags here", "no tags here", ""),
        ("<speak>done</speak>", "<speak>done</speak>", ""),
        # Trailing incomplete tag is held back for the next chunk.
        ("Hello <emph", "Hello ", "<emph"),
        ("<speak>Hi <", "<speak>Hi ", "<"),
        ("", "", ""),
    ],
)
def test_split_partial_tag(text, safe, carry):
    assert split_partial_tag(text) == (safe, carry)


def test_tag_split_across_chunks_is_not_spoken():
    """The bug carry-over exists to prevent: a tag straddling a boundary."""
    chunks = ["<speak>Hello <emph", "asis>world</emphasis></speak>"]

    carry, spoken = "", []
    for chunk in chunks:
        safe, carry = split_partial_tag(carry + chunk)
        spoken.append(strip_ssml(safe))

    joined = " ".join(part for part in spoken if part)
    assert "asis" not in joined
    assert joined == "Hello world"


def test_naive_per_chunk_stripping_would_leak_markup():
    """Guards the reason split_partial_tag exists, not just its behaviour."""
    chunks = ["<speak>Hello <emph", "asis>world</emphasis></speak>"]
    naive = " ".join(strip_ssml(c) for c in chunks)
    assert "asis" in naive
