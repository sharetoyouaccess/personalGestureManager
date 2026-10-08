# Personal Gesture Manager - NVDA global plugin
# Copyright (C) 2026 Peem Narkkhwan. GPL v2.

import os
import sys

import addonHandler
import config
import globalPluginHandler
import globalVars
import inputCore
import scriptHandler
import ui
import wx
from logHandler import log
from scriptHandler import script

from . import core

addonHandler.initTranslation()

ADDON_CATEGORY = _("Personal Gesture Manager")
_plugin = None
_origExecuteScript = None
_addonCache = {}
_gestureTextCache = {}
_keyCache = {}
SAVE_INTERVAL_MS = 30000


def addonForModule(modName):
	"""(addonName, summary) owning a module, or (None, None) for NVDA core."""
	if modName in _addonCache:
		return _addonCache[modName]
	res = (None, None)
	f = getattr(sys.modules.get(modName), "__file__", None)
	if f:
		f = os.path.normcase(os.path.abspath(f))
		try:
			addons = list(addonHandler.getRunningAddons())
		except Exception:
			addons = []
		for a in addons:
			p = os.path.normcase(os.path.abspath(a.path)) + os.sep
			if f.startswith(p):
				res = (a.name, a.manifest.get("summary") or a.name)
				break
		else:
			sp = os.path.normcase(os.path.join(globalVars.appArgs.configPath, "scratchpad")) + os.sep
			if f.startswith(sp):
				res = ("scratchpad", _("Scratchpad"))
	_addonCache[modName] = res
	return res


def gestureText(gid):
	"""Short spoken name: "NVDA+X", "NVDA+X (laptop)", or "dot1 (Braille)" for other devices.
	Cached: asking NVDA for display text is the most repeated cost when lists are built."""
	try:
		return _gestureTextCache[gid]
	except KeyError:
		pass
	try:
		src, txt = inputCore.getDisplayTextForGestureIdentifier(gid)
	except Exception:
		return gid
	if gid.lower().startswith("kb"):
		lays, _base = core.gestureLayouts(gid)
		text = txt if len(lays) > 1 else "%s (%s)" % (txt, _(next(iter(lays))))
	else:
		text = "%s (%s)" % (txt, src)
	_gestureTextCache[gid] = text
	return text


def gestureParts(gid):
	"""(display text, layout or None, source or None) for a gesture; cached (asking NVDA is slow).
	Keyboard gestures get a layout only when they apply to one layout; other devices get their source."""
	try:
		return _gestureTextCache[("parts", gid)]
	except KeyError:
		pass
	try:
		src, txt = inputCore.getDisplayTextForGestureIdentifier(gid)
	except Exception:
		return (gid, None, None)
	if gid.lower().startswith("kb"):
		lays, _base = core.gestureLayouts(gid)
		parts = (txt, None if len(lays) > 1 else next(iter(lays)), None)
	else:
		parts = (txt, None, src)
	_gestureTextCache[("parts", gid)] = parts
	return parts


def envInfo():
	import buildVersion
	# A key, not text: the dialog translates it in its own (switchable) language.
	try:
		mode = "installed" if config.isInstalledCopy() else "portable"
	except Exception:
		mode = "unknown"
	if getattr(config, "isAppX", False):
		mode = "store"
	app = ""
	try:
		import gui
		focus = getattr(gui.mainFrame, "prevFocus", None)
		app = focus.appModule.appName if focus is not None and focus.appModule else ""
	except Exception:
		pass
	return {"version": buildVersion.version, "mode": mode, "app": app or "?",
		"configPath": globalVars.appArgs.configPath,
		"layout": config.conf["keyboard"]["keyboardLayout"]}


WINDOWS_EDITIONS = {"Core": "Home", "CoreSingleLanguage": "Home Single Language", "CoreCountrySpecific": "Home",
	"Professional": "Pro", "ProfessionalWorkstation": "Pro for Workstations", "ProfessionalEducation": "Pro Education",
	"Enterprise": "Enterprise", "EnterpriseS": "Enterprise LTSC", "Education": "Education",
	"IoTEnterprise": "IoT Enterprise", "IoTEnterpriseS": "IoT Enterprise LTSC", "ServerStandard": "Server Standard",
	"ServerDatacenter": "Server Datacenter"}


def systemInfo():
	"""Facts read live from this computer; each value is "?" when it cannot be read."""
	info = {"nvdaDir": "?", "windows": "?", "build": "?", "computer": "?", "inputLanguage": "?", "addons": None,
		"running": None}
	try:
		info["nvdaDir"] = globalVars.appDir
	except Exception:
		pass
	try:
		import winVersion
		ver = winVersion.getWinVer()
		name = getattr(ver, "releaseName", None) or "Windows"
		info["build"] = str(ver.build)
		edition = ""
		try:
			import winreg
			with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as k:
				ed = winreg.QueryValueEx(k, "EditionID")[0]
			edition = WINDOWS_EDITIONS.get(ed, ed)
		except Exception:
			pass
		# Windows version from the release name (the registry says "Windows 10" on 11); edition from the registry.
		parts = name.split(" ")
		if edition and len(parts) >= 2 and parts[0] == "Windows":
			name = " ".join(parts[:2] + [edition] + parts[2:])
		info["windows"] = name
	except Exception:
		log.debugWarning("PersonalGestureManager: Windows version unknown", exc_info=True)
	try:
		import platform
		info["computer"] = os.environ.get("COMPUTERNAME") or platform.node() or "?"
	except Exception:
		pass
	try:
		import ctypes
		import languageHandler
		try:
			import keyboardHandler
			hkl = keyboardHandler.getInputHkl()
		except Exception:
			hkl = ctypes.windll.user32.GetKeyboardLayout(0)
		lcid = (hkl or 0) & 0xFFFF
		loc = languageHandler.windowsLCIDToLocaleName(lcid)
		info["inputLanguage"] = languageHandler.getLanguageDescription(loc) or loc or "?"
	except Exception:
		pass
	try:
		info["addons"] = sum(1 for a in addonHandler.getAvailableAddons() if not getattr(a, "isPendingInstall", False))
		info["running"] = sum(1 for a in addonHandler.getRunningAddons())
	except Exception:
		pass
	return info


def previousFocus():
	"""(object, ancestors) that had focus before NVDA's own window was shown, or None.
	Read it right after gui.mainFrame.prePopup(): postPopup() clears it."""
	import gui
	obj = getattr(gui.mainFrame, "prevFocus", None)
	return (obj, getattr(gui.mainFrame, "prevFocusAncestors", None)) if obj is not None else None


def collectCommands(focus=None):
	"""All documented commands with their current (effective) gestures, for the application in `focus`
	((object, ancestors) from previousFocus(); the current focus if None)."""
	import api
	obj, anc = focus if focus else (api.getFocusObject(), api.getFocusAncestors())
	try:
		mappings = inputCore.manager.getAllGestureMappings(obj=obj, ancestors=anc)
	except Exception:
		# The remembered focus may have died (e.g. its window closed); use the current focus instead.
		log.debugWarning("PersonalGestureManager: mappings for previous focus failed", exc_info=True)
		obj, anc = api.getFocusObject(), api.getFocusAncestors()
		mappings = inputCore.manager.getAllGestureMappings(obj=obj, ancestors=anc)
	out = []
	for category, scripts in mappings.items():
		for displayName, info in scripts.items():
			cls = info.cls
			name, summary = addonForModule(cls.__module__)
			out.append(core.Command(
				core.scriptKey(cls, info.scriptName), displayName, category, name, summary,
				cls.__module__, cls.__name__, info.scriptName, info.gestures))
	known = {c.key for c in out}
	objs = list(globalPluginHandler.runningPlugins)
	objs += [getattr(obj, "appModule", None), getattr(obj, "treeInterceptor", None), obj]
	objs += list(anc or [])
	try:
		import globalCommands
		objs.append(globalCommands.commands)
	except Exception:
		pass
	out.extend(_undocumentedCommands([o for o in objs if o is not None], known))
	return out


def _isUnbound(gid, cls, scriptName=None):
	"""True if the user/locale gesture map unbinds gid for cls (or a base class), or gives it to another script
	of that class: NVDA checks those maps first, so the class's own binding never runs."""
	names = {(c.__module__, c.__name__) for c in cls.__mro__}
	for gm in (inputCore.manager.userGestureMap, getattr(inputCore.manager, "localeGestureMap", None)):
		if gm is None:
			continue
		try:
			for mod, clsName, scr in getattr(gm, "_map", {}).get(gid, ()):
				if (mod, clsName) in names and scr != scriptName:
					return True
		except Exception:
			pass
	return False


def _undocumentedCommands(objs, known):
	"""Commands bound to gestures but without a description (hidden in NVDA's Input gestures)."""
	found = {}
	for o in objs:
		gmap = getattr(o, "_gestureMap", None)
		if not isinstance(gmap, dict):
			continue
		for gid, func in list(gmap.items()):
			fname = getattr(func, "__name__", "")
			if not fname.startswith("script_") or getattr(func, "__doc__", None):
				continue
			sname = fname[7:]
			key = core.scriptKey(type(o), sname)
			if key in known:
				continue
			cls = core.definingClass(type(o), sname)
			c = found.get(key)
			if c is None:
				addon, summary = addonForModule(cls.__module__)
				c = found[key] = core.Command(key, sname, _("Commands without a description"), addon, summary,
					cls.__module__, cls.__name__, sname, [], documented=False)
			if gid not in c.gestures and not _isUnbound(gid, type(o), sname):
				c.gestures.append(gid)
	# Shortcuts the user added to undocumented commands live only in gestures.ini.
	for gid, entries in list(getattr(inputCore.manager.userGestureMap, "_map", {}).items()):
		seen = set()
		for mod, clsName, scr in entries:
			if (mod, clsName) in seen:
				continue  # only the first binding of a class counts, as in NVDA
			seen.add((mod, clsName))
			c = found.get("%s.%s:%s" % (mod, clsName, scr)) if scr else None
			if c and gid not in c.gestures:
				c.gestures.append(gid)
	# Keep commands even when all their shortcuts were removed, so they can get one again.
	return list(found.values())


def gesturesPath():
	return os.path.join(globalVars.appArgs.configPath, "gestures.ini")


DATA_DIR = "personalGestureManager"


def dataDir():
	return os.path.join(globalVars.appArgs.configPath, DATA_DIR)


def backupDir():
	return os.path.join(dataDir(), "backups")


# ---------- guides (documentation of NVDA and add-ons) ----------

def _docLanguages(docRoot, fileName):
	"""{language code: path} for every doc/<lang>/<fileName> that exists."""
	out = {}
	try:
		for lang in sorted(os.listdir(docRoot)):
			p = os.path.join(docRoot, lang, fileName)
			if os.path.isfile(p):
				out[lang] = p
	except OSError:
		pass
	return out


def listAddonGuides():
	"""Every installed add-on (running or not) with what is needed for its guide."""
	out = []
	try:
		addons = list(addonHandler.getAvailableAddons())
	except Exception:
		log.error("PersonalGestureManager: could not list add-ons", exc_info=True)
		addons = []
	for a in addons:
		try:
			if getattr(a, "isPendingRemove", False):
				continue
			m = a.manifest
			docFile = m.get("docFileName") or ""
			out.append({
				"name": a.name,
				"summary": m.get("summary") or a.name,
				"description": " ".join((m.get("description") or "").split()),
				"author": m.get("author") or "",
				"version": m.get("version") or "",
				"running": bool(getattr(a, "isRunning", False)),
				"disabled": bool(getattr(a, "isDisabled", False)),
				"docs": _docLanguages(os.path.join(a.path, "doc"), docFile) if docFile else {},
			})
		except Exception:
			log.debugWarning("PersonalGestureManager: skipped add-on %r" % (getattr(a, "path", a),), exc_info=True)
	out.sort(key=lambda x: x["summary"].lower())
	return out


def nvdaDocRoot():
	try:
		import documentationUtils
		documentationUtils.getDocFilePath("userGuide.html")  # initialises rootPath (also when run from source)
		root = getattr(documentationUtils.getDocFilePath, "rootPath", None)
		if root:
			return root
	except Exception:
		pass
	return os.path.join(globalVars.appDir, "documentation")


def nvdaGuides():
	"""NVDA's own User Guide and Commands Quick Reference, per available language."""
	root = nvdaDocRoot()
	return [("userGuide", _docLanguages(root, "userGuide.html")),
		("keyCommands", _docLanguages(root, "keyCommands.html"))]


def currentLanguage():
	try:
		import languageHandler
		return languageHandler.getLanguage()
	except Exception:
		return "en"


def languageName(code):
	try:
		import languageHandler
		return languageHandler.getLanguageDescription(code) or code
	except Exception:
		return code


def openFile(path):
	os.startfile(path)


def showHtml(html, title):
	"""Show text in NVDA's browseable message window (read with arrows, H for headings)."""
	try:
		ui.browseableMessage(html, title, isHtml=True, closeButton=True)  # Close button: NVDA 2025.1+
	except TypeError:
		ui.browseableMessage(html, title, isHtml=True)


def reloadUserGestures():
	m = inputCore.manager
	if hasattr(m, "loadUserGestureMap"):
		m.loadUserGestureMap()
	else:
		m.userGestureMap.clear()
		if os.path.isfile(gesturesPath()):
			m.userGestureMap.load(gesturesPath())


def _layoutVariants(gid):
	"""kb(desktop):X and kb(laptop):X for kb:X; nothing for other gestures."""
	if not gid.lower().startswith("kb:"):
		return []
	key = gid.split(":", 1)[1]
	return ["kb(desktop):" + key, "kb(laptop):" + key]


def addGesture(cmd, gid, save=True):
	gm = inputCore.manager.userGestureMap
	try:
		gm.remove(gid, cmd.module, cmd.className, None)  # undo a previous unbinding (as NVDA's own dialog does)
	except ValueError:
		pass
	# A layout-specific unbinding of this command's default would block the new kb: shortcut: drop it.
	# Another command's unbinding is kept (removing it would bring that default back).
	variants = _layoutVariants(gid)
	if variants:
		own = defaultGestures(cmd)
		for g in variants:
			if g in own or gid in own:
				try:
					gm.remove(g, cmd.module, cmd.className, None)
				except ValueError:
					pass
	gm.add(gid, cmd.module, cmd.className, cmd.scriptName)
	if save:
		gm.save()


def isUserGesture(cmd, gid):
	"""True if gid is bound to cmd in gestures.ini (not only by default)."""
	m = getattr(inputCore.manager.userGestureMap, "_map", {})
	return (cmd.module, cmd.className, cmd.scriptName) in m.get(gid, ())


def blockedLayouts(cmd, gid):
	"""Keyboard layouts on which gid cannot run cmd, because NVDA finds an unbinding of a layout-specific
	variant of the key for the same class first (left by removing another command's default)."""
	m = getattr(inputCore.manager.userGestureMap, "_map", {})
	out = []
	for g in _layoutVariants(gid):
		if (cmd.module, cmd.className, None) in m.get(g, ()) \
				and (cmd.module, cmd.className, cmd.scriptName) not in m.get(g, ()):
			out.append(g[3:g.index(")")])
	return out


def removeGesture(cmd, gid, spare=None):
	"""spare: a script of the same class that keeps its binding of gid (the one the key is moved to)."""
	gm = inputCore.manager.userGestureMap
	try:
		gm.remove(gid, cmd.module, cmd.className, cmd.scriptName)
	except ValueError:
		_unbind(gm, cmd, gid)  # a default gesture
	else:
		# NVDA gives a key to one script per class: removing it here must not let another script take it.
		for mod, clsName, scr in list(getattr(gm, "_map", {}).get(gid, ())):
			if (mod, clsName) == (cmd.module, cmd.className) and scr not in (None, cmd.scriptName, spare):
				gm.remove(gid, mod, clsName, scr)
	gm.save()


def takenInClass(cmd, gid):
	"""True if gestures.ini gives gid to another command of cmd's class: NVDA then never runs cmd with it."""
	gid = inputCore.normalizeGestureIdentifier(gid)
	for mod, clsName, scr in getattr(inputCore.manager.userGestureMap, "_map", {}).get(gid, ()):
		if (mod, clsName) == (cmd.module, cmd.className):
			return scr is not None and scr != cmd.scriptName
	return False


def snapshotUserGestures():
	"""A copy of the user's bindings, to undo a change that did not work as a whole."""
	m = getattr(inputCore.manager.userGestureMap, "_map", {})
	return {g: list(v) for g, v in m.items()}


def restoreUserGestures(snap):
	gm = inputCore.manager.userGestureMap
	gm._map.clear()
	for g, v in snap.items():
		gm._map[g] = list(v)
	gm.save()


def unbindGesture(cmd, gid):
	"""Explicitly unbind gid from cmd (needed when it is also a default binding)."""
	gm = inputCore.manager.userGestureMap
	_unbind(gm, cmd, gid)
	gm.save()


def _unbind(gm, cmd, gid):
	"""Unbind gid for cmd's class, unless another script of that class already holds it in gestures.ini
	(an extra unbinding would make the result depend on file order)."""
	gid = inputCore.normalizeGestureIdentifier(gid)
	for mod, clsName, scr in getattr(gm, "_map", {}).get(gid, ()):
		if (mod, clsName) == (cmd.module, cmd.className) and (scr is None or scr != cmd.scriptName):
			return
	gm.add(gid, cmd.module, cmd.className, None)


def defaultGestures(cmd):
	"""Normalized gestures bound to cmd by default: in its class (gestures dict and @script), in running
	instances (gestures bound at run time), in NVDA's locale gesture map and in the braille display's map."""
	out = set()
	cls = getattr(sys.modules.get(cmd.module), cmd.className, None)
	if cls is not None:
		out.update(g for g, scr in _defaultScripts(cls).items() if scr == cmd.scriptName)
	objs = list(globalPluginHandler.runningPlugins)
	try:
		import globalCommands
		objs.append(globalCommands.commands)
	except Exception:
		pass
	for o in objs:
		t = type(o)
		if (t.__module__, t.__name__) != (cmd.module, cmd.className) and not (cls and isinstance(o, cls)):
			continue
		gmap = getattr(o, "_gestureMap", None)
		if isinstance(gmap, dict):
			for g, func in list(gmap.items()):
				if getattr(func, "__name__", "") == "script_" + cmd.scriptName:
					out.add(g)
	maps = [getattr(inputCore.manager, "localeGestureMap", None)]
	try:
		import braille
		maps.append(getattr(braille.handler.display, "gestureMap", None))
	except Exception:
		pass
	entry = (cmd.module, cmd.className, cmd.scriptName)
	for gm in maps:
		try:
			for g, entries in getattr(gm, "_map", {}).items():
				if entry in entries:
					out.add(g)
		except Exception:
			pass
	return out


def _defaultScripts(cls):
	"""normalized gesture -> script name bound by the classes themselves (gestures dict and @script)."""
	out = {}
	for c in reversed(getattr(cls, "__mro__", ())):
		g = vars(c).get("_%s__gestures" % c.__name__)
		if isinstance(g, dict):
			for gid, scr in g.items():
				try:
					out[inputCore.normalizeGestureIdentifier(gid)] = scr
				except Exception:
					pass
	return out


def resetCommand(cmd, save=True):
	"""Remove every user change for cmd (added shortcuts and unbound defaults), so it has its default
	shortcuts again. True if something changed."""
	gm = inputCore.manager.userGestureMap
	defaults = defaultGestures(cmd)
	cls = getattr(sys.modules.get(cmd.module), cmd.className, None)
	ownDefaults = _defaultScripts(cls) if cls is not None else {}
	related = set(defaults)
	for g in list(defaults):
		# kb(desktop)/kb(laptop) unbindings of a kb: default, unless that key is another command's default.
		related.update(v for v in _layoutVariants(g) if ownDefaults.get(v) in (None, cmd.scriptName))
	changed = False
	for gid, entries in list(getattr(gm, "_map", {}).items()):
		for mod, clsName, scr in list(entries):
			if (mod, clsName) != (cmd.module, cmd.className):
				continue
			# Its own changes, and another command of its class holding one of its default keys.
			if scr == cmd.scriptName or (scr is None and gid in related) or (scr is not None and gid in defaults):
				gm.remove(gid, mod, clsName, scr)
				changed = True
	if changed and save:
		gm.save()
	return changed


def saveUserGestures():
	inputCore.manager.userGestureMap.save()


def _firstLine(text, default):
	lines = (text or "").strip().splitlines()
	return lines[0] if lines else default


def _willRun(scriptFunc):
	"""False when NVDA will pass the key through instead of running the script (same script re-entered)."""
	if not getattr(scriptHandler, "_isScriptRunning", False):
		return True
	ref = getattr(scriptHandler, "_lastScriptRef", None)
	last = ref() if ref else None
	return last != getattr(scriptFunc, "__func__", scriptFunc)


def _executeScriptHook(scriptFunc, gesture, *args, **kwargs):
	try:
		if gesture is not None and _plugin is not None and _willRun(scriptFunc):
			_plugin.onScript(scriptFunc)
	except Exception:
		log.debugWarning("PersonalGestureManager: record failed", exc_info=True)
	try:
		if _plugin is not None:
			scriptFunc = _plugin.replacedScript(scriptFunc)
	except Exception:
		log.debugWarning("PersonalGestureManager: script check failed", exc_info=True)
	return _origExecuteScript(scriptFunc, gesture, *args, **kwargs)


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	scriptCategory = ADDON_CATEGORY

	def __init__(self):
		super().__init__()
		global _plugin, _origExecuteScript
		self.stats = None
		self._menuItem = None
		self.dialog = None
		self._saveErrorReported = False
		self.uiLanguage = None  # None: follow NVDA; "th"/"en": chosen with Ctrl+T in the dialog
		self.settings = {}
		self._saveThread = None
		self.testLog = []  # shortcut tester results since NVDA started, newest first
		if globalVars.appArgs.secure:
			return
		self._settingsPath = os.path.join(dataDir(), "settings.json")
		self.settings = self._loadSettings()
		self.uiLanguage = self.settings.get("uiLanguage")
		path = os.path.join(dataDir(), "stats.json")
		self.stats = core.StatsStore(path)
		_plugin = self
		if scriptHandler.executeScript is not _executeScriptHook:  # never wrap ourselves (endless recursion)
			_origExecuteScript = scriptHandler.executeScript
			scriptHandler.executeScript = _executeScriptHook
		self._timer = wx.PyTimer(self._autoSave)
		self._timer.Start(SAVE_INTERVAL_MS)  # writes only when something new was recorded
		import gui
		tools = gui.mainFrame.sysTrayIcon.toolsMenu
		self._menuItem = tools.Append(wx.ID_ANY, _("Personal &Gesture Manager..."))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, lambda e: self.openManager(), self._menuItem)

	# Each setting with the values it may have; anything else in the file is ignored.
	SETTINGS = {
		"uiLanguage": lambda v: v in (None, "th", "en"),
		"statsPeriod": lambda v: v in ("session", "today", "week", "month", "all"),
		"statsAddon": lambda v: isinstance(v, str) and len(v) < 200,
		"statsShow": lambda v: v in ("most", "least", "unused"),
		"lastConflicts": lambda v: isinstance(v, int) and not isinstance(v, bool) and 0 <= v < 100000,
	}

	def _loadSettings(self):
		try:
			import json
			with open(self._settingsPath, encoding="utf-8") as f:
				d = json.load(f)
		except (OSError, ValueError):
			return {}
		if not isinstance(d, dict):
			return {}
		return {k: v for k, v in d.items() if k in self.SETTINGS and self.SETTINGS[k](v)}

	def getSetting(self, key, default=None):
		return self.settings.get(key, default)

	def setSetting(self, key, value):
		"""Remember a choice of the dialog (kept across NVDA restarts)."""
		if not self.SETTINGS[key](value) or self.settings.get(key, object()) == value:
			return
		self.settings[key] = value
		try:
			import json
			os.makedirs(os.path.dirname(self._settingsPath), exist_ok=True)
			tmp = self._settingsPath + ".tmp"
			with open(tmp, "w", encoding="utf-8") as f:
				json.dump(self.settings, f)
			os.replace(tmp, self._settingsPath)
		except OSError:
			log.error("PersonalGestureManager: could not save settings", exc_info=True)

	def setUiLanguage(self, lang):
		"""Remember the dialog language chosen with Ctrl+T."""
		self.uiLanguage = lang
		self.setSetting("uiLanguage", lang)

	def ensureBackup(self, note=None):
		"""Back up gestures.ini before every change; identical content is not duplicated."""
		core.makeBackup(gesturesPath(), backupDir(), note=note)

	def _autoSave(self):
		"""Periodic save, written in a background thread so speech never pauses."""
		if self._saveThread is not None and self._saveThread.is_alive():
			return self._saveThread  # previous write still running; try again next time
		if self.stats.lastWriteOk:
			self._saveErrorReported = False  # writing works again: a new failure is reported again
		self._saveThread = self.stats.saveInBackground(onError=lambda e: wx.CallAfter(self._saveFailed, e))
		return self._saveThread

	def _saveNow(self):
		"""Final save on exit, in this thread, after any background write has finished."""
		if self._saveThread is not None:
			self._saveThread.join(5)
			if self._saveThread.is_alive():
				# The disk does not answer (e.g. a network drive): do not hold NVDA's exit any longer.
				log.error("PersonalGestureManager: statistics not saved on exit, the previous write did not finish")
				return
		try:
			# Forced: if a background write was still running or failed, its data is written again here.
			self.stats.save(force=True)
		except Exception as e:
			self._saveFailed(e)

	def _saveFailed(self, error):
		if self._saveErrorReported:
			log.debugWarning("PersonalGestureManager: save failed again: %r" % (error,))
			return
		self._saveErrorReported = True
		log.error("PersonalGestureManager: save failed: %r" % (error,))
		ui.message(_("Personal Gesture Manager: usage statistics could not be saved. "
			"Check free disk space; details are in the NVDA log."))

	def replacedScript(self, scriptFunc):
		"""NVDA's "report title" command (NVDA+T, or whatever the user chose) in this add-on's window reports
		the window and which NVDA it runs on. Everywhere else, and in its question windows, NVDA's own."""
		func = getattr(scriptFunc, "__func__", scriptFunc)
		owner = getattr(scriptFunc, "__self__", None)
		if (getattr(func, "__name__", "") == "script_title" and type(owner).__name__ == "GlobalCommands"
				and self._dialogInForeground()):
			return self._reportManager
		return scriptFunc

	def _dialogInForeground(self):
		d = self.dialog
		if not d:
			return False
		try:
			import api
			fg = api.getForegroundObject()
			return fg is not None and fg.windowHandle == d.GetHandle()
		except Exception:
			return False

	def _reportManager(self, gesture):
		"""NVDA+T in the window, as NVDA's own title command: once, the short summary; twice quickly, every detail,
		one per line; three times, the details are copied to the clipboard."""
		try:
			repeat = scriptHandler.getLastScriptRepeatCount()
			if repeat >= 2:
				self.dialog.copyDetails()
				return
			if repeat == 1:
				ui.message("\n".join(self.dialog.detailLines()))
				return
			ui.message(self.dialog.statusText())
		except Exception:
			log.debugWarning("PersonalGestureManager: report failed", exc_info=True)

	# Like NVDA's own report-title command, heard in "on-demand" speech mode too.
	_reportManager.speakOnDemand = True

	def onScript(self, scriptFunc):
		func = getattr(scriptFunc, "__func__", scriptFunc)
		fname = getattr(func, "__name__", "")
		if not fname.startswith("script_"):
			return
		sname = fname[7:]
		owner = getattr(scriptFunc, "__self__", None)
		desc = getattr(func, "__doc__", None) or sname
		if owner is None:
			if not sname.startswith("kb:"):
				return
			# Emulated system keyboard key: a plain function NVDA creates, listed under GlobalCommands.
			self.stats.record("globalCommands.GlobalCommands:" + sname, _firstLine(desc, sname), None, None)
			return
		cls = type(owner)
		try:
			key, addon = _keyCache[(cls, sname)]
		except KeyError:
			key = core.scriptKey(cls, sname)
			addon = addonForModule(core.definingClass(cls, sname).__module__)[0]
			_keyCache[(cls, sname)] = (key, addon)
		cat = getattr(func, "category", None) or getattr(owner, "scriptCategory", None)
		self.stats.record(key, _firstLine(desc, sname), addon, cat)

	def terminate(self):
		global _plugin, _origExecuteScript
		# Restore only if nobody wrapped us; otherwise the hook stays as a pass-through.
		if _origExecuteScript is not None and scriptHandler.executeScript is _executeScriptHook:
			scriptHandler.executeScript = _origExecuteScript
			_origExecuteScript = None
		_plugin = None
		if self.stats:
			self._timer.Stop()
			self._saveNow()
		if self._menuItem is not None:
			try:
				import gui
				gui.mainFrame.sysTrayIcon.Unbind(wx.EVT_MENU, id=self._menuItem.GetId())
				gui.mainFrame.sysTrayIcon.toolsMenu.Remove(self._menuItem)
			except Exception:
				pass
		if self.dialog:
			try:
				self.dialog._closed = True
				self.dialog._stopCapture()
				self.dialog.Destroy()
			except Exception:
				pass
		super().terminate()

	def openManager(self, page=0, commands=None, announce=True):
		if self.stats is None:
			ui.message(_("Personal Gesture Manager is not available on secure screens"))
			return
		import gui
		from .dialog import ManagerDialog
		if self.dialog:
			# Already open: bring it to the front (prePopup lets NVDA take the foreground from another app).
			gui.mainFrame.prePopup()
			try:
				self.dialog.Raise()
				# Only brought to the front; the tester command also switches to the tester (unless a question is open).
				if page and self.dialog.IsEnabled():
					self.dialog.selectPage(page)
				elif self.dialog.IsEnabled():
					self.dialog.bringBack()
				return
			except RuntimeError:
				self.dialog = None
			finally:
				gui.mainFrame.postPopup()
		gui.mainFrame.prePopup()
		try:
			self.dialog = ManagerDialog(gui.mainFrame, self, page, commands, announce, focus=previousFocus())
			self.dialog.Show()
		except Exception:
			if self.dialog is not None:
				try:
					self.dialog.Destroy()
				except Exception:
					pass
			self.dialog = None
			log.error("PersonalGestureManager: could not open the dialog", exc_info=True)
			ui.message(_("Personal Gesture Manager could not be opened. Details are in the NVDA log."))
		finally:
			gui.mainFrame.postPopup()

	@script(description=_("Opens Personal Gesture Manager"), gesture="kb:NVDA+g")
	def script_openManager(self, gesture):
		wx.CallAfter(self.openManager, 0)

	@script(description=_("Opens the gesture tester of Personal Gesture Manager"))
	def script_openTester(self, gesture):
		wx.CallAfter(self.openManager, 3)
