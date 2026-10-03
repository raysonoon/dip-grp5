import { useEffect, useState } from 'react';
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';
import L from 'leaflet';
import { Link } from 'react-router-dom';
import { fetchVendors } from '../api/vendors';

import icon from 'leaflet/dist/images/marker-icon.png';
import iconShadow from 'leaflet/dist/images/marker-shadow.png';

// Fix for Leaflet's default icon missing issue in React
const DefaultIcon = L.icon({
  iconUrl: icon,
  shadowUrl: iconShadow,
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
});
L.Marker.prototype.options.icon = DefaultIcon;

const NTU_CENTER = [1.3483, 103.6831];

// Google Maps Universal URL: destination combines the vendor's name and coordinates.
function googleMapsDirectionsUrl(name, lat, lng) {
  const destination = encodeURIComponent(`${name} ${lat},${lng}`);
  return `https://www.google.com/maps/dir/?api=1&destination=${destination}`;
}

// Vendors without valid coordinates get no marker.
function hasCoordinates(vendor) {
  const point = vendor.map_coordinates;
  return (
    point != null &&
    Number.isFinite(point.lat) &&
    Number.isFinite(point.lng)
  );
}

export default function VendorMap() {
  const [vendors, setVendors] = useState([]);

  useEffect(() => {
    const controller = new AbortController();

    fetchVendors("", controller.signal)
      .then(setVendors)
      .catch((error) => {
        if (error.name !== "AbortError") {
          console.error("Could not load vendors for the map", error);
        }
      });

    return () => controller.abort();
  }, []);

  const mappedVendors = vendors.filter(hasCoordinates);

  return (
    <div className="relative z-0 rounded-2xl border border-border overflow-hidden">
      <MapContainer
        center={NTU_CENTER}
        zoom={15}
        scrollWheelZoom={false}
        style={{ height: '400px', width: '100%' }}
      >
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        />

        {mappedVendors.map((vendor) => {
          const { lat, lng } = vendor.map_coordinates;

          return (
            <Marker key={vendor.id} position={[lat, lng]}>
              <Popup>
                <div className="min-w-[160px] font-sans">
                  <strong className="text-base font-display">
                    {vendor.name}
                  </strong>

                  <br />

                  <span className="text-sm text-muted-foreground">
                    {vendor.location} · ⭐ {vendor.average_rating ?? vendor.average_google_rating ?? '—'}
                  </span>

                  <br />

                  <Link
                    to={`/vendors/${vendor.id}`}
                    className="text-primary text-sm font-semibold hover:underline block mt-2"
                  >
                    View Menu &amp; Reviews →
                  </Link>

                  <a
                    href={googleMapsDirectionsUrl(vendor.name, lat, lng)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary text-sm font-semibold hover:underline block mt-1"
                  >
                    Directions →
                  </a>
                </div>
              </Popup>
            </Marker>
          );
        })}
      </MapContainer>
    </div>
  );
}