"""读取剧本并校验跨镜头角色引用；这里是输入格式的唯一实现。"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
from typing import Any


class ValidationError(ValueError):
    """可以直接向创作者展示的输入错误。"""


@dataclass(frozen=True)
class Character:
    id: str
    name: str
    appearance: str
    voice: str


@dataclass(frozen=True)
class Line:
    speaker: str
    text: str


@dataclass(frozen=True)
class Shot:
    id: str
    duration_ms: int
    framing: str
    visual: str
    characters: tuple[str, ...]
    lines: tuple[Line, ...]
    sound: str


@dataclass(frozen=True)
class Scene:
    id: str
    location: str
    shots: tuple[Shot, ...]


@dataclass(frozen=True)
class Episode:
    id: str
    title: str
    aspect_ratio: str
    visual_style: str
    negative_prompt: str
    characters: tuple[Character, ...]
    scenes: tuple[Scene, ...]


def _object(value: Any, path: str, required: set[str], optional: set[str] | None = None) -> dict:
    if not isinstance(value, dict):
        raise ValidationError(f"{path}：应为对象")
    missing = required - value.keys()
    extra = value.keys() - required - (optional or set())
    if missing:
        raise ValidationError(f"{path}：缺少字段 {', '.join(sorted(missing))}")
    if extra:
        raise ValidationError(f"{path}：未知字段 {', '.join(sorted(extra))}")
    return value


def _list(value: Any, path: str, *, allow_empty: bool = False) -> list:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise ValidationError(f"{path}：应为{'可为空的' if allow_empty else '非空'}数组")
    return value


def _text(value: Any, path: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{path}：应为文本")
    value = " ".join(value.split())
    if not value and not allow_empty:
        raise ValidationError(f"{path}：文本不能为空")
    if any(ord(char) < 32 for char in value):
        raise ValidationError(f"{path}：不能包含控制字符")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValidationError(f"{path}：包含无效 Unicode 字符") from exc
    return value


def _identifier(value: Any, path: str) -> str:
    value = _text(value, path)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value):
        raise ValidationError(f"{path}：ID 需为 1–64 位字母、数字、下划线或短横线，首位为字母或数字")
    return value


def _unique(value: str, seen: set[str], path: str) -> None:
    if value in seen:
        raise ValidationError(f"{path}：重复 ID {value}")
    seen.add(value)


def _duration(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValidationError(f"{path}：应为以秒计的数字")
    try:
        seconds = Decimal(str(value))
        if not seconds.is_finite() or not 0 < seconds <= 3600:
            raise ValidationError(f"{path}：需大于 0 且不超过 3600 秒")
        milliseconds = seconds * 1000
        if milliseconds != milliseconds.to_integral_value():
            raise ValidationError(f"{path}：最多保留 3 位小数（毫秒）")
        return int(milliseconds)
    except InvalidOperation as exc:
        raise ValidationError(f"{path}：无效时长") from exc


def parse_episode(data: Any) -> Episode:
    root = _object(data, "episode", {
        "schema_version", "id", "title", "aspect_ratio", "visual_style", "characters", "scenes"
    }, {"negative_prompt"})
    if type(root["schema_version"]) is not int or root["schema_version"] != 1:
        raise ValidationError("schema_version：当前仅支持整数 1")
    episode_id = _identifier(root["id"], "id")
    title = _text(root["title"], "title")
    ratio = _text(root["aspect_ratio"], "aspect_ratio")
    if ratio not in {"9:16", "16:9", "1:1"}:
        raise ValidationError("aspect_ratio：仅支持 9:16、16:9 或 1:1")
    style = _text(root["visual_style"], "visual_style")
    negative = _text(root.get("negative_prompt", ""), "negative_prompt", allow_empty=True)

    characters = []
    character_ids: set[str] = set()
    for index, item in enumerate(_list(root["characters"], "characters", allow_empty=True)):
        path = f"characters[{index}]"
        item = _object(item, path, {"id", "name", "appearance", "voice"})
        char_id = _identifier(item["id"], f"{path}.id")
        if char_id == "narrator":
            raise ValidationError(f"{path}.id：narrator 保留给旁白")
        _unique(char_id, character_ids, f"{path}.id")
        characters.append(Character(char_id, *(
            _text(item[key], f"{path}.{key}") for key in ("name", "appearance", "voice")
        )))

    scenes = []
    scene_ids: set[str] = set()
    shot_ids: set[str] = set()
    for scene_index, item in enumerate(_list(root["scenes"], "scenes")):
        path = f"scenes[{scene_index}]"
        item = _object(item, path, {"id", "location", "shots"})
        scene_id = _identifier(item["id"], f"{path}.id")
        _unique(scene_id, scene_ids, f"{path}.id")
        location = _text(item["location"], f"{path}.location")
        shots = []
        for shot_index, raw in enumerate(_list(item["shots"], f"{path}.shots")):
            shot_path = f"{path}.shots[{shot_index}]"
            raw = _object(raw, shot_path, {
                "id", "duration_seconds", "framing", "visual", "characters", "lines"
            }, {"sound"})
            shot_id = _identifier(raw["id"], f"{shot_path}.id")
            _unique(shot_id, shot_ids, f"{shot_path}.id")
            duration_ms = _duration(raw["duration_seconds"], f"{shot_path}.duration_seconds")
            cast = []
            for value in _list(raw["characters"], f"{shot_path}.characters", allow_empty=True):
                value = _identifier(value, f"{shot_path}.characters")
                if value not in character_ids:
                    raise ValidationError(f"{shot_path}.characters：未定义角色 {value}")
                if value in cast:
                    raise ValidationError(f"{shot_path}.characters：重复角色 {value}")
                cast.append(value)
            lines = []
            for line_index, line in enumerate(_list(raw["lines"], f"{shot_path}.lines", allow_empty=True)):
                line_path = f"{shot_path}.lines[{line_index}]"
                line = _object(line, line_path, {"speaker", "text"})
                speaker = _identifier(line["speaker"], f"{line_path}.speaker")
                if speaker != "narrator" and speaker not in character_ids:
                    raise ValidationError(f"{line_path}.speaker：未定义角色 {speaker}")
                lines.append(Line(speaker, _text(line["text"], f"{line_path}.text")))
            if len(lines) > duration_ms:
                raise ValidationError(f"{shot_path}：每句台词至少需要 1 毫秒")
            shots.append(Shot(
                shot_id, duration_ms,
                _text(raw["framing"], f"{shot_path}.framing"),
                _text(raw["visual"], f"{shot_path}.visual"),
                tuple(cast), tuple(lines),
                _text(raw.get("sound", ""), f"{shot_path}.sound", allow_empty=True),
            ))
        scenes.append(Scene(scene_id, location, tuple(shots)))
    return Episode(episode_id, title, ratio, style, negative, tuple(characters), tuple(scenes))


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"JSON 中存在重复字段：{key}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValidationError(f"JSON 不支持数值 {value}")


def load_episode(path: Path) -> Episode:
    try:
        data = json.loads(
            path.read_text(encoding="utf-8-sig"),
            parse_float=Decimal,
            parse_constant=_invalid_constant,
            object_pairs_hook=_no_duplicate_keys,
        )
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ValidationError(f"无法读取 UTF-8 JSON 剧本：{exc}") from exc
    return parse_episode(data)
