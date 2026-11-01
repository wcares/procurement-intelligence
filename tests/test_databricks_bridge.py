import importlib.util
import inspect

from procintel.core import paths

spec = importlib.util.spec_from_file_location("bridge", paths.ROOT / "scripts" / "databricks_mcp_server.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class FakeDatabricks:
    def __init__(self):
        self.queries = []

    def query(self, statement, params):
        self.queries.append((statement, params))
        return [{"a": "1"}]


def test_a_table_function_becomes_a_read_only_tool_whose_arguments_are_bound_not_pasted():
    from mcp.server.mcpserver import MCPServer
    server, db = MCPServer("t"), FakeDatabricks()
    fn = {"full_name": "cat.sch.awards_for", "comment": "Awards of a project",
          "input_params": {"parameters": [{"name": "project"}]}}
    name = bridge.add_function_tool(server, db, fn)
    assert name == "cat__sch__awards_for"
    tool = server._tool_manager.get_tool(name)
    assert list(tool.parameters["properties"]) == ["project"] and tool.annotations.read_only_hint
    import asyncio
    out = asyncio.run(server.call_tool(name, {"project": "P1'; DROP TABLE x; --"}))
    assert db.queries == [("SELECT * FROM cat.sch.awards_for(:project)",
                           [{"name": "project", "value": "P1'; DROP TABLE x; --"}])]   # a value, never SQL
