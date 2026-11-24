"""CI temporário: transcreve as amostras com o Whisper do app para conferir o que a voz fala."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.config import config  # noqa: E402
from app.media import transcribe  # noqa: E402

for path in sys.argv[2:]:
    t = time.time()
    words = transcribe(Path(path), sys.argv[1], "pt", config.models_dir)
    text = "".join(w.text for w in words).strip()
    print(f"{path} ({time.time() - t:.1f}s): {text}", flush=True)
