# from typing import Any, Union

import aiohttp
from datetime import datetime, timezone
import discord
from redbot.core import commands
from redbot.core import checks
from redbot.core import Config
import urllib.parse
import asyncio
import re

# noinspection PyUnresolvedReferences

# Beer: https://untappd.com/beer/<bid>
# Brewery: https://untappd.com/brewery/<bid>
# Checkin: https://untappd.com/c/<checkin>
# Deeplink Beer: untappd://beer/BEER_ID
# Deeplink Brewery: untappd:///brewery/BREWERY_ID
# Deeplink Checkin: untappd://checkin/CHECKIN_ID
# prefix = ctx.prefix

BaseCog = getattr(commands, "Cog", object)


class Untappd(BaseCog):
    """Untappd cog that lets the bot look up beer
    information from untappd.com!"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=19006438562, force_registration=True)  # Arbitrary but unique ID
        default_config = {
            "max_items_in_list": 5,
            "supporter_emoji": ":moneybag:",
            "moderator_emoji": ":crown:",
            "app_emoji": ":beers:",
            "toast_emoji": ":beers:",
            "client_id": "",
            "client_secret": "",
            "CONFIG": False
        }
        self.config.register_global(**default_config)
        self.channels = {}
        self.is_chatty = False  # Lets some debugging / annoying PMs happen

    @commands.group(invoke_without_command=False)
    async def groupdrink(self, ctx):
        """Settings for a drinking project"""
        pass

    @groupdrink.command()
    @commands.guild_only()
    @checks.mod_or_permissions(manage_messages=True)
    async def sheet_url(self, ctx, url):
        """The published web app URL that accepts GETs and POSTs"""
        await self.config.set_raw(ctx.guild.id, "project_url", value=url)
        await ctx.send("The project endpoint URL has been set")

    @groupdrink.command()
    @commands.guild_only()
    @checks.mod_or_permissions(manage_messages=True)
    async def finish(self, ctx):
        """The published web app URL that accepts GETs and POSTs"""
        await self.config.set_raw(ctx.guild.id, "project_url", value="")
        await ctx.send("The drinking project has been temporarily"
                       " suspended.")

    @commands.group(invoke_without_command=False)
    async def untappd(self, ctx):
        """Explicit Untappd things"""
        # TODO: This might be sending help twice now.
        pass

    @untappd.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def list_size(self, ctx, new_size: int):
        """The length of lists of results specific to a server now"""
        is_pm = not ctx.guild
        server = ctx.guild.id if ctx.guild else 0
        if new_size > 10:
            new_size = 10
            await ctx.send("Reducing the maximum size to "
                           "10 due to emoji constraints")
        if is_pm:
            await self.config.max_items_in_list.set(new_size)
        else:
            await self.config.set_raw(server, "max_items_in_list", value=new_size)
        await ctx.send("Maximum list size is now {!s}".format(new_size))

    @untappd.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def supporter_emoji(self, ctx, emoji: str):
        """The emoji to use for supporters"""
        await self.config.supporter_emoji.set(emoji)
        await ctx.send("Profiles of supporters will now display ("
                       + str(emoji) + ")")

    @untappd.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def moderator_emoji(self, ctx, emoji: str):
        """The emoji to use for super users"""
        await self.config.moderator_emoji.set(emoji)
        await ctx.send("Profiles of super users will now display ("
                       + str(emoji) + ")")

    @untappd.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def app_emoji(self, ctx, emoji: str):
        """The emoji to use for super users"""
        await self.config.app_emoji.set(emoji)
        await ctx.send("App deep links will now use ("
                       + str(emoji) + ")")

    @untappd.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def toast_emoji(self, ctx, emoji: str):
        """The emoji to use for super users"""
        await self.config.toast_emoji.set(emoji)
        await ctx.send("People who react to checkins with {!s} will be toasting!".format(emoji))

    @untappd.command()
    @commands.guild_only()
    async def setnick(self, ctx, keywords):
        """Set your untappd user name to use for future commands"""
        if not keywords:
            await ctx.send_help()
        else:
            author = ctx.author.id
            await self.config.set_raw(ctx.guild.id, author, "nick", value=keywords)
            await ctx.send("When you look yourself up on untappd"
                           " I will use `" + keywords + "`")

    @untappd.command()
    async def authme(self, ctx):
        """Starts the authorization process for a user"""
        auth_url = ("https://untappd.com/oauth/authenticate/?client_id="
                    "{!s}&response_type=token&redirect_url={!s}").format(
            await self.config.client_id(),
            "https://aardwolf.github.io/tokenrevealer.html"
        )
        auth_string = ("Please authenticate with untappd then follow the"
                       " instructions on [this page]"
                       "({!s}) using the proper prefix").format(auth_url)
        embed = embedme(auth_string, title="Authorization")
        disclaimer = ("Following this link and providing the resulting "
                      "token to the bot will allow it to act as you. "
                      "Currently that involves some lookups and all toasts."
                      " Permission can be revoked from the untappd website "
                      "and with the `unauthme` command")
        await ctx.author.send(disclaimer, embed=embed)

    @untappd.command(name="auth-token")
    async def auth_token(self, ctx, keyword):
        """Finishes the authorization process"""
        if not keyword:
            await ctx.send_help()
        else:
            author = ctx.message.author.id
            await self.config.set_raw(author, "token", value=keyword)
            await ctx.author.send("Token saved, thank you")
            if isinstance(ctx.message.channel, discord.TextChannel):
                try:
                    await ctx.message.delete()
                except discord.Forbidden:
                    await ctx.author.send("I tried to remove your token message because it was in a public channel"
                                          " but was not allowed to. You should delete it.")
                else:
                    await ctx.author.send("I removed your token because it was in a public channel")

    @untappd.command()
    async def unauthme(self, ctx):
        """Removes the authorization token for a user"""
        author = ctx.author.id
        try:
            await self.config.get_raw(author)  # Will throw KeyError if author not in config
            await self.config.clear_raw(author, "token")
            response = "Authorization removed"
        except KeyError:
            response = "It doesn't look like you were authorized before"
        await ctx.send(response)

    @untappd.command()
    async def friend(self, ctx, profile: str = None):
        """Accepts existing friend requests from user specified or
        sends a friend request to the user specified"""

        keys = await get_auth(ctx.author.id, self.config)
        if "access_token" not in keys:
            await ctx.send("You must first authorize me to act as you"
                           " using `untappd authme`")
            return

        guild = str(ctx.guild.id) if ctx.guild else 0

        credentials = await check_credentials(self.config)
        if not credentials:
            await ctx.send("The owner has not set the API information "
                           "and should use the `untappd_apikey` command")
            return

        if ctx.message.mentions:
            # If user has set a nickname, use that - but only if it's not a PM
            if guild:
                user = ctx.message.mentions[0]
                try:
                    profile = await self.config.get_raw(guild, user.id, "nick")
                except KeyError:
                    profile = user.display_name

        if not profile:
            await ctx.send("Friend who? Give me a name!")
            return

        # TODO migrate this to with ctx.channel.typing():
        await ctx.channel.trigger_typing()
        qstr = urllib.parse.urlencode(keys)
        # This will be needed several times
        # First get the UID for the profile
        uid = 0
        url = ("https://api.untappd.com/v4/user/info/{!s}?{!s}"
               ).format(profile, qstr)
        j = await get_data_from_untappd(ctx.author, url)
        if "meta" in j:
            if int(j["meta"]["code"]) == 200:
                if "user" in j["response"]:
                    uid = j['response']['user']['uid']
                else:
                    await ctx.send("Could not look up that user")
                    return
            else:
                await ctx.send(
                    "I was unable to look up {!s}: {!s} / {!s}".format(
                        profile, j["meta"]["code"], j["meta"]["error_detail"]
                    ))
                return
        if not uid:
            await ctx.send("Sorry, I couldn't get a uid for " + profile)
            return
        # Step 2: Accept any pending requests
        url = ("https://api.untappd.com/v4/friend/accept/{!s}?{!s}"
               ).format(uid, qstr)
        j = await get_data_from_untappd(ctx.author, url)
        if "meta" in j:
            if int(j['meta']['code']) == 200:
                # This is probably the case where it worked!
                if "target_user" in j['response']:
                    response_str = (
                        "You accepted a friend request from {!s}!"
                        " Now you can toast them and stalk them better."
                    ).format(j['response']['target_user']['user_name'])
                    await ctx.send(response_str)
                else:
                    response_str = "I think you accepted a request "
                    response_str += "but I didn't get the answer I expected"
                    await ctx.send(response_str)
                return
        # Send a request. Even if they're already friends
        url = ("https://api.untappd.com/v4/friend/request/{!s}?{!s}"
               ).format(uid, qstr)

        j = await get_data_from_untappd(ctx.author, url)
        if "meta" in j:
            if int(j["meta"]["code"]) == 200:
                if "target_user" in j['response']:
                    response_str = (
                        "You sent a request to {!s}. The ball is in "
                        "their court now."
                    ).format(j['response']['target_user']['user_name'])
                else:
                    response_str = (
                        "I think you sent a request but I "
                        "didn't get the response I expected: {!s} / {!s}"
                    ).format(
                        j["meta"]["code"], j["meta"]["error_detail"]
                    )
                await ctx.send(response_str)
            else:
                if "meta" in j:
                    response_str = (
                        "I got an error sending a request to that person. "
                        "I blame you for that error. (Specifically: {!s})"
                    ).format(j["meta"]["error_detail"])
                else:
                    response_str = "Something went horribly wrong."
                await ctx.send(response_str)

    @commands.command()
    async def wishlist(self, ctx, *keywords):
        """Requires that you've authorized the bot.
        Adds a beer to or removes a beer from your wishlist.
        If you provide a beer id, that's used.
        Otherwise it's the first search result
        or the last beer shared in the channel"""

        beerid = 0
        default_beer = False
        credentials = await check_credentials(self.config)
        if not credentials:
            await ctx.send("The owner has not set the API information "
                           "and should use the `untappd_apikey` command")
            return

        keys = await get_auth(ctx.author.id, self.config)
        if "access_token" not in keys:
            await ctx.send("You must first authorize me to act as you"
                           " using `untappd authme`")
            return

        if keywords:
            keywords = " ".join(keywords)
        else:
            channel = ctx.channel.id
            if channel in self.channels:
                if self.channels[channel]:
                    if "beer" in self.channels[channel]:
                        beerid = self.channels[channel]["beer"]
                        default_beer = True
            if not beerid:
                await ctx.send_help()
                return

        # TODO migrate this to with ctx.channel.typing():
        await ctx.channel.trigger_typing()
        if not beerid and keywords.isdigit():
            beer = await get_beer_by_id(self.config, ctx, keywords)
            if isinstance(beer, str):
                await ctx.send("Wishlist add failed - {!s}".
                               format(beer))
                return
            beerid = keywords
        elif not beerid:
            beers = await search_beer(self.config, ctx, keywords, limit=1)
            if isinstance(beers["items"], list) and len(beers["items"]) > 0:
                beerid = beers["items"][0]["beer"]["bid"]
            else:
                await ctx.send("I'm afraid `{!s}` was not found".format(
                    keywords
                ))

        if beerid:
            # Attempt to add to the wishlist
            if "access_token" not in keys:
                return ("You have not authorized the bot to act as you, use"
                        "`untappd authme` to start the process")

            keys["bid"] = beerid
            qstr = urllib.parse.urlencode(keys)
            url = ("https://api.untappd.com/v4/user/wishlist/add?{!s}"
                   ).format(qstr)
            # print("Using URL: {!s}".format(url))

            j = await get_data_from_untappd(ctx.author, url)
            if "meta" in j:
                if int(j["meta"]["code"]) == 200:
                    if default_beer:
                        await ctx.send("{!s} from {!s} added to wishlist!".format(
                            j['response']['beer']['beer']['beer_name'],
                            j['response']['beer']['brewery']['brewery_name']
                        ))
                    else:
                        beer = j['response']['beer']['beer']
                        beer['brewery'] = j['response']['beer']['brewery']
                        embed = beer_to_embed(beer)
                        success = await add_react(ctx.message, '✅')
                        if not success:
                            await ctx.send("Added to your wishlist!", embed=embed)
                    return
                elif int(j["meta"]["code"]) == 500:
                    await ctx.send("I'm fairly certain that is already on your list, go find it already!")
                    return
                else:
                    await ctx.send("Weird, got code {!s}".
                                   format(j["meta"]["code"]))
        else:
            await ctx.send("I was unable to find such a beer, sorry")

    @commands.command()
    async def unwishlist(self, ctx, *keywords):
        """Requires that you've authorized the bot.
        Removes a beer from your wishlist.
        If you provide a beer id, that's used.
        Otherwise it's the first search result (findbeer1)
        or the last beer shared in the channel"""

        beerid = 0
        default_beer = False
        credentials = await check_credentials(self.config)
        if not credentials:
            await ctx.send("The owner has not set the API information "
                           "and should use the `untappd_apikey` command")
            return

        keys = await get_auth(ctx.author.id, self.config)
        if "access_token" not in keys:
            await ctx.send("You must first authorize me to act as you"
                           " using `untappd authme`")
            return

        if keywords:
            keywords = " ".join(keywords)
        else:
            channel = ctx.channel.id
            if channel in self.channels:
                if self.channels[channel]:
                    if "beer" in self.channels[channel]:
                        beerid = self.channels[channel]["beer"]
                        default_beer = True
            if not beerid:
                await ctx.send_help()
                return

        # TODO migrate this to with ctx.channel.typing():
        await ctx.channel.trigger_typing()
        if not beerid and keywords.isdigit():
            beer = await get_beer_by_id(self.config, ctx, keywords)
            if isinstance(beer, str):
                await ctx.send("Wishlist remove failed - {!s}".
                               format(beer))
                return
            beerid = keywords
        elif not beerid:
            beers = await search_beer(self.config, ctx, keywords, limit=1)
            if isinstance(beers["items"], list) and len(beers["items"]) > 0:
                beerid = beers["items"][0]["beer"]["bid"]
            else:
                await ctx.send("I'm afraid `{!s}` was not found".format(
                    keywords
                ))

        if beerid:
            # Attempt to add to the wishlist
            if "access_token" not in keys:
                await ctx.send("You have not authorized the bot to act as you, use"
                               "`untappd authme` to start the process")
                return

            keys["bid"] = beerid
            qstr = urllib.parse.urlencode(keys)
            url = ("https://api.untappd.com/v4/user/wishlist/delete?{!s}"
                   ).format(qstr)

            j = await get_data_from_untappd(ctx.author, url)
            if "meta" in j:
                if int(j["meta"]["code"]) == 200:
                    if default_beer:
                        await ctx.send("{!s} from {!s} removed from wishlist!".format(
                            j['response']['beer']['beer']['beer_name'],
                            j['response']['beer']['brewery']['brewery_name']
                        ))
                    else:
                        beer = j['response']['beer']['beer']
                        beer['brewery'] = j['response']['beer']['brewery']
                        embed = beer_to_embed(beer)
                        success = await add_react(ctx.message, '✅')
                        if not success:
                            await ctx.send("Beer removed from your wishlist!", embed=embed)
                    return
                elif int(j["meta"]["code"]) == 500:
                    await ctx.send("Are you sure that was on your wishlist? It's still there if it was")
                    return
                else:
                    await ctx.send("Weird, got code {!s}".
                                   format(j["meta"]["code"]))
        else:
            await ctx.send("I was unable to find such a beer, sorry")

    @commands.command()
    async def haveihad(self, ctx, *keywords):
        """Lookup a beer to see if you've had it
        Requires that you've authenticated the bot to act as you"""

        response = ""  # type: str
        embed = None
        credentials = await check_credentials(self.config)
        if not credentials:
            await ctx.send("The owner has not set the API information "
                           "and should use the `untappd_apikey` command")
            return

        keys = await get_auth(ctx.author.id, self.config)
        if "access_token" not in keys:
            await ctx.send("You must first authorize me to act as you"
                           " using `untappd authme`")
            return

        if keywords:
            keywords = " ".join(keywords)
        else:
            await ctx.send_help()
            return

        set_beer_id = False
        async with ctx.channel.typing():
            if keywords.isdigit():
                beerid = keywords
            else:
                beers = await search_beer(self.config, ctx, keywords, limit=1)
                if isinstance(beers, str):
                    await ctx.send(
                        "Lookup of `{!s}` didn't result in a beer list: {!s}".
                            format(keywords, beers)
                    )
                    return
                elif isinstance(beers["items"], list) and len(beers["items"]) > 0:
                    beerid = beers["items"][0]["beer"]["bid"]
                    set_beer_id = True
                else:
                    await ctx.send(("Lookup of `{!s}` failed. So no, "
                                    "you haven't"
                                    ).format(keywords))
                    return

            if beerid:
                beer = await get_beer_by_id(self.config, ctx, beerid)
                if isinstance(beer, str):
                    await ctx.send(beer)
                    return
                description = ""
                if beer["stats"]["user_count"]:
                    description = "You have had '**{!s}**' by **{!s}** {!s} time{!s}".format(
                        beer["beer_name"],
                        beer["brewery"]["brewery_name"],
                        beer["stats"]["user_count"],
                        add_s(beer["stats"]["user_count"])
                    )
                    if beer["auth_rating"]:
                        description += " and you gave it {!s} cap{!s}.".format(
                            beer["auth_rating"],
                            add_s(beer["auth_rating"])
                        )
                    if set_beer_id:
                        description += " `{!s}findbeer {!s}` or click above to see more details.".format(
                            ctx.prefix,
                            beerid
                        )
                else:
                    description = "You have never had '**{!s}**' by **{!s}**".format(
                        beer["beer_name"],
                        beer["brewery"]["brewery_name"]
                    )
                    if beer["stats"]["total_user_count"]:
                        description += " but {!s} other people have.".format(
                            human_number(beer["stats"]["total_user_count"])
                        )
                    if set_beer_id:
                        description += " `{!s}findbeer {!s}` or click above to see more details.".format(
                            ctx.prefix,
                            beerid
                        )
                if description:
                    embed = discord.Embed(title="{!s}".format(beer["beer_name"]),
                        description=description,
                        url="https://www.untappd.com/beer/{!s}".format(beerid))
                    embed.set_thumbnail(url=beer['beer_label'])
            else:
                await ctx.send_help()
                return

            if embed:
                await ctx.send("", embed=embed)
            elif response:
                await ctx.send(response)
            else:
                await ctx.send("You may not have provided a beer ID")

    @commands.command()
    async def findbeer(self, ctx, *keywords):
        """Search Untappd.com for a beer. Provide a number and it'll
        look up that beer"""
        beer_list = []
        response = ""
        list_limit = await list_size(self.config, ctx.guild)

        credentials = await check_credentials(self.config)
        if not credentials:
            await ctx.send("The owner has not set the API information "
                           "and should use the `untappd_apikey` command")
            return

        if keywords:
            keywords = "+".join(keywords)
        else:
            await ctx.send_help()
            return

        # TODO migrate this to with ctx.channel.typing():
        await ctx.channel.trigger_typing()
        if keywords.isdigit():
            embed = await lookup_beer(self.config, ctx, self.channels, keywords)
            # await ctx.send( embed=embed)
        else:
            results = await search_beer_to_embed(self.config, ctx, self.channels, keywords,
                                                 limit=list_limit)
            if isinstance(results, dict):
                embed = results["embed"]
                if "beer_list" in results:
                    beer_list = results["beer_list"]
            else:
                embed = results
            # await ctx.send(result_text, embed=embed)

        if isinstance(embed, str):
            message = await ctx.send(embed)
        elif embed:
            message = await ctx.send(response, embed=embed)
        else:
            message = await ctx.send(response)

        if len(beer_list) > 1:
            await embed_menu(self.bot, self.config, ctx, self.channels, beer_list,
                             message, 60)
            # Raised to 60 second wait

    @commands.command()
    async def homebrew(self, ctx, *keywords):
        """Search Untappd.com for a beer. Provide a number and it'll
        look up that beer"""
        beer_list = []
        response = ""
        list_limit = await list_size(self.config, ctx.guild)

        credentials = await check_credentials(self.config)
        if not credentials:
            await ctx.send("The owner has not set the API information "
                           "and should use the `untappd_apikey` command")
            return

        if keywords:
            keywords = "+".join(keywords)
        else:
            await ctx.send_help()
            return

        # TODO migrate this to with ctx.channel.typing():
        await ctx.channel.trigger_typing()
        if keywords.isdigit():
            embed = await lookup_beer(self.config, ctx, self.channels, keywords)
            # await ctx.send( embed=embed)
        else:
            results = await search_beer_to_embed(self.config, ctx, self.channels, keywords,
                                                 limit=list_limit, homebrew=True)
            if isinstance(results, dict):
                embed = results["embed"]
                if "beer_list" in results:
                    beer_list = results["beer_list"]
            else:
                embed = results
            # await ctx.send(result_text, embed=embed)

        if isinstance(embed, str):
            message = await ctx.send(embed)
        elif embed:
            message = await ctx.send(response, embed=embed)
        else:
            message = await ctx.send(response)

        if len(beer_list) > 1:
            await embed_menu(self.bot, self.config, ctx, self.channels, beer_list,
                             message, 60)
            # Raised to 60 second wait

    @commands.command()
    async def findbeer1(self, ctx, *keywords):
        result_text = ""
        # TODO migrate this to with ctx.channel.typing():
        await ctx.channel.trigger_typing()
        results = await search_beer_to_embed(self.config, ctx, self.channels,
                                             " ".join(keywords), limit=1)
        if isinstance(results, dict):
            embed = results["embed"]
            await ctx.send(result_text, embed=embed)
        else:
            await ctx.send(result_text, embed=results)

    @commands.command()
    async def lastbeer(self, ctx, profile: str = None):
        """Displays details for the last beer a person had"""

        result_text = ""
        author = ctx.author
        if ctx.guild:
            guild = str(ctx.guild.id)
        else:
            guild = 0

        credentials = await check_credentials(self.config)
        if not credentials:
            await ctx.send("The owner has not set the API information "
                           "and should use the `untappd_apikey` command")
            return

        #        await ctx.send("I got a user " + profile)
        if ctx.message.mentions:
            # If user has set a nickname, use that - but only if it's not a PM
            if ctx.guild:
                user = ctx.message.mentions[0]
                # print("looking up {!s}".format(user.id))
                try:
                    profile = await self.config.get_raw(guild, user.id, "nick")
                except KeyError:
                    profile = user.display_name

        if not profile:
            try:
                profile = await self.config.get_raw(guild, author.id, "nick")
            except KeyError:
                profile = author.display_name

        # TODO migrate this to with ctx.channel.typing():
        await ctx.channel.trigger_typing()
        results = await get_checkins(self.config, ctx, self.channels, profile=profile, count=1)
        if (isinstance(results, dict)) and ("embed" in results):
            embed = results["embed"]
            await ctx.send(result_text, embed=embed)
        else:
            await ctx.send(results)
        return

    @commands.command()
    async def utprofile(self, ctx, profile: str = None):
        """Search for a user's information by providing their profile name,
        discord mentions OK"""

        embed = False
        beer_list = []
        result_text = ""
        author = ctx.author
        guild = str(ctx.guild.id) if ctx.guild else 0

        credentials = await check_credentials(self.config)
        if not credentials:
            await ctx.send("The owner has not set the API information "
                           "and should use the `untappd_apikey` command")
            return

        if ctx.message.mentions:
            # If user has set a nickname, use that - but only if it's not a PM
            if ctx.guild:
                user = ctx.message.mentions[0]
                try:
                    profile = await self.config.get_raw(guild, user.id, "nick")
                except KeyError:
                    profile = user.display_name

        if not profile:
            try:
                profile = await self.config.get_raw(guild, author.id, "nick")
            except KeyError:
                profile = None
        if not profile:
            profile = author.display_name
            print("Using '{}'".format(profile))
        # TODO migrate this to with ctx.channel.typing():
        await ctx.channel.trigger_typing()
        results = await profile_lookup(self.config, ctx, profile,
                                       limit=await list_size(self.config, ctx.guild))
        if isinstance(results, dict):
            if "embed" in results:
                embed = results["embed"]
            if "beer_list" in results:
                beer_list = results["beer_list"]
        else:
            result_text = results
        if embed:
            message = await ctx.send(result_text, embed=embed)
        else:
            message = await ctx.send(result_text)
        if len(beer_list) > 1:
            await embed_menu(self.bot, self.config, ctx, self.channels,
                             beer_list, message, 30, type_="checkin")
        return

    @untappd.command()
    @checks.is_owner()
    async def untappd_apikey(self, ctx, *keywords):
        """Sets the id and secret that you got from applying for
            an untappd api"""
        if len(keywords) == 2:
            await self.config.client_id.set(keywords[0])
            await self.config.client_secret.set(keywords[1])
            await self.config.CONFIG.set(True)
            await ctx.send("API set")
        else:
            await ctx.send("I am expecting two words, the id and "
                           "the secret only")

    @commands.Cog.listener()
    async def on_reaction_add(self, react: discord.Reaction, person: discord.User):
        """
        When someone reacts to a thing, process it.

        :param react: The reaction object
        :param person: The user object for the person reacting
        """
        emoji = react.emoji
        # Process the emoji
        # eid = emoji.id if react.custom_emoji else str(emoji)
        toast_emoji = await self.config.toast_emoji()
        if emoji == toast_emoji:
            # Find the checkin ID to use
            if len(react.message.embeds) > 0:
                footer = react.message.embeds[0].footer.text
                match = re.search('Checkin ([0-9]+) /', footer)
                if match:
                    success = await do_toast(self.config, person, checkin=match.group(1))
                    if success and self.is_chatty:
                        try:
                            await person.send("Toasted {!s}".format(match.group(1)))
                        except (discord.Forbidden, discord.HTTPException):
                            return

    @commands.command()
    async def toast(self, ctx, *keywords):
        """Toasts a checkin by number, if you're friends"""

        checkin = 0

        for word in keywords:
            if word.isdigit():
                checkin = int(word)

        if not checkin:
            channel = ctx.channel.id
            if channel in self.channels:
                if self.channels[channel]:
                    if "checkin" in self.channels[channel]:
                        checkin = self.channels[channel]["checkin"]

        if not checkin:
            await ctx.send("I haven't seen a checkin for this channel "
                           "since my last start. You'll have to tell me "
                           "which to toast.")
            return

        success = await do_toast(self.config, ctx.author, checkin=checkin)
        if success:
            success = await add_react(ctx.message, '✅')
            if not success:
                await ctx.send("Toasted!")
        else:
            await ctx.send("Toast failed for some reason you were PM'd about")

    @commands.command()
    async def checkin(self, ctx, *keywords):
        """Returns a single checkin by number"""

        author = ctx.author
        checkin = 0

        credentials = await check_credentials(self.config)
        if not credentials:
            await ctx.send("The owner has not set the API information "
                           "and should use the `untappd_apikey` command")
            return

        try:
            auth_token = await self.config.get_raw(author.id, "token")
        except KeyError:
            auth_token = None

        for word in keywords:
            if word.isdigit():
                checkin = int(word)

        if not checkin:
            await ctx.send("A checkin ID number is required")
            return

        # TODO migrate this to with ctx.channel.typing():
        await ctx.channel.trigger_typing()
        embed = await get_checkin(self.config, ctx, self.channels,
                                  checkin=checkin, auth_token=auth_token)
        if isinstance(embed, str):
            await ctx.send(embed)
        else:
            await ctx.send("", embed=embed)

    @commands.command()
    async def checkins(self, ctx, *keywords):
        """Returns a list of checkins"""

        embed = None
        profile = ""
        startnum = 0
        author = ctx.author
        if ctx.guild:
            guild = str(ctx.guild.id)
        else:
            guild = 0
        checkin_list = []
        result_text = ""
        countnum = await list_size(self.config, server=ctx.guild)
        # determine if a profile or number was given
        credentials = await check_credentials(self.config)
        if not credentials:
            await ctx.send("The owner has not set the API information "
                           "and should use the `untappd_apikey` command")
            return

        # If a keyword was provided and it's all digits then look up that one
        # Looks like there is no way to look up by id alone

        if ctx.message.mentions:
            # If user has set a nickname, use that - but only if it's not a PM
            if ctx.guild:
                user = ctx.message.mentions[0]
                try:
                    profile = await self.config.get_raw(guild, user.id, "nick")
                except KeyError:
                    profile = user.display_name

        # The way the API works you can provide a checkin number and limit
        for word in keywords:
            # print("Checking " + word)
            if word.isdigit():
                startnum = int(word)
                countnum = 1
            elif not profile:
                profile = word
        if not profile:
            try:
                profile = await self.config.get_raw(guild, author.id, "nick")
            except KeyError:
                profile = None
        if not profile:
            profile = author.display_name

        if countnum > 50:
            countnum = 50
        if countnum < 1:
            countnum = 1
        # print(dir(ctx.message.content))
        # print(dir(ctx.command))
        # print("{!s}".format(ctx.command.invoke))
        # if ctx.command.name == "lastbeer":
        #     countnum = 1

        # TODO migrate this to with ctx.channel.typing():
        await ctx.channel.trigger_typing()
        results = await get_checkins(self.config, ctx, self.channels, profile=profile,
                                     start=startnum, count=countnum)
        if isinstance(results, dict):
            if "embed" in results:
                embed = results["embed"]
            if "list" in results:
                checkin_list = results["list"]
        else:
            result_text = results
        if embed:
            message = await ctx.send(result_text, embed=embed)
        else:
            message = await ctx.send(result_text)
        if len(checkin_list) > 1:
            await embed_menu(self.bot, self.config, ctx, self.channels, checkin_list, message, 30,
                             type_="checkin")
        return

    @commands.command()
    async def ifound(self, ctx, *keywords):
        """Add a found beer to the spreadsheet. Beer id or search"""

        author = ctx.author
        url = ""
        if ctx.guild:
            guild = str(ctx.guild.id)
            try:
                url = await self.config.get_raw(guild, "project_url")
            except KeyError:
                pass
            try:
                profile = await self.config.get_raw(guild, author.id, "nick")
            except KeyError:
                profile = author.display_name
        else:
            profile = author.display_name

        if keywords:
            keywords = " ".join(keywords)
        else:
            await ctx.send_help()
            return

        # TODO migrate this to with ctx.channel.typing():
        await ctx.channel.trigger_typing()
        if keywords.isdigit():
            beerid = keywords
        else:
            beers = await search_beer(self.config, ctx, keywords, limit=1)
            if isinstance(beers, str):
                await ctx.send(
                    "Lookup of `{!s}` didn't result in a beer list: {!s}".format(keywords, beers)
                )
                return
            elif isinstance(beers["items"], list) and len(beers["items"]) > 0:
                beerid = beers["items"][0]["beer"]["bid"]
            else:
                await ctx.send("Lookup of `{!s}` failed. So no, you haven't".format(keywords))
                return

        if beerid:
            beer = await get_beer_by_id(self.config, ctx, beerid)
            if isinstance(beer, str):
                await ctx.send(beer)
                return

        if not url:
            await ctx.send("Looks like there are no projects right now")
            return
        beer = await get_beer_by_id(self.config, ctx, beerid)
        if isinstance(beer, str):
            # This happens in error situations
            await ctx.send(beer)
            return
        # added for March 2019 -- collabs!
        collabs = 0
        if "collaborations_with" in beer:
            collabs = beer["collaborations_with"]["count"]

        payload = {
            "action": "found",
            "bid": beerid,
            "username": profile,
            "beer_string": "{!s} from {!s}".format(beer["beer_name"], beer["brewery"]["brewery_name"]),
            "beer_name": beer["beer_name"],
            "brewery_id": beer["brewery"]["brewery_id"],
            "brewery_name": beer["brewery"]["brewery_name"],
            "collabs": collabs
        }
        async with aiohttp.ClientSession() as sess:
            async with sess.post(url, data=payload) as resp:
                if resp.status == 200:
                    try:
                        j = await resp.json()
                    except ValueError:
                        await ctx.send("Error somewhere in Google")
                        # text = await resp.read()
                        # print(text)
                        return
                else:
                    return "Query failed with code " + str(resp.status)

                if j['result'] == "success":
                    response_str = ""
                    if "message" in j:
                        response_str += j["message"] + " "
                    if "hasStats" in j:
                        response_str += "{} has {} points across {} checkins and {} found beers. ".format(
                            profile, j["points"], j["checkins"], j["found"]
                        )
                    if "beerStats" in j:
                        response_str += " {} has been found by {} people. {} has {} beers found so far. ".format(
                            beer["beer_name"], j["beerPeople"], beer["brewery"]["brewery_name"], j["breweryPeople"])
                    embed = await lookup_beer(self.config, ctx, self.channels, beerid)
                    if embed:
                        await ctx.send(response_str, embed=embed)
                    else:
                        await ctx.send(response_str)
                else:
                    if "message" in j:
                        await ctx.send("Negatory: {}".format(j['message']))
                    else:
                        await ctx.send("Something went wrong finding the beer")

    @commands.command()
    @commands.guild_only()
    async def ddpstats(self, ctx, *keywords):
        """
        Get the Drinking Project stats for yourself or another

        :param ctx: Discord context
        :param keywords: allow to specify other users
        """
        profile = ""
        if ctx.guild:
            guild = str(ctx.guild.id)
            try:
                url = await self.config.get_raw(guild, "project_url")
            except KeyError:
                await ctx.send("Project is currently not open")
                return
        else:
            await ctx.send("This command is not available in a PM")
            return
        if not keywords:
            try:
                profile = await self.config.get_raw(guild, ctx.author.id, "nick")
            except KeyError:
                profile = ctx.author.display_name
        else:
            if ctx.message.mentions:
                # If user has set a nickname, use that - but only if it's not a PM
                if ctx.guild:
                    user = ctx.message.mentions[0]
                    try:
                        profile = await self.config.get_raw(guild, user.id, "nick")
                    except KeyError:
                        profile = user.display_name
            else:
                profile = '+'.join(keywords)
        payload = {
            "action": "status",
            "username": profile
        }
        async with ctx.message.channel.typing():
            async with aiohttp.ClientSession() as sess:
                async with sess.post(url, data=payload) as resp:
                    if resp.status == 200:
                        try:
                            j = await resp.json()
                        except ValueError:
                            await ctx.send("Error somewhere in Google")
                            # print(resp)
                            # text = await resp.read()
                            # print(text)
                            return
                    else:
                        return "Query failed with code " + str(resp.status)

                    if j['result'] == "success":
                        response_str = ""
                        if "message" in j:
                            response_str += j["message"] + " "
                        if "hasStats" in j:
                            response_str += "{} has {} points across {} checkins and {} found beers.".format(
                                profile, j["points"], j["checkins"], j["found"]
                            )
                        await ctx.send(response_str)
                    else:
                        if "message" in j:
                            await ctx.send("Not Today! {}".format(j['message']))
                        else:
                            await ctx.send("Something went wrong checking status")


    @commands.command()
    @commands.guild_only()
    async def whodrank(self, ctx, beerid: int):
        """
        See who else drank this beer

        :param ctx: Discord context
        :param keywords: allow to specify other users
        """
        if ctx.guild:
            guild = str(ctx.guild.id)
            try:
                url = await self.config.get_raw(guild, "project_url")
            except KeyError:
                await ctx.send("Project is currently not open")
                return
        else:
            await ctx.send("This command is not available in a PM")
            return
        if not beerid:
            await ctx.send("Who drank what?")
            return

        payload = {
            "action": "whodrank",
            "beerid": beerid
        }
        async with ctx.message.channel.typing():
            async with aiohttp.ClientSession() as sess:
                async with sess.post(url, data=payload) as resp:
                    if resp.status == 200:
                        try:
                            j = await resp.json()
                        except ValueError:
                            await ctx.send("Error somewhere in Google")
                            # print(resp)
                            # text = await resp.read()
                            # print(text)
                            return
                    else:
                        return "Query failed with code " + str(resp.status)

                    if "message" in j:
                        response_str = "Nobody has added that beer"
                        if j["message"]:
                            response_str = "These people added that beer: " + j["message"]
                        await ctx.send(response_str)
                    else:
                        if "message" in j:
                            await ctx.send("Not Today! {}".format(j['message']))
                        else:
                            await ctx.send("Something went wrong checking status")

    @commands.command()
    @commands.guild_only()
    async def ddp(self, ctx, checkin_id: int = 0):
        """Add a checkin to the spreadsheet. Defaults to last one"""

        author = ctx.author
        url = ""
        if ctx.guild:
            guild = str(ctx.guild.id)
            try:
                url = await self.config.get_raw(guild, "project_url")
            except KeyError:
                pass
            try:
                profile = await self.config.get_raw(guild, author.id, "nick")
            except KeyError:
                profile = author.display_name
        else:
            profile = author.display_name

        try:
            auth_token = await self.config.get_raw(author.id, "token")
        except KeyError:
            auth_token = None

        # TODO migrate this to with ctx.channel.typing():
        await ctx.channel.trigger_typing()
        if not url:
            await ctx.send("Looks like there are no projects right now")
            return

        # Get the information needed for the form, starting with checkin id
        # checkin id	style	beer id	beer name	avg rating
        # brewery id	brewery	username	rating	comment
        if not checkin_id or checkin_id <= 0:
            checkin_url = ("https://api.untappd.com/v4/user/checkins/{!s}".format(profile))
            keys = dict()
            keys["client_id"] = await self.config.client_id()
            if auth_token:
                keys["access_token"] = auth_token
                # print("Doing an authorized lookup")
            else:
                keys["client_secret"] = await self.config.client_secret()
            keys["limit"] = 1
            qstr = urllib.parse.urlencode(keys)
            checkin_url += "?{!s}".format(qstr)
            j = await get_data_from_untappd(ctx.author, checkin_url)
            if j["meta"]["code"] != 200:
                # print("Lookup failed for url: "+url)
                await ctx.send("Lookup failed with {!s} - {!s}".format(
                    j["meta"]["code"],
                    j["meta"]["error_detail"]
                ))
                return

            if isinstance(j["response"]["checkins"]["items"], list):
                checkin = j["response"]["checkins"]["items"][0]
            else:
                await ctx.send("Things seem to work but I did not get"
                               "a list of checkins")
                return
        else:
            # The case where a checkin id was provided
            keys = dict()
            keys["client_id"] = await self.config.client_id()
            if auth_token:
                keys["access_token"] = auth_token
                # print("Doing an authorized lookup")
            else:
                keys["client_secret"] = await self.config.client_secret()
            qstr = urllib.parse.urlencode(keys)
            checkin_url = "https://api.untappd.com/v4/checkin/view/{!s}?{!s}".format(checkin_id, qstr)

            j = await get_data_from_untappd(ctx.author, checkin_url)
            if j["meta"]["code"] != 200:
                # print("Lookup failed for url: "+url)
                await ctx.send("Lookup failed with {!s} - {!s}".format(
                    j["meta"]["code"],
                    j["meta"]["error_detail"]))
                return

            checkin = j["response"]["checkin"]

        checkin_id = checkin["checkin_id"]
        style = checkin["beer"]["beer_style"]
        beer_id = checkin["beer"]["bid"]
        beer_name = checkin["beer"]["beer_name"]
        brewery_id = checkin["brewery"]["brewery_id"]
        brewery = checkin["brewery"]["brewery_name"]
        username = checkin["user"]["user_name"]
        rating = checkin["rating_score"]
        comment = checkin["checkin_comment"]
        checkin_date = checkin["created_at"]

        beer = await get_beer_by_id(self.config, ctx, beer_id)
        avg_rating = beer["rating_score"]
        total_checkins = beer["stats"]["total_user_count"]
        abv = beer["beer_abv"]
        beer_date = beer["created_at"]

        # added for March 2019 -- collabs!
        collabs = 0
        if "collaborations_with" in beer:
            collabs = beer["collaborations_with"]["count"]

        payload = {
            "action": "drank",
            "checkin": checkin_id,
            "style": style,
            "bid": beer_id,
            "beer_name": beer_name,
            "brewery_id": brewery_id,
            "brewery": brewery,
            "username": username,
            "rating": rating,
            "avg_rating": avg_rating,
            "total_checkins": total_checkins,
            "checkin_date": checkin_date,
            "collabs": collabs,
            "abv": abv,
            "comment": comment,
            "beer_date": beer_date
        }
        async with aiohttp.ClientSession() as sess:
            async with sess.post(url, data=payload) as resp:
                if resp.status == 200:
                    try:
                        j = await resp.json()
                    except ValueError:
                        await ctx.send("Error somewhere in Google")
                        # print(resp)
                        # text = await resp.read()
                        # print(text)
                        return
                else:
                    return "Query failed with code " + str(resp.status)

                if j['result'] == "success":
                    response_str = ""
                    if "message" in j:
                        response_str += j["message"] + " "
                    if "hasStats" in j:
                        response_str += "{} has {} points across {} checkins and {} found beers.".format(
                            username, j["points"], j["checkins"], j["found"]
                        )
                        if "styleString" in j:
                            response_str += "\n{}".format(j["styleString"])
                            print(j["styleString"])
                    # embed = await get_checkin(self.config, ctx, self.channels,
                    #                          checkin=checkin_id, auth_token=auth_token)
                    embed = await checkin_to_embed(self.config, ctx, self.channels, checkin)
                    if embed:
                        await ctx.send(response_str,
                                       embed=embed)
                    else:
                        await ctx.send(response_str)
                else:
                    if "message" in j:
                        await ctx.send("Negatory: {}".format(j['message']))
                    else:
                        await ctx.send("Something went wrong adding the checkin")

    @commands.command()
    @commands.guild_only()
    async def undrank(self, ctx, checkin_id: int = 0):
        """Removes a checkin from the spreadsheet. Use ddp to add it back"""

        author = ctx.author
        url = ""
        if ctx.guild:
            guild = str(ctx.guild.id)
            try:
                url = await self.config.get_raw(guild, "project_url")
            except KeyError:
                pass
            try:
                profile = await self.config.get_raw(guild, author.id, "nick")
            except KeyError:
                profile = author.display_name
        else:
            await ctx.send("This does not work in PM")

        try:
            auth_token = await self.config.get_raw(author.id, "token")
        except KeyError:
            auth_token = None

        # TODO migrate this to with ctx.channel.typing():
        await ctx.channel.trigger_typing()
        if not url:
            await ctx.send("Looks like there are no projects right now")
            return

        if not checkin_id or checkin_id <= 0:
            checkin_url = ("https://api.untappd.com/v4/user/checkins/{!s}".format(profile))
            keys = dict()
            keys["client_id"] = await self.config.client_id()
            if auth_token:
                keys["access_token"] = auth_token
                # print("Doing an authorized lookup")
            else:
                keys["client_secret"] = await self.config.client_secret()
            keys["limit"] = 1
            qstr = urllib.parse.urlencode(keys)
            checkin_url += "?{!s}".format(qstr)
            j = await get_data_from_untappd(ctx.author, checkin_url)
            if j["meta"]["code"] != 200:
                # print("Lookup failed for url: "+url)
                await ctx.send("Lookup failed with {!s} - {!s}".format(
                    j["meta"]["code"],
                    j["meta"]["error_detail"]
                ))
                return

            if isinstance(j["response"]["checkins"]["items"], list):
                checkin_id = j["response"]["checkins"]["items"][0]["checkin_id"]
            else:
                await ctx.send("Things seem to work but I did not get"
                               "a list of checkins")
                return
        else:
            # The case where a checkin id was provided
            keys = dict()
            keys["client_id"] = await self.config.client_id()
            if auth_token:
                keys["access_token"] = auth_token
                # print("Doing an authorized lookup")
            else:
                keys["client_secret"] = await self.config.client_secret()
            qstr = urllib.parse.urlencode(keys)
            checkin_url = "https://api.untappd.com/v4/checkin/view/{!s}?{!s}".format(checkin_id, qstr)

            j = await get_data_from_untappd(ctx.author, checkin_url)
            if j["meta"]["code"] != 200:
                # print("Lookup failed for url: "+url)
                await ctx.send("Lookup failed with {!s} - {!s}").format(
                    j["meta"]["code"],
                    j["meta"]["error_detail"])
                return

            checkin_id = j["response"]["checkin"]["checkin_id"]

        payload = {
            "action": "undrank",
            "checkin": checkin_id,
        }
        async with aiohttp.ClientSession() as sess:
            async with sess.post(url, data=payload) as resp:
                if resp.status == 200:
                    try:
                        j = await resp.json()
                    except ValueError:
                        await ctx.send("Error somewhere in Google")
                        text = await resp.read()
                        print(text)
                        return
                else:
                    return "Query failed with code " + str(resp.status)

                if j['result'] == "success":
                    response_str = ""
                    if "message" in j:
                        response_str += j["message"] + " "
                    if "hasStats" in j:
                        response_str += "{} has {} points across {} checkins and {} found beers.".format(
                            j["username"], j["points"], j["checkins"], j["found"]
                        )
                    await ctx.send(response_str)
                else:
                    if "message" in j:
                        await ctx.send(j["message"])
                    else:
                        await ctx.send("Something went wrong adding the checkin")


    @commands.command()
    @commands.guild_only()
    async def unfound(self, ctx, beer_id: int):
        """Removes a beer you found"""

        author = ctx.author
        url = ""
        if ctx.guild:
            guild = str(ctx.guild.id)
            try:
                url = await self.config.get_raw(guild, "project_url")
            except KeyError:
                pass
            try:
                profile = await self.config.get_raw(guild, author.id, "nick")
            except KeyError:
                profile = author.display_name
        else:
            profile = author.display_name

        if not url:
            await ctx.send("Looks like there are no projects right now")
            return

        payload = {
            "action": "unfind",
            "beerid": beer_id,
            "username": profile
        }
        async with ctx.channel.typing():
            async with aiohttp.ClientSession() as sess:
                async with sess.post(url, data=payload) as resp:
                    if resp.status == 200:
                        try:
                            j = await resp.json()
                        except ValueError:
                            await ctx.send("Error somewhere in Google")
                            text = await resp.read()
                            print(text)
                            return
                    else:
                        return "Query failed with code " + str(resp.status)

                    if j['result'] == "success":
                        response_str = ""
                        if "message" in j:
                            response_str += j["message"] + " "
                        if "hasStats" in j:
                            response_str += "{} has {} points across {} checkins and {} found beers.".format(
                                j["username"], j["points"], j["checkins"], j["found"]
                            )
                        await ctx.send(response_str)
                    else:
                        if "message" in j:
                            await ctx.send(j["message"])
                        else:
                            await ctx.send("Something went un-finding the beer")


async def do_toast(config, author, checkin: int):
    """Toast a specific checkin"""

    keys = await get_auth(author.id, config)
    # keys["client_id"] = await self.config.client_id()
    # keys["access_token"] = auth_token
    if "access_token" not in keys:
        return ("You have not authorized the bot to act as you, use"
                "`untappd authme` to start the process")

    qstr = urllib.parse.urlencode(keys)
    url = "https://api.untappd.com/v4/checkin/toast/{!s}?{!s}".format(checkin, qstr)
    # print("Using URL: {!s}".format(url))

    resp = await get_data_from_untappd(author, url)
    if resp['meta']['code'] == 500:
        await author.send("Toast failed, probably because you aren't friends with this person. Fix this by using "
                          "`untappd friend <person>`")
    elif resp["meta"]["code"] == 200:
        if "result" in resp["response"]:
            if resp["response"]["result"] == "success":
                if resp["response"]["like_type"] == "toast":
                    return True
                elif resp["response"]["like_type"] == "un-toast":
                    return await do_toast(config, author, checkin)
        else:
            await author.send("Toast failed for some reason")
    else:
        # print("Lookup failed for url: "+url)
        await author.send("Toast failed with {!s} - {!s}".format(resp["meta"]["code"], resp["meta"]["error_detail"]))


async def check_credentials(config):
    """Confirms bot owner set credentials"""
    client_id = await config.client_id()
    secret = await config.client_secret()
    return client_id and secret


def setup(bot):
    bot.add_cog(Untappd(bot))


async def get_auth(author_id, config):
    """Returns auth dictionary given a context"""
    client_id = await config.client_id()
    keys = {"client_id": client_id}
    try:
        keys["access_token"] = await config.get_raw(author_id, "token")
    except KeyError:
        keys["client_secret"] = await config.client_secret()
    return keys


async def get_beer_by_id(config, ctx, beerid):
    """Use the untappd API to return a beer dict for a beer id"""

    keys = await get_auth(ctx.author.id, config)
    qstr = urllib.parse.urlencode(keys)
    url = "https://api.untappd.com/v4/beer/info/{!s}?{!s}".format(
        beerid, qstr
    )
    resp = await get_data_from_untappd(ctx.author, url)
    if resp['meta']['code'] == 200:
        return resp['response']['beer']
    else:
        return "Query failed with code {!s}: {!s}".format(
            resp['meta']['code'],
            resp['meta']['error_detail']
        )


async def lookup_beer(config, ctx, channels, beerid: int):
    """Look up a beer by id, returns an embed"""

    beer = await get_beer_by_id(config, ctx, beerid)
    if not beer:
        return embedme("Problem looking up a beer by id")
    elif isinstance(beer, str):
        return embedme(beer)
    embed = beer_to_embed(beer)
    channel = ctx.channel.id
    if channel not in channels:
        channels[channel] = {}
    channels[channel]["beer"] = beer["bid"]
    return embed


def beer_to_embed(beer, rating=None):
    """Takes a beer json response object and returns an embed"""
    if 'bid' not in beer:
        return embedme("No bid, didn't look like a beer")
    beerid = beer['bid']
    beer_url = "https://untappd.com/b/{}/{!s}".format(
        beer['beer_slug'],
        beer['bid'])
    brewery_url = "https://untappd.com/brewery/{!s}".format(
        beer['brewery']['brewery_id'])
    beer_title = beer['beer_name']
    if 'created_at' in beer:
        beer_ts = datetime.strptime(beer["created_at"],
                                    "%a, %d %b %Y %H:%M:%S %z")
    else:
        beer_ts = datetime.now(timezone.utc)
    embed = discord.Embed(title="by {!s}".format(
        beer['brewery']['brewery_name']),
        description=beer['beer_description'][:2048],
        url=brewery_url,
        timestamp=beer_ts)
    embed.set_author(name=beer_title,
                     url=beer_url,
                     icon_url=beer['brewery']['brewery_label'])
    embed.add_field(name="Brewery Home",
                    value=brewery_location(beer['brewery']))
    embed.add_field(name="Style", value=beer['beer_style'],
                    inline=True)
    try:
        rating_str = "{!s} Caps ({})".format(
            round(beer['rating_score'], 2),
            human_number(beer['rating_count']))
    except (TypeError, ValueError, KeyError):
        rating_str = "Unknown"
    rating_title = "Rating"
    if beer["auth_rating"]:
        rating_title += " ({!s})".format(beer["auth_rating"])
    embed.add_field(name=rating_title, value=rating_str, inline=True)
    embed.add_field(name="ABV", value=beer['beer_abv'], inline=True)
    embed.add_field(name="IBU", value=beer['beer_ibu'], inline=True)
    if rating:
        embed.add_field(name="Checkin Rating",
                        value=str(rating),
                        inline=True)
    embed.set_thumbnail(url=beer['beer_label'])
    if 'stats' in beer:
        stats_str = "{!s} checkins from {!s} users".format(
            human_number(beer["stats"]["total_count"]),
            human_number(beer["stats"]["total_user_count"])
        )
        if beer["stats"]["monthly_count"]:
            stats_str += " ({!s} this month)".format(
                human_number(beer["stats"]["monthly_count"])
            )
        stats_title = "Stats"
        if beer["stats"]["user_count"]:
            stats_title += " (You: {!s})".format(
                human_number(beer["stats"]["user_count"])
            )
        embed.add_field(name=stats_title, value=stats_str, inline=True)
    last_seen = "Never"
    if 'checkins' in beer:
        if beer["checkins"]["count"]:
            last_seen = time_ago(beer["checkins"]["items"][0]["created_at"],
                                 long=True)
        embed.add_field(name="Last Seen", value=last_seen, inline=True)

    footer_str = "Beer {!s} ".format(beerid)
    prod_str = ""
    if not beer["is_in_production"]:
        prod_str = "Not in production"
    footer_str = footer_str + prod_str
    embed.set_footer(text=footer_str)

    if "collaborations_with" in beer:
        collab_str = ""
        collabs = beer['collaborations_with']['items']
        for num, collab in zip(range(10), collabs): # pylint: disable=unused-variable
            collab_str += " [" + collab['brewery']['brewery_name']
            collab_str += "](https://untappd.com/brewery/"
            collab_str += str(collab['brewery']['brewery_id']) + ")\n"
        if len(collabs) > 10:
            collab_str += "... and more"
        embed.add_field(name="Collaboration with", value=collab_str[:2048])
    return embed


async def get_checkin(config, ctx, channels, checkin: int, auth_token: str = None):
    """Look up a specific checkin"""

    keys = dict()
    keys["client_id"] = await config.client_id()
    if auth_token:
        keys["access_token"] = auth_token
        # print("Doing an authorized lookup")
    else:
        keys["client_secret"] = await config.client_secret()
    qstr = urllib.parse.urlencode(keys)
    url = "https://api.untappd.com/v4/checkin/view/{!s}?{!s}".format(checkin, qstr)

    resp = await get_data_from_untappd(ctx.author, url)
    if resp['meta']['code'] != 200:
        # print("Lookup failed for url: "+url)
        return "Lookup failed with {!s} - {!s}".format(
            resp["meta"]["code"],
            resp["meta"]["error_detail"])

    if "response" in resp:
        if "checkin" in resp["response"]:
            user_checkin = resp["response"]["checkin"]
            return await checkin_to_embed(config, ctx, channels, user_checkin)
    return embedme("Unplanned for error looking up checkin")


async def get_checkins(config, ctx, channels, profile: str = None,
                       start: int = None, count: int = 0):
    """Given some information get checkins of a user"""
    embed = None
    checkin_list = []
    if not profile:
        return "No profile was provided or calculated"
    count = count or await list_size(config, ctx.guild)

    keys = await get_auth(ctx.author.id, config)
    if count:
        keys["limit"] = count
    if start:
        keys["max_id"] = start
    keys["client_id"] = await config.client_id()
    qstr = urllib.parse.urlencode(keys)
    url = "https://api.untappd.com/v4/user/checkins/{!s}?{!s}".format(
        profile, qstr
    )
    # print("Looking up: {!s}".format(url))
    resp = await get_data_from_untappd(ctx.author, url)
    if resp["meta"]["code"] != 200:
        # print("Lookup failed for url: "+url)
        return "Lookup failed with {!s} - {!s}".format(
            resp["meta"]["code"],
            resp["meta"]["error_detail"]
        )

    try:
        if resp["response"]["checkins"]["count"] == 1:
            embed = await checkin_to_embed(
                config, ctx, channels, resp["response"]["checkins"]["items"][0])
        elif resp["response"]["checkins"]["count"] > 1:
            checkins = resp["response"]["checkins"]["items"]
            checkin_text = checkins_to_string(count, checkins)
            checkin_list = checkins
            embed = discord.Embed(title=profile, description=checkin_text[:2048])
    except KeyError:
        return "No checkins found for user"

    result = dict()
    result["embed"] = embed
    if checkin_list:
        result["list"] = checkin_list
    return result


async def search_beer(config, ctx, query, limit=None, homebrew: bool = False):
    """Given a query string and some other
    information returns an embed of results"""

    keys = await get_auth(ctx.author.id, config)
    keys["q"] = query
    keys["limit"] = limit
    qstr = urllib.parse.urlencode(keys)

    url = "https://api.untappd.com/v4/search/beer?%s" % qstr
    #    print(url)
    resp = await get_data_from_untappd(ctx.author, url)
    if resp["meta"]["code"] == 200:
        if homebrew:
            return resp['response']['homebrew']
        else:
            return resp['response']['beers']
    else:
        return ("Search for `{!s}` resulted in {!s}: {!s}".
                format(query, resp["meta"]["code"],
                       resp["meta"]["error_detail"]))


async def search_beer_to_embed(config, ctx, channels, query, limit=None, homebrew: bool = False):
    """Searches for a beer and returns an embed"""
    beers = await search_beer(config, ctx, query, limit, homebrew)
    if isinstance(beers, str):
        # I'm not sure what happens when a naked embed gets returned.
        # return embedme(beers)
        return beers

    response = ""
    list_limit = limit or await list_size(config, None)
    result_text = "Your search returned {!s} beers:\n".format(
        beers["count"]
    )
    beer_list = []
    if beers['count'] == 1:
        return await lookup_beer(
            config, ctx, channels,
            beers['items'][0]['beer']['bid'])
    elif beers['count'] > 1:
        firstnum = 1

        beers = beers['items']
        for num, beer in zip(range(list_limit),
                             beers):
            result_text += EMOJI[num + 1] + " "
            result_text += str(beer['beer']['bid']) + ". ["
            result_text += beer['beer']['beer_name'] + "]"
            result_text += "(" + "https://untappd.com/beer/"
            result_text += str(beer['beer']['bid']) + ") "
            brewery = ("by *[{!s}](https://untappd.com/w/"
                       "{!s}/{!s})*").format(
                beer['brewery']['brewery_name'],
                beer['brewery']['brewery_slug'],
                beer['brewery']['brewery_id'])
            result_text += brewery
            if beer['beer']['auth_rating']:
                result_text += " ({!s})".format(
                    beer['beer']['auth_rating']
                )
            elif beer['have_had']:
                result_text += " (\\*)"
            result_text += "\n"
            beer_list.append(beer['beer']['bid'])
            if firstnum == 1:
                firstnum = beer['beer']['bid']

        result_text += "Look up a beer with `findbeer "
        result_text += str(firstnum) + "`"
    else:
        response += "no beers"
        # print(json.dumps(j, indent=4))

    embed = discord.Embed(title=response, description=result_text[:2048])
    result = dict()
    result["embed"] = embed
    if beer_list:
        result["beer_list"] = beer_list
    return result


async def profile_lookup(config, ctx, profile, limit=5):
    """Looks up a profile in untappd by username"""
    query = urllib.parse.quote_plus(profile)
    api_key = "client_id={}&client_secret={}".format(
        await config.client_id(),
        await config.client_secret())

    url = "https://api.untappd.com/v4/user/info/" + query + "?" + api_key

    # TODO: Honor is_private flag on private profiles.

    resp = await get_data_from_untappd(ctx.author, url)
    if resp["meta"]["code"] == 400:
        return "The profile '{!s}' does not exist".format(profile)
    elif resp['meta']['code'] == 200:
        embed, beer_list = await user_to_embed(config, resp['response']['user'], limit)
        result = {"embed": embed}
        if beer_list:
            result["beer_list"] = beer_list
        return result
        # Coded as an enhancement request but managed through Discord means
        # friendly = await is_friendly(self, config, ctx, profile)
        # if friendly:
        #     embed.add_field(name="Friendly",
        #                     value="Accepts friend requests from Discordians",
        #                     inline=True)
    else:
        return "Profile query failed with code {!s} - {!s}".format(
            resp["meta"]["code"], resp["meta"]["error_detail"])


async def user_to_embed(config, user, limit=5):
    """Takes the user portion of a json response and returns an embed \
and a checkin list"""
    beer_list = []
    recent_message = ""
    if 'checkins' in user:
        recent_message = checkins_to_string(limit, user['checkins']['items'])
        beer_list = user['checkins']['items']
    name_str = user['user_name']
    flair_str = ""
    if user['is_supporter']:
        flair_str += await config.supporter_emoji()
    if user['is_moderator']:
        flair_str += await config.moderator_emoji()
    embed = discord.Embed(title=name_str,
                          description=recent_message[:2048]
                                      or "No recent beers visible",
                          url=user['untappd_url'])
    embed.add_field(
        name="Checkins",
        value=str(user['stats']['total_checkins']),
        inline=True)
    embed.add_field(
        name="Uniques",
        value=str(user['stats']['total_beers']),
        inline=True)
    embed.add_field(
        name="Badges",
        value=str(user['stats']['total_badges']),
        inline=True)
    if (("bio" in user)
            and (user['bio'])):
        embed.add_field(name="Bio",
                        value=user['bio'][:1024],
                        inline=False)
    if user['location']:
        embed.add_field(name="Location",
                        value=user['location'],
                        inline=True)
    if flair_str:
        embed.add_field(name="Flair",
                        value=flair_str,
                        inline=True)
    embed.set_thumbnail(url=user['user_avatar'])

    return embed, beer_list


async def is_friendly(config, ctx, profile: str):
    """Checks if user set themselves to accept friend requests"""
    if ctx.guild:
        server = str(ctx.guild.id)
    else:
        return False

    member = ctx.guild.get_member_named(profile)
    if member:
        try:
            friendme = await config.get_raw(server, str(member.id), "friendme") == 1
            return friendme
        except KeyError:
            pass
    if server:
        # See if they set a nickname
        try:
            authors = await config.get_raw(server)
            try:
                for author in authors:
                    nick = await config.get_raw(server, author, "nick")
                    if nick == profile:
                        friendme = await config.get_raw(server, author, "friendme") == 1
                        return friendme
            except (KeyError, TypeError):
                pass
        except KeyError:
            pass

    return False


EMOJI = {
    1: "1️⃣",
    2: "2️⃣",
    3: "3️⃣",
    4: "4️⃣",
    5: "5️⃣",
    6: "6️⃣",
    7: "7️⃣",
    8: "8️⃣",
    9: "9️⃣",
    10: "🔟",
    "beers": "🍻",
    "beer": "🍺",
    "comments": "💬",
    "right": "➡",
    "left": "⬅"
}


async def embed_menu(client, config, ctx, channels, beer_list: list, message, timeout: int = 30,
                     type_: str = "beer", paging: bool = False, reacted: bool = False):
    """Says the message with the embed and adds menu for reactions"""
    emoji = []
    limit = await list_size(config, ctx.guild)

    if not message:
        await ctx.send("I didn't get a handle to an existing message.")
        return

    for num, beer in zip(range(1, limit + 1), beer_list): # pylint: disable=unused-variable
        emoji.append(EMOJI[num])
        await message.add_reaction(EMOJI[num])

    def check(reaction, person):
        if reaction.emoji and reaction.emoji in emoji:
            return person == ctx.author
        return False

    try:
        react, user = await client.wait_for('reaction_add', timeout=timeout, check=check) # pylint: disable=unused-variable
    except asyncio.TimeoutError:
        # await ctx.send("Timed out, cleaning up")
        try:
            try:
                await message.clear_reactions()
            except discord.Forbidden:
                for e in emoji:
                    await message.remove_reaction(e, client.user)
        except discord.Forbidden:
            pass
        return None
    else:
        # Somebody reacted so can remove the message
        try:
            await message.delete()
        except discord.Forbidden:
            await ctx.send("I wanted to clean up but I am not allowed")

        reacts = {v: k for k, v in EMOJI.items()}
        react = reacts[react.emoji]
        react -= 1
        if len(beer_list) > react:
            new_embed = ""
            if type_ == "beer":
                new_embed = await lookup_beer(config, ctx, channels,
                                              beer_list[react])
            elif type_ == "checkin":
                new_embed = await checkin_to_embed(config, ctx, channels, beer_list[react])
            if isinstance(new_embed, discord.Embed):
                await ctx.send(embed=new_embed)
        return None

    # await embed_menu(client, config, ctx, channels, beer_list, message, timeout=timeout, reacted=True,
    # type_=type_, paging=paging)


def checkins_to_string(count: int, checkins: list):
    """Takes a list of checkins and returns a string"""
    # checkin_text = ("**checkin** - **beerID** - **beer (caps)**\n\t**brewery** - **badges** - **when**\n")
    checkin_text = ""
    for num, checkin in zip(range(count), checkins):
        checkin_text += ("{!s} [{!s}](https://untappd.com/beer/{!s}) ({!s}) [{!s}] by "
                         "[{!s}](https://untappd.com/brewery/{!s})"
                         ).format(
            EMOJI[num + 1],
            checkin["beer"]["beer_name"],
            checkin["beer"]["bid"],
            checkin["rating_score"] or "N/A",
            checkin["beer"]["bid"],
            checkin["brewery"]["brewery_name"],
            checkin["brewery"]["brewery_id"]
        )
        if checkin["badges"]["count"]:
            checkin_text += " - {!s} badge{!s}".format(checkin["badges"]["count"], add_s(checkin["badges"]["count"]))
        checkin_text += " - {!s} [{!s}]\n".format(time_ago(checkin["created_at"]), checkin["checkin_id"])
    return checkin_text


async def checkin_to_embed(config, ctx, channels, checkin):
    """Given a checkin object return an embed of that checkin's information"""

    # Get the base beer information
    beer = await get_beer_by_id(config, ctx, checkin["beer"]["bid"])
    # titleStr = "Checkin {!s}".format(checkin["checkin_id"])
    url = "https://untappd.com/user/{!s}/checkin/{!s}".format(checkin["user"]["user_name"], checkin["checkin_id"])
    # deep_checkin_link = "[{!s}](untappd://checkin/{!s})".format(
    #    await config.app_emoji(),
    #    checkin["checkin_id"]
    # )
    title = "{!s} was drinking {!s} by {!s}".format(checkin["user"]["first_name"], checkin["beer"]["beer_name"],
                                                    checkin["brewery"]["brewery_name"])
    # deep_beer_link = "[{!s}](untappd://beer/{!s})".format(
    #    await config.app_emoji(),
    #    checkin["beer"]["bid"]
    # )
    # deep_brewery_link = "[{!s}](untappd://brewery/{!s})".format(
    #    await config.app_emoji(),
    #    checkin["brewery"]["brewery_id"]
    # )
    checkin_time = datetime.strptime(checkin["created_at"], "%a, %d %b %Y %H:%M:%S %z")

    embed = discord.Embed(title=title, description=beer["beer_description"][:2048], url=url, timestamp=checkin_time)
    if checkin["media"]["count"] >= 1:
        embed.set_thumbnail(
            url=checkin["media"]["items"][0]["photo"]["photo_img_md"]
        )
    # Add fields of interest
    beer_link = "[{!s}](https://untappd.com/beer/{!s})".format(checkin["beer"]["beer_name"], checkin["beer"]["bid"])
    embed.add_field(name="Beer", value=beer_link)
    brewery_link = "[{!s}](https://untappd.com/brewery/{!s})".format(checkin["brewery"]["brewery_name"],
                                                                     checkin["brewery"]["brewery_id"])
    brewery_link += " in {!s}".format(brewery_location(checkin["brewery"]))
    embed.add_field(name="Brewery", value=brewery_link)
    if isinstance(checkin["venue"], dict):
        venue = "[{!s}](https://untappd.com/venue/{!s})".format(checkin["venue"]["venue_name"],
                                                                checkin["venue"]["venue_id"])
        embed.add_field(name="Venue", value=venue)
    title = "Rating"
    if checkin["rating_score"]:
        title += " - {!s}".format(checkin["rating_score"])
    rating = "**{!s}** Average ({!s})".format(round(beer['rating_score'], 2), human_number(beer['rating_count']))
    embed.add_field(name=title, value=rating)
    embed.add_field(name="Style", value=beer["beer_style"])
    embed.add_field(name="ABV", value=(beer["beer_abv"] or "N/A"))
    embed.add_field(name="IBU", value=(beer["beer_ibu"] or "N/A"))
    checkin_text = "{!s} checkins from {!s} users".format(human_number(beer["stats"]["total_count"]),
                                                          human_number(beer["stats"]["total_user_count"]))
    embed.add_field(name="Checkins", value=checkin_text)
    if "collaborations_with" in beer:
        collab_text = ""
        collabs = beer['collaborations_with']['items']
        for num, collab in zip(range(10), collabs): # pylint: disable=unused-variable
            collab_text += "[" + collab['brewery']['brewery_name']
            collab_text += "](https://untappd.com/brewery/"
            collab_text += str(collab['brewery']['brewery_id']) + ")\n"
        if len(collabs) > 10:
            collab_text += "... and more"
        embed.add_field(name="Collaboration with", value=collab_text[:2048])
    if checkin["checkin_comment"]:
        embed.add_field(name="Comment", value=checkin["checkin_comment"][:1024])
    if (checkin["comments"]["count"] + checkin["toasts"]["count"]) > 0:
        new_value = "{!s}({!s}){!s}({!s})".format(EMOJI["comments"], checkin["comments"]["count"], EMOJI["beers"],
                                                  checkin["toasts"]["count"])
        embed.add_field(name="Flags", value=new_value)
    if checkin["badges"]["count"] > 0:
        badge_text = ""
        for badge in checkin["badges"]["items"]:
            badge_text += "{!s}\n".format(badge["badge_name"])
        embed.add_field(name="Badges", value=badge_text[:1024])
    #    embed.add_field(name="DeepCheckin", value=deep_checkin_link)
    #    embed.add_field(name="DeepBeer", value=deep_beer_link)
    #    embed.add_field(name="DeepBrewery", value=deep_brewery_link)
    embed.set_footer(text="Checkin {!s} / Beer {!s}".format(checkin["checkin_id"], checkin["beer"]["bid"]))
    channel = ctx.channel.id
    if channel not in channels:
        channels[channel] = {}
    channels[channel]["checkin"] = checkin["checkin_id"]
    channels[channel]["beer"] = checkin["beer"]["bid"]

    return embed


async def list_size(config, server=None):
    """Returns a list size if configured for the server or the default size"""
    try:
        size = await config.get_raw(server.id, "max_items_in_list")
    except (KeyError, AttributeError):
        size = await config.max_items_in_list()
    return size


def embedme(error_text, title="Error encountered"):
    """Returns an embed object with the error string provided"""
    embed = discord.Embed(title=title,
                          description=error_text[:2048])
    return embed


def human_number(number):
    # Billion, Million, K, end
    number = int(number)
    if number > 1000000000:
        return str(round(number / 1000000000, 1)) + "B"
    elif number > 1000000:
        return str(round(number / 1000000, 1)) + "M"
    elif number > 1000:
        return str(round(number / 1000, 1)) + "K"
    else:
        return str(number)


def time_ago(time_str, long=False):
    """Turns a time string into a string of how long ago a thing was"""

    return_str = "unknown ago"
    timewas = datetime.strptime(time_str, "%a, %d %b %Y %H:%M:%S %z")
    # Thu, 06 Nov 2014 18:54:35 +0000
    nowtime = datetime.now(timezone.utc)
    timediff = nowtime - timewas
    (years, days) = divmod(timediff.days, 365)
    (months, days) = divmod(days, 30)
    (hours, secs) = divmod(timediff.seconds, 3600)
    (minutes, secs) = divmod(secs, 60)
    if long:
        if years:
            return_str = "{!s} year{}, {!s} month{} ago".format(
                years, add_s(years), months, add_s(months))
        elif months:
            return_str = "{!s} month{}, {!s} day{} ago".format(
                months, add_s(months), days, add_s(days))
        elif days:
            return_str = "{!s} day{}, {!s} hour{} ago".format(
                days, add_s(days), hours, add_s(hours))
        elif hours:
            return_str = "{!s} hour{}, {!s} minute{} ago".format(
                hours, add_s(hours), minutes, add_s(minutes))
        elif minutes:
            return_str = "{!s} minute{}, {!s} second{} ago".format(
                minutes, add_s(minutes), secs, add_s(secs))
        elif secs:
            return_str = "less than a minute ago"
    else:
        if years:
            return_str = "{!s}y{!s}m ago".format(years, months)
        elif months:
            return_str = "{!s}m{!s}d ago".format(months, days)
        elif days:
            return_str = "{!s}d{!s}h ago".format(days, hours)
        elif hours:
            return_str = "{!s}h{!s}m ago".format(hours, minutes)
        elif minutes:
            return_str = "{!s}m{!s}s ago".format(minutes, secs)
        elif secs:
            return_str = "now"

    return return_str


def add_s(num):
    """If it's 1, return blank otherwise return s"""
    if num == 1:
        return ""
    return "s"


def brewery_location(brewery):
    """Takes an untappd brewery response and returns a location string"""

    brewery_loca = []
    if "brewery_city" in brewery["location"]:
        if brewery["location"]["brewery_city"]:
            brewery_loca.append(brewery["location"]["brewery_city"])
    if "brewery_state" in brewery["location"]:
        if brewery["location"]["brewery_state"]:
            brewery_loca.append(
                brewery["location"]["brewery_state"]
            )
    if "country_name" in brewery:
        if brewery["country_name"]:
            brewery_loca.append(brewery["country_name"])
    return format(', '.join(brewery_loca))


async def get_data_from_untappd(author, url):
    """Perform a GET against the provided URL, returns a response
    NOTE: Provided URL is already formatted"""

    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.get(url) as resp:
                headers = resp.headers
                if "X-Ratelimit-Remaining" in headers:
                    if int(headers["X-Ratelimit-Remaining"]) < 10:
                        await author.send(
                            ("Warning: **{!s}** API calls left for you this hour "
                             "and some commands use multiple calls. Sorry."
                             ).format(headers["X-Ratelimit-Remaining"])
                        )
                return await resp.json()
    except aiohttp.ClientError as exc:
        return "Untappd call failed with {!s}".format(exc)


async def add_react(message, react):
    """Add a reaction to a message. Return whether success or not"""

    try:
        await(message.add_reaction(react))
    except (discord.HTTPException, discord.Forbidden, discord.NotFound, discord.InvalidArgument):
        return False

    return True
