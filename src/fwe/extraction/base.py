from __future__ import annotations

from typing import Protocol

from fwe.domain.models import ExtractedInvoice


class ExtractionError(Exception):
    """The document could not be parsed into an invoice at all."""


class Extractor(Protocol):
    """Port for document understanding. Implementations: regex over OCR text, Azure Document
    Intelligence, AWS Textract, an LLM with structured output. All return per-field confidence."""

    def extract(self, text: str) -> ExtractedInvoice: ...
