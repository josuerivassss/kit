import discord
from discord.ext import commands
from core.kernel.locale import Locale
from core.kernel.emojis import KitEmojis
from enum import StrEnum
from typing import Union

class AnswerType(StrEnum):
    Info = "info"
    Error = "error"
    Ok = "success"

class KitContext(commands.Context):

    async def get_language(self) -> str:
        if self.guild is None:
            return self.bot.language.default_language
        else:
            lang = await self.bot.db.get(table="guilds", id=self.guild.id, path="language")
            if lang is None:
                return self.bot.language.default_language
            return lang

    async def get_locale(self) -> Locale:
        lang = await self.get_language()
        return self.bot.language.get_locale(lang)
    
    async def answer(
        self, 
        message: str, 
        type: AnswerType = AnswerType.Error, 
        emoji: Union[bool | discord.Emoji] = True, 
        ephemeral: bool = True, 
        deleteAfter: int = 0, 
        bold: bool = True, 
        view: discord.ui.View | None = None,
        hint: str = None
    ):
        """
        Send a formatted answer message.
        
        Args:
            message: Text to send
            type: Message type ('success', 'error', 'info')
            withEmoji: Add emoji prefix based on type
            ephemeral: Send as ephemeral message (interactions only)
            deleteAfter: Auto-delete after N seconds (0 = don't delete)
            bold: Wrap message in bold markdown
            view: Discord UI view to attach
            hint: Additional hint text
        """
        if bold:
            message = f"**{message}**"
        
        if emoji:
            if isinstance(emoji, discord.Emoji):
                message = f"{message} {emoji}"
            else:
                emojis = {
                    AnswerType.Ok: KitEmojis.Heart,
                    AnswerType.Error: KitEmojis.Crying,
                    AnswerType.Info: KitEmojis.Confused
                }
                message = f"{message} {emojis.get(type, "")}"
        
        if hint:
            message = f"{message}\n-# {hint}"
        
        sent = await self.send(message, ephemeral=ephemeral, view=view)
        
        if deleteAfter > 0:
            await sent.delete(delay=deleteAfter)
        
        return sent
    
    async def render(self, template: str):
        """
        Renders a template string using the interpolation engine.
        
        Args:
            template: Template string with placeholders
            
        Returns:
            RenderResult object with content, embeds, and emojis
            
        Example:
            result = await ctx.render("{embed.title:Welcome {user.name}}")
            await ctx.send_render(result)
        """
        if not hasattr(self.bot.toolkit, "interpolation"):
            raise RuntimeError("Interpolation engine not initialized on bot")
        
        return await self.bot.toolkit.interpolation.render(template, self)
    
    async def send_render(
        self,
        template: str = None,
        result = None,
        ephemeral: bool = False,
        delete_after: int = None,
        view: discord.ui.View = None,
        allowed_mentions: discord.AllowedMentions = None
    ):
        """
        Sends a message from a template or RenderResult.
        
        Args:
            template: Template string (if result not provided)
            result: Pre-rendered RenderResult (if template not provided)
            ephemeral: Send as ephemeral (interactions only)
            delete_after: Auto-delete after N seconds
            view: Discord UI view to attach
            allowed_mentions: Mention restrictions
            
        Returns:
            Sent message object
            
        Examples:
            # From template string
            await ctx.send_render("{embed.title:Hello {user.name}}")
            
            # From pre-rendered result
            result = await ctx.render(template)
            await ctx.send_render(result=result)
        """
        # Render template if not already done
        if result is None:
            if template is None:
                raise ValueError("Either template or result must be provided")
            result = await self.render(template)
        
        # Prepare content (use None if empty to avoid sending empty message)
        content = result.content.strip() if result.content else None
        
        # Ensure we have something to send
        if not content and not result.embeds:
            content = "\u200b"  # Zero-width space as fallback
        
        # Send the message
        sent = await self.send(
            content=content,
            embeds=result.embeds[:10],  # Discord limit: 10 embeds
            view=view,
            ephemeral=ephemeral,
            delete_after=delete_after,
            allowed_mentions=allowed_mentions or discord.AllowedMentions.none()
        )
        
        # Add reactions from emojis list
        if result.emojis and not ephemeral:
            for emoji in result.emojis[:20]:  # Limit to 20 reactions
                try:
                    await sent.add_reaction(emoji)
                except (discord.HTTPException, discord.InvalidArgument):
                    # Invalid emoji or permission issue, skip
                    continue
        
        return sent