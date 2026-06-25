from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


class TranslationError(RuntimeError):
    pass


def translate_lines(
    lines: list[str],
    provider: str,
    target_language: str = "zh-CN",
) -> list[str]:
    if provider == "none":
        return lines

    if provider != "google":
        raise TranslationError(f"Unsupported translator: {provider}")

    try:
        from deep_translator import GoogleTranslator
    except Exception as exc:  # pragma: no cover - dependency guard
        raise TranslationError("deep-translator is not installed") from exc

    translator = GoogleTranslator(source="auto", target=target_language)
    translated: list[str] = []

    # Google web translation is less brittle when requests are small.
    batch_size = 30
    for start in range(0, len(lines), batch_size):
        batch = lines[start : start + batch_size]
        try:
            translated.extend(translator.translate_batch(batch))
        except Exception as exc:
            logger.warning("Batch translation failed, falling back line by line: %s", exc)
            for line in batch:
                try:
                    translated.append(translator.translate(line))
                    time.sleep(0.1)
                except Exception as line_exc:
                    logger.warning("Translation failed for line %r: %s", line, line_exc)
                    translated.append(line)

    return translated

