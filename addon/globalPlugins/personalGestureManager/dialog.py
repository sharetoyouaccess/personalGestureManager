# Personal Gesture Manager - main dialog
# Copyright (C) 2026 Peem Narkkhwan. GPL v2.

import functools
import gettext
import os
import re
import time

import addonHandler
import inputCore
import ui
import wx
from gui import guiHelper
from logHandler import log

from . import core
from . import (addGesture, removeGesture, unbindGesture, resetCommand, saveUserGestures, blockedLayouts, isUserGesture,
	snapshotUserGestures, restoreUserGestures, takenInClass,
	collectCommands, envInfo, systemInfo, gestureParts,
	gesturesPath, backupDir, reloadUserGestures,
	listAddonGuides, nvdaGuides, currentLanguage, languageName, openFile, showHtml)

addonHandler.initTranslation()

# ---------- interface language (Ctrl+T switches Thai / English inside this dialog) ----------
_nvdaGettext = _  # the add-on's catalogue for NVDA's own language, installed by initTranslation()
_uiCatalog = None  # None: follow NVDA's language; otherwise an explicit catalogue
LOCALE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "locale")
UI_LANGUAGES = ("th", "en")
LANGUAGE_NAMES = {"th": "\u0e20\u0e32\u0e29\u0e32\u0e44\u0e17\u0e22", "en": "English"}  # spoken in their own language
# Spoken after a switch, always in the new language (not taken from the catalogue).
# Both languages in each announcement: whoever pressed Ctrl+T by mistake understands how to go back.
LANGUAGE_CHANGED = {
	"th": "\u0e40\u0e1b\u0e25\u0e35\u0e48\u0e22\u0e19\u0e20\u0e32\u0e29\u0e32\u0e02\u0e2d\u0e07\u0e2b\u0e19\u0e49\u0e32\u0e15\u0e48\u0e32\u0e07\u0e40\u0e1b\u0e47\u0e19\u0e20\u0e32\u0e29\u0e32\u0e44\u0e17\u0e22\u0e41\u0e25\u0e49\u0e27 "
		"Interface language: Thai. Press Ctrl+T again for English.",
	"en": "Interface language changed to English. "
		"\u0e01\u0e14 Ctrl+T \u0e2d\u0e35\u0e01\u0e04\u0e23\u0e31\u0e49\u0e07\u0e40\u0e1e\u0e37\u0e48\u0e2d\u0e40\u0e1b\u0e25\u0e35\u0e48\u0e22\u0e19\u0e40\u0e1b\u0e47\u0e19\u0e20\u0e32\u0e29\u0e32\u0e44\u0e17\u0e22"}


def _(text):  # noqa: F811 - replaces the gettext function installed above
	return _uiCatalog.gettext(text) if _uiCatalog is not None else _nvdaGettext(text)


def N_(text):
	"""Marks a string for translation; it is translated when used, so a language switch takes effect."""
	return text


def setUiLanguage(lang):
	"""lang: None (follow NVDA), "en" or "th"."""
	global _uiCatalog
	if lang is None:
		_uiCatalog = None
	elif lang == "en":
		_uiCatalog = gettext.NullTranslations()
	else:
		try:
			_uiCatalog = gettext.translation("nvda", localedir=LOCALE_DIR, languages=[lang])
		except OSError:
			_uiCatalog = gettext.NullTranslations()


def shownLanguage(override, nvdaLanguage):
	"""Language the dialog is displayed in: "th", "en" or another NVDA language."""
	return override or ("th" if nvdaLanguage.startswith("th") else nvdaLanguage)


def nextLanguage(override, nvdaLanguage):
	return "en" if shownLanguage(override, nvdaLanguage) == "th" else "th"


if hasattr(wx, "Accessible"):
	class _ShortcutAccessible(wx.Accessible):
		"""Reports the Alt key (MSAA accKeyboardShortcut) for a control whose label has no underlined letter."""

		def __init__(self, window, shortcut):
			super().__init__(window)
			self._shortcut = shortcut

		def GetKeyboardShortcut(self, childId):
			if childId == 0:  # the control itself, not list items
				return (wx.ACC_OK, self._shortcut)
			return (wx.ACC_NOT_IMPLEMENTED, None)
else:
	_ShortcutAccessible = None


def _announceShortcut(ctrl, shortcut):
	if _ShortcutAccessible is None:
		return
	try:
		ctrl.SetAccessible(_ShortcutAccessible(ctrl, shortcut))
	except Exception:
		log.debugWarning("PersonalGestureManager: cannot set accessible shortcut", exc_info=True)


def _layoutText(gid, layout):
	"""The keyboard layout of a shared key; nothing for braille and touch gestures, which have none."""
	return LAYOUT_LABELS[layout] if gid.lower().startswith("kb") else ""


def _withLayout(text, gid, layout):
	lay = _layoutText(gid, layout)
	return "%s, %s" % (text, lay) if lay else text


def _conflictTarget(cf):
	"""The key of a conflict in the layouts where it is shared (kb(desktop):X for a desktop-only conflict)."""
	if cf.layout == "both" or not cf.gesture.lower().startswith("kb:"):
		return cf.gesture
	return "kb(%s):%s" % (cf.layout, cf.gesture.split(":", 1)[1])


def _layoutSplit(cmds, target):
	"""Bindings of cmds on target's key in target's layouts: (pairs to remove, pairs to add back).
	A binding that also covers another layout is re-added for that layout only."""
	lays, base = core.gestureLayouts(target)
	remove, back = [], []
	for c in cmds:
		hit = core.overlapping(c.gestures, target)
		rest = [g for g in c.gestures if g not in hit]
		for g in hit:
			remove.append((c, g))
			if g.lower().startswith("kb"):
				for lay in sorted(core.gestureLayouts(g)[0] - lays):
					v = "kb(%s):%s" % (lay, base.split(":", 1)[1])
					if not core.gestureCovered(rest, v):
						back.append((c, v))
						rest.append(v)
	return remove, back


def _sameClass(a, b):
	return (a.module, a.className) == (b.module, b.className)


def _setColumnTitle(lc, i, title):
	try:
		col = lc.GetColumn(i)
		col.SetText(title)
		lc.SetColumn(i, col)
	except Exception:
		log.debugWarning("PersonalGestureManager: cannot rename a column", exc_info=True)


class _Translated(dict):
	def __getitem__(self, key):
		return _(dict.__getitem__(self, key))

	def get(self, key, default=None):
		return self[key] if key in self else default


MODE_LABELS = _Translated({"installed": N_("installed"), "portable": N_("portable"), "unknown": N_("unknown"),
	"store": N_("Windows Store")})


def gestureText(gid):
	text, layout, source = gestureParts(gid)
	if layout:
		return "%s (%s)" % (text, LAYOUT_LABELS[layout])
	return "%s (%s)" % (text, source) if source else text


PAGE_COMMANDS, PAGE_CONFLICTS, PAGE_STATS, PAGE_TESTER, PAGE_GUIDES = range(5)
PERIOD_LABELS = (
	("session", N_("This NVDA session")), ("today", N_("Today")),
	("week", N_("Last 7 days")), ("month", N_("Last 30 days")),
	("all", N_("All time")))
LAYOUT_LABELS = _Translated({"both": N_("all keyboard layouts"), "desktop": N_("desktop"), "laptop": N_("laptop")})
ALL, ADDONS, CORE = "*", "+", ""
# Self-explanatory, so the meaning is heard on every row.
KIND_LABELS = _Translated({"conflict": N_("Conflict"), "override": N_("Override"),
	"context": N_("Depends on focus")})
# Longer forms, where there is room to explain (the quick guide).
KIND_LONG = _Translated({"conflict": N_("Conflict, only one works"),
	"override": N_("Override, one command wins"), "context": N_("Depends on focused control")})
MOVE, KEEP, AGAIN = "move", "keep", "again"
STATS_SHOW = ("most", "least", "unused")
TAB_ANNOUNCE_DELAY_MS = 300
STATS_FILTERS = (N_("Most used commands"), N_("Least used commands"), N_("Unused commands with a gesture"))
# The Commands tab filters by shortcut; how much commands are used is the Statistics tab's business.
CMD_WITH, CMD_MULTI, CMD_WITHOUT, CMD_ALL = range(4)
CMD_FILTERS = (N_("Commands with a gesture"), N_("Commands with more than one gesture"),
	N_("Commands without a gesture"), N_("All commands"))
PAGE_TITLES = (N_("Commands by add-on"), N_("Conflicts"), N_("Statistics"), N_("Gesture tester"),
	N_("Guides for NVDA and add-ons"))
CONF_KINDS = ("conflict", "override", "context")
HELP_IDS = ("commands", "conflicts", "statistics", "tester", "guides")  # sections of the guide, one per tab
TEST_LOG_MAX = 300  # tester results kept


def _NAV_KEYS():
	return (wx.WXK_UP, wx.WXK_DOWN, wx.WXK_LEFT, wx.WXK_RIGHT, wx.WXK_HOME, wx.WXK_END, wx.WXK_PAGEUP, wx.WXK_PAGEDOWN)


def _cmdName(c):
	"""The command as its owner names it; the one place that marks commands without a description."""
	return c.name if c.documented else _("{name} (no description)").format(name=c.name)


def _cmdText(c, active=None):
	"""The add-on first: it is what tells commands apart, and it is heard at once."""
	t = "%s: %s" % (c.addonSummary or _("NVDA"), _cmdName(c))
	if active is not None and c is active:
		t += " " + _("(runs now)")
	return t


def _layoutOptions(gids):
	"""For a keyboard gesture: all layouts, desktop only and laptop only, whatever layout is in use now
	(NVDA itself only offers the current one). Empty for other devices."""
	generic = next((g for g in gids if g.lower().startswith("kb:")), None)
	if generic is None:
		return []
	key = generic.split(":", 1)[1]
	text = gestureParts(generic)[0]
	return [(generic, _("{key}, all keyboard layouts").format(key=text)),
		("kb(desktop):" + key, _("{key}, desktop layout only").format(key=text)),
		("kb(laptop):" + key, _("{key}, laptop layout only").format(key=text))]


def _gestureLong(gid):
	"""Name that always states the keyboard layout (used where the user picks one shortcut out of several)."""
	text, layout, source = gestureParts(gid)
	if gid.lower().startswith("kb"):
		if layout == "desktop":
			return _("{key}, desktop layout only").format(key=text)
		if layout == "laptop":
			return _("{key}, laptop layout only").format(key=text)
		return _("{key}, all keyboard layouts").format(key=text)
	return "%s (%s)" % (text, source) if source else text


def _timesText(n):
	"""Short count for the Statistics list, e.g. "12 times"."""
	return _("1 time") if n == 1 else _("{n} times").format(n=n)


def _html(text):
	return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _firstSentence(text, limit=120):
	text = (text or "").strip()
	for sep in (". ", "\n"):
		if sep in text:
			text = text.split(sep, 1)[0] + (sep.strip() if sep == ". " else "")
			break
	return text if len(text) <= limit else text[:limit - 1].rstrip() + "\u2026"


def _preferredLanguages(lang):
	order = [lang]
	if "_" in lang:
		order.append(lang.split("_", 1)[0])
	if "en" not in order:
		order.append("en")
	return order


def _match(want, addon):
	if want == ALL:
		return True
	if want == ADDONS:
		return bool(addon)
	return (addon or CORE) == want


def _interrupt():
	try:
		import speech
		speech.cancelSpeech()
	except Exception:
		pass


def _interruptAndSay(msg):
	_interrupt()
	ui.message(msg)


def _ask(parent, msg, title, yesDefault=False, cancelIsNone=False):
	"""Yes/No question via wx.MessageDialog (works on all NVDA versions). No is the default unless asked.
	cancelIsNone: Cancel (or Escape) gives None, so No can mean something else than giving up."""
	# CANCEL too: without it Windows gives the box no close button and Escape does nothing. Escape means No.
	d = wx.MessageDialog(parent, msg, title,
		wx.YES_NO | wx.CANCEL | (wx.YES_DEFAULT if yesDefault else wx.NO_DEFAULT) | wx.ICON_QUESTION)
	try:
		r = d.ShowModal()
		if cancelIsNone and r not in (wx.ID_YES, wx.ID_NO):
			return None
		return r == wx.ID_YES
	finally:
		d.Destroy()


def _askConflict(parent, msg, title):
	"""MOVE, KEEP, AGAIN (press another key) or None (cancel)."""
	d = wx.MessageDialog(parent, msg, title, wx.YES_NO | wx.CANCEL | wx.HELP | wx.CANCEL_DEFAULT | wx.ICON_WARNING)
	try:
		d.SetYesNoCancelLabels(_("&Move it to this command"), _("&Keep on both commands"), _("Cancel"))
		d.SetHelpLabel(_("&Choose another gesture"))
		r = d.ShowModal()
		return MOVE if r == wx.ID_YES else KEEP if r == wx.ID_NO else AGAIN if r == wx.ID_HELP else None
	finally:
		d.Destroy()


def _choose(parent, msg, title, items, default=0):
	"""Index chosen in a single choice dialog, or None if cancelled."""
	d = wx.SingleChoiceDialog(parent, msg, title, items)
	try:
		if 0 < default < len(items):
			d.SetSelection(default)
		return d.GetSelection() if d.ShowModal() == wx.ID_OK else None
	finally:
		d.Destroy()


class _ShortcutsDialog(wx.Dialog):
	"""The shortcuts of one command: one row per shortcut (Enter changes it, Delete removes it),
	then a button for each other action. However many shortcuts, the buttons stay the same."""

	def __init__(self, parent, head, actions, name=""):
		super().__init__(parent, title=_("Adjust gestures for this command"))
		self.actions, self.result, self.name, self._hint = actions, None, name, None
		self.rows = [i for i, a in enumerate(actions) if a[1] == "change"]
		h = guiHelper.BoxSizerHelper(self, orientation=wx.VERTICAL)
		h.addItem(wx.StaticText(self, label=head))
		self.list = h.addLabeledControl(_("Gestures"), wx.ListBox,
			choices=[actions[i][3] for i in self.rows])
		bh = guiHelper.ButtonHelper(wx.VERTICAL)
		labels = {"add": _("Add a gesture..."), "reset": _("Reset this command to default"),
			"resetAll": actions[-1][0]}
		first = None
		for i, a in enumerate(actions):
			if a[1] in labels:
				b = bh.addButton(self, label=labels[a[1]])
				b.Bind(wx.EVT_BUTTON, lambda e, i=i: self._done(i))
				if first is None:
					first = b
		bh.addButton(self, id=wx.ID_CANCEL, label=_("&Close"))
		h.addItem(bh)
		self.list.Bind(wx.EVT_KEY_DOWN, self.onListKey)
		self.Bind(wx.EVT_CHAR_HOOK, self.onCharHook)
		self.list.Bind(wx.EVT_LISTBOX_DCLICK, lambda e: self._row(0))
		self.list.Bind(wx.EVT_SET_FOCUS, self.onListFocus)
		self.list.Bind(wx.EVT_LISTBOX, lambda e: (e.Skip(), self._sayHint()))
		self.SetEscapeId(wx.ID_CANCEL)
		s = wx.BoxSizer(wx.VERTICAL)
		s.Add(h.sizer, border=guiHelper.BORDER_FOR_DIALOGS, flag=wx.ALL)
		self.SetSizerAndFit(s)
		self.CentreOnScreen()
		if self.rows:
			self.list.SetSelection(0)
			self.list.SetFocus()
		else:
			first.SetFocus()  # nothing to change: the first thing to do is to add one

	def _done(self, index):
		self.result = index
		self.EndModal(wx.ID_OK)

	def _row(self, offset):
		"""offset 0: the row's "change" action; 1: its "remove" action (the next one in the list), once confirmed."""
		i = self.list.GetSelection()
		if 0 <= i < len(self.rows):
			g = self.actions[self.rows[i]][2]
			if offset and not _ask(self, _("Remove {g} from {cmd}?").format(g=_gestureLong(g), cmd=self.name),
					_("Remove gesture")):
				return  # No: still in the list, on the same shortcut
			self._done(self.rows[i] + offset)
		else:
			ui.message(_("No gesture"))

	def onListKey(self, evt):
		k = evt.GetKeyCode()
		if k in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER) and not evt.HasAnyModifiers():
			self._row(0)
		elif k == wx.WXK_DELETE and not evt.HasAnyModifiers():
			self._row(1)
		elif not self.rows and k in _NAV_KEYS():
			ui.message(_("No gesture"))
		else:
			evt.Skip()

	def onCharHook(self, evt):
		"""Enter on a shortcut changes it: seen here first, before the dialog uses Enter for a button."""
		if (self.FindFocus() is self.list and evt.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER)
				and not evt.HasAnyModifiers()):
			self._row(0)
		else:
			evt.Skip()

	def onListFocus(self, evt):
		evt.Skip()
		if not self.rows:
			wx.CallLater(100, ui.message, _("No gesture"))  # after NVDA has announced the empty list
		else:
			self._sayHint()

	def _sayHint(self):
		"""After NVDA has read the shortcut: what can be done with it. Only the last one is said when moving fast."""
		if self._hint is not None:
			self._hint.Stop()
		self._hint = wx.CallLater(150, _queueMessage, _("Press Enter to change, or Delete to remove the selected gesture."))


def _queueMessage(msg):
	"""Spoken after what NVDA is reading now (queued behind its events), never cutting it off."""
	try:
		import queueHandler
		queueHandler.queueFunction(queueHandler.eventQueue, ui.message, msg)
	except Exception:
		ui.message(msg)


def _shortcutsDialog(parent, head, actions, name=""):
	"""Index in actions of what was chosen, or None if closed."""
	d = _ShortcutsDialog(parent, head, actions, name)
	try:
		d.ShowModal()
		return d.result
	finally:
		d.Destroy()


class _VirtualList(wx.ListCtrl):
	"""A virtual report list: rows are given on demand, so refilling is fast at any size."""

	def __init__(self, parent, **kw):
		kw["style"] = kw.get("style", 0) | wx.LC_VIRTUAL
		super().__init__(parent, **kw)
		self._rows = []

	def OnGetItemText(self, item, col):
		try:
			return self._rows[item][col]
		except IndexError:
			return ""

	def OnFindItem(self, start, prefix):
		"""Type-ahead: the next row whose first column starts with the letters typed."""
		prefix = (prefix or "").lower()
		n = len(self._rows)
		for k in range(n):
			i = (max(start, 0) + k) % n
			if self._rows[i] and str(self._rows[i][0]).lower().startswith(prefix):
				return i
		return -1

	def setRows(self, rows):
		# Clear rows beyond the new end, or NVDA reads a row that no longer exists ("unknown").
		try:
			for i in {self.GetFirstSelected(), self.GetFocusedItem()}:
				if i >= len(rows):
					self.SetItemState(i, 0, wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED)
		except Exception:
			pass
		self._rows = rows
		self.SetItemCount(len(rows))
		self.Refresh()


def _fill(lc, rows, emptyText, select=0):
	"""Refill a list and select one row. An empty list has no row; emptyText is spoken when it gets focus."""
	lc.emptyText = emptyText
	data = [list(r) for r in rows]
	width = max([len(r) for r in data] or [0])
	lc.setRows([r + [""] * (width - len(r)) for r in data])
	if data:
		i = max(0, min(select or 0, len(data) - 1))
		lc.Select(i)
		lc.Focus(i)


def _safe(listAttr, rowsAttr):
	"""A failure in one tab shows a message in that tab's list instead of breaking the dialog."""
	def deco(fn):
		@functools.wraps(fn)
		def wrapper(self, *a, **kw):
			try:
				return fn(self, *a, **kw)
			except Exception:
				log.error("PersonalGestureManager: %s failed" % fn.__name__, exc_info=True)
				setattr(self, rowsAttr, [])
				try:
					_fill(getattr(self, listAttr), [], _("This list could not be loaded. Details are in the NVDA log."))
				except Exception:
					pass
		return wrapper
	return deco


class ManagerDialog(wx.Dialog):

	def __init__(self, parent, plugin, page=PAGE_COMMANDS, commands=None, announce=True, focus=None):
		setUiLanguage(plugin.uiLanguage)
		# The application the user came from: every reload of the commands is for it, not for this window.
		self._focus = focus
		self._rawEnv = dict(envInfo())
		self._translateEnv()
		super().__init__(parent, title=self._title())
		try:
			self.plugin = plugin
			self.stats = plugin.stats
			self._captureCb = None
			self._continuous = False
			self._closed = False
			self._returnTo = None  # (row, gesture, layout, command key) when a change should go back to Conflicts
			self._savedCmdFilters = None  # Commands tab filters before going to a command from another tab
			self._stale = set()
			self._pending = {}  # rows to select when a list is next built (after a language switch)
			self.cmdRows, self.statsKeys, self.confRows, self.guideRows = [], [], [], []
			self._guideSource = None  # loaded the first time the Guides tab is shown
			self.commands = commands if commands is not None else self._collect()
			self.conflicts = []
			# Ctrl+T anywhere in this dialog switches its language between Thai and English.
			self._langId = wx.NewIdRef() if hasattr(wx, "NewIdRef") else wx.NewId()
			self.Bind(wx.EVT_MENU, self.onToggleLanguage, id=self._langId)
			self._letterIds = {}
			self._buildUi()
			outer = wx.BoxSizer(wx.VERTICAL)
			outer.Add(self.root, 1, wx.EXPAND)
			self.SetSizer(outer)
			self.Bind(wx.EVT_CLOSE, self.onClose)
			self.Bind(wx.EVT_ACTIVATE, self.onActivate)
			self.Bind(wx.EVT_CHAR_HOOK, self.onCharHook)
			self.Bind(wx.EVT_CHILD_FOCUS, self.onChildFocus)
			self._lastFocus = None
			self.SetSize((800, 580))
			self.CentreOnScreen()
			self._showPage(page)
			wx.CallAfter(self.selectPage, page)
			# NVDA reads the window name itself; the details are with NVDA+T (see statusText).
			if announce and page == PAGE_CONFLICTS:
				wx.CallAfter(self._announceConflicts)
		except Exception:
			self._closed = True  # pending timers do nothing
			self.Destroy()  # never leave a hidden, half-built window behind
			raise

	def _collect(self):
		return collectCommands(self._focus)

	# ---------- building ----------
	def _translateEnv(self):
		self.env = dict(self._rawEnv)
		self.env["mode"] = MODE_LABELS.get(self._rawEnv["mode"], self._rawEnv["mode"])

	def _title(self):
		return _("Personal Gesture Manager")

	def _sys(self):
		"""Read when asked, so the input language (and anything else that changes) is current."""
		try:
			return systemInfo()
		except Exception:
			return {}

	def statusText(self):
		"""NVDA+T in this window: the name, then which NVDA, on which computer and Windows."""
		s = self._sys()
		return _("{name}. NVDA {version}, {mode}, on {computer}, {windows}.").format(name=self._title(),
			version=self._rawEnv.get("version", "?"), mode=self.env.get("mode", "?"),
			computer=s.get("computer", "?"), windows=s.get("windows", "?"))

	def detailLines(self):
		"""Everything worth knowing about where this add-on works, most useful first (NVDA+T twice, NVDA details)."""
		s, e = self._sys(), self.env
		n = len(self._realConflicts()) if self.conflicts else 0
		lines = [
			_("NVDA {version}, {mode}, running from {nvdaDir}").format(version=e.get("version", "?"),
				mode=e.get("mode", "?"), nvdaDir=s.get("nvdaDir", "?")),
			_("Gestures and settings saved in {configPath}").format(configPath=e.get("configPath", "?")),
			_("Keyboard layout: {layout}. Input language: {lang}.").format(
				layout=LAYOUT_LABELS.get(e.get("layout"), e.get("layout", "?")), lang=s.get("inputLanguage", "?")),
			(_("No conflicts between add-ons.") if not n else _("1 conflict between add-ons") + "." if n == 1
				else _("{n} conflicts between add-ons").format(n=n) + "."),
		]
		if s.get("addons") is not None:
			lines.append(_("{n} add-ons, {running} running.").format(n=s["addons"], running=s.get("running", "?")))
		lines.append(_("{windows}, build {build}. Computer name: {computer}.").format(windows=s.get("windows", "?"),
			build=s.get("build", "?"), computer=s.get("computer", "?")))
		lines.append(_("Application tested: {app}").format(app=e.get("app", "?")))
		return lines

	def _buildUi(self):
		self._mnemonics = []
		self._texts = []  # (control, msgid, kind): relabelled in place when the language changes
		self._altKeys = []  # (control, msgid) with an Alt key
		self._guidesBuilt = False
		self.root = root = wx.Panel(self)
		main = wx.BoxSizer(wx.VERTICAL)
		self.book = root._book = wx.Notebook(root)
		for build, title in zip((self._buildCommands, self._buildConflicts, self._buildStats, self._buildTester,
				self._buildGuides), PAGE_TITLES):
			self.book.AddPage(build(), _(title))
		main.Add(self.book, 1, wx.EXPAND | wx.ALL, 8)
		self._building = None  # available on every page
		close = self._reg(wx.Button(root, wx.ID_CLOSE, _("&Close")), "&Close", "button")
		close.Bind(wx.EVT_BUTTON, lambda e: self.Close())
		main.Add(close, 0, wx.ALIGN_RIGHT | wx.ALL, 8)
		root.SetSizer(main)
		self.SetEscapeId(wx.ID_CLOSE)
		self._installKeys()

	def _showPage(self, page, selectKey=None):
		self.book.SetSelection(page)
		self.refreshAll(selectKey=selectKey)
		# Bound only now: the initial page selection must not rebuild lists a second time.
		self.book.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.onPageChanged)

	# ---------- labels and Alt keys ----------
	def _labeled(self, h, msgid, ctrlClass, **kw):
		ctrl = h.addLabeledControl(_(msgid), ctrlClass, **kw)
		# The label is the static text created just before the control (gui.guiHelper.LabeledControlHelper).
		try:
			label = ctrl.GetPrevSibling()
		except Exception:
			label = None
		if isinstance(label, wx.StaticText):
			self._texts.append((label, msgid, "label"))
		return self._reg(ctrl, msgid, "focus")

	def _reg(self, ctrl, msgid, kind):
		"""Remember the Alt key of msgid. A translation may leave out the "&" (Thai labels have no Latin
		letter to underline); the key is then also reported to NVDA, so it is announced as in English."""
		if kind in ("button", "check"):
			self._texts.append((ctrl, msgid, kind))
		m = re.search(r"&(\w)", msgid)
		if m:
			# Alt keys are handled per tab: Windows' own handling searches every tab and can cycle between them.
			self._mnemonics.append((self._building, m.group(1).lower(), ctrl, kind))
			self._altKeys.append((ctrl, msgid))
			# Not for lists: focus is on a row there, and it would make long lists slow in NVDA.
			self._shortcutFor(ctrl, msgid)
		return ctrl

	@staticmethod
	def _shortcutFor(ctrl, msgid):
		m = re.search(r"&(\w)", msgid)
		# Once added it stays: in English it reports the same key as the underlined letter.
		if (m and "&" not in _(msgid) and not isinstance(ctrl, wx.ListCtrl)
				and not getattr(ctrl, "_pgmShortcut", False)):
			_announceShortcut(ctrl, "Alt+" + m.group(1).upper())
			ctrl._pgmShortcut = True

	def _installKeys(self):
		entries = [(wx.ACCEL_CTRL, ord("T"), self._langId)]
		for letter in sorted({e[1] for e in self._mnemonics}):
			if letter not in self._letterIds:
				self._letterIds[letter] = wx.NewIdRef() if hasattr(wx, "NewIdRef") else wx.NewId()
				self.Bind(wx.EVT_MENU, lambda e, l=letter: self.onMnemonic(l), id=self._letterIds[letter])
			entries.append((wx.ACCEL_ALT, ord(letter.upper()), self._letterIds[letter]))
		self.SetAcceleratorTable(wx.AcceleratorTable(entries))

	def onMnemonic(self, letter):
		page = self.book.GetSelection()
		for p, l, ctrl, kind in self._mnemonics:
			if l == letter and p in (page, None):
				ctrl.SetFocus()
				if kind == "button":
					evt = wx.CommandEvent(wx.wxEVT_BUTTON, ctrl.GetId())
					evt.SetEventObject(ctrl)
					ctrl.ProcessEvent(evt)
				elif kind == "check":
					ctrl.SetValue(not ctrl.GetValue())
					evt = wx.CommandEvent(wx.wxEVT_CHECKBOX, ctrl.GetId())
					evt.SetEventObject(ctrl)
					ctrl.ProcessEvent(evt)
				return

	# ---------- helpers ----------
	def _list(self, h, label, cols):
		"""cols: (msgid, width), translated here so a language switch can translate them again."""
		lc = self._labeled(h, label, _VirtualList, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
		lc.colIds = [t for t, _w in cols]
		for i, (title, width) in enumerate(cols):
			lc.InsertColumn(i, _(title), width=width)
		lc.Bind(wx.EVT_SET_FOCUS, lambda e, lc=lc: self._onListFocus(e, lc))
		return lc

	def _onListFocus(self, evt, lc):
		evt.Skip()
		if not lc.GetItemCount() and getattr(lc, "emptyText", None):
			self._speakAfterFocus(lc.emptyText, lc)  # an empty list says why it is empty

	def selectPage(self, page):
		try:
			if self._closed:
				return
			if self.book.GetSelection() != page:
				self.book.SetSelection(page)  # the page-changed handler refreshes it
			self._ensure(page)
			# Always start at the first control of the page: predictable, and announces the current filter.
			[self.cmdAddon, self.confShow, self.period, self.testBtn, self.guideList][page].SetFocus()
		except RuntimeError:  # dialog already destroyed (e.g. NVDA reloaded plugins)
			pass

	def onCharHook(self, evt):
		"""Ctrl+1 to Ctrl+5: that tab. Ctrl+Tab, Ctrl+Shift+Tab: the next or previous tab, from anywhere in it.
		The name of the tab is always said first."""
		k, ctrl = evt.GetKeyCode(), evt.ControlDown() and not evt.AltDown()
		n = len(PAGE_TITLES)
		if k == wx.WXK_F1 and not evt.HasAnyModifiers():
			self.openHelp()
		elif ctrl and ord("1") <= k < ord("1") + n and not evt.ShiftDown():
			self.switchTab(k - ord("1"))
		elif ctrl and k == wx.WXK_TAB:
			self.switchTab((self.book.GetSelection() + (-1 if evt.ShiftDown() else 1)) % n)
		else:
			evt.Skip()

	def helpPath(self):
		"""This add-on's guide in the window's language (English when there is none), and the section of the tab."""
		lang = self.plugin.uiLanguage or ("th" if _("Conflicts") != "Conflicts" else "en")
		docs = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "doc")
		path = os.path.join(docs, lang, "readme.html")
		if not os.path.isfile(path):
			path = os.path.join(docs, "en", "readme.html")
		page = self.book.GetSelection()
		return path, HELP_IDS[page] if 0 <= page < len(HELP_IDS) else ""

	def openHelp(self):
		"""F1, as in NVDA's own dialogs: this add-on's guide, at the section of the tab in use."""
		if self._captureCb is not None:
			return  # waiting for a gesture: F1 is the gesture
		path, anchor = self.helpPath()
		try:
			import tempfile
			redirect = os.path.join(tempfile.gettempdir(), "nvda", "personalGestureManagerHelp.html")
			os.makedirs(os.path.dirname(redirect), exist_ok=True)
			try:
				from gui.contextHelp import writeRedirect  # NVDA's own way to open a page at a section
				writeRedirect(anchor, path, redirect)
			except ImportError:
				url = "file:///" + path.replace("\\", "/") + "#" + anchor
				with open(redirect, "w", encoding="utf-8") as f:
					f.write('<html><head><meta http-equiv="refresh" content="0;url=%s"></head></html>' % url)
			os.startfile("file://" + redirect)
		except Exception:
			log.error("PersonalGestureManager: could not open the guide", exc_info=True)
			ui.message(_("The guide could not be opened. Details are in the NVDA log."))

	def switchTab(self, page):
		if self._captureCb is not None:
			return  # waiting for a shortcut: keys are not commands
		self.selectPage(page)
		self._sayTabFirst(page)

	def _sayTabFirst(self, page):
		"""Once NVDA has moved to the first control of the tab: the tab's name, then that control again."""
		def say():
			try:
				import api
				import controlTypes
				import speech
				speech.cancelSpeech()
				ui.message(_(PAGE_TITLES[page]))
				speech.speakObject(api.getFocusObject(), reason=controlTypes.OutputReason.FOCUS)
			except Exception:
				ui.message(_(PAGE_TITLES[page]))
		self._speakAfterFocus(say)

	def onChildFocus(self, evt):
		evt.Skip()
		self._lastFocus = evt.GetWindow()

	def bringBack(self):
		"""Opened again while open: back to where the user was, and say so."""
		try:
			if self._lastFocus:
				self._lastFocus.SetFocus()
		except RuntimeError:  # that control is gone (rebuilt)
			pass
		self._speakAfterFocus(_("Personal Gesture Manager is already open"))

	def _realConflicts(self):
		return [cf for cf in self.conflicts if cf.kind == "conflict" and any(c.addon for c in cf.commands)]

	def _announceConflicts(self):
		"""On arriving at the Conflicts tab: how many there are, if any (the list shows which)."""
		try:
			if self._closed:
				return
			n = len(self._realConflicts())
		except RuntimeError:  # dialog already destroyed
			return
		if n:
			self._speakAfterFocus(_("1 conflict between add-ons") if n == 1
				else _("{n} conflicts between add-ons").format(n=n))

	def _addonChoices(self, extraKeys=()):
		names = {}
		for c in self.commands:
			if c.addon:
				names[c.addon] = c.addonSummary
		for k in extraKeys:
			m = self.stats.meta(k)
			if m and m[1] and m[1] not in names:
				names[m[1]] = m[1]
		items = [(ADDONS, _("All add-ons")), (CORE, _("NVDA"))]
		items += sorted(names.items(), key=lambda x: x[1].lower())
		items.append((ALL, _("All add-ons and NVDA")))  # last: the longest list, the least used
		return items

	@staticmethod
	def _setChoice(choice, items, keep, fallback=None):
		"""Update a choice only when its items changed, so NVDA does not re-announce it.
		keep is selected again; if it is gone, fallback, else the first item."""
		if getattr(choice, "items", None) == items:
			return
		choice.items = items
		choice.SetItems([t for _k, t in items])
		keys = [k for k, _t in items]
		choice.SetSelection(keys.index(keep) if keep in keys else keys.index(fallback) if fallback in keys else 0)

	@staticmethod
	def _choiceKey(choice):
		items = getattr(choice, "items", None)
		return items[choice.GetSelection()][0] if items else getattr(choice, "pendingKey", ADDONS)

	def _cmdByKey(self):
		return {c.key: c for c in self.commands}

	def refreshAll(self, selectKey=None, fallbackIndex=0):
		"""Recompute shared data, rebuild the visible tab now and the others when they are first shown.
		Without selectKey, the selected command stays selected."""
		if selectKey is None and self.cmdRows:
			selectKey = self._selectedKey(self.cmdList, [c.key for c, _n in self.cmdRows])
		try:
			self.conflicts = core.findConflicts(self.commands, includeCoreOnly=True)
		except Exception:
			log.error("PersonalGestureManager: conflict detection failed", exc_info=True)
			self.conflicts = []
		self.refreshCommands(selectKey=selectKey, fallbackIndex=fallbackIndex)  # always: other tabs jump into it
		# The Guides list does not depend on the shortcuts: built once.
		self._stale = {PAGE_CONFLICTS, PAGE_STATS} | (set() if self._guidesBuilt else {PAGE_GUIDES})
		self._ensure(self.book.GetSelection())

	def _ensure(self, page):
		if page in self._stale:
			self._stale.discard(page)
			{PAGE_CONFLICTS: self.refreshConflicts, PAGE_STATS: self.refreshStats,
				PAGE_GUIDES: self.refreshGuides}[page]()

	def onPageChanged(self, evt):
		"""Usage numbers change while NVDA runs, so they are rebuilt (keeping the selected row) on every visit."""
		evt.Skip()
		self._returnTo = None  # the user moved on by themselves
		try:
			page = self.book.GetSelection()
			if page != PAGE_COMMANDS:
				self._restoreCmdFilters()
			if page == PAGE_COMMANDS:
				self.refreshCommands(selectKey=self._selectedKey(self.cmdList, [c.key for c, _n in self.cmdRows]))
			elif page == PAGE_STATS:
				self._stale.discard(page)
				self.refreshStats(selectKey=self._selectedKey(self.statsList, self.statsKeys))
			else:
				self._ensure(page)
			if page == PAGE_CONFLICTS:
				# After NVDA has said the new tab: the tab change reaches NVDA after this handler has run.
				wx.CallLater(TAB_ANNOUNCE_DELAY_MS, self._announceConflicts)
		except RuntimeError:  # dialog destroyed
			pass

	@staticmethod
	def _selectedKey(lc, keys):
		i = lc.GetFirstSelected()
		return keys[i] if 0 <= i < len(keys) else None

	def goToCommand(self, key):
		"""Show a command in the Commands tab, ready to edit."""
		c = self._cmdByKey().get(key)
		if c is None:
			ui.message(_("This command is not available here. App-specific commands are listed only "
				"for the application that had focus before opening this dialog."))
			return False
		if self._savedCmdFilters is None:  # given back when the user returns (see _restoreCmdFilters)
			self._savedCmdFilters = (self._choiceKey(self.cmdAddon), self.cmdFilter.GetSelection())
		keys = [k for k, _t in getattr(self.cmdAddon, "items", [])]
		want = c.addon or CORE
		self.cmdAddon.SetSelection(keys.index(want) if want in keys else 0)
		self.cmdFilter.SetSelection(CMD_ALL)  # the command is shown whether or not it has a shortcut
		self.refreshCommands(selectKey=key)
		if self.book.GetSelection() != PAGE_COMMANDS:
			# ChangeSelection does not raise the page-changed event, so the list is not rebuilt twice.
			getattr(self.book, "ChangeSelection", self.book.SetSelection)(PAGE_COMMANDS)
		self._returnTo = None  # set again by the caller when it wants the user brought back
		self.cmdList.SetFocus()
		return True

	# ---------- page: commands by add-on ----------
	def _buildCommands(self):
		self._building = PAGE_COMMANDS
		p = wx.Panel(self.book)
		h = guiHelper.BoxSizerHelper(p, orientation=wx.VERTICAL)
		self.cmdAddon = self._labeled(h, N_("&Add-on"), wx.Choice, choices=[])
		self.cmdFilter = self._labeled(h, N_("&Filter type"), wx.Choice,
			choices=[_(t) for t in CMD_FILTERS])
		self.cmdFilter.optionIds = CMD_FILTERS
		self.cmdFilter.SetSelection(CMD_WITH)  # a short list of what can be checked or changed
		self.cmdList = self._list(h, N_("C&ommands"),
			((N_("Command"), 300), (N_("Gestures"), 260), (N_("Conflict"), 200)))
		bh = guiHelper.ButtonHelper(wx.HORIZONTAL)
		keys = self._reg(bh.addButton(p, label=_("Adjust ge&stures for this command...")),
			"Adjust ge&stures for this command...", "button")
		bak = self._reg(bh.addButton(p, label=_("&Backups...")), "&Backups...", "button")
		h.addItem(bh)
		self.cmdAddon.Bind(wx.EVT_CHOICE, lambda e: self.refreshCommands())
		self.cmdFilter.Bind(wx.EVT_CHOICE, lambda e: self.refreshCommands())
		keys.Bind(wx.EVT_BUTTON, self.onCmdMenu)  # the same list as Enter on the command
		bak.Bind(wx.EVT_BUTTON, self.onBackups)
		self.cmdList.Bind(wx.EVT_KEY_DOWN, self.onCmdKey)
		self.cmdList.Bind(wx.EVT_CONTEXT_MENU, self.onCmdMenu)
		self.cmdList.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.onCmdMenu)
		self.cmdList.Bind(wx.EVT_LIST_ITEM_SELECTED, self.onCmdSelected)
		p.SetSizer(h.sizer)
		return p

	def _sinceText(self):
		return time.strftime("%Y-%m-%d", time.localtime(self.stats.since()))

	def onCmdSelected(self, evt):
		evt.Skip()
		i = evt.GetIndex() if hasattr(evt, "GetIndex") else -1
		if self._returnTo and 0 <= i < len(self.cmdRows) and self.cmdRows[i][0].key != self._returnTo[3]:
			self._returnTo = None  # the user moved on to another command

	def onCmdKey(self, evt):
		if evt.GetKeyCode() == wx.WXK_DELETE and not evt.HasAnyModifiers():
			self.onRemove(None)
		else:
			evt.Skip()

	def onCmdMenu(self, evt):
		"""The one place to manage the shortcuts of a command (Enter, the Applications key or the button):
		one list, one choice. For each shortcut: change it, remove it; then add, reset."""
		cmd = self._selectedCmd()
		if not cmd:
			return
		actions = []
		for g in cmd.gestures:
			users = self._usedBy([g], cmd)
			key = _gestureLong(g)
			if users:
				change = _("Change {key}, also used by {cmds}...").format(
					key=key, cmds="; ".join(_cmdText(c) for c, _l in users))
			else:
				change = _("Change {key}...").format(key=key)
			row = _("{key}, also used by {cmds}").format(key=key, cmds="; ".join(_cmdText(c) for c, _l in users)) \
				if users else key
			actions += [(change, "change", g, row), (_("Remove {key}").format(key=key), "remove", g, row)]
		actions += [(_("Add a gesture..."), "add", None, None), (_("Reset this command to default"), "reset", None, None),
			(_("Reset all commands of {owner} to default...").format(owner=cmd.addonSummary or _("NVDA")),
				"resetAll", None, None)]
		head = _("Gestures of {cmd}") if cmd.gestures else _("{cmd} has no gesture")
		sel = _shortcutsDialog(self, head.format(cmd=_cmdText(cmd)), actions, cmd.name)
		if sel is None:
			return
		_t, what, g, _r = actions[sel]
		if what == "change":
			self._capturePrompt(cmd, g)
		elif what == "remove":
			self._removeGesture(cmd, g)
		elif what == "add":
			self._capturePrompt(cmd, None)
		elif what == "reset":
			self.onResetCommand(None)
		else:
			self.onResetAddon(None)

	def onResetCommand(self, evt):
		cmd = self._selectedCmd()
		if cmd:
			self._reset([cmd], cmd.key)

	def onResetAddon(self, evt):
		cmd = self._selectedCmd()
		if not cmd:
			return
		cmds = [c for c in self.commands if c.addon == cmd.addon]
		owner = cmd.addonSummary or _("NVDA")
		if _ask(self, _("Reset all {n} commands of {addon} to their default gestures? A backup is made first.").format(n=len(cmds), addon=owner), _("Confirm")):
			self._reset(cmds, cmd.key, owner)

	def _reset(self, cmds, selectKey, owner=None):
		note = (_("resetting all commands of {addon}").format(addon=owner) if owner
			else _("resetting {cmd}").format(cmd=cmds[0].name))
		if not self._backup(note):
			return
		changed = 0
		for c in cmds:
			try:
				changed += bool(resetCommand(c, save=False))
			except Exception:
				log.error("PersonalGestureManager: reset failed for %s" % c.key, exc_info=True)
		saved = True
		if changed:
			try:
				saveUserGestures()  # once for all commands
			except Exception:
				log.error("PersonalGestureManager: could not save gestures", exc_info=True)
				saved = False
		self.commands = self._collect()
		if not saved:
			self._afterEdit(selectKey, _("The default gestures could not be saved. Details are in the NVDA log."))
			return
		if not changed:
			msg = _("Already using the default gestures")
		elif owner:
			msg = _("{addon}: commands reset to default: {n}").format(n=changed, addon=owner)
		else:
			now = self._cmdByKey().get(selectKey)
			keys = ", ".join(gestureText(g) for g in now.gestures) if now and now.gestures else _("No gesture")
			msg = _("Reset to default. Gestures now: {keys}").format(keys=keys)
		self._afterEdit(selectKey, msg, ok=bool(changed))

	def _conflictIndex(self):
		"""Commands with a real conflict, the same ones the Conflicts tab lists by default (overrides and
		overlaps that depend on focus are normal and not marked)."""
		idx = {}
		for cf in self._realConflicts():
			for c in cf.commands:
				idx.setdefault(c.key, []).append(cf)
		return idx

	@_safe("cmdList", "cmdRows")
	def refreshCommands(self, selectKey=None, fallbackIndex=0):
		self._setChoice(self.cmdAddon, self._addonChoices(), self._choiceKey(self.cmdAddon))
		want = self._choiceKey(self.cmdAddon)
		mode = self.cmdFilter.GetSelection()
		uses = self.stats.counts("all")  # since recording started
		cidx = self._conflictIndex()
		rowsData = []
		for c in self.commands:
			if not _match(want, c.addon):
				continue
			n = uses.get(c.key, 0)
			if ((mode == CMD_WITH and not c.gestures) or (mode == CMD_MULTI and len(c.gestures) < 2)
					or (mode == CMD_WITHOUT and c.gestures)):
				continue
			rowsData.append((c, n))
		rowsData.sort(key=lambda r: (r[0].addonSummary or "", r[0].category or "", r[0].name.lower()))
		rows = []
		for c, n in rowsData:
			conf = _("Gesture conflict") if c.key in cidx else ""  # details: Enter on the command
			label = _cmdName(c)
			if want in (ALL, ADDONS):
				label = "%s - %s" % (label, c.addonSummary or _("NVDA"))
			rows.append((label, ", ".join(gestureText(g) for g in c.gestures) or _("No gesture"), conf))
		self.cmdRows = rowsData
		# The command itself, or (when it no longer matches the filter) the row that took its place.
		keys = [c.key for c, _n in rowsData]
		sel = keys.index(selectKey) if selectKey in keys else fallbackIndex
		_fill(self.cmdList, rows, _("No commands"), select=sel)

	def _selectedCmd(self):
		i = self.cmdList.GetFirstSelected()
		if i < 0 or i >= len(self.cmdRows):
			ui.message(getattr(self.cmdList, "emptyText", None) if not self.cmdRows else _("No command selected"))
			return None
		return self.cmdRows[i][0]

	def _capturePrompt(self, cmd, old):
		msg = _("Enter the new gesture now, or press Escape to cancel.").format(cmd=cmd.name)
		# Spoken once focus is back in this window, so it is never cut off.
		self._speakAfterFocus(msg)
		self._startCapture(lambda g: self._addCaptured(cmd, g, old))

	def _usedBy(self, gids, cmd):
		"""Other commands that already use one of these identifiers: [(command, layout)]."""
		return [(c, lay) for c, lay in core.commandsForGesture(self.commands, gids) if c.key != cmd.key]

	def _addCaptured(self, cmd, gesture, old=None):
		"""Assign gesture to cmd; with old, replace that shortcut (the old one is removed only once the new one works)."""
		gids = list(gesture.normalizedIdentifiers)
		# Keyboard: the general form (a layout is chosen next). Other devices: the identifier assigned below.
		shown = gids[-1] if _layoutOptions(gids) else gids[0]
		if core.isTypingKey(shown):
			if cmd.level in (0, 3):  # global: the key is taken everywhere
				q = _("{g} is a normal typing key. If it is assigned to a command, it will no longer type in any application. Assign it anyway?")
			else:
				q = _("{g} is a normal typing key. If it is assigned to a command, it will no longer type where this command works. Assign it anyway?")
			answer = _ask(self, q.format(g=gestureText(shown)) + "\n" + _("No: press another key. Cancel: go back."),
				_("Typing key"), cancelIsNone=True)
			if answer is None:
				return
			if not answer:
				self._capturePrompt(cmd, old)  # still waiting for the new shortcut
				return
		if old:
			prompt = _("Replace {old} with {g} for {cmd}?").format(old=gestureText(old), g=gestureText(shown), cmd=cmd.name)
		else:
			prompt = _("Assign {g} to {cmd}?").format(g=gestureText(shown), cmd=cmd.name)
		# Said at once whether the key is free, before any other question.
		users = self._usedBy(gids, cmd)
		if users:
			prompt += "\n" + _("It is already used by {cmds}.").format(cmds="; ".join(_cmdText(c) for c, _l in users))
		else:
			prompt += "\n" + _("It is free.")
		options = _layoutOptions(gids)
		if options:
			# When replacing, the layout of the old shortcut is offered first.
			lays = core.gestureLayouts(old)[0] if old and old.lower().startswith("kb") else set()
			default = 1 if lays == {"desktop"} else 2 if lays == {"laptop"} else 0
			sel = _choose(self, prompt + "\n" + _("Choose where this gesture applies, or Cancel:"),
				_("Keyboard layout"), [label for _g, label in options], default=default)
			if sel is None:
				return
			gid = options[sel][0]
		else:
			gid = gids[0]
			if not _ask(self, prompt, _("Confirm"), yesDefault=True):  # the user just chose this gesture
				return
		if old and gid.lower() == old.lower():
			self._speakAfterFocus(_("{g} is already assigned to this command").format(g=gestureText(gid)))
			return
		rest = [g for g in cmd.gestures if g != old]
		if core.gestureCovered(rest, gid):
			if not old:
				self._speakAfterFocus(_("{g} is already assigned to this command").format(g=gestureText(gid)))
				return
			# The command already has the new shortcut: replacing only means removing the old one.
			if not self._backup(_("removing {g} from {cmd}").format(g=gestureText(old), cmd=cmd.name)):
				return
			try:
				ok = not self._removeVerified([(cmd, old)])
			except Exception:
				log.error("PersonalGestureManager: replace failed", exc_info=True)
				ok = False
				self._reload()
			if ok:
				msg = _("Replaced {old} with {g}").format(old=gestureText(old), g=gestureText(gid))
			else:
				msg = _("Could not remove {g}. Details are in the NVDA log.").format(g=gestureText(old))
			self._afterEdit(cmd.key, msg, ok=ok)
			return
		others = self._usedBy([gid], cmd)
		action = KEEP
		if others:
			action = _askConflict(self, self._conflictQuestion(cmd, gid, others), _("Gesture conflict"))
			if action is None:
				return
			if action == AGAIN:
				self._capturePrompt(cmd, old)
				return
		if old:
			note = _("replacing {old} with {g} for {cmd}").format(old=gestureText(old), g=gestureText(gid), cmd=cmd.name)
		else:
			note = _("adding {g} to {cmd}").format(g=gestureText(gid), cmd=cmd.name)
		if not self._backup(note):
			return
		# NVDA gives a key to only one command of the same group (class): there it is always moved.
		pairs, back = _layoutSplit([o for o, _lay in others if action == MOVE or _sameClass(o, cmd)], gid)
		try:
			msg, ok = self._applyAdd(cmd, gid, old, pairs, back)
		except Exception:
			log.error("PersonalGestureManager: could not apply %s" % gid, exc_info=True)
			self._reload()
			msg, ok = _("Could not fully apply {g} ({cmds}). Details are in the NVDA log.").format(
				g=gestureText(gid), cmds=cmd.name), False
		self._afterEdit(cmd.key, msg, ok=ok)

	def _conflictQuestion(self, cmd, gid, others):
		"""Says plainly what each choice does, and which command will really run if both keep the key."""
		lines = "\n".join("- " + _withLayout(_cmdText(c), gid, lay) for c, lay in others)
		kind, winner = core.classify([cmd] + [c for c, _l in others])
		if kind == "override" and winner is cmd:
			keep = _("Keep on both commands: {cmd} will run; the others will no longer run with this key.").format(
				cmd=cmd.name)
		elif kind == "override":
			keep = _("Keep on both commands: {winner} will still run; {cmd} will not run with this key.").format(
				winner=_cmdText(winner), cmd=cmd.name)
		elif kind == "context":
			keep = _("Keep on both commands: which one runs depends on the focused control.")
		else:
			keep = _("Keep on both commands: only one of them will run, and it cannot be known which.")
		text = _("{g} is already used by:\n{list}\n\nMove it to this command: it is removed from the command(s) above.\n{keep}\nChoose another gesture: enter a different one instead.").format(
			g=gestureText(gid), list=lines, keep=keep)
		same = [c for c, _l in others if _sameClass(c, cmd)]
		if same:
			text += "\n\n" + _("{cmds} and {cmd} are in the same group of commands, where NVDA gives a key to only one "
				"command: if you keep it, it is still moved from {cmds}.").format(
				cmds="; ".join(_cmdText(c) for c in same), cmd=cmd.name)
		if any(c.addon is None for c, _l in others):
			text += "\n\n" + _("Warning: this key belongs to one of NVDA's own commands.")
		return text

	def _reload(self):
		try:
			self.commands = self._collect()
		except Exception:
			log.error("PersonalGestureManager: could not reload commands", exc_info=True)

	def _applyAdd(self, cmd, gid, old, pairs, back=()):
		"""Returns (message, success); on failure every binding is put back.
		back: bindings for the other layout, given back to the commands the key is moved from."""
		snap = snapshotUserGestures()
		addGesture(cmd, gid)
		# One reload of NVDA's mappings covers the add and all removals (reloading is the slow part).
		failed = sorted({c.name for c, _g in self._removeVerified(pairs, keep=cmd)} | set(self._addBack(back)))
		c2 = self._cmdByKey().get(cmd.key)
		if c2 is None or not core.gestureCovered(c2.gestures, gid):
			# The new shortcut did not take effect: put every binding back as it was.
			restoreUserGestures(snap)
			self.commands = self._collect()
			if old:
				return _("Could not assign {g}. {old} was kept. Details are in the NVDA log.").format(
					g=gestureText(gid), old=gestureText(old)), False
			return _("Could not assign {g}. No changes were made. Details are in the NVDA log.").format(
				g=gestureText(gid)), False
		if old and core.gestureCovered([gid], old) and not isUserGesture(c2, old):
			# The old shortcut is a default covered by the new one (e.g. kb(laptop):X -> kb:X): unbinding it
			# would block the new one on that layout, so it is left as it is.
			pass
		elif old:
			# Only now that the new shortcut works is the old one removed, so the command is never left without one.
			if self._removeVerified([(c2, old)]):
				return _("{g} was added, but {old} could not be removed. Details are in the NVDA log.").format(
					g=gestureText(gid), old=gestureText(old)), False
			c3 = self._cmdByKey().get(cmd.key)
			if c3 is None or not core.gestureCovered(c3.gestures, gid):
				failed.append(cmd.name)
		if failed:
			return _("Could not fully apply {g} ({cmds}). Details are in the NVDA log.").format(
				g=gestureText(gid), cmds=", ".join(failed)), False
		if old:
			msg = _("Replaced {old} with {g}").format(old=gestureText(old), g=gestureText(gid))
		elif pairs:
			msg = _("Moved {g} to {cmd}").format(g=gestureText(gid), cmd=cmd.name)
		else:
			msg = _("Added {g}").format(g=gestureText(gid))
		blocked = blockedLayouts(cmd, gid)
		if blocked:
			msg = _("{msg}. It does not work on the {layout} layout, because this key was removed there from "
				"another command of the same group.").format(msg=msg, layout=", ".join(LAYOUT_LABELS[b] for b in blocked))
		return msg, True

	def _addBack(self, back):
		"""Bind (command, gesture) pairs again after a removal. Returns the names of the commands where it failed."""
		if not back:
			return []
		byKey = self._cmdByKey()
		# A layout already given to another command of the same group never ran this one: nothing to give back.
		back = [(c, g) for c, g in back if not takenInClass(c, g)]
		if not back:
			return []
		for c, g in back:
			addGesture(byKey.get(c.key, c), g, save=False)
		saveUserGestures()
		self.commands = self._collect()
		byKey = self._cmdByKey()
		return [c.name for c, g in back if c.key not in byKey or not core.gestureCovered(byKey[c.key].gestures, g)]

	def _stillBound(self, pairs):
		byKey = self._cmdByKey()
		return [(byKey[c.key], g) for c, g in pairs if c.key in byKey and g in byKey[c.key].gestures]

	def _removeVerified(self, pairs, keep=None):
		"""Remove each (command, gesture), reload once and verify; defaults still active are unbound explicitly.
		keep: the command receiving the shortcut. Returns the pairs that could not be removed."""
		before = {c.key: set(c.gestures) for c in self.commands}
		removed = {g for _c, g in pairs}
		spare = keep.scriptName if keep is not None else None
		for c, g in pairs:
			removeGesture(c, g, spare if keep is not None and _sameClass(c, keep) else None)
		self.commands = self._collect()
		left = self._stillBound(pairs)
		# The removed key must not pass to another command of the same class: remove it there too.
		took = [(c, g) for c in self.commands for g in c.gestures
			if (keep is None or c.key != keep.key) and g in removed and g not in before.get(c.key, ())
			and any(_sameClass(c, p) for p, _g in pairs)]
		for c, g in took:
			removeGesture(c, g)
		if took:
			self.commands = self._collect()
		left = self._stillBound(left + took)
		if left:
			for c, g in left:
				unbindGesture(c, g)
			self.commands = self._collect()
			left = self._stillBound(left)
		return left

	def onRemove(self, evt):
		cmd = self._selectedCmd()
		if not cmd:
			return
		if not cmd.gestures:
			self._speakAfterFocus(_("This command has no gesture"))
			return
		if len(cmd.gestures) == 1:
			sel = 0 if _ask(self, _("Remove {g} from {cmd}?").format(g=_gestureLong(cmd.gestures[0]), cmd=cmd.name),
				_("Remove gesture")) else None
		else:
			sel = _choose(self, _("Gesture to remove from {cmd}:").format(cmd=cmd.name),
				_("Remove gesture"), [_gestureLong(g) for g in cmd.gestures])
		if sel is None:
			return
		self._removeGesture(cmd, cmd.gestures[sel])

	def _removeGesture(self, cmd, gid):
		if not self._backup(_("removing {g} from {cmd}").format(g=gestureText(gid), cmd=cmd.name)):
			return
		try:
			ok = not self._removeVerified([(cmd, gid)])
		except Exception:
			log.error("PersonalGestureManager: could not remove %s" % gid, exc_info=True)
			self._reload()
			ok = False
		if ok:
			msg = _("Removed {g}").format(g=gestureText(gid))
		else:
			msg = _("Could not remove {g}. Details are in the NVDA log.").format(g=gestureText(gid))
		self._afterEdit(cmd.key, msg, ok=ok)

	def _backup(self, note=None):
		"""note: the change about to be made, shown with the backup in Backups."""
		try:
			self.plugin.ensureBackup(note)
			return True
		except Exception:
			log.error("PersonalGestureManager: backup failed", exc_info=True)
			return _ask(self, _("Could not back up gestures.ini. Continue without a backup?"), _("Backup failed"))

	def onBackups(self, evt):
		baks = core.listBackups(backupDir())
		if not baks:
			ui.message(_("No backups yet. A backup is made automatically before every change."))
			return
		labels = []
		for b in baks:
			note = core.backupNote(b)
			labels.append(_("{date}, before {change}").format(date=core.backupLabel(b), change=note) if note
				else core.backupLabel(b))
		choices = list(zip(baks, labels))
		# The newest backup differing from the current file is offered first, as "undo".
		last = next((b for b in baks if not core.sameAsCurrent(b, gesturesPath())), None)
		if last is not None:
			note = core.backupNote(last)
			undo = _("Undo the last change: {change}").format(change=note) if note else _("Undo the last change")
			choices.insert(0, (last, undo))
		sel = _choose(self, _("Choose a backup of your gestures to restore (newest first):"),
			_("Restore gestures"), [t for _b, t in choices])
		if sel is None:
			return
		bak, label = choices[sel]
		if not _ask(self, _("Restore gestures from {date}? This replaces all your own gestures, including changes made in NVDA's Input gestures dialog. Your current gestures are backed up first, so this can be undone too.").format(date=core.backupLabel(bak)), _("Confirm")):
			return
		try:
			data = core.readBackup(bak)  # read first: backing up the current file may drop the oldest backup
		except OSError:
			log.error("PersonalGestureManager: could not read %s" % bak, exc_info=True)
			self._afterEdit(None, _("Could not restore the backup. Details are in the NVDA log."))
			return
		if not self._backup(_("restoring the backup of {date}").format(date=core.backupLabel(bak))):
			return
		try:
			core.restoreBackup(data, gesturesPath())
			reloadUserGestures()
			msg = _("Gestures restored")
		except Exception:
			log.error("PersonalGestureManager: restore failed", exc_info=True)
			msg = _("Could not restore the backup. Details are in the NVDA log.")
		self.commands = self._collect()
		self._returnTo = None  # a restore changes everything: stay here
		self._afterEdit(None, msg)

	def _afterEdit(self, key, msg, ok=False):
		"""self.commands is already reloaded; refresh every view from it.
		A change started in the Conflicts tab ends there, in the list, whether it worked or not."""
		back = self._returnTo if self._returnTo and self._returnTo[3] == key else None
		i = self.cmdList.GetFirstSelected()
		if key is None and 0 <= i < len(self.cmdRows):
			key = self.cmdRows[i][0].key
		self.refreshAll(selectKey=key, fallbackIndex=max(i, 0))
		if back is None:
			self.cmdList.SetFocus()
			# A question window has just closed: spoken once NVDA's focus is on the list, or it is cut off.
			self._speakAfterFocus(msg, "cmdList")
			return
		self._returnTo = None
		self._ensure(PAGE_CONFLICTS)  # rebuilt now, so the count below is current
		self._selectConflict(*back)
		msg = self._remainingText(msg)
		self._restoreCmdFilters()
		# Go back first; the result is spoken after NVDA has read the focused item, so it is not cut off.
		getattr(self.book, "ChangeSelection", self.book.SetSelection)(PAGE_CONFLICTS)
		self.confList.SetFocus()
		self._speakAfterFocus(msg, "confList")

	def _restoreCmdFilters(self):
		"""Give the Commands tab back the filters the user had before being taken to a command."""
		saved, self._savedCmdFilters = self._savedCmdFilters, None
		if not saved:
			return
		addon, mode = saved
		keys = [k for k, _t in getattr(self.cmdAddon, "items", [])]
		if addon in keys:
			self.cmdAddon.SetSelection(keys.index(addon))
		if 0 <= mode < self.cmdFilter.GetCount():
			self.cmdFilter.SetSelection(mode)
		self.refreshCommands(selectKey=self._selectedKey(self.cmdList, [c.key for c, _n in self.cmdRows]))

	def _selectConflict(self, index, gesture, layout, key=None):
		"""Select the row of this key, or the row that took its place once the conflict is resolved."""
		ids = [self._confId(r) for r in self.confRows]
		i = ids.index((gesture, layout)) if (gesture, layout) in ids else min(index, len(ids) - 1)
		if i >= 0:
			self.confList.Select(i)
			self.confList.Focus(i)

	def _speakAfterFocus(self, msg, target=None, tries=40):
		"""Speak msg once NVDA's focus is in the control named `target` (or anywhere in this window).
		Checked every 50 ms, for at most 2 s."""
		if self._closed:
			return
		try:
			win = getattr(self, target) if isinstance(target, str) else (target or self)
			want = win.GetHandle()
		except RuntimeError:  # dialog destroyed
			return
		try:
			import api
			import queueHandler
			obj = api.getFocusObject()
			hwnd = getattr(obj, "windowHandle", None)
			if not target and hwnd:
				import winUser
				hwnd = winUser.getAncestor(hwnd, winUser.GA_ROOT)  # the top-level window
			ready = hwnd == want
		except Exception:  # NVDA internals unavailable: just speak
			msg() if callable(msg) else ui.message(msg)
			return
		if ready or tries <= 0:
			# Queued behind the focus event, so it never interrupts NVDA reading the focused item.
			if callable(msg):
				queueHandler.queueFunction(queueHandler.eventQueue, msg)
			else:
				queueHandler.queueFunction(queueHandler.eventQueue, ui.message, msg)
			return
		wx.CallLater(50, self._speakAfterFocus, msg, target, tries - 1)

	# ---------- page: conflicts ----------
	# One row per shared key; Enter chooses a command, then removes the key or changes its shortcut.
	def _buildConflicts(self):
		self._building = PAGE_CONFLICTS
		p = wx.Panel(self.book)
		h = guiHelper.BoxSizerHelper(p, orientation=wx.VERTICAL)
		self.confShow = self._labeled(h, N_("&Filter type"), wx.Choice,
			choices=[KIND_LABELS[k] for k in CONF_KINDS])
		self.confShow.optionIds = [dict.__getitem__(KIND_LABELS, k) for k in CONF_KINDS]
		self.confShow.SetSelection(0)  # conflicts: the ones to resolve, and the number announced on arrival
		self.coreConf = h.addItem(self._reg(wx.CheckBox(p, label=_("&Include overlaps between NVDA's own commands")),
			"&Include overlaps between NVDA's own commands", "check"))
		self.confList = self._list(h, N_("&Shared gestures"),
			((N_("Gesture"), 200), (N_("Layout"), 150), (N_("Shared by"), 150)))
		self.confShow.Bind(wx.EVT_CHOICE, lambda e: self.refreshConflicts())
		self.coreConf.Bind(wx.EVT_CHECKBOX, lambda e: self.refreshConflicts())
		self.confList.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.onConflictActivate)
		self.confList.Bind(wx.EVT_CONTEXT_MENU, self.onConflictActivate)
		self.confList.Bind(wx.EVT_KEY_DOWN, self.onConflictKey)
		p.SetSizer(h.sizer)
		return p

	@staticmethod
	def _confId(cf):
		return (cf.gesture, cf.layout)

	@_safe("confList", "confRows")
	def refreshConflicts(self, select=None):
		"""select: (gesture, layout, ...) of the row to select; by default the selected row stays."""
		pending = self._pending.pop("conf", None)  # used once, never later
		select = select or pending
		if select is None:
			select = self._selectedKey(self.confList, [self._confId(r) for r in self.confRows])
		rows, data = [], []
		kind = CONF_KINDS[max(self.confShow.GetSelection(), 0)]
		for cf in self.conflicts:
			if not self.coreConf.GetValue() and all(c.addon is None for c in cf.commands):
				continue
			if cf.kind != kind:
				continue
			data.append(cf)
			rows.append((gestureText(cf.gesture), _layoutText(cf.gesture, cf.layout),
				_("{n} commands").format(n=len(cf.commands))))
		self.confRows = data
		ids = [self._confId(r) for r in data]
		want = tuple(select[:2]) if select else None
		_fill(self.confList, rows, _("No conflicts"), select=ids.index(want) if want in ids else 0)

	def _selectedConflict(self):
		i = self.confList.GetFirstSelected()
		if not 0 <= i < len(self.confRows):
			return None, None
		return i, self.confRows[i]

	def _chooseConflictCommand(self, cf):
		"""The command, among those sharing the key, to act on; None if cancelled."""
		byKey = self._cmdByKey()
		cmds = [byKey.get(c.key, c) for c in cf.commands]
		g = _withLayout(gestureText(cf.gesture), cf.gesture, cf.layout)
		sel = _choose(self, _("{g} is used by {n} commands. Choose a command:").format(g=g, n=len(cmds)),
			_("Gesture conflict"), [_cmdText(c, cf.active) for c in cmds])
		return None if sel is None else cmds[sel]

	def onConflictActivate(self, evt):
		"""Enter (or the Applications key) on a key: which command, then remove the key or change the shortcut."""
		i, cf = self._selectedConflict()
		if cf is None:
			self._speakEmpty(self.confList)
			return
		c = self._chooseConflictCommand(cf)
		if c is None:
			return
		g = gestureText(cf.gesture)
		acts = ["change", "remove"]
		if len(cf.commands) > 2:  # with two, removing the key from one already leaves it to the other
			acts.insert(0, "only")
		labels = {"only": _("Only this command uses {g} (it is removed from the others)").format(g=g),
			"change": _("Change the gesture of this command..."),
			"remove": _("Remove {g} from this command").format(g=g)}
		sel = _choose(self, _("{g}, {cmd}:").format(g=g, cmd=_cmdText(c)), _("Gesture conflict"),
			[labels[a] for a in acts])
		act = None if sel is None else acts[sel]
		if act == "only":
			others = [o for o in cf.commands if o.key != c.key]
			self._removeFromConflict(i, cf, [self._cmdByKey().get(o.key, o) for o in others])
		elif act == "change":
			old = core.overlapping(c.gestures, cf.gesture)
			if not old:
				return
			# Captured here, without leaving the tab; the result is spoken back in this list.
			self._returnTo = (i, cf.gesture, cf.layout, c.key)
			self._capturePrompt(c, old[0])
		elif act == "remove":
			self._removeFromConflict(i, cf, [c])

	def onConflictKey(self, evt):
		if evt.GetKeyCode() == wx.WXK_DELETE and not evt.HasAnyModifiers():
			i, cf = self._selectedConflict()
			c = cf is not None and self._chooseConflictCommand(cf)
			if c:
				self._removeFromConflict(i, cf, [c])
		elif not (evt.GetKeyCode() in _NAV_KEYS() and self._speakEmpty(self.confList)):
			evt.Skip()

	@staticmethod
	def _speakEmpty(lc):
		"""In an empty list, moving or pressing Enter says why it is empty (there is no row to read)."""
		if lc.GetItemCount() or not getattr(lc, "emptyText", None):
			return False
		ui.message(lc.emptyText)
		return True

	def _removeFromConflict(self, index, cf, cmds):
		"""Remove the shared key from these commands without leaving the Conflicts tab."""
		g = gestureText(cf.gesture)
		names = ", ".join(c.name for c in cmds)
		if not cmds or not self._backup(_("removing {g} from {cmd}").format(g=g, cmd=names)):
			return
		pairs, back = _layoutSplit(cmds, _conflictTarget(cf))
		try:
			ok = not self._removeVerified(pairs)
			ok = not self._addBack(back) and ok
		except Exception:
			log.error("PersonalGestureManager: could not remove %s" % cf.gesture, exc_info=True)
			self._reload()
			ok = False
		if not ok:
			msg = _("Could not remove {g}. Details are in the NVDA log.").format(g=g)
		elif back:
			msg = _("Removed {g} from {cmd}, on the {layout} layout only").format(
				g=g, cmd=", ".join(c.name for c in cmds), layout=LAYOUT_LABELS[cf.layout])
		elif len(cmds) == 1:
			msg = _("Removed {g} from {cmd}").format(g=g, cmd=cmds[0].name)
		else:
			msg = _("Removed {g} from {n} commands").format(g=g, n=len(cmds))
		self.refreshAll()
		self._ensure(PAGE_CONFLICTS)
		self._selectConflict(index, cf.gesture, cf.layout)
		self.confList.SetFocus()
		self._speakAfterFocus(self._remainingText(msg), "confList")

	def _remainingText(self, msg):
		n = len(self.confRows)  # one row per shared key
		if not n:
			return _("{msg}. No conflicts remaining").format(msg=msg)
		if n == 1:
			return _("{msg}. 1 conflict remaining").format(msg=msg)
		return _("{msg}. {n} conflicts remaining").format(msg=msg, n=n)

	# ---------- page: statistics ----------
	def _buildStats(self):
		self._building = PAGE_STATS
		p = wx.Panel(self.book)
		h = guiHelper.BoxSizerHelper(p, orientation=wx.VERTICAL)
		setting = getattr(self.plugin, "getSetting", lambda k, d=None: d)
		self.period = self._labeled(h, N_("&Period"), wx.Choice, choices=[])
		self.period.pendingKey = setting("statsPeriod", "week")
		self.statsAddon = self._labeled(h, N_("&Add-on"), wx.Choice, choices=[])
		self.statsAddon.pendingKey = setting("statsAddon", ADDONS)
		self.statsShow = self._labeled(h, N_("&Filter type"), wx.Choice, choices=[_(t) for t in STATS_FILTERS])
		self.statsShow.optionIds = STATS_FILTERS
		self.statsShow.SetSelection(STATS_SHOW.index(setting("statsShow", "most")) if setting("statsShow", "most")
			in STATS_SHOW else 0)
		# Name and number of uses first: they are what is read first in each row.
		self.statsList = self._list(h, N_("Commands by &use"),
			((N_("Command"), 280), (N_("Uses"), 90), (N_("Gestures"), 170), (N_("Add-on"), 170)))
		self.statsInfo = self._labeled(h, N_("Su&mmary"), wx.TextCtrl, style=wx.TE_READONLY)
		reset = h.addItem(self._reg(wx.Button(p, label=_("&Delete all statistics...")), "&Delete all statistics...", "button"))
		self.period.Bind(wx.EVT_CHOICE, lambda e: self._statsChoice())
		self.statsAddon.Bind(wx.EVT_CHOICE, lambda e: self._statsChoice())
		self.statsShow.Bind(wx.EVT_CHOICE, lambda e: self._statsChoice())
		self.statsList.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.onStatsActivate)
		reset.Bind(wx.EVT_BUTTON, self.onReset)
		p.SetSizer(h.sizer)
		return p

	def _statsChoice(self):
		"""A choice of the Statistics tab changed: show it and remember it for next time."""
		self.refreshStats()
		save = getattr(self.plugin, "setSetting", None)
		if not save:
			return
		save("statsPeriod", self._choiceKey(self.period))
		save("statsAddon", self._choiceKey(self.statsAddon))
		save("statsShow", STATS_SHOW[self.statsShow.GetSelection()])

	@_safe("statsList", "statsKeys")
	def refreshStats(self, selectKey=None):
		pending = self._pending.pop("stats", None)  # used once, never later
		selectKey = selectKey or pending
		items = [(k, _(t)) for k, t in PERIOD_LABELS]
		keep = (self.period.items[self.period.GetSelection()][0] if getattr(self.period, "items", None)
			else getattr(self.period, "pendingKey", "week"))
		if keep not in [k for k, _t in items]:
			keep = "week"
		self._setChoice(self.period, items, keep)
		period = self.period.items[self.period.GetSelection()][0]
		periodName = self.period.items[self.period.GetSelection()][1]
		least = self.statsShow.GetSelection() == 1
		if self.statsShow.GetSelection() == 2:
			return self._fillUnused(period, periodName, selectKey)
		counts = self.stats.counts(period)
		self._setChoice(self.statsAddon, self._addonChoices(counts), self._choiceKey(self.statsAddon), fallback=ADDONS)
		want = self._choiceKey(self.statsAddon)
		byKey = self._cmdByKey()
		addonNames = {c.addon: c.addonSummary for c in self.commands if c.addon}
		data = []
		total = 0
		hidden = 0
		for k, n in counts.items():
			c = byKey.get(k)
			if least and not (c and c.gestures):
				hidden += 1  # least used: only commands whose shortcut could be given to another command
				continue
			if c:
				name, addon, summary = c.name, c.addon, c.addonSummary
				keys = ", ".join(gestureText(g) for g in c.gestures)
			else:  # not available here (other application, add-on not running): from what was recorded
				m = self.stats.meta(k) or [k, None, None]
				name, addon, keys = m[0], m[1], _("No gesture")
				summary = addonNames.get(addon, addon)
			if not _match(want, addon):
				continue
			total += n
			data.append((n, name, keys, summary or _("NVDA"), k))
		data.sort(key=lambda r: ((r[0] if least else -r[0]), r[1].lower()))
		self.statsKeys = [r[4] for r in data]
		_fill(self.statsList, [(name, _timesText(n), keys, s) for n, name, keys, s, _k in data],
			_("No commands with a gesture were used in this period") if least and hidden
			else _("No usage recorded yet for this selection"),
			select=self.statsKeys.index(selectKey) if selectKey in self.statsKeys else 0)
		since = time.strftime("%Y-%m-%d", time.localtime(self.stats.since()))
		if not total and least and hidden:
			info = _("{period}: no command with a gesture was used. Recording since {date}.").format(
				period=periodName, date=since)
		elif not total:
			info = _("{period}: no uses recorded. Recording since {date}.").format(period=periodName, date=since)
		elif total == 1:
			info = _("{period}: 1 use of 1 command. Recording since {date}.").format(period=periodName, date=since)
		elif len(data) == 1:
			info = _("{period}: {total} uses of 1 command. Recording since {date}.").format(
				period=periodName, total=total, date=since)
		else:
			info = _("{period}: {total} uses of {cmds} commands. Recording since {date}.").format(
				period=periodName, total=total, cmds=len(data), date=since)
		self.statsInfo.SetValue(info)

	def _fillUnused(self, period, periodName, selectKey):
		"""Commands that have a shortcut but were not used in the period: shortcuts that could be freed."""
		counts = self.stats.counts(period)
		self._setChoice(self.statsAddon, self._addonChoices(counts), self._choiceKey(self.statsAddon), fallback=ADDONS)
		want = self._choiceKey(self.statsAddon)
		data = sorted((c for c in self.commands if c.gestures and not counts.get(c.key) and _match(want, c.addon)),
			key=lambda c: ((c.addonSummary or "").lower(), c.name.lower()))
		self.statsKeys = [c.key for c in data]
		_fill(self.statsList, [(c.name, _("Not used"), ", ".join(gestureText(g) for g in c.gestures),
			c.addonSummary or _("NVDA")) for c in data], _("Every gesture was used in this period"),
			select=self.statsKeys.index(selectKey) if selectKey in self.statsKeys else 0)
		since = self._sinceText()
		if len(data) == 1:
			info = _("{period}: 1 command with a gesture was not used. Recording since {date}.")
		else:
			info = _("{period}: {n} commands with a gesture were not used. Recording since {date}.")
		self.statsInfo.SetValue(info.format(period=periodName, n=len(data), date=since))

	def onStatsActivate(self, evt):
		i = self.statsList.GetFirstSelected()
		if 0 <= i < len(self.statsKeys):
			self.goToCommand(self.statsKeys[i])

	def onReset(self, evt):
		if self.stats.readOnly:
			ui.message(_("The statistics file could not be read when NVDA started, so it cannot be changed now. "
				"Restart NVDA and try again."))
			return
		if _ask(self, _("Delete all usage statistics? This cannot be undone."), _("Confirm")):
			self.stats.reset()
			msg = _("All statistics deleted")
			try:
				self.stats.save(force=True)
			except Exception:
				log.error("PersonalGestureManager: save failed", exc_info=True)
				msg = _("Statistics deleted, but the file could not be saved. Details are in the NVDA log.")
			self.refreshStats()
			self.refreshCommands(selectKey=self._selectedKey(self.cmdList, [c.key for c, _n in self.cmdRows]))
			self._speakAfterFocus(msg)  # the question window has just closed

	# ---------- page: tester ----------
	def _buildTester(self):
		self._building = PAGE_TESTER
		p = wx.Panel(self.book)
		h = guiHelper.BoxSizerHelper(p, orientation=wx.VERTICAL)
		self.testBtn = h.addItem(self._reg(wx.Button(p, label=_("&Start testing gestures")), "&Start testing gestures", "button"))
		# Every result since NVDA started, newest first: kept by the plugin, so closing the window keeps it.
		if getattr(self.plugin, "testLog", None) is None:
			self.plugin.testLog = []
		self.testResult = self._labeled(h, N_("Test &results"), wx.TextCtrl,
			style=wx.TE_MULTILINE | wx.TE_READONLY, size=(600, 200), value="\n\n".join(self.plugin.testLog))
		self.testBtn.Bind(wx.EVT_BUTTON, self.onTest)
		p.SetSizer(h.sizer)
		return p

	def copyDetails(self):
		"""NVDA+T three times: the details to the clipboard, for a message asking for help.
		They include the computer name and the Windows user's folder."""
		text = "\n".join(self.detailLines())
		try:
			import api
			ok = api.copyToClip(text)
		except Exception:
			ok = False
		ui.message(_("Details copied") if ok is not False else _("Could not copy the details"))

	def onTest(self, evt, afterFocus=False):
		msg = _("Testing. Press a key or perform a gesture to hear what it does; it will not run. Escape stops.").format(app=self.env["app"])
		if afterFocus:  # focus is moving to this tab: spoken once it is there, or it is cut off
			self._speakAfterFocus(msg, "testBtn")
		else:
			ui.message(msg)
		self._lastTested = None
		self._startCapture(self._testCaptured, continuous=True)

	def _testCaptured(self, gesture):
		gids = list(gesture.normalizedIdentifiers)
		name = gestureText(gids[-1])
		hits = core.commandsForGesture(self.commands, gids)
		if not hits:
			text = _("{g} is free: not assigned to any command.").format(g=name)
		else:
			# Only commands valid in the current keyboard layout can really collide.
			live = [c for c, lay in hits if lay in ("both", self.env["layout"])]
			kind, active = core.classify(live) if len(live) > 1 else ("", None)
			lines = ["- " + _withLayout(_cmdText(c, active), gids[-1], lay) for c, lay in hits]
			head = (_("{g} is assigned to 1 command:").format(g=name) if len(hits) == 1
				else _("{g} is assigned to {n} commands:").format(g=name, n=len(hits)))
			text = head + "\n" + "\n".join(lines)
			if kind == "conflict":
				text += "\n" + _("Warning: conflict. These commands have the same priority, only one works.")
			elif kind == "override":
				text += "\n" + _("Only the command marked (runs now) works; the others do not run.")
			elif kind == "context":
				text += "\n" + _("Which command runs depends on the focused control.")
		self.plugin.testLog.insert(0, _("In {app}:").format(app=self.env["app"]) + "\n" + text)
		del self.plugin.testLog[TEST_LOG_MAX:]
		self.testResult.SetValue("\n\n".join(self.plugin.testLog))
		_interrupt()  # each key pressed replaces the previous result, as NVDA does for other keys
		ui.message(text)

	# ---------- page: guides for NVDA and add-ons ----------
	def _buildGuides(self):
		self._building = PAGE_GUIDES
		p = wx.Panel(self.book)
		h = guiHelper.BoxSizerHelper(p, orientation=wx.VERTICAL)
		self.guideList = self._list(h, N_("&Add-ons and NVDA"),
			((N_("Name"), 260), (N_("Status"), 110), (N_("Description"), 380)))
		bh = guiHelper.ButtonHelper(wx.HORIZONTAL)
		quick = self._reg(bh.addButton(p, label=_("&Quick guide")), "&Quick guide", "button")
		full = self._reg(bh.addButton(p, label=_("Open full &guide")), "Open full &guide", "button")
		h.addItem(bh)
		self.guideList.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.onGuideActivate)
		quick.Bind(wx.EVT_BUTTON, self.onQuickGuide)
		full.Bind(wx.EVT_BUTTON, self.onFullGuide)
		p.SetSizer(h.sizer)
		return p

	def _guideEntries(self):
		if self._guideSource is None:
			names = {"userGuide": _("NVDA User Guide"), "keyCommands": _("NVDA Commands Quick Reference")}
			descs = {"userGuide": _("Complete manual of NVDA."), "keyCommands": _("All NVDA keyboard commands on one page.")}
			entries = [{"nvda": True, "name": "nvda:" + k, "summary": names[k], "description": descs[k], "docs": docs,
				"status": ""}
				for k, docs in nvdaGuides()]
			for a in listAddonGuides():
				a = dict(a, nvda=False)
				a["status"] = _("Disabled") if a["disabled"] else (_("Running") if a["running"] else _("Not running"))
				entries.append(a)
			self._guideSource = entries
		return self._guideSource

	@_safe("guideList", "guideRows")
	def refreshGuides(self, selectName=None):
		self._guidesBuilt = True
		rows = list(self._guideEntries())
		pending = self._pending.pop("guide", None)  # used once, never later
		selectName = selectName or pending
		if selectName is None:
			old = self._selectedGuide() if self.guideRows else None
			selectName = old and (old.get("name") or old["summary"])
		self.guideRows = rows
		idx = next((j for j, e in enumerate(rows) if (e.get("name") or e["summary"]) == selectName), 0) \
			if selectName else 0
		# The row ends with what Enter does, so the user knows it without looking it up.
		_fill(self.guideList, [(e["summary"], e["status"], "%s %s" % (_firstSentence(e["description"]),
			_("Press Enter to open it.") if e["nvda"] else _("Press Enter to read the quick guide.")))
			for e in rows], _("No add-ons found"), select=idx)

	def _selectedGuide(self):
		i = self.guideList.GetFirstSelected()
		return self.guideRows[i] if 0 <= i < len(self.guideRows) else None

	def _guideLanguages(self, e):
		"""Languages of the full guide, NVDA's language first."""
		order = _preferredLanguages(currentLanguage())
		return sorted(e["docs"], key=lambda l: (order.index(l) if l in order else len(order), languageName(l).lower()))

	def onGuideActivate(self, evt):
		e = self._selectedGuide()
		if e and e["nvda"]:
			self.onFullGuide(None)  # NVDA's own guides are opened directly
		else:
			self.onQuickGuide(None)

	def onQuickGuide(self, evt):
		e = self._selectedGuide()
		if not e:
			ui.message(_("No add-on selected"))
			return
		if e["nvda"]:
			self.onFullGuide(None)
			return
		showHtml(self.quickGuideHtml(e), _("Quick guide: {name}").format(name=e["summary"]))

	def onFullGuide(self, evt):
		e = self._selectedGuide()
		if not e:
			ui.message(_("No add-on selected"))
			return
		langs = self._guideLanguages(e)
		if not langs:
			ui.message(_("{name} has no full guide").format(name=e["summary"]))
			return
		lang = langs[0]
		if len(langs) > 1:  # the language is asked only now, when there is a choice to make
			sel = _choose(self, _("Language of the full guide of {name}:").format(name=e["summary"]),
				_("Open full guide"), [languageName(l) for l in langs])
			if sel is None:
				return
			lang = langs[sel]
		try:
			openFile(e["docs"][lang])
		except Exception:
			log.error("PersonalGestureManager: could not open guide", exc_info=True)
			ui.message(_("The guide could not be opened. Details are in the NVDA log."))

	def quickGuideHtml(self, e):
		"""Short guide built from the add-on's own description and its live list of commands."""
		esc = _html
		cmds = [c for c in self.commands if c.addon == e["name"]]
		out = ["<h1>%s</h1>" % esc(e["summary"])]
		out.append("<p>%s</p>" % esc(e["description"] or _("The developer did not provide a description.")))
		out.append("<h2>%s</h2>" % esc(_("Commands")))
		if e["disabled"] or not e["running"]:
			out.append("<p>%s</p>" % esc(_("This add-on is not running, so its commands cannot be listed. "
				"Enable it in the Add-on Store and restart NVDA.")))
		elif not cmds:
			out.append("<p>%s</p>" % esc(_("No commands were found. Some add-ons only add commands inside "
				"particular applications, or work without commands.")))
		else:
			byCat = {}
			for c in cmds:
				byCat.setdefault(c.category or _("Other"), []).append(c)
			for cat in sorted(byCat, key=str.lower):
				out.append("<h3>%s</h3><ul>" % esc(cat))
				for c in sorted(byCat[cat], key=lambda c: (not c.gestures, c.name.lower())):
					keys = ", ".join(gestureText(g) for g in c.gestures) or _("No gesture")
					out.append("<li>%s: %s</li>" % (esc(c.name), esc(keys)))
				out.append("</ul>")
			out.append("<p>%s</p>" % esc(_("App-specific commands are listed for the application that had focus "
				"before opening Personal Gesture Manager.")))
		mine = [cf for cf in self.conflicts if any(c.addon == e["name"] for c in cf.commands)]
		if mine:
			out.append("<h2>%s</h2><ul>" % esc(_("Gesture conflicts")))
			for cf in mine:
				out.append("<li>%s (%s): %s. %s</li>" % (esc(gestureText(cf.gesture)), esc(_layoutText(cf.gesture, cf.layout) or "-"),
					esc(KIND_LONG[cf.kind]), esc("; ".join(_cmdText(c, cf.active) for c in cf.commands))))
			out.append("</ul>")
		out.append("<h2>%s</h2><ul>" % esc(_("About")))
		out.append("<li>%s</li>" % esc(_("Version: {v}").format(v=e["version"] or "?")))
		if e["author"]:
			out.append("<li>%s</li>" % esc(_("Author: {a}").format(a=e["author"])))
		out.append("<li>%s</li></ul>" % esc(_("Status: {s}").format(s=e["status"])))
		return "\n".join(out)

	def onToggleLanguage(self, evt):
		"""Switch Thai/English in place: focus and list selections are kept."""
		lang = nextLanguage(self.plugin.uiLanguage, currentLanguage())
		ui.message(LANGUAGE_CHANGED[lang])
		self.plugin.setUiLanguage(lang)
		setUiLanguage(lang)
		self._stopCapture()
		focused = self.FindFocus() if hasattr(self, "FindFocus") else None
		self.Freeze()
		try:
			self._retranslate()
		finally:
			self.Thaw()
		wx.CallLater(100, self._sayFocus, focused)

	def _retranslate(self):
		self._translateEnv()
		self.SetTitle(self._title())
		for i, title in enumerate(PAGE_TITLES):
			self.book.SetPageText(i, _(title))
		for ctrl, msgid, kind in self._texts:
			ctrl.SetLabel(_(msgid))
		for ctrl, msgid in self._altKeys:
			self._shortcutFor(ctrl, msgid)
		for lc in (self.cmdList, self.confList, self.statsList, self.guideList):
			for i, title in enumerate(lc.colIds):
				_setColumnTitle(lc, i, _(title))
		for choice in (self.cmdFilter, self.confShow, self.statsShow):
			sel = choice.GetSelection()
			choice.SetItems([_(t) for t in choice.optionIds])
			choice.SetSelection(max(sel, 0))
		# Choices with keys (add-ons, periods) are rebuilt by the refresh, keeping the chosen key.
		self._pending = {"stats": self._selectedKey(self.statsList, self.statsKeys),
			"guide": (lambda g: (g.get("name") or g["summary"]) if g else None)(self._selectedGuide())}
		self._guideSource = None  # statuses are translated text
		self._guidesBuilt = False
		cmdKey = self._selectedKey(self.cmdList, [c.key for c, _n in self.cmdRows])
		self.refreshAll(selectKey=cmdKey)

	def _sayFocus(self, focused):
		"""Read the focused control again in the new language (NVDA reads buttons and check boxes itself)."""
		if self._closed or isinstance(focused, (wx.Button, wx.CheckBox)):
			return
		try:
			import api
			import controlTypes
			import queueHandler
			import speech
			queueHandler.queueFunction(queueHandler.eventQueue, speech.speakObject, api.getFocusObject(),
				reason=controlTypes.OutputReason.FOCUS)
		except Exception:
			log.debugWarning("PersonalGestureManager: could not read the focus again", exc_info=True)

	# ---------- gesture capture ----------
	def _startCapture(self, cb, continuous=False):
		self._captureCb = cb
		self._continuous = continuous
		inputCore.manager._captureFunc = self._capture

	def _stopCapture(self):
		if inputCore.manager._captureFunc == self._capture:
			inputCore.manager._captureFunc = None
		self._captureCb = None

	def _capture(self, gesture):
		if gesture.isModifier:
			return False
		cb = self._captureCb
		ids = list(gesture.normalizedIdentifiers)
		# Braille displays and touch screens have no Escape: in the tester, the same gesture twice stops.
		again = (self._continuous and ids and not ids[0].lower().startswith("kb")
			and ids == getattr(self, "_lastTested", None))
		if "kb:escape" in ids or again:
			self._stopCapture()
			if not self._continuous:
				self._returnTo = None  # cancelled: never jump back to Conflicts later
			wx.CallAfter(_interruptAndSay, _("Stopped") if self._continuous else _("Cancelled"))
			return False
		self._lastTested = ids
		if not self._continuous:
			self._stopCapture()
		if cb and not self._closed:
			wx.CallAfter(cb, gesture)
		return False

	def onActivate(self, evt):
		# Never keep swallowing keys after the user leaves this dialog.
		if not evt.GetActive() and self._captureCb is not None:
			self._stopCapture()
		evt.Skip()

	def onClose(self, evt):
		self._closed = True
		self._stopCapture()
		save = getattr(self.plugin, "_autoSave", None)
		if save:  # in the background: closing never waits for the disk
			try:
				save()
			except Exception:
				pass
		self.plugin.dialog = None
		self.Destroy()
