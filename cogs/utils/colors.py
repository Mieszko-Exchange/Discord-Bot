# The MIT License (MIT)
#
# Copyright (c) 2021 Mieszko Exchange

# Please don't ask questions about this code
# just remember the picture of Homer with his loose skin clipped up behind his back
# ... it WORKS

import sys
import types
from dataclasses import InitVar, dataclass, field
from enum import Enum
from typing import List, Optional


class Color(Enum):
    Black = 0
    Red = 1
    Green = 2
    Yellow = 3
    Blue = 4
    Magenta = 5
    Cyan = 6
    White = 7

    BrightBlack = 60
    BrightRed = 61
    BrightGreen = 62
    BrightYellow = 63
    BrightBlue = 64
    BrightMagenta = 65
    BrightCyan = 66
    BrightWhite = 67

    def fg(self):
        return str(self.value + 30)

    def bg(self):
        return str(self.value + 40)

    @classmethod
    def from_str(cls, name):
        clean_name = name.lower().title().replace("_", "")
        if clean_name in cls.__members__:
            return cls.__members__[clean_name]


class Style(Enum):
    Clear = 0
    Bold = 1
    Dimmed = 2
    Italic = 3
    Underline = 4
    Blink = 5
    Reversed = 6
    Hidden = 7
    Strikethrough = 8

    @classmethod
    def from_str(cls, name: str):
        clean_name = name.lower().title()
        if clean_name in cls.__members__:
            return cls.__members__[clean_name]

    @classmethod
    def from_bitflag(cls, flag: int):
        if flag is None:
            return []

        return [style for name in cls.__members__ if (flag >> (style := getattr(cls, name)).value) & 1]

    @property
    def bitmask(self):
        return 1 << self.value


@dataclass
class StylizedString:
    foreground: Optional[Color]
    background: Optional[Color]
    style_flag: InitVar[Optional[int]]
    text: str
    styles: List[Style] = field(init=False)

    def __post_init__(self, style_flag):
        self.styles = Style.from_bitflag(style_flag)

    def __str__(self):
        f_style = f"{self.foreground.fg()};" if self.foreground is not None else ""
        b_style = f"{self.background.bg()};" if self.background is not None else ""
        styles = ";".join(map(str, (style.value for style in self.styles))) if self.styles is not None else ""

        return f"\x1b[{(f'{styles};{f_style}{b_style}').strip(';')}m{self.text}"


class StyleHandler(types.ModuleType):
    __foreground: Optional[Color] = None
    __background: Optional[Color] = None
    __style: Optional[int] = None
    __spans: List[StylizedString] = []

    def __getattr__(self, name: str):
        if (style := Style.from_str(name)) is None:
            clean_name = name[3 if name.startswith("on_") else 0 :]
            is_fg = name == clean_name

            if (color := Color.from_str(clean_name)) is None:
                raise ValueError(f"Color or style `{name}` is not known")

            if is_fg:
                if self.__foreground is not None:
                    raise ValueError(f"Duplicate foreground colors specified, `{clean_name}` cannot be applied")

                else:
                    self.__foreground = color

            else:
                if self.__background is not None:
                    raise ValueError(f"Duplicate background colors specified, `{clean_name}` cannot be applied")

                else:
                    self.__background = color

        else:
            if style == Style.Clear:
                self.__foreground = None
                self.__background = None
                self.__style = style.bitmask

            else:
                if self.__style is None:
                    self.__style = style.bitmask
                else:
                    self.__style |= style.bitmask

        return self

    def __rmatmul__(self, text: str):
        # if not isinstance(text, str):
        #   raise RuntimeError("oops")

        span = StylizedString(self.__foreground, self.__background, self.__style, str(text))

        # self.__foreground = None
        # self.__background = None
        # self.__style = None
        _ = self.clear

        self.__spans.append(span)

        return self

    def __add__(self, other):
        if not isinstance(other, self.__class__):
            raise TypeError(f"other (`{other!r}`) should be StyleHandler, not {other.__class__.__name__}")

            assert self.__spans == other._StyleHandler__spans, "uh-oh"

        return self

    def __str__(self):
        formatted = f"{''.join(map(str, self.__spans))}\x1b[0m"

        self.__spans = []
        self.__foreground = None
        self.__background = None
        self.__style = None

        return formatted


sys.modules[__name__].__class__ = StyleHandler
