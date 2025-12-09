# morphio/http_server.py

import http.server
import socketserver
import threading
import os


class HttpServer:
    """
    Minimal static-file HTTP server.
    Ensures ui_root is properly bound to the handler via closure
    (Python 3.10–3.12 compatible).
    """

    def __init__(self, host="127.0.0.1", port=8080, ui_root="sarpedon"):
        self.host = host
        self.port = port

        # Resolve absolute UI directory
        self.ui_root = os.path.abspath(ui_root)

        if not os.path.isdir(self.ui_root):
            raise RuntimeError(f"UI root does not exist: {self.ui_root}")

        self.httpd = None
        self.thread = None

    def start(self):
        print(f"[HTTP] UI root = {self.ui_root}")

        # Closure-bound handler so handler has correct directory
        def make_handler(ui_path):
            class _Handler(http.server.SimpleHTTPRequestHandler):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, directory=ui_path, **kwargs)

                # optional: clean logging
                def log_message(self, fmt, *args):
                    pass

            return _Handler

        handler = make_handler(self.ui_root)

        self.httpd = socketserver.TCPServer((self.host, self.port), handler)
        print(f"[HTTP] Serving UI on http://{self.host}:{self.port}/")

        # Threaded server
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            print("[HTTP] stopped")

