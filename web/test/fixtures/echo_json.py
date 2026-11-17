import json, sys
print(json.dumps({"args": sys.argv[1:]}))
