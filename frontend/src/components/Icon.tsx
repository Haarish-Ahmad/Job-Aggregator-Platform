// Small stroke icons drawn inline: no icon font or extra package, and nothing the CSP has to allow.
const PATHS = {
  search: "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM20 20l-4-4",
  sliders: "M4 7h9M17 7h3M4 17h3M11 17h9M15 5v4M9 15v4",
  briefcase: "M4 8h16v11H4zM9 8V6a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2M4 13h16",
  cap: "M2 9l10-5 10 5-10 5zM6 11v5c3 2 9 2 12 0v-5",
  clock: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7v5l3 2",
  file: "M6 3h9l4 4v14H6zM14 3v5h5",
  upload: "M12 16V4M7 9l5-5 5 5M4 16v4h16v-4",
  layers: "M12 3l9 5-9 5-9-5zM3 13l9 5 9-5",
  pin: "M12 21s-7-6-7-11a7 7 0 0 1 14 0c0 5-7 11-7 11zM12 8a2 2 0 1 0 0 4 2 2 0 0 0 0-4z",
  globe: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18",
  target: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z",
  chart: "M4 20h16M7 16v-5M12 16V6M17 16v-8",
  user: "M12 4a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM4 21a8 8 0 0 1 16 0",
  menu: "M4 7h16M4 12h16M4 17h16",
  bell: "M6 9a6 6 0 0 1 12 0c0 6 3 7 3 7H3s3-1 3-7M10 20a2 2 0 0 0 4 0",
  calendar: "M4 6h16v14H4zM4 10h16M8 3v4M16 3v4",
  refresh: "M20 11a8 8 0 0 0-14-5l-2 2M4 4v4h4M4 13a8 8 0 0 0 14 5l2-2M20 20v-4h-4",
  external: "M14 4h6v6M20 4l-9 9M18 14v5H5V6h5",
  left: "M15 18l-6-6 6-6",
  right: "M9 18l6-6-6-6",
  arrow: "M5 12h14M13 6l6 6-6 6",
  logout: "M9 4H5v16h4M16 16l4-4-4-4M20 12H10",
  sparkle: "M12 3l2 6 6 2-6 2-2 6-2-6-6-2 6-2z",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 18, className }: { name: IconName; size?: number; className?: string }) {
  return (
    <svg
      className={className ? `icon ${className}` : "icon"}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
