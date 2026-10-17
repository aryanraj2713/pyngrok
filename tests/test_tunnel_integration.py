"""Actual native transport tests. Require a built engine; never substitute a mock."""

from __future__ import annotations

import concurrent.futures
import json
import os
import queue
import shutil
import socket
import socketserver
import subprocess
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from pyngrok.engine import find_engine

TOKEN = "integration-only-shared-token-0123456789"


@pytest.fixture
def engine() -> Path:
    try:
        return find_engine()
    except ValueError:
        pytest.skip("Native engine is absent; build crates/pyngrok-core first")


class Echo(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        while chunk := self.request.recv(65536):
            self.request.sendall(chunk)


class EchoServer(socketserver.ThreadingTCPServer):
    daemon_threads = True


@contextmanager
def core(binary: Path, args: list[str], *, token: str = TOKEN) -> Iterator[subprocess.Popen[str]]:
    process = subprocess.Popen(
        [str(binary), *args],
        env={**os.environ, "PYNGROK_TOKEN": token},
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        yield process
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        if process.stdout:
            process.stdout.close()


def event(process: subprocess.Popen[str], expected: str) -> dict[str, object]:
    result: queue.Queue[str] = queue.Queue()
    assert process.stdout is not None
    stream = process.stdout
    thread = threading.Thread(target=lambda: result.put(stream.readline()), daemon=True)
    thread.start()
    line = result.get(timeout=10)
    value: dict[str, object] = json.loads(line)
    assert value["event"] == expected, value
    return value


def address(value: object) -> tuple[str, int]:
    host, port = str(value).rsplit(":", 1)
    return host, int(port)


@pytest.mark.parametrize("tls", [False, True])
def test_concurrent_binary_transfers_and_session_cleanup(
    engine: Path, tmp_path: Path, tls: bool
) -> None:
    relay_args = ["relay", "--bind", "127.0.0.1:0"]
    agent_tls: list[str] = []
    if tls:
        openssl = shutil.which("openssl")
        if openssl is None:
            pytest.skip("TLS integration needs openssl for an ephemeral certificate")
        cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
        ca, ca_key, csr = tmp_path / "ca.pem", tmp_path / "ca-key.pem", tmp_path / "leaf.csr"
        config = tmp_path / "openssl.cnf"
        config.write_text(
            "[req]\ndistinguished_name=dn\nx509_extensions=ca\nprompt=no\n"
            "[dn]\nCN=pyngrok integration CA\n[ca]\nbasicConstraints=critical,CA:TRUE\n"
            "keyUsage=critical,keyCertSign,cRLSign\n"
            "[leaf]\nsubjectAltName=DNS:localhost\nbasicConstraints=critical,CA:FALSE\n"
            "keyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n"
        )
        for command in [
            [
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-config",
                str(config),
                "-keyout",
                str(ca_key),
                "-out",
                str(ca),
            ],
            [
                "req",
                "-new",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-subj",
                "/CN=localhost",
                "-keyout",
                str(key),
                "-out",
                str(csr),
            ],
            [
                "x509",
                "-req",
                "-in",
                str(csr),
                "-CA",
                str(ca),
                "-CAkey",
                str(ca_key),
                "-set_serial",
                "1",
                "-days",
                "1",
                "-extfile",
                str(config),
                "-extensions",
                "leaf",
                "-out",
                str(cert),
            ],
        ]:
            subprocess.run([openssl, *command], check=True, capture_output=True)
        relay_args += ["--tls-cert", str(cert), "--tls-key", str(key)]
        agent_tls = ["--tls-server-name", "localhost", "--ca-cert", str(ca)]
    with EchoServer(("127.0.0.1", 0), Echo) as upstream:
        thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        try:
            with core(engine, relay_args) as relay:
                ready = event(relay, "relay_ready")
                with core(
                    engine,
                    [
                        "connect",
                        "--relay",
                        str(ready["bind"]),
                        "--upstream",
                        f"127.0.0.1:{upstream.server_address[1]}",
                        *agent_tls,
                    ],
                ) as agent:
                    tunnel = event(agent, "tunnel_ready")
                    public = address(tunnel["public_address"])

                    def transfer(index: int) -> None:
                        payload = bytes(range(256)) * (index + 1) * 64
                        with socket.create_connection(public, timeout=5) as stream:
                            stream.settimeout(10)
                            stream.sendall(payload)
                            stream.shutdown(socket.SHUT_WR)
                            received = bytearray()
                            while chunk := stream.recv(65536):
                                received.extend(chunk)
                        assert received == payload

                    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                        list(pool.map(transfer, range(8)))
                # Ending the control session must release its public listener.
                deadline = time.monotonic() + 5
                while True:
                    try:
                        with socket.create_connection(public, timeout=0.2):
                            pass
                    except OSError:
                        break
                    assert time.monotonic() < deadline, "public listener survived agent exit"
                    time.sleep(0.05)
        finally:
            upstream.shutdown()
            thread.join(timeout=5)


def test_wrong_token_is_rejected(engine: Path) -> None:
    with core(engine, ["relay", "--bind", "127.0.0.1:0"]) as relay:
        ready = event(relay, "relay_ready")
        with core(
            engine,
            ["connect", "--relay", str(ready["bind"]), "--upstream", "127.0.0.1:1"],
            token="different-token-0123456789",
        ) as agent:
            failure = event(agent, "error")
            assert "rejected" in str(failure["message"])
            assert agent.wait(timeout=5) != 0
