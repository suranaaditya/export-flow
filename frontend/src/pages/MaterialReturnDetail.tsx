import { useState } from 'react';
import { useFrappeGetCall, useFrappePostCall } from 'frappe-react-sdk';
import { Link, useParams } from 'react-router-dom';
import { Icon } from '@/components/Icon';
import { Card, CHead, Tag } from '@/components/ui';
import { API, parseServerError, type ReturnDetailData } from '@/lib/api';
import { fmtDateLong } from '@/lib/format';

const STATUS_TONE: Record<string, 'ok' | 'pend' | 'err'> = {
	Draft: 'pend',
	Returned: 'ok',
	Cancelled: 'err',
};

export function MaterialReturnDetail() {
	const { id = '' } = useParams<{ id: string }>();
	const { data, error, isLoading, mutate } = useFrappeGetCall<{ message: ReturnDetailData }>(
		API.returnDetail,
		{ name: id },
	);
	const { call: confirmReturn, loading: confirming } = useFrappePostCall(API.submitReturn);
	const { call: cancelReturn, loading: cancelling } = useFrappePostCall(API.cancelReturn);
	const [actionErr, setActionErr] = useState<string | null>(null);

	async function onConfirm() {
		setActionErr(null);
		try {
			await confirmReturn({ name: id });
			await mutate();
		} catch (e) {
			setActionErr(parseServerError(e));
		}
	}

	async function onCancel() {
		setActionErr(null);
		try {
			await cancelReturn({ name: id });
			await mutate();
		} catch (e) {
			setActionErr(parseServerError(e));
		}
	}

	if (isLoading) {
		return (
			<main className="tight">
				<div className="eyebrow">Buying · Material return</div>
				<div className="sub" style={{ marginTop: 14 }}>Loading…</div>
			</main>
		);
	}
	const d = data?.message;
	if (error || !d) {
		return (
			<main className="tight">
				<div className="crumb">
					<span className="data">{id}</span>
				</div>
				<div style={{ marginTop: 22 }}>
					<Card>
						<div className="ferr" style={{ padding: '18px 20px' }}>
							This material return could not be loaded. {error ? parseServerError(error) : ''}
						</div>
					</Card>
				</div>
			</main>
		);
	}

	const { mr, items, can } = d;

	return (
		<main className="tight">
			<div className="eyebrow">Buying · Material return</div>
			<div className="crumb" style={{ marginTop: 6 }}>
				<Link to={'/grns/' + mr.goods_receipt_note}>{mr.goods_receipt_note}</Link> /{' '}
				<span className="data">{mr.name}</span>
			</div>

			<div className="titlebar">
				<h1>{mr.name}</h1>
				<span className="who">· {mr.supplier_name}</span>
				<span style={{ marginTop: 9, display: 'inline-flex', gap: 6 }}>
					<Tag tone={STATUS_TONE[mr.status] ?? 'pend'}>{mr.status}</Tag>
				</span>
				<span className="spacer" />
				{can.cancel && (
					<button className="btn" disabled={cancelling} onClick={() => void onCancel()}>
						<Icon name="close" size={15} /> {cancelling ? 'Cancelling…' : 'Cancel return'}
					</button>
				)}
				{can.confirm && (
					<button className="btn primary" disabled={confirming} onClick={() => void onConfirm()}>
						<Icon name="check" size={15} /> {confirming ? 'Returning…' : 'Confirm return'}
					</button>
				)}
			</div>

			{actionErr && <div className="ferr" style={{ marginBottom: 10 }}>{actionErr}</div>}

			<div className="metaline">
				<span className="kv">
					<b>Goods receipt</b>
					<Link className="data" to={'/grns/' + mr.goods_receipt_note}>
						{mr.goods_receipt_note}
					</Link>
				</span>
				<span className="kv">
					<b>Purchase order</b>
					<Link className="data" to={'/purchases/' + mr.purchase_order}>
						{mr.purchase_order}
					</Link>
				</span>
				<span className="kv">
					<b>From warehouse</b>
					<span className="data">{mr.warehouse}</span>
				</span>
				<span className="kv">
					<b>Date</b>
					<span className="data">{fmtDateLong(mr.posting_date)}</span>
				</span>
			</div>

			<div className="stack">
				<Card accent>
					<CHead icon="cube" title="Returned items" count={`${items.length} lines`} />
					<table>
						<thead>
							<tr>
								<th>Item</th>
								<th>Received</th>
								<th>Returned</th>
							</tr>
						</thead>
						<tbody>
							{items.map((it) => (
								<tr key={it.name}>
									<td>
										<div className="c1">{it.item_name}</div>
										<div className="c2">{it.item_code}</div>
									</td>
									<td className="num">{it.received_qty || <span className="dim">—</span>}</td>
									<td className="num">
										{it.returned_qty} {it.uom ? <span className="dim">{it.uom}</span> : null}
									</td>
								</tr>
							))}
						</tbody>
					</table>
				</Card>

				{mr.reason && (
					<Card>
						<CHead icon="file-text" title="Reason" />
						<div className="c2" style={{ padding: '12px 18px', whiteSpace: 'pre-wrap' }}>
							{mr.reason}
						</div>
					</Card>
				)}
			</div>

			<footer>
				<b>ExportFlow</b> · DUX Digitech
			</footer>
		</main>
	);
}
