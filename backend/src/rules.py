RULES = {

    "PC-001": {
        "field": "manufacturer",
        "name": "Manufacturer / Packer / Importer",
        "severity": "HIGH",
        "message": "Name and address of manufacturer, packer or importer could not be detected.",
        "source": "Rule 6"
    },

    "PC-002": {
        "field": "country_of_origin",
        "name": "Country of Origin",
        "severity": "MEDIUM",
        "message": "Country of origin could not be detected for an imported product.",
        "source": "Rule 6",
        "condition": "imported"
    },

    "PC-003": {
        "field": "product_name",
        "name": "Common / Generic Name",
        "severity": "HIGH",
        "message": "Common or generic name of the commodity could not be detected.",
        "source": "Rule 6"
    },

    "PC-004": {
        "field": "net_quantity",
        "name": "Net Quantity",
        "severity": "HIGH",
        "message": "Net quantity could not be detected.",
        "source": "Rule 6"
    },

    "PC-005": {
        "field": "manufacturing_date",
        "name": "Manufacturing / Packing Date",
        "severity": "MEDIUM",
        "message": "Month and year of manufacture, packing or import could not be detected.",
        "source": "Rule 6"
    },

    "PC-006": {
        "field": "best_before",
        "name": "Best Before / Use By",
        "severity": "HIGH",
        "message": "Best before / use by declaration could not be detected.",
        "source": "Rule 6"
    },

    "PC-007": {
        "field": "mrp",
        "name": "Maximum Retail Price",
        "severity": "HIGH",
        "message": "MRP declaration could not be detected.",
        "source": "Rule 6"
    },

    "PC-008": {
        "field": "consumer_care",
        "name": "Consumer Care Details",
        "severity": "MEDIUM",
        "message": "Consumer care details could not be detected.",
        "source": "Rule 6"
    },

    "PC-009": {
        "field": "batch_number",
        "name": "Batch / Lot / Code Number",
        "severity": "MEDIUM",
        "message": "Batch, lot or code number could not be detected.",
        "source": "Rule 6"
    },

    "PC-010": {
        "field": "unit_sale_price",
        "name": "Unit Sale Price",
        "severity": "MEDIUM",
        "message": "Unit sale price could not be detected.",
        "source": "Rule 6"
    }
}


# ============================================================
# VALIDATE EXTRACTED FIELDS
# ============================================================

def validate_fields(fields):

    violations = []

    for rule_id, rule in RULES.items():

        field = rule["field"]
        result = fields.get(field)

        # Field was not extracted at all
        if result is None:

            violations.append({
                "rule_id": rule_id,
                "field": field,
                "name": rule["name"],
                "severity": rule["severity"],
                "message": rule["message"],
                "source": rule["source"]
            })

            continue

        # Extract value safely whether result is dict or raw value
        if isinstance(result, dict):
            extracted_value = result.get("value")
        else:
            extracted_value = result

        # Field exists but contains no value
        if extracted_value is None or str(extracted_value).strip() == "":

            violations.append({
                "rule_id": rule_id,
                "field": field,
                "name": rule["name"],
                "severity": rule["severity"],
                "message": rule["message"],
                "source": rule["source"]
            })

    return violations