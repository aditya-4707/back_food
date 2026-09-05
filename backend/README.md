# Legal Metrology Compliance Engine

An automated OCR-based auditing tool to verify packaged commodity labels against **Rule 6 of the Legal Metrology (Packaged Commodities) Rules**.

This engine processes images of product packaging, automatically extracts critical label declarations (MRP, Net Quantity, Best Before, Batch Number, Manufacturer, etc.), and generates a formatted audit report highlighting compliance violations and low-confidence reads that require manual verification.

## Features
- **Auto-Orientation & Image Pre-processing**: Uses OpenCV (Bicubic Upscaling, CLAHE, Unsharp Masking) to enhance small text and automatically detects the correct image orientation.
- **Robust Field Extraction**: Powered by EasyOCR with extensive regex fallback systems to recover from common OCR misreads (e.g. reading 'g' as '9', 'USE BY' as 'USEBH').
- **Confidence-Aware Auditing**: Numeric fields and text fields use different confidence thresholds to determine if a field was cleanly extracted or if it needs manual human review.
- **Formatted Reporting**: Generates both a human-readable `.txt` report with confidence bars and a machine-readable `.json` payload.

## Project Structure
```
backend/
├── src/
│   ├── main.py                # Main orchestrator and report generator
│   ├── field_extractor.py     # OCR text parsing, regex, and misread recovery
│   ├── compliance_engine.py   # Rule 6 logic and confidence evaluation
│   ├── rules.py               # Schema and severity definitions for Rule 6
│   ├── requirements.txt       # Python dependencies
├── outputs/                   # Automatically generated audit reports & temp files
└── README.md
```

## Installation

1. Clone this repository.
2. Install the required Python packages:
   ```bash
   pip install -r src/requirements.txt
   ```
   *(Note: This project uses `easyocr` and `opencv-python` for text extraction and image processing).*

## Usage

Place an image of a product label in the root folder, and run the engine pointing to the image:

```bash
python src/main.py my_product_label.jpeg
```

The engine will scan the image and generate two files in the `outputs/` folder:
- `outputs/my_product_label_audit.txt` (Human-readable report)
- `outputs/my_product_label_audit.json` (Raw extraction data)

### Demo Output
```text
=================================================================
   LEGAL METROLOGY COMPLIANCE AUDIT REPORT
   Legal Metrology (Packaged Commodities) Rules — Rule 6
=================================================================
  Status      : ⚠️ NEEDS VERIFICATION
-----------------------------------------------------------------
  Total Rules : 9
  ✅ Passed   : 6
  ⚠️ Review   : 3
  ❌ Violated : 0
=================================================================
...
```
