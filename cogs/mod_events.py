# The MIT License (MIT)
#
# Copyright (c) 2021 Mieszko Exchange

from enum import Enum

import discord
from discord.ext import commands, ipc

from .utils.logger import get_logger

log = get_logger()


class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    def _reduce(data):
        if isinstance(data, list):
            return [Events._reduce(item) for item in data]

        if isinstance(data, dict):
            return {Events._reduce(key): Events._reduce(value) for (key, value) in data.items()}

        if isinstance(data, Enum):
            return data.value

        if hasattr(data, "_asdict"):
            return Events._reduce(data._asdict())

        return data



def setup(bot):
    bot.add_cog(Events(bot))
