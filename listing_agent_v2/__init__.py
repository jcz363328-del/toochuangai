"""Compatibility for the original listing_agent_v2 package import."""

import sys

from Department.流程与AI部.listing_agent_v2 import blueprint, listing_agent_v2_bp

sys.modules[f"{__name__}.blueprint"] = blueprint
