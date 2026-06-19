import { useMemo, useState } from 'react';
import { useFrappeGetCall } from 'frappe-react-sdk';
import { useNavigate } from 'react-router-dom';
import { Icon } from '@/components/Icon';
import { TextInput } from '@/components/form';
import { FilterBar, applyFilters, useFilterState, type FilterDef } from '@/components/FilterBar';
import { Card, CHead, EmptyMsg, Tag } from '@/components/ui';
import { API, parseServerError, type ShipmentListRow } from '@/lib/api';
import { fmtDate } from '@/lib/format';

const SHIPMENT_FILTERS: FilterDef<ShipmentListRow>[] = [
	{
		key: 'mode',
		label: 'Mode',
		control: 'select',
		get: (r) => r.mode,
		options: [
			{ value: 'Sea', label: 'Sea' },
			{ value: 'Air', label: 'Air' },
		],
	},
	{
		key: 'trade',
		label: 'Trade type',
		control: 'select',
		// an untagged shipment is an ordinary export — never let it vanish from the
		// "Export from India" filter (the doctype default + the create path)
		get: (r) => r.trade_type || 'Export from India',
		options: [
			{ value: 'Export from India', label: 'Export from India' },
			{ value: 'Third-country / Merchanting', label: 'Merchanting' },
		],
	},
	{ key: 'milestone', label: 'Milestone', control: 'select', get: (r) => r.current_milestone },
	{ key: 'customer', label: 'Customer', control: 'searchselect', get: (r) => r.customer_name },
];

export function Shipments() {
	const navigate = useNavigate();
	const [query, setQuery] = useState('');

	const { data, error, isLoading } = useFrappeGetCall<{ message: ShipmentListRow[] }>(
		API.shipments,
		undefined,
	);
	const all = data?.message;

	const { state, set, clear } = useFilterState();
	const searched = useMemo(() => {
		const list = all ?? [];
		const q = query.trim().toLowerCase();
		if (!q) return list;
		return list.filter(
			(r) =>
				r.name.toLowerCase().includes(q) ||
				(r.customer_name ?? '').toLowerCase().includes(q) ||
				(r.port_of_loading ?? '').toLowerCase().includes(q) ||
				(r.port_of_discharge ?? '').toLowerCase().includes(q),
		);
	}, [all, query]);
	const rows = useMemo(() => applyFilters(searched, SHIPMENT_FILTERS, state), [searched, state]);

	return (
		<main>
			<div className="eyebrow">Logistics</div>
			<h1>
				Live <em>shipments</em>
			</h1>
			<div className="sub">
				{isLoading ? 'Loading…' : <><b>{all?.length ?? 0}</b> shipments</>}
			</div>

			<div
				style={{
					display: 'flex',
					justifyContent: 'flex-end',
					alignItems: 'center',
					gap: 10,
					margin: '22px 0 12px',
				}}
			>
				<div className="field" style={{ width: 280 }}>
					<TextInput value={query} onChange={setQuery} placeholder="Search shipment or customer" />
				</div>
				<button className="btn primary" onClick={() => navigate('/shipments/new')}>
					<Icon name="plus" size={15} /> New shipment
				</button>
			</div>

			<FilterBar
				rows={searched}
				defs={SHIPMENT_FILTERS}
				state={state}
				onChange={set}
				onClear={clear}
			/>

			<Card accent>
				<CHead icon="ship" title="Shipments" count={`${rows.length} shown`} />
				{error ? (
					<div className="ferr" style={{ padding: '16px 18px' }}>
						Could not load shipments. {parseServerError(error)}
					</div>
				) : isLoading ? null : rows.length === 0 ? (
					<EmptyMsg
						title={query ? 'No matching shipments' : 'No shipments yet'}
						text={
							query
								? 'Try a different shipment number or customer name.'
								: 'Book the first consignment with "New shipment".'
						}
					/>
				) : (
					<table className="clickable">
						<thead>
							<tr>
								<th>Shipment</th>
								<th>Customer</th>
								<th>Mode</th>
								<th>Milestone</th>
								<th>ETD</th>
								<th>Status</th>
							</tr>
						</thead>
						<tbody>
							{rows.map((r) => (
								<tr key={r.name} onClick={() => navigate('/shipments/' + r.name)}>
									<td className="id">{r.name}</td>
									<td>
										<div className="c1">{r.customer_name}</div>
										{r.port_of_loading && r.port_of_discharge ? (
											<div className="c2">{`${r.port_of_loading} → ${r.port_of_discharge}`}</div>
										) : null}
									</td>
									<td>
										<span className="mode">
											<Icon name={r.mode === 'Air' ? 'plane' : 'ship'} size={15} />
											{r.mode}
										</span>
									</td>
									<td>
										<div className="mile">
											<span className="nm">{r.current_milestone}</span>
											<span className="seg">
												{Array.from({ length: r.milestones_total }, (_, i) => (
													<i key={i} className={i < r.milestones_done ? 'f' : undefined} />
												))}
											</span>
										</div>
									</td>
									<td className="dim">{fmtDate(r.etd)}</td>
									<td>
										<Tag tone={r.milestones_done >= 7 ? 'ok' : 'pend'}>
											{r.current_milestone === 'Completed' ? 'Delivered' : r.current_milestone}
										</Tag>
									</td>
								</tr>
							))}
						</tbody>
					</table>
				)}
			</Card>

			<footer>
				<b>ExportFlow</b> · DUX Digitech
			</footer>
		</main>
	);
}
