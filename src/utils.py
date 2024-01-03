import os


def is_debug():
    return os.environ.get("DEBUG", False)
