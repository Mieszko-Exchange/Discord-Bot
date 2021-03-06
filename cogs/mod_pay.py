# The MIT License (MIT)
#
# Copyright (c) 2021 Mieszko Exchange

from decimal import Decimal

import discord
from discord.ext import commands

from .utils.db import DecimalInvalidAmountError

# from .utils import checks
from .utils.logger import get_logger
from .utils.payment_api import ApiResponseError, CurrencyType

log = get_logger()


class Pay(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Request test
    @commands.command(name="request", brief="request money")
    @commands.is_owner()
    async def request_payment(self, ctx, coin: CurrencyType, amount: float):
        try:
            response = await self.bot.payment_client.request_payment(coin, amount)

        except Exception as e:
            await ctx.send(f"[{type(e).__name__}]: {e}")

        else:
            await ctx.send(f"Transaction filed..\n{response}")

    @commands.command(name="addrs_for")
    @commands.is_owner()
    async def check_addr(self, ctx, coin: CurrencyType):
        currency_data = await self.bot.db.get_addresses_for(ctx.author.id, coin)

        await ctx.send(f"```\n{currency_data!r}\n```")

    @commands.command(name="addrs", enabled=False)
    @commands.is_owner()
    async def get_addrs(self, ctx):
        currency_data = await self.bot.db.get_all_addresses(ctx.author.id)

        await ctx.send(f"```\n{currency_data!r}\n```")

    @commands.command(name="get_tx")
    @commands.is_owner()
    async def get_transaction(self, ctx, sender: discord.User, receiver: discord.User):
        data = await self.bot.db.get_active_payment_by_participants(sender.id, receiver.id)

        await ctx.send(f"```\n{data!r}\n```")

    @commands.command(name="amount")
    @commands.is_owner()
    async def get_amount(self, ctx, amount: Decimal, coin: CurrencyType):
        try:
            verified_amount = await self.bot.db.ensure_precise_amount(coin, amount)

        except DecimalInvalidAmountError as e:
            await ctx.send(
                f"\N{WARNING SIGN} The amount {e.args[0]} is not valid. A maximum of {e.args[1]} decimal places is allowed."
            )
            return

        await ctx.send(f"Verified amount is {verified_amount} {coin.value}")


def setup(bot):
    bot.add_cog(Pay(bot))
