import { useEffect, useMemo, useRef } from "react";
import { Polygon, Tooltip } from "react-leaflet";
import L from "leaflet";
import { buildLocationBoundaries } from "../lib/locationBoundaries.js";

export function LocationBoundaries({ vendors }) {
  const boundaries = useMemo(() => buildLocationBoundaries(vendors), [vendors]);
  return boundaries.map((b) => (
    <Polygon
      key={b.location}
      positions={b.positions}
      pathOptions={{ color: b.color, fillColor: b.color, fillOpacity: 0.18, weight: 2 }}
    >
      <Tooltip sticky>{`${b.location} · ${b.count} vendor${b.count === 1 ? "" : "s"}`}</Tooltip>
    </Polygon>
  ));
}

/** Render INSIDE <MapContainer>. */
export function LocationLegend({ vendors }) {
  const boundaries = useMemo(() => buildLocationBoundaries(vendors), [vendors]);
  const ref = useRef(null);
  useEffect(() => {
    if (ref.current) {
      L.DomEvent.disableClickPropagation(ref.current);
      L.DomEvent.disableScrollPropagation(ref.current);
    }
  }, []);
  if (!boundaries.length) return null;
  return (
    <div
      ref={ref}
      className="absolute bottom-6 left-2 z-[1000] max-h-48 overflow-y-auto rounded-lg bg-white/90 p-2 text-xs shadow"
    >
      {boundaries.map((b) => (
        <div key={b.location} className="flex items-center gap-2 py-0.5">
          <span className="inline-block h-3 w-3 rounded-sm" style={{ background: b.color }} />
          <span>{b.location}</span>
          <span className="text-gray-500">({b.count})</span>
        </div>
      ))}
    </div>
  );
}