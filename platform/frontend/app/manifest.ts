import type { MetadataRoute } from "next";

/** The installability manifest.
 *
 * `start_url` is `/work` rather than `/`: `/` is the marketing landing page,
 * and a clinician who installed the application to their home screen has
 * already decided. `AuthGuard` sends them to `/login?next=/work` if the
 * session has expired, which is the right landing either way.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "SEPHIROTH — Clinical AI Copilot",
    short_name: "SEPHIROTH",
    description: "Decision support and daily clinical operations, for healthcare professionals.",
    start_url: "/work",
    display: "standalone",
    background_color: "#EBF3FE",
    theme_color: "#3683F8",
    orientation: "portrait",
    icons: [
      { src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" },
      { src: "/apple-icon", sizes: "180x180", type: "image/png" },
    ],
  };
}
