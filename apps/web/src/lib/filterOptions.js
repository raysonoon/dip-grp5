// "Others" is a catch-all bucket rather than a real cuisine/category, so it
// belongs at the end of the list instead of alphabetically in the middle.
export function isOtherOption(value) {
  return /^others?$/i.test(String(value ?? "").trim());
}

export function sortFilterOptions(values) {
  return [...values].sort(
    (a, b) =>
      Number(isOtherOption(a)) - Number(isOtherOption(b)) ||
      a.localeCompare(b),
  );
}
