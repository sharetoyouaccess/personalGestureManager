import os, sys, tempfile, json, time, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "addon", "globalPlugins", "personalGestureManager"))
import core

class Base:
	def script_a(self, g): pass
class Sub(Base): pass

def cmd(key, gest, addon="x"):
	return core.Command(key, key, "cat", addon, addon, "globalPlugins.m", "C", key, gest)

class T(unittest.TestCase):
	def test_layouts(self):
		self.assertEqual(core.gestureLayouts("kb(laptop):nvda+a"), ({"laptop"}, "kb:nvda+a"))
		self.assertEqual(core.gestureLayouts("kb:nvda+a")[0], {"desktop", "laptop"})
		self.assertEqual(core.gestureLayouts("br(freedomScientific):dot1")[1], "br(freedomscientific):dot1")
	def test_key(self):
		self.assertEqual(core.scriptKey(Sub, "a"), core.scriptKey(Base, "a"))
		self.assertTrue(core.scriptKey(Sub, "a").endswith(".Base:a"))
	def test_conflicts(self):
		a = cmd("a", ["kb:nvda+x"]); b = cmd("b", ["kb(laptop):nvda+x"]); c = cmd("c", ["kb:nvda+y"])
		cf = core.findConflicts([a, b, c])
		self.assertEqual(len(cf), 1); self.assertEqual(cf[0].layout, "laptop")
		d = cmd("d", ["kb:nvda+x"])
		cf = core.findConflicts([a, d])
		self.assertEqual(cf[0].layout, "both")
		e = cmd("e", ["kb:nvda+x"], None); f = cmd("f", ["kb:nvda+x"], None)
		self.assertEqual(core.findConflicts([e, f]), [])
		self.assertEqual(len(core.findConflicts([e, f], True)), 1)
	def test_forGesture(self):
		a = cmd("a", ["kb(desktop):nvda+x"]); b = cmd("b", ["kb:nvda+z"])
		r = core.commandsForGesture([a, b], ["kb(laptop):nvda+x", "kb:nvda+x"])
		self.assertEqual([(c.key, l) for c, l in r], [("a", "desktop")])
		self.assertEqual(core.commandsForGesture([a, b], ["kb:nvda+q"]), [])
	def test_stats(self):
		d = tempfile.mkdtemp(); p = os.path.join(d, "s", "stats.json")
		t = [1_800_000_000.0]
		s = core.StatsStore(p, now=lambda: t[0])
		s.record("k1", "One", "x", None); s.record("k1", "One", "x", None); s.record("k2", "Two", None, None)
		self.assertEqual(s.counts("session"), {"k1": 2, "k2": 1})
		s.save()
		t[0] += 10 * 86400
		s2 = core.StatsStore(p, now=lambda: t[0])
		s2.record("k2", "Two", None, None)
		self.assertEqual(s2.counts("session"), {"k2": 1})
		self.assertEqual(s2.counts("today"), {"k2": 1})
		self.assertEqual(s2.counts("week"), {"k2": 1})
		self.assertEqual(s2.counts("month"), {"k1": 2, "k2": 2})
		self.assertEqual(s2.counts("all"), {"k1": 2, "k2": 2})
		self.assertEqual(s2.sessionCount(), 2)
		self.assertEqual(s2.meta("k1"), ["One", "x", None])
	def test_corrupt(self):
		d = tempfile.mkdtemp(); p = os.path.join(d, "stats.json")
		open(p, "w").write("{broken")
		s = core.StatsStore(p)
		self.assertEqual(s.counts(), {}); self.assertTrue(os.path.exists(p + ".corrupt"))
	def test_reset(self):
		d = tempfile.mkdtemp(); s = core.StatsStore(os.path.join(d, "a.json"))
		s.record("k", "K", None, None); s.reset()
		self.assertEqual(s.counts("all"), {}); self.assertEqual(s.counts("session"), {})

class T2(unittest.TestCase):
	def mk(self, key, module, addon="x"):
		return core.Command(key, key, "c", addon, addon, module, "C", key, ["kb:nvda+x"])
	def test_classify(self):
		gp1 = self.mk("a", "globalPlugins.a"); gp2 = self.mk("b", "globalPlugins.b")
		app = self.mk("c", "appModules.notepad"); gc = self.mk("d", "globalCommands", None)
		obj = self.mk("e", "browseMode"); obj2 = self.mk("f", "NVDAObjects.x")
		self.assertEqual(core.classify([gp1, gp2]), ("conflict", None))
		self.assertEqual(core.classify([gp1, gc]), ("override", gp1))
		self.assertEqual(core.classify([app, gc, obj]), ("override", app))
		self.assertEqual(core.classify([obj, obj2]), ("context", None))
		cf = core.findConflicts([gc, gp1])
		self.assertEqual((cf[0].kind, cf[0].active.key, [c.key for c in cf[0].commands]), ("override", "a", ["a", "d"]))
	def test_backups(self):
		d = tempfile.mkdtemp(); src = os.path.join(d, "gestures.ini"); b = os.path.join(d, "b")
		t = [1_800_000_000.0]
		p0 = core.makeBackup(src, b, now=lambda: t[0])  # missing source -> empty backup
		self.assertEqual(open(p0).read(), "")
		open(src, "w").write("v1")
		paths = []
		for i in range(12):
			t[0] += 0.5
			open(src, "w").write("v%d" % i)
			paths.append(core.makeBackup(src, b, now=lambda: t[0], keep=10))
		self.assertEqual(core.makeBackup(src, b, now=lambda: t[0] + 5), paths[-1])  # unchanged -> no new backup
		lst = core.listBackups(b)
		self.assertEqual(len(lst), 10); self.assertEqual(lst[0], paths[-1])
		self.assertRegex(core.backupLabel(lst[0]), r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$")
		open(src, "w").write("zz"); core.restoreBackup(core.readBackup(lst[0]), src)
		with self.assertRaises(OSError):
			core.readBackup(os.path.join(b, "missing.ini"))  # never restores an empty file by mistake
		self.assertEqual([x for x in os.listdir(b) if x.endswith(".tmp")], [])
		self.assertEqual(open(src).read(), "v11")

class T3(unittest.TestCase):
	def test_damaged_stats_are_repaired(self):
		d = tempfile.mkdtemp(); p = os.path.join(d, "s.json")
		bad = {"version": 1, "since": True, "meta": {"k": "x", "ok": ["Ok", None, None]},
			"days": {"2026-10-01": 5, "2026-10-02": {"k": "a", "ok": 3, "neg": -1, "b": True}, "junk": {"x": 1}},
			"sessions": [5, {"start": 1, "counts": {"ok": 2, "z": "q"}}]}
		json.dump(bad, open(p, "w"))
		s = core.StatsStore(p)
		self.assertEqual(s.counts("all"), {"ok": 3})
		self.assertEqual(s.meta("ok"), ["Ok", None, None]); self.assertIsNone(s.meta("k"))
		self.assertEqual(s.sessionCount(), 2)
		s.record("k", "K", None, None); s.save()
		self.assertEqual(core.StatsStore(p).counts("all"), {"ok": 3, "k": 1})
		self.assertEqual(time.strftime("%Y-%m-%d", time.localtime(s.since())), "2026-10-02")
	def test_save_failure_keeps_dirty(self):
		s = core.StatsStore("/proc/nope/s.json"); s.record("k", "K", None, None)
		with self.assertRaises(OSError):
			s.save()
		self.assertTrue(s.dirty)
	def test_calendar_periods_and_past_sessions(self):
		d = tempfile.mkdtemp(); p = os.path.join(d, "s.json")
		# Wednesday 2026-10-14 12:00 local time
		wed = time.mktime((2026, 10, 14, 12, 0, 0, 0, 0, -1))
		t = [wed]
		s = core.StatsStore(p, now=lambda: t[0])
		s.data["days"] = {"2026-10-12": {"k": 1}, "2026-10-11": {"k": 10}, "2026-10-01": {"k": 100}, "2026-09-30": {"k": 1000}}
		self.assertEqual(s.counts("thisweek"), {"k": 1})     # Monday 12th onward
		self.assertEqual(s.counts("week"), {"k": 11})        # last 7 days
		self.assertEqual(s.counts("thismonth"), {"k": 111})  # from the 1st
		self.assertEqual(s.counts("month"), {"k": 1111})
		s.record("k", "K", None, None); s.save()
		t[0] += 3600
		s2 = core.StatsStore(p, now=lambda: t[0])
		self.assertEqual(s2.counts("session"), {})  # a new NVDA session starts empty
		self.assertEqual(s2.counts("all")["k"], 1112)  # earlier sessions still count in the other periods

	def test_background_save(self):
		d = tempfile.mkdtemp(); p = os.path.join(d, "s.json")
		s = core.StatsStore(p); s.record("k", "K", None, None)
		t = s.saveInBackground(); s.record("k", "K", None, None)  # recording continues while writing
		t.join()
		self.assertIsNone(s.saveInBackground() if not s.dirty else None)
		self.assertEqual(core.StatsStore(p).counts("all"), {"k": 1})
		s.save(); self.assertEqual(core.StatsStore(p).counts("all"), {"k": 2})
		errs = []
		bad = core.StatsStore("/proc/nope/s.json"); bad.record("k", "K", None, None)
		bad.saveInBackground(onError=errs.append).join()
		self.assertEqual(len(errs), 1); self.assertTrue(bad.dirty)

	def test_data_edge_cases(self):
		d = tempfile.mkdtemp(); p = os.path.join(d, "s.json")
		# an impossible date is dropped, the rest kept
		json.dump({"days": {"2026-03-01": {"a": 2}, "2026-02-31": {"a": 5}, "2026-13-01": {"a": 7}}}, open(p, "w"))
		s = core.StatsStore(p)
		self.assertEqual(s.counts("all"), {"a": 2}); self.assertFalse(os.path.exists(p + ".corrupt"))
		# days beyond the limit move into the "older" totals: All time stays complete
		s.MAX_DAYS = 1
		s.data["days"]["2026-03-02"] = {"a": 1, "b": 4}; s.dirty = True; s.save()
		s2 = core.StatsStore(p)
		self.assertEqual(list(s2.data["days"]), ["2026-03-02"]); self.assertEqual(s2.counts("all"), {"a": 3, "b": 4})
		# an older snapshot written late never replaces newer data (reset during a background save)
		s2.record("k", "K", None, None)
		snapOld = s2._snapshot(); genOld = s2._gen
		s2.reset(); s2.save()
		s2._write(snapOld, genOld)
		self.assertEqual(core.StatsStore(p).counts("all"), {})
		# a file that exists but cannot be read is left untouched
		import unittest.mock as um
		real = open
		def deny(path, *a, **k):
			if path == p: raise PermissionError("locked")
			return real(path, *a, **k)
		with um.patch("builtins.open", deny), um.patch("time.sleep"):
			s3 = core.StatsStore(p)
		self.assertTrue(s3.readOnly); s3.record("z", "Z", None, None); s3.save()
		self.assertNotIn("z", core.StatsStore(p).counts("all")); self.assertFalse(os.path.exists(p + ".corrupt"))

	def test_daylight_saving(self):
		old = os.environ.get("TZ")
		os.environ["TZ"] = "America/New_York"; time.tzset()
		try:
			d = tempfile.mkdtemp(); p = os.path.join(d, "s.json")
			now = time.mktime((2026, 3, 9, 0, 30, 0, 0, 0, -1))  # just after the 23-hour day of 2026-03-08
			s = core.StatsStore(p, now=lambda: now)
			s.data["days"] = {k: {"a": 1} for k in ("2026-03-03", "2026-03-04", "2026-03-05", "2026-03-06",
				"2026-03-07", "2026-03-08", "2026-03-09")}
			self.assertEqual(s.counts("week"), {"a": 7})
			self.assertEqual(s.counts("thisweek"), {"a": 1})  # Monday the 9th
		finally:
			if old is None: os.environ.pop("TZ", None)
			else: os.environ["TZ"] = old
			time.tzset()

	def test_typing_keys_and_backup_notes(self):
		# also as NVDA normalizes them: parts sorted, so the key may come before "shift"
		for g in ("kb:t", "kb:shift+t", "kb:space", "kb:tab", "kb(laptop):enter", "kb:1", "kb:a+shift",
				"kb:downarrow+shift", "kb:home+shift", "kb:1+shift"):
			self.assertTrue(core.isTypingKey(g), g)
		for g in ("kb:nvda+t", "kb:control+t", "kb:f5", "kb:numpad5", "br(x):dot1", "kb:shift+f1", "kb:f1+shift",
				"kb:a+control+shift", "kb:shift"):
			self.assertFalse(core.isTypingKey(g), g)
		# an unreadable gestures.ini is never backed up as an empty file (undoing it would erase every shortcut)
		dd = tempfile.mkdtemp()
		self.assertEqual(core._read(os.path.join(dd, "missing.ini")), b"")
		with self.assertRaises(OSError):
			core._read(dd)  # a folder: cannot be read
		with self.assertRaises(OSError):
			core.makeBackup(dd, os.path.join(dd, "b"))
		d = tempfile.mkdtemp(); src = os.path.join(d, "gestures.ini"); b = os.path.join(d, "b")
		open(src, "w").write("v1")
		p1 = core.makeBackup(src, b, note="adding X to Y")
		self.assertEqual(core.backupNote(p1), "adding X to Y")
		self.assertEqual(core.makeBackup(src, b, note="removing X"), p1)  # same content: note updated
		self.assertEqual(core.backupNote(p1), "removing X")
		self.assertTrue(core.sameAsCurrent(p1, src)); open(src, "w").write("v2"); self.assertFalse(core.sameAsCurrent(p1, src))
		t = [1_900_000_000.0]
		for i in range(12):
			t[0] += 1; open(src, "w").write("w%d" % i); core.makeBackup(src, b, now=lambda: t[0], note="n%d" % i)
		self.assertEqual(len([x for x in os.listdir(b) if x.endswith(".txt")]), 10)  # notes pruned with backups

	def test_covered_overlap(self):
		self.assertTrue(core.gestureCovered(["kb:nvda+x"], "kb(laptop):nvda+x"))
		self.assertFalse(core.gestureCovered(["kb(desktop):nvda+x"], "kb:nvda+x"))
		self.assertTrue(core.gestureCovered(["kb(desktop):nvda+x", "kb(laptop):nvda+x"], "kb:nvda+x"))
		self.assertEqual(core.overlapping(["kb(desktop):nvda+x", "kb:nvda+y"], "kb:nvda+x"), ["kb(desktop):nvda+x"])
		self.assertEqual(core.overlapping(["kb(desktop):nvda+x"], "kb(laptop):nvda+x"), [])

if __name__ == "__main__":
	unittest.main()
