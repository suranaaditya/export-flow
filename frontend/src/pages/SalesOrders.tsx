import { useMemo, useState } from 'react';
import { useFrappeGetDocList } from 'frappe-react-sdk';
import { useNavigate } from 'react-router-dom';
import { Icon } from '@/components/Icon';
import { TextInput } from '@/components/form';
import { Card, CHead, EmptyMsg, Tag } from '@/components/ui';
import { soTone } from '@/lib/api';
import { fmtDate, fmtMoney } from '@/lib/format';

/** List-view slice of Sales Order (custom field: incoterm). */
interface SOListRow {
	name: string;
	customer_name: string;
	currency: string;
	grand_total: number;
	transaction_date: string;
	delivery_date: string | null;
	status: string;
	incoterm: string | null;
}

export function SalesOrders() {
	const navigate = useNavigate();
	const [query, setQuery] = useState('');

	const { data, error, isLoading } = useFrappeGetDocList<SOListRow>('Sales Order', {
		fields: [
			'name',
			'customer_name',
			'currency',
			'grand_total',
			'transaction_date',
			'delivery_date',
			'status',
			'incoterm',
		],
		// drafts entered in ExportFlow show here too; cancelled orders do not
		filters: [['docstatus', '<', 2]],
		orderBy: { field: 'transaction_date', order: 'desc' },
		limit: 50,
	});

	const rows = useMemo(() => {
		const all = data ?? [];
		const q = query.trim().toLowerCase();
		if (!q) return all;
		return all.filter(
			(r) =>
				r.name.toLowerCase().includes(q) ||
				(r.customer_name ?? '').toLowerCase().includes(q),
		);
	}, [data, query]);

	return (
		<main>
			<div className="eyebrow">Selling</div>
			<h1>
				Sales <em>orders</em>
			</h1>
			<div className="sub">
				{isLoading ? 'Loading…' : <><b>{data?.length ?? 0}</b> orders</>}
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
					<TextInput value={query} onChange={setQuery} placeholder="Search SO or customer" />
				</div>
				<button className="btn primary" onClick={() => navigate('/sales-orders/new')}>
					<Icon name="plus" size={15} /> New sales order
				</button>
			</div>

			<Card accent>
				<CHead icon="file-text" title="Sales orders" count={`${rows.length} shown`} />
				{error ? (
					<div className="ferr" style={{ padding: '16px 18px' }}>
						Could not load sales orders. {error.message}
					</div>
				) : isLoading ? null : rows.length === 0 ? (
					<EmptyMsg
						title={query ? 'No matching orders' : 'No sales orders yet'}
						text={
							query
								? 'Try a different SO number or customer name.'
								: 'Book the first export deal with "New sales order".'
						}
					/>
				) : (
					<table className="clickable">
						<thead>
							<tr>
								<th>SO</th>
								<th>Customer</th>
								<th>Date</th>
								<th>Delivery</th>
								<th>Value</th>
								<th>Status</th>
							</tr>
						</thead>
						<tbody>
							{rows.map((r) => (
								<tr key={r.name} onClick={() => navigate('/sales-orders/' + r.name)}>
									<td className="id">{r.name}</td>
									<td>
										<div className="c1">{r.customer_name}</div>
										{r.incoterm ? <div className="c2">{r.incoterm}</div> : null}
									</td>
									<td className="dim">{fmtDate(r.transaction_date)}</td>
									<td className="dim">{fmtDate(r.delivery_date)}</td>
									<td className="num">{fmtMoney(r.grand_total, r.currency)}</td>
									<td>
										<Tag tone={soTone(r.status)}>{r.status}</Tag>
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
