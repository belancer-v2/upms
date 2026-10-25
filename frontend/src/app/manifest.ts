import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "FlatWise", short_name: "FlatWise", description: "Your building, in order.", start_url: "/app", display: "standalone",
    background_color: "#F7F3F3", theme_color: "#691542",
    icons: [{ src: "/brand/icon-192.png", sizes: "192x192", type: "image/png" }, { src: "/brand/icon-512.png", sizes: "512x512", type: "image/png" }],
  };
}
