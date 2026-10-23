# [0.4.1] (2026-10-23)

## Security

- Game images downloaded from their URLs are only opened as PNG, JPEG, WebP or GIF. A crafted image in a rarer format (such as FlashPix) could run code through a Pillow bug. Image links in other formats are now treated as unreadable images when added, tested or picked for a game
