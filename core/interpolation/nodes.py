"""
AST nodes for the interpolation engine.

Nodes represent parsed template components and maintain
their original raw text for fallback rendering.
"""

class Node:
    """
    Base AST node.
    
    The `raw` attribute contains the original literal text
    and is used as fallback when evaluation fails.
    """
    __slots__ = ('raw',)
    
    def __init__(self, raw: str):
        self.raw = raw
    
    def __repr__(self):
        return f"{self.__class__.__name__}(raw={self.raw!r})"


class TextNode(Node):
    """
    Represents literal text in the template.
    
    Example: "Hello world" -> TextNode("Hello world")
    """
    __slots__ = ('value',)
    
    def __init__(self, value: str):
        super().__init__(value)
        self.value = value
    
    def __repr__(self):
        return f"TextNode(value={self.value!r})"


class PlaceholderNode(Node):
    """
    Represents a placeholder in the template.
    
    Args structure: List of argument groups, where each group is a list of nodes.
    This preserves the boundary between semicolon-separated arguments.
    
    Examples:
        {user.name} -> PlaceholderNode(raw="{user.name}", name="user.name", args=[])
        {sum:1;2} -> PlaceholderNode(raw="{sum:1;2}", name="sum", args=[[TextNode("1")], [TextNode("2")]])
        {embed.title:Hello {user.name}} -> PlaceholderNode(raw="...", name="embed.title", 
                                                           args=[[TextNode("Hello "), PlaceholderNode(...)]])
    """
    __slots__ = ('name', 'args')
    
    def __init__(self, raw: str, name: str, args: list):
        super().__init__(raw)
        self.name = name
        self.args = args  # List[List[Node]] - each inner list is one argument
    
    def __repr__(self):
        return f"PlaceholderNode(name={self.name!r}, args={self.args!r})"