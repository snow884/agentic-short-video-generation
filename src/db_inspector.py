#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "local.db"
HTML_PATH = BASE_DIR / "docs" / "database_inspector.html"

ENTITY_SPECS = [
    {"name": "towns", "label": "Towns", "table": "towns"},
    {"name": "weekends", "label": "Weekends", "table": "weekends"},
    {"name": "events", "label": "Events", "table": "events"},
    {
        "name": "videos",
        "label": "Videos",
        "table": "media",
        "filter_column": "media_type",
        "filter_value": "video",
    },
    {"name": "video_segments", "label": "Video Segments", "table": "video_segments"},
    {"name": "media", "label": "Media", "table": "media"},
    {"name": "weather", "label": "Weather", "table": "weather"},
]


class DatabaseInspectorHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/api/entities":
            self._send_json(list_entities())
            return

        if path == "/api/rows":
            entity = query.get("entity", [""])[0]
            self._send_json(get_entity_rows(entity))
            return

        if path == "/api/schema":
            entity = query.get("entity", [""])[0]
            self._send_json(get_entity_schema(entity))
            return

        if path == "/":
            self._send_html(HTML_PATH.read_text(encoding="utf-8"))
            return

        self.send_error(404, "Not found")

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _send_json(self, payload: object) -> None:
        body = json.dumps(payload, indent=2, default=str).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, body: str) -> None:
        content = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def list_entities() -> list[dict[str, object]]:
    with get_connection() as conn:
        available_tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }

    entities = []
    for spec in ENTITY_SPECS:
        table = spec["table"]
        if table in available_tables:
            entities.append(
                {
                    "name": spec["name"],
                    "label": spec["label"],
                    "table": table,
                }
            )
    return entities


def get_entity_rows(entity: str) -> dict[str, object]:
    spec = next((item for item in ENTITY_SPECS if item["name"] == entity), None)
    if spec is None:
        return {"error": "Unknown entity"}

    with get_connection() as conn:
        table = spec["table"]
        if not table_exists(conn, table):
            return {"entity": entity, "rows": [], "count": 0, "columns": []}

        if spec.get("filter_column") and spec.get("filter_value"):
            query = (
                f"SELECT * FROM {table} "
                f"WHERE {spec['filter_column']} LIKE ? "
                "ORDER BY id LIMIT 200"
            )
            rows = conn.execute(query, (f"%{spec['filter_value']}%",)).fetchall()
        else:
            rows = conn.execute(
                f"SELECT * FROM {table} ORDER BY id LIMIT 200"
            ).fetchall()

        columns = [
            description[0]
            for description in conn.execute(
                f"SELECT * FROM {table} LIMIT 0"
            ).description
        ]
        return {
            "entity": entity,
            "rows": [dict(row) for row in rows],
            "count": len(rows),
            "columns": columns,
        }


def get_entity_schema(entity: str) -> dict[str, object]:
    spec = next((item for item in ENTITY_SPECS if item["name"] == entity), None)
    if spec is None:
        return {"error": "Unknown entity"}

    with get_connection() as conn:
        table = spec["table"]
        if not table_exists(conn, table):
            return {"entity": entity, "columns": []}

        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        columns = [row[1] for row in rows]
        return {"entity": entity, "columns": columns}


def main() -> None:
    port = 8000
    while True:
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), DatabaseInspectorHandler)
            break
        except OSError as exc:
            if exc.errno != 48:
                raise
            port += 1
            if port > 8010:
                raise

    print(f"Database inspector running at http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down database inspector")
        server.server_close()


if __name__ == "__main__":
    main()
