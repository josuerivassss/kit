import datetime
from discord.ext import commands
from core.kernel import KitBot, KitContext

class Events(commands.Cog):
    def __init__(self, bot: KitBot):
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Emits when kit is ready"""
        print(f"{self.bot.user.display_name} is online.")
        
    @commands.Cog.listener()
    async def on_command_error(self, ctx: KitContext, error: commands.CommandError):
        T = await ctx.get_locale()
        
        if isinstance(error, commands.CommandOnCooldown):
            return await ctx.answer(f"{T.get('errors.onCooldown')}", hint=T.get("errors.onCooldownHint", time=round(error.retry_after, 2)), type="error", deleteAfter=5)
        elif isinstance(error, commands.MissingRequiredArgument):
            return await ctx.answer(f"{T.get('errors.missingArgument')}", hint=T.get("errors.missingArgumentHint", argument=error.param.name), type="error")
        elif isinstance(error, commands.UserNotFound):
            return await ctx.answer(f"{T.get('errors.userNotFound', user=error.argument)}", hint=T.get("errors.userNotFoundHint"), type="error")
        elif isinstance(error, commands.MemberNotFound):
            return await ctx.answer(f"{T.get('errors.memberNotFound', member=error.argument)}", hint=T.get("errors.memberNotFoundHint"), type="error")
        elif isinstance(error, commands.ChannelNotFound):
            return await ctx.answer(f"{T.get('errors.channelNotFound', channel=error.argument)}", hint=T.get("errors.channelNotFoundHint"), type="error")
        elif isinstance(error, commands.RoleNotFound):
            return await ctx.answer(f"{T.get('errors.roleNotFound', role=error.argument)}", hint=T.get("errors.roleNotFoundHint"), type="error")
        elif isinstance(error, commands.BadArgument):
            return await ctx.answer(f"{T.get('errors.badArgument')}", hint=T.get("errors.badArgumentHint", argument=error.param.name if hasattr(error, 'param') else 'unknown'), type="error")
        elif isinstance(error, commands.CommandNotFound):
            return
        elif isinstance(error, commands.MissingPermissions):
            missing = ", ".join(error.missing_permissions)
            return await ctx.answer(f"{T.get('errors.missingPermissions')}", hint=T.get("errors.missingPermissionsHint", permissions=missing), type="error", bold=False)
        elif isinstance(error, commands.BotMissingPermissions):
            missing = ", ".join(error.missing_permissions)
            return await ctx.answer(f"{T.get('errors.botMissingPermissions')}", hint=T.get("errors.botMissingPermissionsHint", permissions=missing), type="error", bold=False)
        elif isinstance(error, commands.NoPrivateMessage):
            return await ctx.answer(f"{T.get('errors.noDM')}", hint=T.get("errors.noDMHint"), type="error")
        elif isinstance(error, commands.CommandError):
            message = error.args[0] if error.args else T.get('errors.unexpectedError')
            hint = error.args[1] if len(error.args) > 1 else ''
            if hint:
                return await ctx.answer(f"{message}\n-# {hint}", type="error")
            else:
                return await ctx.answer(message, type="error")
        else:
            await ctx.answer(f"{T.get('errors.unexpectedError')}", hint=T.get("errors.unexpectedErrorHint"), type="error", deleteAfter=10)
            print(f"Error in command {ctx.command}:")
            import traceback
            traceback.print_exception(type(error), error, error.__traceback__)
    
    @commands.Cog.listener()
    async def on_error(self, event_method, *args, **kwargs):
        """Emits when an error occurs outside commands"""
        print(f"Error in {event_method}:")
        import traceback
        traceback.print_exc()
    

async def setup(bot: KitBot):
    await bot.add_cog(Events(bot))
