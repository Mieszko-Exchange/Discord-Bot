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



def setup(bot):
    bot.add_cog(Pay(bot))
