import discord
import asyncio
import json
import xmltojson

from redbot.core import commands, Config

import aiohttp

from xbox.webapi.authentication.manager import AuthenticationManager
from xbox.webapi.authentication.models import OAuth2TokenResponse
from xbox.webapi.api.client import XboxLiveClient

from .menus import (menu,
                    DEFAULT_CONTROLS,
                    next_page,
                    prev_page,
                    skip_ten,
                    back_ten,
                    close_menu)

from .formatter import (profile,
                        profile_embed,
                        screenshot_embeds,
                        game_embeds,
                        friend_embeds,
                        gameclip_embeds,
                        status,
                        gwg_embeds,
                        mostplayed)

REDIRECT_URI = "http://localhost/auth/callback"
LOADING = "https://i.imgur.com/l3p6EMX.gif"


class XTools(commands.Cog):
    """
    Cool Tools for Xbox
    """

    __author__ = "Vertyco"
    __version__ = "3.3.6"

    def format_help_for_context(self, ctx):
        helpcmd = super().format_help_for_context(ctx)
        return f"{helpcmd}\nCog Version: {self.__version__}\nAuthor: {self.__author__}"
        # formatted for when you type [p]help Xbox

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.config = Config.get_conf(self, 117117117117, force_registration=True)
        default_global = {
            "tokens": {},
            "clientid": None,
            "clientsecret": None,
            "users": {}
        }
        self.config.register_global(**default_global)

        # Caching friend list for searching
        self.cache = {}

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())

    # Get Microsoft services status
    async def microsoft_services_status(self):
        async with aiohttp.ClientSession() as session:
            async with session.get("https://xnotify.xboxlive.com/servicestatusv6/US/en-US") as resp:
                data = xmltojson.parse(await resp.text())  # Parse HTML response to JSON
                data = json.loads(data)
                return data

    # General authentication manager
    async def auth_manager(self, ctx, session):
        tokens = await self.config.tokens()
        client_id = await self.config.clientid()
        client_secret = await self.config.clientsecret()
        if not client_id:
            await ctx.send(f"Client ID and Secret have not been set yet!\n"
                           f"Bot owner needs to run `{ctx.prefix}apiset tokens`")
            return None
        auth_mgr = AuthenticationManager(
            session, client_id, client_secret, REDIRECT_URI
        )
        if tokens == {}:
            if ctx.author.id in self.bot.owner_ids:
                url = "https://login.live.com/oauth20_authorize.srf?"
                cid = f"client_id={client_id}"
                types = "&response_type=code&approval_prompt=auto"
                scopes = "&scope=Xboxlive.signin+Xboxlive.offline_access&"
                redirect_uri = "&redirect_uri=http://localhost/auth/callback"
                auth_url = f"{url}{cid}{types}{scopes}{redirect_uri}"
                await ctx.send("Sending you a DM to authorize your tokens.")
                await self.ask_auth(ctx, ctx.author, auth_url)
                return None
            else:
                await ctx.send(f"Tokens have not been authorized by bot owner yet!")
                return None
        try:
            auth_mgr.oauth = OAuth2TokenResponse.parse_raw(json.dumps(tokens))
        except Exception as e:
            if "validation error" in str(e):
                await ctx.send(f"Tokens have not been authorized by bot owner yet!")
                return None
        await auth_mgr.refresh_tokens()
        await self.config.tokens.set(json.loads(auth_mgr.oauth.json()))
        xbl_client = XboxLiveClient(auth_mgr)
        return xbl_client

    # Send user DM asking for authentication
    async def ask_auth(self, ctx, author: discord.User, auth_url):
        plz_auth = f"Please follow this link to authorize your tokens with Microsoft.\n" \
                   f"Copy the ENTIRE contents of the address bar after you authorize, " \
                   f"and reply to this message with what you copied.\n" \
                   f"{auth_url}"
        await author.send(plz_auth)

        def check(message):
            return message.author == ctx.author

        try:
            reply = await self.bot.wait_for("message", check=check, timeout=120)
        except asyncio.TimeoutError:
            return await author.send("Authorization timeout.")

        if "code" in reply.content:
            code = reply.content.split("code=")[-1]
        else:
            return await author.send("Invalid response")

        client_id = await self.config.clientid()
        client_secret = await self.config.clientsecret()

        async with aiohttp.ClientSession() as session:
            auth_mgr = AuthenticationManager(
                session, client_id, client_secret, REDIRECT_URI
            )
            try:
                await auth_mgr.request_tokens(code)
                await self.config.tokens.set(json.loads(auth_mgr.oauth.json()))
            except Exception as e:
                if "Bad Request" in str(e):
                    return await author.send("Bad Request")
                return await author.send(f"Authorization failed: {e}")
            await author.send("Your authorization has been verified✅")

    # Get XSTS token
    async def get_token(self, session):
        tokens = await self.config.tokens()
        client_id = await self.config.clientid()
        client_secret = await self.config.clientsecret()
        auth_mgr = AuthenticationManager(
            session, client_id, client_secret, REDIRECT_URI
        )
        auth_mgr.oauth = OAuth2TokenResponse.parse_raw(json.dumps(tokens))
        await auth_mgr.refresh_tokens()
        await self.config.tokens.set(json.loads(auth_mgr.oauth.json()))
        token = auth_mgr.xsts_token.authorization_header_value
        return token

    # Pulls user info if theyve set a Gamertag
    async def pull_user(self, ctx):
        users = await self.config.users()
        if str(ctx.author.id) not in users:
            await ctx.send(f"You haven't set your Gamertag yet! To set a Gamertag type `{ctx.prefix}setgt`\n"
                           f"Alternatively, you can type the command and include a Gamertag.")
            return None
        return users[str(ctx.author.id)]["gamertag"]

    @commands.group(name="apiset")
    @commands.is_owner()
    async def api_settings(self, ctx):
        """Setup the XTools cog"""
        pass

    @api_settings.command(name="help")
    async def get_help(self, ctx):
        """Tutorial for getting your ClientID and Secret"""
        embed = discord.Embed(
            description="**How to get your Client ID and Secret**",
            color=discord.Color.magenta()
        )
        embed.add_field(
            name="Step 1",
            value="• Register a new application in "
                  "[Azure AD](https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps/ApplicationsListBlade)",
            inline=False
        )
        embed.add_field(
            name="Step 2",
            value="• Name your app\n"
                  "• Select `Personal Microsoft accounts only` under supported account types\n"
                  "• Add http://localhost/auth/callback as a Redirect URI of type `Web`",
            inline=False
        )
        embed.add_field(
            name="Step 3",
            value="• Copy your Application (client) ID and save it for setting your tokens",
            inline=False
        )
        embed.add_field(
            name="Step 4",
            value="• On the App Page, navigate to `Certificates & secrets`\n"
                  "• Generate a new client secret and save it for setting your tokens\n",
            inline=False
        )
        embed.add_field(
            name="Step 5",
            value=f"• Type `{ctx.prefix}apiset tokens` and include your Client ID and Secret\n",
            inline=False
        )
        embed.add_field(
            name="Step 6",
            value=f"• Try any command and the bot will DM you the link with instructions to authorize your tokens",
            inline=False
        )
        embed.set_footer(text='Hint: The "Value" for the secret is what you use, NOT the "Secret ID"')
        await ctx.send(embed=embed)

    @api_settings.command(name="tokens")
    async def set_tokens(self, ctx, client_id, client_secret):
        """Set Client ID and Secret"""
        await self.config.clientid.set(client_id)
        await self.config.clientsecret.set(client_secret)
        await ctx.send(f"Tokens have been set! Run `{ctx.prefix}apiset authorize` to authorize your tokens")
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            await ctx.send("I do not have permissions to delete your message!")
        except discord.NotFound:
            print("Where dafuq did the message go?")

    @commands.command(name="setgt")
    async def set_gamertag(self, ctx: commands, *, gamertag):
        """Set your Gamertag to use commands without entering it"""
        async with ctx.typing():
            async with aiohttp.ClientSession() as session:
                xbl_client = await self.auth_manager(ctx, session)
                if not xbl_client:
                    return
                try:
                    profile_data = json.loads((await xbl_client.profile.get_profile_by_gamertag(gamertag)).json())
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
        # If user didnt enter Gamertag, check if theyve set one
        if not gamertag:
            gamertag = await self.pull_user(ctx)
            if not gamertag:
                return
        async with aiohttp.ClientSession() as session:
            xbl_client = await self.auth_manager(ctx, session)
            if not xbl_client:
                return
            try:
                profile_data = json.loads((await xbl_client.profile.get_profile_by_gamertag(gamertag)).json())
            except aiohttp.ClientResponseError:
                return await ctx.send("Invalid Gamertag. Try again.")
            _, xuid, _, _, _, _, _, _, _ = profile(profile_data)
            return await ctx.send(f"`{xuid}`")

    @commands.command(name="gamertag")
    async def get_gamertag(self, ctx, *, xuid):
        """Get the Gamertag associated with an XUID"""
        async with aiohttp.ClientSession() as session:
            xbl_client = await self.auth_manager(ctx, session)
            if not xbl_client:
                return
            try:
                profile_data = json.loads((await xbl_client.profile.get_profile_by_xuid(xuid)).json())
            except aiohttp.ClientResponseError:
                return await ctx.send("Invalid XUID. Try again.")
            gt, _, _, _, _, _, _, _, _ = profile(profile_data)
            return await ctx.send(f"`{gt}`")

    @commands.command(name="xprofile")
    async def get_profile(self, ctx, *, gamertag: str = None):
        """View your Xbox profile"""
        # If user didnt enter Gamertag, check if theyve set one
        if not gamertag:
            gamertag = await self.pull_user(ctx)
            if not gamertag:
                return
        async with aiohttp.ClientSession() as session:
            xbl_client = await self.auth_manager(ctx, session)
            if not xbl_client:
                return
            embed = discord.Embed(
                description="Gathering data...",
                color=discord.Color.random()
            )
            embed.set_thumbnail(url=LOADING)
            msg = await ctx.send(embed=embed)
            try:
                profile_data = json.loads((await xbl_client.profile.get_profile_by_gamertag(gamertag)).json())
            except aiohttp.ClientResponseError:
                embed = discord.Embed(description="Invalid Gamertag. Try again.")
                return await msg.edit(embed=embed)
            _, xuid, _, _, _, _, _, _, _ = profile(profile_data)
            friends_data = json.loads((await xbl_client.people.get_friends_summary_by_gamertag(gamertag)).json())

            # Manually get presence and activity info since xbox webapi method is outdated
            token = await self.get_token(session)
            header = {"x-xbl-contract-version": "3",
                      "Authorization": token,
                      "Accept": "application/json",
                      "Accept-Language": "en-US",
                      "Host": "presencebeta.xboxlive.com"
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
    async def get_screenshots(self, ctx, *, gamertag=None):
        """View your Screenshots"""
        if not gamertag:
            gamertag = await self.pull_user(ctx)
            if not gamertag:
                return
        async with aiohttp.ClientSession() as session:
            xbl_client = await self.auth_manager(ctx, session)
            if not xbl_client:
                return
            embed = discord.Embed(
                description="Gathering data...",
                color=discord.Color.random()
            )
            embed.set_thumbnail(url=LOADING)
            msg = await ctx.send(embed=embed)
            try:
                profile_data = json.loads((await xbl_client.profile.get_profile_by_gamertag(gamertag)).json())
            except aiohttp.ClientResponseError:
                embed = discord.Embed(description="Invalid Gamertag. Try again.")
                return await msg.edit(embed=embed)
            _, xuid, _, _, _, _, _, _, _ = profile(profile_data)
            data = json.loads(
                (await xbl_client.screenshots.get_saved_screenshots_by_xuid(xuid=xuid, max_items=10000)).json())
            pages = screenshot_embeds(data, gamertag)
            if len(pages) == 0:
                color = discord.Color.red()
                embed = discord.Embed(description="No screenshots found", color=color)
                return await msg.edit(embed=embed)
            await msg.delete()
            await menu(ctx, pages, DEFAULT_CONTROLS)

    @commands.command(name="xgames")
    async def get_games(self, ctx, *, gamertag=None):
        """View your games and achievements"""
        if not gamertag:
            gamertag = await self.pull_user(ctx)
            if not gamertag:
                return
        async with aiohttp.ClientSession() as session:
            xbl_client = await self.auth_manager(ctx, session)
            if not xbl_client:
                return
            embed = discord.Embed(
                description="Gathering data...",
                color=discord.Color.random()
            )
            embed.set_thumbnail(url=LOADING)
            msg = await ctx.send(embed=embed)
            try:
                profile_data = json.loads((await xbl_client.profile.get_profile_by_gamertag(gamertag)).json())
            except aiohttp.ClientResponseError:
                embed = discord.Embed(description="Invalid Gamertag. Try again.")
                return await msg.edit(embed=embed)
            gt, xuid, _, _, _, _, _, _, _ = profile(profile_data)

            token = await self.get_token(session)
            header = {"x-xbl-contract-version": "2",
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
                                "**[Click Here](https://account.xbox.com/en-gb/Settings)** to change your settings."
                )
                return await msg.edit(embed=embed)

            embed = discord.Embed(
                description="What game would you like to search for?",
                color=discord.Color.random()
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
                    embed=discord.Embed(description=f"Couldn't find {reply.content} in your game history."))
            elif len(gamelist) > 1:
                games = ""
                count = 1
                for item in gamelist:
                    games += f"**{count}.** {item[0]}\n"
                    count += 1
                embed = discord.Embed(
                    title="Type the number of the game you want to select",
                    description=games,
                    color=discord.Color.random()
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

            header = {"x-xbl-contract-version": "2",
                      "Authorization": token,
                      "Accept": "application/json",
                      "Accept-Language": "en-US",
                      "Content-Type": "application/json"
                      }
            url = f"https://userstats.xboxlive.com/batch"
            payload = json.dumps({
                "arrangebyfield": "xuid",
                "xuids": [
                    xuid
                ],
                "groups": [
                    {
                        "name": "Hero",
                        "titleId": title_id
                    }
                ],
                "stats": [
                    {
                        "name": "MinutesPlayed",
                        "titleId": title_id
                    }
                ]
            })
            async with self.session.post(url=url, headers=header, data=payload) as res:
                game_stats = await res.json(content_type=None)

            title_info = json.loads((await xbl_client.titlehub.get_title_info(title_id)).json())
            achievement_data = json.loads(
                (await xbl_client.achievements.get_achievements_xboxone_gameprogress(xuid, title_id)).json())
            data = {
                "stats": game_stats,
                "info": title_info,
                "achievements": achievement_data
            }
            pages = game_embeds(gt, gamename, gs, data)
            await msg.delete()
            await menu(ctx, pages, DEFAULT_CONTROLS)

    @commands.command(name="xfriends")
    async def get_friends(self, ctx, *, gamertag=None):
        """View your friends list"""
        if not gamertag:
            gamertag = await self.pull_user(ctx)
            if not gamertag:
                return
        async with aiohttp.ClientSession() as session:
            xbl_client = await self.auth_manager(ctx, session)
            if not xbl_client:
                return
            embed = discord.Embed(
                description="Gathering data...",
                color=discord.Color.random()
            )
            embed.set_thumbnail(url=LOADING)
            msg = await ctx.send(embed=embed)
            try:
                profile_data = json.loads((await xbl_client.profile.get_profile_by_gamertag(gamertag)).json())
            except aiohttp.ClientResponseError:
                embed = discord.Embed(description="Invalid Gamertag. Try again.")
                return await msg.edit(embed=embed)
            gt, xuid, _, _, _, _, _, _, _ = profile(profile_data)
            friend_data = json.loads((await xbl_client.people.get_friends_by_xuid(xuid)).json())
            self.cache[str(ctx.author.id)] = friend_data
            pages = friend_embeds(friend_data, gt)
            if len(pages) == 0:
                embed = discord.Embed(
                    description=f"No friends found for {gamertag}."
                )
                return await msg.edit(embed=embed)
            await msg.delete()

            search_controls = {
                "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE}": back_ten,
                "\N{LEFTWARDS BLACK ARROW}\N{VARIATION SELECTOR-16}": prev_page,
                "\N{CROSS MARK}": close_menu,
                "\N{BLACK RIGHTWARDS ARROW}\N{VARIATION SELECTOR-16}": next_page,
                "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE}": skip_ten,
                "\N{LEFT-POINTING MAGNIFYING GLASS}": self.searching,
            }
            await menu(ctx, pages, search_controls)

    async def searching(self,
                        ctx: commands.Context,
                        pages: list,
                        controls: dict,
                        msg: discord.Message,
                        page: int,
                        timeout: float,
                        emoji: str,
                        ):
        data = self.cache[str(ctx.author.id)]
        embed = discord.Embed(
            description="Type in a Gamertag to search",
            color=discord.Color.random()
        )
        embed.set_footer(text='Reply "cancel" to close the menu')
        await msg.edit(embed=embed)
        try:
            await msg.clear_reactions()
        except discord.Forbidden:
            pass

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
            return await msg.edit(
                embed=discord.Embed(description=f"Couldn't find {reply.content} in friends list."))
        elif len(players) > 1:
            flist = ""
            count = 1
            for gt in players:
                flist += f"**{count}.** {gt}\n"
                count += 1
            embed = discord.Embed(
                title="Multiple Gamertag's match that name, Type the number to select the one you want",
                description=flist,
                color=discord.Color.random()
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
    async def get_clips(self, ctx, *, gamertag=None):
        """View your game clips"""
        if not gamertag:
            gamertag = await self.pull_user(ctx)
            if not gamertag:
                return
        async with aiohttp.ClientSession() as session:
            xbl_client = await self.auth_manager(ctx, session)
            if not xbl_client:
                return
            embed = discord.Embed(
                description="Gathering data...",
                color=discord.Color.random()
            )
            embed.set_thumbnail(url=LOADING)
            msg = await ctx.send(embed=embed)
            try:
                profile_data = json.loads((await xbl_client.profile.get_profile_by_gamertag(gamertag)).json())
            except aiohttp.ClientResponseError:
                embed = discord.Embed(description="Invalid Gamertag. Try again.")
                return await msg.edit(embed=embed)
            gt, xuid, _, _, _, _, _, _, _ = profile(profile_data)
            data = json.loads((await xbl_client.gameclips.get_saved_clips_by_xuid(xuid)).json())
            pages = gameclip_embeds(data, gamertag)
            if len(pages) == 0:
                color = discord.Color.red()
                embed = discord.Embed(description="No game clips found", color=color)
                return await msg.edit(embed=embed)
            await msg.delete()
            await menu(ctx, pages, DEFAULT_CONTROLS)

    @commands.command(name="xstatus")
    async def get_microsoft_status(self, ctx):
        """Check Microsoft Services Status"""
        data = await self.microsoft_services_status()
        embed = status(data)
        await ctx.send(embed=embed)

    @commands.command(name="gameswithgold")
    async def get_gameswithgold(self, ctx):
        """View this month's free games with Gold"""
        url = f"https://reco-public.rec.mp.microsoft.com/channels/Reco/V8.0/Lists/Collection/GamesWithGold?ItemTypes=Game&Market=US&deviceFamily=Windows.Xbox"
        async with self.session.post(url=url) as res:
            async with ctx.typing():
                games_raw = await res.json(content_type=None)
                game_ids = []
                for game in games_raw["Items"]:
                    game_ids.append(game["Id"])
                if len(game_ids) == 0:
                    return await ctx.send("No games found!")
                async with aiohttp.ClientSession() as session:
                    xbl_client = await self.auth_manager(ctx, session)
                    if not xbl_client:
                        return
                    game_data = json.loads((await xbl_client.catalog.get_products(game_ids)).json())
                    products = game_data["products"]
                    pages = gwg_embeds(products)
                    return await menu(ctx, pages, DEFAULT_CONTROLS)

    @commands.command(name="xmostplayed")
    async def get_mostplayed(self, ctx, *, gamertag=None):
        """View your most played games"""
        if not gamertag:
            gamertag = await self.pull_user(ctx)
            if not gamertag:
                return
        async with aiohttp.ClientSession() as session:
            xbl_client = await self.auth_manager(ctx, session)
            if not xbl_client:
                return
            embed = discord.Embed(
                description="Gathering data...",
                color=discord.Color.random()
            )
            embed.set_thumbnail(url=LOADING)
            msg = await ctx.send(embed=embed)
            try:
                profile_data = json.loads((await xbl_client.profile.get_profile_by_gamertag(gamertag)).json())
            except aiohttp.ClientResponseError:
                embed = discord.Embed(description="Invalid Gamertag. Try again.")
                return await msg.edit(embed=embed)
            gt, xuid, _, _, _, _, _, _, _ = profile(profile_data)

            token = await self.get_token(session)
            header = {"x-xbl-contract-version": "2",
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
                                "**[Click Here](https://account.xbox.com/en-gb/Settings)** to change your settings."
                )
                return await msg.edit(embed=embed)

            titles = game_data["titles"]
            embed = discord.Embed(
                description=f"Found `{len(titles)}` titles..",
                color=discord.Color.random()
            )
            embed.set_thumbnail(url=LOADING)
            await msg.edit(embed=embed)
            most_played = {}
            for title in titles:
                scid = title["serviceConfigId"]
                apptype = title["titleType"]
                if apptype != "LiveApp":
                    data = json.loads((await xbl_client.userstats.get_stats(xuid, scid)).json())
                    most_played[title["name"]] = int(data["statlistscollection"][0]["stats"][0]["value"])
            pages = mostplayed(most_played, gt)
            await msg.delete()
            return await menu(ctx, pages, DEFAULT_CONTROLS)
