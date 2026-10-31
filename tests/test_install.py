import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SKILL = Path(os.environ.get("CASEWORK_SKILL_ROOT", ROOT / "skills" / "us-immigration-casework"))
spec = importlib.util.spec_from_file_location("installer", ROOT / "scripts" / "install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def test_targets(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {}, clear=True):
            base = Path(temp)
            for target, folder in (("codex", ".agents"), ("claude", ".claude"), ("deepseek", ".dsh")):
                self.assertEqual(installer.destination(target, "user", user_home=base), base / folder / "skills" / installer.NAME)
                self.assertEqual(installer.destination(target, "project", project_root=base), base / folder / "skills" / installer.NAME)

    def test_dsh_home(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"DSH_HOME": temp}):
            self.assertEqual(installer.destination("deepseek", "user"), Path(temp) / "skills" / installer.NAME)

    def test_relative_dsh_home_rejected(self):
        with patch.dict(os.environ, {"DSH_HOME": "relative"}):
            with self.assertRaises(ValueError): installer.destination("deepseek", "user")

    def test_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / "skills" / installer.NAME
            result = installer.install(SKILL, dest, dry_run=True)
            self.assertEqual(result["state"], "planned")
            self.assertFalse(dest.parent.exists())

    def test_copy_matches_and_repeat_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / "skills" / installer.NAME
            self.assertEqual(installer.install(SKILL, dest)["state"], "installed")
            self.assertEqual(installer.fingerprint(dest), installer.fingerprint(SKILL))
            self.assertEqual(installer.install(SKILL, dest)["state"], "unchanged")

    def test_conflicting_install_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / "skills" / installer.NAME
            dest.mkdir(parents=True)
            (dest / "custom.txt").write_text("preserve")
            with self.assertRaises(ValueError): installer.install(SKILL, dest)
            self.assertEqual((dest / "custom.txt").read_text(), "preserve")

    def test_replace_backup_outside_scan(self):
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / "skills" / installer.NAME
            dest.mkdir(parents=True)
            (dest / "custom.txt").write_text("preserve")
            result = installer.install(SKILL, dest, replace=True)
            backup = Path(result["backup"])
            self.assertEqual((backup / "custom.txt").read_text(), "preserve")
            self.assertNotEqual(backup.parent, dest.parent)
            self.assertTrue((dest / "SKILL.md").is_file())

    def test_overlap_rejected(self):
        with self.assertRaises(ValueError): installer.install(SKILL, SKILL / "nested")

    def test_cache_files_not_copied(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            source.mkdir()
            (source / "SKILL.md").write_text("reviewed source")
            cache = source / "__pycache__"
            cache.mkdir()
            (cache / "sample.pyc").write_bytes(b"cache")
            dest = Path(temp) / "skills" / installer.NAME
            installer.install(source, dest)
            self.assertFalse((dest / "__pycache__").exists())

    @unittest.skipUnless(os.name == "posix", "POSIX symlink fixture")
    def test_source_link_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            source.mkdir()
            (source / "SKILL.md").write_text("reviewed source")
            (source / "outside").symlink_to(Path(temp), target_is_directory=True)
            with self.assertRaises(ValueError): installer.install(source, Path(temp) / "dest")

    def test_failed_swap_restores_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / "skills" / installer.NAME
            dest.mkdir(parents=True)
            (dest / "custom.txt").write_text("preserve")
            original = Path.rename
            def fail_staging(path, target):
                if path.parent.name.startswith(".casework-install-"):
                    raise OSError("synthetic failure")
                return original(path, target)
            with patch.object(Path, "rename", fail_staging), self.assertRaises(OSError):
                installer.install(SKILL, dest, replace=True)
            self.assertEqual((dest / "custom.txt").read_text(), "preserve")

    @unittest.skipUnless(os.name == "posix", "POSIX symlink fixture")
    def test_symlink_destination_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            real = Path(temp) / "real"
            real.mkdir()
            link = Path(temp) / "link"
            link.symlink_to(real, target_is_directory=True)
            with self.assertRaises(ValueError): installer.install(SKILL, link / installer.NAME)
            self.assertEqual(list(real.iterdir()), [])


if __name__ == "__main__": unittest.main()
