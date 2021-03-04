# The MIT License (MIT)
#
# Copyright (c) 2021 Mieszko Exchange

import asyncio
from decimal import Decimal
from typing import Union

import discord
from discord.ext import commands

from .utils.db import (EscrowAction, EscrowActioner, EscrowEvent,
                       EscrowPayment, EscrowStatus, SavedAddress, User)
from .utils.logger import get_logger
from .utils.payment_api import ApiResponseError, CurrencyType

log = get_logger()

MaybeRemoteMember = Union[ discord.Member, discord.User ]

# TODO:

# ergonomics of error messages !!

# secret escrow flow for sensitive information
# [moderator] cancel and release
# database writes
# checks for default addresses [x]
# flow for specifying adresses not found [x]

class AddressFlowError(Exception):
    pass

class AddressFlowDMsError(AddressFlowError):
    pass

class Escrow(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # give an opportunity to save an address in the address flow
    async def ask_save_address(self, msg, user, currency, address, react):
        def is_dm_response(reaction, r_user):
            return (reaction.message.id == msg.id
                and r_user.id == user.id
                and str(reaction.emoji) == react)

        try:
            response = await self.bot.wait_for("reaction_add", timeout=5 * 60, check=is_dm_response)

        except asyncio.TimeoutError:
            pass

        else:
            changed = await self.bot.db.add_address_for(user.id, currency, address, create_private=True)
            if changed is not None:
                await user.send(f"\N{THUMBS UP SIGN} Saved that address (private) for {currency.value}")

    # make sure we have addresses, one way or another
    async def do_address_flow(self, msg, sender, receiver, currency):
        sender_address = await self.bot.db.get_address_for(sender.id, currency)
        receiver_address = await self.bot.db.get_address_for(receiver.id, currency)

        def is_sender_dm_response(message):
            return (message.channel.type == discord.ChannelType.private
                and message.author.id == sender.id
                and message.channel.recipient.id == sender.id)

        def is_receiver_dm_response(message):
            return (message.channel.type == discord.ChannelType.private
                and message.author.id == receiver.id
                and message.channel.recipient.id == receiver.id)

        if not sender_address:
            try:
                query = await sender.send(f"Looks like you don't have an address on file for {currency.name}...\nSend me your address now. (timeout in 60s)")

            except discord.Forbidden:
                await msg.channel.send(
                    f"Hey {sender.display_name}, I need to DM you to setup this transaction. Please make sure you have DMs enabled.",
                    reference=msg
                )
                raise AddressFlowDMsError(f"{sender.name} has DMs disabled")

            else:
                await self.bot.post_reaction(msg, emoji="\N{POSTBOX}")
                try:
                    response = await self.bot.wait_for("message", timeout=60.0, check=is_sender_dm_response)
                    log.debug(response)
                except asyncio.TimeoutError:
                    await query.edit(content=f"{query.content}\n*No address received after 60s, timed out.*")
                    raise AddressFlowError(f"{sender.name} did not respond in time")

                else:
                    sender_address = response.clean_content
                    confirmation = await sender.send("Got it, thanks.\n*click the green checkmark to save this address for future use (timeout in 5m)*")
                    react = await self.bot.post_reaction(confirmation, emoji="\N{WHITE HEAVY CHECK MARK}")
                    self.bot.loop.create_task(self.ask_save_address(confirmation, sender, currency, sender_address, react))

        if not receiver_address:
            try:
                query = await receiver.send(f"{sender.display_name} wants to send you {currency.value}, but you don't have an address on file for that currency...\nSend me your address now. (timeout in 60s)")

            except discord.Forbidden:
                await msg.channel.send(
                    f"Hey {receiver.mention}, I need to DM you to setup this transaction. Please make sure you have DMs enabled.",
                    reference=msg,
                    mention_author=False
                )
                raise AddressFlowDMsError(f"{receiver.name} has DMs disabled")

            else:
                await self.bot.post_reaction(msg, emoji="\N{POSTBOX}")
                try:
                    response = await self.bot.wait_for("message", timeout=60.0, check=is_receiver_dm_response)
                    log.debug(response)
                except asyncio.TimeoutError:
                    await query.edit(content=f"{query.content}\nNo address received after 60s, timed out.*")
                    raise AddressFlowError(f"{receiver.name} did not respond in time")

                else:
                    receiver_address = response.clean_content
                    confirmation = await receiver.send("Got it, thanks.\n*click the green checkmark to save this address for future use (timeout in 5m)*")
                    react = await self.bot.post_reaction(confirmation, emoji="\N{WHITE HEAVY CHECK MARK}")
                    self.bot.loop.create_task(self.ask_save_address(confirmation, receiver, currency, receiver_address, react))


        return (sender_address, receiver_address)

    # actual escrow commands
    @commands.group(name="escrow", brief="securely send money", invoke_without_command=True)
    @commands.is_owner()
    async def escrow_group(self, ctx):
        await self.bot.post_reaction(ctx.message, emoji="\N{CALL ME HAND}")

    @escrow_group.command(name="send", brief="initiate an escrow transaction")
    @commands.is_owner()
    async def escrow_send(self, ctx, recipient: MaybeRemoteMember, amount: Decimal, currency: CurrencyType, *, note: str = None):
        await self.bot.db.ensure_user(ctx.author.id)
        await self.bot.db.ensure_user(recipient.id)

        sender = ctx.author
        receiver = recipient

        try:
            sender_addr, receiver_addr = await self.do_address_flow(ctx.message, sender, receiver, currency)

            if isinstance(sender_addr, SavedAddress):
                sender_addr = sender_addr.address

            if isinstance(receiver_addr, SavedAddress):
                receiver_addr = receiver_addr.address

        except AddressFlowError as e:
            if not isinstance(e, AddressFlowDMsError):
                await ctx.send(f"\N{NO ENTRY} Cannot initiate escrow transaction: {e}", reference=ctx.message, mention_author=False)

        else:

            payment_id = await self.bot.db.create_payment(
                currency, sender.id, receiver.id, sender_addr, receiver_addr, amount, reason=note
            )

            await ctx.send(f"Sending {amount} {currency.name} to {receiver.name}\n({sender_addr} -> {receiver_addr})\n> {note}\nPayment ID: {payment_id}")

    @escrow_group.command(name="abort", brief="abort a pending transaction")
    @commands.is_owner()
    async def escrow_abort(self, ctx, receiver: MaybeRemoteMember, *, reason: str = None):
        await ctx.send(f"Aborting your pending transaction with {receiver.name}\n{f'> {reason}' if reason else ''}")

    @escrow_group.command(name="release", brief="release escrow money to the recipient")
    @commands.is_owner()
    async def escrow_release(self, ctx, receiver: MaybeRemoteMember):
        await ctx.send(f"Releasing your held money to {receiver.name}")

    @escrow_group.command(name="cancel", brief="cancel a transaction and refund money")
    @commands.is_owner()
    async def escrow_cancel(self, ctx, sender: MaybeRemoteMember, *, reason: str = None):
        await ctx.send(f"Cancelling your escrow transaction with {sender.name}. They will be refunded shortly.\n{f'> {reason}' if reason else ''}")


def setup(bot):
    bot.add_cog(Escrow(bot))
