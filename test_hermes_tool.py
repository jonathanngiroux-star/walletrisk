from hermes_tools import tool_call, tool_describe
print("Testing tool_describe for list_messages")
try:
    desc = tool_describe(names=["mcp__agentmail__list_messages"])
    print("Describe result:", desc)
except Exception as e:
    print("Describe failed:", e)
print("Testing tool_call for list_messages")
try:
    result = tool_call(
        name="mcp__agentmail__list_messages",
        arguments={"inboxId": "wallethygiene@agentmail.to"}
    )
    print("Call result:", result)
except Exception as e:
    print("Call failed:", e)
