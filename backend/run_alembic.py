#!/usr/bin/env python
"""
Wrapper to run alembic with SQLAlchemy FastIntFlag Python 3.14 fix.
Uses import hook to patch sqlalchemy.util.langhelpers before it's used.
"""
import sys
import importlib.abc
import importlib.util

class SQLAlchemyLanghelpersPatcher(importlib.abc.MetaPathFinder):
    """Import hook to patch sqlalchemy.util.langhelpers.FastIntFlag on import."""
    
    def find_spec(self, fullname, path, target=None):
        if fullname == 'sqlalchemy.util.langhelpers':
            # Found the target module - load and patch it
            spec = importlib.util.find_spec(fullname)
            if spec and spec.loader:
                # Wrap the loader to patch after module execution
                original_loader = spec.loader
                
                class PatchedLoader:
                    def __init__(self, loader):
                        self.loader = loader
                    
                    def create_module(self, spec):
                        return self.loader.create_module(spec)
                    
                    def exec_module(self, module):
                        self.loader.exec_module(module)
                        # Patch FastIntFlag after module execution
                        self._patch_fastintflag(module)
                        return module
                    
                    def _patch_fastintflag(self, module):
                        if hasattr(module, 'FastIntFlag'):
                            original = module.FastIntFlag
                            
                            class PatchedFastIntFlag(original):
                                def __new__(cls, value, *args, **kwargs):
                                    # Handle Python 3.14 __firstlineno__ attribute
                                    if isinstance(value, int) and hasattr(value, '__firstlineno__'):
                                        return super().__new__(cls, int(value))
                                    return super().__new__(cls, value)
                            
                            module.FastIntFlag = PatchedFastIntFlag
                            print("Patched sqlalchemy.util.langhelpers.FastIntFlag for Python 3.14", file=sys.stderr)
                
                spec.loader = PatchedLoader(original_loader)
                return spec
        return None

# Install the import hook BEFORE any SQLAlchemy imports
sys.meta_path.insert(0, SQLAlchemyLanghelpersPatcher())

# Now run alembic
from alembic.config import main
sys.exit(main())