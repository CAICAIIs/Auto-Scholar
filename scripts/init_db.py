#!/usr/bin/env python3
import asyncio
import sys

from backend.db import init_db


async def main() -> None:
    print("Initializing PostgreSQL database schema...")
    try:
        await init_db()
        print("✓ Database schema created successfully")
        print("  Tables: papers, chunks, embeddings")
        return 0
    except Exception as e:
        print(f"✗ Database initialization failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
