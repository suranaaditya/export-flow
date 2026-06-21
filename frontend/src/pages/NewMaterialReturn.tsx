import { useEffect, useRef, useState } from 'react';
import { useFrappeGetCall, useFrappePostCall } from 'frappe-react-sdk';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Icon } from '@/components/Icon';
import { TextArea, TextInput } from '@/components/form';
import { Card, CHead } from '@/components/ui';
import { API, parseServerError, type ReturnContext } from '@/lib/api';

interface RLine {
	item_code: string;
	item_name: string;
	po_detail: string | null;
	grn_detail: string;
	received_qty: number;
	already_returned: number;
	returnable: number;
	returned_qty: string;
	uom: string | null;
}

export function NewMaterialReturn() {
	const [params] = useSearchParams();
	const grn = params.get('grn') || '';
	const navigate = useNavigate();

	const { data, error: ctxErr } = useFrappeGetCall<{ message: ReturnContext }>(
		API.returnContext,
		{ goods_receipt_note: grn },
		grn ? undefined : null,
	);
	const { call: createReturn, loading } = useFrappePostCall<{ message: { name: string } }>(
		API.createReturn,
	);

	const [lines, setLines] = useState<RLine[]>([]);
	const [reason, setReason] = useState('');
	const [err, setErr] = useState<string | null>(null);
	const seeded = useRef(false);

	useEffect(() => {
		if (seeded.current || !data) return;
		setLines(data.message.lines.map((l) => ({ ...l, returned_qty: String(l.returned_qty) })));
		seeded.current = true;
	}, [data]);

	function setLine(i: number, v: string) {
		setLines((rows) => rows.map((r, idx) => (idx === i ? { ...r, returned_qty: v } : r)));
	}

	async function onSave() {
		setErr(null);
		const items = lines
			.filter((l) => Number(l.returned_qty) > 0)
			.map((l) => ({
				item_code: l.item_code,
				item_name: l.item_name,
				po_detail: l.po_detail,
				grn_detail: l.grn_detail,
				received_qty: l.received_qty,
				returned_qty: Number(l.returned_qty) || 0,
				uom: l.uom,
			}));
		if (items.length === 0) return setErr('Enter a quantity to return for at least one line.');
		try {
			const r = await createReturn({
				payload: { goods_receipt_note: grn, reason: reason.trim() || null, items },
			});
			navigate('/returns/' + r.message.name);
		} catch (e) {
			setErr(parseServerError(e));
		}
	}

	if (!grn) {
		return (
			<main className="tight">
				<div className="eyebrow">Buying · Material return</div>
				<div className="sub" style={{ marginTop: 14 }}>
					Open a received goods receipt and choose “Return material”.
				</div>
			</main>
		);
	}

	const ctx = data?.message;

	return (
		<main className="tight">
			<div className="eyebrow">Buying · Material return</div>
			<div className="crumb" style={{ marginTop: 6 }}>
				<Link to={'/grns/' + grn}>{grn}</Link> / <span className="data">Return</span>
			</div>

			<div className="titlebar">
				<h1>Return material</h1>
				<span className="who">· {ctx?.supplier_name}</span>
				<span className="spacer" />
				<button className="btn" onClick={() => navigate('/grns/' + grn)}>
					Cancel
				</button>
				<button className="btn primary" disabled={loading} onClick={() => void onSave()}>
					<Icon name="check" size={15} /> {loading ? 'Saving…' : 'Create return'}
				</button>
			</div>

			{ctxErr && <div className="ferr" style={{ marginBottom: 10 }}>{parseServerError(ctxErr)}</div>}
			{err && <div className="ferr" style={{ marginBottom: 10 }}>{err}</div>}

			<div className="stack">
				<Card accent>
					<CHead icon="cube" title="Returning to supplier" count={ctx ? ctx.warehouse : undefined} />
					<table>
						<thead>
							<tr>
								<th>Item</th>
								<th>Received</th>
								<th>Already returned</th>
								<th>Returning now</th>
							</tr>
						</thead>
						<tbody>
							{lines.map((l, i) => (
								<tr key={l.grn_detail}>
									<td>
										<div className="c1">{l.item_name}</div>
										<div className="c2">{l.item_code}</div>
									</td>
									<td className="num">
										{l.received_qty} {l.uom ? <span className="dim">{l.uom}</span> : null}
									</td>
									<td className="num">{l.already_returned || <span className="dim">—</span>}</td>
									<td className="num" style={{ maxWidth: 120 }}>
										<TextInput
											type="number"
											mono
											value={l.returned_qty}
											onChange={(v) => setLine(i, v)}
										/>
									</td>
								</tr>
							))}
						</tbody>
					</table>
				</Card>

				<Card>
					<CHead icon="file-text" title="Reason" />
					<div style={{ padding: '6px 18px 16px' }}>
						<div className="sub" style={{ marginBottom: 8 }}>
							Why it’s going back — off-spec, damaged, short, wrong item…
						</div>
						<TextArea value={reason} onChange={setReason} rows={2} />
					</div>
				</Card>
			</div>

			<footer>
				<b>ExportFlow</b> · DUX Digitech
			</footer>
		</main>
	);
}
