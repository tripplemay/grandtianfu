'use client'
import * as React from "react";
import Map from "react-map-gl";

import "mapbox-gl/dist/mapbox-gl.css";

const MAPBOX_TOKEN =
  "REDACTED_MAPBOX_TOKEN"; // Set your mapbox token her

export default function MapComponent() {
  return (
    <Map
      initialViewState={{
        latitude: 37.8,
        longitude: -122.4,
        zoom: 14,
      }}
      style={{ width: 800, height: 600 }}
      mapStyle='mapbox://styles/mapbox/streets-v9'
      mapboxAccessToken={MAPBOX_TOKEN}></Map>
  );
}
