# The MIT License (MIT)
#
# Copyright (c) 2021 Mieszko Exchange

from decimal import Decimal
from typing import Union

import discord
from discord.ext import commands

from .utils.db import (EscrowAction, EscrowActioner, EscrowEvent,
                       EscrowPayment, EscrowStatus, SavedAddress)
from .utils.logger import get_logger
from .utils.payment_api import ApiResponseError, CurrencyType

log = get_logger()

MaybeRemoteMember = Union[ discord.Member, discord.User ]

# TODO:

# secret escrow flow for sensitive information
# [moderator] cancel and release
# database writes
# checks for default addresses
# flow for specifying adresses not found


class Escrow(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="escrow", brief="securely send money", invoke_without_command=True)
    @commands.is_owner()
    async def escrow_group(self, ctx):
        await self.bot.post_reaction(ctx.message, emoji="\N{CALL ME HAND}")

    @escrow_group.command(name="send", brief="initiate an escrow transaction")
    @commands.is_owner()
    async def escrow_send(self, ctx, receiver: MaybeRemoteMember, amount: Decimal, currency: CurrencyType, *, note: str):
        await ctx.send(f"Sending {amount} {currency.name} to {receiver.name}\n> {note}")

    @escrow_group.command(name="release", brief="release escrow money to the recipient")
    @commands.is_owner()
    async def escrow_release(self, ctx, receiver: MaybeRemoteMember):
        await ctx.send(f"Releasing your held money to {receiver.name}")

    @escrow_group.command(name="cancel", brief="cancel a transaction and refund money")
    @commands.is_owner()
    async def escrow_cancel(self, ctx, sender: MaybeRemoteMember):
        await ctx.send(f"Cancelling your escrow transaction with {sender.name}. They will be refunded shortly.")


def setup(bot):
    bot.add_cog(Escrow(bot))
