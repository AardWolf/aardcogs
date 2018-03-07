import discord
from discord.ext import commands
from cogs.utils import checks
import aiohttp
from .utils.dataIO import dataIO
import os
import urllib.parse
from __main__ import send_cmd_help

# Beer: https://untappd.com/beer/<bid>
# Brewery: https://untappd.com/brewery/<bid>


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
            "beer": "🍺"
            }

    @commands.group(no_pm=False, invoke_without_command=False,
                    pass_context=True)
    async def untappd(self, ctx):
        """Explicit Untappd things"""
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)

    @untappd.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def list_size(self, new_size: int):
        """The length of lists of results"""
        try:
            new_size += 0
            # The true maximum size is 10 because there's that many emoji
            if new_size > 10:
                new_size = 10
                await self.bot.say("Reducing the maximum size to " +
                                   "10 due to emoji constraints")
            self.settings["max_items_in_list"] = new_size
            dataIO.save_json("data/untappd/settings.json", self.settings)
            await self.bot.say("Maximum list size is now " +
                               str(self.settings["max_items_in_list"]))
        except TypeError:
            await self.bot.say("The new size isn't an integer, keeping " +
                               str(self.settings["max_items_in_list"]))

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
        if (ctx.message.server):
            server = str(ctx.message.server)
            if server not in self.settings:
                self.settings[server] = {}
            author = str(ctx.message.author.id)
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

    @commands.command(pass_context=True, no_pm=False)
    async def findbeer(self, ctx, *keywords):
        """Search Untappd.com using the API"""
        """A search uses characters, a lookup uses numbers"""
        embed = False
        beer_list = []
        resultStr = ""

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
            embed = await lookupBeer(self, keywords)
            # await self.bot.say( embed=embed)
        else:
            results = await searchBeer(self, keywords)
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
        results = await searchBeer(self, keywords, limit=1)
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
        guild = str(ctx.message.server)

        if not check_credentials(self.settings):
            await self.bot.say("The owner has not set the API information " +
                               "and should use the `untappd_apikey` command")
            return

#        await self.bot.say("I got a user " + profile)
        if ctx.message.mentions:
            if ctx.message.mentions[0].nick:
                profile = ctx.message.mentions[0].nick
            else:
                profile = ctx.message.mentions[0].name

        if not profile:
            try:
                profile = self.settings[guild][author.id]["nick"]
            except KeyError:
                profile = None
        if not profile:
            profile = author.display_name
        await self.bot.send_typing(ctx.message.channel)
        results = await profileToBeer(self, profile)
        if (isinstance(results, dict)) and ("embed" in results):
            embed = results["embed"]
        else:
            embed = results
        await self.bot.say(resultStr, embed=embed)

    @commands.command(pass_context=True, no_pm=False)
    async def profile(self, ctx, profile: str=None):
        """Search for a user's information by providing their profile name,
        discord mentions OK"""

        embed = False
        beer_list = []
        resultStr = ""
        author = ctx.message.author
        guild = str(ctx.message.server)

        if not check_credentials(self.settings):
            await self.bot.say("The owner has not set the API information " +
                               "and should use the `untappd_apikey` command")
            return

#        await self.bot.say("I got a user " + profile)
        if ctx.message.mentions:
            if ctx.message.mentions[0].nick:
                profile = ctx.message.mentions[0].nick
            else:
                profile = ctx.message.mentions[0].name

        if not profile:
            try:
                profile = self.settings[guild][author.id]["nick"]
            except KeyError:
                profile = None
        if not profile:
            profile = author.display_name
        await self.bot.send_typing(ctx.message.channel)
        results = await profileLookup(self, profile)
        if (isinstance(results, dict)) and ("embed" in results):
            embed = results["embed"]
            if "beer_list" in results:
                beer_list = results["beer_list"]
        else:
            embed = results
        message = await self.bot.say(resultStr, embed=embed)
        if len(beer_list) > 1:
            await embed_menu(self, ctx, beer_list, message, 30)

    @commands.command(pass_context=True, no_pm=False)
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


async def lookupBeer(self, beerid, rating=None):
    """Look up a beer by id"""

    api_key = "client_id=" + self.settings["client_id"] + "&client_secret="
    api_key += self.settings["client_secret"]
    url = "https://api.untappd.com/v4/beer/info/" + str(beerid) + "?" + api_key
    async with self.session.get(url) as resp:
        if resp.status == 200:
            j = await resp.json()
        else:
            return embedme("Query failed with code " + str(resp.status))

        if j['meta']['code'] == 200:
            beer = j['response']['beer']
            beer_url = "https://untappd.com/b/{}/{!s}".format(
                beer['beer_slug'],
                beer['bid'])
            brewery_url = "https://untappd.com/w/{!s}/{!s}".format(
                beer['brewery']['brewery_slug'],
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

            if "collaborations_with" in j['response']['beer']:
                collabStr = ""
                for num, collab in zip(range(
                        self.settings["max_items_in_list"]),
                        j['response']['beer']['collaborations_with']['items']
                        ):
                    collabStr += "[" + collab['brewery']['brewery_name']
                    collabStr += "](https://untappd.com/brewery/"
                    collabStr += str(collab['brewery']['brewery_id']) + ")\n"
                embed.add_field(name="Collaboration with", value=collabStr)
            return embed

    return embedme("A problem")


async def searchBeer(self, query, limit=None, rating=None):
    returnStr = ""
    resultStr = ""
    qstr = urllib.parse.urlencode({
        "q": query,
        "limit": limit or self.settings["max_items_in_list"],
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
                    self, j['response']['beers']['items'][0]['beer']['bid'])
            elif j['response']['beers']['count'] > 1:
                returnStr += str(j['response']['beers']['count']) + " beers:\n"
                beers = j['response']['beers']['items']
                for num, beer in zip(range(self.settings["max_items_in_list"]),
                                     beers):
                    resultStr += self.emoji[num+1] + " "
                    resultStr += str(beer['beer']['bid']) + ". ["
                    resultStr += beer['beer']['beer_name'] + "]"
                    resultStr += "(" + "https://untappd.com/b/"
                    resultStr += beer['beer']['beer_slug'] + "/"
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
            except KeyError:
                return embedme("No recent checkins for {}".format(profile))

    if beerid:
        return await lookupBeer(self,
                                beerid=beerid,
                                rating=rating)
    else:
        return embedme("User '{!s}' did not have a recent beer"
                       .format(profile))


async def profileLookup(self, profile):
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
        elif resp.status == 500:
            return embedme("The profile '" + profile + "' does not exist")
        else:
            print("Failed for url: " + url)
            return embedme("Profile query failed with code " +
                           str(resp.status))

#        print (json.dumps(j['response'],indent=4))
        if j['meta']['code'] == 200:
            recentStr = ""
            # print(url)
            if 'checkins' in j['response']['user']:
                for num, checkin in zip(
                        range(self.settings["max_items_in_list"]),
                        j['response']['user']['checkins']['items']):
                    recentStr += str(self.emoji[num+1]) + " "
                    recentStr += str(checkin['beer']['bid']) + ". ["
                    recentStr += checkin['beer']['beer_name']
                    recentStr += "](https://untappd.com/beer/"
                    recentStr += str(checkin['beer']['bid']) + ")"
                    if "rating_score" in checkin:
                        if checkin['rating_score']:
                            recentStr += " (" + str(checkin['rating_score'])
                            recentStr += ")"

                    recentStr += " by *[" + checkin['brewery']['brewery_name']
                    recentStr += "](https://untappd.com/brewery/"
                    recentStr += str(checkin['brewery']['brewery_id']) + ")*"
                    if (("toasts" in checkin) and
                            (checkin["toasts"]["count"] > 0)):
                        recentStr += " " + self.emoji["beers"] + " ("
                        recentStr += str(checkin["toasts"]["total_count"])
                        recentStr += ")"

                    recentStr += "\n"
                    beerList.append(checkin['beer']['bid'])
            name_str = j['response']['user']['user_name']
            flair_str = ""
            if j['response']['user']['is_supporter']:
                flair_str += self.settings["supporter_emoji"]
            if j['response']['user']['is_moderator']:
                flair_str += self.settings["moderator_emoji"]
            embed = discord.Embed(title=name_str,
                                  description=recentStr[:2048]
                                  or "No recent beers visible",
                                  url=j['response']['user']['untappd_url'])
            embed.add_field(
                name="Checkins",
                value=str(j['response']['user']['stats']['total_checkins']),
                inline=True)
            embed.add_field(
                name="Uniques",
                value=str(j['response']['user']['stats']['total_beers']),
                inline=True)
            embed.add_field(
                name="Badges",
                value=str(j['response']['user']['stats']['total_badges']),
                inline=True)
            if (("bio" in j['response']['user'])
                    and (j['response']['user']['bio'])):
                embed.add_field(name="Bio",
                                value=j['response']['user']['bio'][:1024],
                                inline=False)
            if j['response']['user']['location']:
                embed.add_field(name="Location",
                                value=j['response']['user']['location'],
                                inline=True)
            if flair_str:
                embed.add_field(name="Flair",
                                value=flair_str,
                                inline=True)
            embed.set_thumbnail(url=j['response']['user']['user_avatar'])
        else:
            embed = discord.Embed(
                title="No user found",
                description="Search for " + profile + " resulted in no users")

    result = dict()
    result["embed"] = embed
    if beerList:
        result["beer_list"] = beerList
    return result


async def embed_menu(self, ctx, beer_list: list,
                     message,
                     timeout: int=30):
    """Says the message with the embed and adds menu for reactions"""
    emoji = []

    if not message:
        await self.bot.say("I didn't get a handle to an existing message.")
        return

    for num, beer in zip(
            range(1, self.settings["max_items_in_list"]+1), beer_list):
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
        new_embed = await lookupBeer(self, beer_list[react])
        await self.bot.say(embed=new_embed)
        try:
            try:
                await self.bot.clear_reactions(message)
            except discord.Forbidden:
                for e in emoji:
                    await self.bot.remove_reaction(message, e, self.bot.user)
        except discord.Forbidden:
            pass


def embedme(errorStr):
    """Returns an embed object with the error string provided"""
    embed = discord.Embed(title="Error encountered",
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
