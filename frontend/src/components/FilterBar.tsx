import { useMemo, useState } from 'react';
import { Icon } from '@/components/Icon';

/** A config-driven filter bar for list views. Filters are applied CLIENT-SIDE
 *  over the already-fetched rows (the lists are bounded), so adding a filter is
 *  just a row-field accessor — no endpoint changes. */
export type FilterControl = 'select' | 'toggle';

export interface FilterDef<Row> {
	key: string;
	label: string;
	control: FilterControl;
	/** the value used for matching (and, for selects, for deriving options) */
	get: (row: Row) => string | number | boolean | null | undefined;
	/** explicit, ordered options for a select; when omitted, distinct row values
	 *  are derived and sorted */
	options?: { value: string; label: string }[];
}

export type FilterState = Record<string, string>;

export function useFilterState() {
	const [state, setState] = useState<FilterState>({});
	return {
		state,
		set: (key: string, value: string) => setState((s) => ({ ...s, [key]: value })),
		clear: () => setState({}),
	};
}

/** Apply the active filters to a row set. A toggle keeps only truthy rows when
 *  on; a select keeps rows whose value equals the selection. Empty = inactive. */
export function applyFilters<Row>(rows: Row[], defs: FilterDef<Row>[], state: FilterState): Row[] {
	const active = defs.filter((d) => state[d.key]);
	if (!active.length) return rows;
	return rows.filter((row) =>
		active.every((def) => {
			const sel = state[def.key];
			const v = def.get(row);
			if (def.control === 'toggle') return !!v;
			return String(v ?? '') === sel;
		}),
	);
}

export function FilterBar<Row>({
	rows,
	defs,
	state,
	onChange,
	onClear,
}: {
	rows: Row[];
	defs: FilterDef<Row>[];
	state: FilterState;
	onChange: (key: string, value: string) => void;
	onClear: () => void;
}) {
	// selects without explicit options show only the values present in the data
	const derived = useMemo(() => {
		const map: Record<string, { value: string; label: string }[]> = {};
		for (const def of defs) {
			if (def.control === 'select' && !def.options) {
				const seen = new Set<string>();
				for (const r of rows) {
					const v = def.get(r);
					if (v != null && v !== '') seen.add(String(v));
				}
				map[def.key] = [...seen].sort().map((v) => ({ value: v, label: v }));
			}
		}
		return map;
	}, [rows, defs]);

	const anyActive = defs.some((d) => state[d.key]);

	return (
		<div className="filterbar">
			{defs.map((def) => {
				if (def.control === 'toggle') {
					const on = state[def.key] === 'on';
					return (
						<button
							key={def.key}
							type="button"
							className={`fchip${on ? ' on' : ''}`}
							aria-pressed={on}
							onClick={() => onChange(def.key, on ? '' : 'on')}
						>
							{on && <Icon name="check" size={12} strokeWidth={3} />}
							{def.label}
						</button>
					);
				}
				const opts = def.options ?? derived[def.key] ?? [];
				const sel = state[def.key] ?? '';
				return (
					<div key={def.key} className={`fsel${sel ? ' on' : ''}`}>
						<select value={sel} onChange={(e) => onChange(def.key, e.target.value)} aria-label={def.label}>
							<option value="">{def.label}</option>
							{opts.map((o) => (
								<option key={o.value} value={o.value}>
									{o.label}
								</option>
							))}
						</select>
						<Icon name="chevron" size={13} />
					</div>
				);
			})}
			{anyActive && (
				<button type="button" className="fclear" onClick={onClear}>
					<Icon name="close" size={12} /> Clear
				</button>
			)}
		</div>
	);
}
