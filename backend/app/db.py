import os
from contextlib import contextmanager

import pymysql
from dotenv import load_dotenv


load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))


def connect():
    """Open a new connection to MySQL using the settings in .env."""
    return pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "six_degrees"),
        cursorclass=pymysql.cursors.DictCursor,  # rows come back as dicts
        autocommit=True,
    )


def query(sql, params=None):
    """Run a SELECT and return all rows."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()
    finally:
        conn.close()


@contextmanager
def transaction():
    """
    Run several statements as one unit: all are saved, or none are.

        with db.transaction() as cur:
            cur.execute("INSERT ...", (...))
            cur.execute("INSERT ...", (...))

    If anything inside raises an error, every change in the block is undone.
    """
    conn = connect()
    try:
        conn.begin()
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute(sql, params=None):
    """Run an INSERT/UPDATE/DELETE and return the new row's id."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.lastrowid
    finally:
        conn.close()