from app import config


def test_config_constants_exist_with_expected_types():
    assert isinstance(config.MIN_PDF_TEXT_LENGTH, int)
    assert isinstance(config.LOW_OCR_CONFIDENCE_THRESHOLD, float)
    assert isinstance(config.AMOUNT_TOLERANCE_RATIO, float)
    assert "total" in config.REQUIRED_HEADER_FIELDS
    assert "subtotal" in config.REQUIRED_HEADER_FIELDS
    import re
    re.compile(config.CUIT_PATTERN)
    re.compile(config.CAE_PATTERN)
    re.compile(config.DATE_PATTERN)
