import unittest
from field_extractor import (
    extract_fields,
    extract_mrp,
    extract_quantity,
    extract_country_of_origin,
    extract_manufacturer,
    extract_batch_number,
    get_confidence,
    safe_confidence
)
from compliance_engine import check_compliance, is_applicable
from rules import RULES, validate_fields


class TestFieldExtractor(unittest.TestCase):

    def test_safe_confidence_without_confidence_key(self):
        words = [
            {"text": "MRP"},
            {"text": "100"}
        ]
        # Should not raise KeyError
        conf = safe_confidence(words)
        self.assertEqual(conf, 0.0)

    def test_mrp_extraction_with_commas(self):
        words = [
            {"text": "MRP", "confidence": 95},
            {"text": "Rs.", "confidence": 90},
            {"text": "1,299.50", "confidence": 92}
        ]
        result = extract_mrp(words)
        self.assertIsNotNone(result)
        self.assertEqual(result["value"], 1299.50)

    def test_net_quantity_extraction(self):
        words = [
            {"text": "NET", "confidence": 90},
            {"text": "WEIGHT:", "confidence": 88},
            {"text": "250g", "confidence": 95}
        ]
        result = extract_quantity(words)
        self.assertIsNotNone(result)
        self.assertEqual(result["value"], "250 g")

    def test_multi_word_country_of_origin(self):
        words = [
            {"text": "Made", "confidence": 90},
            {"text": "in", "confidence": 90},
            {"text": "Great", "confidence": 92},
            {"text": "Britain", "confidence": 94}
        ]
        result = extract_country_of_origin(words)
        self.assertIsNotNone(result)
        self.assertEqual(result["value"], "Great Britain")

    def test_multi_word_manufacturer(self):
        words = [
            {"text": "Manufactured", "confidence": 90},
            {"text": "by:", "confidence": 90},
            {"text": "Acme", "confidence": 92},
            {"text": "Consumer", "confidence": 85},
            {"text": "Products", "confidence": 88},
            {"text": "Ltd", "confidence": 90}
        ]
        result = extract_manufacturer(words)
        self.assertIsNotNone(result)
        self.assertIn("Acme", result["value"])

    def test_batch_number_extraction(self):
        words = [
            {"text": "Batch", "confidence": 90},
            {"text": "No:", "confidence": 88},
            {"text": "LOT9921", "confidence": 95}
        ]
        result = extract_batch_number(words)
        self.assertIsNotNone(result)
        self.assertEqual(result["value"], "LOT9921")


class TestComplianceEngine(unittest.TestCase):

    def test_compliant_product(self):
        fields = {
            "mrp": {"value": 150.0},
            "net_quantity": {"value": "100 g"},
            "manufacturing_date": {"value": "10/2024"},
            "best_before": {"value": "24 months"},
            "product_name": {"value": "Ayurvedic Soap"},
            "country_of_origin": {"value": "India"},
            "manufacturer": {"value": "Acme Ltd"},
            "consumer_care": {"value": "care@acme.com"},
            "batch_number": {"value": "B123"},
            "unit_sale_price": {"value": 1.50}
        }
        report = check_compliance(fields)
        self.assertEqual(report["status"], "COMPLIANT")
        self.assertEqual(len(report["violations"]), 0)

    def test_non_compliant_status_when_high_severity_field_missing(self):
        fields = {
            "mrp": None,  # High severity missing
            "net_quantity": {"value": "100 g"},
            "product_name": {"value": "Soap"}
        }
        report = check_compliance(fields)
        self.assertEqual(report["status"], "NON_COMPLIANT")
        self.assertGreater(len(report["violations"]), 0)

    def test_validate_fields_legacy(self):
        fields = {
            "mrp": "100",  # String instead of dict
            "net_quantity": None
        }
        # Should not raise AttributeError
        violations = validate_fields(fields)
        self.assertIsInstance(violations, list)


if __name__ == "__main__":
    unittest.main()
