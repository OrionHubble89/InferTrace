# Event schema 1.0
`infertrace.events.Event` is the authoritative strict schema. Serialize with
`to_json()` and parse with `from_json()`. Unknown versions/fields and invalid
types are rejected; changes to the envelope require a version change and an
explicit migration. The client-chunk fixture is a compatibility regression test.

IDs join sessions, turns and requests. An all-zero trace/span ID explicitly
indicates no active recording context. Empty correlation IDs indicate unknown
scope, especially process-wide metrics. Aggregate vLLM metrics cannot be assigned
to a request. Client chunks and engine tokens have distinct types and sources.

`timestamp_ns` is only comparable within the named clock domain.
`observed_unix_ns` is wall-clock receipt time, not proof of cross-host alignment.
`missing` and `provenance` describe evidence limits. Parent event IDs encode
known causal edges; chronological adjacency does not imply causation.

The envelope has no prompt, completion text, API key or arbitrary attributes.
Only bounded identifiers, metric names and numeric observations are stored.
