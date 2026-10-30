export const SITE_TITLE = "NTU Food Guide";

/**
 * "<Page name> | NTU Food Guide", or just "NTU Food Guide" without a name.
 * @param {string | null | undefined} pageName
 * @returns {string}
 */
export function formatDocumentTitle(pageName) {
  const name = typeof pageName === "string" ? pageName.trim() : "";
  return name ? `${name} | ${SITE_TITLE}` : SITE_TITLE;
}
