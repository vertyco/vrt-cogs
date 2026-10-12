import base64
import binascii
import struct
import zlib

W = 320
H = 180
N = W * H
ELEMENT_COUNT = 62
HEADER = 34
MAX_WORLD = 512 * 1024
MAX_RAW = 1024 * 1024
MAX_PNG = 200 * 1024
MAX_NAME = 40

MAGIC = b"SAND"
VERSION = 1
# The header, the four cell planes (element, shade, heat, life), the particle count and the creatures length
MIN_RAW = HEADER + N * 6 + 2 + 4
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def decode_base64(text: object, limit: int, what: str) -> bytes:
    """The bytes inside a base64 text, refusing anything that decodes to more than `limit` bytes"""
    if not isinstance(text, str) or not text:
        raise ValueError(f"That isn't a {what}.")
    if len(text) > limit * 4 // 3 + 4:
        raise ValueError(f"That {what} is too big.")
    try:
        data = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError) as e:
        raise ValueError(f"That isn't a {what}.") from e
    if len(data) > limit:
        raise ValueError(f"That {what} is too big.")
    return data


def inflate(data: bytes) -> bytes:
    """Inflates a zlib stream, stopping as soon as it passes MAX_RAW so a tiny file can't grow into gigabytes"""
    unpacker = zlib.decompressobj()
    try:
        raw = unpacker.decompress(data, MAX_RAW + 1)
    except zlib.error as e:
        raise ValueError("That world is damaged.") from e
    if len(raw) > MAX_RAW or unpacker.unconsumed_tail:
        raise ValueError("That world is too big.")
    if not unpacker.eof or unpacker.unused_data:
        raise ValueError("That world is damaged.")
    return raw


def check_world(text: str) -> bytes:
    """
    The deflated bytes to store for a world sent as base64 text.

    Raises ValueError with a plain reason when the text is not a Sandfall world of exactly 320 x 180 cells that only
    holds known elements.
    """
    data = decode_base64(text, MAX_WORLD, "world")
    raw = inflate(data)
    if len(raw) < MIN_RAW or raw[:4] != MAGIC:
        raise ValueError("That isn't a Sandfall world.")
    if raw[4] != VERSION:
        raise ValueError("That world was saved by a different version of Sandfall.")
    width, height = struct.unpack_from("<HH", raw, 6)
    if (width, height) != (W, H):
        raise ValueError("That world is the wrong size.")
    if max(raw[HEADER : HEADER + N]) >= ELEMENT_COUNT:
        raise ValueError("That world holds a material Sandfall doesn't know.")
    return data


def check_png(text: str) -> bytes:
    """The bytes of a PNG picture sent as base64 text (no data: prefix), or ValueError with a plain reason"""
    data = decode_base64(text, MAX_PNG, "picture")
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("That isn't a picture.")
    return data


def clean_name(text: object) -> str:
    """A world's name as plain text: printable characters only, spaces collapsed, at most 40 characters"""
    if not isinstance(text, str):
        return ""
    printable = "".join(ch if ch.isprintable() else " " for ch in text)
    return " ".join(printable.split())[:MAX_NAME].strip()


def to_text(data: bytes) -> str:
    """Stored world bytes as the base64 text the page reads"""
    return base64.b64encode(data).decode("ascii")
