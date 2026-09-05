import sys
import os
import io
import json
import argparse
from datetime import datetime
from field_extractor import extract_fields
from compliance_engine import check_compliance

# Force UTF-8 output on Windows (avoids cp1252 UnicodeEncodeError with emoji)
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DEMO_OCR_RESULT = {
    "words": [
        {"text": "AYURVEDIC",  "confidence": 95, "bbox": [10, 10, 100, 30]},
        {"text": "SOAP",       "confidence": 92, "bbox": [105, 10, 150, 30]},
        {"text": "Net",        "confidence": 90, "bbox": [10, 40, 40, 55]},
        {"text": "Wt:",        "confidence": 88, "bbox": [45, 40, 70, 55]},
        {"text": "125g",       "confidence": 94, "bbox": [75, 40, 110, 55]},
        {"text": "MRP",        "confidence": 98, "bbox": [10, 60, 45, 75]},
        {"text": "Rs.",        "confidence": 91, "bbox": [50, 60, 75, 75]},
        {"text": "1,250.00",   "confidence": 96, "bbox": [80, 60, 140, 75]},
        {"text": "MFD:",       "confidence": 89, "bbox": [10, 80, 50, 95]},
        {"text": "10/2024",    "confidence": 93, "bbox": [55, 80, 110, 95]},
        {"text": "Best",       "confidence": 87, "bbox": [10, 100, 45, 115]},
        {"text": "Before:",    "confidence": 86, "bbox": [50, 100, 95, 115]},
        {"text": "24",         "confidence": 90, "bbox": [100, 100, 120, 115]},
        {"text": "months",     "confidence": 91, "bbox": [125, 100, 175, 115]},
        {"text": "Mfg",        "confidence": 85, "bbox": [10, 120, 40, 135]},
        {"text": "by:",        "confidence": 84, "bbox": [45, 120, 65, 135]},
        {"text": "Himalaya",   "confidence": 90, "bbox": [70, 120, 130, 135]},
        {"text": "Wellness",   "confidence": 89, "bbox": [135, 120, 195, 135]},
        {"text": "Company",    "confidence": 88, "bbox": [200, 120, 260, 135]},
        {"text": "Customer",   "confidence": 82, "bbox": [10, 140, 75, 155]},
        {"text": "Care:",      "confidence": 83, "bbox": [80, 140, 115, 155]},
        {"text": "care@himalayawellness.com", "confidence": 95, "bbox": [120, 140, 290, 155]},
        {"text": "Batch",      "confidence": 88, "bbox": [10, 160, 50, 175]},
        {"text": "No:",        "confidence": 86, "bbox": [55, 160, 80, 175]},
        {"text": "BATCH2024A", "confidence": 92, "bbox": [85, 160, 170, 175]}
    ]
}


# ============================================================
# IMAGE PRE-PROCESSING
# ============================================================

def preprocess_image_cv(image_path):
    """
    Applies 2.5x Super-Resolution Bicubic Upscaling, CLAHE Contrast Enhancement,
    and Unsharp Masking using OpenCV to drastically improve low-res OCR accuracy.
    """
    try:
        import cv2
        import numpy as np

        img = cv2.imread(image_path)
        if img is None:
            return image_path

        h, w = img.shape[:2]
        scale = 1.0
        if max(h, w) < 1200:
            scale = max(2.5, 1200.0 / max(h, w))

        if scale > 1.0:
            img = cv2.resize(img, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        kernel = [[0, -1, 0], [-1, 5, -1], [0, -1, 0]]
        import numpy as np
        sharp = cv2.filter2D(enhanced, -1, np.array(kernel))

        os.makedirs("outputs", exist_ok=True)
        base_name = os.path.basename(image_path)
        temp_path = os.path.join("outputs", base_name + "_prep.png")
        cv2.imwrite(temp_path, sharp)
        return temp_path
    except Exception as e:
        print(f"Preprocessing note: {e}")
        return image_path


def get_best_orientation(image_path):
    """
    Scans image at 0, 90, 180, and 270 degree rotations,
    returning the best rotated image path.
    """
    try:
        import cv2
        import easyocr

        orig = cv2.imread(image_path)
        if orig is None:
            return image_path

        rotations = [
            (0,   None),
            (90,  cv2.ROTATE_90_CLOCKWISE),
            (180, cv2.ROTATE_180),
            (270, cv2.ROTATE_90_COUNTERCLOCKWISE)
        ]

        keywords = {
            "mrp", "rs", "net", "qty", "g", "ml", "mfd", "mfg",
            "best", "before", "use", "pepsico", "kurkure",
            "manufactured", "consumer", "batch"
        }
        reader = easyocr.Reader(['en'], gpu=False, verbose=False)

        best_score = -1
        best_rotated_path = image_path

        for deg, rot in rotations:
            test_img = orig if rot is None else cv2.rotate(orig, rot)

            os.makedirs("outputs", exist_ok=True)
            base_name = os.path.basename(image_path)
            temp_rot_file = os.path.join("outputs", f"{base_name}_rot{deg}.png")
            cv2.imwrite(temp_rot_file, test_img)
            enhanced_file = preprocess_image_cv(temp_rot_file)

            res = reader.readtext(enhanced_file)
            score = 0
            for bbox, text, prob in res:
                t = str(text).lower()
                if any(kw in t for kw in keywords):
                    score += 10
                elif len(t) > 3 and prob > 0.2:
                    score += 1

            if score > best_score:
                best_score = score
                best_rotated_path = enhanced_file

            if temp_rot_file != image_path and os.path.exists(temp_rot_file):
                try:
                    os.remove(temp_rot_file)
                except Exception:
                    pass

        return best_rotated_path
    except Exception as e:
        print(f"Auto-orientation note: {e}")
        return preprocess_image_cv(image_path)


# ============================================================
# OCR
# ============================================================

def ocr_image(image_path):
    """
    Perform OCR on an image file with multi-angle rotation auto-detection.
    """
    best_image_path = get_best_orientation(image_path)

    words = []

    try:
        import easyocr
        print("Running EasyOCR engine with auto-orientation and image enhancement...")
        reader  = easyocr.Reader(['en'], gpu=False, verbose=False)
        results = reader.readtext(best_image_path)

        for bbox, text, prob in results:
            text_str = str(text).strip()
            if not text_str:
                continue

            subwords = text_str.split()
            xs  = [pt[0] for pt in bbox]
            ys  = [pt[1] for pt in bbox]
            box = [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]

            for sw in subwords:
                words.append({
                    "text":       sw,
                    "confidence": float(prob * 100),
                    "bbox":       box
                })

        if os.path.exists(best_image_path) and best_image_path != image_path:
            try:
                os.remove(best_image_path)
            except Exception:
                pass

        return {"words": words}

    except ImportError:
        pass

    try:
        from PIL import Image
        import pytesseract

        tess_paths = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe")
        ]
        for p in tess_paths:
            if os.path.exists(p):
                pytesseract.pytesseract.tesseract_cmd = p
                break

        img  = Image.open(best_image_path)
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

        for i in range(len(data['text'])):
            txt  = data['text'][i].strip()
            conf = float(data['conf'][i])
            if txt and conf > 0:
                words.append({
                    "text":       txt,
                    "confidence": conf,
                    "bbox": [
                        data['left'][i],
                        data['top'][i],
                        data['left'][i] + data['width'][i],
                        data['top'][i] + data['height'][i]
                    ]
                })

        return {"words": words}

    except Exception as e:
        print(f"OCR Error: {e}")
        print("Please install 'easyocr' via: pip install easyocr")
        sys.exit(1)


# ============================================================
# AUDIT REPORT GENERATOR
# ============================================================

STATUS_ICON = {
    "COMPLIANT":          "[COMPLIANT]",
    "NEEDS_VERIFICATION": "[NEEDS VERIFICATION]",
    "NON_COMPLIANT":      "[NON-COMPLIANT]",
}

# Rich unicode versions saved to .txt file
STATUS_ICON_RICH = {
    "COMPLIANT":          "\u2705  COMPLIANT",
    "NEEDS_VERIFICATION": "\u26a0\ufe0f   NEEDS VERIFICATION",
    "NON_COMPLIANT":      "\u274c  NON-COMPLIANT",
}

SEVERITY_LABEL = {
    "HIGH":   "[HIGH]",
    "MEDIUM": "[MEDIUM]",
    "LOW":    "[LOW]",
}

SEVERITY_LABEL_RICH = {
    "HIGH":   "\U0001f534 HIGH",
    "MEDIUM": "\U0001f7e1 MEDIUM",
    "LOW":    "\U0001f7e2 LOW",
}


def _bar(value, width=20, rich=False):
    """ASCII confidence bar. rich=True uses block chars for file output."""
    filled = int(round(value * width))
    if rich:
        return "[" + "\u2588" * filled + "\u2591" * (width - filled) + f"] {int(value * 100)}%"
    return "[" + "#" * filled + "." * (width - filled) + f"] {int(value * 100)}%"


def generate_audit_report(result, source_label, output_path):
    """
    Write a human-readable audit report (.txt) and a machine-readable
    JSON file (.json) based on the compliance result.
    Returns (txt_path, json_path, console_text, file_text)
    """
    fields  = result.get("extracted_fields", {})
    report  = result.get("compliance_report", {})
    summary = report.get("summary", {})
    now     = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    status_key = report.get("status", "")
    status_console = STATUS_ICON.get(status_key, status_key)
    status_rich    = STATUS_ICON_RICH.get(status_key, status_key)

    def _build(rich=False):
        si = status_rich if rich else status_console
        _b = lambda v: _bar(v, rich=rich)
        _sl = lambda s: SEVERITY_LABEL_RICH.get(s, s) if rich else SEVERITY_LABEL.get(s, s)
        passed_pfx      = "\u2705" if rich else "[OK]"
        warn_pfx        = "\u26a0\ufe0f " if rich else "[!!]"
        fail_pfx        = "\u274c" if rich else "[XX]"

        lines = []
        lines.append("=" * 65)
        lines.append("   LEGAL METROLOGY COMPLIANCE AUDIT REPORT")
        lines.append("   Legal Metrology (Packaged Commodities) Rules \u2014 Rule 6")
        lines.append("=" * 65)
        lines.append(f"  Source      : {source_label}")
        lines.append(f"  Generated   : {now}")
        lines.append(f"  Status      : {si}")
        lines.append("-" * 65)
        lines.append(f"  Total Rules : {summary.get('total_rules', 0)}")
        lines.append(f"  {passed_pfx} Passed   : {summary.get('passed', 0)}")
        lines.append(f"  {warn_pfx} Review   : {summary.get('needs_review', 0)}")
        lines.append(f"  {fail_pfx} Violated : {summary.get('violations', 0)}")
        lines.append("=" * 65)

        # Extracted fields
        lines.append("")
        lines.append("  EXTRACTED FIELDS")
        lines.append("  " + "-" * 63)

        field_labels = {
            "mrp":                "MRP (Rs.)",
            "net_quantity":       "Net Quantity",
            "manufacturing_date": "Mfg. Date",
            "best_before":        "Best Before / Use By",
            "product_name":       "Product Name",
            "country_of_origin":  "Country of Origin",
            "manufacturer":       "Manufacturer / Packer",
            "consumer_care":      "Consumer Care",
            "batch_number":       "Batch / Lot Number",
            "unit_sale_price":    "Unit Sale Price (Rs/g)",
        }

        for key, label in field_labels.items():
            field = fields.get(key)
            if field is None:
                lines.append(f"  {label:<24} : [NOT DETECTED]")
            elif isinstance(field, dict):
                val  = field.get("value", "")
                conf = field.get("confidence", 0.0)
                lines.append(f"  {label:<24} : {str(val)[:38]}")
                lines.append(f"  {'Confidence':<24}   {_b(conf)}")
            else:
                lines.append(f"  {label:<24} : {field}")

        lines.append("")

        # Passed
        passed = report.get("passed", [])
        if passed:
            lines.append("=" * 65)
            lines.append(f"  {passed_pfx}  PASSED CHECKS")
            lines.append("  " + "-" * 63)
            for item in passed:
                lines.append(f"  [{item['rule_id']}]  {item['name']}")
                val = item.get("value", "")
                if val:
                    lines.append(f"         Detected   : {str(val)[:55]}")
                lines.append(f"         Confidence : {_b(item.get('confidence', 0.0))}")
            lines.append("")

        # Verification
        verification = report.get("verification", [])
        if verification:
            lines.append("=" * 65)
            lines.append(f"  {warn_pfx}  NEEDS VERIFICATION")
            lines.append("  " + "-" * 63)
            for item in verification:
                sev = _sl(item.get("severity", ""))
                lines.append(f"  [{item['rule_id']}]  {item['name']}  ({sev})")
                lines.append(f"         \u21b3 {item['message']}")
                val = item.get("value")
                if val:
                    lines.append(f"         Detected   : {str(val)[:55]}")
            lines.append("")

        # Violations
        violations = report.get("violations", [])
        if violations:
            lines.append("=" * 65)
            lines.append(f"  {fail_pfx}  VIOLATIONS (Non-Compliant Declarations)")
            lines.append("  " + "-" * 63)
            for item in violations:
                sev = _sl(item.get("severity", ""))
                lines.append(f"  [{item['rule_id']}]  {item['name']}  ({sev})")
                lines.append(f"         \u21b3 {item['message']}")
            lines.append("")

        lines.append("=" * 65)
        lines.append("  END OF AUDIT REPORT")
        lines.append("=" * 65)
        return "\n".join(lines)

    console_text = _build(rich=False)
    file_text    = _build(rich=True)

    txt_path  = output_path + ".txt"
    json_path = output_path + ".json"

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(file_text)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    return txt_path, json_path, console_text, file_text


# ============================================================
# CORE PIPELINE
# ============================================================

def process_ocr_data(ocr_data):
    fields = extract_fields(ocr_data)
    report = check_compliance(fields)
    return {
        "extracted_fields":   fields,
        "compliance_report":  report
    }


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Legal Metrology Compliance Engine — Rule 6 Audit"
    )

    parser.add_argument(
        "file",
        nargs="?",
        help="Path to image (.jpg/.jpeg/.png) or OCR JSON file"
    )

    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run compliance engine on built-in sample OCR dataset"
    )

    parser.add_argument(
        "--out",
        default=None,
        help="Base path for audit output files (default: <input_file>_audit)"
    )

    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Skip writing audit report files (print JSON only)"
    )

    args = parser.parse_args()

    # ── Determine source ────────────────────────────────────────
    if args.file:
        target_path = args.file

        # Try adding extension if file not found as-is
        if not os.path.exists(target_path):
            for ext in [".jpeg", ".jpg", ".png"]:
                if os.path.exists(target_path + ext):
                    target_path = target_path + ext
                    break

        if not os.path.exists(target_path):
            print(f"Error: File '{args.file}' not found.")
            sys.exit(1)

        ext = os.path.splitext(target_path)[1].lower()
        if ext in [".jpg", ".jpeg", ".png", ".bmp", ".webp"]:
            print(f"Processing image file: {target_path}")
            ocr_data     = ocr_image(target_path)
            source_label = os.path.basename(target_path)
        else:
            with open(target_path, "r", encoding="utf-8") as f:
                ocr_data = json.load(f)
            source_label = os.path.basename(target_path)

        if not args.out:
            os.makedirs("outputs", exist_ok=True)
            out_base = os.path.join("outputs", os.path.basename(os.path.splitext(target_path)[0]) + "_audit")
        else:
            out_base = args.out

    else:
        print("=== Running Legal Metrology Compliance Engine Demo ===")
        ocr_data     = DEMO_OCR_RESULT
        source_label = "Built-in Demo (Himalaya Wellness Soap)"
        out_base     = args.out or os.path.join(os.path.dirname(__file__) or ".", "demo_audit")

    # ── Run compliance engine ────────────────────────────────────
    result = process_ocr_data(ocr_data)

    # ── Always print JSON to stdout ──────────────────────────────
    print(json.dumps(result, indent=2))

    # ── Write audit report ───────────────────────────────────────
    if not args.no_report:
        txt_path, json_path, console_text, _ = generate_audit_report(
            result, source_label, out_base
        )
        print()
        print(console_text)
        print()
        print(f"Audit report saved : {txt_path}")
        print(f"JSON results saved : {json_path}")


if __name__ == "__main__":
    main()
