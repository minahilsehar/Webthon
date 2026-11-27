import os
from pathlib import Path


def load_dotenv():
    base_dir = Path(__file__).resolve().parent.parent.parent
    env_file = base_dir / ".env"
    if not env_file.is_file():
        return

    for line_number, raw_line in enumerate(
        env_file.read_text(encoding="utf-8").splitlines(),
        1,
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not key.strip():
            raise ValueError(f"Invalid .env entry on line {line_number}")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


load_dotenv()

if os.environ.get("DEBUG", "false").lower() == "true":
    from .development import *  # noqa: F403
else:
    from .production import *  # noqa: F403
