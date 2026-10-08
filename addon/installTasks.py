"""On removal, delete this add-on's own data folder (kept on update). gestures.ini is never touched.
"""
import os
import shutil

ADDON_NAME = "personalGestureManager"
DATA_DIR = "personalGestureManager"  # the same name as in globalPlugins/personalGestureManager/__init__.py


def _isUpdate():
	"""A new version of this add-on is waiting to be installed: this removal is part of an update."""
	try:
		import addonHandler
		suffix = getattr(addonHandler, "ADDON_PENDINGINSTALL_SUFFIX", ".pendingInstall")
		addonsDir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
		if os.path.isdir(os.path.join(addonsDir, ADDON_NAME + suffix)):
			return True
		state = getattr(addonHandler, "state", None)
		cat = getattr(getattr(addonHandler, "AddonStateCategory", None), "PENDING_INSTALL", "pendingInstallsSet")
		pending = state.get(cat, ()) if state is not None else ()
		return ADDON_NAME in pending
	except Exception:
		return True  # when in doubt, keep the user's data


def dataPath():
	import globalVars
	config = os.path.abspath(globalVars.appArgs.configPath)
	return config, os.path.join(config, DATA_DIR)


def onUninstall():
	if _isUpdate():
		return
	config, path = dataPath()
	# Only this add-on's own folder, directly inside the configuration folder; never a link to elsewhere.
	if (os.path.dirname(path) != config or os.path.basename(path) != DATA_DIR or not os.path.isdir(path)
			or os.path.islink(path)):
		return
	shutil.rmtree(path, ignore_errors=True)
