import { useMemo, useState } from 'react';
import { useFrappeGetCall } from 'frappe-react-sdk';
import { useNavigate } from 'react-router-dom';
import { Icon } from '@/components/Icon';
import { Field, SearchSelect, TextInput } from '@/components/form';
import { Card, CHead, EmptyMsg, Modal, Tag } from '@/components/ui';
import {
	API,
	parseServerError,
	type GRNListRow,
	type ReceivablePO,
} from '@/lib/api';
import { fmtDate } from '@/lib/format';

const STATUS_TONE: Record<string, 'ok' | 'pend' | 'err'> = {
	Draft: 'pend',
	Received: 'ok',
	Cancelled: 'err',
};

/** Pick a supplier, then one of their open POs, to start a receipt straight from
 *  the Goods receipts screen (the PO detail's "Create GRN" is the other entry). */
function NewReceiptModal({ onClose }: { onClose: () => void }) {
	const navigate = useNavigate();
	const { data, isLoading, error } = useFrappeGetCall<{ message: ReceivablePO[] }>(
		API.receivablePos,
		undefined,
	);
	const [supplier, setSupplier] = useState('');
	const [po, setPo] = useState('');

	const pos = data?.message ?? [];
	const supplierOptions = useMemo(() => {
		const seen = new Map<string, string>();
		for (const p of pos) if (!seen.has(p.supplier)) seen.set(p.supplier, p.supplier_name || p.supplier);
		return [...seen].map(([value, label]) => ({ value, label }));
	}, [pos]);
	const poOptions = useMemo(
		() =>
			pos
				.filter((p) => p.supplier === supplier)
				.map((p) => ({
					value: p.name,
					label: p.name,
					sub: `${p.remaining_lines} line${p.remaining_lines === 1 ? '' : 's'} to receive · ${fmtDate(p.transaction_date)}`,
				})),
		[pos, supplier],
	);

	return (
		<Modal title="New goods receipt" icon="package" onClose={onClose}>
			<div style={{ padding: '14px 18px', display: 'grid', gap: 14 }}>
				{isLoading ? (
					<div className="sub">Loading open purchase orders…</div>
				) : error ? (
					<div className="ferr">{parseServerError(error)}</div>
				) : pos.length === 0 ? (
					<EmptyMsg
						title="No open purchase orders"
						text="Every submitted purchase order is already fully received (merchanting POs never receive goods)."
					/>
				) : (
					<>
						<Field label="Supplier">
							<SearchSelect
								value={supplier}
								onChange={(v) => {
									setSupplier(v);
									setPo('');
								}}
								options={supplierOptions}
								placeholder="Pick a supplier…"
							/>
						</Field>
						<Field label="Purchase order" hint="only POs with goods still to receive">
							<SearchSelect
								value={po}
								onChange={setPo}
								options={poOptions}
								placeholder={supplier ? 'Pick a purchase order…' : 'Pick a supplier first'}
								disabled={!supplier}
							/>
						</Field>
						<div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
							<button className="btn" onClick={onClose}>
								Cancel
							</button>
							<button
								className="btn primary"
								disabled={!po}
								onClick={() => navigate(`/grns/new?po=${po}`)}
							>
								<Icon name="package" size={15} /> Continue to receipt
							</button>
						</div>
					</>
				)}
			</div>
		</Modal>
	);
}

export function GoodsReceiptNotes() {
	const navigate = useNavigate();
	const [query, setQuery] = useState('');
	const [picking, setPicking] = useState(false);

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
				<button className="btn primary" onClick={() => setPicking(true)}>
					<Icon name="plus" size={15} /> New receipt
				</button>
			</div>

			{picking && <NewReceiptModal onClose={() => setPicking(false)} />}

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
								: 'Start a receipt with “New receipt”, or open a purchase order and use “Create GRN”.'
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
