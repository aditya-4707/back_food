from rules import RULES


def is_applicable(rule, fields):
    """
    Determine whether a Legal Metrology rule applies to this product.
    """
    condition = rule.get("condition")

    if condition is None:
        return True

    if condition == "imported":
        # Check explicit flag first
        if "is_imported" in fields:
            return bool(fields["is_imported"])

        # Infer from extracted country_of_origin
        origin_res = fields.get("country_of_origin")
        if isinstance(origin_res, dict):
            val = str(origin_res.get("value") or "").strip().lower()
            if val and val not in {"india", "bharat", "ind"}:
                return True

        return False

    if condition == "where_applicable":
        return True

    return True


def _field_confidence(result):
    """Return confidence value from a field result dict."""
    if isinstance(result, dict):
        try:
            return float(result.get("confidence") or 0.0)
        except (ValueError, TypeError):
            return 0.0
    return 0.0


def check_compliance(fields):
    """
    Check extracted fields against Legal Metrology (Rule 6) rules.

    Severity tiers:
      - HIGH missing  → VIOLATION  → NON_COMPLIANT
      - MEDIUM missing → VERIFICATION → NEEDS_VERIFICATION
      - LOW / present  → PASSED

    Low-confidence detections (< 0.40) are treated as not found for
    HIGH-severity fields, flagged for verification for MEDIUM-severity fields.
    """
    passed       = []
    verification = []
    violations   = []

    LOW_CONF_THRESHOLD = 0.40   # default: below this, treat as "uncertain"

    # Numeric fields are self-validating (we can see the number clearly)
    # so use a lower threshold before flagging them for verification
    NUMERIC_FIELDS = {"mrp", "net_quantity", "unit_sale_price"}

    for rule_id, rule in RULES.items():

        # ── Applicability check ──────────────────────────────────────
        if not is_applicable(rule, fields):
            continue

        field_name   = rule["field"]
        severity     = rule.get("severity", "MEDIUM")
        result       = fields.get(field_name)

        # ── Determine extracted value ────────────────────────────────
        extracted_value = None
        if isinstance(result, dict):
            extracted_value = result.get("value")
        else:
            extracted_value = result

        has_value = (extracted_value is not None and
                     str(extracted_value).strip() != "")

        # ── Confidence assessment ────────────────────────────────────
        confidence    = _field_confidence(result)
        thresh        = 0.30 if field_name in NUMERIC_FIELDS else LOW_CONF_THRESHOLD
        low_conf      = has_value and confidence < thresh

        # ── Categorise ──────────────────────────────────────────────
        if has_value and not low_conf:
            # Clearly detected ✓
            passed.append({
                "rule_id":    rule_id,
                "field":      field_name,
                "name":       rule["name"],
                "message":    "Required information detected.",
                "confidence": round(confidence, 2),
                "source":     rule.get("source"),
                "value":      str(extracted_value)
            })

        elif has_value and low_conf:
            # Detected but uncertain — always goes to verification
            verification.append({
                "rule_id":    rule_id,
                "field":      field_name,
                "name":       rule["name"],
                "message":    (
                    f"Detected with low confidence ({round(confidence * 100)}%). "
                    "Manual verification recommended."
                ),
                "confidence": round(confidence, 2),
                "source":     rule.get("source"),
                "severity":   severity,
                "value":      str(extracted_value)
            })

        else:
            # Not detected at all
            item = {
                "rule_id":    rule_id,
                "field":      field_name,
                "name":       rule["name"],
                "message":    rule["message"],
                "confidence": 0.0,
                "source":     rule.get("source"),
                "severity":   severity
            }

            if severity == "HIGH":
                violations.append(item)
            else:
                verification.append(item)

    # ── Overall status ───────────────────────────────────────────────
    if violations:
        status = "NON_COMPLIANT"
    elif verification:
        status = "NEEDS_VERIFICATION"
    else:
        status = "COMPLIANT"

    return {
        "status":       status,
        "passed":       passed,
        "verification": verification,
        "violations":   violations,
        "summary": {
            "total_rules":    len(passed) + len(verification) + len(violations),
            "passed":         len(passed),
            "needs_review":   len(verification),
            "violations":     len(violations)
        }
    }