"""命令行入口；不把文件系统或模型服务耦合进规划逻辑。"""

import argparse
from pathlib import Path
import sys

from . import __version__
from .exporter import export_bundle
from .model import ValidationError, load_episode
from .planner import build_plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI 漫剧工作台：离线生成分镜生产包", allow_abbrev=False)
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="校验剧本和角色引用", allow_abbrev=False)
    validate.add_argument("script", type=Path, help="UTF-8 JSON 剧本路径")
    build = commands.add_parser("build", help="生成分镜、提示词、配音台本和字幕草稿", allow_abbrev=False)
    build.add_argument("script", type=Path, help="UTF-8 JSON 剧本路径")
    build.add_argument("--out", type=Path, required=True, help="新的输出目录（不覆盖已有目录）")
    args = parser.parse_args(argv)
    try:
        episode = load_episode(args.script)
        plan = build_plan(episode)
        if args.command == "build":
            paths = export_bundle(plan, args.out)
            print(f"已生成 {len(paths)} 个文件：{paths[0].parent}")
        print(f"校验通过：{episode.title}，{len(plan['shots'])} 个镜头，计划 {plan['duration_ms'] / 1000:g} 秒")
        for warning in plan["warnings"]:
            print(f"提醒：{warning}")
        return 0
    except (ValidationError, OSError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
