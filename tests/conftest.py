"""Root conftest.py to setup Python path for all tests.

This module sets up the Python path to allow imports from the custom component.
All tests must use:
  - from custom_components.intelligent_heating_pilot.domain.value_objects import ...
"""

import sys
from pathlib import Path

# Add repository root to sys.path so that custom_components can be imported
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))
