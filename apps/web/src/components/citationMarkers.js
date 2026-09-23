export const CITATION_MARKER_PATTERN = "\\[((?:\\d+\\s*,\\s*)*\\d+)\\]";

export function citationNumbers(markerContent) {
  return markerContent.split(",").map((value) => Number(value.trim()));
}
