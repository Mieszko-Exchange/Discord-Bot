# The MIT License (MIT)
#
# Copyright (c) 2021 Mieszko Exchange

import discord
from discord.ext import commands

from .utils.db import SavedAddress
from .utils.logger import get_logger
from .utils.payment_api import CurrencyType

log = get_logger()

# TODO:

# add/remove/edit/view linked addresses
# view own/others public addresses
# look user up by public address

class Accounts(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


def setup(bot):
    bot.add_cog(Accounts(bot))
