import { useEffect, useMemo, useRef, useState } from 'react';
import { useFrappeGetCall, useFrappePostCall } from 'frappe-react-sdk';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { Icon } from '@/components/Icon';
import { Field, SearchSelect, TextArea, TextInput } from '@/components/form';
import { editToPayload, PackEditor, packToEdit, type PackEdit } from '@/components/packEditor';
import { Card, CHead } from '@/components/ui';
import {
	API,
	parseServerError,
	type GRNContext,
	type GRNDetailData,
} from '@/lib/api';

interface LineEdit {
	po_detail: string;
	item_code: string;
	item_name: string;
	ordered_qty: number;
	already_received: number;
	received_qty: string;
	uom: string | null;
	stock_uom: string | null;
	conversion_factor: number;
}

export function NewGoodsReceiptNote() {
	const { id } = useParams<{ id: string }>();
	const isEdit = !!id;
	const [params] = useSearchParams();
	const navigate = useNavigate();

	const { data: detail } = useFrappeGetCall<{ message: GRNDetailData }>(
		API.grnDetail,
		{ name: id },
		isEdit ? undefined : null,
	);
	const po = isEdit ? detail?.message.grn.purchase_order : params.get('po') || '';
	const { data: ctx, error: ctxErr } = useFrappeGetCall<{ message: GRNContext }>(
		API.grnContext,
		{ purchase_order: po },
		po ? undefined : null,
	);

	const { call: createGrn, loading: creating } = useFrappePostCall<{ message: { name: string } }>(
		API.createGrn,
	);
	const { call: updateGrn, loading: updating } = useFrappePostCall<{ message: { name: string } }>(
		API.updateGrn,
	);

	const [warehouse, setWarehouse] = useState('');
	const [invoiceNo, setInvoiceNo] = useState('');
	const [invoiceDate, setInvoiceDate] = useState('');
	const [remarks, setRemarks] = useState('');
	const [lines, setLines] = useState<LineEdit[]>([]);
	const [packs, setPacks] = useState<PackEdit[]>([]);
	const [err, setErr] = useState<string | null>(null);

	// seed once, when the source data arrives
	const seeded = useRef(false);
	useEffect(() => {
		if (seeded.current) return;
		if (isEdit) {
			const d = detail?.message;
			if (!d) return;
			setWarehouse(d.grn.warehouse || '');
			setInvoiceNo(d.grn.supplier_invoice_no ?? '');
			setInvoiceDate(d.grn.supplier_invoice_date ?? '');
			setRemarks(d.grn.remarks ?? '');
			setLines(
				d.items.map((it) => ({
					po_detail: it.po_detail ?? '',
					item_code: it.item_code,
					item_name: it.item_name ?? it.item_code,
					ordered_qty: it.ordered_qty,
					already_received: 0,
					received_qty: String(it.received_qty),
					uom: it.uom,
					stock_uom: null,
					conversion_factor: 1,
				})),
			);
			setPacks(d.packs.map(packToEdit));
			seeded.current = true;
		} else {
			const c = ctx?.message;
			if (!c) return;
			setWarehouse(c.warehouses[0]?.name ?? '');
			setLines(
				c.lines.map((l) => ({
					po_detail: l.po_detail,
					item_code: l.item_code,
					item_name: l.item_name,
					ordered_qty: l.ordered_qty,
					already_received: l.already_received,
					received_qty: String(l.received_qty),
					uom: l.uom,
					stock_uom: l.stock_uom,
					conversion_factor: l.conversion_factor,
				})),
			);
			seeded.current = true;
		}
	}, [isEdit, detail, ctx]);

	const warehouseOptions = useMemo(
		() =>
			(ctx?.message.warehouses ?? []).map((w) => ({
				value: w.name,
				label: w.name,
				sub: w.warehouse_type === 'Port' ? 'port warehouse' : undefined,
			})),
		[ctx],
	);
	const itemOptions = useMemo(
		() => lines.map((l) => ({ value: l.item_code, label: l.item_name })),
		[lines],
	);

	function setLine(i: number, patch: Partial<LineEdit>) {
		setLines((rows) => rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
	}

	async function onSave() {
		setErr(null);
		const itemRows = lines
			.filter((l) => Number(l.received_qty) > 0)
			.map((l) => ({
				item_code: l.item_code,
				item_name: l.item_name,
				po_detail: l.po_detail || null,
				ordered_qty: l.ordered_qty,
				received_qty: Number(l.received_qty) || 0,
				uom: l.uom,
				stock_uom: l.stock_uom,
				conversion_factor: l.conversion_factor || 1,
			}));
		if (!warehouse) return setErr('Pick a receiving warehouse.');
		if (itemRows.length === 0) return setErr('Enter a received quantity for at least one line.');
		const payload = {
			purchase_order: po,
			warehouse,
			supplier_invoice_no: invoiceNo.trim() || null,
			supplier_invoice_date: invoiceDate || null,
			remarks: remarks.trim() || null,
			items: itemRows,
			packs: editToPayload(packs, new Set(lines.map((l) => l.item_code))),
		};
		try {
			if (isEdit) {
				await updateGrn({ name: id, payload });
				navigate('/grns/' + id);
			} else {
				const r = await createGrn({ payload });
				navigate('/grns/' + r.message.name);
			}
		} catch (e) {
			setErr(parseServerError(e));
		}
	}

	const saving = creating || updating;
	const supplierName = (isEdit ? detail?.message.grn.supplier_name : ctx?.message.supplier_name) || '';

	if (!po) {
		return (
			<main className="tight">
				<div className="eyebrow">Buying · Goods receipt</div>
				<div className="sub" style={{ marginTop: 14 }}>
					Open a submitted purchase order and choose “Create GRN” to receive its goods.
				</div>
			</main>
		);
	}

	return (
		<main className="tight">
			<div className="eyebrow">Buying · Goods receipt</div>
			<div className="crumb" style={{ marginTop: 6 }}>
				<Link to="/grns">Goods receipts</Link> /{' '}
				<span className="data">{isEdit ? id : 'New'}</span>
			</div>

			<div className="titlebar">
				<h1>{isEdit ? 'Edit receipt' : 'Receive goods'}</h1>
				<span className="who">· {supplierName}</span>
				<span className="spacer" />
				<button className="btn" onClick={() => navigate(isEdit ? '/grns/' + id : '/purchases/' + po)}>
					Cancel
				</button>
				<button className="btn primary" disabled={saving} onClick={() => void onSave()}>
					<Icon name="check" size={15} /> {saving ? 'Saving…' : isEdit ? 'Save changes' : 'Create receipt'}
				</button>
			</div>

			{ctxErr && <div className="ferr" style={{ marginBottom: 10 }}>{parseServerError(ctxErr)}</div>}
			{err && <div className="ferr" style={{ marginBottom: 10 }}>{err}</div>}

			<div className="stack">
				<Card accent>
					<CHead icon="cube" title="Receipt" count={po} />
					<div className="formgrid" style={{ padding: '6px 18px 16px' }}>
						<Field label="Receiving warehouse" hint="usually a virtual port warehouse">
							<SearchSelect
								value={warehouse}
								onChange={setWarehouse}
								options={warehouseOptions}
								placeholder="Pick a warehouse…"
							/>
						</Field>
						<Field label="Supplier invoice no" hint="copied back to the PO (GST clock)">
							<TextInput mono value={invoiceNo} onChange={setInvoiceNo} placeholder="Supplier's tax invoice" />
						</Field>
						<Field label="Supplier invoice date">
							<TextInput type="date" value={invoiceDate} onChange={setInvoiceDate} />
						</Field>
					</div>
				</Card>

				<Card>
					<CHead icon="cube" title="Received quantity" count={`${lines.length} lines`} />
					<table>
						<thead>
							<tr>
								<th>Item</th>
								<th>Ordered</th>
								<th>Already received</th>
								<th>Receiving now</th>
							</tr>
						</thead>
						<tbody>
							{lines.map((l, i) => (
								<tr key={l.po_detail || l.item_code}>
									<td>
										<div className="c1">{l.item_name}</div>
										<div className="c2">{l.item_code}</div>
									</td>
									<td className="num">
										{l.ordered_qty} {l.uom ? <span className="dim">{l.uom}</span> : null}
									</td>
									<td className="num">{l.already_received || <span className="dim">—</span>}</td>
									<td className="num" style={{ maxWidth: 120 }}>
										<TextInput
											type="number"
											mono
											value={l.received_qty}
											onChange={(v) => setLine(i, { received_qty: v })}
										/>
									</td>
								</tr>
							))}
						</tbody>
					</table>
				</Card>

				<Card>
					<CHead icon="copy" title="Pack & batch detail" count={packs.length || undefined} />
					<div style={{ padding: '6px 18px 16px' }}>
						<div className="sub" style={{ marginBottom: 8 }}>
							Batches received here forward to the shipment’s packing list.
						</div>
						<PackEditor rows={packs} onChange={setPacks} itemOptions={itemOptions} />
					</div>
				</Card>

				<Card>
					<CHead icon="file-text" title="Remarks" />
					<div style={{ padding: '6px 18px 16px' }}>
						<TextArea value={remarks} onChange={setRemarks} rows={2} />
					</div>
				</Card>
			</div>

			<footer>
				<b>ExportFlow</b> · DUX Digitech
			</footer>
		</main>
	);
}
