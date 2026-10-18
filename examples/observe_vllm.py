"""Usage: python examples/observe_vllm.py"""
import os

from infertrace.stream import observe_completion
from infertrace.tracing import configure_tracing, inference_turn


def main() -> None:
    provider = configure_tracing(
        service_name="infertrace-client",
        otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
        console=os.getenv("INFERTRACE_CONSOLE_TRACES") == "1",
    )
    with inference_turn("demo-session", "turn-1"):
        for chunk in observe_completion(
            base_url=os.getenv("VLLM_BASE_URL", "http://localhost:8000"),
            model=os.getenv("VLLM_MODEL", "Qwen/Qwen2.5-0.5B-Instruct"),
            prompt="Explain KV cache in two sentences.",
        ):
            print(f"chunk={chunk.index} t={chunk.elapsed_ns / 1e6:.2f}ms text={chunk.text!r}")
    provider.force_flush()
    provider.shutdown()


if __name__ == "__main__":
    main()
