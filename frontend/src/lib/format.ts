const CURRENCY_SYMBOLS: Record<string, string> = {
	USD: '$',
	EUR: '€',
	GBP: '£',
	INR: '₹',
	AED: 'AED ',
	JPY: '¥',
};

/** Deal-currency amounts with Indian digit grouping, per the approved mockups
 *  (e.g. "$1,80,000"). */
export function fmtMoney(value: number | null | undefined, currency?: string | null): string {
	if (value === null || value === undefined || Number.isNaN(value)) return '—';
	const symbol = currency ? (CURRENCY_SYMBOLS[currency] ?? `${currency} `) : '';
	const negative = value < 0;
	const grouped = new Intl.NumberFormat('en-IN', {
		minimumFractionDigits: 0,
		maximumFractionDigits: 2,
	}).format(Math.abs(value));
	return `${negative ? '−' : ''}${symbol}${grouped}`;
}

/** "18 Jun" — table/metaline date per mockups. */
export function fmtDate(value: string | null | undefined): string {
	if (!value) return '—';
	const d = new Date(value + 'T00:00:00');
	if (Number.isNaN(d.getTime())) return value;
	return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' });
}

/** "18 Jun 2026" — headers and facts. */
export function fmtDateLong(value: string | null | undefined): string {
	if (!value) return '—';
	const d = new Date(value + 'T00:00:00');
	if (Number.isNaN(d.getTime())) return value;
	return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

/** Whole days from today to the given date (negative = past). */
export function daysUntil(value: string | null | undefined): number | null {
	if (!value) return null;
	const target = new Date(value + 'T00:00:00');
	if (Number.isNaN(target.getTime())) return null;
	const today = new Date();
	today.setHours(0, 0, 0, 0);
	return Math.round((target.getTime() - today.getTime()) / 86_400_000);
}
