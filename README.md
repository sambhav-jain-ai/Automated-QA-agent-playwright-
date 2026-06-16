# Playwright Automation Test Tool

An automated QA testing tool that combines UI crawling, API endpoint testing, and AI-assisted retry logic. Built entirely with Python standard library (no external dependencies required for the backend).

## Features

- **Phase 1 - UI Crawl**: Generates Playwright scripts for browser automation including login, OTP handling, navigation, and button/link discovery
- **Phase 2 - API Testing**: Tests API endpoints defined in an Excel (.xlsx) file using `urllib.request`
- **Phase 3 - AI Retry**: Rule-based AI module analyzes failures, suggests URL corrections, and generates retry scripts
- **Live Logging**: Server-Sent Events (SSE) stream real-time progress to the browser
- **HTML Reports**: Generates detailed test reports with pass/fail breakdowns per phase
- **Excel Parsing**: Reads API endpoint definitions from .xlsx files using `zipfile` + `xml.etree` (no openpyxl needed)

## Project Structure

```
.
├── server.py                  # Main HTTP server (stdlib http.server)
├── src/
│   ├── ai_module.py           # Rule-based AI analysis and script generation
│   ├── api_tester.py          # HTTP API testing via urllib.request
│   ├── crawler_engine.py      # UI crawl logic and Playwright script generation
│   ├── report_generator.py    # HTML report builder
│   ├── script_generator.py    # Phase 3 Playwright script generator
│   └── xlsx_parser.py         # Excel parser using zipfile + XML
├── static/
│   ├── index.html             # Single-page web UI
│   ├── app.js                 # Frontend logic (fetch, SSE, phase management)
│   └── style.css              # Modern responsive styling
├── tests/
│   ├── test_ai_module.py      # AI module unit tests
│   ├── test_api_tester.py     # API tester unit tests
│   ├── test_report_generator.py # Report generator tests
│   ├── test_server.py         # Server integration tests
│   └── test_xlsx_parser.py    # Excel parser tests
├── generated_scripts/         # Generated Playwright scripts (runtime)
├── reports/                   # Generated HTML reports (runtime)
├── screenshots/               # Captured screenshots (runtime)
└── uploads/                   # Temporary uploaded files (runtime)
```

## Requirements

- Python 3.11+ (uses only the standard library)
- pytest (for running tests)

No `pip install` needed for the application itself.

## Usage

### Start the Server

```bash
python3 server.py
```

The server starts on `http://localhost:5000`.

### Run Tests

```bash
python3 -m pytest tests/ -v
```

### How It Works

1. Open `http://localhost:5000` in your browser
2. Enter the target application's frontend URL, credentials, and optionally a backend API URL
3. Optionally upload an Excel (.xlsx) file with API endpoint definitions
4. Click "Start Test" to begin the automated testing pipeline
5. Watch real-time progress in the live log panel
6. When prompted, enter the OTP code if the target application requires one
7. Download the HTML report and generated Playwright scripts when complete

### Excel File Format

The .xlsx file should have columns for API endpoint definitions:

| Method | URL | Headers | Body | Expected Status |
|--------|-----|---------|------|-----------------|
| GET | /api/users | | | 200 |
| POST | /api/login | {"Content-Type": "application/json"} | {"user": "test"} | 200 |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Serve the web UI |
| `/static/*` | GET | Serve static assets |
| `/api/start` | POST | Start a test session |
| `/api/upload` | POST | Upload an Excel file |
| `/api/status/<sessionId>` | GET | SSE stream for live logs |
| `/api/report/<sessionId>` | GET | Get the HTML report |
| `/api/otp` | POST | Submit OTP code |
| `/api/download/report/<sessionId>` | GET | Download report file |
| `/api/download/script/<sessionId>` | GET | Download generated script |

## Architecture

The tool uses a pure Python stdlib approach:

- **Web Server**: `http.server.BaseHTTPRequestHandler` with threaded request handling
- **Excel Parsing**: `.xlsx` files are ZIP archives containing XML; parsed with `zipfile` and `xml.etree.ElementTree`
- **HTTP Testing**: `urllib.request` for making API calls to target endpoints
- **AI Module**: Rule-based pattern matching (no external AI APIs required)
- **Report Generation**: HTML templates built with Python string formatting and `html` module for escaping
- **Live Updates**: Server-Sent Events (SSE) for real-time log streaming to the browser

## License

MIT
