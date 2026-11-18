from pathlib import Path
from platformdirs import user_cache_dir

PARENT = Path(user_cache_dir("kami","kami", ensure_exists=True))
LOG_PATH = PARENT / "logs"
LOG_PATH.mkdir(exist_ok=True)