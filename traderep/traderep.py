import discord
from discord.ext import commands
from cogs.utils import checks
import sqlite3
import os
# noinspection PyUnresolvedReferences
from __main__ import send_cmd_help

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
                partner.mention, ctx.message.author.mention, trade_num))
        else:
            await self.bot.say("Something very bad happened and I didn't get a trade number, try again?")

    @traderep.command(name="done", aliases=["complete", "finish"], pass_context=True, no_pm=True, hidden=True)
    async def trade_complete(self, ctx, trade_num: int):
        """Marks a trade as done. Obsoleted"""
        await self.bot.say("This command is no longer used, just rep the person")
        return

    @traderep.command(name="cancel", aliases=["stop"], pass_context=True, no_pm=True)
    async def trade_stop(self, ctx, arg):
        """Stops a trade but doesn't break it"""
        trade_who, trade_num = None, None
        if isinstance(arg, int):
            trade_num = arg
        elif isinstance(arg, discord.Member):
            trade_who = arg.id
        cur = self.connection.cursor()
        if trade_who:
            cur.execute("SELECT partner, t.tradenum from tradeperson tp join trade t on t.tradenum = tp.tradenum "
                        "where tp.person = ? and tp.partner = ? and t.status is null",
                        (ctx.message.author.id, trade_who))
        elif trade_num:
            cur.execute("SELECT partner, t.tradenum from tradeperson tp join trade t on t.tradenum = tp.tradenum "
                        "where t.tradenum = ? and tp.person = ? and t.status is null",
                        (trade_num, ctx.message.author.id))
        else:
            await self.bot.say("You must provide a trade number and it can't be 0")
            return
        row = cur.fetchone()
        if row:
            trade_who, trade_num = row[0], row[1]
            if row[0]:
                cur.execute("update trade set end_time = 'now', status=-1 where tradenum = {}".format(
                    trade_num
                ))
                if cur.rowcount == 1:
                    if ctx.message.server:
                        partner = ctx.message.server.get_member(trade_who)
                    else:
                        await self.bot.say("This command doesn't work in PM")
                        return
                    if partner:
                        await self.bot.say("Trade {} between {} and {} was cancelled".format(
                            trade_num, ctx.message.author.mention, partner.mention
                        ))
                    else:
                        await self.bot.say("Trade {} between you and {} was cancelled but I could not find a name "
                                           "for that person".format(trade_num, trade_who))
                    cur.execute("INSERT INTO tradelog (logtime, who, tradenum, what) values ('now', ?, ?, ?)",
                                (ctx.message.author.id, trade_num, "Author cancelled trade {} with {}".format(
                                    trade_num, row[0]
                                )))
                else:
                    await self.bot.say("I was unable to cancel trade number {}".format(trade_num))
            else:
                await self.bot.say("Either trade {} didn't involve you or it isn't open".format(trade_num))
        else:
            if isinstance(arg, int):
                await self.bot.say("Either trade {} didn't involve you or it isn't open".format(trade_num))
            elif isinstance(arg, discord.Member):
                await self.bot.say("It doesn't look like you have an open trade with {}".format(arg.display_name))
            else:
                await self.bot.say("Sorry, not sure how this happened but I didn't do anything either")

    @traderep.command(name="rep", pass_context=True, no_pm=True)
    async def rep(self, ctx, arg):
        """Reps a trading partner for a trade. Closes trade"""
        if not arg:
            await self.bot.say("Maybe you only have one trade open but I don't want to risk it, be specific.")
            return
        mentions = ctx.message.mentions
        cur = self.connection.cursor()
        trade_who, trad_num = None, None
        if arg.isdigit():
            trade_num = arg
        elif mentions and isinstance(mentions, list) and isinstance(mentions[0], discord.Member):
            trade_who = mentions[0].id
            # First look to close a trade
            cur.execute("SELECT tp.tradenum, partner from tradeperson tp join trade t on t.tradenum = tp.tradenum"
                        " where person = ? and partner = ? and t.status is null",
                        (ctx.message.author.id, trade_who))
            row = cur.fetchone()
            if row and row[0]:
                trade_num = row[0]
            else:
                # Look for an unrepped trade
                cur.execute("SELECT tp.tradenum, partner from tradeperson tp join trade t on t.tradenum = tp.tradenum"
                            " where person = ? and partner = ? and t.status = 1 and tp.rep is null",
                            (ctx.message.author.id, trade_who))
                row = cur.fetchone()
                if row and row[0]:
                    trade_num = row[0]
                else:
                    # Use most recent started trade
                    cur.execute(
                        "SELECT tp.tradenum, partner from tradeperson tp join trade t on t.tradenum = tp.tradenum"
                        " where person = ? and partner = ? and t.status = 1 order by t.start_time desc",
                        (ctx.message.author.id, trade_who))
                    row = cur.fetchone()
                    if row and row[0]:
                        trade_num = row[0]
                    else:
                        await self.bot.say("I tried but couldn't figure out which trade you meant")
                        return
        else:
            await self.bot.say("I don't know what you're trying to do.")
            return
        # Find the open trade number
        cur.execute("SELECT tp.tradenum, partner from tradeperson tp join trade t on t.tradenum = tp.tradenum"
                    " where tp.tradenum = ? and person = ? and (t.status = 1 or t.status is null)",
                    (trade_num, ctx.message.author.id))
        row = cur.fetchone()
        if row:
            trade_num, trade_who = row[0], row[1]
            if row[0]:
                did_close = False
                cur.execute("update trade set status = 1, end_time = 'now' where tradenum = {} and status is null"
                            .format(trade_num))
                if cur.rowcount == 1:
                    did_close = True
                cur.execute("update tradeperson set rep = 1, rep_time = 'now' where tradenum = ? and "
                            "person = ? and partner = ?", (trade_num, ctx.message.author.id, row[1]))
                if ctx.message.server:
                    partner = ctx.message.server.get_member(trade_who)
                else:
                    await self.bot.say("This command doesn't work in PM")
                    return
                if partner:
                    if did_close:
                        await self.bot.say("You closed trade {} and repped {} for it. It's their turn to rep you"
                                           .format(trade_num, partner.mention))
                    else:
                        await self.bot.say("You repped {} for trade {}.".format(
                            partner.mention, trade_num
                        ))
                else:
                    if did_close:
                        await self.bot.say("You closed trade {} and repped {} for it. It's their turn to rep you"
                                           .format(trade_num, row[0]))
                    else:
                        await self.bot.say("You repped {} for trade {} and that should mean all reps complete.".format(
                            row[0], trade_num
                        ))
                cur.execute("INSERT INTO tradelog (logtime, who, tradenum, what) values ('now', ?, ?, ?)",
                            (ctx.message.author.id, trade_num, "Author repped {} for  trade {}".format(
                                row[0], trade_num
                            )))
            else:
                await self.bot.say("I didn't find a trade matching that description which involved you")
        else:
            await self.bot.say("I didn't find a trade matching that description which involved you")

    @traderep.command(name="derep", pass_context=True, no_pm=True)
    async def derep(self, ctx, arg):
        """Dings a trading partner for messing up a trade"""
        if not arg:
            await self.bot.say("Maybe you only have one trade open but I don't want to risk it, be specific.")
            return
        mentions = ctx.message.mentions
        cur = self.connection.cursor()
        trade_who, trad_num = None, None
        if arg.isdigit():
            trade_num = arg
        elif mentions and isinstance(mentions, list) and isinstance(mentions[0], discord.Member):
            trade_who = mentions[0].id
            # First look to close a trade
            cur.execute("SELECT tp.tradenum, partner from tradeperson tp join trade t on t.tradenum = tp.tradenum"
                        " where person = ? and partner = ? and t.status is null",
                        (ctx.message.author.id, trade_who))
            row = cur.fetchone()
            if row and row[0]:
                trade_num = row[0]
            else:
                # Look for an unrepped trade
                cur.execute("SELECT tp.tradenum, partner from tradeperson tp join trade t on t.tradenum = tp.tradenum"
                            " where person = ? and partner = ? and t.status = 1 and tp.rep is null",
                            (ctx.message.author.id, trade_who))
                row = cur.fetchone()
                if row and row[0]:
                    trade_num = row[0]
                else:
                    # Use most recent started trade
                    cur.execute(
                        "SELECT tp.tradenum, partner from tradeperson tp join trade t on t.tradenum = tp.tradenum"
                        " where person = ? and partner = ? and t.status = 1 order by t.start_time desc",
                        (ctx.message.author.id, trade_who))
                    row = cur.fetchone()
                    if row and row[0]:
                        trade_num = row[0]
                    else:
                        await self.bot.say("I tried but couldn't figure out which trade you meant")
                        return
        else:
            await self.bot.say("I don't know what you're trying to do.")
            return
        # Find the open trade number
        cur.execute("SELECT tp.tradenum, partner from tradeperson tp join trade t on t.tradenum = tp.tradenum"
                    " where tp.tradenum = ? and person = ? and (t.status = 1 or t.status is null)",
                    (trade_num, ctx.message.author.id))
        row = cur.fetchone()
        if row:
            trade_num, trade_who = row[0], row[1]
            if row[0]:
                did_close = False
                cur.execute("update trade set status = 1, end_time = 'now' where tradenum = {} and status is null"
                            .format(trade_num))
                if cur.rowcount == 1:
                    did_close = True
                cur.execute("update tradeperson set rep = -1, rep_time = 'now' where tradenum = ? and "
                            "person = ? and partner = ?", (trade_num, ctx.message.author.id, row[1]))
                if ctx.message.server:
                    partner = ctx.message.server.get_member(trade_who)
                else:
                    await self.bot.say("This command doesn't work in PM")
                    return
                if partner:
                    if did_close:
                        await self.bot.say("You closed trade {} and derepped {} for it. It's their turn"
                                           .format(trade_num, partner.mention))
                    else:
                        await self.bot.say("You derepped {} for trade {}.".format(
                            partner.mention, trade_num
                        ))
                else:
                    if did_close:
                        await self.bot.say("You closed trade {} and derepped {} for it. It's their turn"
                                           .format(trade_num, row[0]))
                    else:
                        await self.bot.say("You derepped {} for trade {} and that should mean all reps complete.".format(
                            row[0], trade_num
                        ))
                cur.execute("INSERT INTO tradelog (logtime, who, tradenum, what) values ('now', ?, ?, ?)",
                            (ctx.message.author.id, trade_num, "Author derepped {} for  trade {}".format(
                                row[0], trade_num
                            )))
            else:
                await self.bot.say("I didn't find a trade matching that description which involved you")
        else:
            await self.bot.say("I didn't find a trade matching that description which involved you")

    @traderep.command(name="report", aliases=["profile", "status"], pass_context=True, no_pm=True)
    async def report(self, ctx, *, args="0"):
        """Generates a report on a user. Accepts names, mentions, and IDs"""
        mentions = ctx.message.mentions
        if not args or args == "0":
            # User is reporting on themself
            id_to_use = ctx.message.author.id
        elif isinstance(args, discord.User):
            id_to_use = args.id
        elif mentions and isinstance(mentions, list) and isinstance(mentions[0], discord.Member):
            id_to_use = mentions[0].id
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
        cur.execute("SELECT count(t.tradenum), sum(rep) from tradeperson tp join trade t on t.tradenum = tp.tradenum"
                    " where partner = {} and rep is not null and t.status = 1".format(id_to_use))
        (repped_trades, rep) = cur.fetchone()
        cur.execute("SELECT count(t.tradenum) from trade t join tradeperson tp on tp.tradenum = t.tradenum"
                    " where t.status is null and tp.person = {}".format(id_to_use))
        row = cur.fetchone()
        open_trades = row[0]
        cur.execute("SELECT count(t.tradenum) from trade t join tradeperson tp on tp.tradenum = t.tradenum"
                    " where t.status = 1 and tp.rep is null and tp.person = {}".format(id_to_use))
        row = cur.fetchone()
        closed_unrepped_trades = row[0]
        cur.execute("SELECT count(t.tradenum) from trade t join tradeperson tp on tp.tradenum = t.tradenum"
                    " where t.status = 1 and tp.rep is null and tp.partner = {}".format(id_to_use))
        row = cur.fetchone()
        closed_waiting_trade = row[0]
        cur.execute("SELECT count(t.tradenum) from trade t join tradeperson tp on tp.tradenum = t.tradenum"
                    " where tp.person = {} and (t.status is null or t.status = 1)".format(id_to_use))
        row = cur.fetchone()
        total_trades = row[0]
        name_to_use = id_to_use
        if user:
            name_to_use = user.display_name
        report_str = "Trade report for **{}**:\n".format(name_to_use)
        status_str = ""

        if rep:
            report_str += "Rep: **{}** across {} repped trades, {} total trades\n".format(rep,
                                                                                          repped_trades, total_trades)
        else:
            status_str += "Has no rep. "

        if open_trades:
            report_str += "Open trades ({}) with: ".format(open_trades)
            cur.execute("SELECT t.tradenum, tp.partner from trade t join tradeperson tp on tp.tradenum = t.tradenum"
                        " where t.status is null and tp.person = {} order by t.start_time desc".format(id_to_use))
            rows = cur.fetchmany(size=10)
            name_str = ""
            for row in rows:
                user = ctx.message.server.get_member(row[1])
                if user:
                    name_str += "{} ({}), ".format(user.display_name, row[0])
                else:
                    name_str += "({}) ({}), ".format(row[0], row[1])
            name_str = name_str.rstrip(", ")
            report_str += name_str + "\n"
        else:
            status_str += "Has no open trades. "

        if repped_trades:
            report_str += "Most recent repped trades: "
            cur.execute("SELECT tp.rep, tp.person from tradeperson tp WHERE tp.partner = {} and tp.rep is not null "
                        "order by tp.rep_time desc"
                        .format(id_to_use))
            rows = cur.fetchmany(size=10)
            name_str = ""
            for row in rows:
                user = ctx.message.server.get_member(row[1])
                if user:
                    name_str += "{} ({}), ".format(user.display_name, row[0])
                else:
                    name_str += "({}) ({}), ".format(row[1], row[0])
            name_str = name_str.rstrip(", ")
            report_str += name_str + "\n"
        else:
            status_str += "Has no repped trades. "

        if closed_unrepped_trades:
            report_str += "Partners waiting on rep: "
            cur.execute("SELECT tp.partner, tp.tradenum from trade t join tradeperson tp on tp.tradenum = t.tradenum"
                        " where t.status = 1 and tp.rep is null and tp.person = {}".format(id_to_use))
            rows = cur.fetchmany(size=10)
            name_str = ""
            for row in rows:
                user = ctx.message.server.get_member(row[0])
                if user:
                    name_str += "{} ({}), ".format(user.display_name, row[1])
                else:
                    name_str += "({}) ({}), ".format(row[0], row[1])
            name_str = name_str.rstrip(", ")
            report_str += name_str + "\n"
        else:
            status_str += "Has no partners waiting on reps. "

        if closed_waiting_trade:
            report_str += "Waiting on rep from {} partners: ".format(name_to_use)
            cur.execute("SELECT tp.person, tp.tradenum from trade t join tradeperson tp on tp.tradenum = t.tradenum"
                        " where t.status = 1 and tp.rep is null and tp.partner = {}".format(id_to_use))
            rows = cur.fetchmany(size=10)
            name_str = ""
            for row in rows:
                user = ctx.message.server.get_member(row[0])
                if user:
                    name_str += "{} ({}), ".format(user.display_name, row[1])
                else:
                    name_str += "({}) ({}), ".format(row[0]. row[1])
            name_str = name_str.rstrip(", ")
            report_str += name_str + "\n"
        else:
            status_str += "Isn't waiting on rep. "

        report_str += status_str
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
        cursor.execute("INSERT INTO version values(1.0)")
        cursor.execute("COMMIT TRANSACTION")
        old_version = 1.0
    # Note for future: create a new table, copy /change data to it, drop old table, create table, copy data
    if old_version < db_version:
        print("Database is at {} but don't know how to upgrade to {}".format(old_version, db_version))


def setup(bot):
    check_folders()
    check_files()

    bot.add_cog(Traderep(bot))
