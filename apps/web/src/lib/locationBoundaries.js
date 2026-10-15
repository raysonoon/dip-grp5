const METERS_PER_DEG = 111320;

/** Accepts {lat,lng}, {latitude,longitude} or GeoJSON {coordinates:[lng,lat]}. */
export function vendorLatLng(vendor) {
  const c = vendor?.map_coordinates ?? vendor?.coordinates;
  if (!c) return null;
  let lat;
  let lng;
  if (Array.isArray(c.coordinates)) {
    [lng, lat] = c.coordinates;
  } else {
    lat = c.lat ?? c.latitude;
    lng = c.lng ?? c.lon ?? c.longitude;
  }
  if (lat == null || lng == null) return null;
  lat = Number(lat);
  lng = Number(lng);
  return Number.isFinite(lat) && Number.isFinite(lng) ? { lat, lng } : null;
}

function cross(o, a, b) {
  return (a.lng - o.lng) * (b.lat - o.lat) - (a.lat - o.lat) * (b.lng - o.lng);
}

/** Andrew's monotone chain convex hull. */
export function convexHull(points) {
  const pts = [...points].sort((a, b) => a.lng - b.lng || a.lat - b.lat);
  if (pts.length < 3) return pts;
  const lower = [];
  for (const p of pts) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop();
    lower.push(p);
  }
  const upper = [];
  for (let i = pts.length - 1; i >= 0; i -= 1) {
    const p = pts[i];
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop();
    upper.push(p);
  }
  lower.pop();
  upper.pop();
  return lower.concat(upper);
}

/** Surround every point with a small ring so 1-2 vendor locations still get an area. */
export function padPoints(points, radiusM = 45, steps = 8) {
  const out = [];
  for (const p of points) {
    const dLat = radiusM / METERS_PER_DEG;
    const dLng = radiusM / (METERS_PER_DEG * Math.cos((p.lat * Math.PI) / 180));
    for (let i = 0; i < steps; i += 1) {
      const a = (2 * Math.PI * i) / steps;
      out.push({ lat: p.lat + dLat * Math.sin(a), lng: p.lng + dLng * Math.cos(a) });
    }
  }
  return out;
}

export function locationColor(index) {
  // golden-angle hue steps keep neighbouring locations visually distinct
  return `hsl(${Math.round((index * 137.508) % 360)}, 70%, 45%)`;
}

/**
 * One boundary per `location` that has at least one vendor with coordinates.
 * Pass the UNFILTERED vendor list so colours stay stable while filters change.
 */
export function buildLocationBoundaries(vendors, { paddingM = 45 } = {}) {
  const groups = new Map();
  for (const vendor of vendors ?? []) {
    const name = String(vendor?.location ?? "").trim();
    const point = vendorLatLng(vendor);
    if (!name || !point) continue;
    if (!groups.has(name)) groups.set(name, []);
    groups.get(name).push(point);
  }
  return [...groups.keys()]
    .sort((a, b) => a.localeCompare(b))
    .map((location, index) => {
      const points = groups.get(location);
      const hull = convexHull(padPoints(points, paddingM));
      return {
        location,
        color: locationColor(index),
        count: points.length,
        positions: hull.map((p) => [p.lat, p.lng]),
      };
    });
}