import type { CSSProperties, SVGProps } from 'react';

/**
 * DUX thin-stroke icon set — 24×24 viewBox, 1.7 stroke, round caps/joins,
 * currentColor. The first block follows the design system's Icon.jsx; the
 * second block carries the extra glyphs from the approved ExportFlow mockups
 * (exact paths). Where the mockups diverge from Icon.jsx — 'check', 'sun',
 * 'truck', 'calendar' — the MOCKUP variants are used deliberately; do not
 * "re-sync" them against the design system.
 */
const PATHS: Record<string, string> = {
	// — DUX design-system originals —
	filter: '<path d="M3 5h18l-7 8v6l-4-2v-4z"/>',
	clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
	building:
		'<path d="M5 21V5a1 1 0 0 1 1-1h8a1 1 0 0 1 1 1v16"/><path d="M15 9h3a1 1 0 0 1 1 1v11"/><path d="M9 8h2M9 12h2M9 16h2"/><path d="M3 21h18"/>',
	rupee: '<path d="M7 5h10M7 9h10M16 5c0 4-3.5 5-6.5 5L16 19"/><path d="M7 9h3"/>',
	box: '<path d="M21 8 12 3 3 8v8l9 5 9-5z"/><path d="M3 8l9 5 9-5M12 13v8"/>',
	search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
	sparkle:
		'<path d="M12 3l1.6 4.8L18 9.4l-4.4 1.6L12 16l-1.6-5L6 9.4l4.4-1.6z"/><path d="M19 14l.7 2.1L22 17l-2.3.9L19 20l-.7-2.1L16 17l2.3-.9z"/>',
	send: '<path d="M12 19V5"/><path d="m5 12 7-7 7 7"/>',
	plus: '<path d="M12 5v14"/><path d="M5 12h14"/>',
	moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
	sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
	chevron: '<path d="m15 18-6-6 6-6"/>',
	layers: '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>',
	refresh:
		'<path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M21 4v4h-4"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/><path d="M3 20v-4h4"/>',
	check: '<path d="m5 13 4 4L19 7"/>',
	close: '<path d="M6 6l12 12M18 6 6 18"/>',
	copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h8"/>',
	download: '<path d="M12 4v11"/><path d="m7 11 5 5 5-5"/><path d="M5 20h14"/>',
	user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',

	// — ExportFlow mockup glyphs (exact paths from the approved screens) —
	truck:
		'<path d="M1 8h13v8H1zM14 11h4l3 3v2h-7z"/><circle cx="5.5" cy="18" r="1.8"/><circle cx="17.5" cy="18" r="1.8"/>',
	calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
	ship: '<path d="M2 20h20M4 17h14a4 4 0 0 0 4-4H8L6 9H3l1.5 4L3 17z"/>',
	plane:
		'<path d="M10.5 13.5 3 11l1.5-1.5L10 10l4.5-4.5a1.6 1.6 0 0 1 2.3 2.3L12.5 12l.5 5.5L11.5 19l-2.5-7.5z"/><path d="M2 21h20"/>',
	'file-text': '<path d="M8 3h8l4 4v14H8z"/><path d="M16 3v4h4M11 12h6M11 16h6"/>',
	'file-text-alt': '<path d="M8 3h8l4 4v14H8z"/><path d="M16 3v4h4M11 13h6M11 17h4"/>',
	file: '<path d="M8 3h8l4 4v14H8z"/><path d="M16 3v4h4"/>',
	banknote: '<path d="M6 4h12M6 9h12M8 4c6 3 6 0 10 5-6 0-6 2-4 5l-4 6C8 14 6 12 6 9"/>',
	shield: '<path d="M12 3 3 8v3c0 5 3.8 8.6 9 10 5.2-1.4 9-5 9-10V8z"/>',
	'shield-check': '<path d="M12 3 3 8v3c0 5 3.8 8.6 9 10 5.2-1.4 9-5 9-10V8z"/><path d="m9 12 2 2 4-4"/>',
	package: '<path d="M21 8 12 3 3 8l9 5 9-5zM3 8v8l9 5 9-5V8"/><path d="M12 13v8"/>',
	cube: '<path d="M21 8 12 3 3 8l9 5 9-5zM3 8v8l9 5 9-5V8"/>',
	'circle-check': '<path d="m9 12 2 2 4-4"/><circle cx="12" cy="12" r="9"/>',
	warning: '<path d="M12 3 2 20h20zM12 10v4M12 17.5v.5"/>',
	exclamation: '<path d="M12 6v6M12 16.5v.5"/>',
	'link-boxes': '<path d="M3 7h7v7H3zM14 10h7v7h-7zM6.5 14v3.5h7.5"/>',
	sliders: '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3"/><path d="M1 14h6M9 8h6M17 16h6"/>',
};

export type IconName = keyof typeof PATHS;
export const ICON_NAMES = Object.keys(PATHS) as IconName[];

interface IconProps extends Omit<SVGProps<SVGSVGElement>, 'name' | 'style'> {
	name?: IconName;
	size?: number;
	color?: string;
	strokeWidth?: number;
	style?: CSSProperties;
}

export function Icon({
	name = 'sparkle',
	size = 18,
	color = 'currentColor',
	strokeWidth = 1.7,
	style = {},
	...rest
}: IconProps) {
	const d = PATHS[name] || PATHS.sparkle;
	return (
		<svg
			viewBox="0 0 24 24"
			width={size}
			height={size}
			fill="none"
			stroke={color}
			strokeWidth={strokeWidth}
			strokeLinecap="round"
			strokeLinejoin="round"
			style={{ display: 'block', flex: '0 0 auto', ...style }}
			dangerouslySetInnerHTML={{ __html: d }}
			{...rest}
		/>
	);
}
