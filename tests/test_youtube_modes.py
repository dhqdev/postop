"""Cortes do YouTube: tempos, trechos manuais, divisão em partes e texto compacto para a IA."""

import pytest

from app.media import Word, ass_title_line
from app.pipelines.youtube_clips import (
    MAX_PARTS,
    check_params,
    clean_clips,
    compact_transcript,
    fmt_time,
    parse_ranges,
    parse_time,
    split_parts,
)


def _words(text, start=0.0, step=0.5):
    out, t = [], start
    for w in text.split():
        out.append(Word(t, t + step - 0.05, " " + w))
        t += step
    return out


@pytest.mark.parametrize(
    ("value", "secs"),
    [("83", 83), ("1:23", 83), ("01:02:03", 3723), ("1:23.5", 83.5), ("1m23s", 83), ("1h2m", 3720),
     ("2,5", 2.5), (90, 90)],
)  # fmt: skip
def test_parse_time(value, secs):
    assert parse_time(value) == pytest.approx(secs)


def test_parse_time_empty_and_invalid():
    assert parse_time("") is None and parse_time(None) is None
    for bad in ("abc", "1:75", "1:2:3:4", "-5"):
        with pytest.raises(ValueError):
            parse_time(bad)


def test_fmt_time():
    assert fmt_time(83) == "1:23" and fmt_time(3723) == "1:02:03" and fmt_time(0) == "0:00"


def test_parse_ranges_formats_and_titles():
    clips = parse_ranges(
        "1:20-2:05 Melhor parte\n\n• 10:00 a 10:45\nde 12:30 até 13:10 | Final\n1:02:10 - 1:03:00"
    )
    assert [(c["start"], c["end"]) for c in clips] == [(80, 125), (600, 645), (750, 790), (3730, 3780)]
    assert [c["title"] for c in clips] == ["Melhor parte", "", "Final", ""]


def test_parse_ranges_errors_say_the_line():
    with pytest.raises(ValueError, match="Linha 2"):
        parse_ranges("1:00-1:30\n5:00-4:00")
    with pytest.raises(ValueError, match="Linha 1"):
        parse_ranges("só texto")
    with pytest.raises(ValueError, match="curto"):
        parse_ranges("1:00-1:01")
    assert len(parse_ranges("\n".join(f"{i}:00-{i}:30" for i in range(1, 50)))) == 30  # limite


def test_check_params():
    assert check_params({"mode": "ai"}) is None
    assert check_params({"mode": "parts", "start": "1:00", "end": "12:00"}) is None
    assert "depois do início" in check_params({"mode": "ai", "start": "5:00", "end": "4:00"})
    assert "curto" in check_params({"mode": "ai", "start": "1:00", "end": "1:02"})
    assert "Trecho do vídeo" in check_params({"mode": "parts", "start": "abc"})
    assert "pelo menos um corte" in check_params({"mode": "manual", "clips": "  "})
    assert "Linha 1" in check_params({"mode": "manual", "clips": "2:00-1:00"})
    assert check_params({"mode": "xyz"})


def test_split_parts_covers_the_range_without_gaps():
    parts = split_parts(120, 870, 60, [])
    assert parts[0][0] == 120 and parts[-1][1] == 870
    assert all(a[1] == b[0] for a, b in zip(parts, parts[1:], strict=False))
    assert all(e - s <= 60 * 1.3 + 0.2 for s, e in parts)
    assert len(parts) == 13 and parts[-1] == (840, 870)  # 750 s em partes de 1 min: sobram 30 s
    assert split_parts(0, 130, 60, [])[-1] == (60, 130)  # sobra pequena (10 s) entra na última parte


def test_split_parts_prefers_end_of_sentence_and_caps():
    words = _words("um dois três quatro cinco seis sete oito nove dez. " * 20)
    parts = split_parts(0, len(words) * 0.5, 30, words)
    ends = {round(w.end + 0.15, 2) for w in words if w.text.endswith(".")}
    assert all(round(e, 2) in ends for _, e in parts[:-1])
    assert len(split_parts(0, 100_000, 15, [])) == MAX_PARTS


def test_compact_transcript_is_short_and_uses_whole_seconds():
    segs = [{"start": i * 4.37, "end": i * 4.37 + 4.0, "text": f" frase número {i}"} for i in range(20)]
    text = compact_transcript(segs, offset=600)
    assert text.startswith("[600-") and ".37" not in text
    assert "|604|" in text and len(text.splitlines()) < 20


def test_clean_clips_respects_the_chosen_range():
    words = _words("a b c d e f g h i j " * 30)
    raw = [{"start": 5, "end": 40, "title": "antes do trecho"}, {"start": 60, "end": 90, "hashtags": "x y"}]
    clips = clean_clips(raw, words, 150, 5, 10, 60, lo=50)
    assert len(clips) == 1 and clips[0]["start"] >= 59
    assert clips[0]["hashtags"] == ["#x", "#y"]


def test_ass_title_line():
    line = ass_title_line("PARTE 2", 0, 30)
    assert line.startswith("Dialogue: 1,0:00:00.00,0:00:30.00,Title,") and line.rstrip().endswith("PARTE 2")
