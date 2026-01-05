from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.getenv("ADMIN_HOST", "0.0.0.0")
    port = int(os.getenv("ADMIN_PORT", "8001"))
    uvicorn.run("maruntime.admin.main:app", host=host, port=port, reload=os.getenv("ADMIN_RELOAD", "0") == "1")


if __name__ == "__main__":
    main()
