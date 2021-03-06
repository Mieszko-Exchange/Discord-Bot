# The MIT License (MIT)
#
# Copyright (c) 2021 Mieszko Exchange

__all__ = "read", "ConfigReadError"

from functools import lru_cache
from pathlib import Path

import toml


class ConfigReadError(Exception):
    pass


@lru_cache
def read(file_path):
    if not isinstance(file_path, Path):
        file_path = Path(file_path)

    file = file_path.resolve()

    if not file.exists():
        raise ConfigReadError(f"named path `{file_path}` does not exist")

    if not file.is_file():
        raise ConfigReadError(f"named path `{file_path}` is not a file")

    try:
        text = file.read_text()

    except Exception as e:
        raise ConfigReadError(f"read error: {e}") from e

    try:
        data = toml.loads(text)

    except Exception as e:
        raise ConfigReadError(f"parse error: {e}") from e

    return data
