# The MIT License (MIT)
#
# Copyright (c) 2021 Mieszko Exchange

import asyncio
import sys
from datetime import datetime
from pathlib import Path

import aiohttp
import discord
from discord.ext import commands, ipc

from cogs.utils import colors as C
from cogs.utils import config, logger
from cogs.utils.db import SQL
from cogs.utils.payment_api import PaymentClient

# Attempt to load uvloop for improved event loop performance
try:
    import uvloop

except ModuleNotFoundError:
    print("Can't find uvloop, defaulting to standard policy" @ C.bold.on_red)

else:
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    print("Using uvloop policy" @ C.bold.on_green)

_DEBUG = any(arg.lower() == "debug" for arg in sys.argv)

log = None


class Builtin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="quit", brief="shutdown bot")
    @commands.is_owner()
    async def quit_command(self, ctx):
        await self.bot.payment_client.close()
        await self.bot.db.close()

        await self.bot.logout()

    @commands.group(name="cog", brief="manage cogs", invoke_without_command=True)
    @commands.is_owner()
    async def manage_cogs(self, ctx, name: str, action: str):
        print("cogs")

    @manage_cogs.command(name="load", brief="load cog")
    @commands.is_owner()
    async def load_cog(self, ctx, name: str):
        cog_name = "cogs.mod_" + name.lower()

        if self.bot.extensions.get(cog_name) is not None:
            await self.bot.post_reaction(ctx.message, emoji="\N{SHRUG}")

        else:
            try:
                self.bot.load_extension(cog_name)

            except Exception as e:
                await ctx.send(f"Failed to load {name}: [{type(e).__name__}]: `{e}`")

            else:
                await self.bot.post_reaction(ctx.message, success=True)

    @manage_cogs.command(name="unload", brief="unload cog")
    @commands.is_owner()
    async def unload_cog(self, ctx, name: str):
        cog_name = "cogs.mod_" + name.lower()

        if self.bot.extensions.get(cog_name) is None:
            await self.bot.post_reaction(ctx.message, emoji="\N{SHRUG}")

        else:
            try:
                self.bot.unload_extension(cog_name)

            except Exception as e:
                await ctx.send(f"Failed to unload {name}: [{type(e).__name__}]: `{e}`")

            else:
                await self.bot.post_reaction(ctx.message, success=True)

    @manage_cogs.command(name="reload", brief="reload cog")
    @commands.is_owner()
    async def reload_cog(self, ctx, name: str):
        cog_name = "cogs.mod_" + name.lower()

        if self.bot.extensions.get(cog_name) is None:
            await self.bot.post_reaction(ctx.message, emoji="\N{SHRUG}")

        else:
            try:
                self.bot.unload_extension(cog_name)
                self.bot.load_extension(cog_name)

            except Exception as e:
                await ctx.send(f"Failed to reload {name}: [{type(e).__name__}]: `{e}`")

            else:
                await self.bot.post_reaction(ctx.message, success=True)

    @manage_cogs.command(name="list", brief="list loaded cogs")
    @commands.is_owner()
    async def list_cogs(self, ctx, name: str = None):
        if name is None:
            await ctx.send(
                f"Currently loaded cogs:\n{' '.join('`' + cog_name + '`' for cog_name in self.bot.extensions)}"
                if len(self.bot.extensions) > 0
                else "No cogs loaded"
            )

        else:
            if self.bot.extensions.get("cogs.mod_" + name) is None:
                await self.bot.post_reaction(ctx.message, failure=True)

            else:
                await self.bot.post_reaction(ctx.message, success=True)


# TODO

# SHORT TERM:
#   sponsored giveaway
#   send tips
#   referrals maybe

# MED TERM:
#   puzzle/timed drops
#   take cut from tips/giveaways to fund drops
#   have donation feature to turn off house cut for a time (based on donation amount)


# LONG TERM:
#   act as client for exchange "serious business"
#   maybe house-backed coin, generated by interaction or exchange
#   escrow service?


# Mieszko - Yesterday at 8:18 PM
# 99% of the time escrow mods won't need to be involved
# /escrow send @user amount currency [free text]
# /escrow release @user - only sender (and mods) can do this
# /escrow cancel @user - only receiver (and mods) can do this

# Short term- personal wallets
# Or escrow or both
# Escrow should work such that people can use it on their own without involvement from us and only come to us if they need to
# And ofc /balance, /send would be better with / commands to hide people's balances if we can


class BrokerBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        # Set up custom stuff before discord.py init
        self.debug = _DEBUG
        self._session_exists = False

        self.loop = asyncio.get_event_loop()

        self.config = config.read("./config.toml")
        self.required_permissions = discord.Permissions(permissions=26688)

        # Load secret credentials
        credentials = config.read("./credentials.toml")
        self.token = credentials["Discord"]["token"]

        self.start_time = None
        self.resume_time = None

        help_cmd = commands.DefaultHelpCommand(command_attrs=dict(hidden=True))

        _intents = discord.Intents.default()
        _intents.members = True
        # Discord.py init
        super().__init__(
            *args,
            **kwargs,
            intents=_intents,
            help_command=help_cmd,
            description="Robo-broker, a handy helper for Mieszko.Exchange",
            command_prefix=commands.when_mentioned_or(self.config["General"]["default_prefix"]),
        )

        # TODO: aiohttp task here

        self.db = SQL(**credentials["Database"], **self.config.get("Database"))

        self.payment_client = PaymentClient(credentials["Exchange"]["api_key"])

        self.ipc = ipc.Server(self, secret_key=credentials["IPC"]["secret"])

        self.payment_tasks = {}  # dict[(sender_id, receiver_id): task]

        global log
        log = logger.get_logger()

        # logger.prepare_logger("discord.ext.ipc.server")

        self.boot_time = datetime.utcnow()

        for file in (Path(__file__).parent / "cogs").glob("mod*.py"):
            if file.is_file():
                name = file.stem[4:]
                cog_name = f"cogs.{file.stem}"

                print(f"Loading {f'[{name}]' @ C.on_bright_blue}")

                try:
                    self.load_extension(cog_name)
                except Exception as e:
                    print(f"Failed to load {f'[{name}]' @ C.on_bright_red}: [{type(e).__name__}]: {e}")

    # Helper functions

    async def post_reaction(self, message: discord.Message, emoji=None, **kwargs):
        reaction = ""

        if emoji is None:
            if kwargs.get("success"):
                reaction = "\N{WHITE HEAVY CHECK MARK}"

            elif kwargs.get("failure"):
                reaction = "\N{CROSS MARK}"

            elif kwargs.get("warning"):
                reaction = "\N{WARNING SIGN}"

            elif kwargs.get("dms"):
                reaction = "\N{POSTBOX}"

            else:
                reaction = "\N{NO ENTRY}"

        else:
            reaction = emoji

        try:
            await message.add_reaction(reaction)

        except Exception as e:
            if not kwargs.get("quiet"):
                await message.channel.send(reaction)

        return reaction

    # Discord events

    async def on_ready(self):
        self.start_time = datetime.utcnow()
        boot_duration = self.start_time - self.boot_time
        print(
            f"Logged in as {self.user.name @ C.on_green}#{self.user.discriminator @ C.on_yellow.bold}{' DEBUG MODE' @ C.bright_magenta if self.debug else ''}\nLoaded in {boot_duration @ C.on_cyan}"
        )

        await self.db.init()

        log.info("Started listening")

        await self.change_presence(activity=discord.Game(f"{self.config['General']['default_prefix']}help"))

    async def on_ipc_ready(self):
        print(f"IPC server is listening {f'[{self.ipc.host}:{self.ipc.port}]' @ C.white.on_black}")

    async def on_resume(self):
        print("resumed")

    # Magic methods

    def __enter__(self):
        if self.is_ready():
            raise RuntimeError("Bot already running")

        self.add_cog(Builtin(self))

        return self

    def __exit__(self, t, value, tb):
        print("Exiting.." @ C.yellow)

        return True


with BrokerBot() as bot:
    bot.ipc.start()
    bot.run(bot.token)
