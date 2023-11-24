import re


def clean_name(name: str):
    """
    Cleans the function name to ensure it only contains alphanumeric characters,
    underscores, or dashes and is not longer than 64 characters.

    Args:
        name (str): The original function name to clean.

    Returns:
        str: The cleaned function name.
    """
    # Remove any characters that are not alphanumeric, underscore, or dash
    cleaned_name = re.sub(r"[^a-zA-Z0-9_-]", "", name)

    # Truncate the string to 64 characters if it's longer
    cleaned_name = cleaned_name[:64]

    return cleaned_name
