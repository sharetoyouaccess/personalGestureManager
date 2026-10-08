"""installTasks.onUninstall removes this add-on's data, never gestures.ini, and nothing during an update."""
import os, sys, types, tempfile, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..", "addon")


class T(unittest.TestCase):
	def setUp(self):
		self.tmp = tempfile.mkdtemp()
		self.config = os.path.join(self.tmp, "userConfig")
		self.addons = os.path.join(self.config, "addons")
		os.makedirs(os.path.join(self.addons, "personalGestureManager"))
		self.data = os.path.join(self.config, "personalGestureManager")
		os.makedirs(os.path.join(self.data, "backups"))
		for f in ("stats.json", "settings.json", os.path.join("backups", "gestures-1.ini")):
			open(os.path.join(self.data, f), "w").close()
		self.gestures = os.path.join(self.config, "gestures.ini")
		open(self.gestures, "w").write("[globalCommands.GlobalCommands]\n")
		sys.modules["globalVars"] = types.SimpleNamespace(appArgs=types.SimpleNamespace(configPath=self.config))
		sys.modules["addonHandler"] = types.SimpleNamespace(ADDON_PENDINGINSTALL_SUFFIX=".pendingInstall", state={})
		import importlib.util
		spec = importlib.util.spec_from_file_location("installTasks", os.path.join(ROOT, "installTasks.py"))
		self.m = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.m)
		self.m.__file__ = os.path.join(self.addons, "personalGestureManager", "installTasks.py")

	def test_removed_with_the_addon(self):
		self.m.onUninstall()
		self.assertFalse(os.path.exists(self.data))
		self.assertTrue(os.path.isfile(self.gestures))  # the user's gestures stay

	def test_kept_on_update(self):
		os.makedirs(os.path.join(self.addons, "personalGestureManager.pendingInstall"))
		self.m.onUninstall()
		self.assertTrue(os.path.isfile(os.path.join(self.data, "stats.json")))

	def test_kept_when_pending_install_is_recorded(self):
		sys.modules["addonHandler"].state = {"pendingInstallsSet": {"personalGestureManager"}}
		self.m.onUninstall()
		self.assertTrue(os.path.isdir(self.data))

	def test_nothing_to_remove(self):
		import shutil; shutil.rmtree(self.data)
		self.m.onUninstall()  # no error
		self.assertTrue(os.path.isfile(self.gestures))


if __name__ == "__main__":
	unittest.main()
