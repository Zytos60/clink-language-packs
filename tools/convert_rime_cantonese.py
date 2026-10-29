#!/usr/bin/env python3
"""Convert upstream Rime Cantonese tables into Clink plain-text sources.

Upstream: https://github.com/Zytos60/rime-cantonese
The source project attributes its main data to CanCLID and licenses it CC BY 4.0.
"""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import re
import unicodedata
from collections import defaultdict

CODE = "yue_jyutping"
SCHEMA = "jyut6ping3.schema.yaml"
WORD_TABLE = "jyut6ping3.words.dict.yaml"
CHAR_TABLE = "jyut6ping3.chars.dict.yaml"
PHRASE_TABLE = "jyut6ping3.phrase.dict.yaml"
READING_SYLLABLE = re.compile(r"[a-z]+[1-6]\Z")
MAX_CANDIDATES = 16
CORE_WORDS = {"香港", "多謝", "唔該", "廣東話", "粵語", "食飯", "再見"}
CORE_PHRASES = {"早晨", "晚安", "香港人"}
CORE_TERMS = CORE_WORDS | CORE_PHRASES


def is_han_word(word: str, min_length: int = 1, max_length: int = 8) -> bool:
    if not min_length <= len(word) <= max_length:
        return False
    for character in word:
        name = unicodedata.name(character, "")
        if not (
            "CJK UNIFIED IDEOGRAPH" in name
            or "CJK COMPATIBILITY IDEOGRAPH" in name
        ):
            return False
    return True


def dictionary_rows(path: pathlib.Path, min_fields: int = 2):
    in_body = False
    found_body = False
    for line_number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not in_body:
            if raw.strip() == "...":
                in_body = found_body = True
            continue
        if not raw or raw.lstrip().startswith("#"):
            continue
        fields = raw.split("\t")
        if len(fields) < min_fields:
            continue
        yield line_number, [field.strip() for field in fields]
    if not found_body:
        raise ValueError(f"{path} has no Rime dictionary body delimiter ('...').")


def checked_syllables(raw_reading: str) -> tuple[str, ...] | None:
    syllables = tuple(raw_reading.split())
    if not syllables or not all(READING_SYLLABLE.fullmatch(syllable) for syllable in syllables):
        return None
    return syllables


def add_candidate(rows: dict[str, list[str]], reading: str, candidate: str) -> None:
    candidates = rows.setdefault(reading, [])
    if candidate not in candidates and len(candidates) < MAX_CANDIDATES:
        candidates.append(candidate)


def stable_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def validate_schema(path: pathlib.Path) -> None:
    schema = path.read_text(encoding="utf-8-sig")
    if not re.search(r"(?m)^\s*schema_id:\s*jyut6ping3\s*$", schema):
        raise ValueError(f"{path} is not the Jyutping schema (schema_id: jyut6ping3).")
    if not re.search(r"(?m)^\s*alphabet:\s*zyxwvutsrqponmlkjihgfedcba\s*$", schema):
        raise ValueError(f"{path} does not declare the expected Jyutping alphabet.")


def convert(
    upstream: pathlib.Path,
    output: pathlib.Path,
    max_char_readings: int,
    max_word_readings: int,
    max_phrases: int,
) -> None:
    validate_schema(upstream / SCHEMA)
    word_groups: dict[str, list[str]] = defaultdict(list)
    word_reading_lengths: dict[str, int] = {}
    word_readings_by_candidate: dict[str, set[str]] = defaultdict(set)
    syllable_frequency: dict[str, int] = defaultdict(int)
    character_groups: dict[str, list[str]] = defaultdict(list)
    character_readings: dict[str, set[str]] = defaultdict(set)
    core_characters = set("".join(CORE_TERMS))

    for _line, fields in dictionary_rows(upstream / WORD_TABLE):
        word = unicodedata.normalize("NFC", fields[0])
        syllables = checked_syllables(fields[1])
        if not is_han_word(word, max_length=8) or syllables is None or len(syllables) != len(word):
            continue
        reading = "".join(syllables)
        if word not in word_groups[reading]:
            word_groups[reading].append(word)
            word_reading_lengths[reading] = len(syllables)
            word_readings_by_candidate[word].add(reading)
            for syllable in syllables:
                syllable_frequency[syllable] += 1

    for _line, fields in dictionary_rows(upstream / CHAR_TABLE):
        character = unicodedata.normalize("NFC", fields[0])
        syllables = checked_syllables(fields[1])
        if not is_han_word(character, max_length=1) or syllables is None or len(syllables) != 1:
            continue
        reading = syllables[0]
        if character not in character_groups[reading]:
            character_groups[reading].append(character)
            character_readings[character].add(reading)

    compound_groups = [
        (reading, candidates)
        for reading, candidates in word_groups.items()
        if word_reading_lengths[reading] > 1
    ]
    compound_groups.sort(
        key=lambda item: (
            not any(candidate in CORE_TERMS for candidate in item[1]),
            -len(item[1]),
            item[0],
        )
    )
    if max_word_readings:
        compound_groups = compound_groups[:max_word_readings]

    character_groups = dict(
        sorted(
            character_groups.items(),
            key=lambda item: (
                not any(character in core_characters for character in item[1]),
                -syllable_frequency[item[0]],
                item[0],
            ),
        )
    )
    if max_char_readings:
        character_groups = dict(list(character_groups.items())[:max_char_readings])

    ime_rows: dict[str, list[str]] = {}
    source_words: set[str] = set()
    for reading, candidates in character_groups.items():
        ranked_candidates = sorted(candidates, key=lambda candidate: candidate not in core_characters)
        for candidate in ranked_candidates[:MAX_CANDIDATES]:
            add_candidate(ime_rows, reading, candidate)
            source_words.add(candidate)

    for reading, candidates in compound_groups:
        for candidate in candidates[:MAX_CANDIDATES]:
            add_candidate(ime_rows, reading, candidate)
            source_words.add(candidate)

    phrase_path = upstream / PHRASE_TABLE
    phrases = set()
    for line_number, fields in dictionary_rows(phrase_path, min_fields=1):
        phrase = unicodedata.normalize("NFC", fields[0])
        if not is_han_word(phrase, min_length=2, max_length=6):
            continue
        if phrase in word_readings_by_candidate:
            continue
        readings = [character_readings.get(character, set()) for character in phrase]
        if any(len(options) != 1 for options in readings):
            continue
        reading = "".join(next(iter(options)) for options in readings)
        phrases.add((stable_key(phrase), phrase, reading, line_number))

    selected_phrases = sorted(phrases, key=lambda row: (len(row[1]), row[0]))
    if max_phrases:
        selected_phrases = selected_phrases[:max_phrases]
    for _key, phrase, reading, _line in selected_phrases:
        add_candidate(ime_rows, reading, phrase)
        source_words.add(phrase)

    output.mkdir(parents=True, exist_ok=True)
    words_path = output / f"{CODE}.txt"
    ime_path = output / f"{CODE}-ime.tsv"
    words_path.write_text("".join(f"{word}\n" for word in sorted(source_words)), encoding="utf-8", newline="\n")
    ime_path.write_text(
        "".join("\t".join((reading, *ime_rows[reading])) + "\n" for reading in sorted(ime_rows)),
        encoding="utf-8",
        newline="\n",
    )
    print(f"Wrote {words_path} with {len(source_words):,} words.")
    print(f"Wrote {ime_path} with {len(ime_rows):,} readings.")
    print(
        f"Selected {len(character_groups):,} character readings, "
        f"{len(compound_groups):,} compound readings, and "
        f"{len(selected_phrases):,} composed phrases."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream", type=pathlib.Path, help="Path to the rime-cantonese checkout")
    parser.add_argument("--output-dir", type=pathlib.Path, default=pathlib.Path("source"))
    parser.add_argument("--max-char-readings", type=int, default=100,
                        help="Most useful single-character readings to keep; 0 means unlimited.")
    parser.add_argument("--max-word-readings", type=int, default=50,
                        help="Most useful compound Jyutping readings to keep; 0 means unlimited.")
    parser.add_argument("--max-phrases", type=int, default=50,
                        help="Unambiguous phrases to compose from character readings; 0 means unlimited.")
    args = parser.parse_args()
    if args.max_char_readings < 0 or args.max_word_readings < 0 or args.max_phrases < 0:
        parser.error("limits must be zero or greater")
    try:
        convert(args.upstream, args.output_dir, args.max_char_readings, args.max_word_readings, args.max_phrases)
    except (OSError, UnicodeError, ValueError) as error:
        parser.exit(1, f"ERROR: {error}\n")


if __name__ == "__main__":
    main()