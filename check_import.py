import sys
print(sys.path)
try:
    import hermes_tools
    print("hermes_tools imported")
except Exception as e:
    print(e)
