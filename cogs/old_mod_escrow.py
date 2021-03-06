# The MIT License (MIT)
#
# Copyright (c) 2021 Mieszko Exchange

import asyncio
from decimal import Decimal
from typing import Union

import discord
from discord.ext import commands

from .utils.db import (
    DecimalInvalidAmountError,
    DecimalPrecisionError,
    EscrowAction,
    EscrowActioner,
    EscrowEvent,
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

# ergonomics of error messages !!

# secret escrow flow for sensitive information [x]
# database writes [x]
# checks for default addresses [x]
# flow for specifying adresses not found [x]
# notifications for transaction status


class AddressFlowError(Exception):
    pass


class AddressFlowDMsError(AddressFlowError):
    pass


class Escrow(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # make sure they read the terms/privacy policy and accept it before using the service
    async def do_terms_flow():
        pass

    # give an opportunity to save an address in the address flow
    async def ask_save_address(self, msg, user, currency, address, react):
        def is_dm_response(reaction, r_user):
            return reaction.message.id == msg.id and r_user.id == user.id and str(reaction.emoji) == react

        try:
            response = await self.bot.wait_for("reaction_add", timeout=5 * 60, check=is_dm_response)

        except asyncio.TimeoutError:
            try:
                await msg.edit(content=f"{msg.content}\n(timed out)")
                await react.remove(self.bot.user)

            except:
                pass

        else:
            changed = await self.bot.db.add_address_for(user.id, currency, address, create_private=True)
            if changed is not None:
                await user.send(f"\N{THUMBS UP SIGN} Saved that address (private) for {currency.value}")

    # make sure we have addresses, one way or another
    async def do_address_flow(self, msg, sender, receiver, currency, *, amount=None):
        sender_address = await self.bot.db.get_address_for(sender.id, currency)
        receiver_address = await self.bot.db.get_address_for(receiver.id, currency)

        def is_sender_dm_response(message):
            return (
                message.channel.type == discord.ChannelType.private
                and message.author.id == sender.id
                and message.channel.recipient.id == sender.id
            )

        def is_receiver_dm_response(message):
            return (
                message.channel.type == discord.ChannelType.private
                and message.author.id == receiver.id
                and message.channel.recipient.id == receiver.id
            )

        if not sender_address:
            try:
                query = await sender.send(
                    f"Looks like you don't have an address on file for {currency.name}...\nSend me your address now. (timeout in 60s)"
                )

            except discord.Forbidden:
                await msg.channel.send(
                    f"Hey {sender.display_name}, I need to DM you to setup this transaction. Please make sure you have DMs enabled.",
                    reference=msg,
                )
                raise AddressFlowDMsError(f"{sender.name} has DMs disabled")

            else:
                await self.bot.post_reaction(msg, dms=True)
                try:
                    response = await self.bot.wait_for("message", timeout=60 * 60, check=is_sender_dm_response)
                    log.debug(response)
                except asyncio.TimeoutError:
                    await query.edit(content=f"{query.content}\n*No address received after 1h, timed out.*")
                    raise AddressFlowError(f"{sender.name} did not respond in time")

                else:
                    sender_address = response.clean_content
                    confirmation = await sender.send(
                        "Got it, thanks.\n*click the green checkmark to save this address for future use (timeout in 5m)*"
                    )
                    react = await self.bot.post_reaction(confirmation, success=True)
                    self.bot.loop.create_task(
                        self.ask_save_address(confirmation, sender, currency, sender_address, react)
                    )

        if not receiver_address:
            try:
                query = await receiver.send(
                    f"Someone wants to send you {f'{amount} ' if amount is not None else ''}{currency.value}, but you don't have an address on file for that currency...\nSend me your address now. (timeout in 60s)"
                )

            except discord.Forbidden:
                await msg.channel.send(
                    f"Hey {receiver.mention}, I need to DM you to setup this transaction. Please make sure you have DMs enabled.",
                    reference=msg,
                    mention_author=False,
                )
                raise AddressFlowDMsError(f"{receiver.name} has DMs disabled")

            else:
                await self.bot.post_reaction(msg, dms=True)
                try:
                    response = await self.bot.wait_for("message", timeout=60 * 60, check=is_receiver_dm_response)
                    log.debug(response)
                except asyncio.TimeoutError:
                    await query.edit(content=f"{query.content}\nNo address received after 1h, timed out.*")
                    raise AddressFlowError(f"{receiver.name} did not respond in time")

                else:
                    receiver_address = response.clean_content
                    confirmation = await receiver.send(
                        "Got it, thanks.\n*click the green checkmark to save this address for future use (timeout in 5m)*"
                    )
                    react = await self.bot.post_reaction(confirmation, success=True)
                    self.bot.loop.create_task(
                        self.ask_save_address(confirmation, receiver, currency, receiver_address, react)
                    )

        return (sender_address, receiver_address)

    # actual escrow commands
    @commands.group(name="escrow", brief="securely send money", invoke_without_command=True)
    @commands.is_owner()
    async def escrow_group(self, ctx):
        await self.bot.post_reaction(ctx.message, emoji="\N{CALL ME HAND}")

    @escrow_group.command(name="send", brief="initiate an escrow transaction")
    @commands.is_owner()
    async def escrow_send(
        self, ctx, recipient: MaybeRemoteMember, amount: Decimal, currency: CurrencyType, *, note: str = None
    ):
        sender = ctx.author

        maybe_transaction = await self.bot.db.get_active_payment_by_participants(sender.id, recipient.id)

        if maybe_transaction is not None:
            await ctx.send(
                f"\N{NO ENTRY} Sorry, you already have an active transaction with {recipient.name}.\nFinish or close that one before opening a new one.",
                reference=ctx.message,
            )

        else:
            await self.bot.db.ensure_user(sender.id)
            await self.bot.db.ensure_user(recipient.id)

            try:
                verified_amount = await self.bot.db.ensure_precise_amount(currency, amount)

            except DecimalInvalidAmountError as e:
                await ctx.send(f"\N{WARNING SIGN} The amount ({e.args[0]}) is not valid")

            else:
                try:
                    sender_addr, receiver_addr = await self.do_address_flow(
                        ctx.message, sender, recipient, currency, amount=verified_amount
                    )

                    if isinstance(sender_addr, SavedAddress):
                        sender_addr = sender_addr.address

                    if isinstance(receiver_addr, SavedAddress):
                        receiver_addr = receiver_addr.address

                except AddressFlowError as e:
                    if not isinstance(e, AddressFlowDMsError):
                        await ctx.send(
                            f"\N{NO ENTRY} Cannot initiate escrow transaction: {e}",
                            reference=ctx.message,
                            mention_author=False,
                        )

                else:

                    payment_id = await self.bot.db.create_payment(
                        currency, sender.id, recipient.id, sender_addr, receiver_addr, verified_amount, reason=note
                    )
                    if payment_id is None:
                        log.critical(f"Could not write payment event for (UNSET, s={sender.id}, r={recipient.id}")
                        raise RuntimeError("database write failed")

                    await ctx.send(
                        f"Sending {verified_amount} {currency.name} to {recipient.name}\n({sender_addr} -> {receiver_addr})\n> {note}\nPayment ID: {payment_id}"
                    )

    @escrow_group.command(name="abort", brief="abort a pending transaction")
    @commands.is_owner()
    async def escrow_abort(self, ctx, recipient: MaybeRemoteMember, *, reason: str = None):
        sender = ctx.author

        maybe_transaction = await self.bot.db.get_active_payment_by_participants(sender.id, recipient.id)

        if maybe_transaction is None:
            await ctx.send(
                f"\N{WARNING SIGN} Looks like you don't have an active transaction going to {recipient.name}.",
                reference=ctx.message,
            )

        else:
            if maybe_transaction.status == EscrowStatus.Received:
                await ctx.send(
                    f"\N{NO ENTRY} You cannot abort a paid transaction. Ask the recipient or an escrow manager to cancel it for you.",
                    reference=ctx.message,
                )

            else:
                did_report = await self.bot.db.create_payment_event(
                    maybe_transaction.id, EscrowAction.Aborted, EscrowActioner.Sender, sender.id, message=reason
                )
                did_update = await self.bot.db.update_payment_status(maybe_transaction.id, EscrowStatus.Failed)

                if not (did_report and did_update):
                    log.critical(
                        f"Could not write payment event for ({maybe_transaction.id}, s={maybe_transaction.sender}, r={maybe_transaction.receiver}"
                    )
                    raise RuntimeError("database write failed")

                await ctx.send(
                    f"Aborted your pending transaction (ID: {maybe_transaction.id}) with {recipient.name}\n{f'> {reason}' if reason else ''}"
                )

    @escrow_group.command(name="release", brief="release escrow money to the recipient")
    @commands.is_owner()
    async def escrow_release(self, ctx, recipient: MaybeRemoteMember):
        sender = ctx.author

        maybe_transaction = await self.bot.db.get_active_payment_by_participants(sender.id, recipient.id)

        if maybe_transaction is None:
            await ctx.send(
                f"\N{WARNING SIGN} Looks like you don't have an active transaction going to {recipient.name}.",
                reference=ctx.message,
            )

        else:
            if maybe_transaction.status == EscrowStatus.Pending:
                await ctx.send(
                    f"\N{NO ENTRY} You cannot release an unpaid transaction.\n(If you wish to cancel this transaction, you may do `{ctx.prefix}{self.bot.get_command('escrow abort').qualified_name}`)",
                    reference=ctx.message,
                )

            else:
                did_report = await self.bot.db.create_payment_event(
                    maybe_transaction.id, EscrowAction.Released, EscrowActioner.Sender, sender.id
                )
                did_update = await self.bot.db.update_payment_status(maybe_transaction.id, EscrowStatus.Completed)

                if not (did_report and did_update):
                    log.critical(
                        f"Could not write payment event for ({maybe_transaction.id}, s={maybe_transaction.sender}, r={maybe_transaction.receiver}"
                    )
                    raise RuntimeError("database write failed")

                await ctx.send(f"Released your transaction (ID: {maybe_transaction.id}) to {recipient.name}")

    @escrow_group.command(name="cancel", brief="cancel a transaction and refund money")
    @commands.is_owner()
    async def escrow_cancel(self, ctx, sender: MaybeRemoteMember, *, reason: str = None):
        recipient = ctx.author

        maybe_transaction = await self.bot.db.get_active_payment_by_participants(sender.id, recipient.id)

        if maybe_transaction is None:
            await ctx.send(
                f"\N{WARNING SIGN} Looks like you don't have an active transaction coming from {sender.name}.",
                reference=ctx.message,
            )

        else:
            if maybe_transaction.status == EscrowStatus.Pending:
                await ctx.send(
                    f"\N{NO ENTRY} You cannot cancel a pending transaction.\nHave the sender abort or have an escrow manager cancel for you.",
                    reference=ctx.message,
                )

            else:
                did_report = await self.bot.db.create_payment_event(
                    maybe_transaction.id, EscrowAction.Cancelled, EscrowActioner.Recipient, recipient.id, message=reason
                )
                did_update = await self.bot.db.update_payment_status(maybe_transaction.id, EscrowStatus.Failed)

                if not (did_report and did_update):
                    log.critical(
                        f"Could not write payment event for ({maybe_transaction.id}, s={maybe_transaction.sender}, r={maybe_transaction.receiver}"
                    )
                    raise RuntimeError("database write failed")

                await ctx.send(
                    f"Cancelling your escrow transaction with {sender.name}. They will be refunded shortly.\n{f'> {reason}' if reason else ''}"
                )


def setup(bot):
    bot.add_cog(Escrow(bot))
