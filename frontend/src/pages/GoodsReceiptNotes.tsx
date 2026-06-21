import { useMemo, useState } from 'react';
import { useFrappeGetCall } from 'frappe-react-sdk';
import { useNavigate } from 'react-router-dom';
import { TextInput } from '@/components/form';
import { Card, CHead, EmptyMsg, Tag } from '@/components/ui';
import { API, parseServerError, type GRNListRow } from '@/lib/api';
import { fmtDate } from '@/lib/format';

const STATUS_TONE: Record<string, 'ok' | 'pend' | 'err'> = {
	Draft: 'pend',
	Received: 'ok',
	Cancelled: 'err',
};

export function GoodsReceiptNotes() {
	const navigate = useNavigate();
	const [query, setQuery] = useState('');

	const { data, error, isLoading } = useFrappeGetCall<{ message: GRNListRow[] }>(API.grns, undefined);

	const rows = useMemo(() => {
		const all = data?.message ?? [];
		const q = query.trim().toLowerCase();
		if (!q) return all;
		return all.filter(
			(r) =>
				r.name.toLowerCase().includes(q) ||
				r.purchase_order.toLowerCase().includes(q) ||
				(r.supplier_name ?? '').toLowerCase().includes(q) ||
				(r.warehouse ?? '').toLowerCase().includes(q) ||
				(r.supplier_invoice_no ?? '').toLowerCase().includes(q),
		);
	}, [data, query]);

	return (
		<main>
			<div className="eyebrow">Buying</div>
			<h1>
				Goods <em>receipts</em>
			</h1>
			<div className="sub">
				{isLoading ? 'Loading…' : <><b>{data?.message.length ?? 0}</b> receipts</>}
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
				<div className="field" style={{ width: 300 }}>
					<TextInput value={query} onChange={setQuery} placeholder="Search GRN, PO, supplier or warehouse" />
				</div>
			</div>

			<Card accent>
				<CHead icon="package" title="Goods receipt notes" count={`${rows.length} shown`} />
				{error ? (
					<div className="ferr" style={{ padding: '16px 18px' }}>
						Could not load goods receipts. {parseServerError(error)}
					</div>
				) : isLoading ? null : rows.length === 0 ? (
					<EmptyMsg
						title={query ? 'No matching receipts' : 'No goods receipts yet'}
						text={
							query
								? 'Try a different GRN, PO, supplier or warehouse.'
								: 'Receive goods from a submitted purchase order — open one and use “Create GRN”.'
						}
					/>
				) : (
					<table className="clickable">
						<thead>
							<tr>
								<th>GRN</th>
								<th>Purchase order</th>
								<th>Warehouse</th>
								<th>Invoice</th>
								<th>Date</th>
								<th>Status</th>
							</tr>
						</thead>
						<tbody>
							{rows.map((r) => (
								<tr key={r.name} onClick={() => navigate('/grns/' + r.name)}>
									<td className="id">{r.name}</td>
									<td>
										<div className="c1">{r.purchase_order}</div>
										{r.supplier_name ? <div className="c2">{r.supplier_name}</div> : null}
									</td>
									<td className="dim">{r.warehouse}</td>
									<td className="dim">{r.supplier_invoice_no || '—'}</td>
									<td className="dim">{fmtDate(r.posting_date)}</td>
									<td>
										<Tag tone={STATUS_TONE[r.status] ?? 'pend'}>{r.status}</Tag>
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
