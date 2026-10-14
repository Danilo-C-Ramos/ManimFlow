"""A local stand-in for the OpenAI Responses API, so the real Codex app-server runs offline.

Each request the app-server makes gets the next scripted reply: a list of output
items such as an assistant message or a shell command, or an HTTP error. Codex
runs the commands in its real sandbox and sends their output back in the next
request.
"""

import json
import threading
from collections import deque
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

Item = dict


def message(text: str) -> Item:
    return {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}


def command(call_id: str, cmd: str) -> Item:
    return {"type": "function_call", "name": "exec_command", "call_id": call_id, "arguments": json.dumps({"cmd": cmd})}


def patch(call_id: str, text: str) -> Item:
    """An apply_patch call; `text` holds the lines between Begin Patch and End Patch."""
    body = f"*** Begin Patch\n{text}*** End Patch\n"
    return {"type": "custom_tool_call", "name": "apply_patch", "call_id": call_id, "input": body}


@dataclass
class HttpError:
    status: int
    error: dict


class MockModel:
    def __init__(self) -> None:
        self.requests: list[dict] = []
        self._replies: deque[list[Item] | HttpError] = deque()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    @property
    def address(self) -> tuple[str, int]:
        host, port = self._server.server_address[:2]
        return str(host), int(port)

    @property
    def url(self) -> str:
        host, port = self.address
        return f"http://{host}:{port}/v1"

    def reply(self, *items: Item) -> None:
        """Queues the output of one model request."""
        self._replies.append(list(items))

    def fail(self, status: int, error: dict) -> None:
        """Queues an HTTP error, shaped like the OpenAI API's, for one model request."""
        self._replies.append(HttpError(status, error))

    def configure(self, codex_home: Path) -> None:
        """Points the Codex install in `codex_home` at this server.

        Codex still picks the tools it offers from the model name: a model in
        its catalog gets apply_patch, and an unknown one gets web search.
        """
        codex_home.mkdir(parents=True, exist_ok=True)
        (codex_home / "config.toml").write_text(
            'model_provider = "mock"\n\n'
            "[model_providers.mock]\n"
            'name = "mock"\n'
            f'base_url = "{self.url}"\n'
            'wire_api = "responses"\n'
            # Errors end the turn at once instead of after Codex's backoff.
            "request_max_retries = 0\n"
            "stream_max_retries = 0\n",
            encoding="utf-8",
        )

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def _next_reply(self) -> list[Item] | HttpError:
        # A turn that runs past its script ends quietly instead of hanging.
        return self._replies.popleft() if self._replies else [message("Fim do roteiro.")]

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        model = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                model.requests.append(body)
                reply = model._next_reply()
                if isinstance(reply, HttpError):
                    self.send_response(reply.status)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": reply.error}).encode())
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                response_id = f"resp_{len(model.requests)}"
                events = [{"type": "response.created", "response": {"id": response_id}}]
                events += [{"type": "response.output_item.done", "item": item} for item in reply]
                events.append({"type": "response.completed", "response": {"id": response_id}})
                for event in events:
                    self.wfile.write(f"event: {event['type']}\ndata: {json.dumps(event)}\n\n".encode())

            def do_GET(self) -> None:
                self.send_response(404)
                self.end_headers()

            def log_message(self, format: str, *args: object) -> None:
                pass

        return Handler
