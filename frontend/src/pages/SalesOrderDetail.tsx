import { useState } from 'react';
import { useFrappeGetCall, useFrappeGetDocList, useFrappePostCall } from 'frappe-react-sdk';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { AttachmentsCard } from '@/components/AttachmentsCard';
import { Icon } from '@/components/Icon';
import { SearchSelect, TextInput } from '@/components/form';
import { Card, CHead, EmptyMsg, Facts, LRow, Modal, Tag } from '@/components/ui';
import {
	API,
	lcIsOpen,
	lcTone,
	parseServerError,
	pfiTone,
	printPdfUrl,
	printPreviewUrl,
	soTone,
	urgencyTone,
	type SOProcurement,
	type SOMoneySummary,
} from '@/lib/api';
import { daysUntil, fmtDate, fmtDateLong, fmtMoney } from '@/lib/format';

/** " · "-joined fragments, skipping empty/null parts. */
function dotJoin(parts: (string | null | undefined)[]): string {
	return parts.filter(Boolean).join(' · ');
}

/** Per-line draft state in the create-PO modal, keyed by so_detail. */
interface PoSelection {
	checked: boolean;
	qty: string;
	supplier: string;
	rate: string;
}

const PO_GRID = '40px 1.7fr 110px 1.1fr 110px';

export function SalesOrderDetail() {
	const { id = '' } = useParams<{ id: string }>();
	const navigate = useNavigate();

	const { data, error, isLoading, mutate } = useFrappeGetCall<{ message: SOMoneySummary }>(
		API.soMoneySummary,
		{ sales_order: id },
	);
	const { call: submitSo, loading: submitting } = useFrappePostCall(API.submitSo);
	const { call: amendDoc, loading: amending } = useFrappePostCall<{ message: { name: string } }>(
		API.amendDoc,
	);
	const { call: closeOrder, loading: closing } = useFrappePostCall(API.closeOrder);
	const { call: reopenOrder, loading: reopening } = useFrappePostCall(API.reopenOrder);
	const [actionErr, setActionErr] = useState<string | null>(null);

	async function onAmend() {
		setActionErr(null);
		try {
			const r = await amendDoc({ doctype: 'Sales Order', name: id });
			navigate('/sales-orders/' + r.message.name + '/edit');
		} catch (e) {
			setActionErr(parseServerError(e));
		}
	}

	async function onCloseOrder() {
		setActionErr(null);
		try {
			await closeOrder({ doctype: 'Sales Order', name: id });
			await mutate();
		} catch (e) {
			setActionErr(parseServerError(e));
		}
	}

	async function onReopenOrder() {
		setActionErr(null);
		try {
			await reopenOrder({ doctype: 'Sales Order', name: id });
			await mutate();
		} catch (e) {
			setActionErr(parseServerError(e));
		}
	}

	// procurement state per SO line + the POs already raised against each
	const proc = useFrappeGetCall<{ message: SOProcurement }>(API.soProcurement, {
		sales_order: id,
	});
	const { call: createPo, loading: creatingPo } = useFrappePostCall<{
		message: { purchase_orders: { name: string; supplier: string }[] };
	}>(API.createPo);
	const suppliersResult = useFrappeGetDocList<{
		name: string;
		supplier_name: string;
		disabled: 0 | 1;
	}>('Supplier', {
		fields: ['name', 'supplier_name'],
		filters: [['disabled', '=', 0]],
		limit: 200,
	});
	const [poOpen, setPoOpen] = useState(false);
	const [poSel, setPoSel] = useState<Record<string, PoSelection>>({});
	const [poErr, setPoErr] = useState<string | null>(null);

	async function onSubmitOrder() {
		setActionErr(null);
		try {
			await submitSo({ name: id });
			mutate();
		} catch (e) {
			setActionErr(parseServerError(e));
		}
	}

	const procLines = proc.data?.message.lines ?? [];
	const companyCurrency = proc.data?.message.company_currency ?? '';
	const openLines = procLines.filter((l) => l.remaining > 0);

	function openPoModal() {
		const seed: Record<string, PoSelection> = {};
		for (const l of openLines) {
			seed[l.so_detail] = { checked: true, qty: String(l.remaining), supplier: '', rate: '' };
		}
		setPoSel(seed);
		setPoErr(null);
		setPoOpen(true);
	}

	const setLineSel = (key: string, patch: Partial<PoSelection>) =>
		setPoSel((s) => {
			const cur = s[key];
			return cur ? { ...s, [key]: { ...cur, ...patch } } : s;
		});

	const checkedLines = openLines.filter((l) => poSel[l.so_detail]?.checked);
	const supplierCount = new Set(
		checkedLines.map((l) => poSel[l.so_detail]?.supplier).filter(Boolean),
	).size;

	async function onCreatePo() {
		if (checkedLines.length === 0) return setPoErr('Tick at least one line to order.');
		for (const l of checkedLines) {
			const s = poSel[l.so_detail];
			if (!s) continue;
			const qty = Number(s.qty);
			if (!s.qty || qty <= 0) return setPoErr(`${l.item_name}: quantity is required.`);
			if (qty > l.remaining)
				return setPoErr(`${l.item_name}: only ${l.remaining} remains unordered.`);
			if (!s.supplier) return setPoErr(`${l.item_name}: pick the supplier.`);
			if (!s.rate || Number(s.rate) <= 0)
				return setPoErr(`${l.item_name}: buying rate is required.`);
		}
		setPoErr(null);
		try {
			const result = await createPo({
				sales_order: id,
				selections: checkedLines.map((l) => {
					const s = poSel[l.so_detail];
					return {
						so_detail: l.so_detail,
						supplier: s?.supplier ?? '',
						qty: Number(s?.qty),
						rate: Number(s?.rate),
					};
				}),
			});
			setPoOpen(false);
			void proc.mutate();
			const made = result.message.purchase_orders;
			if (made.length === 1) navigate('/purchases/' + made[0].name);
		} catch (e) {
			setPoErr(parseServerError(e));
		}
	}

	if (isLoading) {
		return (
			<main className="tight">
				<div className="eyebrow">Selling · Sales order</div>
				<div className="crumb" style={{ marginTop: 6 }}>
					<Link to="/sales-orders">Sales orders</Link> / <span className="data">{id}</span>
				</div>
				<div className="sub" style={{ marginTop: 14 }}>
					Loading…
				</div>
			</main>
		);
	}

	const detail = data?.message;
	if (error || !detail) {
		return (
			<main className="tight">
				<div className="crumb">
					<Link to="/sales-orders">Sales orders</Link> / <span className="data">{id}</span>
				</div>
				<div className="eyebrow" style={{ marginTop: 18 }}>Selling</div>
				<h1>
					Sales <em>order</em>
				</h1>
				<div style={{ marginTop: 22 }}>
					<Card>
						<div className="ferr" style={{ padding: '18px 20px' }}>
							{error
								? parseServerError(error)
								: 'This sales order could not be loaded. It may not exist, or you may not have permission to view it.'}
						</div>
					</Card>
				</div>
				<footer>
					<b>ExportFlow</b> · DUX Digitech
				</footer>
			</main>
		);
	}

	const { so, pfis, lcs, summary, items, can } = detail;

	return (
		<main className="tight">
			<div className="eyebrow">Selling · Sales order</div>
			<div className="crumb" style={{ marginTop: 6 }}>
				<Link to="/sales-orders">Sales orders</Link> / <span className="data">{id}</span>
			</div>

			<div className="titlebar">
				<h1>{so.name}</h1>
				<span className="who">· {so.customer_name}</span>
				<span style={{ marginTop: 9 }}>
					<Tag tone={soTone(so.status)}>{so.status}</Tag>
				</span>
				<span className="spacer" />
				<a
					className="btn"
					href={printPreviewUrl('Sales Order', id, 'ExportFlow Sales Order')}
					target="_blank"
					rel="noreferrer"
					style={{ textDecoration: 'none' }}
				>
					<Icon name="file-text" size={15} /> Print
				</a>
				<a
					className="btn"
					href={printPdfUrl('Sales Order', id, 'ExportFlow Sales Order')}
					target="_blank"
					rel="noreferrer"
					style={{ textDecoration: 'none' }}
				>
					<Icon name="download" size={15} /> PDF
				</a>
				{so.docstatus === 0 ? (
					<>
						{can.edit && (
							<button className="btn" onClick={() => navigate(`/sales-orders/${id}/edit`)}>
								<Icon name="file-text" size={15} /> Edit
							</button>
						)}
						{can.submit && (
							<button className="btn primary" disabled={submitting} onClick={() => void onSubmitOrder()}>
								<Icon name="check" size={15} /> {submitting ? 'Submitting…' : 'Submit order'}
							</button>
						)}
					</>
				) : (
					<>
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
						<button className="btn" onClick={() => navigate('/lc/new?so=' + id)}>
							<Icon name="calendar" size={15} /> New letter of credit
						</button>
						<button className="btn primary" onClick={() => navigate('/pfi/new?so=' + id)}>
							<Icon name="banknote" size={15} /> New pro forma
						</button>
					</>
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
					<span className="data">{fmtDateLong(so.transaction_date)}</span>
				</span>
				{so.delivery_date && (
					<span className="kv">
						<b>Delivery</b>
						<span className="data">{fmtDate(so.delivery_date)}</span>
					</span>
				)}
				<span className="kv">
					<b>Incoterm</b>
					{[so.incoterm, so.named_place].filter(Boolean).join(' ') || '—'}
				</span>
				<span className="kv">
					<b>Currency</b>
					<span className="data">{so.currency}</span>
				</span>
				{so.payment_terms_narrative && (
					<span className="kv">
						<b>Payment terms</b>
						{so.payment_terms_narrative}
					</span>
				)}
				{so.tc_name && (
					<span className="kv">
						<b>Terms</b>
						{so.tc_name}
					</span>
				)}
			</div>

			<div className="grid detail">
				<div className="stack">
					<Card accent>
						<CHead icon="banknote" title="Money" count={so.currency} />
						<Facts
							rows={[
								{ k: 'SO value', v: fmtMoney(summary.so_value, so.currency), data: true },
								{ k: 'PFI raised', v: fmtMoney(summary.raised, so.currency), data: true },
								{ k: 'Received', v: fmtMoney(summary.received, so.currency), data: true },
								{ k: 'Balance', v: fmtMoney(summary.balance, so.currency), data: true },
							]}
						/>
					</Card>

					<Card>
						<CHead
							icon="package"
							title="Order items"
							count={`${items.length} ${items.length === 1 ? 'line' : 'lines'}`}
						/>
						{items.length === 0 ? (
							<EmptyMsg title="No item lines" />
						) : (
							<table>
								<thead>
									<tr>
										<th>Item</th>
										<th>Qty</th>
										<th>Rate</th>
										<th style={{ textAlign: 'right' }}>Amount</th>
									</tr>
								</thead>
								<tbody>
									{items.map((it, i) => (
										<tr key={i}>
											<td>
												<div className="c1">{it.item_name}</div>
												<div className="c2">{it.item_code}</div>
											</td>
											<td className="num">{`${it.qty} ${it.uom ?? ''}`.trim()}</td>
											<td className="num">{fmtMoney(it.rate, so.currency)}</td>
											<td className="num" style={{ textAlign: 'right' }}>
												{fmtMoney(it.amount, so.currency)}
											</td>
										</tr>
									))}
								</tbody>
							</table>
						)}
					</Card>

					<Card>
						<CHead
							icon="file-text"
							title="Pro forma invoices"
							count={pfis.length}
							action={so.docstatus === 1 ? <Link to={'/pfi/new?so=' + id}>New</Link> : undefined}
						/>
						{pfis.length === 0 ? (
							<EmptyMsg
								title="No pro forma invoices yet"
								text={
									so.docstatus === 0
										? 'Submit the order first — PFIs are raised against submitted deals.'
										: 'Raise the first PFI against this order to start collecting payment.'
								}
							/>
						) : (
							pfis.map((p) => (
								<LRow
									key={p.name}
									icon="banknote"
									t1={<span className="data">{p.name}</span>}
									t2={dotJoin([p.stage_description, p.expected_payment_method, fmtDate(p.pfi_date)])}
									right={
										<>
											<span className="num">{fmtMoney(p.amount, p.currency)}</span>
											<div style={{ marginTop: 3 }}>
												<Tag tone={pfiTone(p.status)}>{p.status}</Tag>
											</div>
										</>
									}
									onClick={() => navigate('/pfi/' + p.name)}
								/>
							))
						)}
					</Card>

					<Card>
						<CHead
							icon="cube"
							title="Procurement"
							count={proc.data ? `${procLines.length} lines` : undefined}
							action={
								so.docstatus === 1 && openLines.length > 0 ? (
									<a
										href="#"
										onClick={(e) => {
											e.preventDefault();
											openPoModal();
										}}
									>
										Create PO
									</a>
								) : undefined
							}
						/>
						{proc.error ? (
							<div className="ferr" style={{ padding: '14px 18px' }}>
								{parseServerError(proc.error)}
							</div>
						) : !proc.data ? (
							<div className="sub" style={{ padding: '14px 18px' }}>
								Loading…
							</div>
						) : procLines.length === 0 ? (
							<EmptyMsg title="No lines to procure" text="This order has no item lines yet." />
						) : (
							<table>
								<thead>
									<tr>
										<th>Item</th>
										<th>Ordered</th>
										<th>Shipped</th>
										<th>Suppliers / POs</th>
									</tr>
								</thead>
								<tbody>
									{procLines.map((l) => (
										<tr key={l.so_detail}>
											<td>
												<div className="c1">{l.item_name}</div>
												<div className="c2">{l.item_code}</div>
											</td>
											<td>
												<span className="num">
													{l.ordered_qty + l.draft_qty} / {l.qty}
												</span>
												{l.draft_qty > 0 && <div className="c2">draft {l.draft_qty}</div>}
											</td>
											<td>
												<span className="dim">{l.shipped_qty}</span>
												{l.in_transit_qty > 0 && <div className="c2">in transit {l.in_transit_qty}</div>}
											</td>
											<td>
												{l.pos.length === 0 ? (
													<span className="dim">not ordered</span>
												) : (
													<div
														style={{
															display: 'flex',
															flexWrap: 'wrap',
															alignItems: 'center',
															gap: '4px 12px',
														}}
													>
														{l.pos.map((po) => (
															<span
																key={po.name}
																style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
															>
																<Link className="id id-sm" to={'/purchases/' + po.name}>
																	{po.name}
																</Link>
																{po.merchant_export_scheme === 1 && <Tag tone="pend">0.1%</Tag>}
															</span>
														))}
													</div>
												)}
											</td>
										</tr>
									))}
								</tbody>
							</table>
						)}
					</Card>
				</div>

				<div className="stack">
					<Card>
						<CHead
							icon="calendar"
							title="Letters of credit"
							count={lcs.length}
							action={so.docstatus === 1 ? <Link to={'/lc/new?so=' + id}>New</Link> : undefined}
						/>
						{lcs.length === 0 ? (
							<EmptyMsg
								title="No letters of credit"
								text={
									so.docstatus === 0
										? 'Submit the order first — LCs are recorded against submitted deals.'
										: 'Record an LC here when the buyer’s bank issues one for this order.'
								}
							/>
						) : (
							lcs.map((lc) => {
								// the ship-by alarm only makes sense while the LC is open
								const days = daysUntil(lc.latest_shipment_date);
								const shipTone = lcIsOpen(lc.status) ? urgencyTone(days) : null;
								return (
									<LRow
										key={lc.name}
										icon="calendar"
										t1={<span className="data">{lc.lc_number}</span>}
										t2={dotJoin([lc.issuing_bank, `Expiry ${fmtDate(lc.expiry_date)}`])}
										right={
											shipTone ? (
												<Tag tone={shipTone}>Ship by {fmtDate(lc.latest_shipment_date)}</Tag>
											) : (
												<Tag tone={lcTone(lc.status)}>{lc.status}</Tag>
											)
										}
										onClick={() => navigate('/lc/' + lc.name)}
									/>
								);
							})
						)}
					</Card>

					<AttachmentsCard doctype="Sales Order" name={id} canWrite={!!can.write} />
				</div>
			</div>

			{poOpen && (
				<Modal title="Create purchase order" icon="cube" onClose={() => setPoOpen(false)}>
					<div className="reqhead" style={{ gridTemplateColumns: PO_GRID }}>
						<span />
						<span>Item</span>
						<span>Qty</span>
						<span>Supplier</span>
						<span>Buying rate{companyCurrency ? ` (${companyCurrency})` : ''}</span>
					</div>
					{openLines.map((l) => {
						const s = poSel[l.so_detail];
						if (!s) return null;
						return (
							<div className="reqrow" key={l.so_detail} style={{ gridTemplateColumns: PO_GRID }}>
								<input
									type="checkbox"
									checked={s.checked}
									aria-label={`Order ${l.item_name}`}
									onChange={(e) => setLineSel(l.so_detail, { checked: e.target.checked })}
								/>
								<span>
									<span className="c1" style={{ display: 'block' }}>
										{l.item_name}
									</span>
									<span className="c2" style={{ display: 'block' }}>
										{[l.remaining, l.uom, 'remaining'].filter(Boolean).join(' ')}
									</span>
								</span>
								<TextInput
									type="number"
									value={s.qty}
									onChange={(v) => setLineSel(l.so_detail, { qty: v })}
								/>
								<SearchSelect
									value={s.supplier}
									onChange={(v) => setLineSel(l.so_detail, { supplier: v })}
									options={(suppliersResult.data ?? []).map((sup) => ({
										value: sup.name,
										label: sup.supplier_name,
									}))}
																	/>
								<TextInput
									type="number"
									value={s.rate}
									onChange={(v) => setLineSel(l.so_detail, { rate: v })}
								/>
							</div>
						);
					})}
					<div className="formfoot">
						{poErr && <span className="ferr">{poErr}</span>}
						<span className="spacer" />
						<button
							type="button"
							className="btn primary"
							disabled={creatingPo}
							onClick={() => void onCreatePo()}
						>
							<Icon name="plus" size={15} />
							{creatingPo
								? 'Creating…'
								: `Create purchase order${supplierCount > 1 ? 's' : ''}`}
						</button>
					</div>
				</Modal>
			)}

			<footer>
				<b>ExportFlow</b> · DUX Digitech
			</footer>
		</main>
	);
}
