print("Testing hermes_tools import")
try:
    import hermes_tools
    print("SUCCESS: hermes_tools imported")
    # Try to use one function
    from hermes_tools import tool_describe
    print("tool_describe imported")
except Exception as e:
    print(f"FAILED: {e}")
