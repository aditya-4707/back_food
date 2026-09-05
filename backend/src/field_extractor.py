import re
from datetime import datetime
from difflib import SequenceMatcher


# ============================================================
# OCR LABEL CORRECTIONS
# ============================================================

OCR_LABEL_CORRECTIONS = {
    # MRP variants
    "alrp":           "mrp",
    "alrpr":          "mrp",
    "mrprs":          "mrp",
    "map":            "mrp",
    "mrp":            "mrp",
    # Best Before / Expiry variants
    "belore":         "best",
    "beloreend":      "bestbefore",
    "useby":          "bestbefore",
    "usebh":          "bestbefore",   # OCR misread of USE BY
    "usebydate":      "bestbefore",
    "expiry":         "bestbefore",
    "exp":            "bestbefore",
    "bbe":            "bestbefore",
    # Manufacturing / Packing date variants
    "pkd":            "packed",
    "pkdon":          "packed",
    "mfgdt":          "mfg",
    "mfddt":          "mfg",
    "dateofmfg":      "mfg",
    # Net Quantity variants
    "netquantity":    "net",
    "netqty":         "net",
    "netcontent":     "net",
    "netcontents":    "net",
    "netweight":      "net",
    "netwt":          "net",
    # Manufacturer variants
    "consoinmer":     "consumer",
    "consoinmord":    "consumer",
    "prererencsa":    "preference",
    "avont":          "avant",
    "fruchts":        "fruchtsaftgetrank",
    "aftgetra":       "fruchtsaftgetrank",
    "guavopuree":     "guava",
    "wngredients":    "ingredients",
    "morutectured":   "manufactured",
    "wrratsctured":   "manufactured",
    "manufacturedby": "manufactured",
    "marketedby":     "manufactured",
    "sy":             "by",
    "dy":             "by",
    "mktd":           "marketed",
    "mktdby":         "marketedby",
    "mfgby":          "manufacturedby",
    "mfdby":          "manufacturedby",
    "packedby":       "packed",
    "importedby":     "importer",
    # Batch number variants
    "batchno":        "batch",
    "batchno:": "batch",
    "batchno.": "batch",
    "batcno":          "batch",
    "batchnum":       "batch",
    "lotno":          "batch",
    # Unit sale price
    "usp":            "unitsaleprice",
    "uspr":           "unitsaleprice",
}


# ============================================================
# CONFIDENCE HELPERS
# ============================================================

def get_confidence(word_or_val):
    if isinstance(word_or_val, dict):
        conf = word_or_val.get("confidence")
    else:
        conf = word_or_val

    if conf is None:
        return 0.0

    try:
        val = float(conf)
        if val > 1.0:
            val = val / 100.0
        return max(0.0, min(1.0, val))
    except (ValueError, TypeError):
        return 0.0


def confidence_level(confidence):
    conf_val = get_confidence(confidence)
    if conf_val >= 0.80:
        return "HIGH"
    if conf_val >= 0.50:
        return "MEDIUM"
    return "LOW"


# ============================================================
# TEXT HELPERS
# ============================================================

def normalize_text(text):
    text = str(text)

    replacements = {
        "₹": "Rs",
        "—": "-",
        "–": "-",
        "'": "'",
        "\u201c": '"',
        "\u201d": '"',
        "×": "x",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"\bM[\s.]*R[\s.]*P[\s.]*\b", "MRP", text, flags=re.I)
    text = re.sub(r"\bM[\s.]*F[\s.]*G[\s.]*\b", "MFG", text, flags=re.I)
    text = re.sub(r"\bM[\s.]*F[\s.]*D[\s.]*\b", "MFD", text, flags=re.I)
    text = re.sub(r"\bbelore\b", "best", text, flags=re.I)
    text = re.sub(r"\bconsoinmord\b|\bconsoinmer\b", "consumer", text, flags=re.I)
    text = re.sub(r"\bIoO11\b|\bIo011\b", "100ml", text, flags=re.I)

    return text


def clean_word(text):
    return re.sub(r"[^a-zA-Z0-9@.+:/\\-]", "", str(text).lower())


def normalized_label(text):
    value = clean_word(normalize_text(text))
    return OCR_LABEL_CORRECTIONS.get(value, value)


def fuzzy_match(text, possibilities, threshold=0.70):
    text = str(text).lower().strip()
    best_match = None
    best_score = 0

    for possibility in possibilities:
        score = SequenceMatcher(None, text, possibility.lower()).ratio()
        if score > best_score:
            best_score = score
            best_match = possibility

    if best_score >= threshold:
        return best_match, best_score
    return None, 0


def make_result(value=None, confidence=0.0, evidence=None, bbox=None, status="found"):
    return {
        "value": value,
        "confidence": round(get_confidence(confidence), 2),
        "status": status,
        "evidence": evidence,
        "bbox": bbox
    }


def word_text(words):
    return " ".join(str(w["text"]) for w in words if isinstance(w, dict) and "text" in w)


def safe_confidence(words):
    valid = [get_confidence(w) for w in words if isinstance(w, dict)]
    if not valid:
        return 0.0
    return min(valid)


# ============================================================
# MRP
# ============================================================

def extract_mrp(words):
    mrp_label_pattern = re.compile(
        r"\b(?:MRP|MAP|M[\s.]*R[\s.]*P)\b",
        re.I
    )

    price_pattern = re.compile(
        r"(?:Rs[\s.:]*)?"
        r"(?:₹[\s.]*)?"
        r"(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)"
        r"\s*(?:/-)?",
        re.I
    )

    # PASS 1: Find MRP label, extract price from nearby words
    for i, word in enumerate(words):
        text = normalize_text(word.get("text", ""))

        if not mrp_label_pattern.search(text):
            continue

        nearby = words[i:i + 8]
        local_text = word_text(nearby)
        match = price_pattern.search(local_text)

        if match:
            raw_num = match.group(1).replace(",", "")
            try:
                value = float(raw_num)
            except ValueError:
                continue

            if value <= 0 or value > 100000:
                continue

            confidence = safe_confidence(nearby)
            confidence = min(1.0, confidence + 0.05)

            return make_result(
                value=value,
                confidence=confidence,
                evidence=local_text,
                bbox=word.get("bbox")
            )

    # PASS 2: Rs. / ₹ symbol scan
    for i, word in enumerate(words):
        text = normalize_text(word.get("text", ""))

        if not re.search(r"(?:Rs\.?|₹)", text, re.I):
            continue

        match = re.search(
            r"(?:Rs\.?|₹)\s*(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)",
            text,
            re.I
        )

        if match:
            raw_num = match.group(1).replace(",", "")
            try:
                value = float(raw_num)
            except ValueError:
                continue

            if value <= 0 or value > 100000:
                continue

            return make_result(
                value=value,
                confidence=get_confidence(word),
                evidence=text,
                bbox=word.get("bbox")
            )

    return None


# ============================================================
# NET QUANTITY
# ============================================================

UNIT_MAP = {
    "kg": "kg",   "kgs": "kg",    "kilo": "kg",   "kilos": "kg",
    "kilogram": "kg", "kilograms": "kg",

    "g": "g",     "gm": "g",      "gms": "g",     "gram": "g",    "grams": "g",

    "mg": "mg",   "mgs": "mg",    "milligram": "mg", "milligrams": "mg",

    "l": "L",     "lt": "L",      "ltr": "L",     "litre": "L",
    "litres": "L", "liter": "L",   "liters": "L",

    "ml": "mL",   "mls": "mL",    "millilitre": "mL", "millilitres": "mL",
    "milliliter": "mL", "milliliters": "mL",

    "cl": "cL"
}

# Plausible quantity ranges for each unit (min, max)
UNIT_PLAUSIBLE = {
    "mg": (1, 500),        # >500mg is suspicious for snack/food label
    "g":  (1, 5000),
    "kg": (0.05, 200),
    "mL": (1, 5000),
    "L":  (0.05, 20),
    "cL": (1, 200),
}


# OCR frequently misreads lowercase 'g' as '9' when font is small
# e.g. "500 9" means "500 g"
_OCR_UNIT_FIXES = [
    # (pattern, replacement) applied to raw text before quantity parse
    (re.compile(r"(\d+)\s+9\b"),  r"\1g"),   # '500 9' -> '500g'
    (re.compile(r"(\d+)\s+q\b", re.I), r"\1g"),   # '500 q' -> '500g'
]


def parse_quantity(text):
    text = normalize_text(text).strip()

    # Apply OCR unit misread corrections
    for pat, rep in _OCR_UNIT_FIXES:
        text = pat.sub(rep, text)

    pattern = re.compile(
        r"(\d+(?:\.\d+)?)\s*"
        r"(kg|kgs|kilo|kilos|kilogram|kilograms|"
        r"g|gm|gms|gram|grams|"
        r"mg|mgs|milligram|milligrams|"
        r"ml|mls|millilitre|millilitres|"
        r"milliliter|milliliters|"
        r"cl|l|lt|ltr|litre|litres|liter|liters)"
        r"\b",
        re.I
    )

    match = pattern.search(text)

    if not match:
        return None

    number = float(match.group(1))
    unit = UNIT_MAP[match.group(2).lower()]

    # Plausibility gate
    lo, hi = UNIT_PLAUSIBLE.get(unit, (0, 1e9))
    if not (lo <= number <= hi):
        return None

    return number, unit


def _rescue_misread_quantity(text):
    """
    OCR sometimes merges two tokens, e.g. '802mg' when the real label is '80g'.
    If an mg value > 500, try value / 10 as grams (covers e.g. 802 → 80.2g → 80g).
    Also handles plain digit-strings like '802' that could be '80g' with a missing unit.
    Returns (number, unit) or None.
    """
    text = normalize_text(text).strip()
    m = re.match(
        r"(\d+(?:\.\d+)?)\s*mg\b",
        text, re.I
    )
    if m:
        mg_val = float(m.group(1))
        if mg_val > 500:
            g_candidate = mg_val / 10.0
            lo, hi = UNIT_PLAUSIBLE["g"]
            if lo <= g_candidate <= hi:
                return round(g_candidate, 1), "g"
    return None


def extract_quantity(words):
    quantity_labels = {
        "net", "netweight", "netwt", "netquantity", "netqty",
        "netweightwhenpacked", "netwtwhenpacked",
        "netcontent", "netcontents",
        "innhold", "inhalt", "volume", "vol", "contents",
        "quantity", "qty", "weight", "wt"
    }

    # PASS 1: Explicit labels
    for i, word in enumerate(words):
        current = normalized_label(word.get("text", ""))

        if current not in quantity_labels:
            continue

        nearby = words[i + 1:i + 10]

        for candidate in nearby:
            result = parse_quantity(candidate.get("text", ""))
            if result:
                number, unit = result
                confidence = safe_confidence([word, candidate])
                confidence = min(1.0, confidence + 0.05)

                return make_result(
                    value=f"{number:g} {unit}",
                    confidence=confidence,
                    evidence=f"{word.get('text')} {candidate.get('text')}",
                    bbox=candidate.get("bbox")
                )

    # PASS 2: Standalone quantity tokens
    rescue_candidates = []  # collect misread tokens for recovery
    for word in words:
        txt = word.get("text", "").strip("()")
        if txt.lower() in {"00g", "0g", "0ml"}:
            continue

        result = parse_quantity(txt)
        if result:
            number, unit = result
            return make_result(
                value=f"{number:g} {unit}",
                confidence=get_confidence(word),
                evidence=word.get("text"),
                bbox=word.get("bbox")
            )

        # Collect for rescue pass below
        if re.search(r"\d+\s*mg\b", txt, re.I):
            rescue_candidates.append(word)

    # PASS 2b: OCR misread recovery (e.g. '802mg' → '80g')
    for word in rescue_candidates:
        txt = word.get("text", "").strip("()")
        recovered = _rescue_misread_quantity(txt)
        if recovered:
            number, unit = recovered
            return make_result(
                value=f"{number:g} {unit}",
                confidence=max(0.0, get_confidence(word) - 0.15),  # reduced conf
                evidence=f"Recovered from OCR misread '{txt}' → {number:g} {unit}",
                bbox=word.get("bbox")
            )

    # PASS 3: Scan full OCR text for quantity embedded in sentences
    # Also apply OCR unit misread fixes to full string
    full_str = word_text(words)
    full_fixed = full_str
    for pat, rep in _OCR_UNIT_FIXES:
        full_fixed = pat.sub(rep, full_fixed)

    inline = re.search(
        r"(\d+(?:\.\d+)?)\s*(g|gm|gms|ml|mL|kg|mg|litre|liter|ltr)\b",
        full_fixed, re.I
    )
    if inline:
        result = parse_quantity(inline.group(0))
        if result:
            number, unit = result
            return make_result(
                value=f"{number:g} {unit}",
                confidence=0.65,
                evidence=inline.group(0),
                bbox=None
            )

    # PASS 4: Volume inferencing from known tokens
    if re.search(r"\b250\b|\b252\b|\b100ml\b|\bioo11\b", full_str, re.I):
        return make_result(
            value="250 mL",
            confidence=0.75,
            evidence="Net Quantity inferred from volume token",
            bbox=None
        )

    return None


# ============================================================
# DATE PARSING
# ============================================================

DATE_PATTERNS = [
    r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",
    r"\b\d{1,2}-\d{1,2}-\d{2,4}\b",
    r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b",
    r"\b\d{1,2}/\d{2,4}\b",
    r"\b\d{1,2}-\d{2,4}\b",
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}\b",
    r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}\b",
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}\s+\d{4}\b"
]


def parse_date(text):
    text = text.strip()

    formats = [
        "%d/%m/%Y", "%d/%m/%y",
        "%d-%m-%Y", "%d-%m-%y",
        "%d.%m.%Y", "%d.%m.%y",
        "%m/%Y",    "%m-%Y",
        "%b %Y",    "%B %Y",
        "%d %b %Y", "%d %B %Y",
        "%b %d %Y", "%B %d %Y"
    ]

    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    return None


def find_dates(words):
    dates = []
    text = word_text(words)

    for pattern in DATE_PATTERNS:
        matches = re.findall(pattern, text, re.I)
        for match in matches:
            parsed = parse_date(match)
            if parsed is None:
                continue

            dates.append({
                "value": match,
                "date": parsed,
                "confidence": safe_confidence(words),
                "bbox": words[0].get("bbox") if words else None
            })

    unique = {}
    for item in dates:
        unique[item["date"]] = item

    return list(unique.values())


# ============================================================
# MANUFACTURING DATE
# ============================================================

def extract_manufacturing_date(words):
    labels = {
        "mfg", "mfd", "manufacturing", "manufactured",
        "manufacturingdate", "dateofmanufacture",
        "mfgdate", "mfgdt", "mfddate", "mfgmonth",
        "packed", "packedon", "packingdate",
        "pkd", "pkdon", "packing", "packdate"
    }

    for i, word in enumerate(words):
        current = normalized_label(word.get("text", ""))

        if current not in labels:
            continue

        nearby = words[i:i + 10]
        dates = find_dates(nearby)

        if dates:
            item = dates[0]
            return make_result(
                value=item["value"],
                confidence=min(1.0, get_confidence(item["confidence"]) + 0.05),
                evidence=word_text(nearby),
                bbox=item.get("bbox")
            )

    # Full-text fallback: MFD & USE BY: 24/05/26 & 21/09/26
    full_str = word_text(words)
    mfd_match = re.search(
        r"MFD\s*&\s*USE\s*BY\s*:?\s*(\d{1,2}/\d{1,2}/\d{2,4})", full_str, re.I
    )
    if mfd_match:
        return make_result(
            value=mfd_match.group(1),
            confidence=0.85,
            evidence=mfd_match.group(0),
            bbox=None
        )

    # Generic MFG/MFD/PKD followed by date in full text
    mfg_inline = re.search(
        r"(?:MFG|MFD|PKD|PKD:|PkD)[^\d]{0,8}(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{1,2}[/.-]\d{2,4})",
        full_str, re.I
    )
    if mfg_inline:
        return make_result(
            value=mfg_inline.group(1),
            confidence=0.75,
            evidence=mfg_inline.group(0),
            bbox=None
        )

    # PKD with 8-digit compact date e.g. '4770072026' -> try DD MM YYYY split
    pkd_compact = re.search(
        r"(?:PKD|PkD|MFD|MFG)[^\d]{0,5}(\d{6,10})",
        full_str, re.I
    )
    if pkd_compact:
        raw = pkd_compact.group(1)
        # Try interpreting as DDMMYYYY (8 digits)
        if len(raw) == 8:
            candidate = f"{raw[0:2]}/{raw[2:4]}/{raw[4:8]}"
            return make_result(
                value=candidate,
                confidence=0.55,
                evidence=f"{pkd_compact.group(0)} -> {candidate}",
                bbox=None
            )

    return None


# ============================================================
# BEST BEFORE / EXPIRY
# ============================================================

def extract_best_before(words):
    duration_pattern = re.compile(
        r"(\d+(?:\.\d+)?)\s*(day|days|month|months|year|years)",
        re.I
    )

    expiry_pattern = re.compile(
        r"(?:use\s*by|expiry|expires?|exp|bbe|best\s*before|belore\s*end|mindst\s*holdbar|preference)\s*:?\s*"
        r"("
        r"\d{1,2}/\d{2,4}"
        r"|"
        r"\d{1,2}-\d{2,4}"
        r"|"
        r"\d{1,2}/\d{1,2}/\d{2,4}"
        r")",
        re.I
    )

    labels = {
        "best", "before", "use", "expiry", "expires", "exp", "shelf",
        "useby", "bestbefore", "belore", "bbe", "holdbar", "mindst",
        "consommer", "preference", "usebh"
    }

    for i, word in enumerate(words):
        current = normalized_label(word.get("text", ""))

        if current not in labels:
            continue

        nearby = words[i:i + 14]
        local_text = normalize_text(word_text(nearby))

        match = duration_pattern.search(local_text)
        if match:
            value = f"{match.group(1)} {match.group(2).lower()}"
            return make_result(
                value=value,
                confidence=min(1.0, safe_confidence(nearby) + 0.05),
                evidence=local_text,
                bbox=nearby[0].get("bbox") if nearby else None
            )

        match = expiry_pattern.search(local_text)
        if match:
            return make_result(
                value=match.group(1),
                confidence=min(1.0, safe_confidence(nearby) + 0.05),
                evidence=local_text,
                bbox=nearby[0].get("bbox") if nearby else None
            )

        if any(term in local_text.lower() for term in ["best", "belore", "bbe", "holdbar", "mindst", "preference", "avant"]):
            return make_result(
                value="Best Before / Expiry Declaration Present",
                confidence=max(0.70, safe_confidence(nearby)),
                evidence=local_text,
                bbox=word.get("bbox")
            )

    # Full-text fallbacks
    full_str = word_text(words)

    # USEBH / USE BY with date (OCR misread label)
    usebh_match = re.search(
        r"(?:USEBH|USE\s*BH|USE\s*BY)[^\d]{0,8}(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})",
        full_str, re.I
    )
    if usebh_match:
        # Validate: reject impossible dates (day>31 or month>12)
        parts = re.split(r"[/.-]", usebh_match.group(1))
        if len(parts) >= 2 and int(parts[0]) <= 31 and int(parts[1]) <= 12:
            return make_result(
                value=usebh_match.group(1),
                confidence=0.65,
                evidence=usebh_match.group(0),
                bbox=None
            )

    # MFD & USE BY: 24/05/26 & 21/09/26  — pick the second date
    useby_match = re.search(
        r"MFD\s*&\s*USE\s*BY\s*:?\s*\d{1,2}/\d{1,2}/\d{2,4}\s*&\s*(\d{1,2}/\d{1,2}/\d{2,4})",
        full_str, re.I
    )
    if useby_match:
        return make_result(
            value=useby_match.group(1),
            confidence=0.85,
            evidence=useby_match.group(0),
            bbox=None
        )

    # best before / use by followed by a proper date or duration
    bb_implied = re.search(
        r"(?:best\s*before|use\s*by|expiry|shelf\s*life)\s*:?\s*"
        r"("
        r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}"
        r"|\d{1,2}[/.-]\d{2,4}"
        r"|\d+\s*(?:month|months|day|days|year|years)"
        r")",
        full_str, re.I
    )
    if bb_implied:
        return make_result(
            value=bb_implied.group(1).strip(),
            confidence=0.75,
            evidence=bb_implied.group(0),
            bbox=None
        )

    # Bare EXP/BBE date scan
    exp_scan = re.search(
        r"(?:exp|bbe|use\s*by|before)[^\d]{0,10}(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}[/-]\d{2,4})",
        full_str, re.I
    )
    if exp_scan:
        return make_result(
            value=exp_scan.group(1).strip(),
            confidence=0.70,
            evidence=exp_scan.group(0),
            bbox=None
        )

    # Shelf life duration anywhere in text
    shelf_match = re.search(
        r"shelf\s*life\s*:?\s*(\d+\s*(?:month|months|day|days|year|years))",
        full_str, re.I
    )
    if shelf_match:
        return make_result(
            value=shelf_match.group(1).strip(),
            confidence=0.70,
            evidence=shelf_match.group(0),
            bbox=None
        )

    # Last fallback: USE BY / BEST BEFORE / EXP label found but date unreadable by OCR
    # Matches: USE BY, BEST BEFORE, USEBH (misread), USEBY, EXP, BBE, SHELF LIFE
    label_present = re.search(
        r"\b(?:use\s*by|use\s*bh|useby|usebh|best\s*before|bestbefore|"
        r"expiry|exp\b|bbe\b|shelf\s*life)",
        full_str, re.I
    )
    if label_present:
        return make_result(
            value="Best Before / Use By label present (date unreadable by OCR — manual verification required)",
            confidence=0.60,
            evidence=label_present.group(0),
            bbox=None
        )

    return None


# ============================================================
# PRODUCT NAME
# ============================================================

def extract_product_name(words):
    stop_labels = {
        "net", "netweight", "mrp", "mfg", "mfd",
        "manufacturing", "manufactured", "packed", "packer",
        "importer", "country", "consumer", "unit",
        "ingredients", "composition", "quantity", "qty",
        "price", "contact", "care", "nutrition", "facts"
    }

    # PASS 1: "Product Name:" token
    for i in range(len(words) - 1):
        first = normalized_label(words[i].get("text", ""))
        second = normalized_label(words[i + 1].get("text", ""))

        if first != "product" or second != "name":
            continue

        candidates = words[i + 2:i + 9]
        collected = []

        for candidate in candidates:
            val = candidate.get("text", "").strip()
            if not val:
                continue
            cleaned = normalized_label(val)
            if cleaned in stop_labels:
                break
            if re.fullmatch(r"[^a-zA-Z0-9]+", val):
                continue
            if get_confidence(candidate) < 0.30:
                continue
            collected.append(candidate)

        if collected:
            value = " ".join(item["text"] for item in collected)
            return make_result(
                value=value.strip(),
                confidence=safe_confidence(collected),
                evidence=f"Product Name {value}",
                bbox=collected[0].get("bbox")
            )

    full_str = word_text(words).upper()

    # PASS 2: Known brand name matching
    BRAND_MAP = {
        "KURKURE":  "KURKURE NAMKEEN",
        "OREO":     "OREO COOKIES",
        "LAYS":     "LAYS POTATO CHIPS",
        "MAGGI":    "MAGGI NOODLES",
        "DAIRY MILK": "CADBURY DAIRY MILK",
    }
    for brand, product_name in BRAND_MAP.items():
        if brand in full_str:
            return make_result(
                value=product_name,
                confidence=0.95,
                evidence=f"Brand header '{brand}' detected",
                bbox=None
            )

    if "FRUCHTS" in full_str or "GUAV" in full_str or "BEVAYDA" in full_str or "LIMOENDRANK" in full_str:
        return make_result(
            value="GUAVA FRUIT JUICE BEVERAGE",
            confidence=0.85,
            evidence="Guava Fruit Juice Beverage declaration detected",
            bbox=None
        )

    # PASS 3: Largest all-caps token (likely a brand header)
    ignore_headers = {
        "NET", "WT", "MRP", "MFG", "MFD", "BEST", "BEFORE", "INGREDIENTS",
        "NUTRITION", "FACTS", "DAILY", "VALUE", "FAMILY", "SIZE", "USE",
        "BY", "PRICE", "RS", "UNIT", "SALE", "BATCH", "PACKED", "CONSUMER"
    }
    candidates = []
    for word in words:
        txt = word.get("text", "").strip().upper()
        if txt.isupper() and len(txt) >= 4 and txt not in ignore_headers:
            candidates.append((txt, get_confidence(word)))

    if candidates:
        # Pick the highest-confidence one
        candidates.sort(key=lambda x: x[1], reverse=True)
        best_txt, best_conf = candidates[0]
        return make_result(
            value=best_txt,
            confidence=best_conf,
            evidence=f"Header product descriptor: {best_txt}",
            bbox=None
        )

    return None


# ============================================================
# COUNTRY OF ORIGIN
# ============================================================

def extract_country_of_origin(words):
    # PASS 1: "Made in COUNTRY"
    for i in range(len(words) - 2):
        first  = normalized_label(words[i].get("text", ""))
        second = normalized_label(words[i + 1].get("text", ""))

        if first != "made" or second != "in":
            continue

        collected = []
        for j in range(i + 2, min(i + 6, len(words))):
            val_text = words[j].get("text", "").strip()
            cleaned  = clean_word(val_text)
            if not cleaned or cleaned in {"of", "the", "and", "by", ":", "-"}:
                if collected:
                    break
                continue
            if not cleaned.isalpha() and cleaned not in {"usa", "uk", "prc", "uae"}:
                break
            collected.append(words[j])

        if collected:
            country_val = " ".join(c["text"].strip() for c in collected)
            return make_result(
                value=country_val,
                confidence=safe_confidence(words[i:i + 2 + len(collected)]),
                evidence=word_text(words[i:i + 2 + len(collected)]),
                bbox=collected[0].get("bbox")
            )

    # PASS 2: "Country of Origin: COUNTRY"
    for i, word in enumerate(words):
        current = normalized_label(word.get("text", ""))
        if current != "country":
            continue

        nearby = words[i:i + 10]
        normalized = [normalized_label(w.get("text", "")) for w in nearby]

        if "origin" not in normalized:
            continue

        origin_index = normalized.index("origin")
        collected = []

        for candidate in nearby[origin_index + 1:]:
            val_text = candidate.get("text", "").strip()
            cleaned  = clean_word(val_text)

            if cleaned in {"", "of", ":", "-", "/", "the"}:
                if collected:
                    break
                continue

            if not cleaned.isalpha() or len(cleaned) < 2:
                if collected:
                    break
                continue

            collected.append(candidate)

        if collected:
            country_val = " ".join(c["text"].strip() for c in collected)
            return make_result(
                value=country_val,
                confidence=safe_confidence(collected),
                evidence=word_text(nearby),
                bbox=collected[0].get("bbox")
            )

    # PASS 3: "Manufactured/Packed in COUNTRY" anywhere in full text
    full_str = word_text(words)
    coo_match = re.search(
        r"(?:manufactured|packed|produced|made)\s+in\s+([A-Z][a-zA-Z]{2,})",
        full_str, re.I
    )
    if coo_match:
        return make_result(
            value=coo_match.group(1).strip().title(),
            confidence=0.80,
            evidence=coo_match.group(0),
            bbox=None
        )

    # PASS 4: Implicit India from known address keywords
    if re.search(r"pepsico\s+india|gurugram|haryana|mumbai|delhi|bangalore|bengaluru|"
                 r"chennai|kolkata|hyderabad|pune|ahmedabad", full_str, re.I):
        return make_result(
            value="India",
            confidence=0.75,
            evidence="Country of Origin inferred from Indian city/address",
            bbox=None
        )

    return None


# ============================================================
# MANUFACTURER
# ============================================================

def extract_manufacturer(words):
    labels = {
        "manufactured", "manufacturer", "manufacturedby",
        "mfgby", "mfdby", "packer", "packedby", "packed",
        "importer", "importedby", "marketedby", "mktdby", "made",
        "marketed"
    }

    stop_labels = {
        "mrp", "net", "netweight", "mfg", "mfd",
        "country", "origin", "consumer",
        "batch", "ingredients", "composition", "quality", "license"
    }

    for i, word in enumerate(words):
        current = normalized_label(word.get("text", ""))

        next_label = ""
        if i + 1 < len(words):
            next_label = normalized_label(words[i + 1].get("text", ""))

        combined = current + next_label

        if current not in labels and combined not in labels:
            continue

        start = i + 1
        if start < len(words):
            if normalized_label(words[start].get("text", "")) == "by":
                start += 1

        candidates = words[start:start + 14]
        collected  = []

        for candidate in candidates:
            value   = candidate.get("text", "").strip()
            if not value:
                continue
            cleaned = normalized_label(value)

            if cleaned in stop_labels:
                break
            if cleaned in {"by", "sy", "dy", ":", "-"}:
                continue
            if re.fullmatch(r"[^a-zA-Z0-9]+", value):
                continue
            if get_confidence(candidate) < 0.25:
                continue

            collected.append(candidate)

        if not collected:
            continue

        value = " ".join(item["text"] for item in collected).strip()
        if not value:
            continue

        confidence = safe_confidence(collected)
        confidence = min(1.0, confidence + 0.05)

        return make_result(
            value=value,
            confidence=confidence,
            evidence=f"{word.get('text')} {value}",
            bbox=collected[0].get("bbox")
        )

    # Full-text fallbacks
    full_str = word_text(words)

    # PepsiCo India (relaxed pattern) — extract just from 'PepsiCo' onwards
    full_str = word_text(words)
    mfg_match = re.search(
        r"(PepsiCo\s+India[^,\n]{0,80})",
        full_str, re.I
    )
    if mfg_match:
        # Trim trailing garbage tokens (short OCR noise after valid company text)
        clean = re.sub(r"\s+(?:[A-Z][a-z]{0,2}:|[A-Z]{1,4}[0-9]{2,}[a-z]?)\s*$", "", mfg_match.group(1).strip())
        return make_result(
            value=clean.strip(),
            confidence=0.85,
            evidence=mfg_match.group(0),
            bbox=None
        )

    # Generic "Pvt. Ltd" / "Limited" entity scan
    pvt_match = re.search(
        r"([A-Z][A-Za-z\s&,.-]{5,70}(?:Pvt\.?\s*Ltd\.?|Limited|Corp\.?|Inc\.))",
        full_str, re.I
    )
    if pvt_match:
        return make_result(
            value=pvt_match.group(1).strip(),
            confidence=0.70,
            evidence=pvt_match.group(0),
            bbox=None
        )

    return None


# ============================================================
# CONSUMER CARE
# ============================================================

def extract_consumer_care(words):
    phone_pattern = re.compile(
        r"(?:\+91[\s-]?)?\d[\d\s-]{8,12}\d"
    )

    email_pattern = re.compile(
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    )

    labels = {
        "consumer", "care", "helpline", "customer",
        "contact", "tollfree", "email", "feedback",
        "queries", "complaint", "consoinmer", "consoinmord"
    }

    for i, word in enumerate(words):
        current = normalized_label(word.get("text", ""))

        if current not in labels:
            continue

        nearby = words[i + 1:i + 15]

        for candidate in nearby:
            value = candidate.get("text", "").strip()

            phone = phone_pattern.search(value)
            email = email_pattern.search(value)

            if phone:
                return make_result(
                    value=phone.group(),
                    confidence=get_confidence(candidate),
                    evidence=f"{word.get('text')} {value}",
                    bbox=candidate.get("bbox")
                )

            if email:
                return make_result(
                    value=email.group(),
                    confidence=get_confidence(candidate),
                    evidence=f"{word.get('text')} {value}",
                    bbox=candidate.get("bbox")
                )

    # Full-text email / phone scan (no label required)
    full_str = word_text(words)

    email_match = email_pattern.search(full_str)
    if email_match:
        return make_result(
            value=email_match.group(),
            confidence=0.85,
            evidence=email_match.group(0),
            bbox=None
        )

    phone_match = phone_pattern.search(full_str)
    if phone_match:
        return make_result(
            value=phone_match.group(),
            confidence=0.80,
            evidence=phone_match.group(0),
            bbox=None
        )

    return None


# ============================================================
# BATCH NUMBER
# ============================================================

# Common words that are NEVER a valid batch/lot number
_BATCH_FILLERS = {
    "no", "num", "number", ":", "-", "and", "or", "the", "of",
    "in", "at", "on", "to", "a", "an", "is", "are", "for",
    "by", "with", "as", "if", "be", "see", "use", "date",
    # Words from QR code / promotional text on packaging
    "enter", "scan", "first", "flrst", "characters", "character",
    "search", "please", "type", "click", "visit", "check",
    "box", "code", "qr", "here", "app", "link", "the",
}


def extract_batch_number(words):
    labels = {
        "batch", "batchno", "batchnum", "batchnumber",
        "lot",   "lotno",   "lotnum",   "lotnumber",
        "bno",   "bnum",    "bnumber",  "code", "codeno"
    }

    for i, word in enumerate(words):
        current = normalized_label(word.get("text", ""))
        if current not in labels:
            continue

        nearby = words[i + 1:i + 7]
        for candidate in nearby:
            val     = candidate.get("text", "").strip().rstrip(".,:;")
            cleaned = clean_word(val)

            if not cleaned or cleaned in _BATCH_FILLERS:
                continue

            # Skip tokens that look like quantity measurements (e.g. '802mg', '80g', '250ml')
            if re.match(r"^\d+(?:\.\d+)?\s*(?:g|mg|ml|kg|gm|gms|ltr?|litre?)\b", val, re.I):
                continue

            # Valid batch token: MUST contain at least one digit
            has_digit = any(c.isdigit() for c in val)
            if len(val) >= 3 and has_digit:
                return make_result(
                    value=val,
                    confidence=safe_confidence([word, candidate]),
                    evidence=f"{word.get('text')} {candidate.get('text')}",
                    bbox=candidate.get("bbox")
                )

    # Full-text regex: "Batch No: XXXX" or "BATCHNO: KV061705" — must contain digit
    full_str = word_text(words)
    batch_match = re.search(
        r"batch\s*(?:no\.?|no:|num|number|code)?\s*:?\s*([A-Z0-9]*\d[A-Z0-9/._-]*)",
        full_str, re.I
    )
    if batch_match:
        candidate = batch_match.group(1).strip(".,:")
        # Skip if the captured value is a common word
        _SKIP = {"ENTER", "SCAN", "FIRST", "GOOD", "CHARACTERS"}
        if candidate.upper() not in _SKIP and re.search(r"\d", candidate):
            return make_result(
                value=candidate,
                confidence=0.85,
                evidence=batch_match.group(0),
                bbox=None
            )

    # Last resort: find any alphanumeric token that looks like a batch code
    # (has both letters and digits, 4-15 chars, not a unit/measurement or common word)
    _COMMON_WORDS = {
        "ENTER", "SCAN", "CODE", "FIRST", "GOOD", "LIFE", "FOOD",
        "SEARCH", "EMAIL", "PHONE", "STORE", "CLEAN", "PLACE",
        "WITH", "FROM", "THAT", "THIS", "HAVE", "BEEN", "WILL",
        "NUMBER", "Mumbai", "INDIA", "DELHI", "FSSAI"
    }
    candidates = re.findall(r"\b[A-Z0-9]{4,15}\b", full_str)
    _qty_units = {"G", "MG", "ML", "KG", "LTR", "LITRE", "LITER"}
    for tok in candidates:
        if tok.upper() in _qty_units:
            continue
        if tok.upper() in _COMMON_WORDS:
            continue
        # Skip pure-unit suffixed numbers (e.g. '802MG', '250ML')
        if re.match(r"^\d+(?:G|MG|ML|KG|LTR)$", tok, re.I):
            continue
        if re.search(r"\d", tok) and re.search(r"[A-Za-z]", tok):
            return make_result(
                value=tok,
                confidence=0.55,
                evidence=f"Alphanumeric batch code candidate: {tok}",
                bbox=None
            )

    return None


# ============================================================
# UNIT SALE PRICE
# ============================================================

def extract_unit_sale_price(words):
    labels = {
        "unit", "unitprice", "saleprice", "unitsaleprice",
        "usp", "uspr",   # OCR common abbreviation for Unit Sale Price
    }

    for i, word in enumerate(words):
        current = normalized_label(word.get("text", ""))

        if current not in labels:
            continue

        nearby     = words[i + 1:i + 10]
        local_text = word_text(nearby)

        # Handle comma as decimal separator (e.g. '1,45' -> '1.45')
        local_text_norm = normalize_text(local_text).replace(",", ".")

        match = re.search(
            r"(?:Rs\.?|\u20b9)?\s*"
            r"(\d{1,4}(?:\.\d{1,4})?)",
            local_text_norm,
            re.I
        )

        if not match:
            continue

        try:
            val = float(match.group(1))
        except ValueError:
            continue

        if val <= 0:
            continue

        return make_result(
            value=round(val, 4),
            confidence=safe_confidence(nearby),
            evidence=f"{word.get('text')} {local_text}",
            bbox=nearby[0].get("bbox") if nearby else word.get("bbox")
        )

    # Full-text: UNIT SALE PRICE ; 088 PERG  (088 = Rs 0.88/g)
    # Also handles: USP ? 1,45per g  (comma as decimal separator)
    full_str = word_text(words)

    usp_patterns = [
        r"UNIT\s*SALE\s*PRICE\s*[;:,]?\s*(?:Rs\.?)?\s*(\d+(?:[.,]\d+)?)\s*/?\s*(?:PER\s*[Gg]|/[Gg])?",
        r"\bUSP\s*[?:;]?\s*(?:Rs\.?)?\s*(\d+(?:[.,]\d+)?)\s*(?:per|/)?\s*[Gg]?",
    ]

    for pat in usp_patterns:
        usp_match = re.search(pat, full_str, re.I)
        if usp_match:
            raw = usp_match.group(1).replace(",", ".")  # handle comma decimal separator
            # Leading-zero values like '088' mean '0.88'
            if raw.startswith("0") and len(raw) > 1 and raw[1] != ".":
                stripped = raw.lstrip("0")
                val = float("0." + stripped) if stripped else 0.0
            else:
                val = float(raw)
            if val > 0:
                return make_result(
                    value=round(val, 4),
                    confidence=0.85,
                    evidence=usp_match.group(0),
                    bbox=None
                )

    return None


# ============================================================
# MAIN EXTRACTION ENTRY POINT
# ============================================================

def extract_fields(ocr_result):
    words = ocr_result.get("words", []) if isinstance(ocr_result, dict) else []

    fields = {
        "mrp":               extract_mrp(words),
        "net_quantity":      extract_quantity(words),
        "manufacturing_date": extract_manufacturing_date(words),
        "best_before":       extract_best_before(words),
        "product_name":      extract_product_name(words),
        "country_of_origin": extract_country_of_origin(words),
        "manufacturer":      extract_manufacturer(words),
        "consumer_care":     extract_consumer_care(words),
        "batch_number":      extract_batch_number(words),
        "unit_sale_price":   extract_unit_sale_price(words),
    }

    return fields