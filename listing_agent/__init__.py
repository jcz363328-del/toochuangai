"""Compatibility for the original listing_agent package import."""

import sys

from Department.流程与AI部.listing_agent import blueprint, listing_agent_bp

sys.modules[f"{__name__}.blueprint"] = blueprint
