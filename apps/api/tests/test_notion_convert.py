"""Pure translator + OAuth-state tests (no DB, no network)."""

import time

from lore_api.migrate import oauth
from lore_api.notion import convert as c


def _text(content: str, **annotations) -> dict:
    return {
        "type": "text",
        "text": {"content": content},
        "plain_text": content,
        "annotations": annotations,
    }


def test_rich_text_styles_and_links():
    rich = [
        _text("bold ", bold=True),
        {
            "type": "text",
            "text": {"content": "link", "link": {"url": "https://x.com"}},
            "plain_text": "link",
            "href": "https://x.com",
            "annotations": {"italic": True, "color": "red"},
        },
    ]
    inline = c.rich_text_to_inline(rich)
    assert inline[0] == {"type": "text", "text": "bold ", "styles": {"bold": True}}
    assert inline[1]["type"] == "link" and inline[1]["href"] == "https://x.com"
    assert inline[1]["content"][0]["styles"] == {"italic": True, "textColor": "red"}
    assert c.rich_text_to_plain(rich) == "bold link"


def test_background_color_style():
    inline = c.rich_text_to_inline([_text("hi", color="blue_background")])
    assert inline[0]["styles"] == {"backgroundColor": "blue"}


def test_page_mention_becomes_placeholder_link():
    rich = [{
        "type": "mention",
        "mention": {"type": "page", "page": {"id": "notion-xyz"}},
        "plain_text": "Target",
        "annotations": {},
    }]
    inline = c.rich_text_to_inline(rich)
    assert inline[0]["type"] == "link"
    assert inline[0]["href"] == f"{c.PAGE_LINK_SCHEME}notion-xyz"


def test_block_type_coverage():
    def blk(t, **body):
        return {"type": t, t: body}

    heading = c.convert_block(blk("heading_2", rich_text=[_text("H")]), [])
    assert heading["type"] == "heading" and heading["props"]["level"] == 2

    todo = c.convert_block(blk("to_do", checked=True, rich_text=[_text("t")]), [])
    assert todo["type"] == "checkListItem" and todo["props"]["checked"] is True

    code = c.convert_block(blk("code", language="Python", rich_text=[_text("x=1")]), [])
    assert code["type"] == "codeBlock" and code["props"]["language"] == "python"

    quote = c.convert_block(blk("quote", rich_text=[_text("q")]), [])
    assert quote["type"] == "quote"

    bullet = c.convert_block(blk("bulleted_list_item", rich_text=[_text("b")]), [])
    assert bullet["type"] == "bulletListItem"

    # Callout keeps its emoji, mapped to a quote.
    callout = c.convert_block(
        {"type": "callout", "callout": {"rich_text": [_text("note")], "icon": {"emoji": "💡"}}}, []
    )
    assert callout["type"] == "quote" and callout["content"][0]["text"].startswith("💡")

    # Divider / unsupported carry no body.
    assert c.convert_block(blk("divider"), []) is None


def test_children_attached():
    child = c.convert_block({"type": "paragraph", "paragraph": {"rich_text": [_text("c")]}}, [])
    parent = c.convert_block({"type": "toggle", "toggle": {"rich_text": [_text("p")]}}, [child])
    assert parent["children"] == [child]


def test_media_keeps_original_url_for_rehost():
    img = c.convert_block(
        {"type": "image", "image": {"type": "file", "file": {"url": "https://s3/notion.png?sig=1"},
                                    "caption": [_text("cap")]}},
        [],
    )
    assert img["type"] == "image"
    assert img["props"]["url"] == "https://s3/notion.png?sig=1"
    assert img["props"]["caption"] == "cap"


def test_table_builder():
    tbl = c.build_table([[[_text("a")], [_text("b")]]])
    assert tbl["type"] == "table"
    rows = tbl["content"]["rows"]
    assert rows[0]["cells"][0][0]["text"] == "a"


def test_property_mapping_and_options():
    assert c.PROPERTY_TYPE_MAP["status"] == "select"
    assert c.PROPERTY_TYPE_MAP["multi_select"] == "multi_select"
    opts = c.options_for("select", {"select": {"options": [{"id": "o1", "name": "A", "color": "green"}]}})
    assert opts["choices"][0]["id"] == "o1"
    assert opts["choices"][0]["color"] == c.NOTION_COLOR_HEX["green"]


def test_cell_value_shapes():
    assert c.cell_value("select", {"select": {"id": "o1"}}) == {"select": "o1"}
    assert c.cell_value("multi_select", {"multi_select": [{"id": "a"}, {"id": "b"}]}) == {
        "multi_select": ["a", "b"]
    }
    assert c.cell_value("date", {"date": {"start": "2026-01-01", "end": "2026-01-02"}}) == {
        "date": {"start": "2026-01-01", "end": "2026-01-02"}
    }
    assert c.cell_value("checkbox", {"checkbox": True}) == {"checkbox": True}
    assert c.cell_value("number", {"number": 5}) == {"number": 5}
    assert c.cell_value("number", {"number": None}) is None
    assert c.cell_value("url", {"url": "https://x"}) == {"url": "https://x"}
    assert c.cell_value("relation", {"relation": [{"id": "p1"}]}) == {"relation": ["p1"]}
    assert c.cell_value("email", {"email": "a@b.c"}) == {"text": "a@b.c"}


def test_title_of():
    page = {"properties": {"Name": {"type": "title", "title": [_text("My Row")]}}}
    assert c.title_of(page) == "My Row"
    assert c.title_of({"properties": {}}) == "Untitled"


# --- OAuth state ---

import uuid  # noqa: E402


def test_state_roundtrip_and_tamper():
    u, w = uuid.uuid4(), uuid.uuid4()
    state = oauth.sign_state(u, w)
    assert oauth.verify_state(state) == (u, w)
    assert oauth.verify_state(state + "tamper") is None
    assert oauth.verify_state("garbage") is None


def test_state_expiry(monkeypatch):
    u, w = uuid.uuid4(), uuid.uuid4()
    state = oauth.sign_state(u, w)
    # Jump past the TTL (compute the future instant before patching so the fake
    # doesn't recurse into the patched clock).
    future = time.time() + oauth.STATE_TTL_SECONDS + 10
    monkeypatch.setattr(oauth.time, "time", lambda: future)
    assert oauth.verify_state(state) is None
