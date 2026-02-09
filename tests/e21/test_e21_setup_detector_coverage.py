from src.e21.scenarios import default_context
from src.strategies.common.foundation import SETUP_FAMILIES
from src.strategies.common.foundation_detectors import detect_setup_family


def test_setup_detector_coverage():
    context = default_context()
    for setup_family_id in SETUP_FAMILIES:
        result = detect_setup_family(setup_family_id, context)
        assert result.setup_family_id == setup_family_id
