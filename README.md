# aardcogs
Cogs for Discord-Red

## Untappd 

The first cog, it interacts with Untappd through its API. If you'd like to use it you'll need an Untappd API key (https://untappd.com/api/dashboard). By default it will use https://aardwolf.github.io/tokenrevealer.html as the callback URL. I encourage you to take a look at that and decide if it's safe enough for your purposes. It's hard-coded for now but easy enough to change.

The cog itself is used to interact with simple untappd calls - look up beers, display checkins, and toast checkins.

```
Commands:
  checkin     Returns a single checkin by number
  checkins    Returns a list of checkins
  findbeer    Search Untappd.com for a beer.
  findbeer1   Gives beer details for the first beer that matches
  haveihad    Lookup a beer to see if you've had it
  lastbeer    Displays details for the last beer a person had
  utprofile   Search for a user's information by providing their profile name,
  toast       Toasts a checkin by number, if you're friends
  untappd     Explicit Untappd things
  unwishlist  Requires that you've authorized the bot.
  wishlist    Requires that you've authorized the bot.
```
You'll also see drinking project commands but I have not made the underlying spreadsheet generally available.

## Traderep

Built out of a request on the [Untappd Discord server](http://discord.me/untappd) this cog adds very simple trade management. All commands are in the traderep command structure because many common words are used. Initially designed for beer trading it's pretty simple so could work with any sort of trading with people who were anonymous once.

```
Commands:
  cancel Stops a trade but doesn't break it
  derep  Dings a trading partner for messing up a trade
  rep    Reps a trading partner for a trade
  report Generates a report on a user. Accepts names, mentions, and IDs
  start  Starts a trade between the person executing the command and the pers...
```

A database will be created in `data/traderep` and it's a really good idea to back this up if you want to be able to restore it.

All commands that make a change to the database are logged within it with the idea that you can work backwards in the case of shenanigans. 
