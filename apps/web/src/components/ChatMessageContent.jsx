import { Children, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ExternalLink, Quote } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { Link } from "react-router-dom";
import remarkBreaks from "remark-breaks";

import { CITATION_MARKER_PATTERN, citationNumbers } from "./citationMarkers.js";

const SOURCE_LABELS = {
  count: "Count",
  google_review: "Google review",
  internal_review: "NTU Foodie review",
  reddit: "Reddit comment",
  vendor: "Vendor",
};

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function redditUrl(permalink) {
  if (!permalink) return null;
  try {
    const url = new URL(permalink, "https://www.reddit.com");
    const hostname = url.hostname.toLowerCase();
    if (hostname !== "reddit.com" && !hostname.endsWith(".reddit.com")) {
      return null;
    }
    return url.toString();
  } catch {
    return null;
  }
}

function CitationPopover({ source, citationNumber, showVendorLink }) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef(null);
  const buttonRef = useRef(null);
  const tooltipRef = useRef(null);
  const [placement, setPlacement] = useState(null);
  const externalUrl = source.source_type === "reddit"
    ? redditUrl(source.permalink)
    : null;

  useEffect(() => {
    if (!open) return undefined;

    function closeOnOutsideClick(event) {
      if (
        !containerRef.current?.contains(event.target) &&
        !tooltipRef.current?.contains(event.target)
      ) {
        setOpen(false);
      }
    }

    function closeOnEscape(event) {
      if (event.key === "Escape") setOpen(false);
    }

    document.addEventListener("pointerdown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  function positionTooltip() {
    const button = buttonRef.current;
    const tooltip = tooltipRef.current;
    if (!button || !tooltip) return;

    const chatWindow = button.closest("[data-chat-window]");
    const chatRect = chatWindow?.getBoundingClientRect() ?? null;
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;

    const maxWidth = chatRect
      ? Math.min(256, chatRect.width - 32)
      : Math.min(256, viewportWidth - 32);

    tooltip.style.maxWidth = `${maxWidth}px`;

    const tooltipHeight = tooltip.offsetHeight;
    const tooltipWidth = tooltip.offsetWidth;
    const buttonRect = button.getBoundingClientRect();
    const gap = 8;

    const bounds = chatRect
      ? { left: chatRect.left, right: chatRect.right, top: chatRect.top, bottom: chatRect.bottom }
      : { left: 0, right: viewportWidth, top: 0, bottom: viewportHeight };

    const spaceAbove = buttonRect.top - bounds.top - gap;
    const spaceBelow = bounds.bottom - buttonRect.bottom - gap;
    const flipBelow = spaceAbove < tooltipHeight && spaceBelow >= spaceAbove;

    let rawTop;
    if (flipBelow) {
      rawTop = buttonRect.bottom + gap;
    } else {
      rawTop = buttonRect.top - tooltipHeight - gap;
    }
    const top = Math.max(
      bounds.top + gap,
      Math.min(rawTop, bounds.bottom - tooltipHeight - gap)
    );

    const left = Math.min(
      Math.max(bounds.left + gap, buttonRect.left),
      bounds.right - tooltipWidth - gap
    );

    setPlacement({ top, left, maxWidth });
  }

  useLayoutEffect(() => {
    if (!open) return undefined;

    positionTooltip();
    function closeOnScroll() {
      setOpen(false);
    }
    window.addEventListener("scroll", closeOnScroll, true);
    window.addEventListener("resize", positionTooltip);
    return () => {
      window.removeEventListener("scroll", closeOnScroll, true);
      window.removeEventListener("resize", positionTooltip);
    };
  }, [open]);

  return (
    <span ref={containerRef} className="relative inline-flex items-center gap-1 align-middle">
      {showVendorLink && source.vendor_id != null && source.vendor_name && (
        <Link
          to={`/vendors/${source.vendor_id}`}
          target="_blank"
          rel="noreferrer"
          className="font-medium text-primary underline decoration-primary/40 underline-offset-2 hover:decoration-primary"
        >
          {source.vendor_name}
        </Link>
      )}
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen((current) => !current)}
        className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-primary/10 text-primary transition-colors hover:bg-primary/20 focus:outline-none focus:ring-2 focus:ring-primary/40"
        aria-label={`Open source ${citationNumber}`}
        aria-expanded={open}
      >
        <Quote className="h-3 w-3" aria-hidden="true" />
      </button>
      {open &&
        createPortal(
          <span
            ref={tooltipRef}
            role="tooltip"
            className="fixed z-50 block rounded-xl border border-border bg-card p-3 text-left text-xs font-normal leading-relaxed text-foreground shadow-xl"
            style={placement ? { top: placement.top, left: placement.left } : undefined}
          >
            <span className="mb-1 block font-semibold text-primary">
              {SOURCE_LABELS[source.source_type] ?? source.source_type}
            </span>
            {source.vendor_name && (
              source.vendor_id != null ? (
                <Link
                  to={`/vendors/${source.vendor_id}`}
                  target="_blank"
                  rel="noreferrer"
                  className="mb-2 block font-semibold text-foreground hover:text-primary"
                >
                  {source.vendor_name}
                </Link>
              ) : (
                <span className="mb-2 block font-semibold">{source.vendor_name}</span>
              )
            )}
            {source.excerpt && (
              <span className="block text-muted-foreground">{source.excerpt}</span>
            )}
            {externalUrl && (
              <a
                href={externalUrl}
                target="_blank"
                rel="noreferrer"
                className="mt-2 inline-flex items-center gap-1 font-semibold text-primary hover:underline"
              >
                Open Reddit comment
                <ExternalLink className="h-3 w-3" aria-hidden="true" />
              </a>
            )}
          </span>,
          document.body
        )}
    </span>
  );
}

function decorateText(text, sources, answerText) {
  const vendors = [];
  const seenVendors = new Set();
  for (const source of sources) {
    if (source.vendor_id == null || !source.vendor_name) continue;
    const key = source.vendor_name.toLocaleLowerCase();
    if (seenVendors.has(key)) continue;
    seenVendors.add(key);
    vendors.push(source);
  }
  vendors.sort((left, right) => right.vendor_name.length - left.vendor_name.length);

  const patterns = [CITATION_MARKER_PATTERN, ...vendors.map((source) => escapeRegExp(source.vendor_name))];
  const matcher = new RegExp(patterns.join("|"), "gi");
  const parts = [];
  let cursor = 0;

  for (const match of text.matchAll(matcher)) {
    if (match.index > cursor) parts.push(text.slice(cursor, match.index));
    const citationMatch = new RegExp(`^${CITATION_MARKER_PATTERN}$`).exec(match[0]);

    if (citationMatch) {
      const citations = citationNumbers(citationMatch[1]);
      parts.push(...citations.map((citationNumber) => {
        const source = sources[citationNumber - 1];
        if (!source) return `[${citationNumber}]`;

        const vendorMentioned = source.vendor_name
          ? answerText.toLocaleLowerCase().includes(source.vendor_name.toLocaleLowerCase())
          : false;
        return (
          <CitationPopover
            key={`citation-${match.index}-${citationNumber}`}
            source={source}
            citationNumber={citationNumber}
            showVendorLink={!vendorMentioned}
          />
        );
      }));
    } else {
      const source = vendors.find(
        (candidate) => candidate.vendor_name.toLocaleLowerCase() === match[0].toLocaleLowerCase(),
      );
      parts.push(
        <Link
          key={`vendor-${match.index}-${source.vendor_id}`}
          to={`/vendors/${source.vendor_id}`}
          target="_blank"
          rel="noreferrer"
          className="font-medium text-primary underline decoration-primary/40 underline-offset-2 hover:decoration-primary"
        >
          {match[0]}
        </Link>,
      );
    }
    cursor = match.index + match[0].length;
  }

  if (cursor < text.length) parts.push(text.slice(cursor));
  return parts.length ? parts : text;
}

function decorateChildren(children, sources, answerText) {
  return Children.map(children, (child) => (
    typeof child === "string" ? decorateText(child, sources, answerText) : child
  ));
}

/**
 * @param {object} props
 * @param {string} props.answer
 * @param {unknown[]} [props.sources]
 */
export default function ChatMessageContent({ answer, sources = [] }) {
  const components = useMemo(() => ({
    p: ({ children }) => (
      <p className="mb-2 last:mb-0">{decorateChildren(children, sources, answer)}</p>
    ),
    ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>,
    ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>,
    li: ({ children }) => <li>{decorateChildren(children, sources, answer)}</li>,
    strong: ({ children }) => (
      <strong className="font-semibold">{decorateChildren(children, sources, answer)}</strong>
    ),
    em: ({ children }) => <em>{decorateChildren(children, sources, answer)}</em>,
    a: ({ href, children }) => {
      if (href?.startsWith("/")) {
        return (
          <Link
            to={href}
            target="_blank"
            rel="noreferrer"
            className="text-primary underline"
          >
            {children}
          </Link>
        );
      }
      return (
        <a href={href} target="_blank" rel="noreferrer" className="text-primary underline">
          {children}
        </a>
      );
    },
  }), [answer, sources]);

  return (
    <div className="chat-markdown break-words">
      <ReactMarkdown remarkPlugins={[remarkBreaks]} components={components}>
        {answer}
      </ReactMarkdown>
    </div>
  );
}
