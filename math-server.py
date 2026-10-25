from mcp.server.mcpserver import MCPServer

server = MCPServer('qa-math-35459', version='1.0')


@server.tool()
def add(a: int, b: int) -> int:
    return a + b


@server.tool()
def multiply(a: int, b: int) -> int:
    return a * b


server.run(transport='streamable-http', host='127.0.0.1', port=41476)
