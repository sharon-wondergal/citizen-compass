"""Describes a SQLite database's structure so two databases can be compared.

Used to prove the models match the design tested in Stage 2.
"""

import re

# SQLAlchemy calls this type FLOAT. The design calls it REAL. SQLite treats them alike.
TYPE_ALIASES = {"FLOAT": "REAL"}


def describe_table(connection, table):
    """Return the columns, links, rules and indexes of one table."""
    columns = {}
    for row in connection.execute(f"PRAGMA table_info({table})"):
        _, name, column_type, not_null, default, primary_key = row
        columns[name] = {
            "type": TYPE_ALIASES.get(column_type, column_type),
            # A primary key can never be empty, whether or not NOT NULL is written.
            "not_null": bool(not_null or primary_key),
            "default": default,
            "primary_key": bool(primary_key),
        }

    foreign_keys = sorted(
        (row[3], row[2], row[4], row[6])  # column, target table, target column, on delete
        for row in connection.execute(f"PRAGMA foreign_key_list({table})")
    )

    unique_rules = []
    indexes = []
    for row in connection.execute(f"PRAGMA index_list({table})").fetchall():
        index_name, origin = row[1], row[3]
        index_columns = tuple(
            info[2] for info in connection.execute(f"PRAGMA index_info('{index_name}')")
        )
        if origin == "u":
            unique_rules.append(index_columns)
        elif origin == "c":
            indexes.append(index_columns)

    create_sql = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()[0]
    without_comments = re.sub(r"--[^\n]*", "", create_sql)

    return {
        "columns": columns,
        "foreign_keys": foreign_keys,
        "unique_rules": sorted(unique_rules),
        "indexes": sorted(indexes),
        "check_rule_count": len(re.findall(r"\bCHECK\b", without_comments)),
    }


def describe_database(connection):
    """Return a description of every table, ignoring SQLite's own tables."""
    tables = [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%' AND name <> 'alembic_version'"
        )
    ]
    return {table: describe_table(connection, table) for table in sorted(tables)}
