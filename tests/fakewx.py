"""Strict minimal fake of wx + gui.guiHelper: unknown attributes raise, so attribute bugs surface."""
import sys, types

class W:
	def __init__(self, parent=None, *a, **kw):
		self.parent, self.kw, self.handlers = parent, kw, {}
		self.label = kw.get("label", "")
	def Bind(self, evt, handler, *a, **kw): self.handlers[evt] = handler
	def Unbind(self, evt, *a, **kw): self.unbound = getattr(self, "unbound", 0) + 1
	def IsEnabled(self): return True
	def SetFocus(self): FOCUS[0] = self
	def SetSizer(self, s): self.sizer = s
	def SetSize(self, s): pass
	def CentreOnScreen(self): pass
	def SetEscapeId(self, i): pass
	def Show(self): pass
	def Raise(self): pass
	def Destroy(self): self.destroyed = True
	def DestroyChildren(self): self.childrenDestroyed = getattr(self, "childrenDestroyed", 0) + 1
	def SetTitle(self, t): self.title = t
	def Layout(self): pass
	def Close(self):
		h = self.handlers.get(wx.EVT_CLOSE)
		h(None) if h else self.Destroy()
	def PopupMenu(self, m): pass
	def SetAcceleratorTable(self, t): self.accel = [({ACCEL_CTRL: "ctrl", ACCEL_ALT: "alt"}[k], c, i) for k, c, i in t]
	def Hide(self): self.hidden = True
	def GetSizer(self): return self.sizer
	def GetId(self): return id(self)
	def ProcessEvent(self, e):
		h = self.handlers.get(e.kind)
		if h: h(e)
	def SetLabel(self, l): self.label = l
	def GetHandle(self): return id(self)
	def FindFocus(self): return FOCUS[0]
	def SetAccessible(self, a): self.accessible = a
	def Freeze(self): self.frozen = getattr(self, "frozen", 0) + 1
	def Thaw(self): self.frozen -= 1
	def GetPrevSibling(self): return getattr(self, "_prev", None)

class Dialog(W):
	def __init__(self, parent, title=""):
		super().__init__(parent); self.title = title
class Panel(W): pass
class Button(W): pass
class StaticText(W): pass
class Notebook(W):
	def __init__(self, *a, **kw): super().__init__(*a, **kw); self.pages = []; self.sel = 0
	def AddPage(self, p, t): self.pages.append(t)
	def SetPageText(self, i, t): self.pages[i] = t
	def SetSelection(self, i):
		self.sel = i
		h = self.handlers.get(wx.EVT_NOTEBOOK_PAGE_CHANGED)
		if h: h(types.SimpleNamespace(Skip=lambda: None))
	def GetSelection(self): return self.sel
	def ChangeSelection(self, i): self.sel = i
class Choice(W):
	def __init__(self, parent, choices=(), **kw): super().__init__(parent, **kw); self.strings = list(choices); self.sel = -1
	def SetItems(self, items): self.strings = list(items); self.sel = -1
	def SetSelection(self, i): assert 0 <= i < len(self.strings); self.sel = i
	def GetSelection(self): return self.sel
	def GetCount(self): return len(self.strings)
class CheckBox(W):
	value = False
	def GetValue(self): return self.value
	def SetValue(self, v): self.value = v
class TextCtrl(W):
	def __init__(self, parent, value="", **kw): super().__init__(parent, **kw); self.value = value
	def SetValue(self, v): self.value = v
	def ChangeValue(self, v): self.value = v
	def SelectAll(self): self.allSelected = True
	def GetValue(self): return self.value
class ListCtrl(W):
	def __init__(self, *a, **kw): super().__init__(*a, **kw); self.cols = []; self.rows = []; self.sel = -1
	def InsertColumn(self, i, t, width=0): self.cols.append(t)
	def GetColumn(self, i): return _Col(self.cols[i])
	def SetColumn(self, i, c): self.cols[i] = c.text
	def DeleteAllItems(self): self.rows = []; self.sel = -1
	def InsertItem(self, i, t): self.rows.insert(i, [t] + [""] * (len(self.cols) - 1)); return i
	def SetItem(self, i, c, v): self.rows[i][c] = v
	def GetItemCount(self): return len(self.rows)
	def Select(self, i):
		self.sel = i
		h = self.handlers.get(wx.EVT_LIST_ITEM_SELECTED)  # real wx reports programmatic selection too
		if h: h(types.SimpleNamespace(Skip=lambda: None, GetIndex=lambda: i))
	def Focus(self, i): pass
	def GetFirstSelected(self): return self.sel
	def GetFocusedItem(self): return self.sel
	def SetItemState(self, i, state, mask):
		assert 0 <= i, i
		if i == self.sel and not state & LIST_STATE_SELECTED: self.sel = -1
	def SetItemCount(self, n): self.count = n
	def Refresh(self): pass
	@property
	def rows(self): return getattr(self, "_rows", [])
	@rows.setter
	def rows(self, v): self._rows = v
class _Col:
	def __init__(self, t): self.text = t
	def SetText(self, t): self.text = t
LIST_STATE_SELECTED, LIST_STATE_FOCUSED = 2, 1
ACCEL_CTRL = 2
ACCEL_ALT = 1
class CommandEvent:
	def __init__(self, kind, id_): self.kind = kind
	def SetEventObject(self, o): pass
class AcceleratorTable(list): pass
def NewIdRef(): return object()
class Accessible:
	def __init__(self, window): self.window = window
ACC_OK, ACC_NOT_IMPLEMENTED = 0, 1
class Menu:
	def Append(self, i, label): return types.SimpleNamespace(label=label, GetId=lambda: id(label))
	def Destroy(self): pass
class BoxSizer:
	def __init__(self, o): self.items = []
	def Add(self, item, *a, **kw): self.items.append(item)
	def Detach(self, item): self.items.remove(item)

FOCUS = [None]
CALLS = []
def CallAfter(f, *a, **kw): CALLS.append((f, a, kw))
class _Later:
	def __init__(self, f, a, kw): self.entry = (f, a, kw); CALLS.append(self.entry)
	def Stop(self):
		if self.entry in CALLS: CALLS.remove(self.entry)
def CallLater(ms, f, *a, **kw): return _Later(f, a, kw)
def runCalls():
	while CALLS:
		f, a, kw = CALLS.pop(0); f(*a, **kw)

wx = types.ModuleType("wx")
for k, v in dict(Dialog=Dialog, Panel=Panel, Button=Button, StaticText=StaticText, Notebook=Notebook, Choice=Choice,
		CheckBox=CheckBox, TextCtrl=TextCtrl, ListCtrl=ListCtrl, Menu=Menu, BoxSizer=BoxSizer, ACCEL_CTRL=ACCEL_CTRL, ACCEL_ALT=ACCEL_ALT, Accessible=Accessible, ACC_OK=ACC_OK, ACC_NOT_IMPLEMENTED=ACC_NOT_IMPLEMENTED, CommandEvent=CommandEvent, AcceleratorTable=AcceleratorTable, NewIdRef=NewIdRef, CallAfter=CallAfter, CallLater=CallLater, LIST_STATE_SELECTED=LIST_STATE_SELECTED, LIST_STATE_FOCUSED=LIST_STATE_FOCUSED).items():
	setattr(wx, k, v)
for i, k in enumerate(("ID_CLOSE ID_ANY ID_OK ID_YES ID_NO EXPAND ALL ALIGN_RIGHT VERTICAL HORIZONTAL LC_REPORT LC_SINGLE_SEL "
		"TE_READONLY TE_MULTILINE YES_NO NO_DEFAULT ICON_QUESTION ICON_WARNING CANCEL CANCEL_DEFAULT ID_CANCEL WXK_DELETE WXK_F1 WXK_TAB EVT_CHAR_HOOK EVT_CHILD_FOCUS WXK_RETURN WXK_NUMPAD_ENTER EVT_LISTBOX_DCLICK WXK_UP WXK_DOWN WXK_LEFT WXK_RIGHT WXK_HOME WXK_END WXK_PAGEUP WXK_PAGEDOWN EVT_BUTTON EVT_CHOICE EVT_CLOSE EVT_ACTIVATE "
		"EVT_CHECKBOX EVT_KEY_DOWN EVT_CONTEXT_MENU EVT_LIST_ITEM_ACTIVATED EVT_MENU EVT_TEXT EVT_NOTEBOOK_PAGE_CHANGED EVT_LIST_ITEM_SELECTED EVT_SET_FOCUS HELP ID_HELP LC_VIRTUAL YES_DEFAULT").split(), 100):
	setattr(wx, k, i)

wx.wxEVT_BUTTON, wx.wxEVT_CHECKBOX = wx.EVT_BUTTON, wx.EVT_CHECKBOX

class BoxSizerHelper:
	def __init__(self, parent, orientation=None): self.parent = parent; self.sizer = None
	def addLabeledControl(self, label, cls, **kw):
		lbl = StaticText(self.parent, label=label)
		c = cls(self.parent, **kw); c.labelText = label; c._prev = lbl; c.labelCtrl = lbl; return c
	def addItem(self, item, **kw): return item
class ButtonHelper:
	def __init__(self, o): pass
	def addButton(self, parent, label=""): return Button(parent, label=label)
guiHelper = types.ModuleType("gui.guiHelper"); guiHelper.BoxSizerHelper = BoxSizerHelper; guiHelper.ButtonHelper = ButtonHelper

def install():
	sys.modules["wx"] = wx
	gui = sys.modules.get("gui") or types.ModuleType("gui")
	gui.guiHelper = guiHelper
	sys.modules["gui"] = gui; sys.modules["gui.guiHelper"] = guiHelper


def shortcutsViaChoose(mod):
	"""Tests answer the shortcuts window like the flat list it replaced: [change k, remove k, ...] + the buttons."""
	return lambda parent, head, actions, name="": mod._choose(parent, head, "Shortcuts of this command", [a[0] for a in actions])
