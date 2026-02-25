import json
from pathlib import Path
from typing import Any


class JsonFileCache:

    def __init__(self, file_path: Path):
        self.file_path = file_path

    def exists(self) -> bool:
        return self.file_path.exists()

    def load(self) -> Any:
        if not self.exists():
            return None

        with open(self.file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save(self, data: Any):
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
