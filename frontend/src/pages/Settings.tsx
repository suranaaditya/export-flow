import { useMemo, useState } from 'react';
import { useFrappeGetCall, useFrappeGetDocList } from 'frappe-react-sdk';
import { MasterModal } from '@/components/MasterModal';
import { TextInput } from '@/components/form';
import { Card, CHead, EmptyMsg } from '@/components/ui';
import { API, type NewSOContext } from '@/lib/api';
import { GRADE_OPTIONS, MASTERS, PORT_MODES, type MasterDef, type OptionSource } from '@/lib/masters';

type Row = Record<string, unknown> & { name: string };

function MasterPanel({
	def,
	options,
	canEdit,
}: {
	def: MasterDef;
	options: Record<OptionSource, string[]>;
	canEdit: boolean;
}) {
	const [query, setQuery] = useState('');
	const [modal, setModal] = useState<'new' | Row | null>(null);

	const { data, error, mutate } = useFrappeGetDocList<Row>(def.doctype, {
		fields: def.listFields,
		orderBy: { field: 'modified', order: 'desc' },
		limit: 100,
	});

	const rows = useMemo(() => {
		const all = data ?? [];
		const q = query.trim().toLowerCase();
		if (!q) return all;
		return all.filter((r) =>
			def.columns.some((c) => String(r[c.key] ?? '').toLowerCase().includes(q)) ||
			r.name.toLowerCase().includes(q),
		);
	}, [data, query, def.columns]);

	return (
		<Card>
			<CHead
				icon={def.icon}
				title={def.title}
				count={data ? data.length : undefined}
				action={
					canEdit ? (
						<a
							onClick={(e) => {
								e.preventDefault();
								setModal('new');
							}}
							href="#"
						>
							New
						</a>
					) : undefined
				}
			/>
			{(data?.length ?? 0) > 6 && (
				<div style={{ padding: '10px 18px 0' }}>
					<div className="field" style={{ width: 260 }}>
						<TextInput value={query} onChange={setQuery} placeholder={`Search ${def.title.toLowerCase()}`} />
					</div>
				</div>
			)}
			{error ? (
				<div className="ferr" style={{ padding: '14px 18px' }}>
					Could not load {def.title.toLowerCase()} — check permissions.
				</div>
			) : rows.length === 0 ? (
				<EmptyMsg title={query ? 'No matches' : `No ${def.title.toLowerCase()} yet`} />
			) : (
				<table className={canEdit ? 'clickable' : undefined}>
					<thead>
						<tr>
							{def.columns.map((c) => (
								<th key={c.key}>{c.label}</th>
							))}
						</tr>
					</thead>
					<tbody>
						{rows.slice(0, 12).map((r) => (
							<tr key={r.name} onClick={canEdit ? () => setModal(r) : undefined}>
								{def.columns.map((c) => {
									const v = r[c.key];
									const isCheck = def.fields.find((f) => f.key === c.key)?.type === 'check';
									return (
										<td key={c.key} className={c.dim ? 'dim' : 'c1'}>
											{isCheck ? (v ? 'Yes' : '—') : v != null && v !== '' ? String(v) : '—'}
										</td>
									);
								})}
							</tr>
						))}
					</tbody>
				</table>
			)}
			{rows.length > 12 && (
				<div className="dim" style={{ padding: '8px 18px 12px' }}>
					{rows.length - 12} more — refine the search
				</div>
			)}
			{modal !== null && (
				<MasterModal
					def={def}
					options={options}
					record={modal === 'new' ? null : modal}
					onClose={() => setModal(null)}
					onSaved={() => {
						setModal(null);
						mutate();
					}}
				/>
			)}
		</Card>
	);
}

export function Settings() {
	// the SO-context endpoint doubles as the masters option source; viewers
	// without create rights still browse the lists below read-only
	const ctxResult = useFrappeGetCall<{ message: NewSOContext }>(API.newSoContext, undefined);
	const ctx = ctxResult.data?.message;
	const canEdit = !ctxResult.error;

	const options: Record<OptionSource, string[]> = {
		currencies: ctx?.currencies ?? [],
		incoterms: ctx?.incoterms ?? [],
		uoms: ctx?.uoms ?? [],
		countries: ctx?.countries ?? [],
		grades: GRADE_OPTIONS,
		portModes: PORT_MODES,
	};

	return (
		<main>
			<div className="eyebrow">Workspace</div>
			<h1>
				Masters & <em>settings</em>
			</h1>
			<div className="sub">
				Customers, suppliers, items, units and ports — everything the deal and shipment forms pick
				from.
			</div>

			<div className="stack" style={{ marginTop: 22 }}>
				{MASTERS.map((def) => (
					<MasterPanel key={def.doctype} def={def} options={options} canEdit={canEdit} />
				))}
			</div>

			<footer>
				<b>ExportFlow</b> · DUX Digitech
			</footer>
		</main>
	);
}
