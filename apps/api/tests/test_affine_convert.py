"""AFFiNE/BlockSuite -> BlockNote translator tests. Builds real BlockSuite-shaped
Yjs blocks with pycrdt (the same types the snapshot loader decodes)."""

from pycrdt import Array, Doc, Map, Text

from lore_api.affine import convert


def _blocks(specs: list[dict]) -> Map:
    """Build a `blocks` Y.Map from lightweight specs (mirrors AFFiNE's YBlock shape)."""
    doc = Doc()
    blocks = doc.get("blocks", type=Map)
    for s in specs:
        m = Map()
        blocks[s["id"]] = m
        m["sys:id"] = s["id"]
        m["sys:flavour"] = s["flavour"]
        if "children" in s:
            m["sys:children"] = Array(s["children"])
        for k in ("type", "checked", "sourceId", "pageId", "url", "title", "displayMode",
                  "hidden", "language", "latex"):
            if k in s:
                m[f"prop:{k}"] = s[k]
        if "text" in s:
            m["prop:text"] = Text(s["text"])
            for start, end, attr in s.get("formats", []):
                m["prop:text"].format(start, end, attr)
    return blocks


def _page(content: list[dict], root_extra: list[dict] | None = None) -> Map:
    """Wrap content blocks in the affine:page -> affine:note structure."""
    ids = [c["id"] for c in content]
    specs = [
        {"id": "root", "flavour": "affine:page", "children": ["note"] + [x["id"] for x in (root_extra or [])]},
        {"id": "note", "flavour": "affine:note", "displayMode": "both", "children": ids},
        *content,
        *(root_extra or []),
    ]
    return _blocks(specs)


def _titles() -> dict[str, str]:
    return {"other": "Other Page"}


def test_paragraph_heading_quote():
    blocks = _page([
        {"id": "p", "flavour": "affine:paragraph", "type": "text", "text": "hello"},
        {"id": "h", "flavour": "affine:paragraph", "type": "h2", "text": "Heading"},
        {"id": "h5", "flavour": "affine:paragraph", "type": "h5", "text": "Deep"},
        {"id": "q", "flavour": "affine:paragraph", "type": "quote", "text": "quoted"},
    ])
    out = convert.page_to_blocks(blocks, _titles())
    assert [b["type"] for b in out] == ["paragraph", "heading", "heading", "quote"]
    assert out[1]["props"]["level"] == 2
    assert out[2]["props"]["level"] == 3  # h5 clamped
    assert out[0]["content"][0]["text"] == "hello"


def test_lists_and_todo():
    blocks = _page([
        {"id": "b", "flavour": "affine:list", "type": "bulleted", "text": "b"},
        {"id": "n", "flavour": "affine:list", "type": "numbered", "text": "n"},
        {"id": "t", "flavour": "affine:list", "type": "todo", "checked": True, "text": "done"},
    ])
    out = convert.page_to_blocks(blocks, _titles())
    assert [b["type"] for b in out] == ["bulletListItem", "numberedListItem", "checkListItem"]
    assert out[2]["props"]["checked"] is True


def test_text_formatting_and_link():
    blocks = _page([
        {"id": "p", "flavour": "affine:paragraph", "type": "text", "text": "bold and link",
         "formats": [(0, 4, {"bold": True}), (9, 13, {"link": "https://x.com"})]},
    ])
    out = convert.page_to_blocks(blocks, _titles())
    runs = out[0]["content"]
    assert runs[0] == {"type": "text", "text": "bold", "styles": {"bold": True}}
    link = next(r for r in runs if r.get("type") == "link")
    assert link["href"] == "https://x.com" and link["content"][0]["text"] == "link"


def test_code_block():
    blocks = _page([
        {"id": "c", "flavour": "affine:code", "language": "Python", "text": "x = 1"},
    ])
    out = convert.page_to_blocks(blocks, _titles())
    assert out[0]["type"] == "codeBlock" and out[0]["props"]["language"] == "python"
    assert out[0]["content"][0]["text"] == "x = 1"


def test_image_and_linked_doc():
    blocks = _page([
        {"id": "img", "flavour": "affine:image", "sourceId": "BLOBKEY"},
        {"id": "ld", "flavour": "affine:embed-linked-doc", "pageId": "other"},
    ])
    out = convert.page_to_blocks(blocks, _titles())
    img = next(b for b in out if b["type"] == "image")
    assert img["props"]["url"] == f"{convert.ATTACHMENT_REF}BLOBKEY"
    link = next(i for b in out if isinstance(b.get("content"), list)
                for i in b["content"] if i.get("type") == "link")
    assert link["href"] == f"{convert.AFFINE_LINK_SCHEME}other"
    assert link["content"][0]["text"] == "Other Page"  # resolved title


def test_edgeless_notes_and_surface_skipped():
    # An edgeless-only note and a surface must NOT contribute to the document.
    blocks = _page(
        content=[{"id": "p", "flavour": "affine:paragraph", "type": "text", "text": "keep"}],
        root_extra=[
            {"id": "surface", "flavour": "affine:surface"},
            {"id": "edn", "flavour": "affine:note", "displayMode": "edgeless", "children": ["hidden_p"]},
            {"id": "hidden_p", "flavour": "affine:paragraph", "type": "text", "text": "DROP ME"},
        ],
    )
    out = convert.page_to_blocks(blocks, _titles())
    texts = [i.get("text") for b in out if isinstance(b.get("content"), list) for i in b["content"]]
    assert "keep" in texts and "DROP ME" not in texts


def test_nested_list_children():
    blocks = _page([
        {"id": "parent", "flavour": "affine:list", "type": "bulleted", "text": "parent",
         "children": ["child"]},
        {"id": "child", "flavour": "affine:list", "type": "bulleted", "text": "child"},
    ])
    out = convert.page_to_blocks(blocks, _titles())
    assert out[0]["content"][0]["text"] == "parent"
    assert out[0]["children"][0]["content"][0]["text"] == "child"
