import { useMemo, useState } from 'react';
import { useFrappeGetCall } from 'frappe-react-sdk';
import { useNavigate } from 'react-router-dom';
import { Icon } from '@/components/Icon';
import { TextInput } from '@/components/form';
import { Card, CHead, EmptyMsg, Tag } from '@/components/ui';
import { API, parseServerError, poTone, urgencyTone, type POListRow } from '@/lib/api';
import { daysUntil, fmtDate, fmtMoney } from '@/lib/format';

/** The 90-day merchant-export clock cell: chip once the supplier invoice
 *  starts the clock, mono hints otherwise. */
function GstClock({ row }: { row: POListRow }) {
	if (!row.merchant_export_scheme) return <span className="dim">—</span>;
	if (!row.gst_export_deadline) return <span className="dim">awaiting invoice</span>;
	const tone = urgencyTone(daysUntil(row.gst_export_deadline)) ?? 'ok';
	return <Tag tone={tone}>Export by {fmtDate(row.gst_export_deadline)}</Tag>;
}

export function Purchases() {
	const navigate = useNavigate();
	const [query, setQuery] = useState('');

	const { data, error, isLoading } = useFrappeGetCall<{ message: POListRow[] }>(
		API.poList,
		undefined,
	);

	const rows = useMemo(() => {
		const all = data?.message ?? [];
		const q = query.trim().toLowerCase();
		if (!q) return all;
		return all.filter(
			(r) =>
				r.name.toLowerCase().includes(q) ||
				(r.supplier_name ?? '').toLowerCase().includes(q) ||
				r.sales_orders.some((so) => so.toLowerCase().includes(q)),
		);
	}, [data, query]);

	return (
		<main>
			<div className="eyebrow">Buying</div>
			<h1>
				Purchase <em>orders</em>
			</h1>
			<div className="sub">
				{isLoading ? 'Loading…' : <><b>{data?.message.length ?? 0}</b> orders</>}
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
					<TextInput value={query} onChange={setQuery} placeholder="Search PO, supplier or SO" />
				</div>
				<button className="btn primary" onClick={() => navigate('/purchases/new')}>
					<Icon name="plus" size={15} /> New purchase order
				</button>
			</div>

			<Card accent>
				<CHead icon="cube" title="Purchase orders" count={`${rows.length} shown`} />
				{error ? (
					<div className="ferr" style={{ padding: '16px 18px' }}>
						Could not load purchase orders. {parseServerError(error)}
					</div>
				) : isLoading ? null : rows.length === 0 ? (
					<EmptyMsg
						title={query ? 'No matching orders' : 'No purchase orders yet'}
						text={
							query
								? 'Try a different PO number, supplier or SO.'
								: 'Raise POs from a sales order — open one and use its procurement panel.'
						}
					/>
				) : (
					<table className="clickable">
						<thead>
							<tr>
								<th>PO</th>
								<th>Supplier</th>
								<th>Date</th>
								<th>Value</th>
								<th>GST clock</th>
								<th>Status</th>
							</tr>
						</thead>
						<tbody>
							{rows.map((r) => (
								<tr key={r.name} onClick={() => navigate('/purchases/' + r.name)}>
									<td className="id">{r.name}</td>
									<td>
										<div className="c1">{r.supplier_name}</div>
										{r.sales_orders[0] ? <div className="c2">for {r.sales_orders[0]}</div> : null}
									</td>
									<td className="dim">{fmtDate(r.transaction_date)}</td>
									<td className="num">{fmtMoney(r.grand_total, r.currency)}</td>
									<td>
										<GstClock row={r} />
									</td>
									<td>
										<Tag tone={poTone(r.status, r.docstatus)}>
											{r.docstatus === 0 ? 'Draft' : r.status}
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
