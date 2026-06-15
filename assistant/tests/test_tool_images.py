from assistant.common.utils import build_tool_image_message


def test_build_tool_image_message_structure():
    msg = build_tool_image_message(["http://cdn/a.png", "http://cdn/b.png"], "low")
    assert msg["role"] == "user"
    blocks = msg["content"]
    assert blocks[0]["type"] == "text"
    image_blocks = [b for b in blocks if b["type"] == "image_url"]
    assert len(image_blocks) == 2
    assert image_blocks[0]["image_url"]["url"] == "http://cdn/a.png"
    assert image_blocks[0]["image_url"]["detail"] == "low"


def test_build_tool_image_message_empty():
    assert build_tool_image_message([], "auto") is None
