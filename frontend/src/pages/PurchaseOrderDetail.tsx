import { useEffect, useRef, useState } from 'react';
import { useFrappeGetCall, useFrappePostCall, useFrappeUpdateDoc } from 'frappe-react-sdk';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Icon } from '@/components/Icon';
import { Field, TextInput } from '@/components/form';
import { Card, CHead, EmptyMsg, Facts, LRow, Tag } from '@/components/ui';
import {
	API,
	parseServerError,
	poTone,
	urgencyLabel,
	urgencyTone,
	type PODetailData,
	printPdfUrl,
	printPreviewUrl,
} from '@/lib/api';
import { daysUntil, fmtDate, fmtDateLong, fmtMoney } from '@/lib/format';

/** Fields on a submitted PO that stay writable (allow_on_submit). */
interface POInvoiceWritable {
	supplier_invoice_no: string | null;
	supplier_invoice_date: string | null;
}

export function PurchaseOrderDetail() {
	const { id = '' } = useParams<{ id: string }>();
	const navigate = useNavigate();

	const { data, error, isLoading, mutate } = useFrappeGetCall<{ message: PODetailData }>(
		API.poDetail,
		{ name: id },
	);
	const { call: submitPo, loading: submitting } = useFrappePostCall(API.submitPo);
	const { call: amendDoc, loading: amending } = useFrappePostCall<{ message: { name: string } }>(
		API.amendDoc,
	);
	const { call: closeOrder, loading: closing } = useFrappePostCall(API.closeOrder);
	const { call: reopenOrder, loading: reopening } = useFrappePostCall(API.reopenOrder);
	const { updateDoc, loading: savingInvoice } = useFrappeUpdateDoc<POInvoiceWritable>();
	const [actionErr, setActionErr] = useState<string | null>(null);
	const [invoiceErr, setInvoiceErr] = useState<string | null>(null);
	const [invoiceNo, setInvoiceNo] = useState('');
	const [invoiceDate, setInvoiceDate] = useState('');

	const po = data?.message.po;

	// Seed the GST capture form once per PO — background revalidation must not
	// clobber in-progress edits.
	const seededFor = useRef<string | null>(null);
	useEffect(() => {
		if (!po || seededFor.current === po.name) return;
		seededFor.current = po.name;
		setInvoiceNo(po.supplier_invoice_no ?? '');
		setInvoiceDate(po.supplier_invoice_date ?? '');
	}, [po]);

	async function onSubmitOrder() {
		setActionErr(null);
		try {
			await submitPo({ name: id });
			await mutate();
		} catch (e) {
			setActionErr(parseServerError(e));
		}
	}

	async function onAmend() {
		setActionErr(null);
		try {
			const r = await amendDoc({ doctype: 'Purchase Order', name: id });
			navigate('/purchases/' + r.message.name + '/edit');
		} catch (e) {
			setActionErr(parseServerError(e));
		}
	}

	async function onCloseOrder() {
		setActionErr(null);
		try {
			await closeOrder({ doctype: 'Purchase Order', name: id });
			await mutate();
		} catch (e) {
			setActionErr(parseServerError(e));
		}
	}

	async function onReopenOrder() {
		setActionErr(null);
		try {
			await reopenOrder({ doctype: 'Purchase Order', name: id });
			await mutate();
		} catch (e) {
			setActionErr(parseServerError(e));
		}
	}

	async function onSaveInvoice() {
		setInvoiceErr(null);
		try {
			await updateDoc('Purchase Order', id, {
				supplier_invoice_no: invoiceNo.trim() || null,
				supplier_invoice_date: invoiceDate || null,
			});
			await mutate();
		} catch (e) {
			setInvoiceErr(parseServerError(e));
		}
	}

	if (isLoading) {
		return (
			<main className="tight">
				<div className="eyebrow">Buying · Purchase order</div>
				<div className="crumb" style={{ marginTop: 6 }}>
					<Link to="/purchases">Purchases</Link> / <span className="data">{id}</span>
				</div>
				<div className="sub" style={{ marginTop: 14 }}>
					Loading…
				</div>
			</main>
		);
	}

	const detail = data?.message;
	if (error || !detail || !po) {
		return (
			<main className="tight">
				<div className="crumb">
					<Link to="/purchases">Purchases</Link> / <span className="data">{id}</span>
				</div>
				<div className="eyebrow" style={{ marginTop: 18 }}>Buying</div>
				<h1>
					Purchase <em>order</em>
				</h1>
				<div style={{ marginTop: 22 }}>
					<Card>
						<div className="ferr" style={{ padding: '18px 20px' }}>
							This purchase order could not be loaded.{' '}
							{error ? parseServerError(error) : 'It may not exist, or you may not have permission to view it.'}
						</div>
					</Card>
				</div>
				<footer>
					<b>ExportFlow</b> · DUX Digitech
				</footer>
			</main>
		);
	}

	const { items, shipments, can } = detail;
	const linkedSos = [...new Set(items.map((it) => it.sales_order).filter((so): so is string => !!so))];
	const deadlineDays = daysUntil(po.gst_export_deadline);
	const deadlineTone = urgencyTone(deadlineDays);

	return (
		<main className="tight">
			<div className="eyebrow">Buying · Purchase order</div>
			<div className="crumb" style={{ marginTop: 6 }}>
				<Link to="/purchases">Purchases</Link> / <span className="data">{id}</span>
			</div>

			<div className="titlebar">
				<h1>{po.name}</h1>
				<span className="who">· {po.supplier_name}</span>
				<span style={{ marginTop: 9 }}>
					<Tag tone={poTone(po.status, po.docstatus)}>
						{po.docstatus === 0 ? 'Draft' : po.status}
					</Tag>
				</span>
				<span className="spacer" />
				<a className="btn" href={printPreviewUrl('Purchase Order', id, 'ExportFlow Purchase Order')} target="_blank" rel="noreferrer" style={{ textDecoration: 'none' }}>
					<Icon name="file-text" size={15} /> Print
				</a>
				<a className="btn" href={printPdfUrl('Purchase Order', id, 'ExportFlow Purchase Order')} style={{ textDecoration: 'none' }}>
					<Icon name="download" size={15} /> PDF
				</a>
				{can.edit && (
					<button className="btn" onClick={() => navigate(`/purchases/${id}/edit`)}>
						<Icon name="file-text" size={15} /> Edit
					</button>
				)}
				{can.amend && (
					<button className="btn" disabled={amending} onClick={() => void onAmend()}>
						<Icon name="refresh" size={15} /> {amending ? 'Amending…' : 'Amend'}
					</button>
				)}
				{can.close && (
					<button className="btn" disabled={closing} onClick={() => void onCloseOrder()}>
						<Icon name="lock" size={15} /> {closing ? 'Closing…' : 'Close'}
					</button>
				)}
				{can.reopen && (
					<button className="btn" disabled={reopening} onClick={() => void onReopenOrder()}>
						<Icon name="unlock" size={15} /> {reopening ? 'Reopening…' : 'Re-open'}
					</button>
				)}
				{po.docstatus === 0 && can.submit && (
					<button className="btn primary" disabled={submitting} onClick={() => void onSubmitOrder()}>
						<Icon name="check" size={15} /> {submitting ? 'Submitting…' : 'Submit order'}
					</button>
				)}
			</div>
			{actionErr && (
				<div className="ferr" style={{ marginBottom: 10 }}>
					{actionErr}
				</div>
			)}

			<div className="metaline">
				<span className="kv">
					<b>Date</b>
					<span className="data">{fmtDateLong(po.transaction_date)}</span>
				</span>
				<span className="kv">
					<b>Schedule</b>
					<span className="data">{fmtDateLong(po.schedule_date)}</span>
				</span>
				<span className="kv">
					<b>Value</b>
					<span className="data">{fmtMoney(po.grand_total, po.currency)}</span>
				</span>
			</div>

			<div className="grid detail">
				<div className="stack">
					<Card accent>
						<CHead icon="cube" title="Items" count={`${items.length} lines`} />
						<table>
							<thead>
								<tr>
									<th>Item</th>
									<th>Qty</th>
									<th>Rate</th>
									<th>Amount</th>
									<th>Fulfils</th>
								</tr>
							</thead>
							<tbody>
								{items.map((it) => (
									<tr key={it.name}>
										<td>
											<div className="c1">{it.item_name}</div>
											<div className="c2">{it.item_code}</div>
										</td>
										<td className="num">
											{it.qty} {it.uom ? <span className="dim">{it.uom}</span> : null}
										</td>
										<td className="num">{fmtMoney(it.rate, po.currency)}</td>
										<td className="num">{fmtMoney(it.amount, po.currency)}</td>
										<td>
											{it.sales_order ? (
												<span className="id">{it.sales_order}</span>
											) : (
												<span className="dim">—</span>
											)}
										</td>
									</tr>
								))}
							</tbody>
						</table>
					</Card>

					<Card>
						<CHead icon="banknote" title="Taxes & totals" count={detail.totals.taxes.length ? `${detail.totals.taxes.length} heads` : undefined} />
						<Facts
							rows={[
								{ k: 'Net total', v: fmtMoney(detail.totals.net_total, po.currency), data: true },
								...detail.totals.taxes.map((tax) => ({
									k: tax.rate ? `${tax.description} @ ${tax.rate}%` : tax.description,
									v: fmtMoney(tax.tax_amount, po.currency),
									data: true,
								})),
								{ k: 'Grand total', v: fmtMoney(detail.totals.grand_total, po.currency), data: true },
							]}
						/>
					</Card>

					<Card>
						<CHead icon="ship" title="Shipments" count={shipments.length} />
						{shipments.length === 0 ? (
							<EmptyMsg
								title="No shipments yet"
								text="Lines from this PO appear here once a shipment carries them."
							/>
						) : (
							shipments.map((s) => (
								<LRow
									key={s.shipment}
									icon={s.mode === 'Air' ? 'plane' : 'ship'}
									t1={<span className="data">{s.shipment}</span>}
									t2={`${s.current_milestone} · ETD ${fmtDate(s.etd)}`}
									onClick={() => navigate('/shipments/' + s.shipment)}
								/>
							))
						)}
					</Card>
				</div>

				<div className="stack">
					<Card>
						<CHead icon="banknote" title="GST · merchant export" />
						{!po.merchant_export_scheme ? (
							<div className="empty" style={{ padding: '28px 20px' }}>
								<div className="t2">Not under the 0.1% scheme.</div>
							</div>
						) : (
							<>
								<Facts
									rows={[
										{ k: 'Scheme', v: <Tag tone="pend">0.1% GST</Tag> },
										{ k: 'Supplier invoice', v: po.supplier_invoice_no ?? '—', data: true },
										{ k: 'Invoice date', v: fmtDateLong(po.supplier_invoice_date), data: true },
										{
											k: 'Export deadline',
											v: po.gst_export_deadline ? (
												<>
													<span className="data">{fmtDateLong(po.gst_export_deadline)}</span>
													{deadlineTone && deadlineDays !== null ? (
														<>
															{' '}
															<Tag tone={deadlineTone}>{urgencyLabel(deadlineDays)}</Tag>
														</>
													) : null}
												</>
											) : (
												<span className="dim">enter the supplier invoice</span>
											),
										},
									]}
								/>
								<div style={{ padding: '4px 18px 16px', display: 'grid', gap: 12 }}>
									<Field label="Supplier invoice no">
										<TextInput
											mono
											value={invoiceNo}
											onChange={setInvoiceNo}
											placeholder="Supplier's tax invoice"
										/>
									</Field>
									<Field label="Invoice date">
										<TextInput type="date" value={invoiceDate} onChange={setInvoiceDate} />
									</Field>
									{invoiceErr && <div className="ferr">{invoiceErr}</div>}
									<div>
										<button
											className="btn"
											disabled={savingInvoice}
											onClick={() => void onSaveInvoice()}
										>
											<Icon name="check" size={15} /> {savingInvoice ? 'Saving…' : 'Save'}
										</button>
									</div>
								</div>
							</>
						)}
					</Card>

					{(po.tc_name || po.terms) && (
						<Card>
							<CHead icon="file-text" title="Terms & conditions" count={po.tc_name ?? undefined} />
							<div className="c2" style={{ padding: '12px 18px', whiteSpace: 'pre-wrap' }}>
								{(po.terms ?? '').replace(/<[^>]*>/g, '') || '—'}
							</div>
						</Card>
					)}
					<Card>
						<CHead icon="link-boxes" title="Linked" />
						<Facts
							rows={[
								...linkedSos.map((so, i) => ({
									k: i === 0 ? 'Sales order' : `Sales order ${i + 1}`,
									v: (
										<Link className="data" to={`/sales-orders/${so}`}>
											{so}
										</Link>
									),
								})),
								{ k: 'Supplier', v: po.supplier_name },
							]}
						/>
					</Card>
				</div>
			</div>

			<footer>
				<b>ExportFlow</b> · DUX Digitech
			</footer>
		</main>
	);
}
