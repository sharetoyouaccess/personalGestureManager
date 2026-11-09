import re
"""Exercise ManagerDialog logic with a strict fake wx and a model of NVDA's gesture maps."""
import os, sys, types, tempfile, builtins, unittest, json
builtins._ = lambda s: s
sys.path.insert(0, os.path.dirname(__file__))
import fakewx
fakewx.install()
TMP = tempfile.mkdtemp()
def mod(name, **kw):
	m = types.ModuleType(name); m.__dict__.update(kw); sys.modules[name] = m; return m
mod("addonHandler", initTranslation=lambda: None, getRunningAddons=lambda: [])
mod("config", isInstalledCopy=lambda: True, conf={"keyboard": {"keyboardLayout": "desktop"}})
mod("globalPluginHandler", runningPlugins=set(), GlobalPlugin=object)
mod("globalVars", appArgs=types.SimpleNamespace(secure=True, configPath=TMP))
mod("inputCore", manager=types.SimpleNamespace(_captureFunc=None))
mod("scriptHandler", executeScript=None, script=lambda **kw: (lambda f: f))
ERRORS = []
mod("logHandler", log=types.SimpleNamespace(debugWarning=lambda *a, **k: None, error=lambda *a, **k: ERRORS.append(a)))
SPOKEN = []
mod("ui", message=SPOKEN.append)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins"))
import personalGestureManager as igm
from personalGestureManager import core, dialog

C = core.Command
SPEC = [  # key, name, addon, module, defaults, documented
	("a", "Alpha", "addA", "globalPlugins.a", ["kb:nvda+x"], True),
	("b", "Beta", "addB", "globalPlugins.b", ["kb(laptop):nvda+x"], True),
	("e", "Echo", "addB", "globalPlugins.b", ["kb:nvda+x"], True),
	("c", "Core", None, "globalCommands", ["kb:nvda+y"], True),
	("d", "Gamma", "addA", "globalPlugins.a", ["kb:nvda+g"], False),
]

class Model:
	"""Mirrors NVDA: effective = defaults - unbound + user additions."""
	def __init__(self):
		self.user = {k: [] for k, *_ in SPEC}; self.unbound = {k: set() for k, *_ in SPEC}
	def gestures(self, key, defaults):
		return [g for g in defaults if g not in self.unbound[key]] + [g for g in self.user[key] if g not in defaults or g in self.unbound[key]]
	def commands(self):
		return [C(k, n, "cat", a, a and "Add " + a[-1], m, "GP", k, self.gestures(k, d), doc) for k, n, a, m, d, doc in SPEC]
	def add(self, c, g, save=True): self.unbound[c.key].discard(g); self.user[c.key].append(g)
	def remove(self, c, g, spare=None):
		if g in self.user[c.key]: self.user[c.key].remove(g)
		else: self.unbound[c.key].add(g)
	def unbind(self, c, g): self.unbound[c.key].add(g)
	def snapshot(self): return ({k: list(v) for k, v in self.user.items()}, {k: set(v) for k, v in self.unbound.items()})
	def restore(self, snap): self.user, self.unbound = ({k: list(v) for k, v in snap[0].items()}, {k: set(v) for k, v in snap[1].items()})
	def reset(self, c, save=True):
		changed = bool(self.user[c.key] or self.unbound[c.key])
		self.user[c.key] = []; self.unbound[c.key] = set()
		return changed

class G:
	def __init__(self, ids, mod=False): self.normalizedIdentifiers = ids; self.isModifier = mod
def kb(k): return G(["kb(desktop):" + k, "kb:" + k])
def cap(): return sys.modules["inputCore"].manager._captureFunc

def setKey(choice, key):
	"""Select the item with this key in a choice built by the dialog (the order of items may change)."""
	choice.sel = [k for k, t in choice.items].index(key)

def pick(prefix):
	"""A chooser that takes the first item starting with prefix (else the first item)."""
	return lambda p, m, t, items, **k: next((i for i, x in enumerate(items) if x.startswith(prefix)), 0)

class T(unittest.TestCase):
	def setUp(self):
		SPOKEN.clear(); ERRORS.clear(); fakewx.CALLS.clear()
		dialog._shortcutsDialog = fakewx.shortcutsViaChoose(dialog)
		self.m = m = Model()
		self.collects = 0
		def collect(*a):
			self.collects += 1
			return m.commands()
		dialog.collectCommands = collect
		dialog.envInfo = lambda: {"version": "2026.3", "mode": "installed", "configPath": TMP, "layout": "desktop", "app": "notepad"}
		dialog.gestureText = lambda g: g
		dialog.addGesture, dialog.removeGesture, dialog.unbindGesture = m.add, m.remove, m.unbind
		dialog.resetCommand = m.reset
		dialog.snapshotUserGestures, dialog.restoreUserGestures = m.snapshot, m.restore
		dialog.takenInClass = lambda c, g: False
		dialog.saveUserGestures = lambda: None
		dialog.blockedLayouts = lambda c, g: []
		dialog.isUserGesture = lambda c, g: g in m.user[c.key]
		dialog._ask = lambda *a, **k: True
		dialog._askConflict = lambda *a: dialog.KEEP
		self.opened, self.shown = [], []
		dialog.listAddonGuides = lambda: [
			{"name": "addA", "summary": "Add A", "description": "Reads things aloud. Has many options.", "author": "Ann <a@x>",
				"version": "1.2", "running": True, "disabled": False, "docs": {"en": "/a/en.html", "th": "/a/th.html"}},
			{"name": "addB", "summary": "Add B", "description": "B <b>tools</b> & more", "author": "", "version": "",
				"running": True, "disabled": False, "docs": {}},
			{"name": "off", "summary": "Sleepy", "description": "", "author": "", "version": "0.1",
				"running": False, "disabled": True, "docs": {"de": "/s/de.html"}}]
		dialog.nvdaGuides = lambda: [("userGuide", {"en": "/n/ug-en.html", "th": "/n/ug-th.html"}), ("keyCommands", {"en": "/n/kc-en.html"})]
		dialog.currentLanguage = lambda: "th"
		dialog.languageName = lambda c: {"en": "English", "th": "Thai", "de": "German"}.get(c, c)
		dialog.openFile = self.opened.append
		dialog.showHtml = lambda html, title: self.shown.append((title, html))
		self.backups = []
		stats = core.StatsStore(os.path.join(tempfile.mkdtemp(), "s.json"))
		stats.record("a", "Alpha", "addA", None); stats.record("c", "Core", None, None)
		self.reopened = []
		self.plugin = types.SimpleNamespace(stats=stats, dialog=None, ensureBackup=lambda note=None: self.backups.append(note),
			uiLanguage=None, openManager=lambda *a: self.reopened.append(a))
		self.plugin.setUiLanguage = lambda lang: setattr(self.plugin, "uiLanguage", lang)
		self.saved = {}
		self.plugin.setSetting = self.saved.__setitem__
		self.addCleanup(dialog.setUiLanguage, None)
		self.d = dialog.ManagerDialog(None, self.plugin)
		fakewx.runCalls()

	def cmd(self, key):
		return [c for c in self.d.commands if c.key == key][0]

	def sel(self, key):
		self.d.cmdList.sel = [c.key for c, n in self.d.cmdRows].index(key)

	def test_open(self):
		d = self.d
		self.assertEqual(d.book.pages, ["Commands by add-on", "Conflicts", "Statistics", "Gesture tester", "Guides for NVDA and add-ons"])
		self.assertEqual(SPOKEN, [])  # opening: NVDA reads the window name, nothing more
		self.assertIs(fakewx.FOCUS[0], d.cmdAddon)  # starts at the first control of the page
		# lazy tabs: only the visible tab is built when the window opens
		self.assertEqual(d.statsList.rows, []); self.assertEqual(d.confList.rows, [])
		self.assertEqual(self.collects, 1)
		d.book.SetSelection(dialog.PAGE_STATS); d.book.SetSelection(dialog.PAGE_CONFLICTS)
		# arriving at the Conflicts tab: how many, not which; after NVDA has said the tab
		self.assertEqual(SPOKEN, [])
		fakewx.runCalls()
		self.assertEqual(SPOKEN, ["2 conflicts between add-ons"])
		self.assertEqual(d.title, "Personal Gesture Manager")
		# NVDA+T: the name, which NVDA, which computer and Windows; twice: every detail, most useful first
		dialog.systemInfo = lambda: {"nvdaDir": "C:\\NVDA", "windows": "Windows 11 Pro 24H2", "build": "26100", "computer": "VT36", "inputLanguage": "Thai", "addons": 32, "running": 30}
		self.assertEqual(d.statusText(), "Personal Gesture Manager. NVDA 2026.3, installed, on VT36, Windows 11 Pro 24H2.")
		lines = d.detailLines()
		self.assertTrue(lines[0].startswith("NVDA 2026.3, installed, running from C:\\NVDA"))
		self.assertTrue(lines[1].startswith("Gestures and settings saved in "))
		self.assertEqual(lines[2], "Keyboard layout: desktop. Input language: Thai.")
		self.assertEqual(lines[3], "2 conflicts between add-ons.")
		self.assertEqual(lines[4], "32 add-ons, 30 running.")
		self.assertEqual(lines[5], "Windows 11 Pro 24H2, build 26100. Computer name: VT36.")
		self.assertEqual(lines[6], "Application tested: notepad")
		dialog.systemInfo = lambda: {}  # nothing readable: still a report, never an error
		self.assertIn("?", d.statusText()); self.assertEqual(len(d.detailLines()), 6)
		# default: last 7 days, all add-ons, most used; name and uses read first
		self.assertEqual((d.period.items[d.period.sel][0], d._choiceKey(d.statsAddon), d.statsShow.sel), ("week", "+", 0))
		self.assertEqual(d.statsList.rows, [["Alpha", "1 time", "kb:nvda+x", "Add A"]])
		self.assertEqual(d.statsInfo.value[:len("Last 7 days: 1 use of 1 command.")], "Last 7 days: 1 use of 1 command.")
		self.assertIn("Gamma (no description) - Add A", [r[0] for r in d.cmdList.rows])
		# one row per shared key: shortcut, layout, how many commands share it (the type is chosen above)
		self.assertEqual({len(r) for r in d.confList.rows}, {3})
		self.assertEqual(len(d.confRows), len([cf for cf in d.conflicts if cf.kind == "conflict"]))
		self.assertTrue(all(re.fullmatch(r"\d+ commands", r[2]) for r in d.confList.rows))
		self.assertEqual({r[0] for r in d.confList.rows}, {"kb:nvda+x"})
		self.assertEqual({r[1] for r in d.confList.rows}, {"desktop", "laptop"})
		self.assertFalse(hasattr(d, "confHelp")); self.assertFalse(hasattr(d, "cmdPeriod"))
		self.assertFalse(hasattr(d, "envText"))  # the details are with NVDA+T only, not in the tester tab
		copied = []
		sys.modules["api"] = types.SimpleNamespace(copyToClip=lambda t: copied.append(t) or True)
		try:
			d.copyDetails()  # NVDA+T three times
		finally:
			del sys.modules["api"]
		self.assertEqual(copied, ["\n".join(d.detailLines())]); self.assertEqual(SPOKEN[-1], "Details copied")
		self.assertIn("Application tested: notepad", copied[0])
		# F1: this guide, at the section of the tab in use
		for page, anchor in ((dialog.PAGE_COMMANDS, "commands"), (dialog.PAGE_CONFLICTS, "conflicts"),
				(dialog.PAGE_STATS, "statistics"), (dialog.PAGE_TESTER, "tester"), (dialog.PAGE_GUIDES, "guides")):
			d.book.SetSelection(page)
			path, a = d.helpPath()
			self.assertEqual(a, anchor); self.assertTrue(path.endswith("readme.html"))
			self.assertIn('id="%s"' % anchor, open(path, encoding="utf-8").read())  # the section exists
		opened = []
		d.openHelp = lambda: opened.append(1)
		d.onCharHook(types.SimpleNamespace(GetKeyCode=lambda: fakewx.wx.WXK_F1, HasAnyModifiers=lambda: False,
			ControlDown=lambda: False, AltDown=lambda: False, ShiftDown=lambda: False, Skip=lambda: None))
		self.assertEqual(opened, [1])
		del d.openHelp
		for page, ctrl in ((dialog.PAGE_CONFLICTS, d.confShow), (dialog.PAGE_STATS, d.period), (dialog.PAGE_TESTER, d.testBtn), (dialog.PAGE_GUIDES, d.guideList)):
			d.selectPage(page); self.assertIs(fakewx.FOCUS[0], ctrl)
		d.selectPage(dialog.PAGE_COMMANDS)

	def test_show_filters(self):
		d = self.d
		self.assertEqual(d.cmdFilter.strings, ["Commands with a gesture", "Commands with more than one gesture",
			"Commands without a gesture", "All commands"])
		self.assertEqual(d._choiceKey(d.cmdAddon), "+")  # all add-ons by default, as in Statistics
		self.assertEqual([t for k, t in d.cmdAddon.items][0], "All add-ons")
		self.assertEqual(d.cmdAddon.items[-1], ("*", "All add-ons and NVDA"))  # the longest list comes last
		setKey(d.cmdAddon, "+")  # add-ons only
		self.m.unbind(self.cmd("d"), "kb:nvda+g"); d.commands = self.m.commands()
		def keys(mode):
			d.cmdFilter.sel = mode; d.refreshCommands(); return sorted(c.key for c, n in d.cmdRows)
		self.assertEqual(keys(dialog.CMD_ALL), ["a", "b", "d", "e"])
		self.assertEqual(keys(dialog.CMD_WITH), ["a", "b", "e"])  # d has no shortcut
		self.assertEqual(keys(dialog.CMD_WITHOUT), ["d"])
		self.assertEqual(d.cmdFilter.sel, dialog.CMD_WITHOUT)
		self.assertEqual(keys(dialog.CMD_MULTI), [])
		self.m.user["e"] = self.m.user.get("e", []) + ["kb:nvda+shift+e", "kb:nvda+control+e"]
		d.commands = self.m.commands()
		self.assertEqual(keys(dialog.CMD_MULTI), ["e"])  # two or more shortcuts only
		setKey(d.cmdAddon, "*"); self.assertEqual(keys(dialog.CMD_WITHOUT), ["d"])
		d.goToCommand("a"); self.assertEqual(d.cmdFilter.sel, dialog.CMD_ALL)
		# command, shortcuts, conflict: uses are in the Statistics tab only
		setKey(d.cmdAddon, "+"); d.cmdFilter.sel = dialog.CMD_ALL; d.refreshCommands()
		row = {c.key: d.cmdList.rows[i] for i, (c, n) in enumerate(d.cmdRows)}
		self.assertEqual({len(r) for r in d.cmdList.rows}, {3})
		self.assertEqual((row["a"][1], row["a"][2]), ("kb:nvda+x", "Gesture conflict"))  # details: Enter on it
		self.assertEqual((row["d"][1], row["d"][2]), ("No gesture", ""))
		self.plugin.stats.record("a", "Alpha", "addA", None); d.refreshCommands()
		self.assertEqual(d.cmdList.rows[[c.key for c, n in d.cmdRows].index("a")][2], "Gesture conflict")

	def test_reset(self):
		d = self.d
		d.cmdFilter.sel = dialog.CMD_ALL; d.refreshCommands()  # the command stays listed without a shortcut
		dialog._choose = lambda *a, **k: 0
		self.sel("a"); d.onRemove(None)
		self.assertEqual(self.cmd("a").gestures, [])
		self.sel("a"); d.onResetCommand(None)
		self.assertEqual((self.cmd("a").gestures, SPOKEN[-1]), (["kb:nvda+x"], "Reset to default. Gestures now: kb:nvda+x"))
		self.sel("a"); d.onResetCommand(None)
		self.assertEqual(SPOKEN[-1], "Already using the default gestures")
		self.m.add(self.cmd("b"), "kb:nvda+q"); self.m.unbind(self.cmd("e"), "kb:nvda+x")
		d.commands = self.m.commands(); d.refreshCommands()
		self.sel("b"); d.onResetAddon(None)
		self.assertEqual(SPOKEN[-1], "Add B: commands reset to default: 2")
		self.assertEqual((self.cmd("b").gestures, self.cmd("e").gestures), (["kb(laptop):nvda+x"], ["kb:nvda+x"]))
		self.assertTrue(len(self.backups) >= 3)

	def test_periods(self):
		d = self.d
		d.selectPage(dialog.PAGE_STATS)
		labels = [t for k, t in d.period.items]
		self.assertEqual(labels, ["This NVDA session", "Today", "Last 7 days", "Last 30 days", "All time"])
		st = self.plugin.stats
		old = {"start": 1_700_000_000, "counts": {"c": 4}}
		st.data["sessions"].insert(0, old); st.data["sessions"].insert(0, {"start": 1_600_000_000, "counts": {}})
		d.refreshStats()
		self.assertEqual([t for k, t in d.period.items], labels)  # earlier sessions are not listed
		d.period.sel = 4; setKey(d.statsAddon, ""); d._statsChoice()  # all time includes earlier sessions
		self.assertEqual(d.statsList.rows[0][0], "Core")
		d.period.sel = 3; d._statsChoice()  # last 30 days keeps selection across refresh
		d.refreshStats(); self.assertEqual(d.period.items[d.period.sel][0], "month")
		self.assertEqual(self.saved["statsPeriod"], "month")
		# least used: only commands with a shortcut, fewest uses first
		st.record("a", "Alpha", "addA", None); st.record("a", "Alpha", "addA", None)
		d.period.sel = 4; setKey(d.statsAddon, "*"); d.statsShow.sel = 1; d._statsChoice()
		self.assertEqual([r[0] for r in d.statsList.rows], ["Core", "Alpha"])  # 1 use, then 3
		self.assertEqual(self.saved["statsShow"], "least")
		# least used with nothing that has a shortcut: says so, not "no usage"
		st.record("zz", "Gone", "oldAddon", None); d.refreshStats()
		d.statsAddon.sel = [k for k, t in d.statsAddon.items].index("oldAddon"); d._statsChoice()
		self.assertEqual((d.statsList.rows, d.statsList.emptyText), ([], "No commands with a gesture were used in this period"))
		self.assertIn("no command with a gesture was used", d.statsInfo.value)
		# an add-on choice that is gone falls back to "All add-ons"
		d.statsShow.sel = 0; d.statsAddon.items = None; d.statsAddon.pendingKey = "gone"; d.refreshStats()
		self.assertEqual(d._choiceKey(d.statsAddon), "+")
		# reset is confirmed aloud
		dialog._ask = lambda *a, **k: True
		d.onReset(None); self.assertEqual(SPOKEN[-1], "All statistics deleted")
		self.saved.clear(); d.period.sel = 4; d.statsShow.sel = 1; d._statsChoice()
		# remembered for the next window
		self.plugin.getSetting = lambda k, dflt=None: self.saved.get(k, dflt)
		e = dialog.ManagerDialog(None, self.plugin); fakewx.runCalls(); e.selectPage(dialog.PAGE_STATS)
		self.assertEqual((e.period.items[e.period.sel][0], e.statsShow.sel, e._choiceKey(e.statsAddon)), ("all", 1, "+"))

	def test_one_reload_per_edit(self):
		d = self.d
		dialog._choose = lambda *a, **k: 0
		n = self.collects; self.sel("b"); d.onRemove(None)
		self.assertEqual(self.collects - n, 1)  # plain removal: one reload
		dialog._askConflict = lambda *a: dialog.MOVE
		n = self.collects; d._addCaptured(self.cmd("c"), kb("nvda+x"))  # moves from a and e
		self.assertEqual(self.collects - n, 1)
		self.assertEqual(SPOKEN[-1], "Moved kb:nvda+x to Core")

	def test_live_numbers_on_tab_visit(self):
		d = self.d
		d.selectPage(dialog.PAGE_STATS)
		self.assertEqual(d.statsList.rows[0], ["Alpha", "1 time", "kb:nvda+x", "Add A"])
		d.selectPage(dialog.PAGE_COMMANDS); self.sel("b")
		self.plugin.stats.record("b", "Beta", "addB", None); self.plugin.stats.record("b", "Beta", "addB", None)
		d.selectPage(dialog.PAGE_STATS)  # recorded while the dialog was open
		self.assertEqual(d.statsList.rows[0][0], "Beta")
		d.statsList.sel = 1; d.selectPage(dialog.PAGE_COMMANDS)
		self.assertEqual(d.cmdRows[d.cmdList.sel][0].key, "b")  # selection kept
		d.selectPage(dialog.PAGE_STATS)
		self.assertEqual(d.statsKeys[d.statsList.sel], "a")  # selection kept after rebuild

	def test_guides(self):
		d = self.d
		self.assertEqual(d.guideList.rows, [])  # built only when the tab is shown
		d.selectPage(dialog.PAGE_GUIDES)
		self.assertIs(fakewx.FOCUS[0], d.guideList)  # no search field: letters move in the list
		self.assertFalse(hasattr(d, "guideSearch") or hasattr(d, "guideLang"))
		self.assertEqual([r[0] for r in d.guideList.rows],
			["NVDA User Guide", "NVDA Commands Quick Reference", "Add A", "Add B", "Sleepy"])
		self.assertEqual(d.guideList.rows[2][1:], ["Running", "Reads things aloud. Press Enter to read the quick guide."])
		self.assertTrue(d.guideList.rows[0][2].endswith("Press Enter to open it."))
		self.assertEqual(d.guideList.rows[4][1], "Disabled")
		# NVDA entry: the language is asked only when there is a choice, NVDA's language first
		langs = []
		dialog._choose = lambda p, m, t, items, **k: langs.append(items) or 0
		d.guideList.sel = 0; d.onGuideActivate(None)
		self.assertEqual((langs[-1], self.opened), (["Thai", "English"], ["/n/ug-th.html"]))
		dialog._choose = lambda *a, **k: 1
		d.onFullGuide(None); self.assertEqual(self.opened[-1], "/n/ug-en.html")
		dialog._choose = lambda *a, **k: None
		n = len(self.opened); d.onFullGuide(None); self.assertEqual(len(self.opened), n)  # cancelled
		d.guideList.sel = 1; d.onFullGuide(None); self.assertEqual(self.opened[-1], "/n/kc-en.html")  # one language: no question
		# quick guide of a running add-on: its window says whose guide it is
		d.guideList.sel = 2; d.onGuideActivate(None)
		title, html = self.shown[-1]
		self.assertEqual(title, "Quick guide: Add A")
		for part in ("<h1>Add A</h1>", "Reads things aloud. Has many options.", "<li>Alpha: kb:nvda+x</li>",
				"<li>Gamma: kb:nvda+g</li>", "Gesture conflicts", "Conflict, only one works",
				"Version: 1.2", "Author: Ann &lt;a@x&gt;", "Status: Running"):
			self.assertIn(part, html)
		# text is escaped, missing docs reported
		d.guideList.sel = 3; d.onQuickGuide(None)
		html = self.shown[-1][1]
		self.assertIn("B &lt;b&gt;tools&lt;/b&gt; &amp; more", html); self.assertNotIn("full guide", html)  # languages: only when opening it
		n = len(self.opened); d.onFullGuide(None)
		self.assertEqual((len(self.opened), SPOKEN[-1]), (n, "Add B has no full guide"))
		# disabled add-on: commands cannot be listed, but its guide can still be opened
		d.guideList.sel = 4; d.onQuickGuide(None)
		self.assertIn("This add-on is not running", self.shown[-1][1])
		d.onFullGuide(None); self.assertEqual(self.opened[-1], "/s/de.html")
		# opening failure is reported
		d.guideList.sel = 4
		def boom(p): raise OSError("no app")
		dialog.openFile = boom; d.onFullGuide(None)
		self.assertEqual(SPOKEN[-1], "The guide could not be opened. Details are in the NVDA log.")
	def test_lists_built_once_on_open(self):
		builds = []
		orig = dialog.ManagerDialog.refreshCommands
		dialog.ManagerDialog.refreshCommands = lambda self, *a, **k: builds.append(1) or orig(self, *a, **k)
		try:
			d = dialog.ManagerDialog(None, self.plugin, dialog.PAGE_COMMANDS, None, False); fakewx.runCalls()
			self.assertEqual(len(builds), 1)
			d.statsList.sel = 0; d.selectPage(dialog.PAGE_STATS); n = len(builds)
			d.onStatsActivate(None)  # jump to the command: one rebuild, not two
			self.assertEqual(len(builds) - n, 1)
		finally:
			dialog.ManagerDialog.refreshCommands = orig
		self.assertIn("Keyboard layout: desktop", "\n".join(d.detailLines()))

	def test_language_toggle(self):
		d = self.d
		self.assertIn(("ctrl", "T"), [(k, chr(c)) for k, c, _i in d.accel])
		# English: Alt keys are handled per tab by the dialog too; Windows reports them from the underlined letter
		self.assertIn(("alt", "S"), [(k, chr(c)) for k, c, _i in d.accel])
		self.assertFalse(hasattr(d.cmdAddon, "accessible"))
		d.selectPage(dialog.PAGE_STATS); d.onMnemonic("a"); self.assertIs(fakewx.FOCUS[0], d.statsAddon)  # not the Commands tab's
		d.selectPage(dialog.PAGE_COMMANDS); d.onMnemonic("a"); self.assertIs(fakewx.FOCUS[0], d.cmdAddon)
		self.assertEqual(dialog.nextLanguage(None, "th"), "en"); self.assertEqual(dialog.nextLanguage(None, "ja"), "th")
		self.assertEqual(dialog.nextLanguage("en", "th"), "th")
		d.cmdAddon.sel = [k for k, t in d.cmdAddon.items].index("addB"); d.cmdFilter.sel = 2; d.refreshCommands()
		d.selectPage(dialog.PAGE_CONFLICTS); d.coreConf.value = True; d.confShow.sel = 0
		d.onTest(None); self.assertIsNotNone(cap())
		n, spoken, oldRoot, oldList = self.collects, len(SPOKEN), d.root, d.cmdList
		fakewx.CALLS.clear()
		d.confShow.SetFocus()
		d.onToggleLanguage(None)  # NVDA in Thai, nothing chosen yet: shown in Thai -> English
		self.assertEqual(SPOKEN[spoken], dialog.LANGUAGE_CHANGED['en']); self.assertIn("Ctrl+T", SPOKEN[spoken])
		self.assertIsNone(cap())
		self.assertEqual(self.plugin.uiLanguage, "en")
		# translated in place: nothing rebuilt, focus never moves
		self.assertIs(d.root, oldRoot); self.assertIs(d.cmdList, oldList); self.assertFalse(getattr(oldRoot, "destroyed", False))
		self.assertIs(fakewx.FOCUS[0], d.confShow)
		fakewx.runCalls()
		self.assertEqual(d.book.sel, dialog.PAGE_CONFLICTS); self.assertEqual(d.book.pages[0], "Commands by add-on")
		self.assertEqual((d.coreConf.value, d.confShow.sel), (True, 0))
		self.assertEqual((d._choiceKey(d.cmdAddon), d.cmdFilter.sel), ("addB", 2))
		self.assertEqual(self.collects, n)
		self.assertEqual(SPOKEN[spoken:], [dialog.LANGUAGE_CHANGED['en']])  # conflicts not announced again
		# Thai, with the real catalogue: clean labels, same Alt keys provided by the dialog
		d.onToggleLanguage(None); fakewx.runCalls()
		self.assertEqual(self.plugin.uiLanguage, "th"); self.assertEqual(SPOKEN[-1], dialog.LANGUAGE_CHANGED['th']); self.assertIn("Thai", SPOKEN[-1])
		self.assertTrue(d.book.pages[1].startswith("ปุ่มลัดซ้ำ"))
		self.assertTrue(d.title.startswith("Personal Gesture Manager"))
		self.assertIn("แบบติดตั้ง", d.statusText())
		self.assertRegex(d.cmdList.cols[0], "[\u0e00-\u0e7f]")  # column titles
		self.assertRegex(d.cmdFilter.strings[0], "[\u0e00-\u0e7f]")  # options, selection kept
		self.assertRegex(d.cmdList.labelCtrl.label, "[\u0e00-\u0e7f]")  # the label shown
		# every label is translated and clean (no "&", no key hints)
		for c in (d.cmdAddon, d.cmdFilter, d.cmdList, d.confShow, d.confList, d.period, d.statsAddon,
				d.statsList, d.statsInfo, d.testResult, d.guideList):
			self.assertNotIn("&", c.labelCtrl.label); self.assertRegex(c.labelCtrl.label, "[\u0e00-\u0e7f]")
		# NVDA is told the Alt key of each control, like in English, without "(D)" in the label
		def said(c): return c.accessible.GetKeyboardShortcut(0)
		self.assertEqual(said(d.cmdAddon), (fakewx.wx.ACC_OK, "Alt+A"))
		for lst in (d.cmdList, d.confList, d.statsList, d.guideList):  # lists: no accessibility layer (slow, unheard)
			self.assertFalse(hasattr(lst, "accessible"))
		self.assertEqual(said(d.coreConf)[1], "Alt+I"); self.assertEqual(said(d.testBtn)[1], "Alt+S")
		self.assertIn("แบบติดตั้ง", "\n".join(d.detailLines()))
		self.assertEqual(d.confShow.strings[0], "ปุ่มลัดซ้ำ")
		alts = {chr(c).lower() for k, c, _i in d.accel if k == "alt"}
		self.assertTrue({"a", "s", "o", "b", "c", "i", "u", "p", "r", "q", "g", "f", "m"} <= alts)
		# Alt+S is "Shared gestures" on the Conflicts tab and "Start testing" on the tester tab
		d.onMnemonic("s"); self.assertIs(fakewx.FOCUS[0], d.confList)
		d.onMnemonic("i"); self.assertFalse(d.coreConf.value)  # checkbox toggled
		d.selectPage(dialog.PAGE_TESTER); d.onMnemonic("s"); self.assertIsNotNone(cap())  # button pressed
		d._stopCapture()
		d.selectPage(dialog.PAGE_COMMANDS); d.onMnemonic("o"); self.assertIs(fakewx.FOCUS[0], d.cmdList)
		# a new window opens in the remembered language
		e = dialog.ManagerDialog(None, self.plugin, 0, None, False)
		self.assertTrue(e.book.pages[1].startswith("ปุ่มลัดซ้ำ"))

	def test_random_use_never_breaks(self):
		"""300 random user actions in a row (deterministic): no exception, capture never left on after close."""
		import random
		rnd = random.Random(int(os.environ.get("SEED", 2026)))
		d = self.d
		randomChoose = lambda p, m, t, items, **kw: rnd.choice([None] + list(range(len(items))))
		dialog._choose = randomChoose
		dialog._ask = lambda *a, **k: rnd.choice([True, False])
		dialog._askConflict = lambda *a: rnd.choice([None, dialog.MOVE, dialog.KEEP, dialog.AGAIN])
		keys = ["nvda+x", "nvda+y", "nvda+q", "control+shift+k"]
		def act():
			op = rnd.randrange(14)
			if op == 0: d.selectPage(rnd.randrange(5))
			elif op == 1: d.onToggleLanguage(None)
			elif op == 2:
				if d.cmdRows:
					d.cmdList.sel = rnd.randrange(len(d.cmdRows)); c = d.cmdRows[d.cmdList.sel][0]
					if rnd.random() < 0.5: d._addCaptured(c, kb(rnd.choice(keys)))
					else:
						dialog._choose = pick("Add a gesture")
						d.onCmdMenu(None); dialog._choose = randomChoose
						cap() and cap()(kb(rnd.choice(keys + ["escape"])))
			elif op == 3:
				if d.cmdRows: d.cmdList.sel = rnd.randrange(len(d.cmdRows)); d.onRemove(None)
			elif op == 4: d.cmdAddon.sel = rnd.randrange(len(d.cmdAddon.items)); d.refreshCommands()
			elif op == 5: d.cmdFilter.sel = rnd.randrange(4); d.refreshCommands()
			elif op == 6: d.cmdList.sel = rnd.randrange(max(1, len(d.cmdRows))); d.cmdRows and d.onCmdMenu(None); cap() and cap()(kb(rnd.choice(keys + ["escape"])))
			elif op == 7: d.onTest(None); cap() and cap()(kb(rnd.choice(keys + ["escape"])))
			elif op == 8:
				if d.cmdRows: d.cmdList.sel = rnd.randrange(len(d.cmdRows)); d.onResetCommand(None)
			elif op == 9: d.selectPage(dialog.PAGE_STATS); d.period.sel = rnd.randrange(len(d.period.items)); d.statsShow.sel = rnd.randrange(3); d.statsAddon.sel = rnd.randrange(len(d.statsAddon.items)); d._statsChoice(); d.statsList.sel = rnd.randrange(max(1, len(d.statsKeys))); rnd.random() < 0.3 and d.onStatsActivate(None)
			elif op == 10: d.selectPage(dialog.PAGE_CONFLICTS); d.confShow.sel = rnd.randrange(3); d.refreshConflicts(); d.confList.sel = 0; d.onConflictActivate(None)
			elif op == 11: d.selectPage(dialog.PAGE_GUIDES); d.guideList.sel = rnd.randrange(max(1, len(d.guideRows))); d.onGuideActivate(None); rnd.random() < 0.3 and d.onFullGuide(None)
			elif op == 12: d.onMnemonic(rnd.choice("asfodmbiuprnlqg"))  # not "c": Close ends the window
			elif op == 13: self.plugin.stats.record(rnd.choice("abcde"), "x", None, None); d.selectPage(dialog.PAGE_TESTER)
			fakewx.runCalls()
		for _i in range(300):
			act()
		d.onClose(None)
		self.assertIsNone(cap())
		self.assertEqual(ERRORS, [])  # no list ever failed to load

	def test_remove_default_also_added_by_user(self):  # E2
		d = self.d
		self.m.user["a"].append("kb:nvda+x")
		d.commands = self.m.commands(); d.refreshCommands()
		self.sel("a"); dialog._choose = lambda *a, **k: 0
		d.onRemove(None)
		self.assertNotIn("kb:nvda+x", self.m.gestures("a", ["kb:nvda+x"]))
		self.assertEqual(SPOKEN[-1], "Removed kb:nvda+x")
		self.assertEqual(self.backups, ["removing kb:nvda+x from Alpha"])  # each backup says what followed

	def test_remove_failure_is_reported(self):
		d = self.d
		dialog.unbindGesture = lambda c, g: None  # NVDA refuses
		dialog.removeGesture = lambda c, g: None
		self.sel("a"); dialog._choose = lambda *a, **k: 0
		d.onRemove(None)
		self.assertTrue(SPOKEN[-1].startswith("Could not remove"))

	def test_undocumented_without_shortcut_stays(self):  # E3 (dialog side)
		d = self.d
		d.cmdFilter.sel = dialog.CMD_ALL; d.refreshCommands()  # the command stays listed without a shortcut
		self.sel("d"); dialog._choose = lambda *a, **k: 0
		d.onRemove(None)
		self.assertIn("d", [c.key for c, n in d.cmdRows])
		self.sel("d"); d.onRemove(None)
		self.assertEqual(SPOKEN[-1], "This command has no gesture")

	def test_already_covered(self):  # E4
		d = self.d
		dialog._choose = lambda *a, **k: 1  # desktop-only variant (list is generic first)
		d._addCaptured(self.cmd("a"), kb("nvda+x"))
		self.assertEqual(SPOKEN[-1], "kb(desktop):nvda+x is already assigned to this command")

	def test_layout_choices(self):
		d = self.d
		orig = dialog.gestureParts
		self.addCleanup(setattr, dialog, "gestureParts", orig)
		dialog.gestureParts = lambda g: ("NVDA+Q", {"kb(desktop)": "desktop", "kb(laptop)": "laptop"}.get(g.split(":")[0]), None)
		seen = []
		def choose(parent, msg, title, items, **kw):
			seen.append(items); return 2
		dialog._choose = choose
		d._addCaptured(self.cmd("a"), kb("nvda+q"))  # user is on the desktop layout, picks "laptop only"
		self.assertEqual(seen[-1], ["NVDA+Q, all keyboard layouts", "NVDA+Q, desktop layout only",
			"NVDA+Q, laptop layout only"])
		self.assertIn("kb(laptop):nvda+q", self.m.user["a"])
		dialog._choose = lambda *a, **k: 0
		d._addCaptured(self.cmd("b"), kb("nvda+w")); self.assertIn("kb:nvda+w", self.m.user["b"])
		# a laptop-only shortcut does not conflict with a desktop-only one
		asked = []
		dialog._askConflict = lambda *a: asked.append(a) or dialog.KEEP
		dialog._choose = lambda *a, **k: 1
		d._addCaptured(self.cmd("e"), kb("nvda+q"))
		self.assertEqual(asked, []); self.assertIn("kb(desktop):nvda+q", self.m.user["e"])
		# braille / touch gestures have no layout: only a confirmation is asked
		confirmed = []
		dialog._ask = lambda p, msg, t, **k: confirmed.append(msg) or True
		d._addCaptured(self.cmd("c"), G(["br(freedomscientific):dot1"]))
		self.assertEqual(len(confirmed), 1); self.assertIn("br(freedomscientific):dot1", self.m.user["c"])
		self.assertEqual(dialog._layoutOptions(["br(x):dot1"]), [])
		# removing: every choice states its layout
		self.m.user["a"] = ["kb:nvda+q", "kb(laptop):nvda+q"]; d.commands = self.m.commands(); d.refreshCommands()
		self.sel("a"); dialog._choose = lambda p, m, t, items, **kw: seen.append(items) or None
		d.onRemove(None)
		self.assertEqual(seen[-1], ["NVDA+Q, all keyboard layouts", "NVDA+Q, all keyboard layouts", "NVDA+Q, laptop layout only"])

	def test_move_and_keep(self):  # U3
		d = self.d
		dialog._choose = lambda *a, **k: 0  # generic kb:nvda+x
		dialog._askConflict = lambda *a: dialog.MOVE
		d._addCaptured(self.cmd("b"), kb("nvda+x"))
		self.assertEqual(SPOKEN[-1], "Moved kb:nvda+x to Beta")
		cm = {c.key: c.gestures for c in self.m.commands()}
		self.assertEqual((cm["a"], cm["e"], cm["b"]), ([], [], ["kb(laptop):nvda+x", "kb:nvda+x"]))
		self.assertEqual(d._realConflicts(), [])
		dialog._askConflict = lambda *a: None  # cancel
		d._addCaptured(self.cmd("c"), kb("nvda+x"))
		self.assertEqual(self.m.user["c"], [])
		dialog._askConflict = lambda *a: dialog.KEEP
		d._addCaptured(self.cmd("d"), kb("nvda+x"))
		self.assertEqual(SPOKEN[-1], "Added kb:nvda+x")

	def test_add_via_capture(self):
		d = self.d
		setKey(d.cmdAddon, "*"); d.refreshCommands(); self.sel("c")
		dialog._choose = lambda *a, **k: 0
		dialog._choose = pick("Add a gesture")
		d.onCmdMenu(None)
		self.assertIs(cap()(G(["kb(desktop):nvda"], mod=True)), False)
		self.assertIsNotNone(cap())
		cap()(kb("nvda+q")); fakewx.runCalls()
		self.assertIsNone(cap())
		self.assertIn("kb:nvda+q", self.m.user["c"])

	def test_navigation(self):  # U4
		d = self.d
		d.selectPage(dialog.PAGE_STATS); d.selectPage(dialog.PAGE_CONFLICTS)
		d.statsList.sel = 0; d.onStatsActivate(None)
		self.assertEqual(d.book.sel, dialog.PAGE_COMMANDS)
		self.assertEqual(d.cmdRows[d.cmdList.sel][0].key, "a")
		# Conflicts: changing a command's key starts at once, without leaving the tab
		d.selectPage(dialog.PAGE_CONFLICTS)
		dialog._choose = pick("Change the gesture")
		d.confList.sel = 0; d.onConflictActivate(None)
		self.assertEqual(d.book.sel, dialog.PAGE_CONFLICTS); self.assertIsNotNone(cap())
		cap()(kb("escape")); fakewx.runCalls(); self.assertIsNone(cap())
		d.selectPage(dialog.PAGE_COMMANDS)
		d.cmdFilter.sel = dialog.CMD_WITHOUT; d.refreshCommands()
		d.statsList.sel = 0; d.onStatsActivate(None)
		self.assertEqual((d.cmdFilter.sel, d.cmdRows[d.cmdList.sel][0].key), (dialog.CMD_ALL, "a"))
		d.goToCommand("zzz")
		self.assertIn("not available here", SPOKEN[-1])

	def test_replace_existing(self):
		d = self.d
		setKey(d.cmdAddon, "*"); d.refreshCommands(); self.sel("c")  # Core has kb:nvda+y
		dialog._choose = lambda *a, **k: None  # cancel: nothing happens
		d.onCmdMenu(None); self.assertIsNone(cap())
		defaults = []
		dialog._choose = lambda p, m, t, items, default=0: defaults.append(default) or 0  # its shortcut, "Change it"
		d.onCmdMenu(None); cap()(kb("nvda+q")); fakewx.runCalls()
		self.assertEqual(self.cmd("c").gestures, ["kb:nvda+q"])
		self.assertEqual(SPOKEN[-1], "Replaced kb:nvda+y with kb:nvda+q")
		# replacing a laptop-only shortcut offers "laptop only" first
		orig = dialog.gestureParts
		self.addCleanup(setattr, dialog, "gestureParts", orig)
		dialog.gestureParts = lambda g: (g, {"kb(desktop)": "desktop", "kb(laptop)": "laptop"}.get(g.split(":")[0]), None)
		d._addCaptured(self.cmd("b"), kb("nvda+w"), "kb(laptop):nvda+x")
		self.assertEqual(defaults[-1], 2)
		self.assertEqual(self.cmd("b").gestures, ["kb:nvda+w"])
		# several shortcuts: the user picks which one to change
		self.m.user["a"] = ["kb:nvda+k"]; d.commands = self.m.commands(); d.refreshCommands(); self.sel("a")
		picks = []
		dialog._choose = lambda p, m, t, items, default=0: picks.append(items) or (2 if len(picks) == 1 else 0)
		d.onCmdMenu(None); cap()(kb("nvda+j")); fakewx.runCalls()
		self.assertEqual(len(picks[0]), 2 * 2 + 3)  # change / remove for each shortcut, then add / reset / reset all
		self.assertTrue(picks[0][2].startswith("Change kb:nvda+k"))
		self.assertEqual(self.cmd("a").gestures, ["kb:nvda+x", "kb:nvda+j"])
		# Add always adds one more
		dialog._choose = lambda p, m, t, items, **k: items.index("Add a gesture...") if "Add a gesture..." in items else 0
		d.onCmdMenu(None); cap()(kb("nvda+l")); fakewx.runCalls()
		self.assertIn("kb:nvda+l", self.cmd("a").gestures); self.assertIn("kb:nvda+j", self.cmd("a").gestures)
		# same key as the old one: nothing changes
		d._addCaptured(self.cmd("a"), kb("nvda+j"), "kb:nvda+j")
		self.assertIn("already assigned", SPOKEN[-1])
		# the new shortcut fails: the old one is kept
		add = dialog.addGesture
		dialog.addGesture = lambda c, g: None
		self.addCleanup(setattr, dialog, "addGesture", add)
		d._addCaptured(self.cmd("a"), kb("nvda+z"), "kb:nvda+j")
		self.assertIn("kb:nvda+j", self.cmd("a").gestures); self.assertIn("was kept", SPOKEN[-1])

	def test_keeps_place(self):
		d = self.d
		# Ctrl+T keeps the focused control and the selected rows
		setKey(d.cmdAddon, "*"); d.refreshCommands(); self.sel("d"); d.cmdList.SetFocus()
		d.testResult.SetValue("last")
		d.onToggleLanguage(None); fakewx.runCalls()
		self.assertIs(fakewx.FOCUS[0], d.cmdList); self.assertEqual(d.cmdRows[d.cmdList.sel][0].key, "d")
		self.assertEqual(d.testResult.GetValue(), "last")
		self.plugin.stats.record("e", "Echo", "addB", None); d.selectPage(dialog.PAGE_STATS); d.refreshStats(); d.statsList.sel = 1; key = d.statsKeys[1]; d.statsList.SetFocus()
		d.onToggleLanguage(None); fakewx.runCalls()
		self.assertEqual(d.statsKeys[d.statsList.sel], key); self.assertIs(fakewx.FOCUS[0], d.statsList)
		d.selectPage(dialog.PAGE_GUIDES); d.guideList.sel = 0; first = d.guideRows[0]["name"]
		d.guideList.sel = 1; d.onToggleLanguage(None); fakewx.runCalls()
		self.assertEqual(d.guideRows[d.guideList.sel]["name"], "nvda:keyCommands")  # NVDA's own guides too
		self.assertEqual(first, "nvda:userGuide")
		d.guideList.sel = 2; name = d.guideRows[2]["summary"]
		d.onToggleLanguage(None); fakewx.runCalls()
		self.assertEqual(d.guideRows[d.guideList.sel]["summary"], name)
		# an edited command that leaves the filtered list: the row that took its place is selected
		d.selectPage(dialog.PAGE_COMMANDS)
		setKey(d.cmdAddon, "*"); d.cmdFilter.sel = dialog.CMD_ALL; d.refreshCommands()
		d.cmdFilter.sel = 4; d.refreshCommands()  # commands with conflicts
		self.assertTrue(len(d.cmdRows) >= 2)
		d.cmdList.sel = 1; target = d.cmdRows[1][0]
		dialog._choose = lambda *a, **k: 0
		while target.gestures and target.key in [c.key for c, _n in d.cmdRows]:
			d.cmdList.sel = [c.key for c, _n in d.cmdRows].index(target.key); d.onRemove(None)
			target = self.cmd(target.key)
		self.assertTrue(0 <= d.cmdList.sel < max(1, len(d.cmdRows)))
		# the command menu never piles up bindings
		# choosing another command ends the return to Conflicts
		d._returnTo = (0, "kb:nvda+x", "both", "zz")
		d.cmdList.Select(0)
		self.assertIsNone(d._returnTo)

	def test_replace_keeps_included_default(self):
		d = self.d
		dialog._choose = lambda *a, **k: 0  # all keyboard layouts
		d._addCaptured(self.cmd("b"), kb("nvda+x"), "kb(laptop):nvda+x")  # Beta's laptop default, same key
		self.assertNotIn("kb(laptop):nvda+x", self.m.unbound["b"])  # never unbound: it would block the new one
		self.assertIn("kb:nvda+x", self.m.user["b"]); self.assertIn("Replaced", SPOKEN[-1])

	def test_round_two(self):
		d = self.d
		# Ctrl+T in the search field stays there
		d.cmdFilter.SetFocus(); d.onToggleLanguage(None); fakewx.runCalls()
		self.assertIs(fakewx.FOCUS[0], d.cmdFilter)
		# a selected Conflicts row survives Ctrl+T pressed on another tab
		d.coreConf.value = True; d.selectPage(dialog.PAGE_CONFLICTS); d.refreshConflicts()
		d.confList.sel = len(d.confRows) - 1; want = d._confId(d.confRows[-1])
		d.selectPage(dialog.PAGE_TESTER); d.onToggleLanguage(None); fakewx.runCalls()
		d.coreConf.value = True; d.selectPage(dialog.PAGE_CONFLICTS)
		self.assertEqual(d._confId(d.confRows[d.confList.sel]), want)
		# statistics that could not be read are never reset or overwritten
		self.plugin.stats.readOnly = True; asked = []
		dialog._ask = lambda *a: asked.append(a) or True
		d.onReset(None); self.assertEqual(asked, []); self.assertTrue("Restart NVDA" in SPOKEN[-1] or "เริ่ม NVDA ใหม่" in SPOKEN[-1])
		self.plugin.stats.readOnly = False
		# a dialog that fails while being built is destroyed
		orig = dialog.ManagerDialog._buildUi
		self.addCleanup(setattr, dialog.ManagerDialog, "_buildUi", orig)
		def boom(self): raise ValueError("x")
		dialog.ManagerDialog._buildUi = boom
		with self.assertRaises(ValueError):
			dialog.ManagerDialog(None, self.plugin)
		# reset whose save fails reports it
		dialog.ManagerDialog._buildUi = orig
		def fail(): raise OSError("locked")
		dialog.saveUserGestures = fail
		self.m.user["a"].append("kb:nvda+k"); d.commands = self.m.commands(); d.selectPage(dialog.PAGE_COMMANDS)
		setKey(d.cmdAddon, "*"); d.refreshCommands(); self.sel("a"); d.onResetCommand(None)
		self.assertTrue("could not be saved" in SPOKEN[-1] or "ไม่สามารถบันทึกปุ่มลัดเริ่มต้น" in SPOKEN[-1], SPOKEN[-1])

	def test_user_review_round(self):
		d = self.d
		asked = []
		dialog._ask = lambda p, msg, t, **k: asked.append(msg) or False
		# a plain typing key needs a confirmation, and No is the default answer
		d._addCaptured(self.cmd("c"), kb("t"))
		self.assertIn("normal typing key", asked[-1]); self.assertNotIn("kb:t", self.m.user["c"])
		dialog._ask = lambda *a, **k: True
		# the first question already says whether the key is free or used
		prompts = []
		dialog._choose = lambda p, m, t, items, **k: prompts.append(m) or 0
		d._addCaptured(self.cmd("c"), kb("nvda+q")); self.assertIn("It is free.", prompts[-1])
		# the conflict question says which command really runs, warns about NVDA's own keys, offers another key
		qs = []
		dialog._askConflict = lambda p, msg, t: qs.append(msg) or dialog.AGAIN
		d._addCaptured(self.cmd("b"), kb("nvda+y"))
		self.assertIn("already used by", prompts[-1])
		self.assertIn("NVDA's own commands", qs[-1]); self.assertIn("Keep on both commands", qs[-1])
		self.assertIsNotNone(cap())  # waiting for another key at once
		cap()(kb("escape")); fakewx.runCalls()
		# a command with one shortcut: one yes/no question
		dialog._ask = lambda p, msg, t, **k: asked.append(msg) or True
		self.sel("e"); d.onRemove(None)
		self.assertEqual(asked[-1], "Remove kb:nvda+x, all keyboard layouts from Echo?")
		# backups say what followed them, and the newest is offered as "undo"
		self.assertTrue(any(b and b.startswith("removing kb:nvda+x from Echo") for b in self.backups))
		# Conflicts tab: the count is said on arrival; conflicts only by default; act from the list
		d.selectPage(dialog.PAGE_COMMANDS); d.selectPage(dialog.PAGE_CONFLICTS); fakewx.runCalls()
		self.assertEqual(d.confShow.sel, 0); self.assertEqual(d.book.pages[1], "Conflicts")
		self.assertEqual(SPOKEN[-1], dialog._("1 conflict between add-ons") if len(d._realConflicts()) == 1 else "%d conflicts between add-ons" % len(d._realConflicts()))
		# one row per key; Enter asks which command, then what to do with it
		self.m.user["c"].append("kb:nvda+x"); d.commands = self.m.commands(); d.refreshAll()
		d.coreConf.value = True
		for kind in range(3):
			d.confShow.sel = kind; d.refreshConflicts()
			if d.confRows:
				break
		d.confList.sel = 0; cf = d.confRows[0]; many = len(cf.commands) > 2
		keeper = cf.commands[0]
		steps = []
		def only(p, m, t, items, **k):
			steps.append(items)
			# many: the keeper, then "only this command"; two: the other one, then "remove"
			return 0 if many else 1
		dialog._choose = only
		d.onConflictActivate(None)
		self.assertEqual(len(steps), 2)
		self.assertEqual(len(steps[0]), len(cf.commands))  # the commands sharing the key
		self.assertEqual(len(steps[1]), 3 if many else 2)
		self.assertTrue(steps[1][0].startswith("Only this command uses" if many else "Change the gesture"))
		self.assertEqual(d.book.sel, dialog.PAGE_CONFLICTS)  # stayed on the tab
		self.assertTrue(any("remaining" in x for x in SPOKEN[-2:]))
		self.assertIn(cf.gesture, self.cmd(keeper.key).gestures)
		self.assertFalse(any(cf.gesture in self.cmd(o.key).gestures for o in cf.commands if o.key != keeper.key))
		# change the key of the command in a row: captured here, and the list is back in focus
		self.m.user["c"].append("kb:nvda+x"); d.commands = self.m.commands(); d.refreshAll()
		d.selectPage(dialog.PAGE_CONFLICTS)
		for kind in range(3):
			d.confShow.sel = kind; d.refreshConflicts()
			if d.confRows:
				break
		d.confList.sel = len(d.confRows) - 1; other = d.confRows[-1].commands[-1]
		calls = []
		def change(p, m, t, items, **k):  # the last command, "Change the gesture", then all layouts
			calls.append(1)
			if len(calls) == 1:
				return len(items) - 1
			return next((i for i, x in enumerate(items) if x.startswith("Change")), 0)
		dialog._choose = change
		d.onConflictActivate(None)
		self.assertIsNotNone(cap()); self.assertEqual(d.book.sel, dialog.PAGE_CONFLICTS)
		cap()(kb("nvda+j")); fakewx.runCalls()
		self.assertEqual(d.book.sel, dialog.PAGE_CONFLICTS); self.assertIs(fakewx.FOCUS[0], d.confList)
		self.assertIn("kb:nvda+j", self.cmd(other.key).gestures)
		# going to a command and back gives the Commands tab its filters again
		d.selectPage(dialog.PAGE_COMMANDS); d.cmdFilter.sel = dialog.CMD_WITHOUT; d.refreshCommands()
		d.selectPage(dialog.PAGE_STATS); d.statsList.sel = 0; d.onStatsActivate(None)
		self.assertEqual(d.cmdFilter.sel, dialog.CMD_ALL)
		d.book.SetSelection(dialog.PAGE_STATS)
		self.assertEqual(d.cmdFilter.sel, dialog.CMD_WITHOUT)
		# Statistics: shortcuts not used in the period
		d.selectPage(dialog.PAGE_STATS); d.statsShow.sel = 2; d._statsChoice()
		self.assertTrue(all(r[1] == "Not used" for r in d.statsList.rows))
		self.assertIn("not used", d.statsInfo.value)
		self.assertFalse(any("Wait a few weeks" in x for x in SPOKEN))  # no extra hint
		# tester: "Test a shortcut" starts at once; the same braille gesture twice stops
		d.selectPage(dialog.PAGE_TESTER); d.onTest(None); self.assertIsNotNone(cap())
		cap()(G(["br(x):dot1"])); self.assertIsNotNone(cap())
		cap()(G(["br(x):dot1"])); fakewx.runCalls(); self.assertIsNone(cap()); self.assertEqual(SPOKEN[-1], "Stopped")
		# no conflicts: nothing said on arrival
		d.conflicts = []; SPOKEN.clear(); d._announceConflicts(); self.assertEqual(SPOKEN, [])
		# overrides and focus-dependent ones are reported too, after the conflicts; NVDA-only ones are not
		cf = lambda kind, addon="a": types.SimpleNamespace(kind=kind, commands=[types.SimpleNamespace(addon=addon)])
		d.conflicts = [cf("override"), cf("override"), cf("context"), cf("conflict", None)]
		d._announceConflicts(); fakewx.runCalls()
		self.assertEqual(SPOKEN[-1], "No conflicts between add-ons, 2 overrides, 1 depends on focus")
		d.conflicts += [cf("conflict"), cf("context")]
		self.assertIn("1 conflict between add-ons, 2 overrides, 2 depend on focus.", d.detailLines())
		d.conflicts = []
		self.assertEqual(d.title, "Personal Gesture Manager")

	def test_undo_skips_changes_that_did_nothing(self):
		d = self.d
		tmp = tempfile.mkdtemp(); src = os.path.join(tmp, "gestures.ini"); bdir = os.path.join(tmp, "b")
		for name, val in (("backupDir", lambda: bdir), ("gesturesPath", lambda: src)):
			self.addCleanup(setattr, dialog, name, getattr(dialog, name)); setattr(dialog, name, val)
		open(src, "w").write("v1"); core.makeBackup(src, bdir, now=lambda: 1_900_000_000, note="adding X to Y")
		open(src, "w").write("v2"); core.makeBackup(src, bdir, now=lambda: 1_900_000_100, note="resetting Z")  # did nothing
		seen = []
		dialog._choose = lambda p, m, t, items, **k: seen.append(items) or None
		d.onBackups(None)
		self.assertEqual(seen[-1][0], "Undo the last change: adding X to Y")
		self.assertTrue(seen[-1][1].endswith("before resetting Z"))

	def test_latest_requests(self):
		d = self.d
		# Enter on a command: all its shortcuts, with what each clashes with, ready to change or remove
		setKey(d.cmdAddon, "*"); d.refreshCommands(); self.sel("a")
		seen = []
		def choose(p, m, t, items, **k):
			seen.append(items)
			return 1  # "Remove kb:nvda+x": one list, one choice
		dialog._choose = choose
		d.onCmdMenu(None)
		self.assertEqual(len(seen), 1)
		self.assertTrue(seen[0][0].startswith("Change kb:nvda+x, all keyboard layouts, also used by "))
		self.assertTrue(seen[0][0].endswith("..."))
		self.assertEqual(seen[0][1], "Remove kb:nvda+x, all keyboard layouts")
		self.assertEqual(seen[0][-3:], ["Add a gesture...", "Reset this command to default",
			"Reset all commands of Add A to default..."])  # no duplicate actions: testing has its own tab
		self.assertNotIn("kb:nvda+x", self.cmd("a").gestures)
		# ...or change it: capture starts and replaces it
		self.sel("b"); seen.clear()
		dialog._choose = lambda p, m, t, items, **k: seen.append(items) or 0
		d.onCmdMenu(None); self.assertIsNotNone(cap())
		cap()(kb("nvda+k")); fakewx.runCalls()
		self.assertIn("kb:nvda+k", self.cmd("b").gestures)
		# a list emptied while a row was selected keeps no stale focused row (NVDA would say "unknown")
		d.confShow.sel = 0; d.refreshConflicts()
		if d.confRows:
			d.confList.sel = len(d.confRows) - 1
			d.confRows = []; dialog._fill(d.confList, [], "x")
			self.assertEqual(d.confList.sel, -1)
		# an empty list has no row ("1 of 1"); it says why it is empty when it gets focus
		d.selectPage(dialog.PAGE_CONFLICTS); d.confShow.sel = 2; d.refreshConflicts()
		self.assertEqual((d.confList.rows, d.confList.emptyText), ([], "No conflicts"))
		SPOKEN.clear(); d._onListFocus(types.SimpleNamespace(Skip=lambda: None), d.confList); fakewx.runCalls()
		self.assertEqual(SPOKEN, ["No conflicts"])
		# moving in the empty list, or pressing Enter, says it again
		SPOKEN.clear()
		for k in (fakewx.wx.WXK_DOWN, fakewx.wx.WXK_UP, fakewx.wx.WXK_HOME):
			d.onConflictKey(types.SimpleNamespace(GetKeyCode=lambda k=k: k, HasAnyModifiers=lambda: False, Skip=lambda: None))
		d.onConflictActivate(None)
		self.assertEqual(SPOKEN, ["No conflicts"] * 4)
		# the conflicts type box has no "All"
		self.assertEqual(d.confShow.strings, ["Conflict", "Override", "Depends on focus"])
		# tester: every result since NVDA started stays, newest first, also in a new window
		d.selectPage(dialog.PAGE_TESTER); d.onTest(None); cap()(kb("nvda+q")); cap()(kb("nvda+x")); fakewx.runCalls(); cap()(kb("escape")); fakewx.runCalls()
		self.assertEqual(len(self.plugin.testLog), 2); self.assertIn("kb:nvda+x", self.plugin.testLog[0])
		e = dialog.ManagerDialog(None, self.plugin); fakewx.runCalls()
		self.assertIn("kb:nvda+q", e.testResult.value)

	def test_failures_lose_nothing(self):
		d = self.d
		dialog._choose = lambda *a, **k: 0
		dialog._askConflict = lambda *a: dialog.MOVE
		add = dialog.addGesture
		self.addCleanup(setattr, dialog, "addGesture", add)
		# the add does not take effect: the shortcut moved away from Alpha and Echo is given back
		dialog.addGesture = lambda c, g: add(c, g) if c.key != "b" else None
		d._addCaptured(self.cmd("b"), kb("nvda+x"))
		self.assertIn("kb:nvda+x", self.cmd("a").gestures); self.assertIn("kb:nvda+x", self.cmd("e").gestures)
		self.assertIn("No changes were made", SPOKEN[-1])
		# saving gestures.ini fails: reported, the dialog keeps working
		def boom(c, g): raise OSError("read-only")
		dialog.addGesture = boom
		d._addCaptured(self.cmd("c"), kb("nvda+q"))
		self.assertIn("Could not fully apply", SPOKEN[-1])
		rm = dialog.removeGesture
		self.addCleanup(setattr, dialog, "removeGesture", rm)
		dialog.removeGesture = boom
		setKey(d.cmdAddon, "*"); d.refreshCommands(); self.sel("c"); d.onRemove(None)
		self.assertIn("Could not remove", SPOKEN[-1])
		dialog.addGesture, dialog.removeGesture = add, rm
		# replace with a shortcut the command already has: only the old one is removed
		self.m.user["c"] = ["kb:nvda+k"]; d.commands = self.m.commands()
		d._addCaptured(self.cmd("c"), kb("nvda+k"), "kb:nvda+y")
		self.assertEqual(self.cmd("c").gestures, ["kb:nvda+k"]); self.assertEqual(SPOKEN[-1], "Replaced kb:nvda+y with kb:nvda+k")

	def test_result_spoken_after_focus_arrives(self):
		d = self.d
		focus = [None]
		queued = []
		ap = types.ModuleType("api"); ap.getFocusObject = lambda: focus[0]
		qh = types.ModuleType("queueHandler"); qh.eventQueue = "events"
		qh.queueFunction = lambda q, f, *a: queued.append((q, f, a))
		sys.modules["api"], sys.modules["queueHandler"] = ap, qh
		self.addCleanup(sys.modules.pop, "api"); self.addCleanup(sys.modules.pop, "queueHandler")
		d.selectPage(dialog.PAGE_CONFLICTS); fakewx.CALLS.clear()  # (the count said on arrival)
		d.confList.sel = 0
		SPOKEN.clear(); d.onConflictKey(types.SimpleNamespace(GetKeyCode=lambda: fakewx.wx.WXK_DELETE, HasAnyModifiers=lambda: False))
		self.assertEqual(d.book.sel, dialog.PAGE_CONFLICTS)  # back at once
		self.assertEqual((SPOKEN, queued), ([], []))  # nothing spoken while NVDA's focus is elsewhere
		f, a, kw = fakewx.CALLS.pop(0); f(*a, **kw)  # one 50 ms check: still not there
		self.assertEqual(len(fakewx.CALLS), 1)  # and another one scheduled
		self.assertEqual(queued, [])
		focus[0] = types.SimpleNamespace(windowHandle=d.confList.GetHandle())
		fakewx.runCalls()
		self.assertEqual(len(queued), 1); self.assertIn("remaining", queued[0][2][0])
		# focus never arrives (e.g. another window): spoken anyway after the time limit, once
		queued.clear(); focus[0] = None
		d._speakAfterFocus("x", "confList", tries=3); fakewx.runCalls()
		self.assertEqual(queued, [("events", dialog.ui.message, ("x",))])
		# closed meanwhile: nothing
		queued.clear(); d._closed = True
		d._speakAfterFocus("y", "confList"); fakewx.runCalls()
		self.assertEqual(queued, []); d._closed = False

	def test_shortcuts_window_keys(self):
		W = dialog._ShortcutsDialog
		w = W.__new__(W)
		ended = []
		w.EndModal = lambda code: ended.append(code)
		actions = [("Change a...", "change", "kb:a", "a"), ("Remove a", "remove", "kb:a", "a"),
			("Change b...", "change", "kb:b", "b"), ("Remove b", "remove", "kb:b", "b"),
			("Add a gesture...", "add", None, None)]
		w.actions, w.rows, w.result, w.name = actions, [0, 2], None, "Echo"
		w.list = types.SimpleNamespace(GetSelection=lambda: 1)
		key = lambda k, mods=False: types.SimpleNamespace(GetKeyCode=lambda: k, HasAnyModifiers=lambda: mods,
			Skip=lambda: ended.append("skip"))
		w.onListKey(key(fakewx.wx.WXK_RETURN)); self.assertEqual(w.result, 2)  # change b
		asked = []
		dialog._ask = lambda p, msg, t, **k: asked.append(msg) or False  # No: nothing removed, still there
		w.result = None; w.onListKey(key(fakewx.wx.WXK_DELETE)); self.assertIsNone(w.result)
		self.assertEqual(asked, ["Remove kb:b, all keyboard layouts from Echo?"])
		dialog._ask = lambda *a, **k: True
		w.onListKey(key(fakewx.wx.WXK_DELETE)); self.assertEqual(w.result, 3)  # remove b, confirmed
		w.onListKey(key(65)); self.assertEqual(ended[-1], "skip")
		w.rows = []; w.list = types.SimpleNamespace(GetSelection=lambda: -1); SPOKEN.clear()
		w.onListKey(key(fakewx.wx.WXK_DOWN)); w.onListKey(key(fakewx.wx.WXK_DELETE))
		self.assertEqual(SPOKEN, ["No gesture", "No gesture"])

	def test_tab_keys_and_open_again(self):
		d = self.d
		said = []
		d._sayTabFirst = lambda page: said.append(page)
		key = lambda k, shift=False, ctrl=True: types.SimpleNamespace(GetKeyCode=lambda: k, ControlDown=lambda: ctrl,
			AltDown=lambda: False, ShiftDown=lambda: shift, Skip=lambda: said.append("skip"))
		d.onCharHook(key(ord("3"))); self.assertEqual(d.book.sel, dialog.PAGE_STATS)
		d.onCharHook(key(fakewx.wx.WXK_TAB)); self.assertEqual(d.book.sel, dialog.PAGE_TESTER)
		d.onCharHook(key(fakewx.wx.WXK_TAB, shift=True)); d.onCharHook(key(fakewx.wx.WXK_TAB, shift=True))
		self.assertEqual(d.book.sel, dialog.PAGE_CONFLICTS)
		d.onCharHook(key(ord("1"))); d.onCharHook(key(fakewx.wx.WXK_TAB, shift=True))
		self.assertEqual(d.book.sel, dialog.PAGE_GUIDES)  # wraps around
		self.assertEqual(said, [2, 3, 2, 1, 0, 4])
		d.onCharHook(key(ord("2"), ctrl=False)); self.assertEqual(said[-1], "skip")  # plain keys go on
		# opened again: back to the last control, and said so
		d._lastFocus = d.cmdFilter; SPOKEN.clear()
		d.bringBack(); fakewx.runCalls()
		self.assertIs(fakewx.FOCUS[0], d.cmdFilter); self.assertIn("Personal Gesture Manager is already open", SPOKEN)

	def test_back_to_conflicts(self):
		d = self.d
		d.selectPage(dialog.PAGE_CONFLICTS); fakewx.runCalls()
		n0 = len(d.confRows)
		# Delete on a key asks which command, then removes the key from that command only
		d.confList.sel = 0; cf = d.confRows[0]; c = cf.commands[0]
		dialog._choose = lambda *a, **k: 0
		d.onConflictKey(types.SimpleNamespace(GetKeyCode=lambda: fakewx.wx.WXK_DELETE, HasAnyModifiers=lambda: False))
		self.assertNotIn(cf.gesture, self.cmd(c.key).gestures)
		self.assertEqual(d.book.sel, dialog.PAGE_CONFLICTS); self.assertIn("remaining", SPOKEN[-1])
		self.assertEqual(len(d.confRows), n0 - 1)
		# a cancelled change stays in the list, and does not jump back later
		if d.confRows:
			d.confList.sel = 0
			dialog._choose = pick("Change the gesture")
			d.onConflictActivate(None); cap()(kb("escape")); fakewx.runCalls()
			self.assertIsNone(d._returnTo); self.assertEqual(d.book.sel, dialog.PAGE_CONFLICTS)
		# other keys go on to the list
		skipped = []
		d.onConflictKey(types.SimpleNamespace(GetKeyCode=lambda: 65, HasAnyModifiers=lambda: False, Skip=lambda: skipped.append(1)))
		self.assertEqual(skipped, [1])
		# from Statistics: no return
		dialog._choose = lambda *a, **k: 0
		d.selectPage(dialog.PAGE_STATS); d.statsList.sel = 0; d.onStatsActivate(None)
		d.onRemove(None)
		self.assertEqual(d.book.sel, dialog.PAGE_COMMANDS)

	def test_tab_failure_is_isolated(self):  # #8
		d = self.d
		d.stats.counts = lambda p: 1 / 0
		d.refreshStats()
		self.assertEqual((d.statsList.rows, d.statsList.emptyText), ([], "This list could not be loaded. Details are in the NVDA log."))
		self.assertEqual(d.statsKeys, [])
		d.onStatsActivate(None)
		d.refreshConflicts()
		self.assertEqual(d.confList.rows[0][0], "kb:nvda+x")

	def test_tester(self):
		d = self.d
		d.onTest(None)
		self.assertTrue(SPOKEN[-1].startswith("Testing."))
		cap()(kb("nvda+x")); fakewx.runCalls()
		self.assertTrue(d.testResult.value.startswith("In notepad:"))
		self.assertIn("Warning: conflict", d.testResult.value)  # Alpha vs Echo, both global plugins
		self.assertIsNotNone(cap())
		cap()(kb("nvda+z")); fakewx.runCalls()
		self.assertIn("is free", d.testResult.value)
		cap()(kb("escape")); fakewx.runCalls()
		self.assertIsNone(cap()); self.assertIn("Stopped", SPOKEN)
		d.onTest(None)
		d.onActivate(types.SimpleNamespace(GetActive=lambda: False, Skip=lambda: None))
		self.assertIsNone(cap())
		d.onTest(None); d.onClose(None)
		self.assertIsNone(cap()); self.assertIsNone(self.plugin.dialog)
		n = len(SPOKEN); d._announceConflicts(); self.assertEqual(len(SPOKEN), n)  # silent after close

if __name__ == "__main__":
	unittest.main()
