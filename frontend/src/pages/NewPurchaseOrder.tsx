import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import { useFrappeGetCall, useFrappePostCall } from 'frappe-react-sdk';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { Icon } from '@/components/Icon';
import { MasterModal } from '@/components/MasterModal';
import { CheckInput, Field, SearchSelect, TextArea, TextInput } from '@/components/form';
import { Card, CHead, EmptyMsg, Facts } from '@/components/ui';
import {
	API,
	parseServerError,
	type NewPOContext,
	type PODetailData,
	type POTotals,
	type SOProcurement,
} from '@/lib/api';
import { fmtMoney } from '@/lib/format';
import { MASTERS, STATIC_OPTIONS, type OptionSource } from '@/lib/masters';

const SUPPLIER_DEF = MASTERS.find((m) => m.doctype === 'Supplier')!;
const ITEM_DEF = MASTERS.find((m) => m.doctype === 'Item')!;
const TC_DEF = MASTERS.find((m) => m.doctype === 'Terms and Conditions')!;
const PAYMENT_DEF = MASTERS.find((m) => m.doctype === 'Export Payment Term')!;

/** A PO line — SO-linked rows carry the deal references, free rows don't. */
interface PORow {
	item_code: string;
	item_name: string;
	qty: string;
	uom: string;
	rate: string;
	sales_order: string | null;
	so_detail: string | null;
	max_qty: number | null;
	specification: string;
	packaging: string;
}

interface ChargeRow {
	description: string;
	account_head: string;
	amount: string;
}

const GRID = '1.8fr 1fr 90px 70px 120px 120px 34px';
// charge name + amount + remove — the expense account is filled in behind the
// scenes from the configured default (feedback #11), so users never pick one
const CHARGE_GRID = '1fr 130px 34px';

function todayISO(): string {
	const d = new Date();
	return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function NewPurchaseOrder() {
	const navigate = useNavigate();
	const [searchParams] = useSearchParams();
	const { id: editId } = useParams<{ id?: string }>();
	const isEdit = !!editId;

	const ctxResult = useFrappeGetCall<{ message: NewPOContext }>(API.newPoContext, undefined);
	const ctx = ctxResult.data?.message;

	const editResult = useFrappeGetCall<{ message: PODetailData }>(
		API.poDetail,
		{ name: editId },
		isEdit ? undefined : null,
	);

	const [supplier, setSupplier] = useState('');
	const [mes, setMes] = useState(false);
	const [orderDate, setOrderDate] = useState(todayISO());
	const [requiredBy, setRequiredBy] = useState('');
	const [tcName, setTcName] = useState('');
	const [terms, setTerms] = useState('');
	const [paymentTerms, setPaymentTerms] = useState('');
	// payment-terms picker selection — display-only within the session (the chosen
	// template just fills the narrative, which is the saved/printed value; the ref is
	// not persisted, so this resets to blank on edit)
	const [ptName, setPtName] = useState('');
	const [taxesTemplate, setTaxesTemplate] = useState('');
	const [taxDefaulted, setTaxDefaulted] = useState(false);
	const [charges, setCharges] = useState<ChargeRow[]>([]);
	const [rows, setRows] = useState<PORow[]>([]);
	const [soPick, setSoPick] = useState(searchParams.get('so') ?? '');
	const [err, setErr] = useState<string | null>(null);
	const [quickCreate, setQuickCreate] = useState<'supplier' | 'item' | 'terms' | 'payment' | null>(null);
	const [preview, setPreview] = useState<POTotals | null>(null);
	const [currency, setCurrency] = useState('');
	const [convRate, setConvRate] = useState('');
	const [rateTouched, setRateTouched] = useState(false);
	const [merchanting, setMerchanting] = useState(false);
	const companyCurrency = ctx?.company_currency ?? '';

	// default the taxes template once the context arrives (creates only — an
	// edit prefills the order's own template)
	useEffect(() => {
		if (!ctx || taxDefaulted || isEdit) return;
		const def = ctx.taxes_templates.find((t) => t.is_default);
		if (def) setTaxesTemplate(def.name);
		setTaxDefaulted(true);
	}, [ctx, taxDefaulted, isEdit]);

	// prefill from the existing PO when editing (seed exactly once)
	const seeded = useRef(false);
	const seededCurrency = useRef<string | null>(null);
	const seededRate = useRef<string>('');
	useEffect(() => {
		if (!isEdit || seeded.current) return;
		const d = editResult.data?.message;
		if (!d) return;
		setSupplier(d.po.supplier ?? '');
		setMes(d.po.merchant_export_scheme === 1);
		setMerchanting(!!d.po.merchanting_trade);
		seededCurrency.current = d.po.currency ?? '';
		seededRate.current = d.po.conversion_rate != null ? String(d.po.conversion_rate) : '';
		setCurrency(d.po.currency ?? '');
		setConvRate(seededRate.current);
		setRateTouched(true); // keep the order's booked rate, don't auto-suggest over it
		setOrderDate(d.po.transaction_date ?? todayISO());
		setRequiredBy(d.po.schedule_date ?? '');
		setTcName(d.po.tc_name ?? '');
		setTerms(d.po.terms ?? '');
		setPaymentTerms(d.po.payment_terms_narrative ?? '');
		setTaxesTemplate(d.po.taxes_and_charges ?? '');
		setTaxDefaulted(true);
		setCharges(
			(d.extra_charges ?? []).map((c) => ({
				description: c.description,
				account_head: c.account_head,
				amount: String(c.amount),
			})),
		);
		const editItems = d.items ?? [];
		setRows(
			editItems.map((it) => ({
				item_code: it.item_code,
				item_name: it.item_name,
				qty: String(it.qty),
				uom: it.uom ?? '',
				rate: String(it.rate),
				sales_order: it.sales_order,
				so_detail: it.sales_order_item,
				max_qty: null, // editing existing lines — backend skips the remaining guard
				specification: it.specification ?? '',
				packaging: it.packaging ?? '',
			})),
		);
		// surface the live "remaining on SO" caption while editing — load the
		// linked SO's lines (soProcurement excludes this PO via exclude_po)
		const firstSo = editItems.find((it) => it.sales_order)?.sales_order;
		if (firstSo) setSoPick(firstSo);
		seeded.current = true;
	}, [isEdit, editResult.data]);

	// lines of the picked SO, to pull into the order. When editing, exclude this
	// PO's own draft contribution so the live remaining caption isn't double-counted
	const soLines = useFrappeGetCall<{ message: SOProcurement }>(
		API.soProcurement,
		{ sales_order: soPick, exclude_po: isEdit ? editId : null },
		soPick ? undefined : null,
	);
	// suggest the day's BUYING exchange rate when the PO currency changes; a
	// manual edit (rateTouched) or returning to the edited PO's booked currency
	// is preserved
	const rateResult = useFrappeGetCall<{ message: number }>(
		API.poExchangeRate,
		{ currency },
		currency ? undefined : null,
	);
	useEffect(() => {
		if (isEdit && seededCurrency.current !== null && currency === seededCurrency.current) {
			setConvRate(seededRate.current);
			setRateTouched(true);
			return;
		}
		setRateTouched(false);
	}, [currency, isEdit]);
	useEffect(() => {
		const suggested = rateResult.data?.message;
		if (!rateTouched && suggested && suggested > 0) setConvRate(String(suggested));
	}, [rateResult.data, rateTouched]);

	const isCompanyCurrency = !currency || currency === companyCurrency;
	// align with the backend: a supplier is foreign only when its country is set
	// and not India (a blank country is treated as domestic)
	const supplierIsForeign = !!ctx?.suppliers.find(
		(x) => x.name === supplier && !!x.country && x.country !== 'India',
	);

	const { call: fetchTerms } = useFrappePostCall<{ message: string }>(API.termsText);
	const { call: fetchPaymentTerms } = useFrappePostCall<{ message: string }>(API.paymentTermsText);
	const { call: fetchItemInfo } = useFrappePostCall<{ message: { stock_uom: string; item_name: string } }>(
		API.itemInfo,
	);
	const { call: previewPo } = useFrappePostCall<{ message: POTotals }>(API.previewPo);
	const { call: createPo, loading: saving } = useFrappePostCall<{
		message: { name: string; docstatus: number };
	}>(API.createPoDraft);
	const { call: updatePo, loading: updating } = useFrappePostCall<{
		message: { name: string; docstatus: number };
	}>(API.updatePo);
	const busy = saving || updating;

	function buildPayload(submit: boolean) {
		return {
			supplier,
			transaction_date: orderDate,
			schedule_date: requiredBy || null,
			currency: currency || null,
			conversion_rate: isCompanyCurrency ? 1 : Number(convRate) || 0,
			// only the scheme applicable to this supplier type is sent — the other
			// checkbox is disabled (and forced off), so it can never leak (#9)
			merchant_export_scheme: !supplierIsForeign && mes ? 1 : 0,
			merchanting_trade: supplierIsForeign && merchanting ? 1 : 0,
			taxes_template: taxesTemplate || null,
			// charges need only a name + amount; the expense account is resolved
			// server-side from the configured default when omitted (#11)
			extra_charges: charges
				.filter((c) => Number(c.amount) > 0)
				.map((c) => ({
					description: c.description || 'Charges',
					account_head: c.account_head || null,
					amount: Number(c.amount),
				})),
			tc_name: tcName || null,
			terms,
			payment_terms_narrative: paymentTerms,
			submit: submit ? 1 : 0,
			items: rows.map((r) => ({
				item_code: r.item_code,
				qty: Number(r.qty),
				rate: Number(r.rate),
				sales_order: r.sales_order,
				so_detail: r.so_detail,
				specification: r.specification || null,
				packaging: r.packaging || null,
			})),
		};
	}

	// live tax preview through the real ERPNext engine, debounced
	const previewKey = JSON.stringify({
		supplier,
		taxesTemplate,
		charges,
		currency,
		convRate,
		merchanting,
		mes,
		rows: rows.map((r) => [r.item_code, r.qty, r.rate]),
	});
	const previewTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
	useEffect(() => {
		if (previewTimer.current) clearTimeout(previewTimer.current);
		const complete =
			supplier && rows.length > 0 && rows.every((r) => Number(r.qty) > 0 && Number(r.rate) > 0);
		if (!complete) {
			setPreview(null);
			return;
		}
		previewTimer.current = setTimeout(() => {
			previewPo({ podata: buildPayload(false) })
				.then((res) => setPreview(res.message))
				.catch(() => setPreview(null));
		}, 600);
		return () => {
			if (previewTimer.current) clearTimeout(previewTimer.current);
		};
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [previewKey]);

	function onSupplier(v: string) {
		setSupplier(v);
		const s = ctx?.suppliers.find((x) => x.name === v);
		const foreign = !!s && !!s.country && s.country !== 'India';
		setMes(!foreign && !!s?.default_merchant_export_scheme);
		if (!foreign) setMerchanting(false); // MTT is overseas-only
		// prefill the PO currency from the supplier's default (foreign → its own)
		setCurrency(s?.default_currency || (foreign ? 'USD' : companyCurrency));
		setRateTouched(false);
	}

	async function onTemplate(v: string) {
		setTcName(v);
		if (!v) return;
		try {
			const text = (await fetchTerms({ template: v })).message;
			setTerms(text.replace(/<[^>]*>/g, ''));
		} catch {
			// template text is a convenience — leave the field as typed
		}
	}

	async function onPaymentTemplate(v: string) {
		setPtName(v);
		if (!v) return;
		try {
			// Export Payment Term.terms is plain text (printed via | e) — assign as-is,
			// no HTML strip (unlike the rich-text T&C path).
			setPaymentTerms((await fetchPaymentTerms({ template: v })).message);
		} catch {
			// template text is a convenience — leave the field as typed
		}
	}

	const addedDetails = new Set(rows.map((r) => r.so_detail).filter(Boolean));
	const pickableLines = (soLines.data?.message.lines ?? []).filter(
		(l) => l.remaining > 0 && !addedDetails.has(l.so_detail),
	);

	// live "remaining on SO" per line: the server figure (which excludes this PO
	// when editing, via exclude_po) minus what the current form rows consume —
	// so reducing a line's qty immediately frees its SO quantity in the caption (#10)
	const soLineByDetail = new Map((soLines.data?.message.lines ?? []).map((l) => [l.so_detail, l]));
	const usedByForm = useMemo(() => {
		const m: Record<string, number> = {};
		for (const r of rows) {
			if (r.so_detail) m[r.so_detail] = (m[r.so_detail] ?? 0) + (Number(r.qty) || 0);
		}
		return m;
	}, [rows]);
	function liveRemaining(soDetail: string | null): number | null {
		if (!soDetail) return null;
		const l = soLineByDetail.get(soDetail);
		if (!l) return null;
		return Math.round((l.remaining - (usedByForm[soDetail] ?? 0)) * 1000) / 1000;
	}

	// per-row specification + packaging editor (feedback #13) — collapsed by default
	const [expanded, setExpanded] = useState<Set<number>>(new Set());
	const toggleExpand = (i: number) =>
		setExpanded((s) => {
			const n = new Set(s);
			if (n.has(i)) n.delete(i);
			else n.add(i);
			return n;
		});
	// remove an item row AND remap the index-keyed expand state so the open flag
	// stays with the right row after the array reindexes
	const removeRow = (i: number) => {
		setRows((rs) => rs.filter((_, idx) => idx !== i));
		setExpanded((s) => {
			const n = new Set<number>();
			for (const x of s) {
				if (x === i) continue;
				n.add(x > i ? x - 1 : x);
			}
			return n;
		});
	};

	function addSoLine(soDetail: string) {
		const l = (soLines.data?.message.lines ?? []).find((x) => x.so_detail === soDetail);
		if (!l) return;
		setRows((rs) => [
			...rs,
			{
				item_code: l.item_code,
				item_name: l.item_name,
				qty: String(l.remaining),
				uom: l.uom ?? '',
				rate: '',
				sales_order: soPick,
				so_detail: l.so_detail,
				max_qty: l.remaining,
				specification: '',
				packaging: '',
			},
		]);
	}

	async function addFreeRow(itemCode: string) {
		if (!itemCode) return;
		const listed = ctx?.items.find((i) => i.name === itemCode);
		setRows((rs) => [
			...rs,
			{
				item_code: itemCode,
				item_name: listed?.item_name ?? itemCode,
				qty: '',
				uom: listed?.stock_uom ?? '',
				rate: '',
				sales_order: null,
				so_detail: null,
				max_qty: null,
				specification: '',
				packaging: '',
			},
		]);
		if (!listed) {
			try {
				const info = (await fetchItemInfo({ item_code: itemCode })).message;
				setRows((rs) =>
					rs.map((r) =>
						r.item_code === itemCode && !r.uom ? { ...r, uom: info.stock_uom, item_name: info.item_name } : r,
					),
				);
			} catch {
				// best effort
			}
		}
	}

	const setRow = (i: number, patch: Partial<PORow>) =>
		setRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
	const setCharge = (i: number, patch: Partial<ChargeRow>) =>
		setCharges((cs) => cs.map((c, idx) => (idx === i ? { ...c, ...patch } : c)));

	const subtotal = useMemo(
		() => rows.reduce((sum, r) => sum + (Number(r.qty) || 0) * (Number(r.rate) || 0), 0),
		[rows],
	);

	async function onSave(submit: boolean) {
		if (!supplier) return setErr('Pick the supplier.');
		if (!isCompanyCurrency && (!convRate || Number(convRate) <= 0))
			return setErr('Set the exchange rate.');
		if (merchanting && !rows.some((r) => r.so_detail))
			return setErr('A merchanting purchase must pull its lines from a sales order.');
		if (rows.length === 0) return setErr('Add at least one item.');
		for (const [i, r] of rows.entries()) {
			if (!r.qty || Number(r.qty) <= 0) return setErr(`Row ${i + 1}: quantity is required.`);
			if (r.max_qty !== null && Number(r.qty) > r.max_qty + 1e-6)
				return setErr(`Row ${i + 1}: only ${r.max_qty} remains unordered on ${r.sales_order}.`);
			if (!r.rate || Number(r.rate) <= 0) return setErr(`Row ${i + 1}: buying rate is required.`);
		}
		for (const [i, c] of charges.entries()) {
			if (!c.amount || Number(c.amount) <= 0)
				return setErr(`Charge ${i + 1}: enter an amount.`);
		}
		setErr(null);
		try {
			if (isEdit) {
				await updatePo({ name: editId, podata: buildPayload(submit) });
				navigate('/purchases/' + editId);
			} else {
				const result = await createPo({ podata: buildPayload(submit) });
				navigate('/purchases/' + result.message.name);
			}
		} catch (e) {
			setErr(parseServerError(e));
		}
	}

	if (ctxResult.error) {
		return (
			<main className="tight">
				<div className="eyebrow">Buying · New purchase order</div>
				<h1>
					New purchase <em>order</em>
				</h1>
				<div style={{ marginTop: 22 }}>
					<Card>
						<div className="ferr" style={{ padding: '18px 20px' }}>
							You don't have permission to create purchase orders. {parseServerError(ctxResult.error)}
						</div>
					</Card>
				</div>
			</main>
		);
	}

	const masterOptions: Record<OptionSource, string[]> = {
		currencies: [],
		incoterms: [],
		uoms: ctx?.uoms ?? [],
		countries: ctx?.countries ?? [],
		itemTaxTemplates: ctx?.item_tax_templates ?? [],
		...STATIC_OPTIONS,
	};

	const supplierOptions = (ctx?.suppliers ?? []).map((s) => ({ value: s.name, label: s.supplier_name }));
	const soOptions = (ctx?.sales_orders ?? []).map((s) => ({
		value: s.name,
		label: s.name,
		sub: s.customer_name,
	}));
	const freeItems = (ctx?.items ?? []).map((i) => ({ value: i.name, label: i.item_name, sub: i.stock_uom }));
	const taxTemplateOptions = (ctx?.taxes_templates ?? []).map((t) => ({ value: t.name }));
	const termsOptions = (ctx?.terms_templates ?? []).map((t) => ({ value: t }));
	const paymentTermsOptions = (ctx?.payment_terms_templates ?? []).map((t) => ({ value: t }));

	const totals = preview;
	// only the lines that actually bear tax — keeps the per-item breakup honest
	const taxedItems = totals?.by_item.filter((b) => b.tax > 0) ?? [];

	return (
		<main className="tight">
			<div className="eyebrow">Buying · {isEdit ? 'Edit purchase order' : 'New purchase order'}</div>
			<div className="crumb" style={{ marginTop: 6 }}>
				<Link to="/purchases">Purchases</Link> /{' '}
				{isEdit ? <span className="data">{editId}</span> : <span>New</span>}
			</div>
			<div className="titlebar">
				<span className="who">{isEdit ? `Edit ${editId}` : 'New purchase order'}</span>
				<span className="spacer" />
			</div>

			<div className="grid detail" style={{ marginTop: 14 }}>
				<Card accent>
					<CHead icon="cube" title="Purchase order" count={ctx?.company} />
					<div className="formgrid">
						<Field label="Supplier" required>
							<SearchSelect
								value={supplier}
								onChange={onSupplier}
								options={supplierOptions}
								onCreate={() => setQuickCreate('supplier')}
								createLabel="New supplier"
							/>
						</Field>
						{/* both schemes are always shown; only the one applicable to the
						    selected supplier is enabled — more intuitive than swapping (#9) */}
						<div style={{ paddingTop: 22, display: 'grid', gap: 8 }}>
							<div>
								<CheckInput
									checked={mes}
									disabled={supplierIsForeign || !supplier}
									onChange={setMes}
									label="Merchant export scheme (0.1% GST)"
								/>
								{(supplierIsForeign || !supplier) && (
									<div className="c2" style={{ marginLeft: 26, marginTop: 2 }}>
										For domestic GST-registered suppliers
									</div>
								)}
							</div>
							<div>
								<CheckInput
									checked={merchanting}
									disabled={!supplierIsForeign}
									onChange={setMerchanting}
									label="Third-country / merchanting trade"
								/>
								{!supplierIsForeign && (
									<div className="c2" style={{ marginLeft: 26, marginTop: 2 }}>
										Available for overseas suppliers
									</div>
								)}
							</div>
						</div>
						<Field label="Currency">
							<SearchSelect
								value={currency}
								onChange={setCurrency}
								options={(ctx?.currencies ?? []).map((c) => ({ value: c }))}
								placeholder="Currency…"
							/>
						</Field>
						{!isCompanyCurrency ? (
							<Field label={`Exchange rate → ${companyCurrency}`} hint="Day rate suggested; editable">
								<TextInput
									type="number"
									value={convRate}
									onChange={(v) => {
										setConvRate(v);
										setRateTouched(true);
									}}
								/>
							</Field>
						) : (
							<div />
						)}
						<Field label="Order date">
							<TextInput type="date" value={orderDate} onChange={setOrderDate} />
						</Field>
						<Field label="Required by" hint="Defaults to 15 days out">
							<TextInput type="date" value={requiredBy} onChange={setRequiredBy} />
						</Field>
					</div>
					{merchanting && (
						<div className="c2" style={{ padding: '0 18px 12px' }}>
							Merchanting: goods ship directly from the overseas supplier to the buyer (never
							entering India) — 0 GST, and the order must be linked to its sales order below.
						</div>
					)}

					{/* ---- items ---- */}
					<div className="reqhead" style={{ borderTop: '1px solid var(--hairline)', gridTemplateColumns: GRID }}>
						<span>Item</span>
						<span>For SO</span>
						<span>Qty</span>
						<span>UOM</span>
						<span>Rate{currency ? ` (${currency})` : ''}</span>
						<span style={{ textAlign: 'right' }}>Amount</span>
						<span />
					</div>
					{rows.length === 0 && (
						<EmptyMsg title="No items yet" text="Pull lines from a sales order below, or add a free item." />
					)}
					{rows.map((r, i) => {
						const rem = liveRemaining(r.so_detail);
						const open = expanded.has(i) || !!r.specification || !!r.packaging;
						return (
							<Fragment key={`${r.item_code}-${r.so_detail ?? i}`}>
								<div className="reqrow" style={{ gridTemplateColumns: GRID }}>
									<span>
										<span className="c1" style={{ display: 'block' }}>
											{r.item_name}
										</span>
										<button
											type="button"
											onClick={() => toggleExpand(i)}
											style={{
												background: 'none',
												border: 0,
												padding: 0,
												marginTop: 2,
												cursor: 'pointer',
												color: 'var(--brand-iris, var(--text-link))',
												font: 'inherit',
												fontSize: 11,
											}}
										>
											{open ? '▾' : '▸'} Spec &amp; packing{r.specification || r.packaging ? ' ✓' : ''}
										</button>
									</span>
									{r.sales_order ? (
										<span style={{ alignSelf: 'center' }}>
											<span className="id id-sm">{r.sales_order}</span>
											{rem !== null && (
												<span className="c2" style={{ display: 'block' }}>
													{rem < 0
														? `${Math.abs(rem)} ${r.uom ?? ''} over SO`
														: `${rem} ${r.uom ?? ''} left on SO`}
												</span>
											)}
										</span>
									) : (
										<span className="dim" style={{ alignSelf: 'center' }}>
											—
										</span>
									)}
									<TextInput type="number" value={r.qty} onChange={(v) => setRow(i, { qty: v })} />
									<span className="dim" style={{ alignSelf: 'center' }}>
										{r.uom || '—'}
									</span>
									<TextInput type="number" value={r.rate} onChange={(v) => setRow(i, { rate: v })} />
									<span className="num" style={{ textAlign: 'right', alignSelf: 'center' }}>
										{fmtMoney((Number(r.qty) || 0) * (Number(r.rate) || 0), currency)}
									</span>
									<button
										type="button"
										className="xbtn"
										aria-label={`Remove ${r.item_name}`}
										onClick={() => removeRow(i)}
									>
										<Icon name="close" size={14} />
									</button>
								</div>
								{open && (
									<div style={{ padding: '0 18px 12px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
										<Field label="Specification">
											<TextArea
												value={r.specification}
												onChange={(v) => setRow(i, { specification: v })}
												rows={2}
												placeholder="Grade, purity, particle size, pharmacopoeia…"
											/>
										</Field>
										<Field label="Packaging required">
											<TextArea
												value={r.packaging}
												onChange={(v) => setRow(i, { packaging: v })}
												rows={2}
												placeholder="e.g. 25 kg HDPE drums, double LDPE liner"
											/>
										</Field>
									</div>
								)}
							</Fragment>
						);
					})}

					<div style={{ padding: '12px 18px', display: 'grid', gap: 10 }}>
						<div style={{ display: 'flex', gap: 10, alignItems: 'flex-end', flexWrap: 'wrap' }}>
							<div className="field" style={{ minWidth: 260, flex: 1 }}>
								<span className="flabel">Pull lines from a sales order</span>
								<SearchSelect value={soPick} onChange={setSoPick} options={soOptions} placeholder="Search sales orders…" />
							</div>
							{soPick &&
								(pickableLines.length > 0 ? (
									<div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
										{pickableLines.map((l) => (
											<button type="button" key={l.so_detail} className="btn" onClick={() => addSoLine(l.so_detail)}>
												<Icon name="plus" size={14} /> {l.item_name} · {l.remaining} {l.uom ?? ''}
											</button>
										))}
									</div>
								) : (
									<span className="dim" style={{ paddingBottom: 11 }}>
										{soLines.isLoading ? 'Loading…' : 'Nothing left to order on this SO'}
									</span>
								))}
						</div>
						<div className="field" style={{ maxWidth: 340 }}>
							<span className="flabel">Add a free item (no SO link)</span>
							<SearchSelect
								value=""
								onChange={(v) => void addFreeRow(v)}
								options={freeItems}
								placeholder="Search items…"
								onCreate={() => setQuickCreate('item')}
								createLabel="New item master"
							/>
						</div>
					</div>

					{/* ---- taxes & charges (after items, per ERPNext) ---- */}
					<div className="docgrp">Taxes &amp; charges</div>
					<div className="formgrid" style={{ paddingBottom: 4 }}>
						<Field label="Taxes template" hint="GST autofills from the item/HSN tax setup">
							<SearchSelect
								value={taxesTemplate}
								onChange={setTaxesTemplate}
								options={taxTemplateOptions}
								placeholder="Search tax templates…"
							/>
						</Field>
					</div>
					{charges.length > 0 && (
						<div className="reqhead" style={{ gridTemplateColumns: CHARGE_GRID }}>
							<span>Charge</span>
							<span>Amount</span>
							<span />
						</div>
					)}
					{charges.map((c, i) => (
						<div className="reqrow" key={i} style={{ gridTemplateColumns: CHARGE_GRID }}>
							<TextInput value={c.description} onChange={(v) => setCharge(i, { description: v })} placeholder="e.g. Cartage to CFS" />
							<TextInput type="number" value={c.amount} onChange={(v) => setCharge(i, { amount: v })} />
							<button
								type="button"
								className="xbtn"
								aria-label="Remove charge"
								onClick={() => setCharges((cs) => cs.filter((_, idx) => idx !== i))}
							>
								<Icon name="close" size={14} />
							</button>
						</div>
					))}
					<div style={{ padding: '8px 18px 12px' }}>
						<button
							type="button"
							className="btn"
							onClick={() => setCharges((cs) => [...cs, { description: '', account_head: '', amount: '' }])}
						>
							<Icon name="plus" size={15} /> Add charge (cartage, freight…)
						</button>
						{charges.length > 0 && (
							<div className="c2" style={{ marginTop: 6 }}>
								Charges post to the default expense account automatically — set it in Settings.
							</div>
						)}
					</div>

					{/* ---- terms (after items & taxes, per ERPNext) ---- */}
					<div className="docgrp">Terms &amp; conditions</div>
					<div className="formgrid">
						<Field label="Payment terms template" hint="Payment templates — manage in Settings">
							<SearchSelect
								value={ptName}
								onChange={(v) => void onPaymentTemplate(v)}
								options={paymentTermsOptions}
								placeholder="Search payment templates…"
								onCreate={() => setQuickCreate('payment')}
								createLabel="New payment terms template"
							/>
						</Field>
						<div className="span2">
							<Field label="Payment terms" hint="Picked from a template or typed; this text prints">
								<TextArea value={paymentTerms} onChange={setPaymentTerms} rows={2} placeholder="e.g. 30% advance, balance against goods receipt…" />
							</Field>
						</div>
						<Field label="Terms template" hint="Manage templates in Settings">
							<SearchSelect
								value={tcName}
								onChange={(v) => void onTemplate(v)}
								options={termsOptions}
								placeholder="Search templates…"
								onCreate={() => setQuickCreate('terms')}
								createLabel="New terms template"
							/>
						</Field>
						<div className="span2">
							<Field label="Terms text">
								<TextArea value={terms} onChange={setTerms} rows={4} placeholder="Delivery, quality, jurisdiction and documentation conditions…" />
							</Field>
						</div>
					</div>

					<div className="formfoot">
						{err && <span className="ferr">{err}</span>}
						<span className="spacer" />
						<span className="num" style={{ fontSize: 15 }}>
							{fmtMoney(totals?.grand_total ?? subtotal, currency)}
						</span>
						<button type="button" className="btn" disabled={busy} onClick={() => void onSave(false)}>
							{busy ? 'Saving…' : 'Save draft'}
						</button>
						<button type="button" className="btn primary" disabled={busy} onClick={() => void onSave(true)}>
							<Icon name="check" size={15} />
							{busy ? 'Saving…' : isEdit ? 'Save & submit' : 'Create & submit'}
						</button>
					</div>
				</Card>

				<div className="stack">
					<Card accent>
						<CHead icon="banknote" title="Totals" count={totals ? 'computed' : undefined} />
						<Facts
							rows={[
								{ k: 'Net total', v: fmtMoney(totals?.net_total ?? subtotal, currency), data: true },
								...(totals?.taxes ?? []).map((tax) => ({
									k: tax.rate ? `${tax.description} @ ${tax.rate}%` : tax.description,
									v: fmtMoney(tax.tax_amount, currency),
									data: true,
								})),
								{ k: 'Grand total', v: fmtMoney(totals?.grand_total ?? subtotal, currency), data: true },
							]}
						/>
						{!totals && (
							<div className="c2" style={{ padding: '10px 18px 14px' }}>
								Taxes compute automatically once the supplier, items and rates are filled — using
								the same engine as the ledger.
							</div>
						)}
					</Card>
					{taxedItems.length > 0 && (
						<Card>
							<CHead icon="banknote" title="Tax by item" count={`${taxedItems.length}`} />
							<table>
								<thead>
									<tr>
										<th>Item</th>
										<th>Taxable</th>
										<th>Tax</th>
									</tr>
								</thead>
								<tbody>
									{taxedItems.map((b) => (
										<tr key={b.item_code}>
											<td>{b.item_name || b.item_code}</td>
											<td className="num">{fmtMoney(b.net, currency)}</td>
											<td className="num">{fmtMoney(b.tax, currency)}</td>
										</tr>
									))}
								</tbody>
							</table>
						</Card>
					)}
					<Card>
						<CHead icon="truck" title="Drop ship" />
						<div className="empty" style={{ padding: '18px 20px', alignItems: 'flex-start', textAlign: 'left' }}>
							<div className="t2">
								Lines pulled from a sales order ship directly from this supplier to the port and
								stay connected to the exact deal line. Free items are a plain purchase with no
								deal link.
							</div>
						</div>
					</Card>
				</div>
			</div>

			{quickCreate !== null && (
				<MasterModal
					def={
						quickCreate === 'supplier'
							? SUPPLIER_DEF
							: quickCreate === 'item'
								? ITEM_DEF
								: quickCreate === 'payment'
									? PAYMENT_DEF
									: TC_DEF
					}
					options={masterOptions}
					record={null}
					defaults={quickCreate === 'terms' || quickCreate === 'payment' ? { buying: true } : undefined}
					onClose={() => setQuickCreate(null)}
					onSaved={(name) => {
						const which = quickCreate;
						setQuickCreate(null);
						void ctxResult.mutate();
						if (which === 'supplier') onSupplier(name);
						else if (which === 'item') void addFreeRow(name);
						else if (which === 'payment') void onPaymentTemplate(name);
						else void onTemplate(name);
					}}
				/>
			)}

			<footer>
				<b>ExportFlow</b> · DUX Digitech
			</footer>
		</main>
	);
}
