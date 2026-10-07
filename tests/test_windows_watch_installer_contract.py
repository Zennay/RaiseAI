import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "install-watch-windows.ps1"


class WindowsWatchInstallerContractTests(unittest.TestCase):
    def setUp(self):
        self.script = SCRIPT.read_text(encoding="utf-8")

    def test_requires_wear_os_before_model_validation(self):
        wear = self.script.index('android.hardware.type.watch')
        model_query = self.script.index('getprop ro.product.model')
        self.assertLess(wear, model_query)

    def test_accepts_only_canonical_galaxy_watch_7_model_aliases(self):
        self.assertIn('$model -ne "SM-L315F" -and $model -ne "SM_L315F"', self.script)
        self.assertIn('Onverwacht Watch-model', self.script)

    def test_model_and_abi_checks_happen_before_install(self):
        model = self.script.index('getprop ro.product.model')
        abi = self.script.index('getprop ro.product.cpu.abi')
        install = self.script.index('adb -s $serial install -r')
        self.assertLess(model, abi)
        self.assertLess(abi, install)


if __name__ == "__main__":
    unittest.main()
