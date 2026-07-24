"""Pure ADF -> BlockNote translator tests (no DB, no network)."""

from lore_api.confluence import convert as c


def _p(*inline) -> dict:
    return {"type": "paragraph", "content": list(inline)}


def _text(s: str, *marks) -> dict:
    node = {"type": "text", "text": s}
    if marks:
        node["marks"] = list(marks)
    return node


def test_text_marks_and_link():
    adf = {
        "type": "doc",
        "content": [
            _p(
                _text("bold ", {"type": "strong"}),
                _text("code", {"type": "code"}),
                _text("x", {"type": "link", "attrs": {"href": "https://x.com"}}),
            )
        ],
    }
    para = c.adf_to_blocks(adf)[0]
    assert para["type"] == "paragraph"
    assert para["content"][0] == {"type": "text", "text": "bold ", "styles": {"bold": True}}
    assert para["content"][1]["styles"] == {"code": True}
    link = para["content"][2]
    assert link["type"] == "link" and link["href"] == "https://x.com"


def test_internal_page_link_becomes_placeholder():
    href = "https://acme.atlassian.net/wiki/spaces/ENG/pages/98765/Design"
    adf = {"type": "doc", "content": [_p(_text("Design", {"type": "link", "attrs": {"href": href}}))]}
    link = c.adf_to_blocks(adf)[0]["content"][0]
    assert link["type"] == "link"
    assert link["href"] == f"{c.CONFLUENCE_LINK_SCHEME}98765"


def test_heading_level_clamped():
    adf = {"type": "doc", "content": [{"type": "heading", "attrs": {"level": 5},
                                       "content": [_text("Deep")]}]}
    h = c.adf_to_blocks(adf)[0]
    assert h["type"] == "heading" and h["props"]["level"] == 3


def test_lists_and_tasks():
    adf = {
        "type": "doc",
        "content": [
            {"type": "bulletList", "content": [
                {"type": "listItem", "content": [_p(_text("a"))]}]},
            {"type": "orderedList", "content": [
                {"type": "listItem", "content": [_p(_text("one"))]}]},
            {"type": "taskList", "content": [
                {"type": "taskItem", "attrs": {"state": "DONE"}, "content": [_text("did it")]},
                {"type": "taskItem", "attrs": {"state": "TODO"}, "content": [_text("later")]}]},
        ],
    }
    blocks = c.adf_to_blocks(adf)
    assert blocks[0]["type"] == "bulletListItem"
    assert blocks[1]["type"] == "numberedListItem"
    assert blocks[2]["type"] == "checkListItem" and blocks[2]["props"]["checked"] is True
    assert blocks[3]["type"] == "checkListItem" and blocks[3]["props"]["checked"] is False


def test_nested_list_children():
    adf = {"type": "doc", "content": [
        {"type": "bulletList", "content": [
            {"type": "listItem", "content": [
                _p(_text("parent")),
                {"type": "bulletList", "content": [
                    {"type": "listItem", "content": [_p(_text("child"))]}]},
            ]}]}]}
    top = c.adf_to_blocks(adf)[0]
    assert top["content"][0]["text"] == "parent"
    assert top["children"][0]["type"] == "bulletListItem"
    assert top["children"][0]["content"][0]["text"] == "child"


def test_code_block_language_lowercased():
    adf = {"type": "doc", "content": [
        {"type": "codeBlock", "attrs": {"language": "Python"}, "content": [_text("x=1")]}]}
    code = c.adf_to_blocks(adf)[0]
    assert code["type"] == "codeBlock" and code["props"]["language"] == "python"


def test_panel_becomes_quote_with_emoji():
    adf = {"type": "doc", "content": [
        {"type": "panel", "attrs": {"panelType": "warning"}, "content": [_p(_text("careful"))]}]}
    q = c.adf_to_blocks(adf)[0]
    assert q["type"] == "quote"
    assert q["content"][0]["text"].startswith("⚠️")
    assert q["content"][-1]["text"] == "careful"


def test_table():
    adf = {"type": "doc", "content": [
        {"type": "table", "content": [
            {"type": "tableRow", "content": [
                {"type": "tableHeader", "content": [_p(_text("H"))]},
                {"type": "tableCell", "content": [_p(_text("v"))]}]}]}]}
    tbl = c.adf_to_blocks(adf)[0]
    assert tbl["type"] == "table"
    cells = tbl["content"]["rows"][0]["cells"]
    assert cells[0][0]["text"] == "H" and cells[1][0]["text"] == "v"


def test_media_becomes_attachment_ref():
    adf = {"type": "doc", "content": [
        {"type": "mediaSingle", "content": [
            {"type": "media", "attrs": {"type": "file", "id": "file-42", "alt": "diagram"}}]}]}
    img = c.adf_to_blocks(adf)[0]
    assert img["type"] == "image"
    assert img["props"]["url"] == f"{c.ATTACHMENT_REF}file-42"
    assert img["props"]["caption"] == "diagram"


def test_external_media_keeps_url():
    adf = {"type": "doc", "content": [
        {"type": "mediaSingle", "content": [
            {"type": "media", "attrs": {"type": "external", "url": "https://img/x.png"}}]}]}
    img = c.adf_to_blocks(adf)[0]
    assert img["props"]["url"] == "https://img/x.png"


def test_rule_dropped():
    adf = {"type": "doc", "content": [{"type": "rule"}, _p(_text("after"))]}
    blocks = c.adf_to_blocks(adf)
    assert [b["type"] for b in blocks] == ["paragraph"]
