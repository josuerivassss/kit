"""
Interpreter for evaluating AST nodes.

Resolves placeholders by calling registered variable/function handlers
and handles nested evaluation with depth protection.
"""

from .nodes import TextNode, PlaceholderNode
from .render_result import RenderResult

# Maximum nesting depth to prevent stack overflow
MAX_NESTING = 15


class Interpreter:
    """
    Evaluates AST nodes and produces a RenderResult.
    
    Supports both variable placeholders ({user.name}) and
    function placeholders ({sum:1;2}) with nested evaluation.
    """

    def __init__(self, variables: dict, functions: dict):
        """
        Args:
            variables: Dict mapping variable names to async callables
            functions: Dict mapping function names to async callables
        """
        self.variables = variables
        self.functions = functions
        self.result = RenderResult(content="", embeds=[], emojis=[])

    async def render(self, nodes: list, ctx) -> RenderResult:
        """
        Renders a list of AST nodes into a RenderResult.
        
        Args:
            nodes: List of Node objects from lexer
            ctx: Context object passed to variable/function handlers
            
        Returns:
            RenderResult with evaluated content
        """
        for node in nodes:
            try:
                self.result.content += await self._eval(node, ctx, 0)
            except Exception as e:
                # On error, use the raw text as fallback
                self.result.content += node.raw
        
        return self.result

    async def _eval(self, node, ctx, depth: int) -> str:
        """
        Recursively evaluates a single node.
        
        Args:
            node: Node to evaluate
            ctx: Context object
            depth: Current nesting depth
            
        Returns:
            Evaluated string value
        """
        # Prevent infinite recursion
        if depth > MAX_NESTING:
            return node.raw

        # Text nodes return their value directly
        if isinstance(node, TextNode):
            return node.value

        # Placeholder nodes require resolution
        if isinstance(node, PlaceholderNode):
            return await self._eval_placeholder(node, ctx, depth)

        # Unknown node type - fallback to raw
        return node.raw

    async def _eval_placeholder(self, node: PlaceholderNode, ctx, depth: int) -> str:
        """
        Evaluates a placeholder node.
        
        First attempts variable resolution (no args),
        then function resolution (with args).
        
        Args:
            node: PlaceholderNode to evaluate
            ctx: Context object
            depth: Current nesting depth
            
        Returns:
            Evaluated string value
        """
        # VARIABLE PLACEHOLDER (no arguments)
        if not node.args and node.name in self.variables:
            try:
                result = await self.variables[node.name](ctx)
                return str(result) if result is not None else ""
            except Exception:
                # On error, return empty string
                return ""

        # FUNCTION PLACEHOLDER (with arguments)
        if node.name in self.functions:
            try:
                # Evaluate each argument group into a string
                # node.args is now a list of lists: [[nodes for arg1], [nodes for arg2], ...]
                evaluated_args = []
                
                for arg_group in node.args:
                    # Evaluate all nodes in this argument and concatenate them
                    arg_value = ""
                    for arg_node in arg_group:
                        arg_value += await self._eval(arg_node, ctx, depth + 1)
                    evaluated_args.append(arg_value)

                # Call the function with evaluated arguments
                result = await self.functions[node.name](
                    ctx,
                    self.result,
                    *evaluated_args
                )

                return str(result) if result is not None else ""
            except Exception as e:
                # On error, return empty string
                return ""

        # UNKNOWN PLACEHOLDER - return raw text as fallback
        return node.raw