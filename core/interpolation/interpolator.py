"""
Main interpolation engine.

Stateless engine that converts template strings into rendered output
by discovering and invoking registered placeholder handlers.
"""

from .lexer import lex
from .interpreter import Interpreter
from .decorators import PlaceholderType
from .render_result import RenderResult


class InterpolationEngine:
    """
    Stateless interpolation engine.
    
    Each render call is isolated and thread-safe. The engine
    discovers placeholder handlers from a manager object at
    initialization and reuses them for all render calls.
    
    Usage:
        class MyPlaceholders:
            @placeholder(use=PlaceholderType.VARIABLE)
            async def user_name(self, ctx):
                return ctx.author.name
        
        engine = InterpolationEngine(MyPlaceholders())
        result = await engine.render("{user.name}", ctx)
    """

    def __init__(self, placeholder_manager):
        """
        Initialize the engine with a placeholder manager.
        
        Args:
            placeholder_manager: Object with methods decorated with @placeholder
        """
        self._variables = {}
        self._functions = {}

        # Discover all placeholder handlers
        for attr_name in dir(placeholder_manager):
            # Skip private/magic methods
            if attr_name.startswith('_'):
                continue
            
            attr = getattr(placeholder_manager, attr_name)
            
            # Check if this is a registered placeholder
            if hasattr(attr, "__placeholder_type__"):
                name = attr.__placeholder_name__
                placeholder_type = attr.__placeholder_type__
                
                if placeholder_type == PlaceholderType.VARIABLE:
                    self._variables[name] = attr
                elif placeholder_type == PlaceholderType.FUNCTION:
                    self._functions[name] = attr

    async def render(self, text: str, ctx) -> RenderResult:
        """
        Renders a template string with the given context.
        
        Args:
            text: Template string with placeholders
            ctx: Context object passed to all placeholder handlers
            
        Returns:
            RenderResult with rendered content and metadata
            
        Example:
            result = await engine.render(
                "Hello {user.name}, sum is {sum:1;2}",
                ctx
            )
            print(result.content)  # "Hello John, sum is 3"
        """
        if not text:
            return RenderResult(content="", embeds=[], emojis=[])
        
        # Parse template into AST
        nodes = lex(text)
        
        # Evaluate AST with a fresh interpreter
        interpreter = Interpreter(self._variables, self._functions)
        return await interpreter.render(nodes, ctx)
    
    def get_registered_placeholders(self) -> dict:
        """
        Returns information about registered placeholders.
        
        Returns:
            Dict with 'variables' and 'functions' keys containing
            lists of registered placeholder names
        """
        return {
            'variables': list(self._variables.keys()),
            'functions': list(self._functions.keys())
        }