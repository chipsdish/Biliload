from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    source: str
    target: str = ""


def srt_timestamp(seconds: float) -> str:
    milliseconds = int(round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


def cues_to_srt(cues: list[Cue], mode: str) -> str:
    blocks: list[str] = []
    for index, cue in enumerate(cues, 1):
        if mode == "source":
            text = cue.source
        elif mode == "target":
            text = cue.target or cue.source
        elif mode == "bilingual":
            text = cue.source if not cue.target else f"{cue.source}\n{cue.target}"
        else:
            raise ValueError(f"Unsupported SRT mode: {mode}")

        blocks.append(
            f"{index}\n{srt_timestamp(cue.start)} --> {srt_timestamp(cue.end)}\n{text}"
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def cues_to_text(cues: list[Cue]) -> str:
    lines = []
    for cue in cues:
        lines.append(
            f"[{srt_timestamp(cue.start)} --> {srt_timestamp(cue.end)}] {cue.source}"
        )
        if cue.target:
            lines.append(f"  {cue.target}")
    return "\n".join(lines) + ("\n" if lines else "")


def cue_to_json(cue: Cue) -> dict[str, float | str]:
    return {
        "start": cue.start,
        "end": cue.end,
        "source": cue.source,
        "target": cue.target,
    }

