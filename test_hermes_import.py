import hermes_tools
print("hermes_tools imported successfully")
from hermes_tools import tool_describe
tools = tool_describe(names=["mcp__agentmail__list_messages"])
print("Tool describe result:", tools)
