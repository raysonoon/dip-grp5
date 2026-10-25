/** @typedef {{ id: number, name: string, location: string | null, category: string | null, rating: number | null }} WheelVendor */
/** @typedef {{ vendors: WheelVendor[], excludedIds: number[] }} WheelSession */
/** @typedef {{ type: 'sources', sources: unknown[] } | { type: 'remove', vendorId: number } | { type: 'reset' }} WheelAction */

const VENDOR_SOURCE_TYPES = new Set(["vendor", "reddit", "google_review"]);
const text = (value) => typeof value === "string" && value.trim() ? value.trim() : null;
const rating = (value) => typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 5 ? value : null;

/** @returns {WheelSession} */
export function createWheelSession() {
  return { vendors: [], excludedIds: [] };
}

/**
 * Keep this pool separate from bounded model history and from partial streams.
 * Exclusions last until the next session, even if later sources repeat a vendor.
 * @param {WheelSession} state
 * @param {WheelAction} action
 * @returns {WheelSession}
 */
export function wheelSessionReducer(state, action) {
  if (action.type === "reset") return createWheelSession();
  if (action.type === "remove") {
    if (state.vendors.length < 2 || !state.vendors.some((vendor) => vendor.id === action.vendorId)) return state;
    return {
      vendors: state.vendors.filter((vendor) => vendor.id !== action.vendorId),
      excludedIds: [...state.excludedIds, action.vendorId],
    };
  }
  const vendors = new Map(state.vendors.map((vendor) => [vendor.id, vendor]));
  for (const value of action.sources) {
    if (value === null || typeof value !== "object" || Array.isArray(value)) continue;
    const source = /** @type {Record<string, unknown>} */ (value);
    const id = source.vendor_id;
    if (!VENDOR_SOURCE_TYPES.has(source.source_type) || typeof id !== "number"
      || !Number.isSafeInteger(id) || id <= 0 || state.excludedIds.includes(id)) continue;
    const previous = vendors.get(id);
    vendors.set(id, {
      id,
      name: text(source.vendor_name) ?? previous?.name ?? `Vendor ${id}`,
      location: text(source.location) ?? previous?.location ?? null,
      category: text(source.category) ?? previous?.category ?? null,
      rating: rating(source.rating) ?? previous?.rating ?? null,
    });
  }
  return { vendors: [...vendors.values()], excludedIds: state.excludedIds };
}

/**
 * Pick equal-size sectors and land their centre precisely under the top pointer.
 * @param {WheelVendor[]} vendors
 */
export function chooseWheelSpin(vendors, currentRotation = 0, random = Math.random()) {
  if (vendors.length === 0) throw new Error("At least one vendor is needed to spin.");
  if (!Number.isFinite(random) || random < 0 || random >= 1) throw new Error("Invalid random value.");
  const index = Math.floor(random * vendors.length);
  const target = (360 - (index + 0.5) * 360 / vendors.length) % 360;
  const rotation = currentRotation + 5 * 360 + (target - currentRotation % 360 + 360) % 360;
  return { vendor: vendors[index], rotation };
}

/** @param {WheelVendor} vendor */
export function completeWheelVendor(vendor, catalog) {
  const details = catalog.find((item) => item.id === vendor.id);
  return details ? {
    ...vendor,
    name: text(details.name) ?? vendor.name,
    location: text(details.location) ?? vendor.location,
    category: text(details.category) ?? vendor.category,
    rating: rating(details.average_rating) ?? rating(details.average_google_rating) ?? vendor.rating,
  } : vendor;
}
