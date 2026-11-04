"""Source-grounded vendor names for plain and streaming chat answers."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
import re

from app.services.vendor_matching import (
    VendorEntry,
    normalize_vendor_text,
    normalize_vendor_text_with_offsets as _normalized_spans,
    vendor_name_aliases,
)


_PROTECTED = re.compile(
    r"```[\s\S]*?(?:```|\Z)|~~~[\s\S]*?(?:~~~|\Z)"
    r"|`[^`\n]*(?:`|\Z)"
    r"|(?:https?://|www\.)[^\s<>]+"
    r"|<[^>\n]*(?:>|\Z)",
    re.IGNORECASE,
)


def _protected_spans(text: str) -> list[tuple[int, int]]:
    ranges = [(match.start(), match.end()) for match in _PROTECTED.finditer(text)]
    # Markdown destinations may contain balanced or escaped parentheses. A
    # flat regex would stop at an inner ')' and expose the remaining URL as
    # ordinary answer text. Keep incomplete destinations protected as well.
    for match in re.finditer(r"\]\(", text):
        if any(left <= match.start() < right for left, right in ranges):
            continue
        start = position = match.end()
        depth = 1
        while position < len(text):
            character = text[position]
            if character == "\\":
                position += 2
                continue
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0:
                    position += 1
                    break
            position += 1
        ranges.append((start, min(position, len(text))))
    ranges.extend(
        (match.start(), match.end())
        for match in re.finditer(r"(?m)^[ \t]{0,3}\[[^\]\n]+\]:[^\n]*", text)
    )
    return ranges


class VendorAnswerNames:
    """Canonicalize only names supported by this answer's actual sources.

    The full catalog is used only to detect ambiguous aliases. It never adds a
    vendor to the answer or its sources. No vendor IDs or recommendation text
    are embedded here; spelling rules come from the shared alias metadata.
    """

    def __init__(
        self,
        supported: Iterable[VendorEntry],
        *,
        catalog: Iterable[VendorEntry] = (),
    ) -> None:
        self._supported = dict(supported)
        vendors = dict(catalog)
        vendors.update(self._supported)
        aliases = vendor_name_aliases(vendors.items()) if self._supported else {}
        self._targets = {
            alias: targets[0]
            for alias, targets in aliases.items()
            if len(targets) == 1 and targets[0][0] in self._supported
        }
        self._pattern = (
            re.compile(
                r"(?<![a-z0-9])(?:"
                + "|".join(re.escape(alias) for alias in sorted(aliases, key=len, reverse=True))
                + r")(?![a-z0-9])"
            )
            if self._targets else None
        )
        self._hold_words = max((len(alias.split()) for alias in aliases), default=0)
        self._alias_words = [alias.split() for alias in aliases]

    def _spans(self, text: str) -> list[tuple[int, int, str]]:
        if self._pattern is None:
            return []
        normalized, offsets = _normalized_spans(text)
        protected = _protected_spans(text)
        replacements: list[tuple[int, int, str]] = []
        for match in self._pattern.finditer(normalized):
            target = self._targets.get(match.group())
            if target is None:
                continue
            start, end = offsets[match.start()][0], offsets[match.end() - 1][1]
            name = target[1]
            if match.group() == normalize_vendor_text(name):
                # Include punctuation outside the final name token, notably
                # the ')' in an already complete branch-labelled name.
                canonical_normalized, canonical_offsets = _normalized_spans(name)
                tokens = list(re.finditer(r"[a-z0-9]+", canonical_normalized))
                if tokens:
                    leading = name[:canonical_offsets[tokens[0].start()][0]]
                    trailing = name[canonical_offsets[tokens[-1].end() - 1][1]:]
                    if leading and start >= len(leading) and text[start - len(leading):start] == leading:
                        start -= len(leading)
                    if trailing and text[end:end + len(trailing)] == trailing:
                        end += len(trailing)
            if any(start < right and end > left for left, right in protected):
                continue
            # Preserve surrounding Markdown; avoid consuming internal markup
            # such as '*Quad* Cafe' and leaving an unmatched emphasis marker.
            if any(marker in text[start:end] for marker in ("*", "_", "`", "[", "]")):
                continue
            if re.search(r"[.!?;:\n]|(?:[-\u2010-\u2015]\s*){2,}", text[start:end]) and text[start:end] != name:
                continue
            if text[start:end] != name:
                replacements.append((start, end, name))
        return replacements

    @staticmethod
    def _render(
        text: str,
        replacements: list[tuple[int, int, str]],
        start: int,
        end: int,
    ) -> str:
        parts: list[str] = []
        cursor = start
        for left, right, name in replacements:
            if left < start or right > end:
                continue
            parts.extend((text[cursor:left], name))
            cursor = right
        parts.append(text[cursor:end])
        return "".join(parts)

    def rewrite(self, text: str) -> str:
        return self._render(text, self._spans(text), 0, len(text))

    def stream(self, chunks: Iterable[str]) -> Iterator[str]:
        """Keep possible name prefixes until their complete identity is known.

        Holding a directory-derived number of words makes the emitted result
        independent of LLM chunk boundaries, including splits inside a name.
        Answers with no supported names retain their original streaming path.
        """
        if self._pattern is None:
            yield from chunks
            return
        text = ""
        emitted = 0
        for chunk in chunks:
            text += chunk
            normalized, offsets = _normalized_spans(text)
            words = list(re.finditer(r"[a-z0-9]+", normalized))
            cutoff = len(text)
            last_complete = normalized.endswith(" ")
            # Only hold a suffix that could still become a recognized name.
            # Ordinary text can keep streaming immediately.
            for count in range(1, min(self._hold_words, len(words)) + 1):
                suffix = [word.group() for word in words[-count:]]
                for alias in self._alias_words:
                    if len(alias) < count or alias[:count - 1] != suffix[:-1]:
                        continue
                    if last_complete:
                        possible = suffix[-1] == alias[count - 1] and count < len(alias)
                    else:
                        possible = alias[count - 1].startswith(suffix[-1])
                    if possible:
                        cutoff = min(cutoff, offsets[words[-count].start()][0])
                        break
            pending_reference = re.search(r"(?m)^[ \t]{0,3}\[[^\]\n]*(?:\][ \t]*)?\Z", text)
            if pending_reference:
                # Do not emit a rewritten reference ID before a following
                # ':' reveals that this line defines a Markdown link target.
                cutoff = min(cutoff, pending_reference.start())
            replacements = self._spans(text)
            for start, end, _ in replacements:
                if start < cutoff < end:
                    cutoff = start
            if cutoff > emitted:
                yield self._render(text, replacements, emitted, cutoff)
                emitted = cutoff
        if emitted < len(text):
            yield self._render(text, self._spans(text), emitted, len(text))
