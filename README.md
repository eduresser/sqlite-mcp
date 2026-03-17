# sqlite-mcp

An MCP (Model Context Protocol) server that exposes SQLite databases as tools for AI agents. Connect any SQLite database and let LLMs query schemas, run SQL, and inspect tables through a standardized interface.

## Features

- **`execute_sql`** — Run arbitrary SQL statements with support for dry-run mode (EXPLAIN QUERY PLAN), automatic result truncation, and configurable row limits.
- **`get_table_info`** — Retrieve complete table metadata in a single call: columns, types, DDL, indexes, foreign keys, and row count.
- **Read-only mode** — Optionally block all write operations for safe, production-friendly access.
- **Query timeout** — Configurable per-query timeout to prevent runaway queries.

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## Installation

```bash
# Clone the repository
git clone https://github.com/<owner>/sqlite-mcp.git
cd sqlite-mcp

# Install with uv
uv sync
```

Or with pip:

```bash
pip install .
```

## Usage

### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `SQLITE_DB_PATH` | Yes | — | Path to the SQLite database file |
| `SQLITE_READ_ONLY` | No | `false` | Set to `true` to disable write operations |
| `SQLITE_TIMEOUT` | No | `30` | Query timeout in seconds |

### Running the Server

```bash
SQLITE_DB_PATH=./my_database.db sqlite-mcp
```

The server communicates over **stdio** and is designed to be launched by an MCP-compatible client (e.g., Cursor, Claude Desktop).

### MCP Client Configuration

Add the server to your MCP client config (e.g., `.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "sqlite": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/sqlite-mcp", "sqlite-mcp"],
      "env": {
        "SQLITE_DB_PATH": "/path/to/database.db",
        "SQLITE_READ_ONLY": "true"
      }
    }
  }
}
```

## Tools

### `execute_sql`

Execute a SQL statement against the connected database.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `sql` | `str` | — | The SQL statement to execute |
| `dry_run` | `bool` | `false` | Return the query plan instead of executing |
| `max_rows` | `int` | `100` | Maximum rows to return |

**Example response (SELECT):**

```json
{
  "results": [{"id": 1, "name": "Alice"}],
  "row_count": 1,
  "truncated": false
}
```

**Example response (dry run):**

```json
{
  "query_plan": [{"id": 0, "parent": 0, "detail": "SCAN users"}]
}
```

### `get_table_info`

Get complete schema and metadata for a table.

| Parameter | Type | Description |
|---|---|---|
| `table` | `str` | The table name to inspect |

**Example response:**

```json
{
  "table": "users",
  "columns": [
    {"name": "id", "type": "INTEGER", "nullable": false, "default": null, "primary_key": true},
    {"name": "name", "type": "TEXT", "nullable": true, "default": null, "primary_key": false}
  ],
  "ddl": "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)",
  "indexes": [],
  "foreign_keys": [],
  "row_count": 42
}
```

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
