"""
Decorators for registering placeholder handlers.

Allows methods to be marked as variable or function placeholders
with automatic name derivation from method names.
"""

from enum import Enum


class PlaceholderType(str, Enum):
    """
    Types of placeholders supported by the interpolation engine.
    
    VARIABLE: No arguments, direct value lookup
        Example: {user.name}
    
    FUNCTION: Accepts arguments, performs computation
        Example: {sum:1;2}
    """
    VARIABLE = "VARIABLE"
    FUNCTION = "FUNCTION"


def placeholder(*, use: PlaceholderType):
    """
    Registers a method as a placeholder handler.
    
    The placeholder name is derived from the method name,
    converting underscores to dots.
    
    Args:
        use: Type of placeholder (VARIABLE or FUNCTION)
    
    Example:
        @placeholder(use=PlaceholderType.VARIABLE)
        async def user_name(self, ctx):
            return ctx.author.name
        
        # Can be used as: {user.name}
        
        @placeholder(use=PlaceholderType.FUNCTION)
        async def sum(self, ctx, result, *args):
            return str(sum(int(arg) for arg in args))
        
        # Can be used as: {sum:1;2;3}
    """
    def decorator(func):
        func.__placeholder_type__ = use
        func.__placeholder_name__ = func.__name__.replace("_", ".")
        return func
    return decorator