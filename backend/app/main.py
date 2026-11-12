"""
Backend application entrypoint for Adaptive Supply Chain Intelligence (ASCI).
Exposes the FastAPI application instance for uvicorn and ASGI servers.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure root src directory is in sys.path
root_dir = Path(__file__).resolve().parent.parent.parent
src_dir = root_dir / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from asci.llm import load_local_dotenv

load_local_dotenv()

from asci.api.main import create_app

app = create_app(
    data_dir=os.environ.get("ASCI_DATA_DIR"),
    network_scale=os.environ.get("ASCI_NETWORK_SCALE", "v1_corridor"),
)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)
