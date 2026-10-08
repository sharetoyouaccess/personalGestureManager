"""Build the .nvda-addon and run tests: python build.py"""
import os, re, subprocess, sys, zipfile
root = os.path.dirname(os.path.abspath(__file__))
def compileMo(po, mo):
	"""Minimal msgfmt for single-line msgid/msgstr entries."""
	import ast, struct
	cat, cur, field = {}, {}, None
	for line in open(po, encoding="utf-8").read().splitlines() + [""]:
		line = line.strip()
		m = re.match(r'^(msgid|msgstr) (".*")$', line)
		if m:
			if m.group(1) == "msgid" and "msgstr" in cur:
				cat[cur["msgid"]] = cur["msgstr"]
				cur = {}
			field = m.group(1)
			cur[field] = ast.literal_eval(m.group(2))
		elif line.startswith('"') and field:
			cur[field] += ast.literal_eval(line)
	if "msgstr" in cur:
		cat[cur["msgid"]] = cur["msgstr"]
	keys = sorted(cat)
	ids = b"".join(k.encode() + b"\0" for k in keys)
	strs = b"".join(cat[k].encode() + b"\0" for k in keys)
	n = len(keys)
	o1 = 28 + 16 * n
	o2 = o1 + len(ids)
	ti, ts, a, b = [], [], 0, 0
	for k in keys:
		kb, vb = k.encode(), cat[k].encode()
		ti += [len(kb), o1 + a]; a += len(kb) + 1
		ts += [len(vb), o2 + b]; b += len(vb) + 1
	with open(mo, "wb") as f:
		f.write(struct.pack("Iiiiiii", 0x950412de, 0, n, 28, 28 + 8 * n, 0, 0))
		f.write(struct.pack("%di" % (2 * n), *ti) + struct.pack("%di" % (2 * n), *ts) + ids + strs)
for po in __import__("glob").glob(os.path.join(root, "addon", "locale", "*", "LC_MESSAGES", "nvda.po")):
	compileMo(po, po[:-2] + "mo")
def buildDocs():
	"""readme.md (English, project root) and addon/locale/<lang>/readme.md -> addon/doc/<lang>/readme.html"""
	import glob, markdown, shutil
	sources = {"en": os.path.join(root, "readme.md")}
	for md in glob.glob(os.path.join(root, "addon", "locale", "*", "readme.md")):
		sources[os.path.basename(os.path.dirname(md))] = md
	for lang, md in sources.items():
		text = open(md, encoding="utf-8").read()
		title = text.splitlines()[0].lstrip("# ").strip()
		body = markdown.markdown(text, extensions=["sane_lists", "attr_list"])
		out = os.path.join(root, "addon", "doc", lang)
		os.makedirs(out, exist_ok=True)
		shutil.copyfile(md, os.path.join(out, "readme.md"))  # Markdown source is shipped next to the HTML
		with open(os.path.join(out, "readme.html"), "w", encoding="utf-8") as f:
			f.write('<!DOCTYPE html>\n<html lang="%s">\n<head>\n<meta charset="UTF-8">\n'
				'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
				'<link rel="stylesheet" href="../style.css">\n<title>%s</title>\n</head>\n<body>\n%s\n</body>\n</html>\n'
				% (lang, title, body))
	shutil.copyfile(os.path.join(root, "tools", "style.css"), os.path.join(root, "addon", "doc", "style.css"))
buildDocs()
# Tests run after the catalogues are compiled, so the language switch is tested with the real Thai catalogue.
for t in ("test_core.py", "test_plugin.py", "test_dialog.py", "test_i18n.py", "test_e2e.py", "test_install.py"):
	if subprocess.call([sys.executable, os.path.join(root, "tests", t)]):
		sys.exit("TESTS FAILED: " + t)
ver = re.search(r"^version = (\S+)", open(os.path.join(root, "addon", "manifest.ini"), encoding="utf-8").read(), re.M).group(1)
addonName = re.search(r"^name = (\S+)", open(os.path.join(root, "addon", "manifest.ini"), encoding="utf-8").read(), re.M).group(1)
name = "%s-%s" % (addonName, ver)
if "--stamp" in sys.argv:
	# Separate, time-sortable file next to earlier builds (Bangkok time); earlier files are never overwritten.
	import datetime
	now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=7)))
	name += "_build-" + now.strftime("%Y%m%d-%H%M")
out = os.path.join(root, name + ".nvda-addon")
src = os.path.join(root, "addon")
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
	z.write(os.path.join(root, "COPYING.txt"), "COPYING.txt")
	for d, dirs, files in os.walk(src):
		dirs[:] = [x for x in dirs if x != "__pycache__"]
		for f in files:
			if not f.endswith((".pyc", ".pot", ".po")) and not (f.endswith(".md") and "doc" not in os.path.relpath(d, src).split(os.sep)):
				p = os.path.join(d, f)
				z.write(p, os.path.relpath(p, src))
print("Built", out)
