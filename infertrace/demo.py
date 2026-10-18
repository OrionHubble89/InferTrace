"""Run: python -m infertrace.demo"""

import time

from opentelemetry import trace

from infertrace.tracing import configure_tracing, inference_request, inference_turn


def main() -> None:
    provider = configure_tracing(console=True)
    with inference_turn("demo-session", "turn-1"):
        with inference_request("Qwen/Qwen2.5-0.5B-Instruct"):
            tracer = trace.get_tracer("infertrace.demo")
            with tracer.start_as_current_span("infertrace.request.prefill"):
                time.sleep(0.01)
            with tracer.start_as_current_span("infertrace.request.decode"):
                time.sleep(0.02)
    provider.force_flush()
    provider.shutdown()


if __name__ == "__main__":
    main()
