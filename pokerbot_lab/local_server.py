#!/usr/bin/env python3
"""Tiny localhost-only static server for the exported Bet2Bot WebView spike."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

class ReusableHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True

parser = argparse.ArgumentParser()
parser.add_argument("--root", required=True)
parser.add_argument("--port", required=True, type=int)
args = parser.parse_args()
server = ReusableHTTPServer(("127.0.0.1", args.port), partial(QuietHandler, directory=args.root))
server.serve_forever()
