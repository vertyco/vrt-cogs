"""
Transcript processing utilities for the Tickets cog.

Handles:
- Stripping deprecated DiscordChatExporterPy attribution comments
- Compressing images to WebP format for smaller file sizes
- Embedding attachments as base64 data URIs in the HTML
- Managing file size budgets to stay within Discord's upload limits
"""

import asyncio
import base64
import logging
import mimetypes
import re
from io import BytesIO
from pathlib import Path
from typing import Optional

from PIL import Image
from redbot.core.i18n import Translator

log = logging.getLogger("red.vrt.tickets.transcript")
_ = Translator("Tickets", __file__)


# Regex to match the DiscordChatExporterPy attribution comment at the start of HTML
EXPORTER_COMMENT_PATTERN = re.compile(
    r"^\s*<!--\s*This transcript was generated using:.*?-->\s*",
    re.DOTALL | re.IGNORECASE,
)

# Regex to find Discord CDN attachment URLs in HTML (in src/href attributes)
# Matches both cdn.discordapp.com and media.discordapp.net URLs
# Handles both quoted (src="url") and unquoted (src=url) attribute formats
DISCORD_CDN_ATTR_QUOTED_PATTERN = re.compile(
    r'(src|href)=["\']'
    r"(https?://(?:cdn\.discordapp\.com|media\.discordapp\.net)/attachments/(\d+)/(\d+)/([^\"\'?]+)(?:\?[^\"\']*)?)"
    r'["\']',
    re.IGNORECASE,
)

# Pattern for unquoted URLs (chat_exporter uses this format)
# Matches: src=https://media.discordapp.net/... or href=https://cdn.discordapp.com/...
# URL ends at > or whitespace
DISCORD_CDN_ATTR_UNQUOTED_PATTERN = re.compile(
    r"(src|href)="
    r"(https?://(?:cdn\.discordapp\.com|media\.discordapp\.net)/attachments/(\d+)/(\d+)/([^?>\s]+)(?:\?[^>\s]*)?)"
    r"(?=[>\s])",
    re.IGNORECASE,
)

# Regex to find Discord CDN URLs in CSS url() - for background images etc
DISCORD_CDN_CSS_PATTERN = re.compile(
    r"url\(['\"]?"
    r"(https?://(?:cdn\.discordapp\.com|media\.discordapp\.net)/attachments/(\d+)/(\d+)/([^\"\')?]+)(?:\?[^\"\')?]*)?)"
    r"['\"]?\)",
    re.IGNORECASE,
)

# Image extensions that can be compressed to WebP
COMPRESSIBLE_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}

# Extensions that should be embedded as images (excluding GIFs for now due to animation complexity)
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".ico"}

# Video extensions - these go to the zip file, not embedded
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".avi", ".mkv", ".wmv", ".flv"}

# Audio extensions
AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac"}

# Default quality for WebP compression (0-100, higher = better quality, larger file)
DEFAULT_WEBP_QUALITY = 85

# Maximum size for an individual image to be embedded (in bytes)
# Images larger than this will go to the zip file
MAX_INDIVIDUAL_IMAGE_SIZE = 2 * 1024 * 1024  # 2MB


def strip_exporter_comment(html: str) -> str:
    """Remove the DiscordChatExporterPy attribution comment from the HTML.

    Args:
        html: The raw HTML string from chat_exporter

    Returns:
        HTML with the attribution comment removed
    """
    return EXPORTER_COMMENT_PATTERN.sub("", html, count=1)


def get_mime_type(filename: str) -> str:
    """Get the MIME type for a file based on its extension.

    Args:
        filename: The filename to check

    Returns:
        MIME type string, defaults to 'application/octet-stream' if unknown
    """
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or "application/octet-stream"


def is_image(filename: str) -> bool:
    """Check if a filename is an image based on extension."""
    return Path(filename).suffix.lower() in IMAGE_EXTENSIONS


def is_video(filename: str) -> bool:
    """Check if a filename is a video based on extension."""
    return Path(filename).suffix.lower() in VIDEO_EXTENSIONS


def is_audio(filename: str) -> bool:
    """Check if a filename is an audio file based on extension."""
    return Path(filename).suffix.lower() in AUDIO_EXTENSIONS


def can_compress_to_webp(filename: str) -> bool:
    """Check if an image can be compressed to WebP format."""
    return Path(filename).suffix.lower() in COMPRESSIBLE_IMAGE_EXTENSIONS


def compress_image_to_webp(
    image_data: bytes,
    quality: int = DEFAULT_WEBP_QUALITY,
    max_size: Optional[int] = None,
) -> tuple[bytes, bool]:
    """Compress an image to WebP format.

    Args:
        image_data: Raw image bytes
        quality: WebP quality (0-100)
        max_size: Optional maximum size in bytes. If set, will reduce quality to fit.

    Returns:
        Tuple of (compressed_bytes, was_compressed)
        If compression fails, returns original data with False
    """
    try:
        img = Image.open(BytesIO(image_data))

        # Handle different image modes
        if img.mode in ("RGBA", "LA", "P"):
            # Keep transparency
            if img.mode == "P" and "transparency" in img.info:
                img = img.convert("RGBA")
        elif img.mode != "RGB":
            img = img.convert("RGB")

        # Compress to WebP
        output = BytesIO()
        img.save(output, format="WEBP", quality=quality, method=6)
        compressed = output.getvalue()

        # If we have a max_size and exceeded it, try reducing quality
        if max_size and len(compressed) > max_size:
            for q in [70, 50, 30]:
                output = BytesIO()
                img.save(output, format="WEBP", quality=q, method=6)
                compressed = output.getvalue()
                if len(compressed) <= max_size:
                    break

        # Only use compressed version if it's actually smaller
        if len(compressed) < len(image_data):
            return compressed, True

        return image_data, False

    except Exception as e:
        log.debug(f"Failed to compress image to WebP: {e}")
        return image_data, False


def create_data_uri(data: bytes, mime_type: str) -> str:
    """Create a base64 data URI from binary data.

    Args:
        data: Raw binary data
        mime_type: MIME type for the data

    Returns:
        Data URI string (e.g., 'data:image/webp;base64,iVBORw0...')
    """
    b64_data = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{b64_data}"


def calculate_base64_size(data_size: int) -> int:
    """Calculate the size of data after base64 encoding.

    Base64 encoding increases size by approximately 33%.

    Args:
        data_size: Original data size in bytes

    Returns:
        Estimated size after base64 encoding
    """
    return int(data_size * 4 / 3) + 4  # +4 for padding


async def process_transcript_html(
    html: str,
    downloaded_files: list[dict],
    guild_filesize_limit: int,
) -> tuple[str, list[dict], list[str]]:
    """Process an exported HTML transcript for self-contained viewing.

    This function:
    1. Strips the DiscordChatExporterPy attribution comment
    2. Compresses images to WebP where beneficial
    3. Embeds images as base64 data URIs where size permits
    4. Returns files that couldn't be embedded for the zip archive

    Args:
        html: Raw HTML from chat_exporter
        downloaded_files: List of dicts with 'filename', 'content' (bytes), and optionally 'url'
        guild_filesize_limit: Discord's file size limit for this guild

    Returns:
        Tuple of:
        - Processed HTML string with embedded images
        - List of files to include in zip (videos, large files, etc.)
        - List of filenames that were successfully embedded
    """
    # Step 1: Strip the attribution comment
    html = strip_exporter_comment(html)

    # If no files to process, return early
    if not downloaded_files:
        return html, [], []

    # Step 2: Calculate size budget
    html_base_size = len(html.encode("utf-8"))
    # Reserve 85% of limit for safety, minus base HTML size
    available_budget = int(guild_filesize_limit * 0.85) - html_base_size

    if available_budget <= 0:
        # HTML itself is too large, can't embed anything
        return html, downloaded_files, []

    def extract_attachment_path(url: str) -> str:
        """Extract just the /attachments/... path from a Discord CDN URL.

        This normalizes URLs so cdn.discordapp.com and media.discordapp.net
        URLs for the same attachment will match.
        """
        # Strip query params first
        base = url.split("?")[0]
        # Find /attachments/ and return from there
        idx = base.find("/attachments/")
        if idx != -1:
            return base[idx:]
        return base

    # Step 3: Build mapping of attachment paths to file data
    # Use just the path portion so cdn.discordapp.com and media.discordapp.net URLs match
    path_to_file: dict[str, dict] = {}
    for f in downloaded_files:
        if "url" in f and f["url"]:
            path = extract_attachment_path(f["url"])
            path_to_file[path] = f
            log.debug(f"Registered attachment path: {path} -> {f['filename']}")

    # Step 4: Find all Discord CDN URLs in the HTML
    # Collect all URLs that need to be replaced
    urls_in_html: dict[str, str] = {}  # Maps full URL (as in HTML) -> attachment path (for matching)

    # Match quoted src/href attributes (src="url" or src='url')
    for match in DISCORD_CDN_ATTR_QUOTED_PATTERN.finditer(html):
        full_url = match.group(2)  # Full URL including query params
        path = extract_attachment_path(full_url)
        urls_in_html[full_url] = path
        log.debug(f"Found quoted URL in HTML: {full_url[:80]}...")

    # Match unquoted src/href attributes (src=url) - this is what chat_exporter produces
    for match in DISCORD_CDN_ATTR_UNQUOTED_PATTERN.finditer(html):
        full_url = match.group(2)
        path = extract_attachment_path(full_url)
        urls_in_html[full_url] = path
        log.debug(f"Found unquoted URL in HTML: {full_url[:80]}...")

    # Match CSS url() patterns
    for match in DISCORD_CDN_CSS_PATTERN.finditer(html):
        full_url = match.group(1)
        path = extract_attachment_path(full_url)
        urls_in_html[full_url] = path
        log.debug(f"Found URL in CSS: {full_url[:80]}...")

    # Step 5: Match HTML URLs to downloaded files by path
    matched_urls: dict[str, dict] = {}  # Maps full HTML URL -> file data
    for full_url, path in urls_in_html.items():
        if path in path_to_file:
            matched_urls[full_url] = path_to_file[path]
            log.debug(f"Matched URL to file: {path_to_file[path]['filename']}")

    log.debug(f"Matched {len(matched_urls)}/{len(urls_in_html)} URLs to downloaded files")

    # Step 6: Process files - compress images and decide what to embed
    files_to_embed: list[tuple[str, bytes, str]] = []  # (url_in_html, data, mime_type)
    files_for_zip: list[dict] = []
    embedded_filenames: list[str] = []
    processed_file_ids: set[int] = set()  # Track by id() to avoid duplicates

    # Sort by size (smallest first) to maximize number of embedded files
    sorted_urls = sorted(matched_urls.keys(), key=lambda u: len(matched_urls[u].get("content", b"")))

    current_budget = available_budget

    def process_file(html_url: str, file_data: dict) -> None:
        nonlocal current_budget

        # Avoid processing the same file multiple times
        file_id = id(file_data)
        if file_id in processed_file_ids:
            return
        processed_file_ids.add(file_id)

        filename = file_data["filename"]
        content = file_data.get("content", b"")

        if not content:
            return

        # Videos always go to zip
        if is_video(filename):
            files_for_zip.append(file_data)
            return

        # Audio files go to zip (usually large)
        if is_audio(filename):
            files_for_zip.append(file_data)
            return

        # Check if it's an image we can process
        if is_image(filename):
            # Try to compress if it's a compressible format
            processed_data = content
            mime_type = "image/webp"  # Default to webp if we compress

            if can_compress_to_webp(filename):
                compressed, was_compressed = compress_image_to_webp(content)
                if was_compressed:
                    processed_data = compressed
                    log.debug(f"Compressed {filename}: {len(content)} -> {len(processed_data)} bytes")
                else:
                    # Compression didn't help, use original
                    processed_data = content
                    mime_type = get_mime_type(filename)
            else:
                # GIF or other non-compressible, use as-is
                processed_data = content
                mime_type = get_mime_type(filename)

            # Check if this file fits in our budget
            embedded_size = calculate_base64_size(len(processed_data))

            # Check against max individual size using PROCESSED size (after compression)
            if len(processed_data) > MAX_INDIVIDUAL_IMAGE_SIZE:
                # Individual file too large even after compression, skip embedding
                log.debug(f"File {filename} too large for embedding ({len(processed_data)} bytes after processing)")
                files_for_zip.append(file_data)
                return

            if embedded_size <= current_budget:
                files_to_embed.append((html_url, processed_data, mime_type))
                current_budget -= embedded_size
                embedded_filenames.append(filename)
                log.debug(f"Will embed {filename} ({embedded_size} bytes, budget remaining: {current_budget})")
            else:
                # Doesn't fit, add to zip
                log.debug(f"No budget for {filename} ({embedded_size} bytes needed, {current_budget} available)")
                files_for_zip.append(file_data)
        else:
            # Non-image, non-video, non-audio file - add to zip
            files_for_zip.append(file_data)

    # Process in a thread to avoid blocking
    def process_all_files():
        for html_url in sorted_urls:
            process_file(html_url, matched_urls[html_url])

    await asyncio.to_thread(process_all_files)

    # Step 7: Replace URLs in HTML with data URIs
    def replace_urls(html_content: str) -> str:
        result = html_content
        for html_url, data, mime_type in files_to_embed:
            data_uri = create_data_uri(data, mime_type)
            # Replace all occurrences of this URL
            result = result.replace(html_url, data_uri)
        return result

    processed_html = await asyncio.to_thread(replace_urls, html)

    # Also add any downloaded files that weren't matched to URLs to the zip
    matched_file_ids = processed_file_ids
    for f in downloaded_files:
        if id(f) not in matched_file_ids:
            files_for_zip.append(f)
            log.debug(f"Unmatched file going to zip: {f['filename']}")

    log.debug(f"Embedding {len(embedded_filenames)} files, {len(files_for_zip)} going to zip")
    return processed_html, files_for_zip, embedded_filenames
