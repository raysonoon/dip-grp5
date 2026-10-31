import { MapContainer, Marker, Popup, TileLayer } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import "./vendorMap.css";
import { googleMapsDirectionsUrl, pinIcon } from "./VendorClusterLayer.jsx";
import { vendorLatLng } from "../lib/locationBoundaries.js";

const DETAIL_ZOOM = 18;

/**
 * Single-pin map for one vendor's exact location.
 * Renders nothing when the vendor has no map_coordinates, so callers can
 * mount it unconditionally without producing a blank map.
 */
export default function VendorLocationMap({ vendor }) {
  const point = vendor ? vendorLatLng(vendor) : null;
  if (!point) return null;

  const position = [point.lat, point.lng];

  return (
    <section className="mb-8" aria-label={`Location of ${vendor.name}`}>
      <h2 className="text-lg font-bold text-foreground mb-3">Location</h2>
      {/* relative z-0, as on MapPage: keeps Leaflet's high z-index panes below
          the site header and the delete-review modal. */}
      <div className="relative z-0 h-64 sm:h-72 rounded-xl overflow-hidden border border-border">
        <MapContainer
          key={vendor.id}
          center={position}
          zoom={DETAIL_ZOOM}
          scrollWheelZoom={false}
          className="h-full w-full"
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <Marker position={position} icon={pinIcon} title={vendor.name}>
            <Popup>
              <div className="vendor-popup">
                <div style={{ fontWeight: 600 }}>{vendor.name}</div>
                {vendor.location && <div>{vendor.location}</div>}
                <a
                  href={googleMapsDirectionsUrl(vendor.name, point.lat, point.lng)}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Directions →
                </a>
              </div>
            </Popup>
          </Marker>
        </MapContainer>
      </div>
    </section>
  );
}