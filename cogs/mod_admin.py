# The MIT License (MIT)
#
# Copyright (c) 2021 Mieszko Exchange

from typing import Optional, Union

import discord
from discord.ext import commands

from .utils.db import (
    DecimalInvalidAmountError,
    DecimalPrecisionError,
    EscrowAction,
    EscrowActioner,
    EscrowActionType,
    EscrowPayment,
    EscrowRecipient,
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

    @commands.group(name="admin", brief="manage escrow transactions", invoke_without_command=True)
    @commands.is_owner()
    async def admin_group(self, ctx):
        await self.bot.post_reaction(ctx.message, emoji="\N{CALL ME HAND} **₿** \N{SIGN OF THE HORNS}")

    @admin_group.command(name="release", brief="release money to the recipient")
    @commands.is_owner()
    async def admin_release(
        self,
        ctx,
        sender: MaybeRemoteMember,
        recipient: MaybeRemoteMember,
        confirmation_number: int,
        *,
        reason: Optional[str] = None,
    ):
        maybe_tx = await self.bot.db.get_active_payment_by_participants(sender.id, recipient.id)

        if maybe_tx is not None:
            if confirmation_number == maybe_tx.id:
                if maybe_tx.status == EscrowStatus.Received:
                    did_report = await self.bot.db.create_payment_event(
                        maybe_tx.id, EscrowActionType.Released, EscrowActioner.Moderator, ctx.author.id, message=reason
                    )
                    did_update = await self.bot.db.update_payment_status(maybe_tx.id, EscrowStatus.FundsHeld)
                    did_release = await self.bot.db.release_wallet(maybe_tx.id, EscrowRecipient.Receiver)

                    if all((did_report, did_update, did_release)):
                        await ctx.send(
                            f"Released {sender.display_name}'s transaction (ID: {maybe_tx.id}) to {recipient.display_name}"
                        )

                        # TODO: notify flow

                    else:
                        log.critical(
                            f"Could not write payment event for ({maybe_tx.id}, s={maybe_tx.sender}, r={maybe_tx.receiver}"
                        )
                        raise RuntimeError("database write failed")

                else:
                    await ctx.send(
                        f"\N{NO ENTRY} {sender.display_name} has not submitted payment for this transaction yet, it cannot be released.",
                        reference=ctx.message,
                    )

            else:
                await ctx.send(
                    f"\N{WARNING SIGN} Confirmation ID does not match transaction ID, please double check your information and try again.",
                    reference=ctx.message,
                )

        else:
            await ctx.send(
                f"\N{WARNING SIGN} Looks like {sender.display_name} doesn't have an active transaction going to {recipient.display_name}.",
                reference=ctx.message,
            )

    @admin_group.command(name="cancel", brief="cancel a transaction and refund")
    @commands.is_owner()
    async def admin_cancel(
        self,
        ctx,
        sender: MaybeRemoteMember,
        recipient: MaybeRemoteMember,
        confirmation_number: int,
        *,
        reason: Optional[str] = None,
    ):
        maybe_tx = await self.bot.db.get_active_payment_by_participants(sender.id, recipient.id)

        if maybe_tx is not None:
            if confirmation_number == maybe_tx.id:
                did_report = await self.bot.db.create_payment_event(
                    maybe_tx.id, EscrowActionType.Cancelled, EscrowActioner.Moderator, ctx.author.id, message=reason
                )
                did_update = await self.bot.db.update_payment_status(maybe_tx.id, EscrowStatus.Failed)
                did_release = await self.bot.db.release_wallet(maybe_tx.id, EscrowRecipient.Sender)

                if all((did_report, did_update, did_release)):
                    await ctx.send(
                        f"Cancelling {sender.display_name}'s escrow transaction with {recipient.display_name}.\n{f'> {reason}' if reason else ''}"
                    )
                    # TODO: notify flow

                else:
                    log.critical(
                        f"Could not write payment event for ({maybe_tx.id}, s={maybe_tx.sender}, r={maybe_tx.receiver}"
                    )
                    raise RuntimeError("database write failed")

            else:
                await ctx.send(
                    f"\N{WARNING SIGN} Confirmation ID does not match transaction ID, please double check your information and try again.",
                    reference=ctx.message,
                )

        else:
            await ctx.send(
                f"\N{WARNING SIGN} Looks like {sender.display_name} doesn't have an active transaction going to {recipient.display_name}.",
                reference=ctx.message,
            )


def setup(bot):
    bot.add_cog(Admin(bot))
