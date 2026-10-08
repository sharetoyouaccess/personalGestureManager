import ast, glob, json
ids = []
for f in sorted(glob.glob("addon/globalPlugins/personalGestureManager/*.py")):
	for n in ast.walk(ast.parse(open(f, encoding="utf-8").read())):
		if isinstance(n, ast.Call) and getattr(n.func, "id", None) in ("_", "N_") and n.args and isinstance(n.args[0], ast.Constant):
			if n.args[0].value not in ids: ids.append(n.args[0].value)
for i in ids: print(json.dumps(i, ensure_ascii=False))
