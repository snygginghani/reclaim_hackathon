"""Pure Obsidian-Markdown -> BlockNote translator tests (no I/O)."""

from lore_api.obsidian import convert as c


def _titles(blocks):
    return [b["type"] for b in blocks]


def test_frontmatter_stripped_and_heading():
    md = "---\ntags: [a, b]\n---\n# Hello\n"
    blocks = c.markdown_to_blocks(md)
    assert len(blocks) == 1
    assert blocks[0]["type"] == "heading" and blocks[0]["props"]["level"] == 1
    assert blocks[0]["content"][0]["text"] == "Hello"


def test_inline_emphasis_and_code():
    md = "a **b** _i_ ~~s~~ `code` end"
    para = c.markdown_to_blocks(md)[0]
    styled = {run["text"]: run["styles"] for run in para["content"]}
    assert styled["b"] == {"bold": True}
    assert styled["i"] == {"italic": True}
    assert styled["s"] == {"strike": True}
    assert styled["code"] == {"code": True}


def test_nested_emphasis_combines_styles():
    para = c.markdown_to_blocks("**bold _both_**")[0]
    runs = {run["text"]: run["styles"] for run in para["content"]}
    assert runs["both"] == {"bold": True, "italic": True}


def test_wikilink_with_alias_and_heading():
    para = c.markdown_to_blocks("see [[Target Note#Section|the alias]] here")[0]
    link = next(i for i in para["content"] if i["type"] == "link")
    assert link["href"] == f"{c.OBSIDIAN_LINK_SCHEME}Target Note"
    assert link["content"][0]["text"] == "the alias"


def test_markdown_link_is_external():
    para = c.markdown_to_blocks("a [text](https://x.com) b")[0]
    link = next(i for i in para["content"] if i["type"] == "link")
    assert link["href"] == "https://x.com"


def test_lists_nesting_and_tasks():
    md = "- one\n- two\n    - nested\n- [ ] todo\n- [x] done"
    blocks = c.markdown_to_blocks(md)
    assert blocks[0]["type"] == "bulletListItem" and blocks[0]["content"][0]["text"] == "one"
    two = blocks[1]
    assert two["children"][0]["content"][0]["text"] == "nested"
    todo = next(b for b in blocks if b["type"] == "checkListItem" and not b["props"]["checked"])
    done = next(b for b in blocks if b["type"] == "checkListItem" and b["props"]["checked"])
    assert todo["content"][0]["text"] == "todo"
    assert done["content"][0]["text"] == "done"


def test_ordered_list():
    blocks = c.markdown_to_blocks("1. first\n2. second")
    assert [b["type"] for b in blocks] == ["numberedListItem", "numberedListItem"]


def test_code_fence_language():
    md = "```python\nx = 1\ny = 2\n```"
    code = c.markdown_to_blocks(md)[0]
    assert code["type"] == "codeBlock" and code["props"]["language"] == "python"
    assert code["content"][0]["text"] == "x = 1\ny = 2"


def test_blockquote():
    q = c.markdown_to_blocks("> line one\n> line two")[0]
    assert q["type"] == "quote"
    assert "".join(r["text"] for r in q["content"]) == "line one\nline two"


def test_table():
    md = "| A | B |\n| --- | --- |\n| 1 | 2 |"
    tbl = c.markdown_to_blocks(md)[0]
    assert tbl["type"] == "table"
    rows = tbl["content"]["rows"]
    assert rows[0]["cells"][0][0]["text"] == "A"
    assert rows[1]["cells"][1][0]["text"] == "2"


def test_image_embed_and_markdown_image():
    embed = c.markdown_to_blocks("![[diagram.png]]")[0]
    assert embed["type"] == "image"
    assert embed["props"]["url"] == f"{c.ATTACHMENT_REF}diagram.png"

    img = c.markdown_to_blocks("![cap](pics/photo.jpg)")[0]
    assert img["type"] == "image"
    assert img["props"]["url"] == f"{c.ATTACHMENT_REF}pics/photo.jpg"
    assert img["props"]["caption"] == "cap"


def test_note_embed_becomes_link():
    block = c.markdown_to_blocks("![[Some Note]]")[0]
    assert block["type"] == "paragraph"
    link = block["content"][0]
    assert link["type"] == "link" and link["href"] == f"{c.OBSIDIAN_LINK_SCHEME}Some Note"


def test_custom_resolvers():
    blocks = c.markdown_to_blocks(
        "[[X]] and ![[y.png]]",
        resolve_link=lambda name: f"obsidian-note:path/{name}",
        resolve_embed=lambda target: f"vault:resolved/{target}",
    )
    link = next(i for i in blocks[0]["content"] if i["type"] == "link")
    assert link["href"] == "obsidian-note:path/X"
