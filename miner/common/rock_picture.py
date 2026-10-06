import io

from PIL import Image, ImageChops

from . import constants


def with_effects(image_file: str, modifiers: list[constants.Modifier]) -> bytes:
    """Return the live rock picture with each modifier's effect blended on top, as webp bytes.

    Effects are light on pure black, so a screen blend drops the black and stacks cleanly with each other.
    """
    center_x, center_y, size = constants.EFFECT_PLACEMENTS[image_file]
    with Image.open(constants.ROCK_IMAGE_DIR / image_file) as base:
        picture = base.convert("RGB")
    width = picture.width
    effect_width = round(width * size)
    corner = (round(width * center_x - effect_width / 2), round(width * center_y - effect_width / 2))
    for modifier in modifiers:
        with Image.open(constants.EFFECT_IMAGE_DIR / f"{modifier.key}.webp") as effect:
            scaled = effect.convert("RGB").resize((effect_width, effect_width), Image.Resampling.LANCZOS)
        layer = Image.new("RGB", picture.size)
        layer.paste(scaled, corner)
        picture = ImageChops.screen(picture, layer)
    buffer = io.BytesIO()
    picture.save(buffer, "WEBP", quality=85)
    return buffer.getvalue()
