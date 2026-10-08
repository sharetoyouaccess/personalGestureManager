"""Regenerate locale/th nvda.po from source strings: python tools/updatepo.py new.json"""
import ast, json, re, subprocess, sys
PO = "addon/locale/th/LC_MESSAGES/nvda.po"
po = open(PO, encoding="utf-8").read()
tr = {ast.literal_eval(a): ast.literal_eval(b) for a, b in re.findall(r'^msgid (".*")\nmsgstr (".*")$', po, re.M)}
if len(sys.argv) > 1:
	tr.update(json.load(open(sys.argv[1], encoding="utf-8")))
ids = [json.loads(l) for l in subprocess.check_output([sys.executable, "tools/extract.py"], text=True, encoding="utf-8").splitlines()]
missing = [i for i in ids if not tr.get(i)]
if missing:
	sys.exit("Missing translations: %r" % missing)
for i in ids:
	assert sorted(re.findall(r"\{\w+\}", i)) == sorted(re.findall(r"\{\w+\}", tr[i])), i
q = lambda s: json.dumps(s, ensure_ascii=False)
with open(PO, "w", encoding="utf-8") as f:
	f.write('msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n"Language: th\\n"\n\n')
	for i in ids:
		f.write("msgid %s\nmsgstr %s\n\n" % (q(i), q(tr[i])))
with open("nvda.pot", "w", encoding="utf-8") as f:  # template for new translations
	f.write('msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n\n')
	for i in ids:
		f.write('msgid %s\nmsgstr ""\n\n' % q(i))
print("po updated:", len(ids), "strings")
