import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import gha_concurrency_replay as tool


SCRIPT = Path(__file__).resolve().parents[1] / "gha_concurrency_replay.py"
INVALID = "error: invalid input"


class ReplayTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.trace = Path(directory.name) / "trace.json"

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True, text=True, encoding="utf-8", timeout=5,
        )

    def run_trace(self, events, queue="single", cancel=False):
        self.trace.write_text(json.dumps({
            "queue": queue, "cancel_in_progress": cancel, "events": events,
        }), encoding="utf-8")
        return self.cli(str(self.trace))

    def assert_invalid(self, result):
        self.assertEqual((result.returncode, result.stdout, result.stderr.strip()),
                         (2, "", INVALID))

    def assert_replay(self, result, events, running, pending):
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        self.assertEqual(json.loads(result.stdout), {
            "events": events, "running": running, "pending": pending,
        })

    def test_single_replaces_pending_and_promotes_replacement(self):
        self.assert_replay(
            self.run_trace(["arrive", "arrive", "arrive", "finish"]),
            [{"id": 1, "action": "started"},
             {"id": 2, "action": "queued"},
             {"id": 3, "action": "replaced", "replaced_id": 2},
             {"id": 1, "action": "finished", "promoted_id": 3}],
            3, [],
        )

    def test_single_preempts_the_running_id(self):
        self.assert_replay(
            self.run_trace(["arrive", "arrive", "finish", "arrive"], cancel=True),
            [{"id": 1, "action": "started"},
             {"id": 2, "action": "preempted", "cancelled_id": 1},
             {"id": 2, "action": "finished"},
             {"id": 3, "action": "started"}],
            3, [],
        )

    def test_max_preserves_fifo_and_accepts_new_arrival_after_overflow(self):
        result = self.run_trace(["arrive"] * 102 + ["finish", "arrive", "finish"], "max")
        expected = [{"id": 1, "action": "started"}]
        expected.extend({"id": item, "action": "queued"} for item in range(2, 102))
        expected.extend([
            {"id": 102, "action": "rejected"},
            {"id": 1, "action": "finished", "promoted_id": 2},
            {"id": 103, "action": "queued"},
            {"id": 2, "action": "finished", "promoted_id": 3},
        ])
        self.assert_replay(result, expected, 3, [*range(4, 102), 103])

    def test_empty_trace_is_idle(self):
        self.assert_replay(self.run_trace([]), [], None, [])

    def test_idle_finish_rejects_the_entire_trace(self):
        self.assert_invalid(self.run_trace(["arrive", "finish", "finish"]))

    def test_rejects_max_with_cancellation(self):
        self.assert_invalid(self.run_trace([], "max", True))

    def test_rejects_wrong_shape_and_hides_raw_input(self):
        for content in (
            b'{"queue":"single","cancel_in_progress":0,"events":[]}',
            b'{"queue":"single","cancel_in_progress":false,"events":"arrive"}',
            b'{"queue":"single","cancel_in_progress":false,"events":[{}]}',
            b'{"queue":"single","cancel_in_progress":false,"events":["PRIVATE_MARKER"]}',
            b'{"queue":"single","events":[]}',
            b'{"queue":"single","cancel_in_progress":false,"events":[],"PRIVATE_MARKER":true}',
        ):
            with self.subTest(content=content):
                self.trace.write_bytes(content)
                self.assert_invalid(self.cli(str(self.trace)))

    def test_rejects_malformed_json_and_encoding(self):
        for content in (
            b'{"queue":"single","queue":"single","cancel_in_progress":false,"events":[]}',
            b'{"queue":"single","cancel_in_progress":NaN,"events":[]}',
            b'{"queue":"single","cancel_in_progress":false,"events":[1e9999]}',
            b'{"queue":"single","cancel_in_progress":false,"events":["\\ud800"]}',
            b'{"queue":"single","cancel_in_progress":false,"events":["\xff"]}',
            b'{"queue":"single","cancel_in_progress":false,"events":[]} trailing',
            b'\xef\xbb\xbf{"queue":"single","cancel_in_progress":false,"events":[]}',
            b"[" * 1200 + b"]" * 1200,
        ):
            with self.subTest(prefix=content[:80]):
                self.trace.write_bytes(content)
                self.assert_invalid(self.cli(str(self.trace)))

    def test_rejects_large_files_and_nonfiles(self):
        self.trace.write_bytes(b" " * (1024 * 1024 + 1))
        self.assert_invalid(self.cli(str(self.trace)))
        self.assert_invalid(self.cli(str(self.trace.parent)))
        self.assert_invalid(self.cli(str(self.trace.with_name("PRIVATE_MARKER"))))

    def test_rejects_nonlocal_spellings_before_filesystem_access(self):
        for path in (
            "https://example.invalid/trace.json", "file:///trace.json",
            "//host/share/trace.json", "\\/host/share/trace.json",
            "/\\host/share/trace.json", "\\\\?\\C:\\trace.json",
            "\\\\.\\pipe\\trace.json", "\\??\\C:\\trace.json",
            "C:trace.json", "C:/trace.json:stream", "NUL.json", "AUX .json",
        ):
            with self.subTest(path=path), patch.object(os, "stat", side_effect=AssertionError), \
                    patch.object(os, "open", side_effect=AssertionError), \
                    contextlib.redirect_stderr(io.StringIO()) as stderr, \
                    contextlib.redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(tool.main([path]), 2)
                self.assertEqual((stdout.getvalue(), stderr.getvalue().strip()), ("", INVALID))

    def test_argument_errors_are_fixed(self):
        for args in ((), ("--PRIVATE_MARKER",), ("file", "PRIVATE_MARKER")):
            with self.subTest(args=args):
                self.assert_invalid(self.cli(*args))
        result = self.cli("--help")
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        self.assertIn("INPUT", result.stdout)

    def test_closed_stdout_exits_without_a_traceback(self):
        self.trace.write_text(
            '{"queue":"single","cancel_in_progress":false,"events":[]}', encoding="utf-8",
        )
        for arg in (str(self.trace), "--help"):
            with self.subTest(arg=arg):
                read_fd, write_fd = os.pipe()
                os.close(read_fd)
                try:
                    result = subprocess.run(
                        [sys.executable, str(SCRIPT), arg], stdout=write_fd,
                        stderr=subprocess.PIPE, text=True, encoding="utf-8", timeout=5,
                    )
                finally:
                    os.close(write_fd)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn("Traceback", result.stderr)
                self.assertNotIn("Exception ignored", result.stderr)
