import { vendorRating } from "./vendorRanking.js";
import { vendorLatLng } from "./locationBoundaries.js";
import { sortFilterOptions } from "./filterOptions.js";

function isDiscoverable(vendor) {
  return !/^(demo|test)$/i.test(vendor.category?.trim() ?? "");
}

export function guestDiscoveryOptions(vendors) {
  const catalog = vendors.filter(isDiscoverable);
  const values = (field) => sortFilterOptions([
    ...new Set(catalog.map((vendor) => vendor[field]).filter(Boolean)),
  ]);
  return {
    cuisines: values("cuisine"),
    categories: values("category"),
    locations: values("location"),
  };
}

function coordinates(vendor) {
  const point = vendorLatLng(vendor);
  return point && Math.abs(point.lat) <= 90 && Math.abs(point.lng) <= 180 ? point : null;
}

function validLocation(point) {
  return point != null && Number.isFinite(point.lat) && Number.isFinite(point.lng)
    && Math.abs(point.lat) <= 90 && Math.abs(point.lng) <= 180;
}

function median(values) {
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

// Estimate each area's centre from its full vendor catalog, independently of
// food/dietary choices. Distances are straight-line estimates, not walking routes.
function areaCentres(catalog, locations) {
  return locations.flatMap((location) => {
    const points = catalog.filter((vendor) => vendor.location === location).map(coordinates).filter(Boolean);
    return points.length ? [{ lat: median(points.map((point) => point.lat)), lng: median(points.map((point) => point.lng)), label: location, source: "area" }] : [];
  });
}

function distanceMetres(from, to) {
  const radians = Math.PI / 180;
  const dLat = (to.lat - from.lat) * radians;
  const dLng = (to.lng - from.lng) * radians;
  const a = Math.sin(dLat / 2) ** 2
    + Math.cos(from.lat * radians) * Math.cos(to.lat * radians) * Math.sin(dLng / 2) ** 2;
  return 6371000 * 2 * Math.asin(Math.sqrt(Math.min(1, Math.max(0, a))));
}

export function recommendGuestVendors(
  vendors,
  /** @type {{ cuisines?: string[], categories?: string[], locations?: string[], halal?: boolean, vegetarian?: boolean, priceRanges?: string[], userLocation?: { lat: number, lng: number } | null }} */
  { cuisines = [], categories = [], locations = [], halal = false, vegetarian = false, priceRanges = [], userLocation = null } = {},
) {
  const catalog = vendors.filter(isDiscoverable);
  const centres = areaCentres(catalog, locations);
  const hasGps = validLocation(userLocation);
  // GPS is another selected reference point. Keep each distance's actual origin
  // so the UI never labels an area-centre distance as a distance from the user.
  if (hasGps && userLocation) centres.unshift({ ...userLocation, label: "you", source: "gps" });
  return catalog
    .filter((vendor) => (!halal || vendor.halal === true)
      && (!vegetarian || vendor.vegetarian === true)
      && (priceRanges.length === 0 || priceRanges.includes(vendor.price_range)))
    .map((vendor) => {
      const point = coordinates(vendor);
      const distances = point ? centres.map((centre) => distanceMetres(point, centre)) : [];
      const distance = distances.length ? Math.min(...distances) : null;
      const origin = distance == null ? null : centres[distances.indexOf(distance)];
      const cuisineMatch = cuisines.includes(vendor.cuisine);
      const categoryMatch = categories.includes(vendor.category);
      const locationMatch = locations.includes(vendor.location);
      const proximity = distance == null ? (centres.length === 0 ? Number(locationMatch) : 0) : 1 / (1 + distance / 500);
      // Cuisine and category are one "food preference" signal. Nearby
      // alternatives can outrank a far-away food match. Nothing is removed for
      // its food choice or distance; rating breaks relevance ties.
      const foodMatch = Number(cuisineMatch || categoryMatch);
      const relevance = (cuisines.length || categories.length ? 0.4 * foodMatch : 0)
        + (locations.length || hasGps ? 0.6 * proximity : 0);
      return {
        ...vendor,
        discovery_distance_m: distance,
        discovery_distance_from: origin?.label ?? null,
        discovery_distance_source: origin?.source ?? null,
        discovery_cuisine_match: cuisineMatch,
        discovery_category_match: categoryMatch,
        discovery_location_match: locationMatch,
        discovery_relevance: relevance,
      };
    })
    .sort((a, b) => b.discovery_relevance - a.discovery_relevance
      || (a.discovery_distance_m ?? Infinity) - (b.discovery_distance_m ?? Infinity)
      || (vendorRating(b) ?? -1) - (vendorRating(a) ?? -1)
      || a.name.localeCompare(b.name));
}
