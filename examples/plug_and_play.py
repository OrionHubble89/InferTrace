"""Config-driven baseline integration; no inference engine source patch."""

import argparse
import os
from contextlib import closing, nullcontext

from infertrace.adapters import HTTPExporter
from infertrace.collector import Collector
from infertrace.config import load_config
from infertrace.stream import observe_completion
from infertrace.tracing import configure_tracing, inference_session, inference_turn


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config")
    args = parser.parse_args()
    config = load_config(args.config)
    provider = (
        configure_tracing(
            install_global=False, otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        )
        if config.enabled
        else None
    )
    collector = Collector(
        HTTPExporter(config.collector_url),
        capacity=config.capacity,
        batch_size=config.batch_size,
        sample_rate=config.sample_rate,
        adaptive=config.adaptive,
        enabled=config.enabled,
    )
    try:
        session = (
            inference_session("demo-session", collector=collector)
            if config.enabled
            else nullcontext()
        )
        turn = (
            inference_turn("demo-session", "turn-1", collector=collector)
            if config.enabled
            else nullcontext()
        )
        with session, turn:
            with closing(
                observe_completion(
                    base_url=config.base_url,
                    model=config.model,
                    prompt="Explain KV cache.",
                    api_key=config.api_key(),
                    collector=collector,
                    enabled=config.enabled,
                )
            ) as stream:
                for chunk in stream:
                    print(f"client chunk {chunk.index}: {chunk.elapsed_ns / 1e6:.2f} ms")
        if not collector.flush():
            raise RuntimeError("collector did not drain before timeout")
        if collector.stats().export_errors:
            raise RuntimeError("telemetry export failed")
    finally:
        collector.close()
        if provider is not None:
            provider.shutdown()


if __name__ == "__main__":
    main()
