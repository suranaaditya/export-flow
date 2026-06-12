import { useMemo, useState } from 'react';
import { useFrappeGetCall } from 'frappe-react-sdk';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { DocumentModal } from '@/components/DocumentChecklist';
import { Icon, type IconName } from '@/components/Icon';
import { SelectInput, TextInput } from '@/components/form';
import { Card, CHead, EmptyMsg, Tag } from '@/components/ui';
import {
	API,
	docIsBlockingNow,
	docIsDone,
	docTagTone,
	parseServerError,
	type DocCategory,
	type DocInstanceRow,
	type ShipmentDocumentsData,
} from '@/lib/api';
import { fmtDate } from '@/lib/format';

const CATEGORIES: DocCategory[] = [
	'Commercial',
	'Regulatory',
	'Quality',
	'Logistics',
	'Banking',
	'Company',
];

type StateFilter = 'all' | 'open' | 'blocking' | 'done';

function Kpi({
	icon,
	label,
	value,
	detail,
	tone,
}: {
	icon: IconName;
	label: string;
	value: number;
	detail: string;
	tone?: 'warn' | 'bad';
}) {
	return (
		<div className="card kpi">
			<div className="lb">
				<Icon name={icon} size={14} /> {label}
			</div>
			<div className="v">{value}</div>
			<div className="d">{tone ? <span className={tone}>{detail}</span> : detail}</div>
		</div>
	);
}

export function Documents() {
	const navigate = useNavigate();
	const [params, setParams] = useSearchParams();
	const [category, setCategory] = useState('');
	const [state, setState] = useState<StateFilter>('all');
	const query = params.get('shipment') ?? params.get('q') ?? '';
	const [open, setOpen] = useState<DocInstanceRow | null>(null);

	// same payload shape as the checklist card; document_types ride along for
	// the edit modal's generate logic
	const { data, error, isLoading, mutate } = useFrappeGetCall<{
		message: ShipmentDocumentsData;
	}>(API.documentsWorkspace, undefined);

	const docs = data?.message.documents ?? [];

	const filtered = useMemo(() => {
		const q = query.trim().toLowerCase();
		return docs.filter((d) => {
			if (category && d.category !== category) return false;
			if (state === 'open' && docIsDone(d)) return false;
			if (state === 'done' && !docIsDone(d)) return false;
			if (state === 'blocking' && !docIsBlockingNow(d)) return false;
			if (!q) return true;
			return [d.document_type, d.shipment, d.customer, d.document_number, d.purchase_order]
				.filter(Boolean)
				.some((v) => String(v).toLowerCase().includes(q));
		});
	}, [docs, category, state, query]);

	const openCount = docs.filter((d) => !docIsDone(d)).length;
	const blockingCount = docs.filter(docIsBlockingNow).length;
	const draftedCount = docs.filter((d) => d.status === 'Drafted').length;
	const doneCount = docs.filter(docIsDone).length;

	const setQuery = (v: string) => {
		const next = new URLSearchParams(params);
		if (v) next.set('q', v);
		else next.delete('q');
		next.delete('shipment');
		setParams(next, { replace: true });
	};

	return (
		<main>
			<div className="eyebrow">Documentation</div>
			<h1>
				Documents <em>workspace</em>
			</h1>
			<div className="sub">
				Every generated and tracked document across shipments — checklists build themselves from
				mode, incoterm, LC terms and purchase orders.
			</div>

			<div className="kpis">
				<Kpi icon="file-text" label="Open" value={openCount} detail="not yet sent or received" />
				<Kpi
					icon="warning"
					label="Blocking"
					value={blockingCount}
					detail={blockingCount ? 'holding up a milestone' : 'nothing blocked'}
					tone={blockingCount ? 'bad' : undefined}
				/>
				<Kpi icon="file" label="Drafted" value={draftedCount} detail="generated, awaiting dispatch" />
				<Kpi icon="circle-check" label="Done" value={doneCount} detail="sent, received or verified" />
			</div>

			<Card>
				<CHead icon="filter" title="All documents" count={`${filtered.length} of ${docs.length}`} />
				<div style={{ display: 'flex', gap: 10, padding: '12px 18px 4px', flexWrap: 'wrap' }}>
					<div className="field" style={{ width: 260 }}>
						<TextInput
							value={query}
							onChange={setQuery}
							placeholder="Search type, shipment, number…"
						/>
					</div>
					<div className="field" style={{ width: 170 }}>
						<SelectInput
							value={category}
							onChange={setCategory}
							options={CATEGORIES.map((c) => ({ value: c }))}
							allowEmpty
						/>
					</div>
					<div className="field" style={{ width: 150 }}>
						<SelectInput
							value={state}
							onChange={(v) => setState(v as StateFilter)}
							options={[
								{ value: 'all', label: 'All states' },
								{ value: 'open', label: 'Open' },
								{ value: 'blocking', label: 'Blocking' },
								{ value: 'done', label: 'Done' },
							]}
						/>
					</div>
				</div>
				{isLoading ? (
					<div className="sub" style={{ padding: '14px 18px' }}>
						Loading…
					</div>
				) : error ? (
					<div className="ferr" style={{ padding: '14px 18px' }}>{parseServerError(error)}</div>
				) : filtered.length === 0 ? (
					<EmptyMsg
						title={docs.length ? 'No matches' : 'No documents yet'}
						text={
							docs.length
								? 'Try clearing the filters.'
								: 'Book a shipment and its checklist will appear here.'
						}
					/>
				) : (
					<table className="clickable">
						<thead>
							<tr>
								<th>Document</th>
								<th>Shipment</th>
								<th>Number</th>
								<th>Due</th>
								<th>Responsible</th>
								<th>Status</th>
								<th></th>
							</tr>
						</thead>
						<tbody>
							{filtered.slice(0, 100).map((d) => (
								<tr
									key={d.name}
									tabIndex={0}
									onClick={() => setOpen(d)}
									onKeyDown={(e) => {
										if (e.key === 'Enter') setOpen(d);
									}}
								>
									<td>
										<div className="c1">{d.document_type}</div>
										<div className="c2">
											{d.category}
											{d.customer ? ` · ${d.customer}` : ''}
										</div>
									</td>
									<td>
										{d.shipment ? (
											<a
												className="id id-sm"
												onClick={(e) => {
													e.stopPropagation();
													e.preventDefault();
													navigate('/shipments/' + d.shipment);
												}}
												href="#"
											>
												{d.shipment}
											</a>
										) : (
											<span className="dim">—</span>
										)}
									</td>
									<td className="dim">{d.document_number ?? '—'}</td>
									<td className="dim">{d.due_date ? fmtDate(d.due_date) : '—'}</td>
									<td className="c2">{d.responsible_party ?? '—'}</td>
									<td>
										<Tag tone={docTagTone(d)}>
											{docIsBlockingNow(d) ? `Blocking · ${d.status}` : d.status}
										</Tag>
									</td>
									<td>
										{d.file && (
											<a
												className="act"
												href={d.file}
												target="_blank"
												rel="noreferrer"
												onClick={(e) => e.stopPropagation()}
											>
												PDF
											</a>
										)}
									</td>
								</tr>
							))}
						</tbody>
					</table>
				)}
				{filtered.length > 100 && (
					<div className="dim" style={{ padding: '8px 18px 12px' }}>
						{filtered.length - 100} more — refine the search
					</div>
				)}
			</Card>

			{open && (
				<DocumentModal
					doc={open}
					types={data?.message.document_types ?? []}
					onClose={() => setOpen(null)}
					onSaved={() => {
						setOpen(null);
						mutate();
					}}
					onChanged={() => void mutate()}
				/>
			)}

			<footer>
				<b>ExportFlow</b> · DUX Digitech
			</footer>
		</main>
	);
}
