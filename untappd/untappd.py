import discord
# import pprint
from discord.ext import commands
from cogs.utils import checks
import aiohttp
from .utils.dataIO import dataIO
import os
import urllib.parse
from __main__ import send_cmd_help
from datetime import datetime
import json

# Beer: https://untappd.com/beer/<bid>
# Brewery: https://untappd.com/brewery/<bid>
# Checkin: https://untappd.com/c/<checkin>


class Untappd():
    """Untappd cog that lets the bot look up beer
    information from untappd.com!"""

    def __init__(self, bot):
        self.bot = bot
        self.settings = dataIO.load_json("data/untappd/settings.json")
        if "max_items_in_list" not in self.settings:
            self.settings["max_items_in_list"] = 5
        if "supporter_emoji" not in self.settings:
            self.settings["supporter_emoji"] = ":moneybag:"
        if "moderator_emoji" not in self.settings:
            self.settings["moderator_emoji"] = ":crown:"
        self.session = aiohttp.ClientSession()
        self.emoji = {
                1: "1⃣",
                2: "2⃣",
                3: "3⃣",
                4: "4⃣",
                5: "5⃣",
                6: "6⃣",
                7: "7⃣",
                8: "8⃣",
                9: "9⃣",
                10: "🔟",
                "beers": "🍻",
                "beer": "🍺",
                "comments": "💬"
        }

    @commands.group(no_pm=False, invoke_without_command=False,
                    pass_context=True)
    async def untappd(self, ctx):
        """Explicit Untappd things"""
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)

    @untappd.command(no_pm=True, pass_context=True)
    @checks.mod_or_permissions(manage_messages=True)
    async def list_size(self, ctx, new_size: int):
        """The length of lists of resultsm specific to a server now"""
        is_pm = True
        try:
            server = ctx.message.server.id
            if server not in self.settings:
                self.settings[server] = {}
            is_pm = False
        except KeyError:
            is_pm = True
        new_size += 0
        # The true maximum size is 10 because there's that many emoji
        if new_size > 10:
            new_size = 10
            await self.bot.say("Reducing the maximum size to " +
                               "10 due to emoji constraints")
        if is_pm:
            self.settings["max_items_in_list"] = new_size
        else:
            self.settings[server]["max_items_in_list"] = new_size
        dataIO.save_json("data/untappd/settings.json", self.settings)
        await self.bot.say("Maximum list size is now {!s}".format(new_size))

    @untappd.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def supporter_emoji(self, emoji: str):
        """The moji to use for supporters"""
        self.settings["supporter_emoji"] = str(emoji)
        dataIO.save_json("data/untappd/settings.json", self.settings)
        await self.bot.say("Profiles of supporters will now display (" +
                           str(emoji) + ")")

    @untappd.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def moderator_emoji(self, emoji: str):
        """The emoji to use for super users"""
        self.settings["moderator_emoji"] = str(emoji)
        dataIO.save_json("data/untappd/settings.json", self.settings)
        await self.bot.say("Profiles of super users will now display (" +
                           str(emoji) + ")")

    @untappd.command(pass_context=True, no_pm=True)
    async def setnick(self, ctx, keywords):
        """Set your untappd user name to use for future commands"""
        # TODO: Replace future commands with the commands
        if not keywords:
            await send_cmd_help(ctx)
        if (ctx.message.server):
            server = ctx.message.server.id
            if server not in self.settings:
                self.settings[server] = {}
            author = ctx.message.author.id
            if author not in self.settings[server]:
                self.settings[server][author] = {}
            self.settings[server][author]["nick"] = keywords
            await self.bot.say("When you look yourself up on untappd" +
                               " I will use `" + keywords + "`")
            dataIO.save_json("data/untappd/settings.json", self.settings)
        else:
            await self.bot.say("I was unable to set that for this server")
            print("Channel type: {!s}".format(ctx.message.channel.type))
            print("Guild: {!s}".format(ctx.message.server))

    @untappd.command(pass_context=True, no_pm=False)
    async def authme(self, ctx):
        """Starts the authorization process for a user"""
        # TODO: Check if already authorized and confirm to reauth
        auth_url = ("https://untappd.com/oauth/authenticate/?client_id="
                    "{!s}&response_type=token&redirect_url={!s}").format(
                        self.settings["client_id"],
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
        await self.bot.whisper(disclaimer, embed=embed)

    @untappd.command(pass_context=True, no_pm=False, name="auth-token")
    async def auth_token(self, ctx, keyword):
        """Finishes the authorization process"""
        if not keyword:
            await send_cmd_help(ctx)
        author = ctx.message.author.id
        if author not in self.settings:
            self.settings[author] = {}
        self.settings[author]["token"] = keyword
        dataIO.save_json("data/untappd/settings.json", self.settings)
        await self.bot.whisper("Token saved, thank you")

    @untappd.command(pass_context=True, no_pm=False)
    async def unauthme(self, ctx):
        """Removes the authorization token for a user"""
        # TODO: Check if already authorized and confirm to reauth
        author = ctx.message.author.id
        response = ""
        if author in self.settings:
            self.settings[author].pop("token", None)
            response = "Authorization removed"
        else:
            response = "It doesn't look like you were authorized before"
        dataIO.save_json("data/untappd/settings.json", self.settings)
        await self.bot.say(response)

    @commands.command(pass_context=True, no_pm=False)
    async def findbeer(self, ctx, *keywords):
        """Search Untappd.com using the API"""
        """A search uses characters, a lookup uses numbers"""
        embed = False
        beer_list = []
        resultStr = ""
        list_limit = list_size(self, ctx.message.server)

        if not check_credentials(self.settings):
            await self.bot.say("The owner has not set the API information " +
                               "and should use the `untappd_apikey` command")
            return

        if keywords:
            keywords = "+".join(keywords)
        else:
            await self.bot.send_cmd_help(ctx)
            return

        await self.bot.send_typing(ctx.message.channel)
        if keywords.isdigit():
            embed = await lookupBeer(self, keywords, list_size=1)
            # await self.bot.say( embed=embed)
        else:
            results = await searchBeer(self, keywords, limit=list_limit)
            if isinstance(results, dict):
                embed = results["embed"]
                if "beer_list" in results:
                    beer_list = results["beer_list"]
            else:
                embed = results
            # await self.bot.say(resultStr, embed=embed)

        if embed:
            message = await self.bot.say(resultStr, embed=embed)
        else:
            message = await self.bot.say(resultStr)

        if (len(beer_list) > 1):
            await embed_menu(self, ctx, beer_list, message, 30)

    @commands.command(pass_context=True, no_pm=False)
    async def findbeer1(self, ctx, *keywords):
        embed = False
        resultStr = ""
        await self.bot.send_typing(ctx.message.channel)
        results = await searchBeer(self, " ".join(keywords), limit=1)
        if isinstance(results, dict):
            embed = results["embed"]
            await self.bot.say(resultStr, embed=embed)
        else:
            await self.bot.say(resultStr, embed=results)

    @commands.command(pass_context=True)
    async def lastbeer(self, ctx, profile: str=None):
        """Displays details for the last beer a person had"""

        embed = False
        resultStr = ""
        author = ctx.message.author
        if ctx.message.server:
            guild = str(ctx.message.server.id)
        else:
            guild = 0
        auth_token = ""

        if not check_credentials(self.settings):
            await self.bot.say("The owner has not set the API information " +
                               "and should use the `untappd_apikey` command")
            return

#        await self.bot.say("I got a user " + profile)
        if ctx.message.mentions:
            # If user has set a nickname, use that - but only if it's not a PM
            if ctx.message.server:
                user = ctx.message.mentions[0]
                # print("looking up {!s}".format(user.id))
                try:
                    profile = self.settings[guild][user.id]["nick"]
                except KeyError:
                    profile = user.display_name

        if not profile:
            try:
                profile = self.settings[guild][author.id]["nick"]
            except KeyError:
                profile = author.display_name

        if author.id in self.settings:
            if "token" in self.settings[author.id]:
                auth_token = self.settings[author.id]["token"]
        await self.bot.send_typing(ctx.message.channel)
        results = await getCheckins(self, ctx, profile=profile,
                                    count=1, auth_token=auth_token)
        if (isinstance(results, dict)) and ("embed" in results):
            embed = results["embed"]
            await self.bot.say(resultStr, embed=embed)
        else:
            await self.bot.say(results)
        return

    @commands.command(pass_context=True, no_pm=False)
    async def profile(self, ctx, profile: str=None):
        """Search for a user's information by providing their profile name,
        discord mentions OK"""

        embed = False
        beer_list = []
        resultStr = ""
        author = ctx.message.author
        if ctx.message.server:
            guild = str(ctx.message.server.id)
        else:
            guild = 0

        if not check_credentials(self.settings):
            await self.bot.say("The owner has not set the API information " +
                               "and should use the `untappd_apikey` command")
            return

        if ctx.message.mentions:
            # If user has set a nickname, use that - but only if it's not a PM
            if ctx.message.server:
                user = ctx.message.mentions[0]
                try:
                    profile = self.settings[guild][user.id]["nick"]
                except KeyError:
                    profile = user.display_name

        if not profile:
            try:
                profile = self.settings[guild][author.id]["nick"]
            except KeyError:
                profile = None
        if not profile:
            profile = author.display_name
            print("Using '{}'".format(profile))
        await self.bot.send_typing(ctx.message.channel)
        results = await profileLookup(self, profile,
                                      limit=list_size(self,
                                                      ctx.message.server))
        if isinstance(results, dict):
            if "embed" in results:
                embed = results["embed"]
            if "beer_list" in results:
                beer_list = results["beer_list"]
        else:
            resultStr = results
        if embed:
            message = await self.bot.say(resultStr, embed=embed)
        else:
            message = await self.bot.say(resultStr)
        if len(beer_list) > 1:
            await embed_menu(self, ctx, beer_list, message, 30, type="checkin")
        return

    @untappd.command(pass_context=True, no_pm=False)
    @checks.is_owner()
    async def untappd_apikey(self, ctx, *keywords):
        """Sets the id and secret that you got from applying for
            an untappd api"""
        if len(keywords) == 2:
            self.settings["client_id"] = keywords[0]
            self.settings["client_secret"] = keywords[1]
            self.settings["CONFIG"] = True
            dataIO.save_json("data/untappd/settings.json", self.settings)
            await self.bot.say("API set")
        else:
            await self.bot.say("I am expecting two words, the id and " +
                               "the secret only")

    @commands.command(pass_context=True, no_pm=False)
    async def toast(self, ctx, *keywords):
        """Toasts a checkin by number, if you're friends"""

        author = ctx.message.author
        auth_token = None
        checkin = 0

        if not check_credentials(self.settings):
            await self.bot.say("The owner has not set the API information " +
                               "and should use the `untappd_apikey` command")
            return

        if author.id in self.settings:
            if "token" in self.settings[author.id]:
                auth_token = self.settings[author.id]["token"]

        if not auth_token:
            await self.bot.say(("Unable to toast until you have "
                                "authenticated me using `untappd authme`"))
            return

        for word in keywords:
            # print("Checking " + word)
            if word.isdigit():
                checkin = int(word)

        if not word:
            await self.bot.say("A checkin ID number is required")
            return

        embed = await toastIt(self, checkin=checkin, auth_token=auth_token)
        if isinstance(embed, str):
            await self.bot.say(embed)
        else:
            await self.bot.say("", embed=embed)

    @commands.command(pass_context=True, no_pm=False)
    async def checkin(self, ctx, *keywords):
        """Returns a single checkin by number"""

        author = ctx.message.author
        auth_token = None
        checkin = 0

        if not check_credentials(self.settings):
            await self.bot.say("The owner has not set the API information " +
                               "and should use the `untappd_apikey` command")
            return

        if author.id in self.settings:
            if "token" in self.settings[author.id]:
                auth_token = self.settings[author.id]["token"]

        for word in keywords:
            # print("Checking " + word)
            if word.isdigit():
                checkin = int(word)

        if not checkin:
            await self.bot.say("A checkin ID number is required")
            return

        await self.bot.send_typing(ctx.message.channel)
        embed = await getCheckin(self, checkin=checkin, auth_token=auth_token)
        if isinstance(embed, str):
            await self.bot.say(embed)
        else:
            await self.bot.say("", embed=embed)

    @commands.command(pass_context=True, no_pm=False)
    async def checkins(self, ctx, *keywords):
        """Returns a list of checkins"""

        embed = None
        profile = ""
        startnum = 0
        author = ctx.message.author
        if ctx.message.server:
            guild = str(ctx.message.server.id)
        else:
            guild = 0
        auth_token = None
        checkin_list = []
        resultStr = ""
        countnum = list_size(self, server=ctx.message.server)
        # determine if a profile or number was given
        if not check_credentials(self.settings):
            await self.bot.say("The owner has not set the API information " +
                               "and should use the `untappd_apikey` command")
            return

        if author.id in self.settings:
            if "token" in self.settings[author.id]:
                auth_token = self.settings[author.id]["token"]

        # If a keyword was provided and it's all digits then look up that one
        # Looks like there is no way to look up by id alone

        if ctx.message.mentions:
            # If user has set a nickname, use that - but only if it's not a PM
            if ctx.message.server:
                user = ctx.message.mentions[0]
                try:
                    profile = self.settings[guild][user.id]["nick"]
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
                profile = self.settings[guild][author.id]["nick"]
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

        await self.bot.send_typing(ctx.message.channel)
        results = await getCheckins(self, ctx, profile=profile,
                                    start=startnum, count=countnum,
                                    auth_token=auth_token)
        if isinstance(results, dict):
            if "embed" in results:
                embed = results["embed"]
            if "list" in results:
                checkin_list = results["list"]
        else:
            resultStr = results
        if embed:
            message = await self.bot.say(resultStr, embed=embed)
        else:
            message = await self.bot.say(resultStr)
        if len(checkin_list) > 1:
            await embed_menu(self, ctx, checkin_list, message, 30,
                             type="checkin")
        return

    @commands.command(pass_context=True, no_pm=False)
    async def ifound(self, ctx, bid: int):
        """Add a found beer to the spreadsheet. Accepts a beer id"""

        author = ctx.message.author
        if ctx.message.server:
            guild = str(ctx.message.server.id)
            try:
                profile = self.settings[guild][author.id]["nick"]
            except KeyError:
                profile = author.display_name
        else:
            profile = author.display_name

        await self.bot.send_typing(ctx.message.channel)
        url = ("https://script.google.com/macros/s/AKfycbwLJ06a-f_F2egj1oHifV7"
               "YEQkIEjTNKnQ5f42pgFYMhOE8KvI/exec")
        url += "?bid={!s}&username={!s}".format(bid, profile)
        async with self.session.get(url) as resp:
            if resp.status == 200:
                j = await resp.json()
            else:
                return "Query failed with code " + str(resp.status)

            if j['result'] == "success":
                await self.bot.say("Beer added!")
            else:
                await self.bot.say("Something went wrong adding the beer")


def check_folders():
    if not os.path.exists("data/untappd"):
        print("Creating untappd folder")
        os.makedirs("data/untappd")


def check_files():
    f = "data/untappd/settings.json"
    data = {"CONFIG": False,
            "max_items_in_list": 5,
            "supporter_emoji": ":moneybag:",
            "moderator_emoji": ":crown:"
            }
    if not dataIO.is_valid_json(f):
        dataIO.save_json(f, data)
    else:
        temp_settings = dataIO.load_json("data/untappd/settings.json")
        modified = False
        if "client_id" in temp_settings:
            temp_settings["CONFIG"] = True
            modified = True
        if "max_items_in_list" not in temp_settings:
            temp_settings["max_items_in_list"] = 5
            modified = True

        if modified:
            dataIO.save_json(f, temp_settings)


def check_credentials(settings):
    if "client_id" not in settings:
        return False

    if "client_secret" not in settings:
        return False

    return True


def setup(bot):
    check_folders()
    check_files()
    bot.add_cog(Untappd(bot))


async def get_beer_by_id(self, beerid):
    """Use the untappd API to return a beer dict for a beer id"""

    api_key = "client_id=" + self.settings["client_id"] + "&client_secret="
    api_key += self.settings["client_secret"]
    keys = dict()
    keys["client_id"] = self.settings["client_id"]
    keys["client_secret"] = self.settings["client_secret"]
    qstr = urllib.parse.urlencode(keys)
    url = "https://api.untappd.com/v4/beer/info/{!s}?{!s}".format(
        beerid, qstr
    )
    async with self.session.get(url) as resp:
        if resp.status == 200:
            j = await resp.json()
        else:
            return "Query failed with code " + str(resp.status)

        if j['meta']['code'] == 200:
            return j['response']['beer']


async def lookupBeer(self, beerid, rating=None, list_size=5):
    """Look up a beer by id"""

    beer = await get_beer_by_id(self, beerid)
    if (not beer or isinstance(beer, str)):
        return embedme("Problem looking up a beer by id")
    beer_url = "https://untappd.com/b/{}/{!s}".format(
        beer['beer_slug'],
        beer['bid'])
    brewery_url = "https://untappd.com/brewery/{!s}".format(
        beer['brewery']['brewery_id'])
    beer_title = beer['beer_name']
    embed = discord.Embed(title=beer_title,
                          description=beer['beer_description'][:2048],
                          url=beer_url)
    embed.set_author(name=beer['brewery']['brewery_name'],
                     url=brewery_url,
                     icon_url=beer['brewery']['brewery_label'])
    embed.add_field(name="Style", value=beer['beer_style'],
                    inline=True)
    rating_str = "{!s} Caps ({})".format(
        round(beer['rating_score'], 2),
        human_number(beer['rating_count']))
    embed.add_field(name="Rating", value=rating_str, inline=True)
    embed.add_field(name="ABV", value=beer['beer_abv'], inline=True)
    embed.add_field(name="IBU", value=beer['beer_ibu'], inline=True)
    if rating:
        embed.add_field(name="Checkin Rating",
                        value=str(rating),
                        inline=True)
    embed.set_thumbnail(url=beer['beer_label'])

    if "collaborations_with" in beer:
        collabStr = ""
        collabs = beer['collaborations_with']['items']
        for collab in collabs:
            collabStr += "[" + collab['brewery']['brewery_name']
            collabStr += "](https://untappd.com/brewery/"
            collabStr += str(collab['brewery']['brewery_id']) + ")\n"
        embed.add_field(name="Collaboration with", value=collabStr)
    return embed


async def toastIt(self, checkin: int, auth_token: str=None):
    """Toast a specific checkin"""

    keys = dict()
    keys["client_id"] = self.settings["client_id"]
    keys["access_token"] = auth_token

    qstr = urllib.parse.urlencode(keys)
    url = ("https://api.untappd.com/v4/checkin/toast/{!s}?{!s}").format(
        checkin, qstr
    )
    # print("Using URL: {!s}".format(url))

    async with self.session.get(url) as resp:
        if resp.status == 200:
            j = await resp.json()
        elif resp.status == 500:
            return ("Toast failed, probably because you haven't authenticated"
                    " or aren't friends with this person."
                    " Use `untappd authme` to let the bot act as you.")
        else:
            # print("Lookup failed for url: "+url)
            return ("Toast failed with {!s}").format(resp.status)

    if j["meta"]["code"] != 200:
        # print("Lookup failed for url: "+url)
        return ("Toast failed with {!s} - {!s}").format(
            j["meta"]["code"],
            j["meta"]["error_detail"])

    if "result" in j["response"]:
        if j["response"]["result"] == "success":
            if j["response"]["like_type"] == "toast":
                return "Toasted!"
            elif j["response"]["like_type"] == "un-toast":
                return "Toast rescinded!"
        else:
            return "Toast failed for some reason"
    else:
        return "I didn't get an error but I didn't get confirmation either"


async def getCheckin(self, checkin: int, auth_token: str=None):
    """Look up a specific checkin"""

    keys = dict()
    keys["client_id"] = self.settings["client_id"]
    if auth_token:
        keys["access_token"] = auth_token
        # print("Doing an authorized lookup")
    else:
        keys["client_secret"] = self.settings["client_secret"]
    qstr = urllib.parse.urlencode(keys)
    url = ("https://api.untappd.com/v4/checkin/view/{!s}?{!s}").format(
        checkin, qstr
    )

    async with self.session.get(url) as resp:
        if resp.status == 200:
            j = await resp.json()
        else:
            # print("Lookup failed for url: "+url)
            return ("Lookup failed with {!s}").format(resp.status)

    if j["meta"]["code"] != 200:
        # print("Lookup failed for url: "+url)
        return ("Lookup failed with {!s} - {!s}").format(
            j["meta"]["code"],
            j["meta"]["error_detail"])

    user_checkin = j["response"]["checkin"]
    return await checkin_to_embed(self, user_checkin)


async def getCheckins(self, ctx, profile: str=None,
                      start: int=None, count: int=0,
                      auth_token: str=None):
    """Given some information get checkins of a user"""
    # Sanitize our inputs
    if ctx.message.server:
        guild = str(ctx.message.server.id)
    else:
        guild = 0
    embed = None
    checkinList = []
    if not profile:
        return "No profile was provided or calculated"
    if not count:
        try:
            count = self.settings[guild]["max_items_in_list"]
        except KeyError:
            count = self.settings["max_items_in_list"]

    keys = dict()
    if count:
        keys["limit"] = count
    if start:
        keys["max_id"] = start
    keys["client_id"] = self.settings["client_id"]
    if auth_token:
        keys["access_token"] = auth_token
        # print("Doing an authorized lookup")
    else:
        keys["client_secret"] = self.settings["client_secret"]
    qstr = urllib.parse.urlencode(keys)
    url = ("https://api.untappd.com/v4/user/checkins/{!s}?{!s}").format(
        profile, qstr
    )
    # print("Looking up: {!s}".format(url))
    async with self.session.get(url) as resp:
        if resp.status == 200:
            j = await resp.json()
        else:
            # print("Lookup failed for url: "+url)
            return ("Lookup failed with {!s}").format(resp.status)

    if j["meta"]["code"] != 200:
        # print("Lookup failed for url: "+url)
        return ("Lookup failed with {!s} - {!s}").format(
            j["meta"]["code"],
            j["meta"]["error_detail"]
            )

    if j["response"]["checkins"]["count"] == 1:
        embed = await checkin_to_embed(self,
                                       j["response"]["checkins"]["items"][0])
    elif j["response"]["checkins"]["count"] > 1:
        checkins = j["response"]["checkins"]["items"]
        checkinStr = checkins_to_string(self, count, checkins)
        checkinList = checkins
        embed = discord.Embed(title=profile, description=checkinStr[:2048])

    result = dict()
    result["embed"] = embed
    if checkinList:
        result["list"] = checkinList
    return result


async def searchBeer(self, query, limit=None, rating=None):
    """Given a query string and some other
    information returns an embed of results"""
    returnStr = ""
    resultStr = ""
    list_limit = limit or list_size(self, None)
    qstr = urllib.parse.urlencode({
        "q": query,
        "limit": list_limit,
        "client_id": self.settings["client_id"],
        "client_secret": self.settings["client_secret"]
        })

    url = "https://api.untappd.com/v4/search/beer?%s" % qstr
#    print(url)
    try:
        async with self.session.get(url) as resp:
            if resp.status == 200:
                j = await resp.json()
            else:
                return embedme("Beer search failed with code " +
                               str(resp.status))

            beers = []
            beer_list = []
            firstnum = 1

        # Confirm success
        if j['meta']['code'] == 200:
            returnStr = "Your search for " + j['response']['parsed_term']
            returnStr += " found "
            if j['response']['beers']['count'] == 1:
                return await lookupBeer(
                    self, j['response']['beers']['items'][0]['beer']['bid'],
                    list_size=limit)
            elif j['response']['beers']['count'] > 1:
                returnStr += str(j['response']['beers']['count']) + " beers:\n"
                beers = j['response']['beers']['items']
                for num, beer in zip(range(list_limit),
                                     beers):
                    resultStr += self.emoji[num+1] + " "
                    resultStr += str(beer['beer']['bid']) + ". ["
                    resultStr += beer['beer']['beer_name'] + "]"
                    resultStr += "(" + "https://untappd.com/beer/"
                    resultStr += str(beer['beer']['bid']) + ") "
                    brewery = ("by *[{!s}](https://untappd.com/w/"
                               "{!s}/{!s})*").format(
                                beer['brewery']['brewery_name'],
                                beer['brewery']['brewery_slug'],
                                beer['brewery']['brewery_id'])
                    resultStr += brewery + "\n"
                    beer_list.append(beer['beer']['bid'])
                    if firstnum == 1:
                        firstnum = beer['beer']['bid']

                resultStr += "Look up a beer with `findbeer "
                resultStr += str(firstnum) + "`"
            else:
                returnStr += "no beers"
                # print(json.dumps(j, indent=4))

    except (aiohttp.errors.ClientResponseError,
            aiohttp.errors.ClientRequestError,
            aiohttp.errors.ClientOSError,
            aiohttp.errors.ClientDisconnectedError,
            aiohttp.errors.ClientTimeoutError,
            aiohttp.errors.HttpProcessingError) as exc:
        return embedme("Search failed with {%s}".format(exc))
    embed = discord.Embed(title=returnStr, description=resultStr[:2048])
    result = dict()
    result["embed"] = embed
    if beer_list:
        result["beer_list"] = beer_list
    return (result)


async def profileToBeer(self, profile):
    """Takes a profile and returns the last beerid checked in"""
    qstr = urllib.parse.urlencode({
        "client_id": self.settings["client_id"],
        "client_secret": self.settings["client_secret"]
        })
    url = "https://api.untappd.com/v4/user/info/{}?{}".format(profile, qstr)
    beerid = None
    rating = None

    async with self.session.get(url) as resp:
        if resp.status == 200:
            j = await resp.json()
        elif resp.status == 500:
            return embedme("The profile '{}' doesn't exist".format(profile))
        else:
            print("Profile lookup '{!s}' failed: {}".format(url, resp.status))
            return embedme("Profile lookup for '{}' failed".format(profile))

        if j['meta']['code'] == 200:
            try:
                checkin = j['response']['user']['checkins']['items'][0]
                beerid = checkin['beer']['bid']
                if "rating_score" in checkin:
                    rating = checkin["rating_score"]
            except (KeyError, IndexError):
                return embedme("No recent checkins for {}".format(profile))

    if beerid:
        return await lookupBeer(self,
                                beerid=beerid,
                                rating=rating)
    else:
        return embedme("User '{!s}' did not have a recent beer"
                       .format(profile))


async def profileLookup(self, profile, limit=5):
    """Looks up a profile in untappd by username"""
    query = urllib.parse.quote_plus(profile)
    embed = False
    beerList = []
    api_key = "client_id={}&client_secret={}".format(
        self.settings["client_id"],
        self.settings["client_secret"])

    url = "https://api.untappd.com/v4/user/info/" + query + "?" + api_key
    # print("Profile URL: " + url) #TODO: Add debug setting

    # TODO: Honor is_private flag on private profiles.

    async with self.session.get(url) as resp:
        if resp.status == 200:
            j = await resp.json()
        elif resp.status == 404:
            return "The profile '{!s}' does not exist".format(profile)
        elif resp.status == 500:
            return "The untappd server is having an error"
        else:
            print("Failed for url: " + url)
            return "Profile query failed with code {!s}".format(resp.status)

#        print (json.dumps(j['response'],indent=4))
        if j['meta']['code'] == 200:
            (embed, beerList) = user_to_embed(self, j['response']['user'],
                                              limit)
        else:
            embed = discord.Embed(
                title="No user found",
                description="Search for " + profile + " resulted in no users")

    result = dict()
    result["embed"] = embed
    if beerList:
        result["beer_list"] = beerList
    return result


def user_to_embed(self, user, limit=5):
    """Takes the user portion of a json response and returns an embed \
and a checkin list"""
    beerList = []
    if 'checkins' in user:
        recentStr = checkins_to_string(self, limit,
                                       user['checkins']['items'])
        beerList = user['checkins']['items']
    name_str = user['user_name']
    flair_str = ""
    if user['is_supporter']:
        flair_str += self.settings["supporter_emoji"]
    if user['is_moderator']:
        flair_str += self.settings["moderator_emoji"]
    embed = discord.Embed(title=name_str,
                          description=recentStr[:2048]
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
    return (embed, beerList)


async def embed_menu(self, ctx, beer_list: list, message, timeout: int=30,
                     type: str="beer"):
    """Says the message with the embed and adds menu for reactions"""
    emoji = []
    limit = list_size(self, ctx.message.server)

    if not message:
        await self.bot.say("I didn't get a handle to an existing message.")
        return

    for num, beer in zip(range(1, limit+1), beer_list):
        emoji.append(self.emoji[num])
        await self.bot.add_reaction(message, self.emoji[num])

    react = await self.bot.wait_for_reaction(
        message=message, timeout=timeout, emoji=emoji, user=ctx.message.author)
    if react is None:
        try:
            try:
                await self.bot.clear_reactions(message)
            except discord.Forbidden:
                for e in emoji:
                    await self.bot.remove_reaction(message, e, self.bot.user)
        except discord.Forbidden:
            pass
        return None
    reacts = {v: k for k, v in self.emoji.items()}
    react = reacts[react.reaction.emoji]
    react -= 1
    if len(beer_list) > react:
        if type == "beer":
            new_embed = await lookupBeer(self, beer_list[react], list_size=1)
        elif type == "checkin":
            new_embed = await checkin_to_embed(self, beer_list[react])
        await self.bot.say(embed=new_embed)
        try:
            try:
                await self.bot.clear_reactions(message)
            except discord.Forbidden:
                for e in emoji:
                    await self.bot.remove_reaction(message, e, self.bot.user)
        except discord.Forbidden:
            pass


def checkins_to_string(self, count: int, checkins: list):
    """Takes a list of checkins and returns a string"""
    checkinStr = ""
    for num, checkin in zip(range(count), checkins):
        checkinStr += ("{!s}{!s}. [{!s}](https://untappd.com/beer/{!s})"
                       " ({!s}) by [{!s}](https://untappd.com/brewery/{!s})"
                       "{!s}({!s}) - {!s} badges\n").format(
                    self.emoji[num+1],
                    checkin["checkin_id"],
                    checkin["beer"]["beer_name"],
                    checkin["beer"]["bid"],
                    checkin["rating_score"] or "N/A",
                    checkin["brewery"]["brewery_name"],
                    checkin["brewery"]["brewery_id"],
                    self.emoji["beers"],
                    checkin["toasts"]["count"],
                    checkin["badges"]["count"]
                )
    return checkinStr


async def checkin_to_embed(self, checkin):
    """Given a checkin object return an embed of that checkin's information"""

    # Get the base beer information
    beer = await get_beer_by_id(self, checkin["beer"]["bid"])
    # titleStr = "Checkin {!s}".format(checkin["checkin_id"])
    url = ("https://untappd.com/user/{!s}/checkin/{!s}").format(
        checkin["user"]["user_name"],
        checkin["checkin_id"]
        )
    titleStr = ("{!s} was drinking a {!s} by {!s}").format(
                   checkin["user"]["first_name"],
                   checkin["beer"]["beer_name"],
                   checkin["brewery"]["brewery_name"]
               )
    checkinTS = datetime.strptime(checkin["created_at"],
                                  "%a, %d %b %Y %H:%M:%S %z")

    embed = discord.Embed(title=titleStr,
                          description=beer["beer_description"][:2048],
                          url=url, timestamp=checkinTS)
    if checkin["media"]["count"] >= 1:
        embed.set_thumbnail(
            url=checkin["media"]["items"][0]["photo"]["photo_img_md"]
            )
    # Add fields of interest
    if isinstance(checkin["venue"], dict):
        venueStr = "[{!s}](https://untappd.com/venue/{!s})".format(
            checkin["venue"]["venue_name"],
            checkin["venue"]["venue_id"]
        )
        embed.add_field(name="Venue", value=venueStr)
    titleStr = "Rating"
    if checkin["rating_score"]:
        titleStr += " - {!s}".format(checkin["rating_score"])
    ratingStr = "**{!s}** Average ({!s})".format(
        round(beer['rating_score'], 2),
        human_number(beer['rating_count'])
    )
    embed.add_field(name=titleStr, value=ratingStr)
    embed.add_field(name="Style", value=beer["beer_style"])
    embed.add_field(name="ABV", value=(beer["beer_abv"] or "N/A"))
    embed.add_field(name="IBU", value=(beer["beer_ibu"] or "N/A"))
    checkinStr = "{!s} checkins from {!s} users".format(
        human_number(beer["stats"]["total_count"]),
        human_number(beer["stats"]["total_user_count"])
    )
    embed.add_field(name="Checkins", value=checkinStr)
    if "collaborations_with" in beer:
        collabStr = ""
        collabs = beer['collaborations_with']['items']
        for collab in collabs:
            collabStr += "[" + collab['brewery']['brewery_name']
            collabStr += "](https://untappd.com/brewery/"
            collabStr += str(collab['brewery']['brewery_id']) + ")\n"
        embed.add_field(name="Collaboration with", value=collabStr)
    if checkin["checkin_comment"]:
        embed.add_field(name="Comment",
                        value=checkin["checkin_comment"][:1024])
    if (checkin["comments"]["count"] + checkin["toasts"]["count"]) > 0:
        newValue = "{!s}({!s}){!s}({!s})".format(
                self.emoji["comments"],
                checkin["comments"]["count"],
                self.emoji["beers"],
                checkin["toasts"]["count"]
        )
        embed.add_field(name="Flags", value=newValue)
    if checkin["badges"]["count"] > 0:
        badgeStr = ""
        for badge in checkin["badges"]["items"]:
            badgeStr += "{!s}\n".format(badge["badge_name"])
        embed.add_field(name="Badges", value=badgeStr[:1024])

    embed.set_footer(text="Checkin {!s}".format(checkin["checkin_id"]))
    return embed


def list_size(self, server=None):
    """Returns a list size if configured for the server or the default size"""
    size = self.settings["max_items_in_list"]
    if server:
        try:
            size = self.settings[server.id]["max_items_in_list"]
        except KeyError:
            size = self.settings["max_items_in_list"]
    return size


def embedme(errorStr, title="Error encountered"):
    """Returns an embed object with the error string provided"""
    embed = discord.Embed(title=title,
                          description=errorStr[:2048])
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
