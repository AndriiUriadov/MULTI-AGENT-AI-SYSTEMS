"""
mcp_utils — helper to convert MCP tools into LangChain StructuredTool objects.

Usage:
    async with Client(MCP_URL) as mcp_client:
        mcp_tools = await mcp_client.list_tools()
        lc_tools = mcp_tools_to_langchain(mcp_tools, mcp_client)
        agent = create_agent(model, tools=lc_tools, ...)
"""

from langchain_core.tools import StructuredTool
from pydantic import Field, create_model


def mcp_tools_to_langchain(mcp_tools, mcp_client) -> list:
    """Convert MCP tool definitions to LangChain StructuredTool objects.

    Each returned tool calls the MCP server when invoked by the agent.
    Based on the pattern from lesson-9.ipynb.
    """
    _type_map = {"string": str, "integer": int, "number": float, "boolean": bool}
    lc_tools = []

    for tool in mcp_tools:
        schema = tool.inputSchema or {"type": "object", "properties": {}}
        props = schema.get("properties", {})
        required = set(schema.get("required", []))

        # Build Pydantic model from JSON Schema properties
        fields = {}
        for name, prop in props.items():
            py_type = _type_map.get(prop.get("type"), str)
            default = ... if name in required else prop.get("default")
            fields[name] = (
                py_type if name in required else py_type | None,
                Field(default=default, description=prop.get("description", "")),
            )

        args_model = create_model(f"{tool.name}_args", **fields) if fields else None

        # Closure captures tool name and client for the async invocation
        _name, _client = tool.name, mcp_client

        async def _invoke(_name=_name, _client=_client, **kwargs):
            result = await _client.call_tool(_name, kwargs)
            return str(result.data)

        lc_tools.append(StructuredTool.from_function(
            coroutine=_invoke,
            name=tool.name,
            description=tool.description or tool.name,
            args_schema=args_model,
        ))

    return lc_tools
