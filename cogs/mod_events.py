# The MIT License (MIT)
#
# Copyright (c) 2021 Mieszko Exchange

import traceback
from enum import Enum

import discord
from discord.ext import commands, ipc

from .utils import colors as C
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

    # Discord event listeners

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.NoPrivateMessage):
            await ctx.send("\N{WARNING SIGN} You cannot use that command in a direct message channel")

        elif isinstance(error, commands.CommandNotFound):
            log.debug(f"Could not find command '{ctx.invoked_with}' for '{ctx.author.name}'")

        elif isinstance(error, commands.CheckFailure):
            log.debug(f"Check failed for '{ctx.author.name}' on '{ctx.invoked_with}'")

        elif isinstance(error, commands.DisabledCommand):
            await self.bot.post_reaction(ctx.message)

        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"Slow down, {ctx.author.display_name}! Try again in {round(error.retry_after)} seconds")

        elif isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
            await ctx.send(f"\N{WARNING SIGN} {error}")

        elif isinstance(error, discord.Forbidden):
            log.warn(f"{ctx.command.qualified_name} failed: Forbidden")

        elif isinstance(error, commands.CommandInvokeError):
            original_name = error.original.__class__.__name__
            print(f"In {ctx.command.qualified_name @ C.on_bright_red.bold}:")
            traceback.print_tb(error.original.__traceback__)
            print(f"{original_name @ C.on_black.bold.bright_red}: {error.original}")

        else:
            print(f">> ! {f'[{type(error).__name__}]' @ C.on_red.bold}: {error}")


    # IPC event listeners

    @commands.Cog.listener()
    async def on_ipc_error(self, endpoint, error):
        print(f"IPC endpoint {endpoint @ C.on_yellow} raised an error.\n{error @ C.bright_red}")
        traceback.print_tb(error.__traceback__)




def setup(bot):
    bot.add_cog(Events(bot))
