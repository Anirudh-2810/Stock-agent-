"""
SQLAlchemy FastIntFlag Python 3.14 compatibility patch.
Run this before any SQLAlchemy imports.
"""
import enum
import sys

# Patch enum.Flag to handle Python 3.14's __firstlineno__ changes
_original_flag_new = enum.Flag.__new__

def _patched_flag_new(cls, value, *args, **kwargs):
    if hasattr(value, '__firstlineno__') and isinstance(value, int):
        return _original_flag_new(cls, int(value), *args, **kwargs)
    return _original_flag_new(cls, value, *args, **kwargs)

enum.Flag.__new__ = staticmethod(_patched_flag_new)

if hasattr(enum, 'IntFlag'):
    _original_intflag_new = enum.IntFlag.__new__
    def _patched_intflag_new(cls, value, *args, **kwargs):
        if hasattr(value, '__firstlineno__') and isinstance(value, int):
            return _original_intflag_new(cls, int(value), *args, **kwargs)
        return _original_intflag_new(cls, value, *args, **kwargs)
    enum.IntFlag.__new__ = staticmethod(_patched_intflag_new)

print("Applied SQLAlchemy FastIntFlag Python 3.14 compatibility patch", file=sys.stderr)