"""Root conftest.py to setup Python path for all tests."""
import sys
from pathlib import Path

# Patch sqlite3 to use pysqlite3 (with newer SQLite version) for HA recorder tests
try:
    import pysqlite3

    sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
except ImportError:
    pass

# Add repository root to sys.path so that custom_components can be imported
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))
