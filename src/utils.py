import os


def env_var_to_bool(s: str | None) -> bool:
    if s is None:
        return False
    truevals = ("yes", "y", "on", "true", "t", "1")
    falsevals = ("no", "n", "off", "false", "f", "0")
    if s.lower() in truevals:
        return True
    if s.lower() in falsevals:
        return False
    return True


def is_debug() -> bool:
    return env_var_to_bool(os.getenv("DEBUG"))
