# File: config_loader_v01.py
# Created: 2025-12-16
# Version Notes:
# - v01: Configuration loader and validation skeleton

"""
CONFIGURATION LOADER & VALIDATION ENGINE
----------------------------------------

GLOBAL CONTEXT
--------------
This file loads and validates configuration before the system starts.

If configuration is invalid, the system MUST NOT run.

SOURCE OF TRUTH
---------------
Derived strictly from:
- STEP_22_OUTCOME_CONFIGURATION_LOADER_AND_VALIDATION.md

STANDALONE GUARANTEE
-------------------
This file can be tested independently with sample config files.

TRADING MODE
------------
None — startup only.
"""

# ================================
# 1. Imports
# ================================

import json
from typing import Dict

# YAML is optional; import guarded for environments without it
try:
    import yaml
except ImportError:
    yaml = None

# ================================
# 2. Configuration Loader
# ================================

class ConfigLoader:
    """
    ConfigLoader
    ------------
    Loads configuration from disk.
    """

    def load(self, path: str) -> Dict:
        """
        Load configuration from a file.

        Parameters
        ----------
        path : str
            Path to config file.
        """
        if path.endswith(".json"):
            with open(path, "r") as f:
                return json.load(f)

        if path.endswith(".yaml") or path.endswith(".yml"):
            if not yaml:
                raise RuntimeError("PyYAML not installed")
            with open(path, "r") as f:
                return yaml.safe_load(f)

        raise ValueError("Unsupported config format")

# ================================
# 3. Validation Engine
# ================================

class ConfigValidator:
    """
    ConfigValidator
    ---------------
    Validates configuration correctness.
    """

    def validate(self, config: Dict) -> None:
        """
        Validate configuration.

        Raises
        ------
        ValueError on invalid configuration.
        """
        required_sections = [
            "system",
            "scanner",
            "strategy",
            "risk",
            "execution",
            "storage",
        ]

        for section in required_sections:
            if section not in config:
                raise ValueError(f"Missing config section: {section}")

        # Example rule
        phase = config.get("risk", {}).get("phase_mode")
        if phase not in ("TEST", "LIVE"):
            raise ValueError("risk.phase_mode must be TEST or LIVE")

# ================================
# 4. Standalone Execution
# ================================

if __name__ == "__main__":
    loader = ConfigLoader()
    validator = ConfigValidator()

    # Placeholder example
    cfg = {"system": {}, "scanner": {}, "strategy": {}, "risk": {"phase_mode": "TEST"}, "execution": {}, "storage": {}}
    validator.validate(cfg)
    print("Config valid")

# ================================
# END OF FILE
# ================================
