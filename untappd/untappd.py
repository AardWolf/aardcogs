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

#Beer: https://untappd.com/beer/<bid>
#Brewery: https://untappd.com/brewery/<bid>

class Untappd():
    """Untappd cog that lets the bot look up beer information from untappd.com!"""

    def __init__(self, bot):
        self.bot = bot
        self.settings = dataIO.load_json("data/untappd/settings.json")

    @commands.command(pass_context=True, no_pm=True)
    async def findbeer(self, ctx, *keywords):
        """Search Untappd.com using the API"""
        """A search uses characters, a lookup uses numbers"""
        lookup = False
        embed = False
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
            embed = await lookupBeer(self.settings,keywords)
            #await self.bot.say( embed=embed)
        else:
            embed = await searchBeer(self.settings,keywords)
            #await self.bot.say(resultStr, embed=embed)

        if embed:
            await self.bot.say(resultStr, embed=embed)
        else:
            await self.bot.say(resultStr)

    @commands.command(pass_context=True, no_pm=True)
    async def profile(self, ctx, profile: str):
        "Search for a user's information by providing their profile name, discord mentions OK"

        embed = False
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
        embed = await profileLookup(self.settings,profile)
        await self.bot.say(resultStr, embed=embed)

    @commands.command(pass_context=True, no_pm=False)
    @checks.is_owner()
    async def untappd_apikey(self, ctx, *keywords):
        """Sets the id and secret that you got from applying for an untappd api"""
        if len(keywords) == 2:
            self.settings["client_id"] = keywords[0]
            self.settings["client_secret"] = keywords[1]
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
    data = {"CONFIG" : False}
    if not dataIO.is_valid_json(f):
        dataIO.save_json(f, data)

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

async def lookupBeer(settings,beerid):
    returnStr = ""

    api_key = "client_id=" + settings["client_id"] + "&client_secret=" + settings["client_secret"]
    url = "https://api.untappd.com/v4/beer/info/" + str(beerid) + "?" + api_key
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
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
                return embed

    return embedme("A problem")

async def searchBeer(settings,query):
    returnStr = ""
    resultStr = ""
    qstr = urllib.parse.urlencode({'q': query})
    api_key = "client_id=" + settings["client_id"] + "&client_secret=" + settings["client_secret"]

    url = "https://api.untappd.com/v4/search/beer?" + qstr + "&" + api_key
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                j = await resp.json()
            else:
                return embedme("Beer search failed with code " + str(resp.status))

            beers = []
            firstnum=1

            # Confirm success
            if j['meta']['code'] == 200:
                returnStr = "Your search for " + j['response']['parsed_term'] + " found "
                if j['response']['beers']['count'] == 1:
                    return await lookupBeer(settings,j['response']['beers']['items'][0]['beer']['bid'])
                elif j['response']['beers']['count'] > 1:
                    returnStr += str(j['response']['beers']['count']) + " beers:\n"
                    i = 0
                    beers = j['response']['beers']['items']
                    for beer in beers:
                        if (i >= j['response']['beers']['count']) or (i >= 5):
                            break

                        resultStr += str(beer['beer']['bid']) + ". [" + beer['beer']['beer_name'] + "]"
                        resultStr += "(" + "https://untappd.com/b/" + beer['beer']['beer_slug'] + "/" + str(beer['beer']['bid']) + ") "
                        resultStr += " (" + str(human_number(int(beer['checkin_count']))) + " check ins) "
                        resultStr += "brewed by *" + beer['brewery']['brewery_name'] + "*\n"
                        if firstnum == 1:
                            firstnum = beer['beer']['bid']
                        i += 1

                    resultStr += "Look up a beer with `findbeer " + str(firstnum) + "`"
                else:
                    returnStr += "no beers"
                    print(json.dumps(j, indent=4))

    embed = discord.Embed(title=returnStr, description=resultStr[:2048])
    return embed

async def profileLookup(settings,profile):
    returnStr = ""
    query = urllib.parse.quote_plus(profile)
    embed = False
    api_key = "client_id=" + settings["client_id"] + "&client_secret=" + settings["client_secret"]

    url = "https://api.untappd.com/v4/user/info/" + query + "?" + api_key

    #TODO: Honor is_private flag on private profiles.

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                j = await resp.json()
            elif resp.status == 500:
                return embedme("The profile '" + profile + "' does not exist or the lookup failed in another way")
            else:
                print ("Failed for url: " + url)
                return embedme("Profile query failed with code " + str(resp.status))

#        print (json.dumps(j['response'],indent=4))
            if j['meta']['code'] == 200:
                embed = discord.Embed(title=j['response']['user']['user_name'], description=j['response']['user']['bio'][:2048], url=j['response']['user']['untappd_url'])
                embed.add_field(name="Checkins", value=str(j['response']['user']['stats']['total_checkins']), inline=True )
                embed.add_field(name="Uniques", value=str(j['response']['user']['stats']['total_beers']), inline=True )
                embed.add_field(name="Badges", value=str(j['response']['user']['stats']['total_badges']), inline=True)
                if j['response']['user']['location']:
                    embed.add_field(name="Location", value=j['response']['user']['location'], inline=True )
                recentStr = ""
                if 'recent_brews' in j['response']['user']:
                    for checkin in j['response']['user']['recent_brews']['items']:
                        recentStr += str(checkin['beer']['bid']) + ". " + checkin['beer']['beer_name']
                        if checkin['beer']['auth_rating']:
                            recentStr += " (" + str(checkin['beer']['auth_rating']) + ")"

                        recentStr += " brewed by *" + checkin['brewery']['brewery_name'] + "*\n"
                    embed.add_field(name="Recent Activity", value=recentStr[:1024], inline=False)
                embed.set_thumbnail(url=j['response']['user']['user_avatar'])
            else:
                embed = discord.Embed(title="No user found", description="Search for " + profile + " resulted in no users")

            return embed

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
