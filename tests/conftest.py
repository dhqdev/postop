import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="postop-test-"))
os.environ.setdefault("DATA_DIR", str(_tmp))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ.setdefault("ADMIN_USER", "tester")
os.environ.setdefault("ADMIN_PASSWORD", "s3nha-forte")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("PUBLIC_URL", "https://postop.example.com")
