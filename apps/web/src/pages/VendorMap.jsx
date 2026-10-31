import { useEffect, useMemo, useState } from 'react';
import { MapContainer, TileLayer } from 'react-leaflet';
import { Link } from 'react-router-dom';
import 'leaflet/dist/leaflet.css';
import { fetchVendors } from '../api/vendors';
import VendorClusterLayer from '../components/VendorClusterLayer';
import { LocationBoundaries, LocationLegend } from '../components/LocationOverlays';

const NTU_CENTER = [1.3483, 103.6831];

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

    fetchVendors('', controller.signal)
      .then(setVendors)
      .catch((error) => {
        if (error.name !== 'AbortError') {
          console.error('Could not load vendors for the map', error);
        }
      });

    return () => controller.abort();
  }, []);

  const mappedVendors = useMemo(() => vendors.filter(hasCoordinates), [vendors]);

  return (
    <div>
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

          <LocationBoundaries vendors={mappedVendors} />
          <VendorClusterLayer vendors={mappedVendors} />
          <LocationLegend vendors={mappedVendors} />
        </MapContainer>
      </div>

      <div className="mt-2 text-right">
        <Link to="/map" className="text-sm font-semibold text-primary hover:underline">
          View the full map →
        </Link>
      </div>
    </div>
  );
}