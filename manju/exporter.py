"""将计划导出成创作者和后续服务都可读取的生产包。"""

import csv
import html
import io
import json
from pathlib import Path
import tempfile


def timecode(milliseconds: int) -> str:
    seconds, ms = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{ms:03d}"


def _md(text: object) -> str:
    return html.escape(str(text)).replace("|", "\\|")


def _csv(rows: list[list]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    for row in rows:
        # 创作者文本按纯文本打开，避免表格程序把台词当成公式执行。
        writer.writerow([
            "'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")) else value
            for value in row
        ])
    return "\ufeff" + stream.getvalue()


def render_files(plan: dict) -> dict[str, str]:
    title = _md(plan["episode"]["title"])
    names = {character["id"]: character["name"] for character in plan["characters"]}
    storyboard = [
        f"# {title} · 分镜表", "",
        f"计划总时长：{plan['duration_ms'] / 1000:g} 秒；画幅：{plan['episode']['aspect_ratio']}。", "",
        "> 此文件是制作计划，图片和音频尚未生成。字幕时间需要配音后重新对齐。", "",
        "| 镜头 | 时间 | 场景 | 景别 | 出镜角色 | 画面 | 台词 | 声音 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    shot_rows = [["镜头ID", "场景ID", "开始毫秒", "结束毫秒", "时长秒", "场景", "景别", "出镜角色", "画面", "台词", "声音"]]
    voice_rows = [["台词ID", "镜头ID", "角色ID", "角色名称", "声音设定", "台词", "预估开始毫秒", "预估结束毫秒", "预期音频路径"]]
    subtitle_blocks = []
    prompts = []
    for shot in plan["shots"]:
        cast = "、".join(names[char_id] for char_id in shot["characters"]) or "无"
        spoken = " / ".join(f"{line['speaker_name']}：{line['text']}" for line in shot["lines"]) or "无台词"
        timing = f"{timecode(shot['start_ms'])} → {timecode(shot['end_ms'])}"
        cells = [shot["id"], timing, shot["location"], shot["framing"], cast, shot["visual"], spoken, shot["sound_direction"]]
        storyboard.append("| " + " | ".join(_md(cell) for cell in cells) + " |")
        shot_rows.append([
            shot["id"], shot["scene_id"], shot["start_ms"], shot["end_ms"], shot["duration_ms"] / 1000,
            shot["location"], shot["framing"], cast, shot["visual"], spoken, shot["sound_direction"],
        ])
        prompts.append({
            "shot_id": shot["id"], "prompt": shot["image_prompt"],
            "negative_prompt": shot["negative_prompt"], "expected_path": shot["image_path"],
        })
        for line in shot["lines"]:
            voice_rows.append([
                line["id"], shot["id"], line["speaker"], line["speaker_name"], line["voice_direction"], line["text"],
                line["start_ms"], line["end_ms"], line["audio_path"],
            ])
            subtitle_blocks.append(
                f"{len(subtitle_blocks) + 1}\n{timecode(line['start_ms'])} --> {timecode(line['end_ms'])}\n{line['text']}\n"
            )
    storyboard.extend(["", "## 制作提醒", "", *(f"- {_md(item)}" for item in plan["warnings"])])
    cards = [f"# {title} · 角色卡", "", "> 先审核角色参考图；文字设定本身不能保证生成画面中的角色一致。", ""]
    for character in plan["characters"]:
        cards.extend([
            f"## {_md(character['name'])}（{character['id']}）", "",
            f"- 固定外观：{_md(character['appearance'])}",
            f"- 声音设定：{_md(character['voice'])}",
            "- 参考图：待制作、待确认", "",
        ])
    if not plan["characters"]:
        cards.append("本集未定义出镜角色。")
    release = [
        f"# {title} · 成片与发布检查", "",
        "- [ ] 剧本、图片、配音、音乐的使用授权已确认。",
        "- [ ] 角色参考图已确认；逐镜检查脸、手、服装和道具。",
        "- [ ] 台词已试听，多音字、语气和声音一致性已检查。",
        "- [ ] 用实际音频重新对齐字幕，检查停顿、静音和切镜。",
        "- [ ] 图片、音频和字幕已在剪辑工具中合成；完整观看导出文件。",
        "- [ ] 封面、标题、简介和结尾悬念已人工检查。",
        "- [ ] 按发布时平台规则处理 AI 内容标识等要求。",
        "- [ ] 在平台官方客户端人工发布并记录作品链接。",
        "- [ ] 记录本集生成费用、重试次数、工时和播放反馈。", "",
        "当前生产包不会调用模型、生成媒体或登录发布账号。",
    ]
    dump = lambda value: json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    return {
        "production.json": dump(plan),
        "storyboard.md": "\n".join(storyboard) + "\n",
        "storyboard.csv": _csv(shot_rows),
        "characters.md": "\n".join(cards) + "\n",
        "image_prompts.json": dump(prompts),
        "voice_lines.csv": _csv(voice_rows),
        "subtitles.srt": "\n".join(subtitle_blocks),
        "release_checklist.md": "\n".join(release) + "\n",
    }


def export_bundle(plan: dict, destination: Path) -> list[Path]:
    destination = destination.expanduser().absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"输出目录已存在：{destination}；请换一个目录，不会覆盖已有素材")
    files = render_files(plan)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # 全部文件写完再移动目录；失败时清理临时文件，不留下半个生产包。
    with tempfile.TemporaryDirectory(prefix=".manju-", dir=destination.parent) as temporary:
        staging = Path(temporary) / "bundle"
        staging.mkdir()
        for name, content in files.items():
            with (staging / name).open("w", encoding="utf-8", newline="") as handle:
                handle.write(content)
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"输出目录已存在：{destination}；请换一个目录")
        staging.rename(destination)
    return [destination / name for name in files]
