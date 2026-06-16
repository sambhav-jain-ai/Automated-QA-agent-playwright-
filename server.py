"""Main HTTP server for the Playwright Automation Tool.

Uses Python stdlib http.server. Serves static files and API routes.
Run: python3 server.py
"""

import io
import json
import mimetypes
import os
import queue
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Optional
from urllib.parse import urlparse, parse_qs

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.xlsx_parser import parse_xlsx, get_api_endpoints
from src.api_tester import run_api_tests, deep_crawler
from src.crawler_engine import CrawlerEngine
from src.ai_module import AIModule
from src.report_generator import generate_html_report
from src.script_generator import generate_phase3_script

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

sessions: dict[str, dict[str, Any]] = {}
sessions_lock = threading.Lock()


def get_session(session_id: str) -> dict[str, Any]:
    """Get or create a session state dict."""
    with sessions_lock:
        if session_id not in sessions:
            sessions[session_id] = {
                "id": session_id,
                "status": "idle",
                "log_queue": queue.Queue(),
                "otp_event": threading.Event(),
                "otp_value": "",
                "config": {},
                "phase1_result": None,
                "phase2_result": None,
                "phase3_result": None,
                "report_path": None,
            }
        return sessions[session_id]


# ---------------------------------------------------------------------------
# Test orchestrator (runs in background thread)
# ---------------------------------------------------------------------------

def run_test_session(session_id: str, config: dict[str, Any]) -> None:
    """Orchestrate all test phases for a session."""
    session = get_session(session_id)
    session["status"] = "running"
    session["config"] = config

    frontend_url = config.get("frontendUrl", "")
    backend_url = config.get("backendUrl", "")
    username = config.get("username", "")
    password = config.get("password", "")
    xlsx_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "uploads",
        f"{session_id}.xlsx",
    )

    def log(msg: str) -> None:
        session["log_queue"].put(msg)

    try:
        log(f"[Session {session_id}] Starting test orchestration...")
        log(f"[Config] Frontend: {frontend_url}")
        log(f"[Config] Backend: {backend_url}")

        # Phase 1: UI Crawl
        log("\n=== Phase 1: UI Crawl ===")
        crawler = CrawlerEngine()

        def otp_provider() -> str:
            log("[OTP] Waiting for OTP input from user...")
            session["otp_event"].wait(timeout=300)
            return session.get("otp_value", "")

        crawler_result = crawler.run(
            frontend_url=frontend_url,
            username=username,
            password=password,
            otp_provider_fn=otp_provider,
            session_log_fn=log,
            session_id=session_id,
        )

        session["phase1_result"] = {
            "visited_urls": crawler_result.visited_urls,
            "discovered_buttons": crawler_result.discovered_buttons,
            "generated_test_cases": crawler_result.generated_test_cases,
            "screenshots": crawler_result.screenshots,
            "playwright_script_path": crawler_result.playwright_script_path,
        }
        log(f"[Phase 1] Complete. Script saved: {crawler_result.playwright_script_path}")

        # Phase 2: API Tests
        log("\n=== Phase 2: API Tests ===")
        endpoints: list[dict[str, Any]] = []
        xlsx_data: list[dict] = []

        if os.path.exists(xlsx_path):
            log(f"[Phase 2] Loading endpoints from: {xlsx_path}")
            xlsx_data = parse_xlsx(xlsx_path)
            endpoints = get_api_endpoints(xlsx_path)
            log(f"[Phase 2] Found {len(endpoints)} endpoints in xlsx")
        else:
            log("[Phase 2] No xlsx uploaded. Using deep crawler for API discovery.")

        # Run deep crawler on backend
        crawler_urls: list[str] = []
        if backend_url:
            log(f"[Phase 2] Deep crawling backend: {backend_url}")
            crawler_urls = deep_crawler(backend_url, log)

        # Run API tests
        api_results: list[dict[str, Any]] = []
        if endpoints:
            api_results = run_api_tests(endpoints, backend_url, log)
        else:
            log("[Phase 2] No endpoints to test.")

        session["phase2_result"] = api_results
        passed = sum(1 for r in api_results if r.get("passed"))
        log(f"[Phase 2] Complete. {passed}/{len(api_results)} tests passed.")

        # Phase 3: AI Analysis & Retry
        log("\n=== Phase 3: AI Analysis & Retry ===")
        ai = AIModule()
        analysis = ai.analyze_failures(
            test_results=api_results,
            deep_crawler_urls=crawler_urls,
            xlsx_data=xlsx_data,
        )

        log(f"[Phase 3] Confidence score: {analysis.confidence_score}")
        for suggestion in analysis.suggestions:
            log(f"[Phase 3 - AI] {suggestion}")

        # Generate Phase 3 Playwright script
        if analysis.retry_plan:
            log(f"[Phase 3] Generating retry script for {len(analysis.retry_plan)} endpoint(s)")
            phase3_script = generate_phase3_script(
                session_id=session_id,
                retry_plan=analysis.retry_plan,
                frontend_url=frontend_url,
                ai_guidance=analysis.suggestions,
            )
            log(f"[Phase 3] Retry script saved to: generated_scripts/phase3_{session_id}.py")

        session["phase3_result"] = {
            "failure_groups": {k: len(v) for k, v in analysis.failure_groups.items()},
            "suggestions": analysis.suggestions,
            "retry_plan": analysis.retry_plan,
            "confidence_score": analysis.confidence_score,
        }

        # Generate Report
        log("\n=== Generating Report ===")
        report_html = generate_html_report(
            session_id=session_id,
            phase1_result=session["phase1_result"],
            phase2_result=session["phase2_result"],
            phase3_result=session["phase3_result"],
            screenshots=crawler_result.screenshots,
        )
        report_path = f"/projects/sandbox/playwright-autotest/reports/{session_id}.html"
        session["report_path"] = report_path
        log(f"[Report] Generated: {report_path}")
        log(f"\n=== Test Session Complete ===")
        session["status"] = "complete"

    except Exception as e:
        log(f"\n[ERROR] Test session failed: {e}")
        session["status"] = "error"

    # Signal end of log stream
    session["log_queue"].put(None)


# ---------------------------------------------------------------------------
# HTTP Request Handler
# ---------------------------------------------------------------------------

class AutoTestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the automation tool."""

    STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
    UPLOADS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
    REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
    SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generated_scripts")

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default access logs."""
        pass

    def _send_json(self, data: Any, status: int = 200) -> None:
        """Send a JSON response."""
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html_content: str, status: int = 200) -> None:
        """Send an HTML response."""
        body = html_content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, message: str, status: int = 400) -> None:
        """Send an error JSON response."""
        self._send_json({"error": message}, status)

    def _read_body(self) -> bytes:
        """Read request body."""
        content_length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(content_length)

    def do_OPTIONS(self) -> None:
        """Handle CORS preflight."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        """Handle GET requests."""
        parsed = urlparse(self.path)
        path = parsed.path

        # Root -> serve index.html
        if path == "/" or path == "":
            self._serve_static("index.html")
            return

        # Static files
        if path.startswith("/static/"):
            filename = path[len("/static/"):]
            self._serve_static(filename)
            return

        # SSE log stream
        if path.startswith("/api/status/"):
            session_id = path.split("/api/status/")[1].strip("/")
            self._handle_sse(session_id)
            return

        # Report
        if path.startswith("/api/report/"):
            session_id = path.split("/api/report/")[1].strip("/")
            self._handle_get_report(session_id)
            return

        # Download report (with Content-Disposition: attachment)
        if path.startswith("/api/download/report/"):
            session_id = path.split("/api/download/report/")[1].strip("/")
            self._handle_download_report(session_id)
            return

        # Download generated Playwright script
        if path.startswith("/api/download/script/"):
            session_id = path.split("/api/download/script/")[1].strip("/")
            self._handle_download_script(session_id)
            return

        # List available downloads for a session
        if path.startswith("/api/downloads/"):
            session_id = path.split("/api/downloads/")[1].strip("/")
            self._handle_list_downloads(session_id)
            return

        # 404
        self._send_error_json("Not found", 404)

    def do_POST(self) -> None:
        """Handle POST requests."""
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/start":
            self._handle_start()
            return

        if path == "/api/upload":
            self._handle_upload()
            return

        if path == "/api/otp":
            self._handle_otp()
            return

        self._send_error_json("Not found", 404)

    def _serve_static(self, filename: str) -> None:
        """Serve a static file."""
        # Prevent path traversal
        filename = filename.replace("..", "").lstrip("/")
        filepath = os.path.join(self.STATIC_DIR, filename)

        if not os.path.isfile(filepath):
            self._send_error_json("File not found", 404)
            return

        content_type, _ = mimetypes.guess_type(filepath)
        if content_type is None:
            content_type = "application/octet-stream"

        with open(filepath, "rb") as f:
            content = f.read()

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _handle_start(self) -> None:
        """Handle POST /api/start - start a test session."""
        try:
            body = self._read_body()
            data = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, ValueError):
            self._send_error_json("Invalid JSON body")
            return

        session_id = data.get("sessionId") or str(uuid.uuid4())
        frontend_url = data.get("frontendUrl", "")
        username = data.get("username", "")
        password = data.get("password", "")
        backend_url = data.get("backendUrl", "")

        if not frontend_url:
            self._send_error_json("frontendUrl is required")
            return

        config = {
            "frontendUrl": frontend_url,
            "username": username,
            "password": password,
            "backendUrl": backend_url,
            "sessionId": session_id,
        }

        # Start background thread
        session = get_session(session_id)
        thread = threading.Thread(
            target=run_test_session,
            args=(session_id, config),
            daemon=True,
        )
        thread.start()

        self._send_json({"sessionId": session_id, "status": "started"})

    def _handle_upload(self) -> None:
        """Handle POST /api/upload - upload xlsx file."""
        content_type = self.headers.get("Content-Type", "")

        if "multipart/form-data" not in content_type:
            self._send_error_json("Expected multipart/form-data")
            return

        try:
            body = self._read_body()

            # Extract boundary from Content-Type header
            boundary = self._extract_boundary(content_type)
            if not boundary:
                self._send_error_json("Missing boundary in Content-Type")
                return

            # Parse multipart form data manually
            parts = self._parse_multipart(body, boundary)

            # Get session ID and file
            session_id = ""
            file_data = None

            for part in parts:
                name = part.get("name", "")
                if name == "sessionId":
                    session_id = part["data"].decode("utf-8").strip()
                elif name == "file":
                    file_data = part["data"]

            if not session_id:
                session_id = str(uuid.uuid4())

            if not file_data:
                self._send_error_json("No file uploaded")
                return

            # Save file
            os.makedirs(self.UPLOADS_DIR, exist_ok=True)
            filepath = os.path.join(self.UPLOADS_DIR, f"{session_id}.xlsx")
            with open(filepath, "wb") as f:
                f.write(file_data)

            self._send_json({
                "sessionId": session_id,
                "filename": f"{session_id}.xlsx",
                "size": len(file_data),
            })

        except Exception as e:
            self._send_error_json(f"Upload failed: {str(e)}")

    @staticmethod
    def _extract_boundary(content_type: str) -> Optional[str]:
        """Extract the boundary string from a multipart Content-Type header."""
        for part in content_type.split(";"):
            part = part.strip()
            if part.startswith("boundary="):
                boundary = part[len("boundary="):]
                # Remove optional quotes
                if boundary.startswith('"') and boundary.endswith('"'):
                    boundary = boundary[1:-1]
                return boundary
        return None

    @staticmethod
    def _parse_multipart(body: bytes, boundary: str) -> list[dict[str, Any]]:
        """Parse multipart/form-data body into a list of parts.

        Each part is a dict with keys: name, filename (optional), data (bytes).
        """
        parts: list[dict[str, Any]] = []
        boundary_bytes = boundary.encode("utf-8")
        delimiter = b"--" + boundary_bytes
        end_delimiter = delimiter + b"--"

        # Split body by boundary delimiter
        # The body format is:
        #   --boundary\r\n
        #   headers\r\n
        #   \r\n
        #   data\r\n
        #   --boundary\r\n
        #   ...
        #   --boundary--\r\n
        segments = body.split(delimiter)

        for segment in segments:
            # Skip the preamble (before first boundary) and epilogue (after final --)
            if not segment or segment == b"--" or segment == b"--\r\n":
                continue
            # Remove leading \r\n
            if segment.startswith(b"\r\n"):
                segment = segment[2:]
            # Remove trailing \r\n before next boundary
            if segment.endswith(b"\r\n"):
                segment = segment[:-2]
            # Skip the end marker
            if segment.startswith(b"--"):
                continue

            # Split headers from data at the first blank line
            header_end = segment.find(b"\r\n\r\n")
            if header_end == -1:
                continue

            header_block = segment[:header_end].decode("utf-8", errors="replace")
            data = segment[header_end + 4:]

            # Parse Content-Disposition to get name and filename
            name = ""
            filename = ""
            for line in header_block.split("\r\n"):
                lower_line = line.lower()
                if lower_line.startswith("content-disposition:"):
                    # Extract name
                    name_start = line.find('name="')
                    if name_start != -1:
                        name_start += len('name="')
                        name_end = line.find('"', name_start)
                        if name_end != -1:
                            name = line[name_start:name_end]
                    # Extract filename
                    fname_start = line.find('filename="')
                    if fname_start != -1:
                        fname_start += len('filename="')
                        fname_end = line.find('"', fname_start)
                        if fname_end != -1:
                            filename = line[fname_start:fname_end]

            part_info: dict[str, Any] = {"name": name, "data": data}
            if filename:
                part_info["filename"] = filename
            parts.append(part_info)

        return parts

    def _handle_otp(self) -> None:
        """Handle POST /api/otp - provide OTP for a session."""
        try:
            body = self._read_body()
            data = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, ValueError):
            self._send_error_json("Invalid JSON body")
            return

        session_id = data.get("sessionId", "")
        otp = data.get("otp", "")

        if not session_id or not otp:
            self._send_error_json("sessionId and otp are required")
            return

        session = get_session(session_id)
        session["otp_value"] = otp
        session["otp_event"].set()

        self._send_json({"status": "otp_received", "sessionId": session_id})

    def _handle_sse(self, session_id: str) -> None:
        """Handle GET /api/status/<sessionId> - SSE stream."""
        session = get_session(session_id)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        try:
            while True:
                try:
                    msg = session["log_queue"].get(timeout=30)
                    if msg is None:
                        # End of stream
                        event_data = json.dumps({"type": "complete", "message": "Session complete"})
                        self.wfile.write(f"event: complete\ndata: {event_data}\n\n".encode())
                        self.wfile.flush()
                        break

                    event_data = json.dumps({"type": "log", "message": msg})
                    self.wfile.write(f"data: {event_data}\n\n".encode())
                    self.wfile.flush()

                except queue.Empty:
                    # Send keepalive
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()

        except (BrokenPipeError, ConnectionResetError):
            pass

    def _handle_get_report(self, session_id: str) -> None:
        """Handle GET /api/report/<sessionId>."""
        report_path = os.path.join(self.REPORTS_DIR, f"{session_id}.html")

        if os.path.isfile(report_path):
            with open(report_path, "r", encoding="utf-8") as f:
                self._send_html(f.read())
        else:
            session = get_session(session_id)
            if session.get("status") == "running":
                self._send_json({"status": "running", "message": "Test still in progress"}, 202)
            else:
                self._send_error_json("Report not found", 404)

    def _handle_download_report(self, session_id: str) -> None:
        """Handle GET /api/download/report/<sessionId> - download report as file."""
        # Prevent path traversal
        safe_id = os.path.basename(session_id)
        report_path = os.path.join(self.REPORTS_DIR, f"{safe_id}.html")

        if not os.path.isfile(report_path):
            self._send_error_json("Report not found", 404)
            return

        with open(report_path, "rb") as f:
            content = f.read()

        filename = f"report_{safe_id}.html"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(content)

    def _handle_download_script(self, session_id: str) -> None:
        """Handle GET /api/download/script/<sessionId> - download Playwright script."""
        # Prevent path traversal
        safe_id = os.path.basename(session_id)

        # Look for crawl script first, then phase3 script
        crawl_script = os.path.join(self.SCRIPTS_DIR, f"crawl_{safe_id}.py")
        phase3_script = os.path.join(self.SCRIPTS_DIR, f"phase3_{safe_id}.py")

        # If requesting a specific script type via query params, handle that
        # Otherwise, bundle available scripts or return the crawl script
        scripts_found: list[tuple[str, str]] = []

        if os.path.isfile(crawl_script):
            scripts_found.append(("crawl", crawl_script))
        if os.path.isfile(phase3_script):
            scripts_found.append(("phase3", phase3_script))

        if not scripts_found:
            self._send_error_json("No generated scripts found for this session", 404)
            return

        # If only one script, download it directly
        if len(scripts_found) == 1:
            script_type, script_path = scripts_found[0]
            with open(script_path, "rb") as f:
                content = f.read()
            filename = f"{script_type}_{safe_id}.py"
            self.send_response(200)
            self.send_header("Content-Type", "text/x-python; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(content)
            return

        # Multiple scripts: bundle as a zip
        import zipfile as _zipfile

        zip_buffer = io.BytesIO()
        with _zipfile.ZipFile(zip_buffer, "w", _zipfile.ZIP_DEFLATED) as zf:
            for script_type, script_path in scripts_found:
                arcname = f"{script_type}_{safe_id}.py"
                zf.write(script_path, arcname)

        zip_content = zip_buffer.getvalue()
        filename = f"scripts_{safe_id}.zip"
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Length", str(len(zip_content)))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(zip_content)

    def _handle_list_downloads(self, session_id: str) -> None:
        """Handle GET /api/downloads/<sessionId> - list available downloads."""
        safe_id = os.path.basename(session_id)
        downloads: list[dict[str, str]] = []

        # Check for report
        report_path = os.path.join(self.REPORTS_DIR, f"{safe_id}.html")
        if os.path.isfile(report_path):
            downloads.append({
                "type": "report",
                "filename": f"report_{safe_id}.html",
                "url": f"/api/download/report/{safe_id}",
            })

        # Check for scripts
        crawl_script = os.path.join(self.SCRIPTS_DIR, f"crawl_{safe_id}.py")
        if os.path.isfile(crawl_script):
            downloads.append({
                "type": "script",
                "filename": f"crawl_{safe_id}.py",
                "url": f"/api/download/script/{safe_id}",
            })

        phase3_script = os.path.join(self.SCRIPTS_DIR, f"phase3_{safe_id}.py")
        if os.path.isfile(phase3_script):
            downloads.append({
                "type": "script",
                "filename": f"phase3_{safe_id}.py",
                "url": f"/api/download/script/{safe_id}",
            })

        self._send_json({"sessionId": safe_id, "downloads": downloads})


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def create_server(host: str = "0.0.0.0", port: int = 5000) -> HTTPServer:
    """Create the HTTP server instance."""
    server = HTTPServer((host, port), AutoTestHandler)
    return server


def main() -> None:
    """Start the server."""
    host = "0.0.0.0"
    port = int(os.environ.get("PORT", "5000"))

    # Ensure directories exist
    for d in ["uploads", "reports", "screenshots", "generated_scripts"]:
        os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), d), exist_ok=True)

    server = create_server(host, port)
    print(f"Server running at http://{host}:{port}")
    print("Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
