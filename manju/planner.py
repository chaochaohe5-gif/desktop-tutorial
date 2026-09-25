"""纯函数：已校验剧本 → 可复现的生产计划，不调用任何生成服务。"""

from dataclasses import asdict
import hashlib
import json

from .model import Episode


def build_plan(episode: Episode) -> dict:
    characters = {character.id: character for character in episode.characters}
    canonical = json.dumps(asdict(episode), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    shots = []
    warnings = ["字幕按台词字数估算时间；配音后必须根据实际音频重新对齐。"]
    cursor = 0
    for scene in episode.scenes:
        for shot in scene.shots:
            cast = [characters[character_id] for character_id in shot.characters]
            appearance = "；".join(f"{char.name}：{char.appearance}" for char in cast) or "无人物出镜"
            prompt = (
                f"画幅：{episode.aspect_ratio}。统一风格：{episode.visual_style}。"
                f"场景：{scene.location}。景别与构图：{shot.framing}。"
                f"角色固定设定：{appearance}。本镜头画面：{shot.visual}。"
                "保持同一角色的脸型、发型、服装与配色一致。"
            )
            cues = []
            total_weight = sum(len(line.text) for line in shot.lines)
            weight_so_far = 0
            cue_start = cursor
            # 先给每句 1ms，再按字数分配剩余时间，确保无零时长和累计漂移。
            budget = shot.duration_ms - len(shot.lines)
            for index, line in enumerate(shot.lines, 1):
                weight_so_far += len(line.text)
                cue_end = cursor + index + budget * weight_so_far // total_weight
                character = characters.get(line.speaker)
                cues.append({
                    "id": f"{shot.id}-{index:02d}",
                    "speaker": line.speaker,
                    "speaker_name": character.name if character else "旁白",
                    "voice_direction": character.voice if character else "清晰自然的普通话旁白",
                    "text": line.text,
                    "start_ms": cue_start,
                    "end_ms": cue_end,
                    "audio_path": f"audio/shot_{shot.id}_line_{index:02d}.wav",
                    "audio_status": "pending",
                })
                cue_start = cue_end
            if total_weight * 1000 > shot.duration_ms * 6:
                warnings.append(f"{shot.id}：台词密度超过每秒 6 字，建议试听后缩短台词或延长镜头。")
            shots.append({
                "id": shot.id,
                "scene_id": scene.id,
                "location": scene.location,
                "start_ms": cursor,
                "end_ms": cursor + shot.duration_ms,
                "duration_ms": shot.duration_ms,
                "framing": shot.framing,
                "visual": shot.visual,
                "characters": list(shot.characters),
                "sound_direction": shot.sound,
                "image_prompt": prompt,
                "negative_prompt": episode.negative_prompt,
                "image_path": f"images/shot_{shot.id}.png",
                "image_status": "pending",
                "lines": cues,
            })
            cursor += shot.duration_ms
    return {
        "bundle_version": 1,
        "source_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "episode": {"id": episode.id, "title": episode.title, "aspect_ratio": episode.aspect_ratio},
        "status": "planned",
        "duration_ms": cursor,
        "characters": [asdict(character) for character in episode.characters],
        "shots": shots,
        "warnings": warnings,
        "stages": {
            "script": "validated",
            "storyboard": "planned",
            "characters": "specified",
            "images": "pending",
            "voice": "pending",
            "edit": "pending",
            "publish": "manual",
        },
    }
