"""Bound SQLite values/encoded rows before the driver materializes them in Python."""
import sqlite3
from .codec import Rejected, integer


def set_row_limit(connection, maximum):
    integer(maximum,1024,64*1024*1024)
    category = sqlite3.SQLITE_LIMIT_LENGTH
    previous = connection.getlimit(category)
    # Never expand a tighter runtime limit inherited by a connection.
    if previous < maximum:
        raise Rejected('sqlite_runtime_length_limit_too_small')
    connection.setlimit(category,maximum)
    if connection.getlimit(category) != maximum:
        raise Rejected('sqlite_runtime_length_limit_unavailable')
