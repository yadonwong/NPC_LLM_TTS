from pathlib import Path


def build_output_path(base_dir: str, language: str, region: str, subregion: str, voice_id: str, script_id: str) -> Path:
    p = Path(base_dir) / language / region
    if str(subregion).strip():
        p = p / subregion
    return p / voice_id / f"{script_id}.wav"


def resolve_existing_path(path: Path, policy: str) -> tuple[bool, Path]:
    if not path.exists():
        return False, path
    if policy == "overwrite":
        return False, path
    if policy == "skip":
        return True, path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    i = 2
    while True:
        candidate = parent / f"{stem}_v{i}{suffix}"
        if not candidate.exists():
            return False, candidate
        i += 1
