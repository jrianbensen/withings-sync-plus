#!/usr/bin/env python3
"""
HTTP File Server for /withings directory

This script creates a simple HTTP file server that exposes files from the /withings directory
on port 7200. It provides a web interface with file listings showing sizes and modification dates.

Dependencies:
- No external dependencies required (uses Python standard library only)
- Requires Python 3.6+

Usage:
- Run directly: python3 file_server.py
- Or add to entrypoint.sh: python3 /path/to/file_server.py &
"""

import os
import sys
import html
import urllib.parse
import datetime
import mimetypes
import socket
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import logging
import traceback

# === VARIABLES ===
SERVER_PORT = int(os.getenv("SERVER_PORT", 7200))
SERVE_DIRECTORY = os.getenv("SERVE_DIRECTORY", "/withings")
LOG_FILE = os.getenv("LOG_FILE", "/var/log/file_server.log")
BIND_ADDRESS = os.getenv("BIND_ADDRESS", "0.0.0.0")
BUFFER_SIZE = int(os.getenv("BUFFER_SIZE", 1024 * 1024))
BASE_PATH = os.getenv("BASE_PATH", "/wt")

# === LOGGING SETUP ===
def setup_logging():
    """Setup logging to both file and console"""
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'

    # Create formatter
    formatter = logging.Formatter(log_format, datefmt=date_format)

    # Setup root logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler
    try:
        # Create log directory if it doesn't exist
        log_dir = os.path.dirname(LOG_FILE)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)

        file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        logging.error(f"Failed to create log file at {LOG_FILE}: {str(e)}")

    return logger

# Initialize logging
logger = setup_logging()
  
class FileServerHandler(BaseHTTPRequestHandler):
    """Custom HTTP request handler for file serving"""

    def do_GET(self):
        """Handle GET requests"""
        try:
            # Parse the path and remove base path if present
            parsed_path = urllib.parse.unquote(self.path)
            if parsed_path.startswith(BASE_PATH):
                parsed_path = parsed_path[len(BASE_PATH):]
            if not parsed_path.startswith('/'):
                parsed_path = '/' + parsed_path

            # Remove query string if present
            parsed_path = parsed_path.split('?')[0]

            # Construct full file path
            full_path = os.path.normpath(os.path.join(SERVE_DIRECTORY, parsed_path.lstrip('/')))

            # Security check: ensure path is within SERVE_DIRECTORY
            if not full_path.startswith(os.path.abspath(SERVE_DIRECTORY)):
                logger.warning(f"Attempted access outside serve directory: {full_path}")
                self.send_error(403, "Access denied")
                return

            logger.info(f"Processing request for: {parsed_path} -> {full_path}")

            if os.path.isdir(full_path):
                self.serve_directory(full_path, parsed_path)
            elif os.path.isfile(full_path):
                self.serve_file(full_path)
            else:
                logger.warning(f"Path not found: {full_path}")
                self.send_error(404, "File not found")

        except Exception as e:
            logger.error(f"Error handling GET request for {self.path}: {str(e)}\n{traceback.format_exc()}")
            self.send_error(500, f"Internal server error: {str(e)}")

    def serve_directory(self, dir_path, url_path):
        """Serve directory listing"""
        try:
            # Get list of files and directories
            items = []
            for item in os.listdir(dir_path):
                item_path = os.path.join(dir_path, item)
                try:
                    stat = os.stat(item_path)
                    items.append({
                        'name': item,
                        'path': item_path,
                        'is_dir': os.path.isdir(item_path),
                        'size': stat.st_size,
                        'mtime': stat.st_mtime
                    })
                except Exception as e:
                    logger.warning(f"Failed to stat {item_path}: {str(e)}")

            # Sort items: directories first, then alphabetically
            items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))

            # Generate HTML
            html_content = self.generate_directory_html(items, url_path)

            # Send response
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', len(html_content.encode('utf-8')))
            self.end_headers()
            self.wfile.write(html_content.encode('utf-8'))

            logger.info(f"Successfully served directory listing for: {dir_path} ({len(items)} items)")

        except Exception as e:
            logger.error(f"Error serving directory {dir_path}: {str(e)}\n{traceback.format_exc()}")
            self.send_error(500, f"Error listing directory: {str(e)}")


    def serve_file(self, file_path):
        """Serve a single file"""
        try:
            # Get file size
            file_size = os.path.getsize(file_path)

            # Guess content type
            content_type, _ = mimetypes.guess_type(file_path)
            if not content_type:
                content_type = 'application/octet-stream'

            # Send headers
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', file_size)
            self.send_header('Content-Disposition', f'inline; filename="{os.path.basename(file_path)}"')
            self.end_headers()

            # Send file content
            bytes_sent = 0
            with open(file_path, 'rb') as f:
                while True:
                    chunk = f.read(BUFFER_SIZE)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    bytes_sent += len(chunk)

            logger.info(f"Successfully served file: {file_path} ({bytes_sent} bytes)")

        except Exception as e:
            logger.error(f"Error serving file {file_path}: {str(e)}\n{traceback.format_exc()}")
            self.send_error(500, f"Error serving file: {str(e)}")

    def generate_directory_html(self, items, url_path):
        """Generate HTML for directory listing"""
        # Ensure url_path ends with /
        if not url_path.endswith('/'):
            url_path += '/'

        # Build HTML
        html_parts = [
            '<!DOCTYPE html>',
            '<html>',
            '<head>',
            '<meta charset="utf-8">',
            '<title>Directory listing for ' + html.escape(url_path) + '</title>',
            '<style>',
            'body { font-family: monospace; margin: 20px; }',
            'table { border-collapse: collapse; }',
            'th, td { padding: 5px 15px; text-align: left; }',
            'th { background-color: #f0f0f0; border-bottom: 2px solid #ddd; }',
            'tr:hover { background-color: #f5f5f5; }',
            'a { text-decoration: none; color: #0066cc; }',
            'a:hover { text-decoration: underline; }',
            '.dir { font-weight: bold; }',
            '.size { text-align: right; }',
            '</style>',
            '</head>',
            '<body>',
            '<h1>Directory listing for ' + html.escape(url_path) + '</h1>',
            '<table>',
            '<tr><th>Name</th><th>Size</th><th>Last Modified</th></tr>'
        ]

        # Add parent directory link if not at root
        if url_path != '/' and url_path.rstrip('/') != '':
            parent_path = os.path.dirname(url_path.rstrip('/'))
            if not parent_path.endswith('/'):
                parent_path += '/'
            html_parts.append(f'<tr><td colspan="3"><a href="{BASE_PATH}{parent_path}">[Parent Directory]</a></td></tr>')

        # Add items
        for item in items:
            name = html.escape(item['name'])
            if item['is_dir']:
                name_html = f'<a href="{BASE_PATH}{url_path}{name}/" class="dir">{name}/</a>'
                size_html = '&lt;DIR&gt;'
            else:
                name_html = f'<a href="{BASE_PATH}{url_path}{name}">{name}</a>'
                size_html = format_size(item['size'])

            mtime = datetime.datetime.fromtimestamp(item['mtime']).strftime('%Y-%m-%d %H:%M:%S')

            html_parts.append(
                f'<tr><td>{name_html}</td><td class="size">{size_html}</td><td>{mtime}</td></tr>'
            )

        html_parts.extend([
            '</table>',
            '<hr>',
            f'<p>{len(items)} items</p>',
            '</body>',
            '</html>'
        ])

        return '\n'.join(html_parts)

    def log_message(self, format, *args):
        """Override to suppress default console output"""
        # We're handling logging ourselves
        pass

def format_size(size):
    """Format file size in human-readable format"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            if unit == 'B':
                return f"{size} {unit}"
            else:
                return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"

def main():
    """Main server function"""
    try:
        logger.info("=" * 60)
        logger.info("Starting HTTP File Server")
        logger.info(f"Serving directory: {SERVE_DIRECTORY}")
        logger.info(f"Server port: {SERVER_PORT}")
        logger.info(f"Bind address: {BIND_ADDRESS}")
        logger.info(f"Base URL path: {BASE_PATH}")
        logger.info("=" * 60)

        # Check if serve directory exists
        if not os.path.exists(SERVE_DIRECTORY):
            logger.error(f"Serve directory does not exist: {SERVE_DIRECTORY}")
            logger.error("Please create the directory or update SERVE_DIRECTORY variable")
            sys.exit(1)

        if not os.path.isdir(SERVE_DIRECTORY):
            logger.error(f"Serve path is not a directory: {SERVE_DIRECTORY}")
            sys.exit(1)

        # Create server
        server = HTTPServer((BIND_ADDRESS, SERVER_PORT), FileServerHandler)
        logger.info(f"Server started successfully on {BIND_ADDRESS}:{SERVER_PORT}")
        logger.info(f"Access the server at: http://{socket.gethostname()}:{SERVER_PORT}{BASE_PATH}")
        logger.info("Press Ctrl+C to stop the server")

        # Run server
        server.serve_forever()

    except KeyboardInterrupt:
        logger.info("\nReceived interrupt signal, shutting down server...")
        server.socket.close()
        logger.info("Server stopped successfully")
    except Exception as e:
        logger.error(f"Failed to start server: {str(e)}\n{traceback.format_exc()}")
        sys.exit(1)
    finally:
        logger.info("=" * 60)
        logger.info("File server terminated")
        logger.info("=" * 60)

if __name__ == "__main__":
    main()
