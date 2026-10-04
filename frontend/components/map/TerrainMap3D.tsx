"use client";

import React, { useEffect, useRef, useState } from "react";
import { useMapStore, PanchayatFeature } from "../../stores/mapStore";
import { ChoroplethMap2D } from "./ChoroplethMap2D";
import { WeatherParticlesOverlay } from "./WeatherParticlesOverlay";
import { api } from "../../lib/api";

function checkWebGL(): boolean {
  if (typeof window === "undefined") return false;
  try {
    const canvas = document.createElement("canvas");
    return !!(
      window.WebGLRenderingContext &&
      (canvas.getContext("webgl") || canvas.getContext("experimental-webgl"))
    );
  } catch {
    return false;
  }
}

export function TerrainMap3D() {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapInstance = useRef<any>(null);
  const [webglOk, setWebglOk] = useState<boolean | null>(null);
  const [geojson, setGeojson] = useState<any>(null);
  const [hasError, setHasError] = useState<boolean>(false);

  const {
    selectedLayer,
    selectedWeek,
    selectedPanchayat,
    setSelectedPanchayat,
    setWebglSupported,
  } = useMapStore();

  // 1. Initial WebGL capability check
  useEffect(() => {
    const supported = checkWebGL();
    setWebglOk(supported);
    setWebglSupported(supported);

    // Fetch GeoJSON for both 2D fallback and search overlay
    api.geo
      .getPanchayatsGeoJson(selectedWeek)
      .then((data) => setGeojson(data))
      .catch((err) => {
        console.warn("Failed to load geojson for fallback:", err);
      });
  }, [selectedWeek, setWebglSupported]);

  // 2. Initialize MapLibre GL 3D Terrain when WebGL is available
  useEffect(() => {
    if (!webglOk || !mapContainer.current || mapInstance.current) return;

    let map: any = null;
    try {
      const maplibregl = require("maplibre-gl");
      map = new maplibregl.Map({
        container: mapContainer.current,
        style: {
          version: 8,
          sources: {
            osm: {
              type: "raster",
              tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
              tileSize: 256,
              attribution: "&copy; OpenStreetMap Contributors",
            },
            // DEM Terrain Elevation Source
            "terrain-dem": {
              type: "raster-dem",
              tiles: ["https://demotiles.maplibre.org/terrain-tiles/{z}/{x}/{y}.png"],
              tileSize: 256,
            },
            // MVT Vector Tiles for Blocks (low zoom)
            "blocks-tiles": {
              type: "vector",
              tiles: [api.geo.getBlockTileUrl(selectedWeek)],
              minzoom: 0,
              maxzoom: 8,
            },
            // MVT Vector Tiles for Panchayats (high zoom)
            "panchayats-tiles": {
              type: "vector",
              tiles: [api.geo.getPanchayatTileUrl(selectedWeek)],
              minzoom: 8,
              maxzoom: 14,
            },
          },
          layers: [
            {
              id: "osm-layer",
              type: "raster",
              source: "osm",
              minzoom: 0,
              maxzoom: 19,
            },
          ],
        },
        center: [78.9629, 20.5937], // Centre of India
        zoom: 4.8,
        pitch: 45,
        bearing: 0,
        maxPitch: 75,
      });

      map.on("load", () => {
        mapInstance.current = map;
        if (typeof window !== "undefined" && process.env.NODE_ENV !== "production") {
          (window as any).__maplibreMap = map;
        }

        // Set 3D Terrain
        try {
          map.setTerrain({ source: "terrain-dem", exaggeration: 1.5 });
        } catch (e) {
          // Soft fail for DEM if CORS restricted
        }

        // Add 3D Extrusion Layer for Panchayats GeoJSON
        if (geojson) {
          map.addSource("panchayats-3d", {
            type: "geojson",
            data: geojson,
          });

          map.addLayer({
            id: "panchayats-extrusion",
            type: "fill-extrusion",
            source: "panchayats-3d",
            paint: {
              "fill-extrusion-color": [
                "interpolate",
                ["linear"],
                ["get", `${selectedLayer}_prob`],
                0,
                "#bae6fd",
                0.5,
                "#0284c7",
                1,
                "#1e3a8a",
              ],
              "fill-extrusion-height": [
                "*",
                ["get", `${selectedLayer}_prob`],
                15000,
              ],
              "fill-extrusion-opacity": 0.85,
            },
          });

          map.on("click", "panchayats-extrusion", (e: any) => {
            const props = e.features?.[0]?.properties;
            if (props) {
              setSelectedPanchayat(props);
            }
          });
        }
      });

      map.on("error", (e: any) => {
        console.warn("MapLibre runtime error, falling back to 2D:", e);
        setHasError(true);
      });
    } catch (e) {
      console.warn("MapLibre initialization failed, falling back to 2D:", e);
      setHasError(true);
    }

    return () => {
      if (map) {
        map.remove();
        mapInstance.current = null;
      }
    };
  }, [webglOk, geojson, selectedLayer, selectedWeek, setSelectedPanchayat]);

  // 3. FitBounds / FlyTo when a panchayat is selected
  useEffect(() => {
    if (mapInstance.current && selectedPanchayat) {
      const lon = selectedPanchayat.centroid_lon;
      const lat = selectedPanchayat.centroid_lat;
      if (lon && lat) {
        mapInstance.current.flyTo({
          center: [lon, lat],
          zoom: 9.5,
          pitch: 55,
          speed: 1.2,
          curve: 1.4,
          essential: true,
        });
      }
    }
  }, [selectedPanchayat]);

  // If WebGL is absent or encountered an error, render the 2D accessible fallback
  if (!webglOk || hasError) {
    return <ChoroplethMap2D geojson={geojson} onSelectPanchayat={setSelectedPanchayat} />;
  }

  return (
    <div className="relative w-full h-full" id="maplibre-3d-container">
      <div ref={mapContainer} className="w-full h-full" />
      <WeatherParticlesOverlay />
    </div>
  );
}
