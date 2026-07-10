# config.py — DataCraft MDM Quality Workbench
# Central configuration constants and settings

import os

# ─────────────────────────────────────────────
# Brand
# ─────────────────────────────────────────────
APP_TITLE = "DataCraft MDM Quality Workbench"
APP_ICON = "🔬"
BRAND_COLOR = "#1E3A5F"
ACCENT_COLOR = "#2ECC71"
WARNING_COLOR = "#F39C12"
DANGER_COLOR = "#E74C3C"

# ─────────────────────────────────────────────
# Tier thresholds (rows)
# ─────────────────────────────────────────────
TIER_SMALL_MAX = 10_000
TIER_MEDIUM_MAX = 2_000_000
CHUNK_SIZE_MEDIUM = 50_000
CHUNK_SIZE_LARGE = 100_000
TEST_ENV_ROWS = 10_000

# ─────────────────────────────────────────────
# Fuzzy / Confidence
# ─────────────────────────────────────────────
FUZZY_DEFAULT_THRESHOLD = 80
CONFIDENCE_HIGH = 80
CONFIDENCE_MEDIUM = 50

# ─────────────────────────────────────────────
# Project / Cache
# ─────────────────────────────────────────────
PROJECTS_DIR = os.path.join(os.path.dirname(__file__), "projects")
CACHE_SUBDIR = "cache"
TEST_SUBDIR = "test"
PROD_SUBDIR = "prod"
REF_SUBDIR = "reference_library"
PROJECT_META_FILE = "project_meta.json"
FIELD_REGISTRY_FILE = "field_registry.json"
CHUNK_MANIFEST_FILE = "chunk_manifest.json"
REVIEW_DECISIONS_FILE = "review_decisions.pkl"

# ─────────────────────────────────────────────
# 26 Cleaning Rules
# ─────────────────────────────────────────────
ALL_CLEANING_RULES = [
    "trim_whitespace",
    "collapse_internal_spaces",
    "case_normalize",
    "null_handling",
    "pattern_replace",
    "remove_html",
    "remove_special_chars",
    "prefix_remap",
    "trim_leading_zeros",
    "trim_trailing_zeros",
    "pad_leading_zeros",
    "trim_leading_trailing_special",
    "fuzzy_match",
    "reference_lookup_replace",
    "date_standardize",
    "phone_standardize",
    "legal_entity_suffix_norm",
    "boolean_norm",
    "currency_norm",
    "extract_substring",
    "concatenate_fields",
    "split_field",
    "deduplicate_multivalue",
    "flag_duplicate_records",
    "custom_regex_replace",
    "custom_python_expression",
    "custom_lookup_transform",
]

CLEANING_RULE_LABELS = {
    "trim_whitespace": "Trim Whitespace",
    "collapse_internal_spaces": "Collapse Internal Spaces",
    "case_normalize": "Case Normalization",
    "null_handling": "Null Handling (Fill / Flag)",
    "pattern_replace": "Pattern Replace",
    "remove_html": "Remove HTML Tags",
    "remove_special_chars": "Remove Special Characters",
    "prefix_remap": "Prefix Remap",
    "trim_leading_zeros": "Trim Leading Zeros",
    "trim_trailing_zeros": "Trim Trailing Zeros",
    "pad_leading_zeros": "Pad Leading Zeros",
    "trim_leading_trailing_special": "Trim Leading/Trailing Special Chars",
    "fuzzy_match": "Fuzzy Match (difflib WRatio)",
    "reference_lookup_replace": "Reference Lookup Replace",
    "date_standardize": "Date Standardization",
    "phone_standardize": "Phone Standardization",
    "legal_entity_suffix_norm": "Legal Entity Suffix Normalization",
    "boolean_norm": "Boolean Normalization",
    "currency_norm": "Currency Normalization",
    "extract_substring": "Extract Substring → New Column",
    "concatenate_fields": "Concatenate Fields → New Column",
    "split_field": "Split Field → New Columns",
    "deduplicate_multivalue": "Deduplicate Multi-value Within Field",
    "flag_duplicate_records": "Flag Duplicate Records",
    "custom_regex_replace": "Custom Regex Replace",
    "custom_python_expression": "Custom Python Expression (Sandboxed)",
    "custom_lookup_transform": "Custom Lookup Transform",
}

# ─────────────────────────────────────────────
# 19 Validation Types
# ─────────────────────────────────────────────
ALL_VALIDATION_TYPES = [
    "mandatory_null",
    "data_type",
    "pattern_format",
    "allowed_values",
    "range",
    "pk_uniqueness",
    "string_length",
    "trim_validation",
    "cardinality_1_to_1",
    "cardinality_1_to_n",
    "reference_existence",
    "cross_field_tuple",
    "conditional_rule",
    "mutual_exclusivity",
    "co_occurrence",
    "value_dependency",
    "arithmetic_consistency",
    "date_sequence",
    "completeness_score",
    "date_year_range",
    "grouped_fuzzy_duplicate",
    "mapping_cardinality",
    "cross_file_cardinality",
    "suspicious_number",
]

VALIDATION_TYPE_LABELS = {
    "mandatory_null": "Mandatory / Null Check",
    "data_type": "Data Type",
    "pattern_format": "Pattern / Format",
    "allowed_values": "Allowed Values",
    "range": "Range (Min/Max)",
    "pk_uniqueness": "PK Uniqueness",
    "string_length": "String Length",
    "trim_validation": "Trim Validation",
    "cardinality_1_to_1": "1:1 Cardinality Mapping",
    "cardinality_1_to_n": "1:N Cardinality Mapping",
    "reference_existence": "Reference Existence",
    "cross_field_tuple": "Cross-field Tuple Match",
    "conditional_rule": "Conditional Rule (Bidirectional)",
    "mutual_exclusivity": "Mutual Exclusivity",
    "co_occurrence": "Co-occurrence",
    "value_dependency": "Value Dependency (Bidirectional)",
    "arithmetic_consistency": "Arithmetic Consistency",
    "date_sequence": "Date Sequence",
    "completeness_score": "Completeness Score per Record",
    "date_year_range": "Date Year Range",
    "grouped_fuzzy_duplicate": "Grouped Fuzzy Duplicate",
    "mapping_cardinality": "Mapping Cardinality (1:many)",
    "cross_file_cardinality": "Cross-File Cardinality",
    "suspicious_number": "Suspicious / Fake Number",
}

# ─────────────────────────────────────────────
# Validation type help text — shown in Tab 3 UI
# ─────────────────────────────────────────────
VALIDATION_TYPE_HELP = {
    "mandatory_null": "Flags records where the selected field is null or empty. Use when a field is required.",
    "data_type": "Checks that every value in the field matches the expected data type (string, integer, float, date, boolean, pincode). Use for format enforcement.",
    "pattern_format": "Validates values against a regex pattern (e.g. email, phone, pincode). Select a built-in pattern or enter a custom regex.",
    "allowed_values": "Checks that values belong to a fixed allowed set (e.g. M/F, Active/Inactive). Comma-separate the allowed values.",
    "range": "Checks numeric values fall within [Min, Max]. Use for age, salary, score fields.",
    "pk_uniqueness": "Ensures the selected field has no duplicate values across the entire dataset (cross-chunk). Use for primary key columns.",
    "string_length": "Validates that string length falls within [Min Length, Max Length]. Use for codes, IDs, names.",
    "trim_validation": "Flags values with leading or trailing whitespace. Apply after trim cleaning to confirm it worked.",
    "cardinality_1_to_1": "Within the data, verifies that Column A always maps to exactly one Column B and vice versa. Use for Employee ID ↔ Email type relationships.",
    "cardinality_1_to_n": "Within the data, verifies that Column B (many-side) always maps to a single Column A (one-side). Use to detect orphan records.",
    "reference_existence": "Checks that each value in the selected column exists in a reference file column. Use for city names, country codes, employee IDs against a master list. The Expected column in the report will show valid values from the reference.",
    "cross_field_tuple": "Validates that the combination of multiple columns (e.g. pincode + city) exists as a valid tuple in the reference file. Best rule for pincode→city/state/district validation. For 1:N (one pincode, many cities), all valid cities for that pincode appear in the Expected column of the report.",
    "conditional_rule": "If Column A = value X, then Column B must = value Y. Supports bidirectional checking. Use for dependent fields.",
    "mutual_exclusivity": "Checks that at most one (or exactly one) column in a set has a value at a time. Use for radio-button-style fields.",
    "co_occurrence": "Ensures two fields are either both filled or both empty. Use for paired fields like start_date + end_date.",
    "value_dependency": "If Column A is filled, Column B must also be filled (and vice versa). Use for fields that must appear together.",
    "arithmetic_consistency": "Checks that operand columns satisfy: col_a OP col_b = result_col. Use for totals, subtotals, calculated fields.",
    "date_sequence": "Validates that start date <= end date (or strictly <). Use for date ranges.",
    "completeness_score": "Flags records where the fraction of filled fields across selected columns falls below a threshold. Use for overall record quality gating.",
    "date_year_range": "Extracts the year from a date or MMM YYYY field and checks it falls within a min/max year range. Use to catch broken dates like 'Jan 1900'.",
    "grouped_fuzzy_duplicate": "Groups rows by one or more columns (e.g. Depot + Sales Group + Employee Name), then finds exact and fuzzy duplicate values in a compare column (e.g. Prospect Name) within each group. Use to detect duplicate entries by the same person.",
    "mapping_cardinality": "Shows how one column maps to another (e.g. Sales Group -> Sales Office) and flags anomalies: a value tied to multiple groups, blanks, and duplicate pairs. Produces dedicated mapping + anomaly sheets in the report.",
    "cross_file_cardinality": "Compares a shared value (e.g. Sales Group) between two reference files (e.g. dealer file vs employee file). Classifies each as 1:1 / 1:many / many:1 / many:many, and flags REASSIGN (in file A, not B) and CHECK (in file B, not A) gaps. Produces a dedicated cardinality sheet.",
    "suspicious_number": "Detects fake / placeholder phone numbers: all-same-digit (1111111111), repeating blocks (1212121212), low digit variety (few unique digits), sequential runs, and wrong length. Each check is individually toggleable with configurable thresholds. Nulls are skipped.",
}

# ─────────────────────────────────────────────
# FIX: Data type options including pincode
# ─────────────────────────────────────────────
DTYPE_OPTIONS = [
    "string",
    "integer",
    "float",
    "date",
    "boolean",
    "email",
    "phone",
    "pincode",       # NEW — Issue 1 fix
    "postal_code",   # NEW — generic postal
]

DTYPE_LABELS = {
    "string": "String (text)",
    "integer": "Integer (whole number)",
    "float": "Float (decimal number)",
    "date": "Date",
    "boolean": "Boolean (true/false)",
    "email": "Email address",
    "phone": "Phone number",
    "pincode": "Pincode / ZIP (India 6-digit)",
    "postal_code": "Postal Code (generic pattern)",
}

# FIX: Map dtype → default pattern for auto-association
DTYPE_PATTERN_MAP = {
    "email": "email",
    "phone": "phone_india",
    "pincode": "pincode_india",
    "postal_code": "pincode_india",
}

# ─────────────────────────────────────────────
# 14 Issue Types
# ─────────────────────────────────────────────
ISSUE_TYPES = [
    "NULL_VIOLATION",
    "TYPE_MISMATCH",
    "FORMAT_VIOLATION",
    "OUT_OF_RANGE",
    "INVALID_VALUE",
    "LENGTH_VIOLATION",
    "UNIQUENESS_VIOLATION",
    "REFERENCE_NOT_FOUND",
    "CROSS_FIELD_VIOLATION",
    "CARDINALITY_VIOLATION",
    "ADDRESS_VALIDATION_FAIL",
    "COMPLETENESS_BELOW_THRESHOLD",
    "TRIM_VIOLATION",
    "CUSTOM_RULE_VIOLATION",
]

ISSUE_TYPE_TO_VALIDATION = {
    "NULL_VIOLATION": "mandatory_null",
    "TYPE_MISMATCH": "data_type",
    "FORMAT_VIOLATION": "pattern_format",
    "OUT_OF_RANGE": "range",
    "INVALID_VALUE": "allowed_values",
    "LENGTH_VIOLATION": "string_length",
    "UNIQUENESS_VIOLATION": "pk_uniqueness",
    "REFERENCE_NOT_FOUND": "reference_existence",
    "CROSS_FIELD_VIOLATION": "cross_field_tuple",
    "CARDINALITY_VIOLATION": "cardinality_1_to_1",
    "ADDRESS_VALIDATION_FAIL": "address_validation",
    "COMPLETENESS_BELOW_THRESHOLD": "completeness_score",
    "TRIM_VIOLATION": "trim_validation",
    "CUSTOM_RULE_VIOLATION": "conditional_rule",
}

# ─────────────────────────────────────────────
# Severity levels
# ─────────────────────────────────────────────
SEVERITY_LEVELS = ["Critical", "High", "Medium", "Low", "Info"]

REPORT_SEVERITY_COLORS = {
    "Critical": "#E74C3C",
    "High": "#E67E22",
    "Medium": "#F39C12",
    "Low": "#3498DB",
    "Info": "#95A5A6",
}

SEVERITY_EMOJI = {
    "Critical": "🔴",
    "High": "🟠",
    "Medium": "🟡",
    "Low": "🔵",
    "Info": "⚪",
}

# ─────────────────────────────────────────────
# Regex / Format PATTERNS (complete dict)
# ─────────────────────────────────────────────
PATTERNS = {
    # Date
    "date_yyyy_mm_dd": r"^\d{4}-\d{2}-\d{2}$",
    "date_dd_mm_yyyy": r"^\d{2}/\d{2}/\d{4}$",
    "date_mm_dd_yyyy": r"^\d{2}-\d{2}-\d{4}$",
    "date_dd_mon_yyyy": r"^\d{2}-[A-Za-z]{3}-\d{4}$",
    "date_iso8601": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",
    # Phone
    "phone_e164": r"^\+\d{7,15}$",
    "phone_us": r"^\+?1?\s?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}$",
    "phone_india": r"^(\+91|0)?[6-9]\d{9}$",
    "phone_uk": r"^\+44\d{10}$",
    "phone_generic_10": r"^\d{10}$",
    # Email
    "email": r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$",
    # Postal / Pincode
    "pincode_india": r"^\d{6}$",
    "postal_us": r"^\d{5}(-\d{4})?$",
    "postal_uk": r"^[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}$",
    "postal_canada": r"^[A-Za-z]\d[A-Za-z]\s?\d[A-Za-z]\d$",
    # Numeric
    "integer": r"^-?\d+$",
    "decimal": r"^-?\d+(\.\d+)?$",
    "positive_integer": r"^\d+$",
    "currency_amount": r"^-?\d{1,3}(,\d{3})*(\.\d{2})?$",
    # Identifiers
    "pan_india": r"^[A-Z]{5}\d{4}[A-Z]$",
    "gstin_india": r"^\d{2}[A-Z]{5}\d{4}[A-Z]\d[Z][A-Z\d]$",
    "aadhar_india": r"^\d{4}\s?\d{4}\s?\d{4}$",
    "ifsc_india": r"^[A-Z]{4}0[A-Z0-9]{6}$",
    "ssn_us": r"^\d{3}-\d{2}-\d{4}$",
    "uuid": r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
    "hex_color": r"^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$",
    "ip_v4": r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$",
    "url": r"^https?://[^\s/$.?#].[^\s]*$",
    "alphanumeric": r"^[a-zA-Z0-9]+$",
    "alpha_only": r"^[a-zA-Z]+$",
    "numeric_only": r"^\d+$",
    # Custom placeholder
    "custom": r"",
}

PATTERN_LABELS = {k: k.replace("_", " ").title() for k in PATTERNS}

# ─────────────────────────────────────────────
# Date formats for standardization
# ─────────────────────────────────────────────
DATE_INPUT_FORMATS = [
    "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y",
    "%d-%b-%Y", "%d %b %Y", "%Y%m%d", "%d.%m.%Y",
    "%m-%d-%Y", "%B %d, %Y", "%d %B %Y",
]
DATE_OUTPUT_FORMAT = "%Y-%m-%d"

# ─────────────────────────────────────────────
# Boolean normalization maps
# ─────────────────────────────────────────────
BOOLEAN_TRUE_VALUES = {"true", "yes", "y", "1", "on", "active", "enabled", "t", "si", "oui"}
BOOLEAN_FALSE_VALUES = {"false", "no", "n", "0", "off", "inactive", "disabled", "f", "non", "nein"}
BOOLEAN_TRUE_OUTPUT = "True"
BOOLEAN_FALSE_OUTPUT = "False"

# ─────────────────────────────────────────────
# Legal entity suffixes normalization
# ─────────────────────────────────────────────
LEGAL_ENTITY_MAP = {
    r"\bpvt\.?\s*ltd\.?\b": "Pvt Ltd",
    r"\bprivate\s+limited\b": "Pvt Ltd",
    r"\bltd\.?\b": "Ltd",
    r"\blimited\b": "Ltd",
    r"\bllp\b": "LLP",
    r"\blimited\s+liability\s+partnership\b": "LLP",
    r"\binc\.?\b": "Inc",
    r"\bincorporated\b": "Inc",
    r"\bcorp\.?\b": "Corp",
    r"\bcorporation\b": "Corp",
    r"\bllc\b": "LLC",
    r"\bplc\b": "PLC",
    r"\bgmbh\b": "GmbH",
    r"\bsa\b": "SA",
    r"\bsrl\b": "SRL",
    r"\bpte\.?\s*ltd\.?\b": "Pte Ltd",
    r"\bs\.?\s*a\.?\s*r\.?\s*l\.?\b": "SARL",
}

# ─────────────────────────────────────────────
# Currency normalization
# ─────────────────────────────────────────────
CURRENCY_SYMBOLS = ["$", "€", "£", "¥", "₹", "₩", "₪", "₦", "฿", "kr", "CHF"]

# ─────────────────────────────────────────────
# Address validation
# ─────────────────────────────────────────────
ADDRESS_PLACEHOLDER_PATTERNS = [
    r"^(na|n/a|none|null|unknown|tbd|tba|xxx+|test|dummy|placeholder|n\.a\.)$",
    r"^[-_\.\s]*$",
]
ADDRESS_COMPLETENESS_FIELDS = ["street", "city", "state", "pincode", "country"]
GOOGLE_MAPS_API_BASE = "https://maps.googleapis.com/maps/api/geocode/json"

# ─────────────────────────────────────────────
# Report sheet names (12 sheets)
# ─────────────────────────────────────────────
REPORT_SHEETS = [
    "Raw Data",
    "Cleaned Data",
    "Configuration Summary",
    "Duplicate Report",
    "Test Records Report",
    "Validation Report",
    "Data Quality Summary",
    "Reference Validation Detail",
    "Cross-field Consistency",
    "Address Validation Detail",
    "Review Decisions Report",
    "Cleaning & Validation Log",
]

# ─────────────────────────────────────────────
# Validation report columns
# ─────────────────────────────────────────────
VALIDATION_REPORT_COLS = [
    "Record ID",
    "Field Name",
    "Issue Type",
    "Rule Description",
    "Expected",
    "Actual",
    "Severity",
    "Chunk Number",
    "Timestamp",
]

# ─────────────────────────────────────────────
# Test Detection methods (5)
# ─────────────────────────────────────────────
TEST_DETECTION_METHODS = [
    "field_value_match",
    "prefix_suffix_pattern",
    "regex_pattern",
    "value_in_list",
    "null_pk",
]

TEST_DETECTION_LABELS = {
    "field_value_match": "Field Value Match",
    "prefix_suffix_pattern": "Prefix / Suffix Pattern",
    "regex_pattern": "Regex Pattern",
    "value_in_list": "Value in List",
    "null_pk": "Null Primary Key",
}

# ─────────────────────────────────────────────
# Address tier labels
# ─────────────────────────────────────────────
ADDRESS_TIERS = {
    1: "Reference File Match",
    2: "Structural Checks",
    3: "Google Maps API",
}

# ─────────────────────────────────────────────
# Confidence color thresholds
# ─────────────────────────────────────────────
CONFIDENCE_COLOR_HIGH = "#2ECC71"    # >= CONFIDENCE_HIGH (80)
CONFIDENCE_COLOR_MEDIUM = "#F39C12"  # >= CONFIDENCE_MEDIUM (50)
CONFIDENCE_COLOR_LOW = "#E74C3C"     # < CONFIDENCE_MEDIUM

# ─────────────────────────────────────────────
# Misc UI
# ─────────────────────────────────────────────
MAX_PREVIEW_ROWS = 500
CUSTOM_EXPR_PREVIEW_ROWS = 5
FUZZY_FIRST_CHAR_BLOCK = True  # block if first chars don't match

# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────
LOG_FILE = "datacraft_mdm.log"
