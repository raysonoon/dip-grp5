import { useEffect } from "react";

import { formatDocumentTitle } from "./documentTitle.js";

/** Set the browser tab title for the current page. */
export function useDocumentTitle(pageName?: string | null): void {
  const title = formatDocumentTitle(pageName);

  useEffect(() => {
    document.title = title;
  }, [title]);
}
