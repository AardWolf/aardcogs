import discord
from discord.ext import commands
from cogs.utils import checks
import aiohttp
from .utils.dataIO import dataIO
import os
#import asyncio
import urllib.parse
import certifi
import json
from __main__ import send_cmd_help

#Beer: https://untappd.com/beer/<bid>
#Brewery: https://untappd.com/brewery/<bid>

class Untappd():
    """Untappd cog that lets the bot look up beer information from untappd.com!"""

    def __init__(self, bot):
        self.bot = bot
        self.settings = dataIO.load_json("data/untappd/settings.json")
        if "max_items_in_list" not in self.settings:
            sel.settings["max_items_in_list"] = 5
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
            "beers": ":beers:",
            "beer": ":beer:"
            }

    @commands.group(no_pm=False, invoke_without_command=False, pass_context=True)
    async def untappd(self, ctx):
        """Explicit Untappd things"""
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)

    @untappd.command()
    @checks.mod_or_permissions(manage_messages=True)
    async def list_size(self, new_size: int):
        #print ("Trying to set the list size, received " + str(new_size))
        try:
            new_size += 0
            #The true maximum size is 10 because there's that many emoji
            if new_size > 10:
                new_size = 10
                await selt.bot.say("Reducing the maximum size to 10 due to emoji constraints")
            self.settings["max_items_in_list"] = new_size
            dataIO.save_json("data/untappd/settings.json", self.settings)
            await self.bot.say("Maximum list size is now " + str(self.settings["max_items_in_list"]))
        except TypeError:
            await self.bot.say("The new size doesn't look like an integer, keeping " + int(self.settings["max_items_in_list"]))

    @commands.command(pass_context=True, no_pm=True)
    async def findbeer(self, ctx, *keywords):
        """Search Untappd.com using the API"""
        """A search uses characters, a lookup uses numbers"""
        lookup = False
        embed = False
        beer_list = []
        resultStr = ""

        if not check_credentials(self.settings):
            await self.bot.say("The owner has not set the API information and should use the `untappd_apikey` command")
            return

        if keywords:
            keywords = "+".join(keywords)
        else:
            await self.bot.send_cmd_help(ctx)
            return

        await self.bot.send_typing(ctx.message.channel)
        if keywords.isdigit():
            lookup = True
            embed = await lookupBeer(self,keywords)
            #await self.bot.say( embed=embed)
        else:
            results = await searchBeer(self,keywords)
            if type(results) == type(dict()):
                embed = results["embed"]
                if "beer_list" in results:
                    beer_list = results["beer_list"]
            else:
                embed = results
            #await self.bot.say(resultStr, embed=embed)

        if embed:
            message = await self.bot.say(resultStr, embed=embed)
        else:
            message = await self.bot.say(resultStr)

        if (len(beer_list) > 1):
            await embed_menu(self, ctx, beer_list, message, 30)


    @commands.command(pass_context=True, no_pm=True)
    async def profile(self, ctx, profile: str):
        "Search for a user's information by providing their profile name, discord mentions OK"

        embed = False
        beer_list = []
        resultStr = ""

        if not check_credentials(self.settings):
            await self.bot.say("The owner has not set the API information and should use the `untappd_apikey` command")
            return

#        await self.bot.say("I got a user " + profile)
        if ctx.message.mentions:
            if ctx.message.mentions[0].nick:
                profile = ctx.message.mentions[0].nick
            else:
                profile = ctx.message.mentions[0].name

        await self.bot.send_typing(ctx.message.channel)
        results = await profileLookup(self,profile)
        embed = results["embed"]
        if "beer_list" in results:
            beer_list = results["beer_list"]
        message = await self.bot.say(resultStr, embed=embed)
        if len(beer_list) > 1:
            await embed_menu(self, ctx, beer_list, message, 30)

    @commands.command(pass_context=True, no_pm=False)
    @checks.is_owner()
    async def untappd_apikey(self, ctx, *keywords):
        """Sets the id and secret that you got from applying for an untappd api"""
        if len(keywords) == 2:
            self.settings["client_id"] = keywords[0]
            self.settings["client_secret"] = keywords[1]
            self.settings["CONFIG"] = True
            dataIO.save_json("data/untappd/settings.json", self.settings)
            await self.bot.say("API set")
        else:
            await self.bot.say("I am expecting two words, the id and the secret only")


def check_folders():
    if not os.path.exists("data/untappd"):
        print ("Creating untappd folder")
        os.makedirs("data/untappd")

def check_files():
    f = "data/untappd/settings.json"
    data = {"CONFIG" : False, "max_items_in_list": 5}
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
            dataIO.save_json(f,temp_settings)

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

async def lookupBeer(self,beerid):
    returnStr = ""

    api_key = "client_id=" + self.settings["client_id"] + "&client_secret=" + self.settings["client_secret"]
    url = "https://api.untappd.com/v4/beer/info/" + str(beerid) + "?" + api_key
    async with self.session.get(url) as resp:
        if resp.status == 200:
            j = await resp.json()
        else:
            return embedme("Query failed with code " + str(resp.status))

        if j['meta']['code'] == 200:
            beer = j['response']['beer']
            beer_url = "https://untappd.com/b/" + beer['beer_slug'] + "/" + str(beer['bid'])
            brewery_url = "https://untappd.com/w/" + beer['brewery']['brewery_slug'] + "/" + str(beer['brewery']['brewery_id'])
            beer_title = beer['beer_name']
            embed = discord.Embed(title=beer_title, description=beer['beer_description'][:2048], url=beer_url)
            embed.set_author(name=beer['brewery']['brewery_name'], url=brewery_url, icon_url=beer['brewery']['brewery_label'])
            embed.add_field(name="Style", value=beer['beer_style'], inline=True)
            rating_str = str(round(beer['rating_score'],2)) + " Caps"
            rating_str += " (" + human_number(beer['rating_count']) + ")"
            embed.add_field(name="Rating", value=rating_str, inline=True)
            embed.add_field(name="ABV", value=beer['beer_abv'], inline=True)
            embed.add_field(name="IBU", value=beer['beer_ibu'], inline=True)
            embed.set_thumbnail(url=beer['beer_label'])

            if "collaborations_with" in j['response']['beer']:
                collabStr = ""
                for num,collab in zip(range(self.settings["max_items_in_list"]),
                                      j['response']['beer']['collaborations_with']['items']):
                    collabStr += "[" + collab['brewery']['brewery_name'] + "](https://untappd.com/brewery/"
                    collabStr += str(collab['brewery']['brewery_id']) + ")\n"
                embed.add_field(name="Collaboration with", value=collabStr)
            return embed

    return embedme("A problem")

async def searchBeer(self,query):
    returnStr = ""
    resultStr = ""
    qstr = urllib.parse.urlencode({'q': query})
    api_key = "client_id=" + self.settings["client_id"] + "&client_secret=" + self.settings["client_secret"]

    url = "https://api.untappd.com/v4/search/beer?" + qstr + "&" + api_key
#    print(url)
    async with self.session.get(url) as resp:
        if resp.status == 200:
            j = await resp.json()
        else:
            return embedme("Beer search failed with code " + str(resp.status))

        beers = []
        beer_list = []
        firstnum=1

        # Confirm success
        if j['meta']['code'] == 200:
            returnStr = "Your search for " + j['response']['parsed_term'] + " found "
            if j['response']['beers']['count'] == 1:
                return await lookupBeer(self,j['response']['beers']['items'][0]['beer']['bid'])
            elif j['response']['beers']['count'] > 1:
                returnStr += str(j['response']['beers']['count']) + " beers:\n"
                beers = j['response']['beers']['items']
                for num,beer in zip(range(self.settings["max_items_in_list"]),beers):
                    resultStr += str(beer['beer']['bid']) + ". [" + beer['beer']['beer_name'] + "]"
                    resultStr += "(" + "https://untappd.com/b/" + beer['beer']['beer_slug'] + "/" + str(beer['beer']['bid']) + ") "
                    resultStr += " (" + str(human_number(int(beer['checkin_count']))) + " check ins) "
                    resultStr += "brewed by *" + beer['brewery']['brewery_name'] + "*\n"
                    beer_list.append(beer['beer']['bid'])
                    if firstnum == 1:
                        firstnum = beer['beer']['bid']

                resultStr += "Look up a beer with `findbeer " + str(firstnum) + "`"
            else:
                returnStr += "no beers"
                print(json.dumps(j, indent=4))

    embed = discord.Embed(title=returnStr, description=resultStr[:2048])
    result = dict()
    result["embed"] = embed
    if beer_list:
        result["beer_list"] = beer_list
    return (result)

async def profileLookup(self,profile):
    returnStr = ""
    query = urllib.parse.quote_plus(profile)
    embed = False
    beerList = []
    api_key = "client_id=" + self.settings["client_id"] + "&client_secret=" + self.settings["client_secret"]

    url = "https://api.untappd.com/v4/user/info/" + query + "?" + api_key
    #print("Profile URL: " + url) #TODO: Add debug setting

    #TODO: Honor is_private flag on private profiles.

    async with self.session.get(url) as resp:
        if resp.status == 200:
            j = await resp.json()
        elif resp.status == 500:
            return embedme("The profile '" + profile + "' does not exist or the lookup failed in another way")
        else:
            print ("Failed for url: " + url)
            return embedme("Profile query failed with code " + str(resp.status))

#        print (json.dumps(j['response'],indent=4))
        if j['meta']['code'] == 200:
            recentStr = ""
            if 'checkins' in j['response']['user']:
                for num, checkin in zip(range(self.settings["max_items_in_list"]),
                                        j['response']['user']['checkins']['items']):
                    recentStr += str(checkin['beer']['bid']) + ". [" + checkin['beer']['beer_name']
                    recentStr += "](https://untappd.com/beer/" + str(checkin['beer']['bid']) + ")"
                    if "rating_score" in checkin:
                        if checkin['rating_score']:
                            recentStr += " (" + str(checkin['rating_score']) + ")"

                    recentStr += " by *[" + checkin['brewery']['brewery_name']
                    recentStr += "](https://untappd.com/brewery/" + str(checkin['brewery']['brewery_id']) + ")*"
                    if ("toasts" in checkin) and (checkin["toasts"]["count"] > 0):
                        recentStr += " " + self.emoji["beers"] + " (" + str(checkin["toasts"]["total_count"]) + ")"

                    recentStr += "\n"
                    beerList.append(checkin['beer']['bid'])
                embed.add_field(name="Recent Activity", value=recentStr[:1024] or "No Activity", inline=False)
            embed = discord.Embed(title=j['response']['user']['user_name'],
                                  description=recentStr[:2048] or "No recent beers visible",
                                  url=j['response']['user']['untappd_url'])
            embed.add_field(name="Checkins", value=str(j['response']['user']['stats']['total_checkins']), inline=True )
            embed.add_field(name="Uniques", value=str(j['response']['user']['stats']['total_beers']), inline=True )
            embed.add_field(name="Badges", value=str(j['response']['user']['stats']['total_badges']), inline=True)
            embed.add_field(name="Bio", value=j['response']['user']['bio'][:1024] or "Too boring for a bio")
            if j['response']['user']['location']:
                embed.add_field(name="Location", value=j['response']['user']['location'], inline=True )
            embed.set_thumbnail(url=j['response']['user']['user_avatar'])
        else:
            embed = discord.Embed(title="No user found", description="Search for " + profile + " resulted in no users")

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
        await self.bot.say("I didn't get a handle to an existing message. Help!")
        return

    for num, beer in zip(range(1,self.settings["max_items_in_list"]+1),beer_list):
        emoji.append(self.emoji[num])
        await self.bot.add_reaction(message,self.emoji[num])

    react = await self.bot.wait_for_reaction(message=message, timeout=timeout, emoji=emoji, user=ctx.message.author)
    if react is None:
        try:
            try:
                await self.bot.clear_reactions(message)
            except:
                for e in emoji:
                    await self.bot.remove_reaction(message, e, self.bot.user)
        except:
            pass
        return None
    reacts = {v: k for k, v in self.emoji.items()}
    react = reacts[react.reaction.emoji]
    react -= 1
    if len(beer_list) > react:
#        print("React " + str(react+1) + " maps to beer " + str(beer_list[react]))
        new_embed = await lookupBeer(self, beer_list[react])
        await self.bot.say(embed=new_embed)
        try:
            try:
                await self.bot.clear_reactions(message)
            except:
                for e in emoji:
                    await self.bot.remove_reaction(message, e, self.bot.user)
        except:
            pass





def embedme(errorStr):
    """Returns an embed object with the error string provided"""
    embed = discord.Embed(title="Error encountered", description=errorStr[:2048])
    return embed

def human_number(number):
    # Billion, Million, K, end
    number = int(number)
    if number > 1000000000:
        return str(round(number / 1000000000,1)) + "B"
    elif number > 1000000:
        return str(round(number / 1000000, 1)) + "M"
    elif number > 1000:
        return str(round(number / 1000, 1)) + "K"
    else:
        return str(number)
