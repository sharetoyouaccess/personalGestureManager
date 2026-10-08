"""Smoke test of the global plugin with stubbed NVDA modules."""
import os, sys, types, tempfile, builtins, unittest
builtins._ = lambda s: s
TMP = tempfile.mkdtemp()
def mod(name, **kw):
	m = types.ModuleType(name); m.__dict__.update(kw); sys.modules[name] = m; return m
class Addon:
	name = "otherAddon"; path = os.path.join(TMP, "addons", "otherAddon"); manifest = {"summary": "Other"}
mod("addonHandler", initTranslation=lambda: None, getRunningAddons=lambda: [Addon()])
mod("config", isInstalledCopy=lambda: False, conf={"keyboard": {"keyboardLayout": "laptop"}})
mod("globalPluginHandler", runningPlugins=set(), GlobalPlugin=type("GP", (), {"__init__": lambda s: None, "terminate": lambda s: None}))
mod("globalVars", appArgs=types.SimpleNamespace(secure=False, configPath=TMP))
class GM:
	def __init__(s): s._map = {}; s.saved = 0
	def add(s, g, m, c, sc): s._map.setdefault(g, []).append((m, c, sc))
	def remove(s, g, m, c, sc):
		try: s._map[g].remove((m, c, sc))
		except (KeyError, ValueError): raise ValueError
	def save(s): s.saved += 1
def _disp(gid):
	return ("keyboard, all layouts" if gid.startswith("kb:") else "x", gid.split(":", 1)[1].upper())
mod("inputCore", getDisplayTextForGestureIdentifier=_disp, normalizeGestureIdentifier=lambda g: g.lower(), manager=types.SimpleNamespace(userGestureMap=GM(), _captureFunc=None))
orig = lambda f, g: ("ran", f.__name__)
mod("scriptHandler", executeScript=orig, script=lambda **kw: (lambda f: f), getLastScriptRepeatCount=lambda: 0)
class Timer:
	def __init__(s, f): pass
	def Start(s, ms): pass
	def Stop(s): pass
mod("wx", PyTimer=Timer, ID_ANY=-1, EVT_MENU=1, CallAfter=lambda f, *a: f(*a))
LOG = []
mod("logHandler", log=types.SimpleNamespace(debugWarning=lambda *a, **k: LOG.append(("dbg", a[0])), error=lambda *a, **k: LOG.append(("err", a[0]))))
SPOKEN = []
mod("ui", message=SPOKEN.append)
menu = types.SimpleNamespace(Append=lambda *a: "item", Remove=lambda i: None)
mod("gui", mainFrame=types.SimpleNamespace(sysTrayIcon=types.SimpleNamespace(toolsMenu=menu, Bind=lambda *a: None)))
# fake add-on module living inside the add-on dir
os.makedirs(Addon.path); fake = os.path.join(Addon.path, "x.py")
other = mod("globalPlugins.other", __file__=fake)
class OtherPlugin:
	scriptCategory = "Other"
	def script_doIt(self, g):
		"""Does it"""
OtherPlugin.__module__ = "globalPlugins.other"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins"))
import personalGestureManager as igm
import scriptHandler

class T(unittest.TestCase):
	def test_flow(self):
		p = igm.GlobalPlugin()
		self.assertIsNot(scriptHandler.executeScript, orig)
		f = OtherPlugin().script_doIt
		self.assertEqual(scriptHandler.executeScript(f, object()), ("ran", "script_doIt"))
		scriptHandler.executeScript(f, None)  # no gesture -> not counted
		c = p.stats.counts("session")
		self.assertEqual(list(c.values()), [1])
		k = list(c)[0]
		self.assertEqual(p.stats.meta(k), ["Does it", "otherAddon", "Other"])
		self.assertEqual(igm.addonForModule("globalPlugins.other"), ("otherAddon", "Other"))
		self.assertEqual(igm.envInfo.__name__, "envInfo")
		cmd = igm.core.Command(k, "Does it", "Other", "otherAddon", "Other", "globalPlugins.other", "OtherPlugin", "doIt", [])
		gm = sys.modules["inputCore"].manager.userGestureMap
		igm.addGesture(cmd, "kb:nvda+q"); self.assertEqual(gm._map["kb:nvda+q"], [("globalPlugins.other", "OtherPlugin", "doIt")])
		igm.removeGesture(cmd, "kb:nvda+q"); self.assertEqual(gm._map["kb:nvda+q"], [])
		igm.removeGesture(cmd, "kb:nvda+w"); self.assertEqual(gm._map["kb:nvda+w"], [("globalPlugins.other", "OtherPlugin", None)])
		igm.addGesture(cmd, "kb:nvda+w"); self.assertEqual(gm._map["kb:nvda+w"], [("globalPlugins.other", "OtherPlugin", "doIt")])
		# an unbound laptop-only default of this command must not block its new all-layouts shortcut
		other.OtherPlugin = OtherPlugin
		OtherPlugin._OtherPlugin__gestures = {"kb(laptop):NVDA+E": "doIt"}
		igm.removeGesture(cmd, "kb(laptop):nvda+e"); igm.removeGesture(cmd, "kb(desktop):nvda+r")
		igm.addGesture(cmd, "kb:nvda+e")
		self.assertEqual(gm._map["kb(laptop):nvda+e"], [])
		self.assertEqual(igm.blockedLayouts(cmd, "kb:nvda+e"), [])
		# ...but the unbinding of another command's default stays, and is reported
		igm.addGesture(cmd, "kb:nvda+r")
		self.assertEqual(gm._map["kb(desktop):nvda+r"], [("globalPlugins.other", "OtherPlugin", None)])
		self.assertEqual(igm.blockedLayouts(cmd, "kb:nvda+r"), ["desktop"])
		self.assertTrue(igm.isUserGesture(cmd, "kb:nvda+r")); self.assertFalse(igm.isUserGesture(cmd, "kb:nvda+e9"))
		del OtherPlugin._OtherPlugin__gestures
		gm._map.clear()
		# undocumented commands
		class Hidden:
			def script_secret(self, g): pass
			def script_shown(self, g):
				"""Shown"""
		Hidden.__module__ = "globalPlugins.other"
		h = Hidden(); h._gestureMap = {"kb:nvda+1": Hidden.script_secret, "kb:nvda+2": Hidden.script_shown, "kb:nvda+3": Hidden.script_secret}
		gm.add("kb:nvda+3", "globalPlugins.other", "Hidden", None)  # user unbound this one
		u = igm._undocumentedCommands([h], set())
		self.assertEqual([(c.scriptName, c.gestures, c.addon, c.documented) for c in u], [("secret", ["kb:nvda+1"], "otherAddon", False)])
		# emulated system keyboard keys are counted under GlobalCommands
		def emu(g): pass
		emu.__name__ = "script_kb:control+c"; emu.__doc__ = "Emulates pressing control+c on the system keyboard"
		scriptHandler.executeScript(emu, object())
		self.assertEqual(p.stats.counts("session").get("globalCommands.GlobalCommands:kb:control+c"), 1)
		# a script re-entered while running is passed through by NVDA, so it is not counted
		scriptHandler._isScriptRunning = True
		import weakref
		scriptHandler._lastScriptRef = weakref.ref(OtherPlugin.script_doIt)
		before = dict(p.stats.counts("session"))
		scriptHandler.executeScript(OtherPlugin().script_doIt, object())
		self.assertEqual(p.stats.counts("session"), before)
		scriptHandler._isScriptRunning = False
		scriptHandler.executeScript(OtherPlugin().script_doIt, object())
		self.assertEqual(p.stats.counts("session")[k], before[k] + 1)
		# backups: before every change, but identical content is not duplicated
		import glob as g2
		p.ensureBackup(); p.ensureBackup()
		self.assertEqual(len(g2.glob(os.path.join(igm.backupDir(), "*.ini"))), 1)
		open(igm.gesturesPath(), "w").write("[x]")
		p.ensureBackup()
		self.assertEqual(len(g2.glob(os.path.join(igm.backupDir(), "*.ini"))), 2)
		# undocumented command keeps its row when all shortcuts are unbound
		gm.add("kb:nvda+1", "globalPlugins.other", "Hidden", None)
		u = igm._undocumentedCommands([h], set())
		self.assertEqual([(c.scriptName, c.gestures) for c in u], [("secret", [])])
		# short gesture names
		self.assertEqual(igm.gestureText("kb:nvda+x"), "NVDA+X")
		self.assertEqual(igm.gestureText("kb(laptop):nvda+x"), "NVDA+X (laptop)")
		self.assertEqual(igm.gestureText("br(x):dot1"), "DOT1 (x)")
		# save failure is reported once, then only debug-logged
		p.stats.path = "/proc/nope/s.json"; p.stats.dirty = True
		t = p._autoSave(); t.join()
		p.stats.dirty = True  # failed write keeps data marked unsaved
		t = p._autoSave(); t.join()
		# exit waits for a running background write, then saves what is left
		p.stats.path = os.path.join(TMP, "personalGestureManager", "stats.json")
		p.stats.record("late", "Late", None, None); p._autoSave(); p.stats.record("later", "Later", None, None)
		p._saveNow()
		self.assertIn("later", igm.core.StatsStore(p.stats.path).counts("all"))
		self.assertEqual([k for k, _m in LOG].count("err"), 1)
		self.assertEqual(len([m for m in SPOKEN if "could not be saved" in m]), 1)
		p.stats.path = os.path.join(TMP, "personalGestureManager", "stats.json")
		# reset to default: drops user additions and unbinding of own defaults, keeps other classes' entries
		OtherPlugin._OtherPlugin__gestures = {"kb:NVDA+5": "doIt"}
		other.OtherPlugin = OtherPlugin  # classes live in their module
		gm._map.clear()
		gm.add("kb:nvda+5", "globalPlugins.other", "OtherPlugin", None)    # user unbound default
		gm.add("kb:nvda+6", "globalPlugins.other", "OtherPlugin", "doIt")  # user added
		gm.add("kb:nvda+7", "globalPlugins.other", "OtherPlugin", None)    # unbinding of something else
		gm.add("kb:nvda+8", "globalPlugins.x", "Y", "doIt")                 # other class
		saved = gm.saved
		self.assertTrue(igm.resetCommand(cmd))
		self.assertEqual({g: v for g, v in gm._map.items() if v}, {"kb:nvda+7": [("globalPlugins.other", "OtherPlugin", None)],
			"kb:nvda+8": [("globalPlugins.x", "Y", "doIt")]})
		self.assertEqual(gm.saved, saved + 1)
		self.assertFalse(igm.resetCommand(cmd))
		p.terminate()
		self.assertIs(scriptHandler.executeScript, orig)
		self.assertTrue(os.path.isfile(os.path.join(TMP, "personalGestureManager", "stats.json")))

	def test_title_in_manager_window(self):
		"""NVDA's report-title command reports the add-on and NVDA in its window; NVDA's own elsewhere."""
		p = igm.GlobalPlugin()
		class GlobalCommands:
			def script_title(self, g): return "nvda title"
		title = GlobalCommands().script_title
		fg = types.SimpleNamespace(windowHandle=1)
		mod("api", getForegroundObject=lambda: fg)
		self.addCleanup(sys.modules.pop, "api")
		self.assertIs(p.replacedScript(title), title)  # no window open
		p.dialog = types.SimpleNamespace(GetHandle=lambda: 1, statusText=lambda: "PGM, running on NVDA",
			detailLines=lambda: ["line 1", "line 2"])
		self.addCleanup(setattr, p, "dialog", None)
		SPOKEN.clear()
		self.assertEqual(scriptHandler.executeScript(title, object()), ("ran", "_reportManager"))
		p.replacedScript(title)(None); self.assertEqual(SPOKEN, ["PGM, running on NVDA"])
		scriptHandler.getLastScriptRepeatCount = lambda: 1  # pressed twice: every detail, one per line
		p.replacedScript(title)(None); self.assertEqual(SPOKEN[-1], "line 1\nline 2")
		copied = []
		p.dialog.copyDetails = lambda: copied.append(1)
		scriptHandler.getLastScriptRepeatCount = lambda: 2  # three times: copied
		p.replacedScript(title)(None); self.assertEqual(copied, [1])
		scriptHandler.getLastScriptRepeatCount = lambda: 0
		self.assertTrue(p.replacedScript(title).__func__.speakOnDemand)  # heard in on-demand speech mode
		fg.windowHandle = 2  # a question window or another application in front
		self.assertIs(p.replacedScript(title), title)
		other = OtherPlugin().script_doIt
		fg.windowHandle = 1
		self.assertIs(p.replacedScript(other), other)

	def test_guide_helpers(self):
		root = tempfile.mkdtemp()
		def addon(name, summary, doc, langs, **kw):
			path = os.path.join(root, name)
			for l in langs:
				os.makedirs(os.path.join(path, "doc", l)); open(os.path.join(path, "doc", l, doc or "x.html"), "w").close()
			os.makedirs(path, exist_ok=True)
			return types.SimpleNamespace(name=name, path=path, manifest={"summary": summary, "description": "  Line one.\n  Line  two. ",
				"author": "A", "version": "1", "docFileName": doc}, **kw)
		good = addon("zeta", "Zeta", "readme.html", ["en", "th"], isRunning=True, isDisabled=False)
		nodoc = addon("alpha", "alpha", None, ["en"], isRunning=False, isDisabled=True)
		gone = addon("gone", "Gone", "readme.html", ["en"], isPendingRemove=True)
		class Broken:
			path = "x"
			@property
			def manifest(self): raise ValueError("bad manifest")
		sys.modules["addonHandler"].getAvailableAddons = lambda: [good, nodoc, gone, Broken()]
		g = igm.listAddonGuides()
		self.assertEqual([x["name"] for x in g], ["alpha", "zeta"])  # sorted, pending-remove and broken skipped
		self.assertEqual(sorted(g[1]["docs"]), ["en", "th"]); self.assertEqual(g[0]["docs"], {})
		self.assertEqual(g[1]["description"], "Line one. Line two.")
		self.assertEqual((g[0]["running"], g[0]["disabled"]), (False, True))
		sys.modules["globalVars"].appDir = root
		os.makedirs(os.path.join(root, "documentation", "th")); open(os.path.join(root, "documentation", "th", "userGuide.html"), "w").close()
		self.assertEqual([(k, sorted(v)) for k, v in igm.nvdaGuides()], [("userGuide", ["th"]), ("keyCommands", [])])

	def test_language_is_remembered(self):
		p = igm.GlobalPlugin()
		self.assertIsNone(p.uiLanguage)
		p.setUiLanguage("en"); p.terminate()
		self.assertEqual(igm.GlobalPlugin().uiLanguage, "en")  # kept after an NVDA restart
		open(p._settingsPath, "w").write('{"uiLanguage": "xx"}')
		self.assertIsNone(igm.GlobalPlugin().uiLanguage)       # invalid value ignored
		open(p._settingsPath, "w").write("{broken")
		q = igm.GlobalPlugin(); self.assertIsNone(q.uiLanguage)  # damaged file ignored
		q.setUiLanguage("th"); self.assertEqual(igm.GlobalPlugin().uiLanguage, "th")
		# other choices are kept with the language; a bad value is ignored on its own
		q.setSetting("statsPeriod", "month"); q.setSetting("statsShow", "least")
		r = igm.GlobalPlugin()
		self.assertEqual((r.uiLanguage, r.getSetting("statsPeriod"), r.getSetting("statsShow")), ("th", "month", "least"))
		open(p._settingsPath, "w").write('{"uiLanguage": "xx", "statsPeriod": "week", "statsShow": 5}')
		r = igm.GlobalPlugin()
		self.assertEqual((r.uiLanguage, r.getSetting("statsPeriod"), r.getSetting("statsShow", "most")), (None, "week", "most"))

	def test_secure_screen(self):
		sys.modules["globalVars"].appArgs.secure = True
		try:
			p = igm.GlobalPlugin()
			p.openManager()
			self.assertIn("Personal Gesture Manager is not available on secure screens", SPOKEN)
			p.terminate()
		finally:
			sys.modules["globalVars"].appArgs.secure = False

	def test_open_failure_and_focus_fallback(self):
		import gui
		calls = []
		gui.mainFrame.prePopup = lambda: calls.append("pre"); gui.mainFrame.postPopup = lambda: calls.append("post")
		p = igm.GlobalPlugin()
		dlg = types.ModuleType("personalGestureManager.dialog")
		class Boom:
			def __init__(self, *a): raise RuntimeError("boom")
		dlg.ManagerDialog = Boom
		sys.modules["personalGestureManager.dialog"] = dlg
		try:
			p.openManager()
		finally:
			del sys.modules["personalGestureManager.dialog"]
		self.assertEqual(calls, ["pre", "post"]); self.assertIsNone(p.dialog)
		self.assertIn("Personal Gesture Manager could not be opened. Details are in the NVDA log.", SPOKEN)
		# dead previous focus -> falls back to current focus
		class Info:
			cls = OtherPlugin; scriptName = "doIt"; gestures = ["kb:nvda+q"]
		seen = []
		def gam(obj=None, ancestors=None):
			seen.append(obj)
			if obj == "dead": raise RuntimeError("dead window")
			return {"Other": {"Does it": Info()}}
		sys.modules["inputCore"].manager.getAllGestureMappings = gam
		mod("api", getFocusObject=lambda: "alive", getFocusAncestors=lambda: [])
		gui.mainFrame.prevFocus = "dead"; gui.mainFrame.prevFocusAncestors = []
		cmds = igm.collectCommands(igm.previousFocus())
		self.assertEqual(seen, ["dead", "alive"]); self.assertEqual([c.scriptName for c in cmds], ["doIt"])
		p.terminate()

if __name__ == "__main__":
	unittest.main()
