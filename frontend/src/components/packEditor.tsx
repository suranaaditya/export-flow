import { useFrappeGetDocList } from 'frappe-react-sdk';

import { Field, SearchSelect, TextArea, TextInput } from '@/components/form';
import { Icon } from '@/components/Icon';
import type { ShipmentPack } from '@/lib/api';

/** A packing-detail row being edited (string-valued for smooth input). */
export type PackEdit = {
	_uid: string;
	item_code: string;
	batch_no: string;
	marks: string;
	num_packages: string;
	pack_type: string;
	net_per: string;
	tare_per: string;
	mfg_date: string;
	exp_date: string;
	drum_detail: string;
};

// monotonic id for stable React keys (a removed row must not reshuffle the rest)
let _uidCounter = 0;
const s = (v: number | string | null | undefined) => (v != null ? String(v) : '');

export function newPack(item_code = ''): PackEdit {
	return {
		_uid: `pk-${_uidCounter++}`,
		item_code,
		batch_no: '',
		marks: '',
		num_packages: '',
		pack_type: '',
		net_per: '',
		tare_per: '',
		mfg_date: '',
		exp_date: '',
		drum_detail: '',
	};
}

export function packToEdit(p: ShipmentPack, i: number): PackEdit {
	return {
		_uid: p.name ?? `seed-${i}`,
		item_code: p.item_code,
		batch_no: p.batch_no ?? '',
		marks: p.marks ?? '',
		num_packages: s(p.num_packages),
		pack_type: p.pack_type ?? '',
		net_per: s(p.net_per),
		tare_per: s(p.tare_per),
		mfg_date: p.mfg_date ?? '',
		exp_date: p.exp_date ?? '',
		drum_detail: p.drum_detail ?? '',
	};
}

/** Editor rows → the `packs` payload. `validItems` (when given) drops rows whose
 *  item is no longer one of the shipment's lines, so an orphan pack never reaches
 *  the backend (the item picker only ever offers the shipment's own items). */
export function editToPayload(rows: PackEdit[], validItems?: Set<string>) {
	return rows
		.filter((r) => r.item_code && (!validItems || validItems.has(r.item_code)))
		.map((r) => ({
			item_code: r.item_code,
			batch_no: r.batch_no,
			marks: r.marks,
			num_packages: Number(r.num_packages) || 0,
			pack_type: r.pack_type,
			net_per: Number(r.net_per) || 0,
			tare_per: Number(r.tare_per) || 0,
			mfg_date: r.mfg_date || null,
			exp_date: r.exp_date || null,
			drum_detail: r.drum_detail?.trim() || null,
		}));
}

/** Reusable per-batch packing editor. The item is a strict pick from
 *  `itemOptions` — the shipment's own lines — never free text. Used both while
 *  booking a shipment and when editing one afterwards. */
export function PackEditor({
	rows,
	onChange,
	itemOptions,
}: {
	rows: PackEdit[];
	onChange: (rows: PackEdit[]) => void;
	itemOptions: { value: string; label?: string }[];
}) {
	const setRow = (i: number, patch: Partial<PackEdit>) =>
		onChange(rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));

	// the managed pack-type list (Settings → Master data → Pack types); an existing
	// free-text value is appended so it stays visible/selectable on an old row
	const { data: packTypes } = useFrappeGetDocList<{ name: string }>('Export Pack Type', {
		filters: [['disabled', '=', 0]],
		fields: ['name'],
		limit: 0,
		orderBy: { field: 'pack_type_name', order: 'asc' },
	});
	const baseTypeOpts = (packTypes ?? []).map((p) => ({ value: p.name }));
	const typeOptionsFor = (v: string) =>
		v && !baseTypeOpts.some((o) => o.value === v) ? [...baseTypeOpts, { value: v }] : baseTypeOpts;

	return (
		<div className="packlist">
			{itemOptions.length === 0 && (
				<div className="sub">Add shipment lines first — packing is recorded per shipped item.</div>
			)}
			{rows.map((r, i) => (
				<div className="packrow" key={r._uid}>
					<div className="formgrid">
						<Field label="Item">
							<SearchSelect
								value={r.item_code}
								onChange={(v) => setRow(i, { item_code: v })}
								options={itemOptions}
								placeholder="Pick a shipment item…"
							/>
						</Field>
						<Field label="Batch / lot no">
							<TextInput mono value={r.batch_no} onChange={(v) => setRow(i, { batch_no: v })} />
						</Field>
						<Field label="Packages">
							<TextInput type="number" mono value={r.num_packages} onChange={(v) => setRow(i, { num_packages: v })} />
						</Field>
						<Field label="Pack type" hint="Manage the list in Settings → Master data → Pack types">
							<SearchSelect
								value={r.pack_type}
								onChange={(v) => setRow(i, { pack_type: v })}
								options={typeOptionsFor(r.pack_type)}
								placeholder="Pick a pack type…"
							/>
						</Field>
						<Field label="Pkg nos" hint="e.g. 1-10">
							<TextInput value={r.marks} onChange={(v) => setRow(i, { marks: v })} />
						</Field>
						<Field label="Net / pkg (kg)">
							<TextInput type="number" mono value={r.net_per} onChange={(v) => setRow(i, { net_per: v })} />
						</Field>
						<Field label="Tare / pkg (kg)">
							<TextInput type="number" mono value={r.tare_per} onChange={(v) => setRow(i, { tare_per: v })} />
						</Field>
						<Field label="Mfg date">
							<TextInput type="date" value={r.mfg_date} onChange={(v) => setRow(i, { mfg_date: v })} />
						</Field>
						<Field label="Exp date">
							<TextInput type="date" value={r.exp_date} onChange={(v) => setRow(i, { exp_date: v })} />
						</Field>
						<Field
							label="Per-drum weights"
							hint="Optional — one weight per line = that drum's tare (kg); net stays the uniform Net/pkg. Or enter net,tare. Blank = uniform."
						>
							<TextArea
								value={r.drum_detail}
								onChange={(v) => setRow(i, { drum_detail: v })}
								rows={3}
							/>
						</Field>
					</div>
					<button type="button" className="xrow" onClick={() => onChange(rows.filter((_, idx) => idx !== i))}>
						<Icon name="close" size={13} /> Remove batch
					</button>
				</div>
			))}
			<button
				type="button"
				className="btn"
				disabled={itemOptions.length === 0}
				onClick={() => onChange([...rows, newPack(itemOptions[0]?.value ?? '')])}
			>
				<Icon name="plus" size={14} /> Add batch / pack
			</button>
		</div>
	);
}
