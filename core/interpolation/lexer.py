"""
Lexer for template string parsing.

Converts template strings into AST nodes with support for:
- Escaped characters (\\)
- Nested placeholders
- Function arguments with semicolon separator
"""

from .nodes import TextNode, PlaceholderNode

ESCAPE_CHAR = "\\"


def lex(text: str) -> list:
    """
    Converts a template string into AST nodes.
    
    Args:
        text: Template string to parse
        
    Returns:
        List of Node objects (TextNode or PlaceholderNode)
        
    Examples:
        "Hello {user.name}" -> [TextNode("Hello "), PlaceholderNode(...)]
        "{sum:1;2}" -> [PlaceholderNode(...)]
        "\\{literal}" -> [TextNode("{literal}")]
    """
    if not text:
        return []
    
    nodes = []
    buffer = ""
    i = 0
    length = len(text)

    while i < length:
        char = text[i]

        # Handle escape sequences
        if char == ESCAPE_CHAR and i + 1 < length:
            next_char = text[i + 1]
            # Only escape special characters
            if next_char in ('{', '}', '\\', ';', ':'):
                buffer += next_char
                i += 2
                continue
            # Not a special char, keep backslash
            buffer += char
            i += 1
            continue

        # Start of placeholder
        if char == "{":
            # Flush text buffer
            if buffer:
                nodes.append(TextNode(buffer))
                buffer = ""

            # Parse placeholder
            node, consumed = _parse_placeholder(text[i:])
            if node:
                nodes.append(node)
            i += consumed
            continue

        buffer += char
        i += 1

    # Flush remaining buffer
    if buffer:
        nodes.append(TextNode(buffer))

    return nodes


def _parse_placeholder(text: str):
    """
    Parses a placeholder from the given text.
    
    Handles nested placeholders by tracking brace depth.
    
    Args:
        text: String starting with '{'
        
    Returns:
        Tuple of (Node, consumed_chars)
        Returns (TextNode, length) if placeholder is unclosed
    """
    depth = 0
    i = 0
    length = len(text)
    escaped = False

    while i < length:
        char = text[i]
        
        # Track escape state
        if char == ESCAPE_CHAR and not escaped:
            escaped = True
            i += 1
            continue
        
        # If we're escaped, skip this character
        if escaped:
            escaped = False
            i += 1
            continue
        
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                # Found matching closing brace
                raw = text[:i + 1]
                inner = raw[1:-1]  # Remove outer braces
                
                if not inner.strip():
                    # Empty placeholder: {}
                    return TextNode(raw), i + 1
                
                name, args = _parse_arguments(inner)
                return PlaceholderNode(raw, name, args), i + 1
        
        i += 1

    # Unclosed placeholder - treat as literal text
    return TextNode(text), length


def _parse_arguments(inner: str):
    """
    Parses placeholder name and arguments.
    
    Format: "name:arg1;arg2;arg3"
    Arguments can contain nested placeholders.
    
    CRITICAL: Returns args as a list of lists, where each inner list
    contains the nodes for one argument. This preserves argument boundaries.
    
    Args:
        inner: Content inside braces (without { })
        
    Returns:
        Tuple of (name, args_list)
        args_list is a list of lists: [[nodes for arg1], [nodes for arg2], ...]
        
    Examples:
        "user.name" -> ("user.name", [])
        "sum:1;2" -> ("sum", [[TextNode("1")], [TextNode("2")]])
        "embed.title:Hello {user.name}" -> ("embed.title", [[TextNode("Hello "), PlaceholderNode(...)]])
    """
    # Find the first unescaped colon at depth 0
    colon_pos = _find_separator(inner, ":")
    if colon_pos == -1:
        # No arguments
        return inner.strip(), []
    
    name = inner[:colon_pos].strip()
    args_str = inner[colon_pos + 1:]
    
    # Split arguments by semicolons at depth 0
    arg_strings = _split_arguments(args_str)
    
    # Parse each argument string into nodes and keep them grouped
    args = []
    for arg_str in arg_strings:
        # Parse this argument into nodes
        arg_nodes = lex(arg_str)
        # Keep this argument's nodes as a group
        args.append(arg_nodes)
    
    return name, args


def _split_arguments(args_str: str) -> list:
    """
    Splits argument string by semicolons at depth 0.
    
    Args:
        args_str: The arguments portion after the colon
        
    Returns:
        List of argument strings
        
    Example:
        "1;2;Hello {user.name}" -> ["1", "2", "Hello {user.name}"]
    """
    if not args_str:
        return []
    
    segments = []
    buffer = ""
    depth = 0
    escaped = False
    i = 0
    length = len(args_str)
    
    while i < length:
        char = args_str[i]
        
        # Handle escape sequences
        if char == ESCAPE_CHAR and not escaped:
            escaped = True
            buffer += char
            i += 1
            continue
        
        if escaped:
            escaped = False
            buffer += char
            i += 1
            continue
        
        # Track brace depth
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        
        # Semicolon at depth 0 is an argument separator
        if char == ";" and depth == 0:
            if buffer:  # Don't add empty strings
                segments.append(buffer)
            buffer = ""
            i += 1
            continue
        
        buffer += char
        i += 1
    
    # Don't forget the last argument
    if buffer:
        segments.append(buffer)
    
    return segments


def _find_separator(text: str, sep: str) -> int:
    """
    Finds the first occurrence of separator at brace depth 0.
    
    Args:
        text: String to search
        sep: Separator character to find
        
    Returns:
        Index of separator, or -1 if not found
    """
    depth = 0
    escaped = False
    i = 0
    length = len(text)
    
    while i < length:
        char = text[i]
        
        # Handle escape sequences
        if char == ESCAPE_CHAR and not escaped:
            escaped = True
            i += 1
            continue
        
        if escaped:
            escaped = False
            i += 1
            continue
        
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        elif char == sep and depth == 0:
            return i
        
        i += 1
    
    return -1