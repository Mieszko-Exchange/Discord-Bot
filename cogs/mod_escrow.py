# The MIT License (MIT)
#
# Copyright (c) 2021 Mieszko Exchange

import asyncio
from decimal import Decimal
from typing import Union

import discord
from discord.ext import commands

from .utils.db import (
    DecimalInvalidAmountError,
    DecimalPrecisionError,
    EscrowAction,
    EscrowActioner,
    EscrowEvent,
    EscrowPayment,
    EscrowStatus,
    SavedAddress,
    User,
)
from .utils.logger import get_logger
from .utils.payment_api import ApiResponseError, CurrencyType

log = get_logger()

MaybeRemoteMember = Union[discord.Member, discord.User]

# TODO:

# ergonomics of error messages !!

# secret escrow flow for sensitive information [x]
# database writes [x]
# checks for default addresses [x]
# flow for specifying adresses not found [x]
# notifications for transaction status


class Escrow(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


def setup(bot):
    bot.add_cog(Escrow(bot))
