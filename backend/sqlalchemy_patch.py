"""
Monkey patch for SQLAlchemy FastIntFlag Python 3.14 compatibility.
Must be imported before any SQLAlchemy modules.
"""
import enum
import sys

# Patch enum.Flag to handle Python 3.14's __firstlineno__ changes
# The issue is in SQLAlchemy's FastIntFlag which uses enum.Flag
# Python 3.14 changed how enum.Flag handles canonical symbols

original_flag_new = enum.Flag.__new__

def patched_flag_new(cls, value, *args, **kwargs):
    # Handle the __firstlineno__ attribute that Python 3.14 adds
    if hasattr(value, '__firstlineno__') and isinstance(value, int):
        # Strip the __firstlineno__ attribute for enum creation
        return original_flag_new(cls, int(value), *args, **kwargs)
    return original_flag_new(cls, value, *args, **kwargs)

enum.Flag.__new__ = staticmethod(patched_flag_new)

# Also patch IntFlag if it exists
if hasattr(enum, 'IntFlag'):
    original_intflag_new = enum.IntFlag.__new__
    
    def patched_intflag_new(cls, value, *args, **kwargs):
        if hasattr(value, '__firstlineno__') and isinstance(value, int):
            return original_intflag_new(cls, int(value), *args, **kwargs)
        return original_intflag_new(cls, value, *args, **kwargs)
    
    enum.IntFlag.__new__ = staticmethod(patched_intflag_new)

print("Applied SQLAlchemy FastIntFlag Python 3.14 compatibility patch")