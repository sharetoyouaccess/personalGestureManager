# Personal Gesture Manager - pure logic (no NVDA/wx imports, unit-testable)
# Copyright (C) 2026 Peem Narkkhwan. GPL v2.

import calendar
import datetime
import json
import glob
import os
import re
import threading
import time

LAYOUTS = ("desktop", "laptop")


def gestureLayouts(gid):
	"""Return (set of layouts, layout-neutral id) for a normalized gesture identifier."""
	g = gid.lower()
	for lay in LAYOUTS:
		prefix = "kb(%s):" % lay
		if g.startswith(prefix):
			return {lay}, "kb:" + g[len(prefix):]
	return set(LAYOUTS), g


def gestureCovered(existing, gid):
	"""True if every layout of gid is already bound by one of the existing gestures."""
	lays, base = gestureLayouts(gid)
	have = set()
	for g in existing:
		l2, b2 = gestureLayouts(g)
		if b2 == base:
			have |= l2
	return lays <= have


def overlapping(existing, gid):
	"""Gestures in existing that act on the same key as gid in at least one shared layout."""
	lays, base = gestureLayouts(gid)
	out = []
	for g in existing:
		l2, b2 = gestureLayouts(g)
		if b2 == base and l2 & lays:
			out.append(g)
	return out


def layoutLabel(layouts):
	layouts = set(layouts)
	if layouts >= set(LAYOUTS):
		return "both"
	return next(iter(layouts))


def definingClass(cls, scriptName):
	"""Class in cls's MRO that actually defines script_<scriptName>."""
	attr = "script_" + scriptName
	for c in getattr(cls, "__mro__", (cls,)):
		if attr in vars(c):
			return c
	return cls


def scriptKey(cls, scriptName):
	c = definingClass(cls, scriptName)
	return "%s.%s:%s" % (c.__module__, c.__name__, scriptName)


class Command(object):
	__slots__ = ("key", "name", "category", "addon", "addonSummary",
		"module", "className", "scriptName", "gestures", "documented")

	def __init__(self, key, name, category, addon, addonSummary, module, className, scriptName, gestures,
			documented=True):
		self.documented = documented
		self.key = key
		self.name = name
		self.category = category
		self.addon = addon  # add-on name, or None for NVDA core
		self.addonSummary = addonSummary
		self.module = module
		self.className = className
		self.scriptName = scriptName
		self.gestures = list(gestures)

	@property
	def level(self):
		"""NVDA script lookup order: global plugins > app module > objects > global commands."""
		m = self.module
		if m.startswith("globalPlugins."):
			return 0
		if m.startswith("appModules."):
			return 1
		if m == "globalCommands":
			return 3
		return 2


def classify(cmds):
	"""(kind, activeCommand) for commands sharing one gesture.
	kind: 'conflict' (same priority, only one can work), 'context' (depends on focused control),
	'override' (a higher-priority command hides the others)."""
	top = min(c.level for c in cmds)
	tops = [c for c in cmds if c.level == top]
	if len(tops) == 1:
		return "override", tops[0]
	return ("context" if top == 2 else "conflict"), None


class Conflict(object):
	__slots__ = ("gesture", "layout", "commands", "kind", "active")

	def __init__(self, gesture, layout, commands):
		self.gesture = gesture
		self.layout = layout
		self.commands = commands
		self.kind, self.active = classify(commands)


def findConflicts(commands, includeCoreOnly=False):
	"""Gestures bound to 2+ different commands in the same keyboard layout."""
	bucket = {}
	for c in commands:
		for gid in c.gestures:
			lays, base = gestureLayouts(gid)
			for lay in lays:
				bucket.setdefault((base, lay), {})[c.key] = c
	merged = {}
	for (base, lay), cmds in bucket.items():
		if len(cmds) < 2:
			continue
		if not includeCoreOnly and all(c.addon is None for c in cmds.values()):
			continue
		k = (base, frozenset(cmds))
		entry = merged.setdefault(k, [set(), cmds])
		entry[0].add(lay)
	out = [Conflict(base, layoutLabel(lays), sorted(cmds.values(), key=lambda c: (c.level, c.name.lower())))
		for (base, _), (lays, cmds) in merged.items()]
	out.sort(key=lambda x: (x.gesture, x.layout))
	return out


def commandsForGesture(commands, gids):
	"""All (command, layout) bound to any of the given normalized identifiers."""
	wanted = {}
	for gid in gids:
		lays, base = gestureLayouts(gid)
		wanted.setdefault(base, set()).update(lays)
	res = []
	for c in commands:
		for gid in c.gestures:
			lays, base = gestureLayouts(gid)
			hit = lays & wanted.get(base, set())
			if hit:
				res.append((c, layoutLabel(hit)))
				break
	res.sort(key=lambda r: r[0].level)
	return res


# Keys that type or move the cursor: alone (or with Shift only) they are needed for normal typing.
_TYPING_KEYS = {"space", "tab", "enter", "numpadenter", "backspace", "delete", "insert", "home", "end",
	"pageup", "pagedown", "leftarrow", "rightarrow", "uparrow", "downarrow", "escape", "applications"}


def isTypingKey(gid):
	"""True for a keyboard gesture that is a plain typing or navigation key (optionally with Shift)."""
	g = gid.lower()
	if not g.startswith("kb"):
		return False
	# Identifiers are normalized: their parts are sorted, so the key is not always the last part.
	parts = [p for p in g.split(":", 1)[1].split("+") if p != "shift"]
	if len(parts) != 1:
		return False
	main = parts[0]
	return len(main) == 1 or main in _TYPING_KEYS


# ---------- gestures.ini backups ----------
def makeBackup(src, bdir, now=time.time, keep=10, note=None):
	"""Copy src (or an empty file if src is missing) into bdir; keep the newest `keep` backups.
	note: the change about to be made, shown with the backup (e.g. "adding NVDA+X to Say time")."""
	if not os.path.isdir(bdir):
		os.makedirs(bdir)
	current = _read(src)
	existing = listBackups(bdir)
	if existing and _read(existing[0]) == current:
		# Nothing changed since the last backup: it is also the state before this change.
		if note:
			_writeNote(existing[0], note)
		return existing[0]
	t = now()
	# UTC in the name: the order stays right when the clock goes back (end of daylight saving time).
	name = "gestures-%s-%06d.ini" % (time.strftime("%Y%m%d-%H%M%S", time.gmtime(t)), int((t % 1) * 1e6))
	dst = os.path.join(bdir, name)
	tmp = dst + ".tmp"
	with open(tmp, "wb") as f:  # complete or absent, never half written
		f.write(current)
		f.flush()
		os.fsync(f.fileno())
	os.replace(tmp, dst)
	if note:
		_writeNote(dst, note)
	for old in listBackups(bdir)[keep:]:
		for path in (old, old + ".txt"):
			try:
				os.remove(path)
			except OSError:
				pass
	return dst


def _writeNote(backup, note):
	try:
		tmp = backup + ".txt.tmp"
		with open(tmp, "w", encoding="utf-8") as f:
			f.write(note)
		os.replace(tmp, backup + ".txt")
	except OSError:
		pass  # a missing note only shortens the label


def backupNote(backup):
	"""The change that followed this backup, or "" if unknown."""
	try:
		with open(backup + ".txt", encoding="utf-8") as f:
			return f.read().strip()
	except (OSError, ValueError):
		return ""


def sameAsCurrent(backup, src):
	return _read(backup) == _read(src)


def _read(path):
	"""The file's content, or empty if it does not exist. Other errors are raised: never treat an unreadable file as empty."""
	try:
		with open(path, "rb") as f:
			return f.read()
	except FileNotFoundError:
		return b""


def listBackups(bdir):
	"""Backup paths, newest first."""
	return sorted(glob.glob(os.path.join(bdir, "gestures-*.ini")), reverse=True)


def backupLabel(path):
	"""Local date and time of a backup (its name holds UTC)."""
	n = os.path.basename(path)[9:24]  # YYYYmmdd-HHMMSS
	try:
		t = calendar.timegm(time.strptime(n, "%Y%m%d-%H%M%S"))
		return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t))
	except ValueError:
		return n


def readBackup(bak):
	"""Content of a backup; raises OSError if it cannot be read (never restores an empty file by mistake)."""
	with open(bak, "rb") as f:
		return f.read()


def restoreBackup(data, dest):
	"""Write backup content (bytes from readBackup) over dest, atomically."""
	tmp = dest + ".tmp"
	with open(tmp, "wb") as f:
		f.write(data)
		f.flush()
		os.fsync(f.fileno())
	os.replace(tmp, dest)


PERIODS = ("session", "today", "thisweek", "week", "thismonth", "month", "all")


class StatsStore(object):
	MAX_SESSIONS = 100
	MAX_DAYS = 400

	def __init__(self, path, now=time.time):
		self.path = path
		self._now = now
		self._lock = threading.Lock()
		self._writeLock = threading.Lock()
		self.dirty = False
		self.lastWriteOk = None  # True/False after the latest write attempt
		self.readOnly = False  # set when the file exists but cannot be read: never overwrite it then
		self._gen = 0       # generation of the newest snapshot taken
		self._written = 0   # generation of the newest snapshot written
		self.data = self._empty()
		self.load()
		self.session = {"start": int(now()), "counts": {}}
		self.data["sessions"].append(self.session)
		del self.data["sessions"][:-self.MAX_SESSIONS]

	def _empty(self):
		# "older": totals of days dropped from "days" (kept MAX_DAYS), so "All time" stays complete.
		return {"version": 1, "since": int(self._now()), "meta": {}, "days": {}, "sessions": [], "older": {}}

	def _day(self, t=None):
		return time.strftime("%Y-%m-%d", time.localtime(self._now() if t is None else t))

	def load(self):
		if not os.path.isfile(self.path):
			return
		text = None
		for attempt in range(5):  # antivirus, backup or sync tools may hold the file for a moment
			try:
				with open(self.path, "rb") as f:
					text = f.read()
				break
			except OSError:
				time.sleep(0.1)
		if text is None:
			# Unreadable, not damaged: keep the file as it is and do not save over it this session.
			self.readOnly = True
			return
		try:
			d = json.loads(text.decode("utf-8"))
			if not isinstance(d, dict):
				raise ValueError("bad structure")
			self.data = self._sanitize(d)
		except Exception:
			try:
				os.replace(self.path, self.path + ".corrupt")
			except OSError:
				pass
			self.data = self._empty()

	_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")

	@staticmethod
	def _counts(c):
		if not isinstance(c, dict):
			return {}
		return {k: v for k, v in c.items()
			if isinstance(k, str) and isinstance(v, int) and not isinstance(v, bool) and v > 0}

	def _sanitize(self, d):
		"""Keep every valid entry, drop damaged ones (e.g. after a power failure)."""
		out = self._empty()
		days = d.get("days")
		if isinstance(days, dict):
			for k, v in days.items():
				if isinstance(k, str) and self._DAY.match(k) and self._validDay(k):
					c = self._counts(v)
					if c:
						out["days"][k] = c
		meta = d.get("meta")
		if isinstance(meta, dict):
			for k, v in meta.items():
				if isinstance(k, str) and isinstance(v, list) and len(v) == 3 and isinstance(v[0], str) \
						and all(x is None or isinstance(x, str) for x in v[1:]):
					out["meta"][k] = v
		sessions = d.get("sessions")
		if isinstance(sessions, list):
			for s in sessions:
				if isinstance(s, dict) and isinstance(s.get("start"), int):
					out["sessions"].append({"start": s["start"], "counts": self._counts(s.get("counts"))})
		out["older"] = self._counts(d.get("older"))
		since = d.get("since")
		if isinstance(since, int) and not isinstance(since, bool):
			out["since"] = since
		elif out["days"]:
			out["since"] = int(time.mktime(time.strptime(min(out["days"]), "%Y-%m-%d")))
		return out

	@staticmethod
	def _validDay(k):
		try:
			datetime.date.fromisoformat(k)
			return True
		except ValueError:
			return False

	def since(self):
		return self.data.get("since", int(self._now()))

	def record(self, key, name, addon, category):
		with self._lock:
			day = self.data["days"].setdefault(self._day(), {})
			day[key] = day.get(key, 0) + 1
			sc = self.session["counts"]
			sc[key] = sc.get(key, 0) + 1
			self.data["meta"][key] = [name, addon, category]
			self.dirty = True

	def counts(self, period="all"):
		with self._lock:
			if period == "session":
				return dict(self.session["counts"])
			now = self._now()
			if period == "all":
				days = list(self.data["days"].values()) + [self.data.get("older", {})]
			else:
				lt = time.localtime(now)
				if period == "thisweek":  # calendar week, Monday first
					n = lt.tm_wday + 1
				elif period == "thismonth":
					n = lt.tm_mday
				else:
					n = {"today": 1, "week": 7, "month": 30}[period]
				# Calendar days, not 24-hour steps: right across daylight saving time changes.
				today = datetime.date.fromtimestamp(now)
				keys = {(today - datetime.timedelta(days=i)).isoformat() for i in range(n)}
				days = [v for k, v in self.data["days"].items() if k in keys]
			out = {}
			for d in days:
				for k, v in d.items():
					out[k] = out.get(k, 0) + v
			return out

	def meta(self, key):
		return self.data["meta"].get(key)

	def sessionCount(self):
		return len(self.data["sessions"])

	def reset(self):
		with self._lock:
			self.data = self._empty()
			self.session = {"start": int(self._now()), "counts": {}}
			self.data["sessions"].append(self.session)
			self.dirty = True

	def _snapshot(self):
		"""Copy of the data (taken under the lock) that can be written without blocking recording."""
		days = self.data["days"]
		older = self.data.setdefault("older", {})
		for k in sorted(days)[:-self.MAX_DAYS]:
			for key, v in days.pop(k).items():
				older[key] = older.get(key, 0) + v
		self._gen += 1
		snap = dict(self.data)
		snap["older"] = dict(older)
		snap["days"] = {k: dict(v) for k, v in days.items()}
		snap["meta"] = dict(self.data["meta"])
		snap["sessions"] = [{"start": x["start"], "counts": dict(x["counts"])} for x in self.data["sessions"]]
		return snap

	def _write(self, snap, gen):
		# One writer at a time, replaced atomically; never wait forever (e.g. a stuck network drive).
		if not self._writeLock.acquire(timeout=10):
			raise OSError("statistics file is busy")
		try:
			self._writeUnlocked(snap, gen)
		finally:
			self._writeLock.release()

	def _writeUnlocked(self, snap, gen):
		if gen < self._written:
			return  # a newer snapshot (e.g. after a reset) is already on disk: never go back to older data
		d = os.path.dirname(self.path)
		if d and not os.path.isdir(d):
			os.makedirs(d)
		tmp = self.path + ".tmp"
		with open(tmp, "w", encoding="utf-8") as f:
			json.dump(snap, f, ensure_ascii=False)
			f.flush()
			os.fsync(f.fileno())  # complete on disk even after a power failure
		os.replace(tmp, self.path)
		self._written = gen
		self.lastWriteOk = True

	def save(self, force=False):
		"""Write now, in the calling thread. Raises OSError on failure (data stays marked unsaved)."""
		with self._lock:
			if self.readOnly or not (self.dirty or force):
				return
			snap = self._snapshot()
			gen = self._gen
			self.dirty = False
		try:
			self._write(snap, gen)
		except Exception:
			self.dirty = True
			self.lastWriteOk = False
			raise

	def saveInBackground(self, onError=None):
		"""Write without blocking NVDA's main thread (used by the periodic save)."""
		with self._lock:
			if self.readOnly or not self.dirty:
				return None
			snap = self._snapshot()
			gen = self._gen
			self.dirty = False

		def run():
			try:
				self._write(snap, gen)
			except Exception as e:
				self.dirty = True
				self.lastWriteOk = False
				if onError:
					onError(e)
		t = threading.Thread(target=run, name="PersonalGestureManagerSave", daemon=True)
		t.start()
		return t
