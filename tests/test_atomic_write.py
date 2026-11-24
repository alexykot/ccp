"""The one atomic write (`lib.write_atomic`, SPEC §23): a temporary name no other writer takes, beside the
file, and no temporary file left behind when the write fails."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from ccp.queue import lib

WRITES = 300  # each writer's writes: enough that two writers with one temporary name collide

# A writer in its own process: the writes through `lib.write_json`, then the count of those that raised.
WRITER = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import lib
failed = 0
for i in range(int(sys.argv[4])):
    try:
        lib.write_json(Path(sys.argv[2]), {"by": sys.argv[3], "i": i})
    except Exception:
        failed += 1
print(failed)
"""


class AtomicWriteTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp(prefix="ccp-atomic-write-"))
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.path = self.dir / "status.json"

    def test_two_concurrent_writers_of_one_file_both_succeed(self) -> None:
        errors: list[BaseException] = []
        start = threading.Barrier(2)

        def writer(tag: str) -> None:
            start.wait()
            for i in range(WRITES):
                try:
                    lib.write_json(self.path, {"by": tag, "i": i})
                except Exception as e:  # noqa: BLE001  (every failure is the finding)
                    errors.append(e)

        threads = [threading.Thread(target=writer, args=(tag,)) for tag in ("a", "b")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertIn(json.loads(self.path.read_text())["by"], ("a", "b"))
        self.assertEqual(sorted(self.dir.iterdir()), [self.path])

        obs = str(Path(lib.__file__).resolve().parent)
        procs = [subprocess.Popen([sys.executable, "-B", "-c", WRITER, obs, str(self.path), tag, str(WRITES)],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for tag in ("c", "d")]
        for p in procs:
            out, err = p.communicate(timeout=120)
            self.assertEqual((p.returncode, out.strip()), (0, "0"), err)
        self.assertIn(json.loads(self.path.read_text())["by"], ("c", "d"))
        self.assertEqual(sorted(self.dir.iterdir()), [self.path])

    def test_a_failed_write_leaves_no_temporary_file(self) -> None:
        (self.path / "sub").mkdir(parents=True)  # the path is a non-empty directory: the replace fails
        before = sorted(self.dir.iterdir())
        with self.assertRaises(OSError):
            lib.write_atomic(self.path, "{}\n")
        self.assertEqual(sorted(self.dir.iterdir()), before)

    def test_each_temporary_name_is_its_own_beside_the_file(self) -> None:
        sources: list[Path] = []
        replace = os.replace

        def recording(src: os.PathLike[str] | str, dst: os.PathLike[str] | str) -> None:
            sources.append(Path(src))
            replace(src, dst)

        with mock.patch.object(lib.os, "replace", side_effect=recording):
            lib.write_atomic(self.path, "one\n")
            lib.write_atomic(self.path, "two\n")
        self.assertEqual(len(sources), 2)
        self.assertNotEqual(sources[0], sources[1])
        for src in sources:
            self.assertEqual(src.parent, self.path.parent)
            self.assertTrue(src.name.startswith("."), src.name)
            self.assertTrue(src.name.endswith(".tmp"), src.name)
        self.assertEqual(self.path.read_text(), "two\n")


if __name__ == "__main__":
    unittest.main()
