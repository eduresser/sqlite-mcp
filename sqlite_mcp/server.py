from __future__ import annotations

import json
import os
import re
import sqlite3
import time

from mcp.server.fastmcp import FastMCP

WRITE_PATTERN = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|ATTACH|DETACH|REINDEX|VACUUM|ANALYZE)\b",
    re.IGNORECASE,
)

DEFAULT_MAX_ROWS = 100
DEFAULT_TIMEOUT = 30

server: FastMCP | None = None
db_path: str = ""
read_only: bool = False
timeout_seconds: int = DEFAULT_TIMEOUT


class QueryTimeout(Exception):
    pass


def _connect() -> sqlite3.Connection:
    if read_only:
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    else:
        conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    if timeout_seconds > 0:
        deadline = time.monotonic() + timeout_seconds

        def _check_timeout():
            if time.monotonic() > deadline:
                return 1
            return 0

        conn.set_progress_handler(_check_timeout, 1000)

    return conn


def _is_write(sql: str) -> bool:
    return bool(WRITE_PATTERN.match(sql))


def _build_server() -> FastMCP:
    mcp = FastMCP("sqlite-mcp")

    @mcp.tool()
    def execute_sql(sql: str, dry_run: bool = False, max_rows: int = DEFAULT_MAX_ROWS) -> str:
        """Execute a SQL statement against the SQLite database.

        Args:
            sql: The SQL statement to execute.
            dry_run: If true, returns the query plan (EXPLAIN QUERY PLAN) without executing.
            max_rows: Maximum number of rows to return. Defaults to 100.
        """
        if read_only and _is_write(sql):
            return json.dumps({"error": "Write operations are disabled in read-only mode."})

        conn = _connect()
        try:
            if dry_run:
                cursor = conn.execute(f"EXPLAIN QUERY PLAN {sql}")
                plan = [dict(row) for row in cursor.fetchall()]
                return json.dumps({"query_plan": plan})

            cursor = conn.execute(sql)

            if cursor.description is None:
                conn.commit()
                return json.dumps({
                    "rows_affected": cursor.rowcount,
                    "message": "Statement executed successfully.",
                })

            rows = cursor.fetchmany(max_rows + 1)
            results = [dict(row) for row in rows[:max_rows]]
            truncated = len(rows) > max_rows

            output: dict = {"results": results, "row_count": len(results), "truncated": truncated}

            if truncated:
                count_cursor = conn.execute(f"SELECT COUNT(*) FROM ({sql})")
                total = count_cursor.fetchone()[0]
                output["total_rows"] = total

            return json.dumps(output, default=str)
        except sqlite3.OperationalError as e:
            if "interrupted" in str(e).lower():
                return json.dumps({"error": f"Query timed out after {timeout_seconds}s. Try a more restrictive query or increase SQLITE_TIMEOUT."})
            return json.dumps({"error": str(e)})
        except Exception as e:
            return json.dumps({"error": str(e)})
        finally:
            conn.close()

    @mcp.tool()
    def get_table_info(table: str) -> str:
        """Get complete schema and metadata for a SQLite table.

        Returns columns (name, type, nullable, default, primary key), DDL,
        indexes, foreign keys, and row count in a single call.

        Args:
            table: The table name to inspect.
        """
        conn = _connect()
        try:
            columns_cursor = conn.execute(f"PRAGMA table_info('{table}')")
            columns = [
                {
                    "name": row["name"],
                    "type": row["type"],
                    "nullable": not row["notnull"],
                    "default": row["dflt_value"],
                    "primary_key": bool(row["pk"]),
                }
                for row in columns_cursor.fetchall()
            ]

            if not columns:
                return json.dumps({"error": f"Table '{table}' not found."})

            ddl_cursor = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
            )
            ddl_row = ddl_cursor.fetchone()
            ddl = ddl_row["sql"] if ddl_row else None

            indexes_cursor = conn.execute(f"PRAGMA index_list('{table}')")
            indexes = []
            for idx_row in indexes_cursor.fetchall():
                idx_info_cursor = conn.execute(f"PRAGMA index_info('{idx_row['name']}')")
                idx_columns = [col["name"] for col in idx_info_cursor.fetchall()]
                indexes.append({
                    "name": idx_row["name"],
                    "unique": bool(idx_row["unique"]),
                    "columns": idx_columns,
                })

            fk_cursor = conn.execute(f"PRAGMA foreign_key_list('{table}')")
            foreign_keys = [
                {
                    "from": row["from"],
                    "to_table": row["table"],
                    "to_column": row["to"],
                }
                for row in fk_cursor.fetchall()
            ]

            count_cursor = conn.execute(f"SELECT COUNT(*) as cnt FROM '{table}'")
            row_count = count_cursor.fetchone()["cnt"]

            return json.dumps({
                "table": table,
                "columns": columns,
                "ddl": ddl,
                "indexes": indexes,
                "foreign_keys": foreign_keys,
                "row_count": row_count,
            })
        except Exception as e:
            return json.dumps({"error": str(e)})
        finally:
            conn.close()

    return mcp


def main():
    global db_path, read_only, timeout_seconds, server

    db_path = os.environ.get("SQLITE_DB_PATH", "")
    if not db_path:
        raise SystemExit("SQLITE_DB_PATH environment variable is required.")

    read_only = os.environ.get("SQLITE_READ_ONLY", "false").lower() in ("true", "1", "yes")
    timeout_seconds = int(os.environ.get("SQLITE_TIMEOUT", str(DEFAULT_TIMEOUT)))

    conn = _connect()
    conn.close()

    server = _build_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
