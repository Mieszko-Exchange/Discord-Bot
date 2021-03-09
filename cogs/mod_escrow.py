# The MIT License (MIT)
#
# Copyright (c) 2021 Mieszko Exchange

import asyncio
from datetime import datetime
from decimal import Decimal
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

TERMS_EMBED = discord.Embed.from_dict(
    {
        "title": "Please review the privacy policy and terms of use to continue",
        "description": "Click the **green** check to accept, and the **red** X to decline.",
        "color": 0xB71C1C,
        "fields": [
            {"name": "Privacy", "value": "blah blah blah *your soul belongs to me*"},
            {
                "name": "Terms",
                "value": "blah blah and more blah\nDue to the financial nature of this service, any data you supply may be permanent.",
            },
            {"name": "Privacy Contact", "value": "not my job lol", "inline": True},
            {"name": "Privacy Contact", "value": "Pixel maybe", "inline": True},
        ],
    }
)

# TODO:

# ergonomics of error messages !!

# secret escrow flow for sensitive information
# database writes
# checks for default addresses
# flow for specifying adresses not found
# notifications for transaction status


# exception classes for escrow flows


class EnsureTermsDMsFailure(Exception):
    pass


class NoAcceptTermsError(Exception):
    pass


# check for accept terms
def check_message_react_response(user, message, options):
    def predicate(reaction, member):
        return member == user and reaction.message == message and reaction.emoji in options

    return predicate


class Escrow(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def remove_reactions(self, message, reactions):
        for reaction in reactions:
            try:
                await message.remove_reaction(reaction, self.bot.user)

            except:
                pass

    # make sure the user has viewed the terms before using the service
    async def ensure_accept_terms(self, message, member, *, to_recipient=False):
        emoji_accept = "\N{WHITE HEAVY CHECK MARK}"
        emoji_decline = "\N{CROSS MARK}"

        user = await self.bot.db.get_user_details(member.id)

        if user is None:
            try:
                # await self.bot.post_reaction(message, dms=True)

                terms_check = await member.send(
                    content=f"Hi, {member.name}. Before you use the escrow service, you'll need to confirm a few things.\n\n*Timeout in 10m*",
                    embed=TERMS_EMBED,
                )

                await terms_check.add_reaction(emoji_accept)
                await terms_check.add_reaction(emoji_decline)

            except discord.Forbidden:
                raise EnsureTermsDMsFailure(member)

            else:
                try:
                    terms_response, _ = await self.bot.wait_for(
                        "reaction_add",
                        timeout=10 * 60,
                        check=check_message_react_response(member, terms_check, (emoji_accept, emoji_decline)),
                    )

                except asyncio.TimeoutError:
                    await terms_check.edit(content=f"{terms_check.content}\n\n(timed out)")
                    await self.remove_reactions(terms_check, (emoji_accept, emoji_decline))

                    raise NoAcceptTermsError(member, "timed out")

                else:
                    if terms_response.emoji == emoji_decline:
                        await self.remove_reactions(terms_check, (emoji_accept, emoji_decline))

                        raise NoAcceptTermsError(member, "declined")

                    else:
                        await self.bot.db.create_user(member.id)
                        await self.remove_reactions(terms_check, (emoji_accept, emoji_decline))

                        if to_recipient:
                            await member.send(
                                "Thank you. You will be contacted for status updates on your escrow transaction."
                            )

                        else:
                            await member.send("Thank you. You may return to your transaction.")

    # allow the user to save an address for future use
    async def ask_save_address(self, channel, member, currency, address):
        accept_emoji = "\N{WHITE HEAVY CHECK MARK}"

        address_check = await channel.send(
            f"Would you like to save that address for future use with {currency.name}?\n*Click the green checkmark to save, timeout in 5m*"
        )

        await address_check.add_reaction(accept_emoji)

        try:
            address_response, _ = await self.bot.wait_for(
                "reaction_add",
                timeout=5 * 60,
                check=check_message_react_response(member, address_check, (accept_emoji,)),
            )

        except asyncio.TimeoutError:
            await address_check.edit(content=f"{address_check.content}\n\n(timed out)")
            await self.remove_reactions(address_check, (accept_emoji,))

        else:
            did_create = await self.bot.db.add_address_for(member.id, currency, address)
            if did_create:
                await self.remove_reactions(address_check, (accept_emoji,))
                await channel.send(f"\N{OK HAND SIGN} Saved that address for use with {currency.value}.")

    @commands.group(name="escrow", brief="manage escrow transactions", invoke_without_command=True)
    @commands.is_owner()
    async def escrow_group(self, ctx):
        await self.bot.post_reaction(ctx.message, emoji="\N{CALL ME HAND} **₿** \N{SIGN OF THE HORNS}")

    @escrow_group.command(name="send", brief="initiate an escrow transaction")
    @commands.is_owner()
    async def escrow_send(
        self, ctx, recipient: MaybeRemoteMember, amount: Decimal, currency: CurrencyType, *, note: Optional[str] = None
    ):
        sender = ctx.author

        maybe_tx = await self.bot.db.get_active_payment_by_participants(sender.id, recipient.id)

        if maybe_tx is None:
            try:
                await self.ensure_accept_terms(ctx.message, sender)
                await self.ensure_accept_terms(ctx.message, recipient, to_recipient=True)

            except EnsureTermsDMsFailure as e:
                if e.args[0] == sender:
                    await ctx.send(
                        f"\N{WARNING SIGN} I need to DM you to setup this transaction. Please make sure you have DMs enabled.",
                        reference=ctx.message,
                    )

                else:
                    await ctx.send(
                        f"\N{WARNING SIGN} I need to DM {recipient.display_name} to setup this transaction. Please make sure they have DMs enabled.",
                        reference=ctx.message,
                    )

            except NoAcceptTermsError as e:
                if e.args[0] == sender:
                    await sender.send(
                        f"\N{NO ENTRY} You must review and agree to the terms of service before you engage in an escrow transaction."
                    )

                else:
                    await recipient.send(
                        f"\N{NO ENTRY} You must review and agree to the terms of service before you engage in an escrow transaction."
                    )

                    await ctx.send(
                        f"\N{WARNING SIGN} {recipient.display_name} did not agree to the terms of service; the transaction cannot continue.",
                        reference=ctx.message,
                    )

            else:
                try:
                    verified_amount = await self.bot.db.ensure_precise_amount(currency, amount)

                except DecimalInvalidAmountError as e:
                    await ctx.send(f"\N{WARNING SIGN} The amount ({e.args[0]}) is not valid")

                else:
                    payment_requested = True  # TODO: payments API tie-in here
                    # TODO: payment expiry task

                    if payment_requested:
                        payment_id = await self.bot.db.create_payment(
                            currency, sender.id, recipient.id, verified_amount, reason=note
                        )

                        if payment_id:
                            did_create = await self.bot.db.create_wallet(payment_id, datetime.utcnow().isoformat())

                            if did_create:
                                await ctx.send(
                                    f"Sending {verified_amount} {currency.name} to {recipient.display_name}\n> {note}\nPayment ID: {payment_id}"
                                )
                            else:
                                log.critical(f"Could not write wallet data for TX:{payment_id}")
                                raise RuntimeError("database write failed")

                        else:
                            log.critical(f"Could not write payment event for (UNSET, s={sender.id}, r={recipient.id}")
                            raise RuntimeError("database write failed")

                    else:
                        log.error(f"Payment request failed. ({payment_requested})")
                        await ctx.send(
                            f"\N{NO ENTRY} Payments API had bad response, cannot initiate transaction.",
                            reference=ctx.message,
                        )

        else:
            await ctx.send(
                f"\N{NO ENTRY} You already have an active transaction to {recipient.display_name}.\nFinish or close that one before opening a new one.",
                reference=ctx.message,
            )

    @escrow_group.command(name="cancel", brief="cancel a transaction and refund")
    @commands.is_owner()
    async def escrow_cancel(self, ctx, sender: MaybeRemoteMember, *, reason: Optional[str] = None):
        recipient = ctx.author

        maybe_tx = await self.bot.db.get_active_payment_by_participants(sender.id, recipient.id)

        if maybe_tx is not None:
            if maybe_tx.status == EscrowStatus.Paid:
                did_report = await self.bot.db.create_payment_event(
                    maybe_tx.id,
                    EscrowActionType.Cancelled,
                    EscrowActioner.Recipient,
                    recipient.id,
                    message=reason,
                )
                did_update = await self.bot.db.update_payment_status(maybe_tx.id, EscrowStatus.Failed)
                did_relase = await self.bot.db.release_wallet(maybe_tx.id, EscrowRecipient.Sender)

                if all((did_report, did_update, did_relase)):
                    await ctx.send(
                        f"Cancelling your escrow transaction with {sender.display_name}. They will be refunded shortly.\n{f'> {reason}' if reason else ''}"
                    )
                    # TODO: sender notify flow

                else:
                    log.critical(
                        f"Could not write payment event for ({maybe_tx.id}, s={maybe_tx.sender}, r={maybe_tx.receiver}"
                    )
                    raise RuntimeError("database write failed")

            else:
                await ctx.send(
                    f"\N{NO ENTRY} You cannot cancel a pending transaction.\nHave the sender abort or have an escrow manager cancel for you.",
                    reference=ctx.message,
                )

        else:
            await ctx.send(
                f"\N{WARNING SIGN} Looks like you don't have an active transaction coming from {recipient.display_name}.",
                reference=ctx.message,
            )

    @escrow_group.command(name="abort", brief="abort a pending transaction")
    @commands.is_owner()
    async def escrow_abort(self, ctx, recipient: MaybeRemoteMember, *, reason: Optional[str] = None):
        sender = ctx.author

        maybe_tx = await self.bot.db.get_active_payment_by_participants(sender.id, recipient.id)

        if maybe_tx is not None:
            if maybe_tx.status == EscrowStatus.Pending:
                did_report = await self.bot.db.create_payment_event(
                    maybe_tx.id, EscrowActionType.Aborted, EscrowActioner.Sender, sender.id, message=reason
                )

                did_update = await self.bot.db.update_payment_status(maybe_tx.id.EscrowStatus.Failed)
                did_delete = await self.bot.db.delete_wallet(maybe_tx.id)

                if all((did_report, did_update, did_delete)):
                    await ctx.send(
                        f"Aborted your pending transaction (ID: {maybe_tx.id}) with {recipient.display_name}\n{f'> {reason}' if reason else ''}"
                    )

                else:
                    log.critical(
                        f"Could not write payment event for ({maybe_tx.id}, s={maybe_tx.sender}, r={maybe_tx.receiver}"
                    )
                    raise RuntimeError("database write failed")

            else:
                await ctx.send(
                    f"\N{NO ENTRY} You cannot abort a paid transaction. Ask the recipient or an escrow manager to cancel it for you.",
                    reference=ctx.message,
                )

        else:
            await ctx.send(
                f"\N{WARNING SIGN} Looks like you don't have an active transaction going to {recipient.display_name}.",
                reference=ctx.message,
            )

    @escrow_group.command(name="release", brief="release escrow to the recipient")
    @commands.is_owner()
    async def escrow_release(self, ctx, recipient: MaybeRemoteMember):
        sender = ctx.author

        maybe_tx = await self.bot.db.get_active_payment_by_participants(sender.id, recipient.id)

        if maybe_tx is not None:
            if maybe_tx.status == EscrowStatus.Received:
                did_report = await self.bot.db.create_payment_event(
                    maybe_tx.id, EscrowActionType.Released, EscrowActioner.Sender, sender.id
                )
                did_update = await self.bot.db.update_payment_status(maybe_tx.id, EscrowStatus.FundsHeld)
                did_release = await self.bot.db.release_wallet(maybe_tx.id, EscrowRecipient.Receiver)

                if all((did_report, did_update, did_release)):
                    await ctx.send(f"Released your transaction (ID: {maybe_tx.id}) to {recipient.display_name}")

                    # TODO: recipient notify flow

                else:
                    log.critical(
                        f"Could not write payment event for ({maybe_tx.id}, s={maybe_tx.sender}, r={maybe_tx.receiver}"
                    )
                    raise RuntimeError("database write failed")

            else:
                await ctx.send(
                    f"\N{NO ENTRY} You cannot release an unpaid transaction.\n(If you wish to cancel this transaction, you may do `{ctx.prefix}escrow abort {recipient.display_name}`)",
                    reference=ctx.message,
                )

        else:
            await ctx.send(
                f"\N{WARNING SIGN} Looks like you don't have an active transaction going to {recipient.name}.",
                reference=ctx.message,
            )

    @escrow_group.command(name="withdraw", brief="withdraw from a released or cancelled escrow")
    @commands.is_owner()
    async def escrow_withdraw(self, ctx, other_party: MaybeRemoteMember, *, address: Optional[str] = None):
        party_a = ctx.author
        party_b = other_party

        maybe_tx = await self.bot.db.get_held_payment_by_participants(party_b.id, party_a.id)
        wallet_details = None
        tx_is_failed = False

        if maybe_tx is not None:
            wallet_details = await self.bot.db.get_details_for_withdrawal(maybe_tx.id)

        else:
            maybe_tx = await self.bot.db.get_held_payment_by_participants(party_b.id, party_a.id, check_failed=True)

            if maybe_tx is not None:
                tx_is_failed = True
                wallet_details = await self.bot.db.get_details_for_withdrawal(maybe_tx.id, check_failed=True)

        if maybe_tx is not None:
            if wallet_details is not None:
                dest_address = wallet_details.dest_address

                # TODO: make this flow more ergonomic

                if address and not dest_address:
                    self.bot.loop.create_task(
                        self.ask_save_address(ctx.channel, ctx.author, wallet_details.currency, address)
                    )

                if address and dest_address:
                    await ctx.send(
                        f"You already have a saved address for this currency, but you're withdrawing to a new one. To edit addresses, use `{ctx.prefix}account edit {currency.value}`."
                    )

                if dest_address and not address:
                    address = dest_address.address

                if address:
                    payment_sent = True  # TODO: payments api tie-in here
                    if payment_sent:
                        did_report = await self.bot.db.update_payment_status(maybe_tx.id, EscrowStatus.Completed)
                        did_mark = await self.bot.db.mark_as_withdrawn(maybe_tx.id)

                        if all((did_report, did_mark)):
                            await ctx.send(
                                f"Withdrawing {wallet_details.amount} {wallet_details.currency.value} to `{address}`.\nExpect a transaction from `{wallet_details.source_address}` shortly.\n{f'> {maybe_tx.reason}' if maybe_tx.reason else ''}"
                            )

                            # TODO: party B notify flow

                        else:
                            log.critical(
                                f"Could not write withdraw event for  ({maybe_tx.id}, s={maybe_tx.sender}, r={maybe_tx.receiver}"
                            )
                            raise RuntimeError("database write failed")

                else:
                    await ctx.send("\N{NO ENTRY} No valid address found.")

            else:
                await ctx.send(f"\N{WARNING SIGN} Eligible TX, but no funds available.")

        else:
            await ctx.send(
                f"\N{WARNING SIGN} Looks like you don't have an eligible transaction with {other_party.display_name}.\nTo withdraw from an escrow, the transaction must be released or cancelled.",
                reference=ctx.message,
            )


def setup(bot):
    bot.add_cog(Escrow(bot))
