import hashlib
import importlib.util
from pathlib import Path
import plistlib
import struct
import tempfile
import unittest
import zipfile


SPEC = importlib.util.spec_from_file_location(
    "validate_repack", Path(__file__).resolve().parents[1] / "scripts/validate_repack.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ArchiveValidationTests(unittest.TestCase):
    def validate(self, arch="arm64", cpu=None, update_version="70300301", digest=None, unsafe=False, executable=True):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / f"AstraGram-v7.3.3.1-macos-{arch}.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("AstraGram.app/Contents/Info.plist", plistlib.dumps({
                    "CFBundleShortVersionString": "7.3.3",
                    "CFBundleVersion": update_version,
                }))
                info = zipfile.ZipInfo("AstraGram.app/Contents/MacOS/AstraGram")
                info.external_attr = (0o100755 if executable else 0o100644) << 16
                cpu = cpu if cpu is not None else {"arm64": 0x100000C, "x64": 0x1000007}[arch]
                archive.writestr(info, struct.pack("<II", 0xFEEDFACF, cpu))
                if unsafe:
                    archive.writestr("../escape", "invalid")
            expected = hashlib.sha256(path.read_bytes()).hexdigest()
            asset = {"name": path.name, "size": path.stat().st_size, "state": "uploaded", "digest": digest or "sha256:" + expected}
            result = MODULE.validate_archive(path, asset, "7.3.3.1", "70300301", "7.3.3", arch)
            self.assertEqual(result, expected)

    def test_accepts_each_architecture(self):
        for arch in ("arm64", "x64"):
            with self.subTest(arch=arch):
                self.validate(arch=arch)

    def test_rejects_other_release_bytes(self):
        with self.assertRaisesRegex(ValueError, "differs"):
            self.validate(digest="sha256:" + "0" * 64)

    def test_rejects_swapped_architecture(self):
        with self.assertRaisesRegex(ValueError, "architecture"):
            self.validate(cpu=0x1000007)

    def test_rejects_wrong_update_version(self):
        with self.assertRaisesRegex(ValueError, "update version"):
            self.validate(update_version="70300300")

    def test_rejects_path_escape(self):
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            self.validate(unsafe=True)

    def test_rejects_missing_executable_mode(self):
        with self.assertRaisesRegex(ValueError, "permission"):
            self.validate(executable=False)


if __name__ == "__main__":
    unittest.main()
