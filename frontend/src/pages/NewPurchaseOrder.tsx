import { useEffect, useMemo, useRef, useState } from 'react';
import { useFrappeGetCall, useFrappePostCall } from 'frappe-react-sdk';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Icon } from '@/components/Icon';
import { MasterModal } from '@/components/MasterModal';
import { CheckInput, Field, SearchSelect, TextArea, TextInput } from '@/components/form';
import { Card, CHead, EmptyMsg, Facts } from '@/components/ui';
import {
	API,
	parseServerError,
	type NewPOContext,
	type POTotals,
	type SOProcurement,
} from '@/lib/api';
import { fmtMoney } from '@/lib/format';
import { GRADE_OPTIONS, MASTERS, PORT_MODES, type OptionSource } from '@/lib/masters';

const SUPPLIER_DEF = MASTERS.find((m) => m.doctype === 'Supplier')!;
const ITEM_DEF = MASTERS.find((m) => m.doctype === 'Item')!;
const TC_DEF = MASTERS.find((m) => m.doctype === 'Terms and Conditions')!;

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
}

interface ChargeRow {
	description: string;
	account_head: string;
	amount: string;
}

const GRID = '1.8fr 1fr 90px 70px 120px 120px 34px';
const CHARGE_GRID = '1.6fr 1.6fr 130px 34px';

function todayISO(): string {
	const d = new Date();
	return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function NewPurchaseOrder() {
	const navigate = useNavigate();
	const [searchParams] = useSearchParams();

	const ctxResult = useFrappeGetCall<{ message: NewPOContext }>(API.newPoContext, undefined);
	const ctx = ctxResult.data?.message;

	const [supplier, setSupplier] = useState('');
	const [mes, setMes] = useState(false);
	const [orderDate, setOrderDate] = useState(todayISO());
	const [requiredBy, setRequiredBy] = useState('');
	const [tcName, setTcName] = useState('');
	const [terms, setTerms] = useState('');
	const [taxesTemplate, setTaxesTemplate] = useState('');
	const [taxDefaulted, setTaxDefaulted] = useState(false);
	const [charges, setCharges] = useState<ChargeRow[]>([]);
	const [rows, setRows] = useState<PORow[]>([]);
	const [soPick, setSoPick] = useState(searchParams.get('so') ?? '');
	const [err, setErr] = useState<string | null>(null);
	const [quickCreate, setQuickCreate] = useState<'supplier' | 'item' | 'terms' | null>(null);
	const [preview, setPreview] = useState<POTotals | null>(null);

	// default the taxes template once the context arrives
	useEffect(() => {
		if (!ctx || taxDefaulted) return;
		const def = ctx.taxes_templates.find((t) => t.is_default);
		if (def) setTaxesTemplate(def.name);
		setTaxDefaulted(true);
	}, [ctx, taxDefaulted]);

	// lines of the picked SO, to pull into the order
	const soLines = useFrappeGetCall<{ message: SOProcurement }>(
		API.soProcurement,
		{ sales_order: soPick },
		soPick ? undefined : null,
	);
	const { call: fetchTerms } = useFrappePostCall<{ message: string }>(API.termsText);
	const { call: fetchItemInfo } = useFrappePostCall<{ message: { stock_uom: string; item_name: string } }>(
		API.itemInfo,
	);
	const { call: previewPo } = useFrappePostCall<{ message: POTotals }>(API.previewPo);
	const { call: createPo, loading: saving } = useFrappePostCall<{
		message: { name: string; docstatus: number };
	}>(API.createPoDraft);

	function buildPayload(submit: boolean) {
		return {
			supplier,
			transaction_date: orderDate,
			schedule_date: requiredBy || null,
			merchant_export_scheme: mes ? 1 : 0,
			taxes_template: taxesTemplate || null,
			extra_charges: charges
				.filter((c) => c.account_head && Number(c.amount) > 0)
				.map((c) => ({
					description: c.description || c.account_head,
					account_head: c.account_head,
					amount: Number(c.amount),
				})),
			tc_name: tcName || null,
			terms,
			submit: submit ? 1 : 0,
			items: rows.map((r) => ({
				item_code: r.item_code,
				qty: Number(r.qty),
				rate: Number(r.rate),
				sales_order: r.sales_order,
				so_detail: r.so_detail,
			})),
		};
	}

	// live tax preview through the real ERPNext engine, debounced
	const previewKey = JSON.stringify({
		supplier,
		taxesTemplate,
		charges,
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
		setMes(!!s?.default_merchant_export_scheme);
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

	const addedDetails = new Set(rows.map((r) => r.so_detail).filter(Boolean));
	const pickableLines = (soLines.data?.message.lines ?? []).filter(
		(l) => l.remaining > 0 && !addedDetails.has(l.so_detail),
	);

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
	const currency = ctx?.company_currency;

	async function onSave(submit: boolean) {
		if (!supplier) return setErr('Pick the supplier.');
		if (rows.length === 0) return setErr('Add at least one item.');
		for (const [i, r] of rows.entries()) {
			if (!r.qty || Number(r.qty) <= 0) return setErr(`Row ${i + 1}: quantity is required.`);
			if (r.max_qty !== null && Number(r.qty) > r.max_qty + 1e-6)
				return setErr(`Row ${i + 1}: only ${r.max_qty} remains unordered on ${r.sales_order}.`);
			if (!r.rate || Number(r.rate) <= 0) return setErr(`Row ${i + 1}: buying rate is required.`);
		}
		for (const [i, c] of charges.entries()) {
			if ((c.amount && Number(c.amount) > 0) !== !!c.account_head)
				return setErr(`Charge ${i + 1}: needs both an account and an amount.`);
		}
		setErr(null);
		try {
			const result = await createPo({ podata: buildPayload(submit) });
			navigate('/purchases/' + result.message.name);
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
		grades: GRADE_OPTIONS,
		portModes: PORT_MODES,
	};

	const supplierOptions = (ctx?.suppliers ?? []).map((s) => ({ value: s.name, label: s.supplier_name }));
	const soOptions = (ctx?.sales_orders ?? []).map((s) => ({
		value: s.name,
		label: s.name,
		sub: s.customer_name,
	}));
	const freeItems = (ctx?.items ?? []).map((i) => ({ value: i.name, label: i.item_name, sub: i.stock_uom }));
	const accountOptions = (ctx?.accounts ?? []).map((a) => ({ value: a.name, label: a.account_name }));
	const taxTemplateOptions = (ctx?.taxes_templates ?? []).map((t) => ({ value: t.name }));
	const termsOptions = (ctx?.terms_templates ?? []).map((t) => ({ value: t }));

	const totals = preview;

	return (
		<main className="tight">
			<div className="eyebrow">Buying · New purchase order</div>
			<div className="crumb" style={{ marginTop: 6 }}>
				<Link to="/purchases">Purchases</Link> / <span>New</span>
			</div>
			<div className="titlebar">
				<span className="who">New purchase order</span>
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
						<div style={{ paddingTop: 22 }}>
							<CheckInput checked={mes} onChange={setMes} label="Merchant export scheme (0.1% GST)" />
						</div>
						<Field label="Order date">
							<TextInput type="date" value={orderDate} onChange={setOrderDate} />
						</Field>
						<Field label="Required by" hint="Defaults to 15 days out">
							<TextInput type="date" value={requiredBy} onChange={setRequiredBy} />
						</Field>
					</div>

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
					{rows.map((r, i) => (
						<div className="reqrow" key={`${r.item_code}-${r.so_detail ?? i}`} style={{ gridTemplateColumns: GRID }}>
							<span>
								<span className="c1" style={{ display: 'block' }}>
									{r.item_name}
								</span>
							</span>
							{r.sales_order ? (
								<span className="id id-sm" style={{ alignSelf: 'center' }}>
									{r.sales_order}
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
								onClick={() => setRows((rs) => rs.filter((_, idx) => idx !== i))}
							>
								<Icon name="close" size={14} />
							</button>
						</div>
					))}

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
							<span>Expense account</span>
							<span>Amount</span>
							<span />
						</div>
					)}
					{charges.map((c, i) => (
						<div className="reqrow" key={i} style={{ gridTemplateColumns: CHARGE_GRID }}>
							<TextInput value={c.description} onChange={(v) => setCharge(i, { description: v })} placeholder="e.g. Cartage to CFS" />
							<SearchSelect
								value={c.account_head}
								onChange={(v) => setCharge(i, { account_head: v })}
								options={accountOptions}
								placeholder="Search accounts…"
							/>
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
					</div>

					{/* ---- terms (after items & taxes, per ERPNext) ---- */}
					<div className="docgrp">Terms &amp; conditions</div>
					<div className="formgrid">
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
								<TextArea value={terms} onChange={setTerms} rows={4} placeholder="Payment, delivery, quality and documentation conditions…" />
							</Field>
						</div>
					</div>

					<div className="formfoot">
						{err && <span className="ferr">{err}</span>}
						<span className="spacer" />
						<span className="num" style={{ fontSize: 15 }}>
							{fmtMoney(totals?.grand_total ?? subtotal, currency)}
						</span>
						<button type="button" className="btn" disabled={saving} onClick={() => void onSave(false)}>
							Save draft
						</button>
						<button type="button" className="btn primary" disabled={saving} onClick={() => void onSave(true)}>
							<Icon name="check" size={15} />
							{saving ? 'Saving…' : 'Create & submit'}
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
					def={quickCreate === 'supplier' ? SUPPLIER_DEF : quickCreate === 'item' ? ITEM_DEF : TC_DEF}
					options={masterOptions}
					record={null}
					onClose={() => setQuickCreate(null)}
					onSaved={(name) => {
						const which = quickCreate;
						setQuickCreate(null);
						void ctxResult.mutate();
						if (which === 'supplier') onSupplier(name);
						else if (which === 'item') void addFreeRow(name);
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
