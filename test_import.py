import sys
print("Python executable:", sys.executable)
print("sys.path:", sys.path)
try:
    import hermes_tools
    print("SUCCESS: imported hermes_tools")
except Exception as e:
    print("FAILED: ", e)
