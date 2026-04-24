# Phase 77 Multilingual/Multimodal Contract

## Decision

Brainstack must prove multilingual text memory behavior through recurring local gates and must define a typed non-text evidence contract without pretending full multimodal ingestion exists.

## Language Gate

The proof gate must cover:

- English
- Hungarian
- German
- non-Latin script

Coverage must span more than one shelf where practical: profile, graph, corpus, explicit capture, and final packet rendering.

## Modality Contract

The non-text evidence contract supports typed references for:

- `image`
- `file`
- `audio`
- `extracted_document`

The contract stores references, hashes, extractor metadata, and derived evidence refs. It rejects raw binary/base64 payloads in memory records.

## Truthful Unsupported State

Full multimodal extraction is not claimed in this phase. The phase proves evidence shape validation and future-safe projection contracts only.

## Measurement Rule

The gate reports:

- accuracy through golden hard gates
- token/packet size through max rendered packet chars
- latency through local gate runtime
- unsupported/deferred modality gaps explicitly

## Non-Goals

- No language-specific phrase lists.
- No benchmark-only scoring.
- No raw media storage in memory records.
- No pretending full image/audio/file extraction exists.
- No runtime scheduler/executor/governor behavior.

