import discord
from discord.ext import commands
from cogs.utils import checks
from __main__ import send_cmd_help
import sqlite3
import os

db_version = 1.0

"""
!traderep start @person -- Signifies an agreement has been made between the person mentioned and the person running
        the command. Creates an open trade which will have a number to reference.
!traderep done <#> -- Signifies a trade is complete but does nothing for reputation.
!traderep rep <#> @person -- Adds rep to the mentioned person from the person running the command. Requires a trade be
        done (or closes it)
!traderep derep <#> @person <reason> -- Doesn't rep the person, maybe gives a negative rep, but requires a reason.
!traderep report [@person] -- With no argument reports for yourself. Mention a person (requires a mention so they know
        you're looking) generates a report (in PM?) for that person of their rep, any derep reasons 
        (within time period?), number of current open trades, and trading partners (not mentions, most recent 5) 
        in case you want to research.
!trade cancel <#> -- cancels a trade that hasn't been closed yet.
"""


class Traderep:
    """Cog to manage trade reputation amongst Discordians"""

    def __init__(self, bot):
        self.bot = bot
        self.connection = sqlite3.connect("data/traderep/traderep.db")
        self.connection.isolation_level = None

    @commands.group(no_pm=False, invoke_without_command=False,
                    pass_context=True)
    async def traderep(self, ctx):
        """Trade Reputation commands"""
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)

    @traderep.command(name="start", pass_context=True, no_pm=True)
    async def trade_start(self, ctx, partner: discord.Member):
        """Starts a trade between the person executing the command and the person mentioned"""
        # TODO: Simple check to make sure trade between partners doesn't already exist
        await self.bot.send_typing(ctx.message.channel)
        if partner.id == ctx.message.author.id:
            await self.bot.say("You can't trade with yourself, that's a 0-sum game!")
            return
        cur = self.connection.cursor()
        cur.execute("SELECT count(*) from tradeperson tp join trade t on t.tradenum = tp.tradenum "
                    "WHERE tp.person = ? and tp.partner = ? and t.status is null", (ctx.message.author.id, partner.id))
        counts = cur.fetchone()
        if counts[0] >= 1:
            await self.bot.say("You already have a trade open with {}".format(partner.display_name))
            return
        try:
            cur.execute("INSERT INTO trade(initiator, start_time) values ({}, 'now')"
                        .format(ctx.message.author.id))
        except sqlite3.OperationalError as e:
            await self.bot.say("There's a problem right now: {}".format(e))
            return
        trade_num = cur.lastrowid
        if trade_num:
            try:
                cur.execute("INSERT INTO tradeperson (tradenum, person, partner) values (?, ?, ?)",
                            (trade_num, partner.id, ctx.message.author.id))
                cur.execute("INSERT INTO tradeperson (tradenum, person, partner) values (?, ?, ?)",
                            (trade_num, ctx.message.author.id, partner.id))
                cur.execute("INSERT INTO tradelog (logtime, who, tradenum, what) values ('now', ?, ?, ?)",
                            (ctx.message.author.id, trade_num, "Author initiated trade with {}".format(
                                partner.id
                            )))
            except sqlite3.OperationalError as e:
                await self.bot.say("There's a problem right now: {}".format(e))
                return
            await self.bot.say("Trade between {} and {} initiated as trade id: **{}**".format(
                partner.display_name, ctx.message.author.display_name, trade_num))
        else:
            await self.bot.say("Something very bad happened and I didn't get a trade number, try again?")

    @traderep.command(name="done", aliases=["complete", "finish"], pass_context=True, no_pm=True)
    async def trade_complete(self, ctx, trade_num: int):
        """Marks a trade as done"""
        if not trade_num:
            await self.bot.say("You must provide a trade number and it can't be 0")
            return
        cur = self.connection.cursor()
        cur.execute("SELECT partner from tradeperson tp join trade t on t.tradenum = tp.tradenum "
                    "where tp.tradenum = ? and tp.person = ? and t.status is null",
                    (trade_num, ctx.message.author.id))
        row = cur.fetchone()
        if row:
            if row[0]:
                cur.execute("update trade set end_time = 'now', status=1 where tradenum = {}".format(
                    trade_num
                ))
                if cur.rowcount == 1:
                    partner = await self.bot.get_user_info(row[0])
                    if partner:
                        await self.bot.say("Trade {} between {} and {} was closed and ratings can be assigned".format(
                            trade_num, ctx.message.author.display_name, partner.display_name
                        ))
                    else:
                        await self.bot.say("Trade {} between you and {} was closed but I could not find a name "
                                           "for that person".format(trade_num, row[0]))
                    cur.execute("INSERT INTO tradelog (logtime, who, tradenum, what) values ('now', ?, ?, ?)",
                                (ctx.message.author.id, trade_num, "Author stopped trade {} with {}".format(
                                    trade_num, row[0]
                                )))
                else:
                    await self.bot.say("Either trade {} didn't involve you or it isn't open".format(trade_num))
            else:
                await self.bot.say("Either trade {} didn't involve you or it isn't open".format(trade_num))
        else:
            await self.bot.say("Either trade {} didn't involve you or it isn't open".format(trade_num))

    @traderep.command(name="cancel", aliases=["stop"], pass_context=True, no_pm=True)
    async def trade_stop(self, ctx, trade_num: int):
        """Stops a trade but doesn't break it"""
        if not trade_num:
            await self.bot.say("You must provide a trade number and it can't be 0")
            return
        cur = self.connection.cursor()
        cur.execute("SELECT partner from tradeperson tp join trade t on t.tradenum = tp.tradenum "
                    "where t.tradenum = ? and tp.person = ? and t.status is null",
                    (trade_num, ctx.message.author.id))
        row = cur.fetchone()
        if row:
            if row[0]:
                cur.execute("update trade set end_time = 'now', status=-1 where tradenum = {}".format(
                    trade_num
                ))
                if cur.rowcount == 1:
                    partner = await self.bot.get_user_info(row[0])
                    if partner:
                        await self.bot.say("Trade {} between {} and {} was cancelled".format(
                            trade_num, ctx.message.author.display_name, partner.display_name
                        ))
                    else:
                        await self.bot.say("Trade {} between you and {} was cancelled but I could not find a name "
                                           "for that person".format(trade_num, row[0]))
                    cur.execute("INSERT INTO tradelog (logtime, who, tradenum, what) values ('now', ?, ?, ?)",
                                (ctx.message.author.id, trade_num, "Author cancelled trade {} with {}".format(
                                    trade_num, row[0]
                                )))
                else:
                    await self.bot.say("Either trade {} didn't involve you or it isn't open".format(trade_num))
            else:
                await self.bot.say("Either trade {} didn't involve you or it isn't open".format(trade_num))
        else:
            await self.bot.say("Either trade {} didn't involve you or it isn't open".format(trade_num))

    @traderep.command(name="rep", pass_context=True, no_pm=True)
    async def rep(self, ctx, trade_num: int):
        """Reps a trading partner for a trade"""
        if not trade_num:
            await self.bot.say("You must provide a trade number and it can't be 0")
            return
        cur = self.connection.cursor()
        # Confirm the trade is done and involved the person repping
        cur.execute("SELECT partner from tradeperson tp join trade t on t.tradenum = tp.tradenum"
                    " where tp.tradenum = ? and person = ? and t.status = 1",
                    (trade_num, ctx.message.author.id))
        row = cur.fetchone()
        if row:
            if row[0]:
                cur.execute("update tradeperson set rep = 1, rep_time = 'now' where tradenum = ? and "
                            "person = ? and partner = ?", (trade_num, ctx.message.author.id, row[0]))
                partner = await self.bot.get_user_info(row[0])
                if partner:
                    await self.bot.say("You repped {} for trade {}.".format(
                        partner.display_name, trade_num
                    ))
                else:
                    await self.bot.say("You repped the person by id ({}) for trade {}.".format(
                        row[0], trade_num
                    ))
                cur.execute("INSERT INTO tradelog (logtime, who, tradenum, what) values ('now', ?, ?, ?)",
                            (ctx.message.author.id, trade_num, "Author repped {} for  trade {}".format(
                                row[0], trade_num
                            )))
            else:
                await self.bot.say("Either trade {} didn't involve you or it isn't open".format(trade_num))
        else:
            await self.bot.say("Either trade {} didn't involve you or it isn't open".format(trade_num))

    @traderep.command(name="derep", pass_context=True, no_pm=True)
    async def derep(self, ctx, trade_num: int):
        """Dings a trading partner for messing up a trade"""
        if not trade_num:
            await self.bot.say("You must provide a trade number and it can't be 0")
            return
        cur = self.connection.cursor()
        # Confirm the trade is done and involved the person repping
        cur.execute("SELECT partner from tradeperson tp join trade t on t.tradenum = tp.tradenum"
                    " where tp.tradenum = ? and person = ? and t.status = 1",
                    (trade_num, ctx.message.author.id))
        row = cur.fetchone()
        if row:
            if row[0]:
                cur.execute("update tradeperson set rep = -1, rep_time = 'now' where tradenum = ? and "
                            "person = ? and partner = ?",(trade_num, ctx.message.author.id, row[0]))
                partner = await self.bot.get_user_info(row[0])
                if partner:
                    await self.bot.say("You repped {} for trade {}.".format(
                        partner.display_name, trade_num
                    ))
                else:
                    await self.bot.say("You repped the person by id ({}) for trade {}.".format(
                        row[0], trade_num
                    ))
                cur.execute("INSERT INTO tradelog (logtime, who, tradenum, what) values ('now', ?, ?, ?)",
                            (ctx.message.author.id, trade_num, "Author repped {} for  trade {}".format(
                                row[0], trade_num
                            )))
            else:
                await self.bot.say("Either trade {} didn't involve you or it isn't closed".format(trade_num))
        else:
            await self.bot.say("Either trade {} didn't involve you or it isn't closed".format(trade_num))

    @traderep.command(name="report", pass_context=True, no_pm=True)
    async def report(self, ctx, *, args="0"):
        """Generates a report on a user. Accepts names, mentions, and IDs"""
        # TODO: Currently not parsing mentions properly
        id_to_use = 0
        if not args or args == "0":
            # User is reporting on themself
            id_to_use = ctx.message.author.id
        elif isinstance(args, discord.User):
            id_to_use = args.id
        elif args.isdigit():
            id_to_use = args
        else:
            user = ctx.message.server.get_member_named(args)
            if user:
                id_to_use = user.id
            else:
                await self.bot.say("I could not find {}".format(args))
                return

        if not id_to_use:
            id_to_use = ctx.message.author.id

        user = ctx.message.server.get_member(id_to_use)
        cur = self.connection.cursor()
        cur.execute("SELECT count(tradenum), sum(rep) from tradeperson where partner = {} and rep is not null".format(
            id_to_use
        ))
        (repped_trades, rep) = cur.fetchone()
        cur.execute("SELECT count(t.tradenum) from trade t join tradeperson tp on tp.tradenum = t.tradenum"
                    " where t.status is null and tp.person = {}".format(id_to_use))
        (open_trades) = cur.fetchone()
        cur.execute("SELECT count(t.tradenum) from trade t join tradeperson tp on tp.tradenum = t.tradenum"
                    " where t.status = 1 and tp.rep is null and tp.person = {}".format(id_to_use))
        (closed_unrepped_trades) = cur.fetchone()
        total_trades = closed_unrepped_trades[0] + open_trades[0] + repped_trades
        name_to_use = id_to_use
        if user:
            name_to_use = user.display_name
        report_str = ("Trade report for {}:\nRep: **{}** in **{}** trades\nTotal Trades: "
                      "**{}**\nOpen Trades: **{}**\n").format(
            name_to_use, rep, repped_trades, total_trades, open_trades[0]
        )
        if open_trades[0]:
            # Find the trading partners
            cur.execute("SELECT partner, tp.tradenum from tradeperson tp join trade t on tp.tradenum = t.tradenum"
                        " WHERE t.status is null and tp.person = {} ORDER BY start_time ASC LIMIT 100"
                        .format(id_to_use))
            rows = cur.fetchmany(size=100)
            names = ""
            for num, row in zip(range(5), rows):
                user = ctx.message.server.get_member(row[0])
                if user:
                    names += "{}({}), ".format(user.display_name, row[1])
                else:
                    names += "({})({}), ".format(row[0], row[1])
            if len(rows) >= 100:
                names += " and 95+ more"
            elif len(rows) > 5:
                names += " and {} more".format(len(rows) - 5)
            else:
                names = names.rstrip(", ")
            report_str += "Open trades with {}\n".format(names)

        # Find recent trading partners
        cur.execute("SELECT person, rep FROM tradeperson tp JOIN trade t ON t.tradenum = tp.tradenum"
                    " WHERE tp.partner = {} and t.status = 1 ORDER BY rep_time desc LIMIT 5".format(
            id_to_use
        ))
        rows = cur.fetchmany(size=5)
        open_names = ""
        if len(rows) == 0:
            open_names = "No completed trades"
        else:
            open_names = "Most recent {} completed trades (descending) with (rep in parens): ".format(len(rows))
            for num, row in zip(range(5), rows):
                user = ctx.message.server.get_member(row[0])
                if user:
                    open_names += "{} ({}), ".format(user.display_name, row[1])
                else:
                    open_names += "({}) ({}), ".format(row[0], row[1])
            open_names = open_names.rstrip(", ")
        report_str += open_names + "\n"
        await self.bot.say(report_str)


def check_folders():
    if not os.path.exists("data/traderep"):
        print("Creating traderep folder")
        os.makedirs("data/traderep")


def check_files():
    f = "data/traderep/traderep.db"
    if os.path.exists(f):
        con = sqlite3.connect(f)
        cursor = con.cursor()
        cursor.execute("select max(level) from version")
        indb_version = cursor.fetchone()
        if indb_version[0] < db_version:
            db_upgrade(con, indb_version)
    else:
        con = sqlite3.connect(f)
        con.isolation_level = None
        new_database(con)


def new_database(con):
    """Uses the database connection to create the tables needed"""
    cursor = con.cursor()
    cursor.execute("CREATE TABLE version (level real not null)")
    print("Using database version: {}".format(db_version))
    cursor.execute("INSERT INTO version values ({})".format(db_version))
    cursor.execute("CREATE TABLE trade (tradenum integer primary key asc, initiator text, start_time text, "
                   "end_time text, status integer)")
    cursor.execute("CREATE TABLE tradeperson (tradenum integer, person text, partner text, rep integer, "
                   "rep_time text, primary key(tradenum, person, partner))")
    cursor.execute("CREATE TABLE tradelog (logtime text, who integer, tradenum integer, what text)")


def db_upgrade(con, old_version):
    """Takes the old version and applies logic to get to the highest version"""
    if old_version < 1.0:
        cursor = con.cursor()
        cursor.execute("DELETE FROM version where 1=1")
        cursor.execute("INSERT INTO version values(?)", (1.0)) #incremental upgrades
        cursor.execute("COMMIT TRANSACTION")
        old_version = 1.0
    # Note for future: create a new table, copy /change data to it, drop old table, create table, copy data


def setup(bot):
    check_folders()
    check_files()

    bot.add_cog(Traderep(bot))

