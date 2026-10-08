"""End to end: the real add-on code (dialog and plugin functions) on a faithful model of NVDA's gesture maps.
After every change, three things must agree: what the Commands tab shows, what NVDA itself lists
(Input gestures), and which script NVDA really runs for the key."""
import os, sys, types, builtins, unittest
builtins._ = lambda s: s
sys.path.insert(0, os.path.dirname(__file__))
import fakewx
fakewx.install()
import nvdasim as sim
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins"))
import personalGestureManager as pgm
from personalGestureManager import core, dialog

A = sim.plugin("addA", scripts=[("alpha", "Alpha"), ("alpha2", "Alpha two")],
	gestures={"kb:nvda+shift+x": "alpha", "kb:nvda+shift+y": "alpha2"}, category="Add A")
B = sim.plugin("addB", scripts=[("beta", "Beta"), ("beta2", "Beta two"), ("beta3", "Beta three"), ("hidden", None)],
	gestures={"kb:nvda+shift+z": "beta", "kb:nvda+shift+h": "hidden"}, category="Add B")
C = sim.plugin("addC", scripts=[("gamma", "Gamma")], category="Add C")
sim.RUNNING.append(sim.Addon("addC", "Add C"))
X = "kb:nvda+shift+x"


class T(unittest.TestCase):
	def setUp(self):
		sim.start([A, B, C])
		sim.SPOKEN.clear(); fakewx.CALLS.clear(); sim.LOG.clear()
		pgm._gestureTextCache.clear()
		self.answers = []
		dialog._choose = self.choose
		dialog._shortcutsDialog = fakewx.shortcutsViaChoose(dialog)
		dialog._ask = lambda *a, **k: True
		dialog._askConflict = lambda *a: self.conflictAnswer
		self.conflictAnswer = dialog.KEEP
		dialog.listAddonGuides = lambda: []
		dialog.nvdaGuides = lambda: []
		stats = core.StatsStore(os.path.join(sim.TMP, "s.json"))
		self.plugin = types.SimpleNamespace(stats=stats, dialog=None, ensureBackup=lambda note=None: None,
			uiLanguage="en", setUiLanguage=lambda l: None, openManager=lambda *a: None)
		dialog.envInfo = lambda: {"version": "2026.3", "mode": "installed", "configPath": sim.TMP, "layout": "desktop", "app": "x"}
		self.d = dialog.ManagerDialog(None, self.plugin)
		fakewx.runCalls()
		dialog.setUiLanguage("en")

	def choose(self, parent, msg, title, items, default=0):
		"""Answers in order: a string picks the first item starting with it; None cancels."""
		want = self.answers.pop(0)
		if want is None:
			return None
		for i, t in enumerate(items):
			if t.startswith(want) or ", " + want in t or ": " + want in t:
				return i
		self.fail("no item %r in %r (%s)" % (want, items, msg))

	# ---------- helpers ----------
	def truth(self):
		"""{command name: sorted gestures} as NVDA lists them now (after a reload of gestures.ini)."""
		sim.loadUserGestureMap()
		return {c.name: sorted(c.gestures) for c in pgm.collectCommands(None) if c.addon or c.name in ("Say all", "Reports the title")}

	def shown(self):
		"""{command name: shortcuts column} of the Commands tab, all add-ons."""
		d = self.d
		dialog.ManagerDialog._setChoice  # noqa
		d.cmdAddon.sel = [k for k, t in d.cmdAddon.items].index(dialog.ALL); d.cmdFilter.sel = dialog.CMD_ALL
		d.refreshCommands()
		return {c.name: row[1] for (c, _n), row in zip(d.cmdRows, d.cmdList.rows)}

	def check(self):
		"""The tab, the dialog's data and NVDA agree."""
		truth = self.truth()
		mine = {c.name: sorted(c.gestures) for c in self.d.commands if c.addon or c.name in ("Say all", "Reports the title")}
		self.assertEqual(mine, truth)
		shown = self.shown()
		for name, gs in truth.items():
			self.assertEqual(sorted(shown[name].split(", ")), sorted(pgm.gestureText(g) for g in gs) if gs else ["No gesture"],
				name)
		self.assertEqual(sim.LOG, [])
		return truth

	def select(self, name):
		d = self.d
		d.cmdAddon.sel = [k for k, t in d.cmdAddon.items].index(dialog.ALL); d.cmdFilter.sel = dialog.CMD_ALL; d.refreshCommands()
		d.cmdList.sel = [c.name for c, _n in d.cmdRows].index(name)

	def add(self, name, key, layout="all keyboard layouts", conflict=dialog.KEEP):
		"""Add a gesture from the Commands tab: Enter, Add a gesture, press the key, choose the layout."""
		self.select(name)
		self.conflictAnswer = conflict
		self.answers += ["Add a gesture", layout]
		self.d.onCmdMenu(None)
		sim.manager._captureFunc(types.SimpleNamespace(normalizedIdentifiers=sim.kbIds(key, "desktop"), isModifier=False))
		fakewx.runCalls()

	def conflictRow(self, gesture, name=None):
		"""Select the row of this key (and command): one row per command sharing the key."""
		d = self.d
		d.selectPage(dialog.PAGE_CONFLICTS); fakewx.runCalls()
		d.coreConf.value = True
		for kind in range(3):
			d.confShow.sel = kind; d.refreshConflicts()
			for i, cf in enumerate(d.confRows):
				if cf.gesture == gesture and name in [None] + [c.name for c in cf.commands]:
					d.confList.sel = i
					if name:
						self.answers.append(name)  # Enter first asks which command
					return cf
		return None

	def runs(self, key, layout="desktop"):
		sim.loadUserGestureMap()
		return sim.findScript(sim.kbIds(key, layout))

	# ---------- the reported case: a conflict made on purpose, resolved in the Conflicts tab ----------
	def test_conflict_other_gets_no_shortcut(self):
		self.add("Beta two", "nvda+shift+x")
		self.assertEqual(self.check()["Beta two"], [X])
		self.assertIsNotNone(self.conflictRow(X, "Beta two"))
		self.answers += ["Remove"]  # Alpha keeps it
		self.d.onConflictActivate(None); fakewx.runCalls()
		t = self.check()
		self.assertEqual((t["Alpha"], t["Beta two"]), ([X], []))
		self.assertIsNone(self.conflictRow(X))
		self.assertEqual(self.runs("nvda+shift+x"), "alpha")

	def test_conflict_default_owner_loses_it(self):
		self.add("Beta two", "nvda+shift+x")
		self.conflictRow(X, "Alpha")
		self.answers += ["Remove"]  # Alpha (whose default it is) loses it
		self.d.onConflictActivate(None); fakewx.runCalls()
		t = self.check()
		self.assertEqual((t["Alpha"], t["Beta two"]), ([], [X]))
		self.assertEqual(self.runs("nvda+shift+x"), "beta2")
		self.assertIsNone(self.conflictRow(X))

	def test_conflict_other_gets_new_key(self):
		self.add("Beta two", "nvda+shift+x")
		self.conflictRow(X, "Beta two")
		self.answers += ["Change the gesture", "all keyboard layouts"]
		self.d.onConflictActivate(None)
		sim.manager._captureFunc(types.SimpleNamespace(normalizedIdentifiers=sim.kbIds("nvda+shift+q", "desktop"), isModifier=False))
		fakewx.runCalls()
		t = self.check()
		self.assertEqual((t["Alpha"], t["Beta two"]), ([X], ["kb:nvda+q+shift"]))
		self.assertEqual(self.d.book.sel, dialog.PAGE_CONFLICTS)
		self.assertEqual((self.runs("nvda+shift+x"), self.runs("nvda+shift+q")), ("alpha", "beta2"))

	def test_conflict_default_owner_gets_new_key(self):
		self.add("Beta two", "nvda+shift+x")
		self.conflictRow(X, "Alpha")
		self.answers += ["Change the gesture", "all keyboard layouts"]
		self.d.onConflictActivate(None)
		sim.manager._captureFunc(types.SimpleNamespace(normalizedIdentifiers=sim.kbIds("nvda+shift+q", "desktop"), isModifier=False))
		fakewx.runCalls()
		t = self.check()
		self.assertEqual((t["Alpha"], t["Beta two"]), (["kb:nvda+q+shift"], [X]))
		self.assertEqual((self.runs("nvda+shift+x"), self.runs("nvda+shift+q")), ("beta2", "alpha"))

	def test_three_commands(self):
		self.add("Beta two", "nvda+shift+x")
		self.add("Gamma", "nvda+shift+x")
		cf = self.conflictRow(X, "Gamma")
		self.assertEqual(len(cf.commands), 3)
		self.assertEqual(len([r for r in self.d.confRows if r is cf]), 1)  # one row per key
		self.answers += ["Only this command"]  # the other two lose it
		self.d.onConflictActivate(None); fakewx.runCalls()
		t = self.check()
		self.assertEqual((t["Alpha"], t["Beta two"], t["Gamma"]), ([], [], [X]))
		self.assertEqual(self.runs("nvda+shift+x"), "gamma")
		self.assertIsNone(self.conflictRow(X))

	def test_same_group_cannot_share(self):
		"""Two commands of one class: NVDA runs and lists only one. "Keep on both" still moves it, and says so."""
		self.add("Beta two", "nvda+shift+x")
		asked = []
		dialog._askConflict = lambda p, msg, t: asked.append(msg) or dialog.KEEP
		self.add("Beta three", "nvda+shift+x")
		dialog._askConflict = lambda *a: self.conflictAnswer
		self.assertIn("same group of commands", asked[0])
		t = self.check()
		self.assertEqual((t["Beta two"], t["Beta three"], t["Alpha"]), ([], [X], [X]))
		self.assertEqual(self.d.book.pages, self.d.book.pages)
		# no dead binding left behind: removing it from Beta three gives it to nobody else of that add-on
		self.select("Beta three"); self.answers += ["Remove"]
		self.d.onCmdMenu(None); fakewx.runCalls()
		t = self.check()
		self.assertEqual((t["Beta two"], t["Beta three"]), ([], []))
		self.assertEqual(self.runs("nvda+shift+x"), "alpha")

	def test_same_group_default(self):
		"""Alpha two takes Alpha's default key (same class): Alpha really loses it, and gets it back on reset."""
		self.add("Alpha two", "nvda+shift+x")
		t = self.check()
		self.assertEqual((t["Alpha"], t["Alpha two"]), ([], [X, "kb:nvda+shift+y"]) if False else ([], sorted([X, "kb:nvda+shift+y"])))
		self.assertEqual(self.runs("nvda+shift+x"), "alpha2")
		self.select("Alpha two"); self.answers += ["Remove NVDA+SHIFT+X"]
		self.d.onCmdMenu(None); fakewx.runCalls()
		t = self.check()
		self.assertEqual(t["Alpha"], [])  # not silently back
		self.assertIsNone(self.runs("nvda+shift+x"))
		self.select("Alpha"); self.answers += ["Reset this command"]
		self.d.onCmdMenu(None); fakewx.runCalls()
		self.assertEqual(self.check()["Alpha"], [X])

	def test_old_dead_binding_is_cleaned(self):
		"""gestures.ini already holds a binding NVDA hides (left by an older version or another tool)."""
		gm = sim.manager.userGestureMap
		gm.add(X, "globalPlugins.addB", "GlobalPlugin", "beta2")
		gm.add(X, "globalPlugins.addB", "GlobalPlugin", "beta3")  # hidden behind beta2
		gm.save(); self.d.commands = self.d._collect()
		self.assertEqual(self.check()["Beta three"], [])
		self.select("Beta two"); self.answers += ["Remove"]
		self.d.onCmdMenu(None); fakewx.runCalls()
		t = self.check()
		self.assertEqual((t["Beta two"], t["Beta three"]), ([], []))  # Beta three did not take it over

	def test_failed_add_leaves_nothing(self):
		"""A shortcut NVDA does not apply is undone completely: gestures.ini is as before."""
		before = sim.manager.userGestureMap.export()
		orig = pgm.collectCommands
		self.addCleanup(setattr, dialog, "collectCommands", orig)
		dialog.collectCommands = lambda f=None: [c for c in orig(f) if c.name != "Beta two"] + [
			core.Command(*[getattr(c, a) for a in ("key", "name", "category", "addon", "addonSummary", "module",
				"className", "scriptName")], []) for c in orig(f) if c.name == "Beta two"]  # never shows a shortcut
		self.add("Beta two", "nvda+shift+q")
		self.assertIn("Could not assign", sim.SPOKEN[-1])
		self.assertEqual(sim.manager.userGestureMap.export(), before)

	def test_move_and_back(self):
		self.add("Beta two", "nvda+shift+x", conflict=dialog.MOVE)
		t = self.check()
		self.assertEqual((t["Alpha"], t["Beta two"]), ([], [X]))
		self.assertEqual(self.runs("nvda+shift+x"), "beta2")
		self.add("Alpha", "nvda+shift+x", conflict=dialog.MOVE)  # given back to its owner
		t = self.check()
		self.assertEqual((t["Alpha"], t["Beta two"]), ([X], []))
		self.assertEqual(self.runs("nvda+shift+x"), "alpha")

	def test_change_remove_reset_from_menu(self):
		self.select("Alpha")
		self.answers += ["Change NVDA+SHIFT+X", "all keyboard layouts"]
		self.d.onCmdMenu(None)
		sim.manager._captureFunc(types.SimpleNamespace(normalizedIdentifiers=sim.kbIds("nvda+shift+w", "desktop"), isModifier=False))
		fakewx.runCalls()
		self.assertEqual(self.check()["Alpha"], ["kb:nvda+shift+w"])
		self.assertEqual((self.runs("nvda+shift+w"), self.runs("nvda+shift+x")), ("alpha", None))
		self.select("Alpha"); self.answers += ["Remove NVDA+SHIFT+W"]
		self.d.onCmdMenu(None); fakewx.runCalls()
		self.assertEqual(self.check()["Alpha"], [])
		self.select("Alpha"); self.answers += ["Reset this command"]
		self.d.onCmdMenu(None); fakewx.runCalls()
		self.assertEqual(self.check()["Alpha"], [X])
		self.assertEqual(self.runs("nvda+shift+x"), "alpha")

	def test_layout_only(self):
		self.add("Beta two", "nvda+shift+x", layout="desktop layout only")
		t = self.check()
		self.assertEqual(t["Beta two"], ["kb(desktop):nvda+shift+x"])
		cf = self.conflictRow(X, "Alpha")
		self.assertEqual(cf.layout, "desktop")
		self.answers += ["Remove"]
		self.d.onConflictActivate(None); fakewx.runCalls()
		t = self.check()
		self.assertEqual(self.runs("nvda+shift+x", "desktop"), "beta2")
		# Alpha keeps the key where it was not shared: on the laptop layout
		self.assertEqual(t["Alpha"], ["kb(laptop):nvda+shift+x"])
		self.assertEqual(self.runs("nvda+shift+x", "laptop"), "alpha")
		self.assertIn("on the desktop layout only", sim.SPOKEN[-1])
		self.assertIsNone(self.conflictRow(X))

	def test_delete_key_and_undo_via_reset_all(self):
		self.select("Beta"); self.d.onRemove(None); fakewx.runCalls()
		self.assertEqual(self.check()["Beta"], [])
		self.assertIsNone(self.runs("nvda+shift+z"))
		self.select("Beta"); self.answers += ["Reset all commands of Add B"]
		self.d.onCmdMenu(None); fakewx.runCalls()
		self.assertEqual(self.check()["Beta"], ["kb:nvda+shift+z"])


class R(T):
	"""Random edits; after each: the tab = NVDA's list, and a key listed for one command runs that command."""
	def runtimeAgrees(self):
		cmds = pgm.collectCommands(None)
		for layout in ("desktop", "laptop"):
			owners = {}
			for c in cmds:
				for g in c.gestures:
					lays, base = core.gestureLayouts(g)
					if layout in lays and base.startswith("kb:"):
						owners.setdefault(base[3:], []).append(c)
			for key, cs in owners.items():
				if len(cs) == 1:
					got = self.runs(key, layout)
					if got != cs[0].scriptName:
						# Only allowed when the add-on said so (blockedLayouts warning) when it was assigned.
						self.assertIn(layout, pgm.blockedLayouts(cs[0], "kb:" + key), "%s (%s) listed for %s, runs %s" % (
							key, layout, cs[0].name, got))

	def test_random(self):
		import random
		seed = int(os.environ.get("SEED", 7))
		rnd = random.Random(seed)
		names = ["Alpha", "Alpha two", "Beta", "Beta two", "Beta three", "Gamma", "Say all", "Reports the title", "hidden"]
		keys = ["nvda+shift+x", "nvda+shift+y", "nvda+shift+z", "nvda+shift+q", "nvda+a", "nvda+t", "nvda+shift+h"]
		lays = ["all keyboard layouts", "desktop layout only", "laptop layout only"]
		for step in range(int(os.environ.get("STEPS", 80))):
			before = {g: list(v) for g, v in sim.manager.userGestureMap._map.items() if v}
			op = rnd.randrange(6)
			name = rnd.choice(names)
			self.answers = []
			if op <= 1:
				self.add(name, rnd.choice(keys), rnd.choice(lays), rnd.choice([dialog.KEEP, dialog.MOVE]))
			elif op == 2:
				self.select(name)
				c = self.d.cmdRows[self.d.cmdList.sel][0]
				if c.gestures:
					self.answers += ["Remove " + pgm.gestureText(rnd.choice(c.gestures)).split(" (")[0]]
					self.d.onCmdMenu(None); fakewx.runCalls()
			elif op == 3:
				self.select(name); self.answers += ["Reset this command"]
				self.d.onCmdMenu(None); fakewx.runCalls()
				c = self.d._cmdByKey()[self.d.cmdRows[self.d.cmdList.sel][0].key]
				self.assertTrue(pgm.defaultGestures(c) <= set(c.gestures), (c.name, c.gestures))
			elif op == 4:
				d = self.d
				d.selectPage(dialog.PAGE_CONFLICTS); d.coreConf.value = True
				d.confShow.sel = rnd.randrange(3); d.refreshConflicts()
				if d.confRows:
					d.confList.sel = rnd.randrange(len(d.confRows))
					act = rnd.randrange(4)
					self.answers.append(rnd.choice(d.confRows[d.confList.sel].commands).name)  # which command
					if act == 3:  # Delete key
						d.onConflictKey(types.SimpleNamespace(GetKeyCode=lambda: fakewx.wx.WXK_DELETE,
							HasAnyModifiers=lambda: False))
					else:
						self.answers += [["Only this command", "Change the gesture", "Remove"][act]]
						if act == 1:
							self.answers += [rnd.choice(lays)]
						d.onConflictActivate(None)
						if act == 1 and sim.manager._captureFunc:
							sim.manager._captureFunc(types.SimpleNamespace(
								normalizedIdentifiers=sim.kbIds(rnd.choice(keys), "desktop"), isModifier=False))
					fakewx.runCalls()
					self.assertEqual(d.book.sel, dialog.PAGE_CONFLICTS)  # never taken elsewhere
			else:
				self.select(name)
				c = self.d.cmdRows[self.d.cmdList.sel][0]
				if c.gestures:
					g = rnd.choice(c.gestures)
					self.answers += ["Change " + pgm.gestureText(g).split(" (")[0], rnd.choice(lays)]
					self.d.onCmdMenu(None)
					if sim.manager._captureFunc:
						sim.manager._captureFunc(types.SimpleNamespace(
							normalizedIdentifiers=sim.kbIds(rnd.choice(keys), "desktop"), isModifier=False))
					fakewx.runCalls()
			self.assertEqual(self.answers, [], "step %d" % step)
			self.check()
			self.runtimeAgrees()
			self.assertFalse(any("Could not" in s for s in sim.SPOKEN), (step, sim.SPOKEN[-3:], before))


if __name__ == "__main__":
	unittest.main()
