import asyncio
import contextlib
import json
import logging
import traceback
from io import BytesIO, StringIO
from typing import Optional

import aiohttp
import discord
import httpx
import xmltojson
from discord.ext import tasks
from pydantic import VERSION
from redbot.core import Config, commands
from redbot.core.utils.chat_formatting import box
from xbox.webapi.api.client import XboxLiveClient
from xbox.webapi.authentication.manager import AuthenticationManager
from xbox.webapi.authentication.models import OAuth2TokenResponse
from xbox.webapi.common.signed_session import SignedSession

from .dpymenu import DEFAULT_CONTROLS, menu
from .formatter import (
    friend_embeds,
    game_embeds,
    gameclip_embeds,
    gwg_embeds,
    mostplayed,
    ms_status,
    profile,
    profile_embed,
    screenshot_embeds,
    stats_api_format,
)

REDIRECT_URI = "http://localhost/auth/callback"
LOADING = "https://i.imgur.com/l3p6EMX.gif"
log = logging.getLogger("red.vrt.xtools")
V2 = VERSION >= "2.0.0"


class XTools(commands.Cog):
    """
    Provides various features and functionalities related to Xbox, including profile retrieval, game clips and screenshot viewing, Microsoft services status checking, and more.
    """

    __author__ = "[vertyco](https://github.com/vertyco/vrt-cogs)"
    __version__ = "3.11.2"

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"
        # formatted for when you type [p]help Xbox

    async def red_delete_data_for_user(self, *, requester, user_id: int):
        """No data to delete"""
        async with self.config.users() as users:
            if str(user_id) in users:
                del users[str(user_id)]

    def __init__(self, bot, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.config = Config.get_conf(self, 117117117117, force_registration=True)
        default_global = {
            "tokens": {},
            "clientid": None,
            "clientsecret": None,
            "users": {},
        }
        default_guild = {"statuschannel": 0}
        self.config.register_global(**default_global)
        self.config.register_guild(**default_guild)

        # Caching friend list for searching
        self.cache = {}
        self.alert = None
        self.status.start()

    def cog_unload(self):
        self.status.cancel()
        self.bot.loop.create_task(self.session.close())

    # Get Microsoft services status
    @staticmethod
    async def microsoft_services_status():
        async with aiohttp.ClientSession() as session:
            async with session.get("https://xnotify.xboxlive.com/servicestatusv6/US/en-US") as resp:
                data = xmltojson.parse(await resp.text())  # Parse HTML response to JSON
                data = json.loads(data)
                return data

    # General authentication manager
    async def auth_manager(self, session, ctx: commands.Context = None):
        tokens = await self.config.tokens()
        client_id = await self.config.clientid()
        client_secret = await self.config.clientsecret()
        if not client_id:
            if ctx:
                await ctx.send(
                    f"Client ID and Secret have not been set yet!\n"
                    f"Bot owner needs to run `{ctx.clean_prefix}apiset tokens`"
                )
            return None
        auth_mgr = AuthenticationManager(session, client_id, client_secret, REDIRECT_URI)
        if tokens == {}:
            if ctx.author.id in self.bot.owner_ids:
                url = "https://login.live.com/oauth20_authorize.srf?"
                cid = f"client_id={client_id}"
                types = "&response_type=code&approval_prompt=auto"
                scopes = "&scope=Xboxlive.signin+Xboxlive.offline_access&"
                redirect_uri = "&redirect_uri=http://localhost/auth/callback"
                auth_url = f"{url}{cid}{types}{scopes}{redirect_uri}"
                if ctx:
                    await ctx.send("Sending you a DM to authorize your tokens.")
                await self.ask_auth(ctx, ctx.author, auth_url)
                return None
            else:
                if ctx:
                    await ctx.send("Tokens have not been authorized by bot owner yet!")
                return None
        try:
            auth_mgr.oauth = OAuth2TokenResponse.parse_raw(json.dumps(tokens))
        except Exception as e:
            if "validation error" in str(e):
                if ctx:
                    await ctx.send("Tokens have not been authorized by bot owner yet!")
                return None
        try:
            await auth_mgr.refresh_tokens()
        except Exception as e:
            if "Bad Request" in str(e):
                if ctx:
                    await ctx.send(
                        "Tokens have failed to refresh.\n"
                        "Microsoft API may be having issues.\n"
                        f"Bot owner will need to re-authorize their tokens with `{ctx.clean_prefix}apiset auth`"
                    )
                return None
        dump = auth_mgr.oauth.model_dump(mode="json") if V2 else json.loads(auth_mgr.oauth.json())
        await self.config.tokens.set(dump)
        xbl_client = XboxLiveClient(auth_mgr)
        return xbl_client

    # Send user DM asking for authentication
    async def ask_auth(self, ctx, author: discord.User, auth_url):
        plz_auth = (
            f"Please follow this link to authorize your tokens with Microsoft.\n"
            f"Copy the ENTIRE contents of the address bar after you authorize, "
            f"and reply to this message with what you copied.\n"
            f"**[Click Here To Authorize Your Account]({auth_url})**"
        )
        embed = discord.Embed(description=plz_auth, color=ctx.author.color)
        try:
            await author.send(embed=embed)
        except discord.Forbidden:
            return await ctx.send("I am unable to DM you, please open your DMs and try again.")

        def check(message):
            return message.author == ctx.author

        try:
            reply = await self.bot.wait_for("message", check=check, timeout=240)
        except asyncio.TimeoutError:
            return await author.send("Authorization timeout.")

        if "code" in reply.content:
            code = reply.content.split("code=")[-1]
        else:
            return await author.send("Invalid response")

        client_id = await self.config.clientid()
        client_secret = await self.config.clientsecret()

        async with SignedSession() as session:
            auth_mgr = AuthenticationManager(session, client_id, client_secret, REDIRECT_URI)
            try:
                await auth_mgr.request_tokens(code)
                dump = auth_mgr.oauth.model_dump(mode="json") if V2 else json.loads(auth_mgr.oauth.json())
                await self.config.tokens.set(dump)
            except Exception as e:
                if "Bad Request" in str(e):
                    return await author.send(
                        "Bad Request, Make sure to use a **Different** email than the one "
                        "you used to make your Azure app to sign into.\n"
                        "Check the following as well:\n"
                        "• Paste the **entire** contents of the address bar.\n"
                        "• Make sure that the callback URI in your azure app is: "
                        "http://localhost/auth/callback"
                    )
                return await author.send(f"Authorization failed: {e}")
            await author.send("Tokens have been Authorized✅")

    # Get XSTS token
    async def get_token(self, session):
        tokens = await self.config.tokens()
        client_id = await self.config.clientid()
        client_secret = await self.config.clientsecret()
        auth_mgr = AuthenticationManager(session, client_id, client_secret, REDIRECT_URI)
        auth_mgr.oauth = OAuth2TokenResponse.parse_raw(json.dumps(tokens))
        await auth_mgr.refresh_tokens()
        dump = auth_mgr.oauth.model_dump(mode="json") if V2 else json.loads(auth_mgr.oauth.json())
        await self.config.tokens.set(dump)
        token = auth_mgr.xsts_token.authorization_header_value
        return token

    # Pulls user info if they've set a Gamertag
    async def pull_user(self, ctx: commands.Context):
        users = await self.config.users()
        if str(ctx.author.id) not in users:
            await ctx.send(
                f"You haven't set your Gamertag yet! To set a Gamertag type `{ctx.clean_prefix}setgt`\n"
                f"Alternatively, you can type the command and include a Gamertag."
            )
            return None
        return users[str(ctx.author.id)]["gamertag"]

    @commands.group(name="apiset")
    @commands.is_owner()
    async def api_settings(self, ctx: commands.Context):
        """Set up the XTools cog"""

    @api_settings.command(name="auth")
    @commands.bot_has_permissions(embed_links=True)
    async def auth_user(self, ctx: commands.Context):
        client_id = await self.config.clientid()
        if not client_id:
            await ctx.send(
                f"Client ID and Secret have not been set yet!\n"
                f"Bot owner needs to run `{ctx.clean_prefix}apiset tokens`"
            )
            return None
        url = "https://login.live.com/oauth20_authorize.srf?"
        cid = f"client_id={client_id}"
        types = "&response_type=code&approval_prompt=auto"
        scopes = "&scope=Xboxlive.signin+Xboxlive.offline_access&"
        redirect_uri = "&redirect_uri=http://localhost/auth/callback"
        auth_url = f"{url}{cid}{types}{scopes}{redirect_uri}"
        await ctx.send("Sending you a DM to authorize your tokens.")
        await self.ask_auth(ctx, ctx.author, auth_url)

    @api_settings.command(name="help")
    @commands.bot_has_permissions(embed_links=True)
    async def get_help(self, ctx: commands.Context):
        """Tutorial for getting your ClientID and Secret"""
        embed = discord.Embed(
            description="**How to get your Client ID and Secret**",
            color=discord.Color.magenta(),
        )
        embed.add_field(
            name="Step 1",
            value="• Register a new application in "
            "[Azure AD](https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps/ApplicationsListBlade)",
            inline=False,
        )
        embed.add_field(
            name="Step 2",
            value="• Name your app\n"
            "• Select `Personal Microsoft accounts only` under supported account types\n"
            "• Add http://localhost/auth/callback as a Redirect URI of type `Web`",
            inline=False,
        )
        embed.add_field(
            name="Step 3",
            value="• Copy your Application (client) ID and save it for setting your tokens",
            inline=False,
        )
        embed.add_field(
            name="Step 4",
            value="• On the App Page, navigate to `Certificates & secrets`\n"
            "• Generate a new client secret and save it for setting your tokens\n"
            "• **Importatnt:** The 'Value' for the secret is what you use, NOT the 'Secret ID'",
            inline=False,
        )
        embed.add_field(
            name="Step 5",
            value=f"• Type `{ctx.clean_prefix}apiset tokens` and include your Client ID and Secret\n",
            inline=False,
        )
        embed.add_field(
            name="Step 6",
            value=f"• Type `{ctx.clean_prefix}apiset auth` and the bot will dm you a link to authorize your tokens\n"
            f"• Alternatively, try any command and the bot will DM you the link\n"
            f"• Make sure to use a **Different** email to sign in than the one you created the Azure app with",
            inline=False,
        )
        await ctx.send(embed=embed)

    @api_settings.command(name="tokens")
    async def set_tokens(self, ctx, client_id, client_secret):
        """Set Client ID and Secret"""
        await self.config.clientid.set(client_id)
        await self.config.clientsecret.set(client_secret)
        await ctx.send(
            "Tokens have been set! "
            "Try any command and the bot will DM you the link with instructions to authorize your tokens"
        )
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            await ctx.send("I do not have permissions to delete your message!")
        except discord.NotFound:
            pass

    @api_settings.command(name="reset")
    async def reset_cog(self, ctx: commands.Context):
        """Reset the all token data"""
        await self.config.tokens.clear()
        await self.config.clientid.set(None)
        await self.config.clientsecret.set(None)
        await ctx.send("Tokens have been wiped!")

    @commands.command(name="xstatuschannel")
    @commands.has_permissions(manage_messages=True)
    async def set_channel(self, ctx, channel: Optional[discord.TextChannel]):
        """
        Set the channel for Microsoft status alerts

        Any time microsoft services go down an alert will go out in the channel and be updated
        """
        async with self.config.guild(ctx.guild).all() as conf:
            if not channel and not conf["statuschannel"]:
                await ctx.send_help()
            elif conf["statuschannel"] and not channel:
                conf["statuschannel"] = 0
                await ctx.send("Status channel reset")
            else:
                conf["statuschannel"] = channel.id
                await ctx.send(f"Status channel set to {channel.mention}")

    @commands.command(name="setgt")
    async def set_gamertag(self, ctx, *, gamertag):
        """Set your Gamertag to use commands without entering it"""
        async with ctx.typing():
            async with SignedSession() as session:
                xbl_client = await self.auth_manager(session, ctx)
                if not xbl_client:
                    return
                try:
                    pdata = await xbl_client.profile.get_profile_by_gamertag(gamertag)
                    profile_data = pdata.model_dump(mode="json") if V2 else json.loads(pdata.json())
                except aiohttp.ClientResponseError:
                    return await ctx.send("Invalid Gamertag. Try again.")
                # Format json data
                gt, xuid, _, _, _, _, _, _, _ = profile(profile_data)
                async with self.config.users() as users:
                    users[ctx.author.id] = {"gamertag": gt, "xuid": xuid}
                    await ctx.tick()

    @commands.command(name="xuid")
    async def get_xuid(self, ctx, *, gamertag=None):
        """Get a player's XUID"""
        # If user didn't enter Gamertag, check if they've set one
        if not gamertag:
            gamertag = await self.pull_user(ctx)
            if not gamertag:
                return
        async with SignedSession() as session:
            xbl_client = await self.auth_manager(session, ctx)
            if not xbl_client:
                return
            try:
                pdata = await xbl_client.profile.get_profile_by_gamertag(gamertag)
                profile_data = pdata.model_dump(mode="json") if V2 else json.loads(pdata.json())
            except aiohttp.ClientResponseError:
                return await ctx.send("Invalid Gamertag. Try again.")
            _, xuid, _, _, _, _, _, _, _ = profile(profile_data)
            return await ctx.send(f"`{xuid}`")

    @commands.command(name="gamertag")
    async def get_gamertag(self, ctx, *, xuid):
        """Get the Gamertag associated with an XUID"""
        async with SignedSession() as session:
            xbl_client = await self.auth_manager(session, ctx)
            if not xbl_client:
                return
            try:
                pdata = await xbl_client.profile.get_profile_by_xuid(xuid)
                profile_data = pdata.model_dump(mode="json") if V2 else json.loads(pdata.json())
            except aiohttp.ClientResponseError:
                return await ctx.send("Invalid XUID. Try again.")
            gt, _, _, _, _, _, _, _, _ = profile(profile_data)
            return await ctx.send(f"`{gt}`")

    @commands.command(name="xprofile")
    @commands.bot_has_permissions(embed_links=True)
    async def get_profile(self, ctx, *, gamertag: str = None):
        """View your Xbox profile"""
        # If user didn't enter Gamertag, check if they've set one
        if not gamertag:
            gamertag = await self.pull_user(ctx)
            if not gamertag:
                return
        async with SignedSession() as session:
            xbl_client = await self.auth_manager(session, ctx)
            if not xbl_client:
                return
            embed = discord.Embed(description="Gathering data...", color=discord.Color.random())
            embed.set_thumbnail(url=LOADING)
            msg = await ctx.send(embed=embed)
            try:
                pdata = await xbl_client.profile.get_profile_by_gamertag(gamertag)
                profile_data = pdata.model_dump(mode="json") if V2 else json.loads(pdata.json())
            except aiohttp.ClientResponseError:
                embed = discord.Embed(description="Invalid Gamertag. Try again.")
                return await msg.edit(embed=embed)
            _, xuid, _, _, _, _, _, _, _ = profile(profile_data)
            friends = await xbl_client.people.get_friends_summary_by_gamertag(gamertag)
            friends_data = friends.model_dump(mode="json") if V2 else json.loads(friends.json())

            # Manually get presence and activity info since xbox webapi method is outdated
            token = await self.get_token(session)
            header = {
                "x-xbl-contract-version": "3",
                "Authorization": token,
                "Accept": "application/json",
                "Accept-Language": "en-US",
                "Host": "presencebeta.xboxlive.com",
            }
            url = f"https://userpresence.xboxlive.com/users/xuid({xuid})"
            async with self.session.get(url=url, headers=header) as res:
                presence_data = await res.json(content_type=None)
            url = f"https://avty.xboxlive.com/users/xuid({xuid})/Activity/History?numItems=5&excludeTypes=TextPost"
            async with self.session.get(url=url, headers=header) as res:
                activity_data = await res.json(content_type=None)
            profile_data["friends"] = friends_data
            profile_data["presence"] = presence_data
            profile_data["activity"] = activity_data["activityItems"]
            embed = profile_embed(profile_data)
            try:
                return await msg.edit(embed=embed)
            except discord.HTTPException:
                try:
                    return await ctx.send(embed=embed)
                except discord.HTTPException:
                    return await ctx.send("Something broke")  # Fuck it

    @commands.command(name="xscreenshots")
    @commands.bot_has_permissions(embed_links=True)
    async def get_screenshots(self, ctx, *, gamertag=None):
        """View your Screenshots"""
        if not gamertag:
            gamertag = await self.pull_user(ctx)
            if not gamertag:
                return
        async with SignedSession() as session:
            xbl_client = await self.auth_manager(session, ctx)
            if not xbl_client:
                return
            embed = discord.Embed(description="Gathering data...", color=discord.Color.random())
            embed.set_thumbnail(url=LOADING)
            msg = await ctx.send(embed=embed)
            try:
                pdata = await xbl_client.profile.get_profile_by_gamertag(gamertag)
                profile_data = pdata.model_dump(mode="json") if V2 else json.loads(pdata.json())
            except aiohttp.ClientResponseError:
                embed = discord.Embed(description="Invalid Gamertag. Try again.")
                return await msg.edit(embed=embed)
            _, xuid, _, _, _, _, _, _, _ = profile(profile_data)
            try:
                ss = await xbl_client.screenshots.get_saved_screenshots_by_xuid(xuid=xuid, max_items=10000)
                data = ss.model_dump(mode="json") if V2 else json.loads(ss.json())
            except aiohttp.ClientResponseError as e:
                if e.message == "Forbidden":
                    embed = discord.Embed(
                        description="Forbidden: Cannot get screenshots for user, "
                        "they may have their settings on private",
                        color=discord.Color.red(),
                    )
                else:
                    embed = discord.Embed(
                        description=f"Error: {box(e.message)}",
                        color=discord.Color.red(),
                    )
                await msg.edit(embed=embed)
                return
            pages = screenshot_embeds(data, gamertag)
            if len(pages) == 0:
                color = discord.Color.red()
                embed = discord.Embed(description="No screenshots found", color=color)
                return await msg.edit(embed=embed)
            await msg.delete()
            await menu(ctx, pages, DEFAULT_CONTROLS)

    @commands.command(name="xgames")
    @commands.bot_has_permissions(embed_links=True)
    async def get_games(self, ctx, *, gamertag=None):
        """View your games and achievements"""
        if not gamertag:
            gamertag = await self.pull_user(ctx)
            if not gamertag:
                return
        async with SignedSession() as session:
            xbl_client = await self.auth_manager(session, ctx)
            if not xbl_client:
                return
            embed = discord.Embed(description="Gathering data...", color=discord.Color.random())
            embed.set_thumbnail(url=LOADING)
            msg = await ctx.send(embed=embed)
            try:
                pdata = await xbl_client.profile.get_profile_by_gamertag(gamertag)
                profile_data = pdata.model_dump(mode="json") if V2 else json.loads(pdata.json())
            except aiohttp.ClientResponseError:
                embed = discord.Embed(description="Invalid Gamertag. Try again.")
                return await msg.edit(embed=embed)
            gt, xuid, _, _, _, _, _, _, _ = profile(profile_data)

            token = await self.get_token(session)
            header = {
                "x-xbl-contract-version": "2",
                "Authorization": token,
                "Accept-Language": "en-US",
            }
            url = f"https://achievements.xboxlive.com/users/xuid({xuid})/history/titles"

            # Keep pulling continuation token till all data is obtained
            running = True
            params = None
            game_data = {"titles": []}
            while running:
                async with self.session.get(url=url, headers=header, params=params) as res:
                    data = await res.json(content_type=None)
                    c_token = data["pagingInfo"]["continuationToken"]
                    titles = data["titles"]
                    game_data["titles"].extend(titles)
                    if not c_token:
                        running = False
                    else:
                        params = {"continuationToken": c_token}
            if len(game_data["titles"]) == 0:
                embed = discord.Embed(
                    color=discord.Color.red(),
                    description="Your privacy settings are blocking your gameplay history.\n"
                    "**[Click Here](https://account.xbox.com/en-gb/Settings)** to change your settings.",
                )
                return await msg.edit(embed=embed)

            embed = discord.Embed(
                description="What game would you like to search for?",
                color=discord.Color.random(),
            )
            embed.set_footer(text='Reply "cancel" to end the search')
            await msg.edit(embed=embed)

            # Check if reply is from author
            def mcheck(message: discord.Message):
                return message.author == ctx.author and message.channel == ctx.channel

            try:
                reply = await self.bot.wait_for("message", timeout=60, check=mcheck)
            except asyncio.TimeoutError:
                return await msg.edit(embed=discord.Embed(description="You took too long :yawning_face:"))
            if reply.content.lower() == "cancel":
                return await msg.edit(embed=discord.Embed(description="Game search canceled."))
            titles = game_data["titles"]
            gamelist = []
            for title in titles:
                name = title["name"]
                if reply.content.lower() in name.lower():
                    gs = f'{title["currentGamerscore"]}/{title["maxGamerscore"]}'
                    gamelist.append((name, title["titleId"], gs))
            if len(gamelist) == 0:
                return await msg.edit(
                    embed=discord.Embed(description=f"Couldn't find {reply.content} in your game history.")
                )
            elif len(gamelist) > 1:
                txt = StringIO()
                for idx, item in enumerate(gamelist):
                    txt.write(f"**{idx + 1}.** {item[0]}\n")

                embed = discord.Embed(
                    title="Type the number of the game you want to select",
                    description=txt.getvalue(),
                    color=discord.Color.random(),
                )
                embed.set_footer(text='Reply "cancel" to close the menu')
                await msg.edit(embed=embed)
                try:
                    reply = await self.bot.wait_for("message", timeout=60, check=mcheck)
                except asyncio.TimeoutError:
                    return await msg.edit(embed=discord.Embed(description="You took too long :yawning_face:"))
                if reply.content.lower() == "cancel":
                    return await msg.edit(embed=discord.Embed(description="Game select canceled."))
                elif not reply.content.isdigit():
                    return await msg.edit(embed=discord.Embed(description="That's not a number"))
                elif int(reply.content) > len(gamelist):
                    return await msg.edit(embed=discord.Embed(description="That's not a valid number"))
                i = int(reply.content) - 1
                gamename = gamelist[i][0]
                title_id = gamelist[i][1]
                gs = gamelist[i][2]
            else:
                gamename = gamelist[0][0]
                title_id = gamelist[0][1]
                gs = gamelist[0][2]

            url, header, payload = stats_api_format(token, title_id, xuid)
            async with self.session.post(url=url, headers=header, data=payload) as res:
                game_stats = await res.json(content_type=None)
            title = await xbl_client.titlehub.get_title_info(title_id)
            title_info = title.model_dump(mode="json") if V2 else json.loads(title.json())
            achievements = await xbl_client.achievements.get_achievements_xboxone_gameprogress(xuid, title_id)
            achievement_data = achievements.model_dump(mode="json") if V2 else json.loads(achievements.json())
            data = {
                "stats": game_stats,
                "info": title_info,
                "achievements": achievement_data,
            }
            pages = game_embeds(gt, gamename, gs, data)
            await msg.delete()
            await menu(ctx, pages, DEFAULT_CONTROLS)

    @commands.command(name="xfriends")
    @commands.bot_has_permissions(embed_links=True)
    async def get_friends(self, ctx, *, gamertag=None):
        """View your friends list"""
        async with ctx.typing():
            if not gamertag:
                gamertag = await self.pull_user(ctx)
                if not gamertag:
                    return
            async with SignedSession() as session:
                xbl_client = await self.auth_manager(session, ctx)
                if not xbl_client:
                    return
                embed = discord.Embed(
                    description="Gathering data...",
                    color=discord.Color.random(),
                )
                embed.set_thumbnail(url=LOADING)
                msg = await ctx.send(embed=embed)
                try:
                    pdata = await xbl_client.profile.get_profile_by_gamertag(gamertag)
                    profile_data = pdata.model_dump(mode="json") if V2 else json.loads(pdata.json())
                except aiohttp.ClientResponseError:
                    embed = discord.Embed(description="Invalid Gamertag. Try again.")
                    return await msg.edit(embed=embed)
                except Exception as e:
                    if "Forbidden" in str(e):
                        embed = discord.Embed(description="Failed to gather data, Gamertag may be set to private.")
                        return await msg.edit(embed=embed)
                    embed = discord.Embed(description=f"Failed to gather data!\nError: {box(str(e), 'py')}")
                    return await msg.edit(embed=embed)
                gt, xuid, _, _, _, _, _, _, _ = profile(profile_data)
                try:
                    friends = await xbl_client.people.get_friends_by_xuid(xuid)
                    friend_data = friends.model_dump(mode="json") if V2 else json.loads(friends.json())
                except aiohttp.ClientResponseError as e:
                    if e.status == 403:
                        return await msg.edit(embed=None, content="This persons friends list is private!")
                    log.error("Failed to get friends list", exc_info=e)
                    return await msg.edit(embed=None, content="Failed to fetch this person's friends list!")
                self.cache[str(ctx.author.id)] = friend_data
                pages = friend_embeds(friend_data, gt)
                if len(pages) == 0:
                    embed = discord.Embed(description=f"No friends found for {gamertag}.")
                    return await msg.edit(embed=embed)
                await msg.delete()

                search_con = DEFAULT_CONTROLS.copy()
                search_con["\N{LEFT-POINTING MAGNIFYING GLASS}"] = self.searching
                await menu(ctx, pages, search_con)

    async def searching(self, instance, interaction):
        ctx = instance.ctx
        data = self.cache[str(ctx.author.id)]
        embed = discord.Embed(
            description="Type in a Gamertag to search",
            color=discord.Color.random(),
        )
        embed.set_footer(text='Reply "cancel" to close the menu')
        await instance.respond_embed(interaction, embed)
        msg = interaction.message
        await msg.edit(view=None)

        # Check if reply is from author
        def mcheck(message: discord.Message):
            return message.author == ctx.author and message.channel == ctx.channel

        try:
            reply = await self.bot.wait_for("message", timeout=60, check=mcheck)
        except asyncio.TimeoutError:
            return await msg.edit(embed=discord.Embed(description="You took too long :yawning_face:"))
        if reply.content.lower() == "cancel":
            return await msg.edit(embed=discord.Embed(description="Search canceled."))
        players = []
        for player in data["people"]:
            if reply.content.lower() in player["gamertag"].lower():
                players.append(player["gamertag"])
        if len(players) == 0:
            return await msg.edit(embed=discord.Embed(description=f"Couldn't find {reply.content} in friends list."))

        elif len(players) > 1:
            flist = ""
            count = 1
            for gt in players:
                flist += f"**{count}.** {gt}\n"
                count += 1
            embed = discord.Embed(
                title="Multiple Gamertag's match that name, Type the number to select the one you want",
                description=flist,
                color=discord.Color.random(),
            )
            embed.set_footer(text='Reply "cancel" to close the menu')
            await msg.edit(embed=embed)
            try:
                reply = await self.bot.wait_for("message", timeout=60, check=mcheck)
            except asyncio.TimeoutError:
                return await msg.edit(embed=discord.Embed(description="You took too long :yawning_face:"))
            if reply.content.lower() == "cancel":
                return await msg.edit(embed=discord.Embed(description="Selection canceled."))
            elif not reply.content.isdigit():
                return await msg.edit(embed=discord.Embed(description="That's not a number"))
            elif int(reply.content) > len(players):
                return await msg.edit(embed=discord.Embed(description="That's not a valid number"))
            i = int(reply.content) - 1
            gt = players[i]
        else:
            gt = players[0]
        await msg.delete()
        return await self.get_profile(ctx, gamertag=gt)

    # Gets player game clips
    @commands.command(name="xclips")
    @commands.bot_has_permissions(embed_links=True)
    async def get_clips(self, ctx, *, gamertag=None):
        """View your game clips"""
        if not gamertag:
            gamertag = await self.pull_user(ctx)
            if not gamertag:
                return
        async with SignedSession() as session:
            xbl_client = await self.auth_manager(session, ctx)
            if not xbl_client:
                return
            embed = discord.Embed(description="Gathering data...", color=discord.Color.random())
            embed.set_thumbnail(url=LOADING)
            msg = await ctx.send(embed=embed)
            try:
                pdata = await xbl_client.profile.get_profile_by_gamertag(gamertag)
                profile_data = pdata.model_dump(mode="json") if V2 else json.loads(pdata.json())
            except aiohttp.ClientResponseError:
                embed = discord.Embed(description="Invalid Gamertag. Try again.")
                return await msg.edit(embed=embed)
            gt, xuid, _, _, _, _, _, _, _ = profile(profile_data)
            try:
                clips = await xbl_client.gameclips.get_saved_clips_by_xuid(xuid)
                data = clips.model_dump(mode="json") if V2 else json.loads(clips.json())
            except Exception as e:
                if "Forbidden" in str(e):
                    embed = discord.Embed(
                        color=discord.Color.red(),
                        description="Your privacy settings might be blocking your game clips.\n"
                        "**[Click Here](https://account.xbox.com/en-gb/Settings)** to change your settings.",
                    )
                    return await msg.edit(embed=embed)
                else:
                    embed = discord.Embed(
                        color=discord.Color.red(),
                        description=f"Unknown error while fetching xclip data: {e}",
                    )
                    return await msg.edit(embed=embed)
            pages = gameclip_embeds(data, gamertag)
            if len(pages) == 0:
                color = discord.Color.red()
                embed = discord.Embed(description="No game clips found", color=color)
                return await msg.edit(embed=embed)
            await msg.delete()
            await menu(ctx, pages, DEFAULT_CONTROLS)

    @commands.command(name="xstatus")
    async def get_microsoft_status(self, ctx: commands.Context):
        """Check Microsoft Services Status"""
        data = await self.microsoft_services_status()
        if ctx.author.id == 350053505815281665 and ctx.channel.permissions_for(ctx.me).attach_files:
            file = discord.File(BytesIO(json.dumps(data).encode()), filename="status.json")
            await ctx.send(file=file)
        embeds = ms_status(data)
        for embed in embeds:
            await ctx.send(embed=embed)

    @commands.command(name="gameswithgold")
    async def get_gameswithgold(self, ctx: commands.Context):
        """View this month's free games with Gold"""
        url = (
            "https://reco-public.rec.mp.microsoft.com/channels/Reco/V8.0/Lists/"
            "Collection/GamesWithGold?ItemTypes=Game&Market=US&deviceFamily=Windows.Xbox"
        )
        async with self.session.post(url=url) as res:
            async with ctx.typing():
                games_raw = await res.json(content_type=None)
                game_ids = []
                for game in games_raw["Items"]:
                    game_ids.append(game["Id"])
                if len(game_ids) == 0:
                    return await ctx.send("No games found!")
                async with SignedSession() as session:
                    xbl_client = await self.auth_manager(session, ctx)
                    if not xbl_client:
                        return
                    game = await xbl_client.catalog.get_products(game_ids)
                    game_data = game.model_dump(mode="json") if V2 else json.loads(game.json())
                    products = game_data["products"]
                    pages = gwg_embeds(products)
                    return await menu(ctx, pages, DEFAULT_CONTROLS)

    @commands.command(name="xmostplayed")
    @commands.bot_has_permissions(embed_links=True)
    async def get_mostplayed(self, ctx, *, gamertag=None):
        """View your most played games"""
        if not gamertag:
            gamertag = await self.pull_user(ctx)
            if not gamertag:
                return
        async with SignedSession() as session:
            xbl_client = await self.auth_manager(session, ctx)
            if not xbl_client:
                return
            embed = discord.Embed(description="Gathering data...", color=discord.Color.random())
            embed.set_thumbnail(url=LOADING)
            msg = await ctx.send(embed=embed)
            try:
                pdata = await xbl_client.profile.get_profile_by_gamertag(gamertag)
                profile_data = pdata.model_dump(mode="json") if V2 else json.loads(pdata.json())
            except aiohttp.ClientResponseError:
                embed = discord.Embed(description="Invalid Gamertag. Try again.")
                return await msg.edit(embed=embed)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    embed = discord.Embed(description="Invalid Gamertag. Try again.")
                    return await msg.edit(embed=embed)
                embed = discord.Embed(description=f"Failed to gather data!\nError: {box(str(e), 'py')}")
                return await msg.edit(embed=embed)
            gt, xuid, _, _, _, _, _, _, _ = profile(profile_data)

            token = await self.get_token(session)
            header = {
                "x-xbl-contract-version": "2",
                "Authorization": token,
                "Accept-Language": "en-US",
            }
            url = f"https://achievements.xboxlive.com/users/xuid({xuid})/history/titles"

            # Keep pulling continuation token till all data is obtained
            running = True
            params = None
            game_data = {"titles": []}
            while running:
                async with self.session.get(url=url, headers=header, params=params) as res:
                    data = await res.json(content_type=None)
                    c_token = data["pagingInfo"]["continuationToken"]
                    titles = data["titles"]
                    game_data["titles"].extend(titles)
                    if not c_token:
                        running = False
                    else:
                        params = {"continuationToken": c_token}
            if len(game_data["titles"]) == 0:
                embed = discord.Embed(
                    color=discord.Color.red(),
                    description="Your privacy settings are blocking your gameplay history.\n"
                    "**[Click Here](https://account.xbox.com/en-gb/Settings)** to change your settings.",
                )
                return await msg.edit(embed=embed)

            titles = game_data["titles"]
            embed = discord.Embed(
                description=f"Found `{len(titles)}` titles..",
                color=discord.Color.random(),
            )
            embed.set_thumbnail(url=LOADING)
            await msg.edit(embed=embed)
            most_played = {}
            async with ctx.typing():
                cant_find = ""
                not_found = False
                for title in titles:
                    title_id = title["titleId"]
                    apptype = title["titleType"]
                    if apptype != "LiveApp":
                        url, header, payload = stats_api_format(token, title_id, xuid)
                        async with self.session.post(url=url, headers=header, data=payload) as res:
                            data = await res.json(content_type=None)
                        most_played[title["name"]] = 0
                        if len(data["statlistscollection"][0]["stats"]) > 0:
                            if "value" in data["statlistscollection"][0]["stats"][0]:
                                most_played[title["name"]] = int(data["statlistscollection"][0]["stats"][0]["value"])
                            else:
                                not_found = True
                                cant_find += f"{title['name']}\n"
            pages = mostplayed(most_played, gt)
            if not_found:
                embed = discord.Embed(description=f"Couldn't find playtime data for:\n" f"{box(cant_find)}")
                await msg.edit(embed=embed)
            else:
                await msg.delete()

            return await menu(ctx, pages, DEFAULT_CONTROLS)

    @tasks.loop(seconds=60)
    async def status(self):
        try:
            res = await self.microsoft_services_status()
        except Exception:
            log.error(f"Status error: {traceback.format_exc()}")
            return

        embeds = ms_status(res)
        # data = res["ServiceStatus"]["Status"]["Overall"]
        key = "".join([e.description for e in embeds])
        if self.alert is None:
            self.alert = key
            return
        elif self.alert == key:
            return

        # Key doesn't match cached key, send updated status and cache new key
        for guild in self.bot.guilds:
            cid = await self.config.guild(guild).statuschannel()
            if not cid:
                continue
            channel = guild.get_channel(cid)
            if not channel:
                continue
            with contextlib.suppress(discord.Forbidden, discord.HTTPException):
                for e in embeds:
                    await channel.send(embed=e)

        self.alert = key

    @status.before_loop
    async def before_status_loop(self):
        await self.bot.wait_until_red_ready()

    @commands.Cog.listener()
    async def on_assistant_cog_add(self, cog: commands.Cog):
        schema = {
            "name": "get_gamertag_profile",
            "description": "Get details about an Xbox Gamertag profile like gamerscore, bio, followers, ect..",
            "parameters": {
                "type": "object",
                "properties": {
                    "gamertag": {
                        "type": "string",
                        "description": "name of the person's xbox gamertag, fetches set gamertag for user chatting if none provided",
                    },
                },
            },
        }
        await cog.register_function("XTools", schema)

    async def get_gamertag_profile(self, user: discord.Member, gamertag: str = None, *args, **kwargs):
        async with SignedSession() as session:
            if not gamertag:
                users = await self.config.users()
                if str(user.id) not in users:
                    return "No gamertag has been set for this user, please specify a gamertag"
                gamertag = users[str(user.id)]["gamertag"]
            xbl_client = await self.auth_manager(session)
            if not xbl_client:
                return "Could not communicate with XSAPI"

            try:
                pdata = await xbl_client.profile.get_profile_by_gamertag(gamertag)
                profile_data = pdata.model_dump(mode="json") if V2 else json.loads(pdata.json())
            except aiohttp.ClientResponseError:
                return "Invalid Gamertag. Try again."

            _, xuid, _, _, _, _, _, _, _ = profile(profile_data)
            friends = await xbl_client.people.get_friends_summary_by_gamertag(gamertag)
            friends_data = friends.model_dump(mode="json") if V2 else json.loads(friends.json())

            # Manually get presence and activity info since xbox webapi method is outdated
            token = await self.get_token(session)
            header = {
                "x-xbl-contract-version": "3",
                "Authorization": token,
                "Accept": "application/json",
                "Accept-Language": "en-US",
                "Host": "presencebeta.xboxlive.com",
            }
            url = f"https://userpresence.xboxlive.com/users/xuid({xuid})"
            async with self.session.get(url=url, headers=header) as res:
                presence_data = await res.json(content_type=None)
            url = f"https://avty.xboxlive.com/users/xuid({xuid})/Activity/History?numItems=5&excludeTypes=TextPost"
            async with self.session.get(url=url, headers=header) as res:
                activity_data = await res.json(content_type=None)
            profile_data["friends"] = friends_data
            profile_data["presence"] = presence_data
            profile_data["activity"] = activity_data["activityItems"]
            embed = profile_embed(profile_data)
            reply = f"{embed.title}\n"
            for field in embed.fields:
                reply += f"{field.name}\n{field.value}\n\n"
            return reply
