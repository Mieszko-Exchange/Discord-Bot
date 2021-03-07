# The MIT License (MIT)
#
# Copyright (c) 2021 Mieszko Exchange

from typing import Union

import discord
from discord.ext import commands

from .utils.db import (
    DecimalInvalidAmountError,
    DecimalPrecisionError,
    EscrowActioner,
    EscrowActionType,
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

# [developer] add/view/remove escrow moderators [cancelled]
# [moderator] transaction control [x]
# [moderator] lock/unlock user accounts
# [moderator] transaction view (all recent, recent by criteria, all by criteria)
# [moderator] action view (same as above)


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="admin", brief="manage escrow transactions", invoke_without_command=True)
    @commands.is_owner()
    async def admin_group(self, ctx):
        await self.bot.post_reaction(ctx.message, emoji="\N{CALL ME HAND}")

    @admin_group.command(name="release", brief="release money to the recipient")
    @commands.is_owner()
    async def admin_release(self, ctx, sender: MaybeRemoteMember, recipient: MaybeRemoteMember):
        maybe_transaction = await self.bot.db.get_active_payment_by_participants(sender.id, recipient.id)

        if maybe_transaction is None:
            await ctx.send(
                f"\N{WARNING SIGN} Looks like {sender.name} doesn't have a transaction going to {recipient.name}.",
                reference=ctx.message,
            )

        else:
            if maybe_transaction.status == EscrowStatus.Pending:
                await ctx.send(
                    f"\N{NO ENTRY} {sender.name} has not paid this transaction yet, it cannot be released.",
                    reference=ctx.message,
                )

            else:
                did_report = await self.bot.db.create_payment_event(
                    maybe_transaction.id, EscrowActionType.Released, EscrowActioner.Moderator, ctx.author.id
                )
                did_update = await self.bot.db.update_payment_status(maybe_transaction.id, EscrowStatus.Completed)

                if not (did_report and did_update):
                    log.critical(
                        f"Could not write payment event for ({maybe_transaction.id}, s={maybe_transaction.sender}, r={maybe_transaction.receiver}"
                    )
                    raise RuntimeError("database write failed")

                await ctx.send(f"Released {sender.name}'s transaction (ID: {maybe_transaction.id}) to {recipient.name}")

    @admin_group.command(name="cancel", brief="cancel a transaction and refund")
    @commands.is_owner()
    async def admin_cancel(self, ctx, sender: MaybeRemoteMember, recipient: MaybeRemoteMember, *, reason: str = None):
        maybe_transaction = await self.bot.db.get_active_payment_by_participants(sender.id, recipient.id)

        if maybe_transaction is None:
            await ctx.send(
                f"\N{WARNING SIGN} Looks like {sender.name} doesn't have a transaction going to {recipient.name}.",
                reference=ctx.message,
            )

        else:
            did_report = await self.bot.db.create_payment_event(
                maybe_transaction.id,
                EscrowActionType.Cancelled,
                EscrowActioner.Moderator,
                ctx.author.id,
                message=reason,
            )
            did_update = await self.bot.db.update_payment_status(maybe_transaction.id, EscrowStatus.Failed)

            if not (did_report and did_update):
                log.critical(
                    f"Could not write payment event for ({maybe_transaction.id}, s={maybe_transaction.sender}, r={maybe_transaction.receiver}"
                )
                raise RuntimeError("database write failed")

            await ctx.send(
                f"Cancelling {sender.name}'s transaction to {recipient.name}. They will be refunded shortly.\n{f'> {reason}' if reason else ''}"
            )


def setup(bot):
    bot.add_cog(Admin(bot))
