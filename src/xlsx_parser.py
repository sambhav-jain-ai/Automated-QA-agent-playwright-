"""Parse .xlsx files using only Python stdlib (zipfile + xml.etree.ElementTree).

An xlsx file is a ZIP archive containing XML files:
- xl/workbook.xml - sheet definitions
- xl/sharedStrings.xml - string table
- xl/worksheets/sheet1.xml - cell data
"""

import json
import zipfile
import xml.etree.ElementTree as ET
from typing import Any


# XML namespaces used in xlsx files
NS = {
    "s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def _read_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    """Read the shared strings table from the xlsx archive."""
    try:
        with zf.open("xl/sharedStrings.xml") as f:
            tree = ET.parse(f)
    except KeyError:
        return []

    root = tree.getroot()
    strings: list[str] = []
    for si in root.findall("s:si", NS):
        text_parts: list[str] = []
        # Handle <t> directly under <si>
        t_elem = si.find("s:t", NS)
        if t_elem is not None and t_elem.text:
            text_parts.append(t_elem.text)
        # Handle <r><t> (rich text runs)
        for r in si.findall("s:r", NS):
            t_elem = r.find("s:t", NS)
            if t_elem is not None and t_elem.text:
                text_parts.append(t_elem.text)
        strings.append("".join(text_parts))
    return strings


def _get_cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    """Extract the value from a cell element."""
    cell_type = cell.get("t", "")
    value_elem = cell.find("s:v", NS)

    if value_elem is None or value_elem.text is None:
        return ""

    if cell_type == "s":
        # Shared string reference
        idx = int(value_elem.text)
        if idx < len(shared_strings):
            return shared_strings[idx]
        return ""
    elif cell_type == "b":
        # Boolean
        return "TRUE" if value_elem.text == "1" else "FALSE"
    else:
        # Number or inline string
        return value_elem.text


def _col_index(col_str: str) -> int:
    """Convert column letter(s) to zero-based index. A=0, B=1, ..., Z=25, AA=26."""
    result = 0
    for ch in col_str:
        result = result * 26 + (ord(ch.upper()) - ord("A") + 1)
    return result - 1


def _parse_cell_ref(ref: str) -> tuple[int, int]:
    """Parse cell reference like 'A1' into (row_idx, col_idx) zero-based."""
    col_str = ""
    row_str = ""
    for ch in ref:
        if ch.isalpha():
            col_str += ch
        else:
            row_str += ch
    return int(row_str) - 1, _col_index(col_str)


def parse_xlsx(filepath: str) -> list[dict[str, str]]:
    """Parse an xlsx file and return rows as list of dicts with header keys.

    Args:
        filepath: Path to the .xlsx file

    Returns:
        List of dictionaries, one per data row. Keys are from the header row.
    """
    with zipfile.ZipFile(filepath, "r") as zf:
        shared_strings = _read_shared_strings(zf)

        # Read sheet1
        try:
            with zf.open("xl/worksheets/sheet1.xml") as f:
                tree = ET.parse(f)
        except KeyError:
            return []

        root = tree.getroot()
        sheet_data = root.find("s:sheetData", NS)
        if sheet_data is None:
            return []

        # Parse all rows
        rows_data: list[list[tuple[int, str]]] = []
        for row in sheet_data.findall("s:row", NS):
            cells: list[tuple[int, str]] = []
            for cell in row.findall("s:c", NS):
                ref = cell.get("r", "")
                if ref:
                    _, col_idx = _parse_cell_ref(ref)
                    value = _get_cell_value(cell, shared_strings)
                    cells.append((col_idx, value))
            rows_data.append(cells)

        if not rows_data:
            return []

        # First row is header
        header_cells = rows_data[0]
        max_col = max(c[0] for c in header_cells) if header_cells else 0
        headers: list[str] = [""] * (max_col + 1)
        for col_idx, value in header_cells:
            headers[col_idx] = value

        # Data rows
        result: list[dict[str, str]] = []
        for row_cells in rows_data[1:]:
            if not row_cells:
                continue
            row_dict: dict[str, str] = {}
            for col_idx, value in row_cells:
                if col_idx < len(headers) and headers[col_idx]:
                    row_dict[headers[col_idx]] = value
            if any(v for v in row_dict.values()):
                result.append(row_dict)

        return result


def get_api_endpoints(filepath: str) -> list[dict[str, Any]]:
    """Parse xlsx and return structured API endpoint definitions.

    Expects columns: method, url, headers (JSON string), body (JSON string), expected_status

    Args:
        filepath: Path to the .xlsx file

    Returns:
        List of endpoint dicts with keys: method, url, headers, body, expected_status
    """
    rows = parse_xlsx(filepath)
    endpoints: list[dict[str, Any]] = []

    for row in rows:
        endpoint: dict[str, Any] = {
            "method": row.get("method", row.get("Method", "GET")).upper(),
            "url": row.get("url", row.get("URL", row.get("Url", ""))),
        }

        # Parse headers (may be JSON string or empty)
        headers_raw = row.get("headers", row.get("Headers", ""))
        if headers_raw:
            try:
                endpoint["headers"] = json.loads(headers_raw)
            except (json.JSONDecodeError, ValueError):
                endpoint["headers"] = {}
        else:
            endpoint["headers"] = {}

        # Parse body
        body_raw = row.get("body", row.get("Body", ""))
        if body_raw:
            try:
                endpoint["body"] = json.loads(body_raw)
            except (json.JSONDecodeError, ValueError):
                endpoint["body"] = body_raw
        else:
            endpoint["body"] = None

        # Expected status
        status_raw = row.get("expected_status", row.get("Expected_Status", row.get("ExpectedStatus", "")))
        if status_raw:
            try:
                endpoint["expected_status"] = int(status_raw)
            except (ValueError, TypeError):
                endpoint["expected_status"] = 200
        else:
            endpoint["expected_status"] = 200

        if endpoint["url"]:
            endpoints.append(endpoint)

    return endpoints
