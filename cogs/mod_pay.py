# The MIT License (MIT)
#
# Copyright (c) 2021 Mieszko Exchange

import discord
from discord.ext import commands

#from .utils import checks
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

    @commands.command(name="addrs")
    @commands.is_owner()
    async def get_addrs(self, ctx):
        currency_data = await self.bot.db.get_all_addresses(ctx.author.id)

        await ctx.send(f"```\n{currency_data!r}\n```")


    @commands.command(name="get_tx")
    @commands.is_owner()
    async def get_transaction(self, ctx, sender: discord.User, receiver: discord.User):
        data = await self.bot.db.get_active_payment_by_participants(sender.id, receiver.id)

        await ctx.send(f"```\n{data!r}\n```")



def setup(bot):
    bot.add_cog(Pay(bot))
