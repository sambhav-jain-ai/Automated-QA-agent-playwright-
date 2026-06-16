"""Helper script to generate a sample test_endpoints.xlsx fixture.

Run this to create the fixture file:
    python3 tests/fixtures/generate_sample_xlsx.py
"""

import os
import sys
import zipfile
import xml.etree.ElementTree as ET

FIXTURE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(FIXTURE_DIR, "test_endpoints.xlsx")


def create_xlsx(rows: list[list[str]], filepath: str) -> None:
    """Create a minimal .xlsx file."""
    all_strings: list[str] = []
    for row in rows:
        for cell in row:
            if cell and cell not in all_strings:
                all_strings.append(cell)

    # sharedStrings.xml
    ss_root = ET.Element("sst")
    ss_root.set("xmlns", "http://schemas.openxmlformats.org/spreadsheetml/2006/main")
    ss_root.set("count", str(len(all_strings)))
    ss_root.set("uniqueCount", str(len(all_strings)))
    for s in all_strings:
        si = ET.SubElement(ss_root, "si")
        t = ET.SubElement(si, "t")
        t.text = s
    ss_xml = ET.tostring(ss_root, encoding="unicode", xml_declaration=True)

    # sheet1.xml
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
            c_elem.set("t", "s")
            v_elem = ET.SubElement(c_elem, "v")
            v_elem.text = str(all_strings.index(cell_value))

    ws_xml = ET.tostring(ws_root, encoding="unicode", xml_declaration=True)

    # workbook.xml
    wb_root = ET.Element("workbook")
    wb_root.set("xmlns", "http://schemas.openxmlformats.org/spreadsheetml/2006/main")
    sheets = ET.SubElement(wb_root, "sheets")
    sheet = ET.SubElement(sheets, "sheet")
    sheet.set("name", "Sheet1")
    sheet.set("sheetId", "1")
    wb_xml = ET.tostring(wb_root, encoding="unicode", xml_declaration=True)

    with zipfile.ZipFile(filepath, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("xl/sharedStrings.xml", ss_xml)
        zf.writestr("xl/worksheets/sheet1.xml", ws_xml)
        zf.writestr("xl/workbook.xml", wb_xml)
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"></Types>',
        )


if __name__ == "__main__":
    rows = [
        ["method", "url", "headers", "body", "expected_status"],
        ["GET", "/api/users", "", "", "200"],
        ["POST", "/api/users", '{"Content-Type": "application/json"}', '{"name": "Alice"}', "201"],
        ["GET", "/api/health", "", "", "200"],
        ["DELETE", "/api/users/1", "", "", "204"],
        ["PUT", "/api/users/1", '{"Content-Type": "application/json"}', '{"name": "Updated"}', "200"],
    ]
    create_xlsx(rows, OUTPUT_PATH)
    print(f"Created: {OUTPUT_PATH}")
