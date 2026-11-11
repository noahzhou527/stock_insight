r"""Write the OpenAPI schema to a file (input for the frontend's generated TS types).

    .venv\Scripts\python -m backend.scripts.export_openapi frontend/src/api/openapi.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from backend.app.config import Settings
from backend.app.main import create_app


def main(target: str) -> None:
    # The schema does not depend on the database or providers; build the app without a lifespan run.
    app = create_app(Settings(frontend_dist=Path("__no_dist__")))
    Path(target).write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {target}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "frontend/src/api/openapi.json")
