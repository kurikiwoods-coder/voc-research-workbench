"""Run M09 verification against a verified local model with network auditing."""

import argparse
from contextlib import redirect_stdout
import ipaddress
import os
from pathlib import Path
import sys
import unittest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model_dir", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("patterns", nargs="+")
    parser.add_argument("--app-site-packages", type=Path)
    parser.add_argument("--topic-quality-diagnostics", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    if args.app_site_packages:
        sys.path.append(str(args.app_site_packages.resolve(strict=True)))
    for key in tuple(os.environ):
        if key.upper().startswith((
            "VOC_", "TAVILY_", "BRAVE_", "PACKY", "JEV", "HF_", "HUGGINGFACE_", "OPENAI_", "TYPESAFE_", "YOUTUBE_",
        )) or key.upper().endswith(("_API_KEY", "_TOKEN")):
            del os.environ[key]
    os.environ.update(
        HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1",
        OMP_NUM_THREADS="2", MKL_NUM_THREADS="2", OPENBLAS_NUM_THREADS="2", NUMBA_NUM_THREADS="2",
        VOC_M09_MODEL_DIR=str(args.model_dir.resolve(strict=True)),
        VOC_M09_MODEL_MANIFEST=str(args.manifest.resolve(strict=True)),
    )
    if args.topic_quality_diagnostics:
        os.environ["VOC_RUN_M09_TOPIC_QUALITY_GATE"] = "1"
    attempts = []

    def check_network(event, event_args):
        if event in {"socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr", "socket.getnameinfo"}:
            target = event_args[0]
        elif event in {"socket.connect", "socket.sendto"}:
            target = event_args[1]
        else:
            return
        host = target[0] if isinstance(target, tuple) else target
        try:
            if ipaddress.ip_address(host).is_loopback:
                return
        except (TypeError, ValueError):
            pass
        attempts.append(event)
        raise RuntimeError("M09 verification blocks non-loopback network operations")

    sys.addaudithook(check_network)
    with redirect_stdout(sys.stderr):
        suite = unittest.TestSuite(
            unittest.TestLoader().discover(str(root / "tests"), pattern=pattern) for pattern in args.patterns
        )
        if not suite.countTestCases():
            parser.error("No matching verification tests")
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        print(f"Non-loopback socket and DNS attempts: {len(attempts)}", flush=True)
    return 0 if result.wasSuccessful() and not attempts else 1


if __name__ == "__main__":
    raise SystemExit(main())
