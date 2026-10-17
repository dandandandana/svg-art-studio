#!/usr/bin/env python3
"""Preserve supplied SVG/PNG batches and build an offline, snapshot-only replay."""

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import struct
import sys
import xml.etree.ElementTree as ET
import zlib


def digest(data):
    return hashlib.sha256(data).hexdigest()


def png_dimensions(data):
    """Validate PNG framing/CRCs; the rendering tool must decode/check pixels."""
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("预览必须为真实 PNG 文件")
    offset, dimensions, has_pixels = 8, None, False
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        end = offset + length + 12
        if end > len(data):
            raise ValueError("PNG 数据不完整")
        kind = data[offset + 4:offset + 8]
        body = data[offset + 8:end - 4]
        crc = struct.unpack(">I", data[end - 4:end])[0]
        if zlib.crc32(kind + body) & 0xFFFFFFFF != crc:
            raise ValueError("PNG 校验失败")
        if dimensions is None:
            if kind != b"IHDR" or length != 13:
                raise ValueError("PNG 缺少有效 IHDR")
            dimensions = struct.unpack(">II", body[:8])
            if not all(dimensions):
                raise ValueError("PNG 尺寸无效")
        if kind == b"IDAT":
            has_pixels = True
        if kind == b"IEND":
            if length or end != len(data) or not has_pixels:
                raise ValueError("PNG 结束结构无效")
            return dimensions
        offset = end
    raise ValueError("PNG 缺少结束块")


def checkpoint_dirs(root):
    if not root.exists():
        return []
    return sorted((p for p in root.iterdir() if p.is_dir() and p.name.isdecimal()),
                  key=lambda p: int(p.name))


def read_checkpoint(directory):
    metadata = json.loads((directory / "checkpoint.json").read_text(encoding="utf-8"))
    svg = (directory / "state.svg").read_bytes()
    png = (directory / "preview.png").read_bytes()
    if metadata["svg_sha256"] != digest(svg) or metadata["png_sha256"] != digest(png):
        raise ValueError(f"历史快照校验失败：{directory.name}")
    png_dimensions(png)
    return metadata, png


def capture(root, svg_path, png_path, note):
    """Append one batch; keep interrupted directories without overwriting them."""
    svg, png = svg_path.read_bytes(), png_path.read_bytes()
    if ET.fromstring(svg).tag != "{http://www.w3.org/2000/svg}svg":
        raise ValueError("源码必须为具有 SVG 命名空间的 SVG 根元素")
    width, height = png_dimensions(png)
    if not note.strip():
        raise ValueError("请说明本批实际发生的变化")
    directories = checkpoint_dirs(root)
    if directories:
        previous, _ = read_checkpoint(directories[-1])
        if previous["svg_sha256"] == digest(svg) and previous["png_sha256"] == digest(png):
            raise ValueError("与上一批完全相同；没有新增绘制状态")
    sequence = max((int(p.name) for p in directories), default=0) + 1
    metadata = {
        "sequence": sequence,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "note": note.strip(),
        "svg_sha256": digest(svg),
        "png_sha256": digest(png),
        "width": width,
        "height": height,
    }
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{sequence:04d}"
    target.mkdir()  # Exclusive creation: concurrent writers cannot replace history.
    (target / "state.svg").write_bytes(svg)
    (target / "preview.png").write_bytes(png)
    (target / "checkpoint.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


PLAYER = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<title>__TITLE__</title><style>
*{box-sizing:border-box}body{margin:0;background:#161a20;color:#eef1f5;font:16px/1.6 system-ui,sans-serif}
main{max-width:1100px;margin:auto;padding:20px}h1{font-size:1.4rem;margin:0 0 12px}
.canvas{display:flex;justify-content:center;align-items:center;height:65vh;min-height:220px;
background:repeating-conic-gradient(#303740 0% 25%,#252b33 0% 50%) 0/24px 24px;border-radius:8px}
img{max-width:100%;max-height:100%;object-fit:contain}button,input{font:inherit}
button{padding:8px 16px;background:#eef1f5;color:#161a20;border:0;border-radius:5px;cursor:pointer}
button:focus-visible,input:focus-visible{outline:3px solid #e9b957;outline-offset:4px}
.controls{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin-top:16px}
label{flex:1;min-width:150px}input{display:block;width:100%;accent-color:#e9b957}
#note{overflow-wrap:anywhere;min-height:3.2em}small{color:#bdc5d0}
@media(max-width:480px){main{padding:12px}.canvas{height:55vh}.controls{gap:10px}}
</style></head><body><main><h1>__TITLE__</h1>
<div class="canvas"><img id="art" alt=""></div>
<div class="controls"><button id="play" type="button">播放</button>
<button id="restart" type="button">重播</button>
<label for="seek">批次进度<input id="seek" type="range" min="0" max="0" value="0" step="1"></label>
<output id="position" for="seek"></output></div>
<p id="note" aria-live="polite"></p>
<small>基于真实 SVG/PNG 批次快照的回放，非逐笔录像。按实际记录顺序播放，末帧为完整成稿。</small>
</main><script>
const frames=__FRAMES__;
const art=document.getElementById('art'),seek=document.getElementById('seek');
const play=document.getElementById('play'),restart=document.getElementById('restart');
const position=document.getElementById('position'),note=document.getElementById('note');
let current=0,timer=null;seek.max=frames.length-1;
function stop(){clearInterval(timer);timer=null;play.textContent='播放';}
function show(index){current=index;art.src=frames[index].image;art.alt=frames[index].note;
seek.value=index;position.textContent=`${index+1} / ${frames.length}`;
note.textContent=frames[index].note;}
play.addEventListener('click',()=>{if(timer!==null){stop();return;}
if(current===frames.length-1)show(0);play.textContent='暂停';
timer=setInterval(()=>{show(current+1);if(current===frames.length-1)stop();},1200);});
restart.addEventListener('click',()=>{stop();show(0);});
seek.addEventListener('input',()=>{stop();show(Number(seek.value));});
window.addEventListener('pagehide',stop);show(0);
</script></body></html>
'''


def replay(root, final_svg, output, title):
    directories = checkpoint_dirs(root)
    if len(directories) < 2:
        raise ValueError("至少需要两批真实快照才能制作过程回放")
    frames = []
    for index, directory in enumerate(directories, start=1):
        metadata, png = read_checkpoint(directory)
        if int(directory.name) != index or metadata["sequence"] != index:
            raise ValueError("快照编号有缺失或顺序不一致；请检查原始材料")
        frames.append({"note": metadata["note"], "image": "data:image/png;base64," +
                       base64.b64encode(png).decode("ascii")})
    if metadata["svg_sha256"] != digest(final_svg.read_bytes()):
        raise ValueError("末条快照不是当前成稿；请渲染成稿并追加真实记录")
    if output.suffix.lower() != ".html":
        raise ValueError("离线回放输出必须使用 .html 扩展名")
    data = json.dumps(frames, ensure_ascii=False).replace("<", "\\u003c")
    document = PLAYER.replace("__TITLE__", html.escape(title)).replace("__FRAMES__", data)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    record = commands.add_parser("capture", help="保存当前真实 SVG 与已渲染 PNG")
    record.add_argument("--root", type=Path, required=True)
    record.add_argument("--svg", type=Path, required=True)
    record.add_argument("--png", type=Path, required=True)
    record.add_argument("--note", required=True)
    player = commands.add_parser("replay", help="从已保存批次生成离线 HTML")
    player.add_argument("--root", type=Path, required=True)
    player.add_argument("--final-svg", type=Path, required=True)
    player.add_argument("--output", type=Path, required=True)
    player.add_argument("--title", default="SVG 制作过程")
    args = parser.parse_args()
    try:
        if args.command == "capture":
            result = capture(args.root, args.svg, args.png, args.note)
        else:
            result = replay(args.root, args.final_svg, args.output, args.title)
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError) as error:
        print(f"记录失败：{error}", file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
