"""Regression checks for preservation, replay integrity, and invalid inputs."""

import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "record_process.py"
spec = importlib.util.spec_from_file_location("record_process", SCRIPT)
recorder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recorder)


def png(red):
    def chunk(kind, body):
        return (struct.pack(">I", len(body)) + kind + body +
                struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF))
    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(bytes([0, red, 0, 0]))) + chunk(b"IEND", b""))


class RecordingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)
        self.root = self.work / "过程"
        self.svg = self.work / "current.svg"
        self.preview = self.work / "current.png"
        self.output = self.work / "output" / "process.html"

    def capture(self, red, note="实际修改"):
        self.svg.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg"><rect width="1" height="1" '
            f'fill="rgb({red},0,0)"/></svg>', encoding="utf-8")
        self.preview.write_bytes(png(red))
        return recorder.capture(self.root, self.svg, self.preview, note)

    def test_appending_preserves_earlier_source_preview_and_metadata(self):
        first = self.capture(10, "草稿")
        original = {p.name: p.read_bytes() for p in first.iterdir()}
        second = self.capture(200, "调整颜色")
        self.assertEqual(second.name, "0002")
        self.assertEqual(original, {p.name: p.read_bytes() for p in first.iterdir()})
        metadata, preview = recorder.read_checkpoint(second)
        self.assertEqual((metadata["width"], metadata["height"]), (1, 1))
        self.assertEqual(preview, png(200))

    def test_duplicate_does_not_create_another_batch(self):
        self.capture(10)
        with self.assertRaisesRegex(ValueError, "完全相同"):
            recorder.capture(self.root, self.svg, self.preview, "重复保存")
        self.assertEqual(len(recorder.checkpoint_dirs(self.root)), 1)

    def test_tampered_history_is_rejected(self):
        first = self.capture(10)
        self.capture(200)
        (first / "preview.png").write_bytes(png(40))
        with self.assertRaisesRegex(ValueError, "校验失败"):
            recorder.replay(self.root, self.svg, self.output, "过程")
        self.assertFalse(self.output.exists())

    def test_final_source_must_match_the_last_snapshot(self):
        self.capture(10)
        self.capture(200)
        self.svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "不是当前成稿"):
            recorder.replay(self.root, self.svg, self.output, "过程")

    def test_invalid_png_and_non_svg_leave_no_history(self):
        self.svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")
        self.preview.write_bytes(png(10)[:-4])
        with self.assertRaises(ValueError):
            recorder.capture(self.root, self.svg, self.preview, "坏预览")
        self.preview.write_bytes(png(10))
        self.svg.write_text("<html/>", encoding="utf-8")
        with self.assertRaises(ValueError):
            recorder.capture(self.root, self.svg, self.preview, "非 SVG")
        self.assertFalse(self.root.exists())

    def test_missing_or_interrupted_history_is_not_hidden(self):
        first = self.capture(10)
        second = self.capture(200)
        second.rename(self.root / "0003")
        with self.assertRaisesRegex(ValueError, "编号有缺失"):
            recorder.replay(self.root, self.svg, self.output, "过程")
        (first / "checkpoint.json").unlink()
        with self.assertRaises(OSError):
            recorder.replay(self.root, self.svg, self.output, "过程")

    def test_two_snapshots_and_no_external_resources(self):
        self.capture(10)
        with self.assertRaisesRegex(ValueError, "至少需要两批"):
            recorder.replay(self.root, self.svg, self.output, "过程")
        note = '</script><script>window.injected=true</script> & 中文'
        self.capture(200, note)
        recorder.replay(self.root, self.svg, self.output, "<演示>")
        document = self.output.read_text(encoding="utf-8")
        frames = json.loads(document.split("const frames=", 1)[1].split(";\n", 1)[0])
        self.assertEqual([frame["note"] for frame in frames], ["实际修改", note])
        self.assertEqual(len(frames), 2)
        self.assertNotIn(note, document)
        self.assertIn("&lt;演示&gt;", document)
        self.assertTrue(all(frame["image"].startswith("data:image/png;base64,") for frame in frames))


if __name__ == "__main__":
    unittest.main()
