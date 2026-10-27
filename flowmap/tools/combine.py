import json, sys
projects = [json.load(open(f)) for f in sys.argv[2:]]
open(sys.argv[1], "w").write("window.FLOWMAP = " + json.dumps({"projects": projects}, separators=(",", ":")) + ";\n")
