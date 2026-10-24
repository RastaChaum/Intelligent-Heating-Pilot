"""REST API handlers for the Intelligent Heating Pilot integration.

NOTE: REST API endpoints are not used in IHP v0.5.0+.
All functionality is exposed via Home Assistant services:
- service: intelligent_heating_pilot.calculate_anticipated_start_time
- service: intelligent_heating_pilot.reset_learning

See __init__.py for service implementations.

This file is kept for future REST API extensions if needed.
"""

from __future__ import annotations
