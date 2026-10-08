"""A faithful model of how NVDA stores, lists and runs gesture bindings, for end-to-end tests.

GlobalGestureMap, the "all gesture mappings" retriever (Input gestures dialog) and the script lookup
(findScript) follow NVDA's own source (inputCore.py, scriptHandler.py, baseObject.py, release 2026.x),
reduced to what the add-on uses. gestures.ini is kept in memory through export()/update(), as NVDA
writes and reads it, so a save and a reload go through the same conversion as on disk."""
import os, sys, types, tempfile


def normalizeGestureIdentifier(identifier):
	identifier = identifier.lower()
	prefix, main = identifier.split(":", 1)
	main = main.split("+")
	main.sort()
	return "%s:%s" % (prefix, "+".join(main))


class GlobalGestureMap:
	def __init__(self):
		self._map = {}
		self.fileName = None

	def clear(self):
		self._map.clear()

	def add(self, gesture, module, className, script, replace=False):
		gesture = normalizeGestureIdentifier(gesture)
		scripts = self._map.setdefault(gesture, [])
		if replace:
			del scripts[:]
		scripts.append((module, className, script))

	def update(self, entries):
		for locationName, location in entries.items():
			module, className = locationName.rsplit(".", 1)
			for script, gestures in location.items():
				if script == "None":
					script = None
				if isinstance(gestures, str):
					gestures = [gestures]
				for gesture in gestures:
					self.add(gesture, module, className, script)

	def getScriptsForGesture(self, gesture):
		for moduleName, className, scriptName in self._map.get(gesture, ()):
			module = sys.modules.get(moduleName)
			cls = getattr(module, className, None) if module else None
			if cls is not None:
				yield cls, scriptName

	def getScriptsForAllGestures(self):
		for gesture in list(self._map):
			for cls, scriptName in self.getScriptsForGesture(gesture):
				yield cls, gesture, scriptName

	def remove(self, gesture, module, className, script):
		gesture = normalizeGestureIdentifier(gesture)
		try:
			scripts = self._map[gesture]
		except KeyError:
			raise ValueError("Mapping not found")
		scripts.remove((module, className, script))

	def export(self):
		out = {}
		for gesture, scripts in self._map.items():
			for module, className, script in scripts:
				sect = out.setdefault("%s.%s" % (module, className), {})
				key = "None" if script is None else script
				sect.setdefault(key, []).append(gesture)
		return out

	def save(self):
		DISK["gestures.ini"] = {k: {s: list(g) for s, g in v.items()} for k, v in self.export().items()}


DISK = {}


class Info:
	def __init__(self, cls, scriptName):
		self.cls, self.scriptName, self.gestures = cls, scriptName, []


class Retriever:
	"""inputCore._AllGestureMappingsRetriever"""
	def __init__(self, obj, ancestors):
		self.results, self.scriptInfo, self.handled = {}, {}, set()
		self.addGlobalMap(manager.userGestureMap)
		self.addGlobalMap(manager.localeGestureMap)
		for p in globalPluginHandler.runningPlugins:
			self.addObj(p)
		if getattr(obj, "appModule", None):
			self.addObj(obj.appModule)
		self.addObj(obj)
		for anc in reversed(ancestors or []):
			self.addObj(anc, isAncestor=True)
		self.addObj(globalCommands.commands)

	def addResult(self, info):
		self.scriptInfo[info.cls, info.scriptName] = info
		self.results.setdefault(info.category, {})[info.displayName] = info

	def make(self, cls, scriptName, script):
		info = Info(cls, scriptName)
		info.category = getattr(script, "category", None) or getattr(cls, "scriptCategory", "Miscellaneous")
		info.displayName = script.__doc__
		return info if info.displayName else None

	def addGlobalMap(self, gmap):
		for cls, gesture, scriptName in gmap.getScriptsForAllGestures():
			key = (cls, gesture)
			if key in self.handled:
				continue
			self.handled.add(key)
			if scriptName is None:
				continue
			info = self.scriptInfo.get((cls, scriptName))
			if info is None:
				script = getattr(cls, "script_%s" % scriptName, None)
				if script is None:
					self.handled.remove(key)
					continue
				info = self.make(cls, scriptName, script)
				if not info:
					continue
				self.addResult(info)
			info.gestures.append(gesture)

	def addObj(self, obj, isAncestor=False):
		scripts = {}
		for cls in obj.__class__.__mro__:
			for name, script in cls.__dict__.items():
				if not name.startswith("script_"):
					continue
				if isAncestor and not getattr(script, "canPropagate", False):
					continue
				name = name[7:]
				info = self.scriptInfo.get((cls, name))
				if info is None:
					info = self.make(cls, name, script)
					if not info:
						continue
					self.addResult(info)
				scripts[script] = info
		for gesture, script in obj._gestureMap.items():
			info = scripts.get(script)
			if info is None:
				continue
			key = (info.cls, gesture)
			if key in self.handled:
				continue
			self.handled.add(key)
			info.gestures.append(gesture)


class ScriptableObject:
	"""baseObject.ScriptableObject: class gestures (__gestures) bound per instance in _gestureMap."""
	def __init__(self):
		self._gestureMap = {}
		for cls in reversed(type(self).__mro__):
			for g, scr in (vars(cls).get("_%s__gestures" % cls.__name__) or {}).items():
				self._gestureMap[normalizeGestureIdentifier(g)] = getattr(type(self), "script_" + scr)

	def getScript(self, ids):
		for i in ids:
			f = self._gestureMap.get(i)
			if f:
				return f.__get__(self, type(self))
		return None


def kbIds(key, layout):
	"""InputGesture.normalizedIdentifiers of a keyboard gesture: layout-specific first."""
	return [normalizeGestureIdentifier("kb(%s):%s" % (layout, key)), normalizeGestureIdentifier("kb:" + key)]


def findScript(ids):
	"""scriptHandler._findScript, for the global plugins, the focus and global commands."""
	globalMapScripts = []
	for gmap in (manager.userGestureMap, manager.localeGestureMap):
		for i in ids:
			globalMapScripts.extend(gmap.getScriptsForGesture(i))
	objs = list(globalPluginHandler.runningPlugins) + [FOCUS, globalCommands.commands]
	for obj in objs:
		func = None
		for cls, scriptName in globalMapScripts:
			if isinstance(obj, cls):
				if scriptName is None:
					break
				func = getattr(obj, "script_%s" % scriptName, None)
				if func:
					break
		else:
			func = obj.getScript(ids)
		if func:
			return func.__func__.__name__[7:]
	return None


def loadUserGestureMap():
	manager.userGestureMap.clear()
	manager.userGestureMap.update(DISK.get("gestures.ini", {}))


TMP = tempfile.mkdtemp()
ADDONS = os.path.join(TMP, "addons")


def mod(name, **kw):
	m = types.ModuleType(name)
	m.__dict__.update(kw)
	sys.modules[name] = m
	return m


def _disp(gid):
	src = gid.split(":", 1)[0]
	return ({"kb": "keyboard, all layouts", "kb(desktop)": "keyboard, desktop", "kb(laptop)": "keyboard, laptop"}.get(src, src),
		gid.split(":", 1)[1].upper())


manager = types.SimpleNamespace(userGestureMap=GlobalGestureMap(), localeGestureMap=GlobalGestureMap(), _captureFunc=None,
	getAllGestureMappings=lambda obj=None, ancestors=None: Retriever(obj, ancestors).results,
	loadUserGestureMap=loadUserGestureMap)
inputCore = mod("inputCore", manager=manager, normalizeGestureIdentifier=normalizeGestureIdentifier,
	getDisplayTextForGestureIdentifier=_disp)
globalPluginHandler = mod("globalPluginHandler", runningPlugins=[], GlobalPlugin=ScriptableObject)


class Addon:
	def __init__(self, name, summary):
		self.name, self.path, self.manifest = name, os.path.join(ADDONS, name), {"summary": summary}


RUNNING = [Addon("addA", "Add A"), Addon("addB", "Add B")]
mod("addonHandler", initTranslation=lambda: None, getRunningAddons=lambda: RUNNING, getAvailableAddons=lambda: [])
mod("config", isInstalledCopy=lambda: True, conf={"keyboard": {"keyboardLayout": "desktop"}})
mod("globalVars", appArgs=types.SimpleNamespace(secure=True, configPath=TMP), appDir=TMP)
mod("scriptHandler", executeScript=None, script=lambda **kw: (lambda f: f), getLastScriptRepeatCount=lambda: 0)
mod("buildVersion", version="2026.3")
LOG = []
mod("logHandler", log=types.SimpleNamespace(debugWarning=lambda *a, **k: None,
	error=lambda *a, **k: LOG.append(a), warning=lambda *a, **k: None))
SPOKEN = []
mod("ui", message=SPOKEN.append)


def plugin(addonName, className="GlobalPlugin", scripts=(), gestures=None, category=None):
	"""A running global plugin of an add-on: scripts = (name, description)."""
	modName = "globalPlugins." + addonName
	m = sys.modules.get(modName) or mod(modName, __file__=os.path.join(ADDONS, addonName, "globalPlugins", addonName + ".py"))
	ns = {"scriptCategory": category or addonName}
	for name, doc in scripts:
		def f(self, gesture):
			pass
		f.__name__ = "script_" + name
		f.__doc__ = doc
		ns["script_" + name] = f
	cls = type(className, (ScriptableObject,), ns)
	cls.__module__ = modName
	setattr(cls, "_%s__gestures" % className, dict(gestures or {}))
	setattr(m, className, cls)
	return cls


class GlobalCommands(ScriptableObject):
	scriptCategory = "System"
	__gestures = {"kb:nvda+t": "title", "kb(desktop):nvda+downArrow": "sayAll", "kb(laptop):nvda+a": "sayAll"}

	def script_title(self, g):
		"""Reports the title"""

	def script_sayAll(self, g):
		"""Say all"""


GlobalCommands.__module__ = "globalCommands"
globalCommands = mod("globalCommands", GlobalCommands=GlobalCommands)


class Focus(ScriptableObject):
	appModule = None
	treeInterceptor = None


FOCUS = None


def start(plugins):
	"""(Re)start NVDA with these plugin classes and an empty gestures.ini."""
	global FOCUS
	DISK.clear()
	manager.userGestureMap.clear()
	globalCommands.commands = GlobalCommands()
	globalPluginHandler.runningPlugins[:] = [p() for p in plugins]
	FOCUS = Focus()
	mod("api", getFocusObject=lambda: FOCUS, getFocusAncestors=lambda: [], getForegroundObject=lambda: None)
