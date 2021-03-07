# The MIT License (MIT)
#
# Copyright (c) 2021 Mieszko Exchange

import asyncio
from decimal import Decimal
from typing import Union

import discord
from discord.ext import commands

from .utils.db import (
    BalanceRecipient,
    DecimalInvalidAmountError,
    DecimalPrecisionError,
    EscrowAction,
    EscrowActioner,
    EscrowActionType,
    EscrowPayment,
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
def check_terms_accept_response(user, message, options):
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
    async def ensure_accept_terms(self, member, *, to_recipient=False):
        emoji_accept = "\N{WHITE HEAVY CHECK MARK}"
        emoji_decline = "\N{CROSS MARK}"

        user = await self.bot.db.get_user_details(member.id)

        if user is None:
            try:
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
                        check=check_terms_accept_response(member, terms_check, (emoji_accept, emoji_decline)),
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

    @commands.group(name="escrow", brief="manage escrow transactions", invoke_without_command=True)
    @commands.is_owner()
    async def escrow_group(self, ctx):
        await self.bot.post_reaction(ctx.message, emoji="\N{CALL ME HAND} **₿** \N{SIGN OF THE HORNS}")

    @escrow_group.command(name="send", brief="initiate an escrow transaction")
    @commands.is_owner()
    async def escrow_send(
        self, ctx, recipient: MaybeRemoteMember, amount: Decimal, currency: CurrencyType, *, note: str = None
    ):
        sender = ctx.author

        maybe_tx = await self.bot.db.get_active_transaction_by_participants(sender.id, recipient.id)

        if maybe_tx is not None:
            await ctx.send(
                f"\N{NO ENTRY} You already have an active transaction to {recipient.display_name}.\nFinish or close that one before opening a new one.",
                reference=ctx.message,
            )

        else:
            await self.bot.post_reaction(ctx.message, dms=True)

            try:
                await self.ensure_accept_terms(sender)
                await self.ensure_accept_terms(recipient, to_recipient=True)

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
                    verified_amount = self.bot.db.ensure_precise_amount(currency, amount)

                except DecimalInvalidAmountError as e:
                    await ctx.send(f"\N{WARNING SIGN} The amount ({e.args[0]}) is not valid")

                else:
                    maybe_sender_addr = await self.bot.db.get_address_for(sender.id, currency)
                    maybe_reciever_addr = await self.bot.db.get_address_for(recipient.id, currency)

                    payment_id = await self.bot.db.create_payment(
                        currency,
                        sender.id,
                        recipient.id,
                        verified_amount,
                        src_addr=getattr(maybe_sender_addr, "address", None),
                        dst_addr=getattr(maybe_reciever_addr, "address", None),
                    )
                    if payment_id is None:
                        log.critical(f"Could not write payment event for (UNSET, s={sender.id}, r={recipient.id}")
                        raise RuntimeError("database write failed")

                    await ctx.send(
                        f"Sending {verified_amount} {currency.name} to {recipient.name}\n> {note}\nPayment ID: {payment_id}"
                    )


def setup(bot):
    bot.add_cog(Escrow(bot))
