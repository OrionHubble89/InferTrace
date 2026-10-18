# Security and privacy defaults
Prompt, completion, tool inputs/outputs and API keys are absent from the event
schema. Only bounded correlation identifiers, operation/model names and numeric
observations are persisted. HTTP chunk text is returned directly to the caller
and is not telemetry. OTel exceptions retain the SDK's default exception messages
and stack traces; applications handling sensitive errors should configure their
own span processor/redaction policy before enabling external OTel export.

Keep IDs/model/tool names free of sensitive content. These are caller-selected
metadata, not magically anonymized values. OTLP ingestion drops arbitrary span
attributes including gen_ai.prompt. API access logs are disabled. UI uses
textContent rather than HTML interpolation and has no third-party resources.

The HTTP server is trusted-local only, with no authentication/TLS/multi-tenancy.
Default host and Compose published ports are loopback. Do not expose them to an
untrusted network. Use an authenticated reverse proxy and production server for
shared deployment; that integration is outside this MVP. HTTP bodies/events,
query page sizes and export queues have explicit limits. SQLite stores metadata
on disk without application-level encryption or automatic retention/deletion.
Protect the volume and remove it intentionally when no longer needed.

Configuration selects outbound URLs, so config must be trusted. API keys come
from environment variables; TLS verification remains enabled for HTTPS.
Background failure logs do not dump credentials or payloads. Dependency checks
run pip-audit over the installed runtime graph and npm audit for UI test tooling.
Those checks do not replace a full security review.
