import contextlib
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import hardstage  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = os.path.realpath(self._tmp.name)
        self._env = {k: os.environ.get(k) for k in ("HOME", "HARDSTAGE_CONFIG", "XDG_CONFIG_HOME")}
        os.environ["HOME"] = self.home
        os.environ.pop("HARDSTAGE_CONFIG", None)
        os.environ.pop("XDG_CONFIG_HOME", None)
        self.target = os.path.join(self.home, "Backup")
        self.config = os.path.join(self.home, ".config", "hardstage", "config")

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._tmp.cleanup()

    def write(self, rel, text="x"):
        path = os.path.join(self.home, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(text)
        return path

    def configure(self, *lines):
        self.write(".config/hardstage/config", "\n".join(lines) + "\n")

    def run_hs(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = hardstage.main(list(args))
        self.out, self.err = out.getvalue(), err.getvalue()
        return code

    def staged(self, rel):
        return os.path.join(self.target, rel)

    def assertLinked(self, rel):
        self.assertTrue(os.path.samefile(os.path.join(self.home, rel), self.staged(rel)), rel)

    def assertAbsent(self, rel):
        self.assertFalse(os.path.lexists(self.staged(rel)), rel)


class GlobTests(unittest.TestCase):
    def m(self, pattern, path):
        return hardstage.glob_to_regex(pattern).fullmatch(path) is not None

    def test_globs(self):
        self.assertTrue(self.m("*.txt", "a.txt"))
        self.assertFalse(self.m("*.txt", "d/a.txt"))
        self.assertTrue(self.m("a/**/b", "a/b"))
        self.assertTrue(self.m("a/**/b", "a/x/y/b"))
        self.assertTrue(self.m("**/b", "b"))
        self.assertTrue(self.m("a/**", "a/x/y"))
        self.assertTrue(self.m("f?o", "foo"))
        self.assertTrue(self.m("[!a]x", "bx"))
        self.assertFalse(self.m("[!a]x", "ax"))
        self.assertTrue(self.m(r"\*", "*"))


class SyncTests(Base):
    def test_basic(self):
        self.write(".config/Trolltech.conf")
        self.write("Mail/inbox/1")
        self.write("Mail/inbox/2")
        self.write("other")
        self.configure(".config/Trolltech.conf", "Mail/")
        self.assertEqual(self.run_hs(), 0, self.err)
        self.assertEqual(self.out, "")  # silent on success, for cron
        for rel in (".config/Trolltech.conf", "Mail/inbox/1", "Mail/inbox/2"):
            self.assertLinked(rel)
        self.assertAbsent("other")
        self.assertTrue(os.path.exists(self.staged("README.md")))
        self.assertTrue(os.path.exists(self.staged(".hardstage")))
        self.assertEqual(self.run_hs(), 0, self.err)  # idempotent

    def test_excludes_and_reinclude(self):
        self.write(".mozilla/p/prefs.js")
        self.write(".mozilla/p/cache/junk")
        self.write(".mozilla/p/cache/keep")
        self.write(".mozilla/p/x.tmp")
        self.configure(".mozilla/", "!cache/", "!*.tmp", ".mozilla/p/cache/keep")
        self.assertEqual(self.run_hs(), 0, self.err)
        self.assertLinked(".mozilla/p/prefs.js")
        self.assertLinked(".mozilla/p/cache/keep")
        self.assertAbsent(".mozilla/p/cache/junk")
        self.assertAbsent(".mozilla/p/x.tmp")

    def test_atomic_replace_is_relinked(self):
        path = self.write("doc.txt", "old")
        self.configure("doc.txt")
        self.run_hs()
        tmp = self.write("doc.txt.new", "new")
        os.replace(tmp, path)
        self.assertFalse(os.path.samefile(path, self.staged("doc.txt")))
        self.assertEqual(self.run_hs(), 0, self.err)
        self.assertLinked("doc.txt")
        self.assertEqual([n for n in os.listdir(self.target) if n.endswith(".tmp")], [])

    def test_prune_after_config_change(self):
        self.write("a/1")
        self.write("b/1")
        self.configure("a/", "b/")
        self.run_hs()
        self.configure("a/")
        self.assertEqual(self.run_hs(), 0, self.err)
        self.assertAbsent("b")
        self.assertTrue(os.path.exists(os.path.join(self.home, "b/1")))

    def test_refuses_unmarked_nonempty_target(self):
        os.makedirs(self.target)
        self.write("Backup/precious")
        self.configure("a/")
        self.assertEqual(self.run_hs(), hardstage.EXIT_FATAL)
        self.assertTrue(os.path.exists(self.staged("precious")))

    def test_symlinks_reproduced(self):
        self.write("d/real")
        os.symlink("real", os.path.join(self.home, "d/link"))
        self.configure("d/")
        self.run_hs()
        self.assertEqual(os.readlink(self.staged("d/link")), "real")

    def test_keep(self):
        self.write("a/1")
        self.configure("@keep .stfolder", "a/")
        self.run_hs()
        os.makedirs(self.staged(".stfolder"))
        self.run_hs()
        self.assertTrue(os.path.isdir(self.staged(".stfolder")))

    def test_dry_run(self):
        self.write("a/1")
        self.configure("a/")
        self.assertEqual(self.run_hs("--dry-run"), 0, self.err)
        self.assertFalse(os.path.exists(self.target))
        self.assertIn("link: a/1", self.out)

    def test_glob_over_home_skips_target(self):
        self.write("notes/a.txt")
        self.configure("**/*.txt")
        self.run_hs()
        self.assertEqual(self.run_hs(), 0, self.err)
        self.assertLinked("notes/a.txt")
        self.assertAbsent("Backup")

    def test_dir_becomes_file(self):
        self.write("x/inner")
        self.configure("x")
        self.run_hs()
        os.remove(os.path.join(self.home, "x/inner"))
        os.rmdir(os.path.join(self.home, "x"))
        self.write("x")
        self.assertEqual(self.run_hs(), 0, self.err)
        self.assertLinked("x")

    def test_user_readme_left_alone(self):
        self.write("a/1")
        self.configure("a/")
        self.run_hs()
        with open(self.staged("README.md"), "w") as fh:
            fh.write("mine")
        self.run_hs()
        with open(self.staged("README.md")) as fh:
            self.assertEqual(fh.read(), "mine")

    def test_missing_config(self):
        self.assertEqual(self.run_hs(), hardstage.EXIT_FATAL)
        self.assertIn("hardstage init", self.err)

    def test_init_and_list(self):
        self.assertEqual(self.run_hs("init"), 0)
        self.write("a/1")
        with open(self.config, "a") as fh:
            fh.write("a/\n")
        self.assertEqual(self.run_hs("list"), 0, self.err)
        self.assertEqual(self.out.strip(), "a/1")

    def test_bad_pattern(self):
        self.configure("../etc")
        self.assertEqual(self.run_hs(), hardstage.EXIT_FATAL)


if __name__ == "__main__":
    unittest.main()
