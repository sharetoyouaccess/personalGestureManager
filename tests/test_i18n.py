"""Thai catalogue is complete, placeholders match, and no Alt-key mnemonic is used twice on one page."""
import ast, json, os, re, subprocess, sys, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..")
PAGES = {
	"commands": ["&Add-on", "&Filter type", "C&ommands",
		"Adjust ge&stures for this command...", "&Backups...", "&Close"],
	"conflicts": ["&Filter type", "&Include overlaps between NVDA's own commands",
		"&Shared gestures", "&Close"],
	"stats": ["&Period", "&Add-on", "&Filter type", "Commands by &use", "Su&mmary", "&Delete all statistics...", "&Close"],
	"tester": ["&Start testing gestures", "Test &results", "&Close"],
	"guides": ["&Add-ons and NVDA", "&Quick guide", "Open full &guide", "&Close"],
}

class T(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		po = open(os.path.join(ROOT, "addon", "locale", "th", "LC_MESSAGES", "nvda.po"), encoding="utf-8").read()
		cls.tr = {ast.literal_eval(a): ast.literal_eval(b) for a, b in re.findall(r'^msgid (".*")\nmsgstr (".*")$', po, re.M)}
		out = subprocess.check_output([sys.executable, os.path.join("tools", "extract.py")], cwd=ROOT, text=True, encoding="utf-8")
		cls.ids = [json.loads(l) for l in out.splitlines()]

	def test_complete_and_placeholders(self):
		for i in self.ids:
			self.assertTrue(self.tr.get(i), "missing Thai: %r" % i)
			self.assertEqual(sorted(re.findall(r"\{\w+\}", i)), sorted(re.findall(r"\{\w+\}", self.tr[i])), i)

	def test_mnemonics_unique(self):
		"""English Alt keys are unique per page; the same keys work in Thai, provided by the dialog."""
		for name, labels in PAGES.items():
			for l in labels:
				self.assertIn(l, self.ids, "page label not in source: %r" % l)
			keys = [re.search(r"&(.)", l).group(1).lower() for l in labels]
			self.assertEqual(len(keys), len(set(keys)), "%s duplicate Alt key: %s" % (name, keys))

	def test_thai_labels_are_clean(self):
		"""No "(&X)" or "(Enter: ...)" in Thai: NVDA would read the key twice."""
		for i, t in self.tr.items():
			self.assertNotIn("&", t, i)
			self.assertIsNone(re.search(r"\((Enter|Delete|Escape)", t), t)

if __name__ == "__main__":
	unittest.main()
