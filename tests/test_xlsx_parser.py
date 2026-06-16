"""Tests for the xlsx_parser module."""

import os
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.xlsx_parser import parse_xlsx, get_api_endpoints


def _create_test_xlsx(rows: list[list[str]], filepath: str) -> None:
    """Create a minimal .xlsx file for testing.

    An xlsx is a ZIP of XML files. We create the minimum required structure.
    """
    # Collect all unique strings
    all_strings: list[str] = []
    for row in rows:
        for cell in row:
            if cell and cell not in all_strings:
                all_strings.append(cell)

    # Build sharedStrings.xml
    ss_root = ET.Element("sst")
    ss_root.set("xmlns", "http://schemas.openxmlformats.org/spreadsheetml/2006/main")
    ss_root.set("count", str(len(all_strings)))
    ss_root.set("uniqueCount", str(len(all_strings)))
    for s in all_strings:
        si = ET.SubElement(ss_root, "si")
        t = ET.SubElement(si, "t")
        t.text = s
    ss_xml = ET.tostring(ss_root, encoding="unicode", xml_declaration=True)

    # Build sheet1.xml
    ws_root = ET.Element("worksheet")
    ws_root.set("xmlns", "http://schemas.openxmlformats.org/spreadsheetml/2006/main")
    sheet_data = ET.SubElement(ws_root, "sheetData")

    for row_idx, row in enumerate(rows, 1):
        row_elem = ET.SubElement(sheet_data, "row")
        row_elem.set("r", str(row_idx))
        for col_idx, cell_value in enumerate(row):
            if not cell_value:
                continue
            col_letter = chr(ord("A") + col_idx)
            cell_ref = f"{col_letter}{row_idx}"
            c_elem = ET.SubElement(row_elem, "c")
            c_elem.set("r", cell_ref)
            c_elem.set("t", "s")  # shared string type
            v_elem = ET.SubElement(c_elem, "v")
            v_elem.text = str(all_strings.index(cell_value))

    ws_xml = ET.tostring(ws_root, encoding="unicode", xml_declaration=True)

    # Build workbook.xml
    wb_root = ET.Element("workbook")
    wb_root.set("xmlns", "http://schemas.openxmlformats.org/spreadsheetml/2006/main")
    sheets = ET.SubElement(wb_root, "sheets")
    sheet = ET.SubElement(sheets, "sheet")
    sheet.set("name", "Sheet1")
    sheet.set("sheetId", "1")
    wb_xml = ET.tostring(wb_root, encoding="unicode", xml_declaration=True)

    # Create the zip (xlsx) file
    with zipfile.ZipFile(filepath, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("xl/sharedStrings.xml", ss_xml)
        zf.writestr("xl/worksheets/sheet1.xml", ws_xml)
        zf.writestr("xl/workbook.xml", wb_xml)
        zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"></Types>')


class TestParseXlsx:
    """Tests for parse_xlsx function."""

    def test_basic_parsing(self, tmp_path):
        """Test parsing a simple xlsx with header and data rows."""
        filepath = str(tmp_path / "test.xlsx")
        rows = [
            ["name", "age", "city"],
            ["Alice", "30", "NYC"],
            ["Bob", "25", "LA"],
        ]
        _create_test_xlsx(rows, filepath)

        result = parse_xlsx(filepath)
        assert len(result) == 2
        assert result[0]["name"] == "Alice"
        assert result[0]["age"] == "30"
        assert result[0]["city"] == "NYC"
        assert result[1]["name"] == "Bob"

    def test_empty_xlsx(self, tmp_path):
        """Test parsing an xlsx with only a header row."""
        filepath = str(tmp_path / "empty.xlsx")
        rows = [["col1", "col2"]]
        _create_test_xlsx(rows, filepath)

        result = parse_xlsx(filepath)
        assert result == []

    def test_single_row(self, tmp_path):
        """Test parsing an xlsx with exactly one data row."""
        filepath = str(tmp_path / "single.xlsx")
        rows = [
            ["key", "value"],
            ["hello", "world"],
        ]
        _create_test_xlsx(rows, filepath)

        result = parse_xlsx(filepath)
        assert len(result) == 1
        assert result[0]["key"] == "hello"
        assert result[0]["value"] == "world"


class TestGetApiEndpoints:
    """Tests for get_api_endpoints function."""

    def test_basic_endpoints(self, tmp_path):
        """Test extracting API endpoints from xlsx."""
        filepath = str(tmp_path / "api.xlsx")
        rows = [
            ["method", "url", "headers", "body", "expected_status"],
            ["GET", "/api/users", "", "", "200"],
            ["POST", "/api/users", '{"Content-Type": "application/json"}', '{"name": "test"}', "201"],
        ]
        _create_test_xlsx(rows, filepath)

        endpoints = get_api_endpoints(filepath)
        assert len(endpoints) == 2
        assert endpoints[0]["method"] == "GET"
        assert endpoints[0]["url"] == "/api/users"
        assert endpoints[0]["expected_status"] == 200
        assert endpoints[1]["method"] == "POST"
        assert endpoints[1]["headers"] == {"Content-Type": "application/json"}
        assert endpoints[1]["body"] == {"name": "test"}
        assert endpoints[1]["expected_status"] == 201

    def test_missing_columns(self, tmp_path):
        """Test handling of xlsx with minimal columns."""
        filepath = str(tmp_path / "minimal.xlsx")
        rows = [
            ["method", "url"],
            ["GET", "/health"],
        ]
        _create_test_xlsx(rows, filepath)

        endpoints = get_api_endpoints(filepath)
        assert len(endpoints) == 1
        assert endpoints[0]["method"] == "GET"
        assert endpoints[0]["url"] == "/health"
        assert endpoints[0]["expected_status"] == 200
        assert endpoints[0]["headers"] == {}
        assert endpoints[0]["body"] is None
