from __future__ import annotations

from dataclasses import dataclass, field

from .text import tokenize


@dataclass(slots=True)
class QueryValidationResult:
    valid: bool
    why_not_valid: str | None = None
    suggestions: list[str] = field(default_factory=list)


class LenientQueryValidator:
    async def validate(self, query: str) -> QueryValidationResult:
        stripped = query.strip()
        if not stripped:
            return QueryValidationResult(
                valid=False,
                why_not_valid="Query cannot be empty",
                suggestions=[
                    "Describe a concrete topic, such as quantum error correction.",
                    "Add a method, material, or application area.",
                ],
            )

        informative_tokens = tokenize(stripped)
        if informative_tokens:
            return QueryValidationResult(valid=True)

        if any(char.isalnum() for char in stripped) and len(stripped) >= 3:
            return QueryValidationResult(valid=True)

        return QueryValidationResult(
            valid=False,
            why_not_valid="Query is too vague to run safely",
            suggestions=[
                "Include a named topic or concept.",
                "Add a publication constraint or method if needed.",
            ],
        )
