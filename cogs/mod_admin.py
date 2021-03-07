# The MIT License (MIT)
#
# Copyright (c) 2021 Mieszko Exchange

from typing import Union

import discord
from discord.ext import commands

from .utils.db import (
    BalanceRecipient,
    DecimalInvalidAmountError,
    DecimalPrecisionError,
    EscrowAction,
    EscrowActioner,
    EscrowActionType,
    EscrowPayment,
    EscrowStatus,
    EscrowWallet,
    SavedAddress,
    User,
    WithdrawalDetails,
)
from .utils.logger import get_logger
from .utils.payment_api import ApiResponseError, CurrencyType

log = get_logger()

MaybeRemoteMember = Union[discord.Member, discord.User]

# TODO:

# [developer] add/view/remove escrow moderators [cancelled]
# [moderator] transaction control
# [moderator] lock/unlock user accounts
# [moderator] transaction view (all recent, recent by criteria, all by criteria)
# [moderator] action view (same as above)


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


def setup(bot):
    bot.add_cog(Admin(bot))
