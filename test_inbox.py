from hermes_tools import tool_call
result = tool_call(
    name="mcp__agentmail__list_messages",
    arguments={"inboxId": "wallethygiene@agentmail.to"}
)
print("Result:", result)
