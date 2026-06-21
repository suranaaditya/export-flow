import { useEffect, useMemo, useRef, useState } from 'react';
import { useFrappeGetCall, useFrappePostCall } from 'frappe-react-sdk';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Icon } from '@/components/Icon';
import { MasterModal } from '@/components/MasterModal';
import { Field, SearchSelect, TextArea, TextInput } from '@/components/form';
import { Card, CHead, Facts } from '@/components/ui';
import { API, parseServerError, type ItemInfo, type NewSOContext, type SalesOrderForEdit } from '@/lib/api';
import { fmtMoney } from '@/lib/format';
import { MASTERS, STATIC_OPTIONS, type OptionSource } from '@/lib/masters';

const CUSTOMER_DEF = MASTERS.find((m) => m.doctype === 'Customer')!;
const ITEM_DEF = MASTERS.find((m) => m.doctype === 'Item')!;
const TC_DEF = MASTERS.find((m) => m.doctype === 'Terms and Conditions')!;

interface DealRow {
	item_code: string;
	qty: string;
	rate: string;
	uom: string;
}

const EMPTY_ROW: DealRow = { item_code: '', qty: '', rate: '', uom: '' };

function todayISO(): string {
	const d = new Date();
	return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function NewSalesOrder() {
	const navigate = useNavigate();
	const { id: editId } = useParams<{ id?: string }>();
	const isEdit = !!editId;

	const ctxResult = useFrappeGetCall<{ message: NewSOContext }>(API.newSoContext, undefined);
	const ctx = ctxResult.data?.message;

	const editResult = useFrappeGetCall<{ message: SalesOrderForEdit }>(
		API.soForEdit,
		{ name: editId },
		isEdit ? undefined : null,
	);

	const { call: fetchItemInfo } = useFrappePostCall<{ message: ItemInfo }>(API.itemInfo);
	const { call: fetchTerms } = useFrappePostCall<{ message: string }>(API.termsText);
	const { call: createSo, loading: saving } = useFrappePostCall<{
		message: { name: string; docstatus: number };
	}>(API.createSo);
	const { call: updateSo, loading: updating } = useFrappePostCall<{
		message: { name: string; docstatus: number };
	}>(API.updateSo);
	const busy = saving || updating;

	const [customer, setCustomer] = useState('');
	const [orderDate, setOrderDate] = useState(todayISO());
	const [deliveryDate, setDeliveryDate] = useState('');
	const [currency, setCurrency] = useState('');
	const [rate, setRate] = useState('');
	const [rateTouched, setRateTouched] = useState(false);
	const [incoterm, setIncoterm] = useState('');
	const [namedPlace, setNamedPlace] = useState('');
	const [paymentTerms, setPaymentTerms] = useState('');
	const [tcName, setTcName] = useState('');
	const [tcText, setTcText] = useState('');
	const [rows, setRows] = useState<DealRow[]>([{ ...EMPTY_ROW }]);
	const [err, setErr] = useState<string | null>(null);
	const [quickCreate, setQuickCreate] = useState<'customer' | 'item' | 'terms' | null>(null);

	// prefill from the existing order when editing (seed exactly once)
	const seeded = useRef(false);
	const seededCurrency = useRef<string | null>(null);
	const seededRate = useRef<string>('');
	useEffect(() => {
		if (!isEdit || seeded.current) return;
		const d = editResult.data?.message;
		if (!d) return;
		setCustomer(d.customer ?? '');
		setOrderDate(d.transaction_date ?? todayISO());
		setDeliveryDate(d.delivery_date ?? '');
		seededCurrency.current = d.currency ?? '';
		seededRate.current = d.conversion_rate != null ? String(d.conversion_rate) : '';
		setCurrency(d.currency ?? '');
		setRate(seededRate.current);
		setRateTouched(true); // keep the order's stored rate, don't auto-suggest over it
		setIncoterm(d.incoterm ?? '');
		setNamedPlace(d.named_place ?? '');
		setPaymentTerms(d.payment_terms_narrative ?? '');
		setTcName(d.tc_name ?? '');
		setTcText(d.terms ?? '');
		setRows(
			(d.items ?? []).length
				? d.items.map((it) => ({
						item_code: it.item_code,
						qty: String(it.qty),
						rate: String(it.rate),
						uom: it.uom ?? '',
					}))
				: [{ ...EMPTY_ROW }],
		);
		seeded.current = true;
	}, [isEdit, editResult.data]);

	// customer defaults flow into the deal header — never on an edit prefill
	useEffect(() => {
		if (!ctx || !customer || isEdit) return;
		const c = ctx.customers.find((x) => x.name === customer);
		if (!c) return;
		if (c.default_currency) setCurrency(c.default_currency);
		if (c.default_incoterm) setIncoterm(c.default_incoterm);
	}, [customer, ctx, isEdit]);

	// suggest the day's exchange rate whenever the currency changes
	const rateResult = useFrappeGetCall<{ message: number }>(
		API.exchangeRate,
		{ currency },
		currency ? undefined : null,
	);
	// a deliberate currency change re-arms the day-rate suggestion; returning to
	// the edited order's booked currency restores its stored rate instead of
	// letting the day-rate clobber it
	useEffect(() => {
		if (isEdit && seededCurrency.current !== null && currency === seededCurrency.current) {
			setRate(seededRate.current);
			setRateTouched(true);
			return;
		}
		setRateTouched(false);
	}, [currency, isEdit]);
	useEffect(() => {
		const suggested = rateResult.data?.message;
		if (!rateTouched && suggested && suggested > 0) setRate(String(suggested));
	}, [rateResult.data, rateTouched]);

	const isCompanyCurrency = !!ctx && currency === ctx.company_currency;

	const setRow = (i: number, patch: Partial<DealRow>) =>
		setRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));

	async function onPickItem(i: number, itemCode: string) {
		// UOM comes straight from the already-loaded item list — no wait
		const listed = ctx?.items.find((x) => x.name === itemCode);
		setRow(i, { item_code: itemCode, uom: listed?.stock_uom ?? '' });
		if (!itemCode) return;
		try {
			const info = (await fetchItemInfo({ item_code: itemCode })).message;
			setRow(i, {
				item_code: itemCode,
				uom: info.stock_uom ?? listed?.stock_uom ?? '',
				rate: rows[i].rate || (info.standard_rate ? String(info.standard_rate) : ''),
			});
		} catch {
			// row fill is best-effort; the user can complete it manually
		}
	}

	async function onTemplate(v: string) {
		setTcName(v);
		if (!v) return;
		try {
			const text = (await fetchTerms({ template: v })).message;
			setTcText(text.replace(/<[^>]*>/g, ''));
		} catch {
			// template text is a convenience — leave the field as typed
		}
	}

	const total = useMemo(
		() => rows.reduce((sum, r) => sum + (Number(r.qty) || 0) * (Number(r.rate) || 0), 0),
		[rows],
	);

	async function onSave(submit: boolean) {
		const kept = rows.filter((r) => r.item_code || r.qty || r.rate);
		if (!customer) return setErr('Pick the customer.');
		if (!deliveryDate) return setErr('Set the expected delivery date.');
		if (!currency) return setErr('Pick the deal currency.');
		if (!isCompanyCurrency && (!rate || Number(rate) <= 0)) return setErr('Set the exchange rate.');
		if (kept.length === 0) return setErr('Add at least one item.');
		for (const [i, r] of kept.entries()) {
			if (!r.item_code) return setErr(`Item row ${i + 1}: pick the item.`);
			if (!r.qty || Number(r.qty) <= 0) return setErr(`Item row ${i + 1}: quantity is required.`);
			if (!r.rate || Number(r.rate) <= 0) return setErr(`Item row ${i + 1}: rate is required.`);
		}
		setErr(null);
		const deal = {
			customer,
			transaction_date: orderDate,
			delivery_date: deliveryDate,
			currency,
			conversion_rate: Number(rate) || 1,
			incoterm: incoterm || null,
			named_place: namedPlace,
			payment_terms_narrative: paymentTerms,
			tc_name: tcName || null,
			terms: tcText,
			submit: submit ? 1 : 0,
			items: kept.map((r) => ({
				item_code: r.item_code,
				qty: Number(r.qty),
				rate: Number(r.rate),
			})),
		};
		try {
			if (isEdit) {
				await updateSo({ name: editId, deal });
				navigate('/sales-orders/' + editId);
			} else {
				const result = await createSo({ deal });
				navigate('/sales-orders/' + result.message.name);
			}
		} catch (e) {
			setErr(parseServerError(e));
		}
	}

	if (ctxResult.error) {
		return (
			<main className="tight">
				<div className="eyebrow">Selling · New deal</div>
				<h1>
					New export <em>deal</em>
				</h1>
				<div style={{ marginTop: 22 }}>
					<Card>
						<div className="ferr" style={{ padding: '18px 20px' }}>
							You don't have permission to create sales orders. {parseServerError(ctxResult.error)}
						</div>
					</Card>
				</div>
			</main>
		);
	}

	const masterOptions: Record<OptionSource, string[]> = {
		currencies: ctx?.currencies ?? [],
		incoterms: ctx?.incoterms ?? [],
		uoms: ctx?.uoms ?? [],
		countries: ctx?.countries ?? [],
		itemTaxTemplates: ctx?.item_tax_templates ?? [],
		...STATIC_OPTIONS,
	};

	const customers = (ctx?.customers ?? []).map((c) => ({ value: c.name, label: c.customer_name }));
	const items = (ctx?.items ?? []).map((i) => ({
		value: i.name,
		label: i.item_name,
		sub: [i.pharmacopoeia_grade, i.stock_uom].filter(Boolean).join(' · ') || undefined,
	}));
	const termsOptions = (ctx?.terms_templates ?? []).map((t) => ({ value: t }));

	return (
		<main className="tight">
			<div className="eyebrow">Selling · {isEdit ? 'Edit deal' : 'New deal'}</div>
			<div className="crumb" style={{ marginTop: 6 }}>
				<Link to="/sales-orders">Sales orders</Link> /{' '}
				{isEdit ? <span className="data">{editId}</span> : <span>New</span>}
			</div>
			<div className="titlebar">
				<span className="who">{isEdit ? `Edit ${editId}` : 'New export deal'}</span>
				<span className="spacer" />
			</div>

			<div className="grid detail" style={{ marginTop: 14 }}>
				<Card accent>
					<CHead icon="file-text" title="Deal" count={ctx ? ctx.company : undefined} />
					<div className="formgrid">
						<Field label="Customer" required>
							<SearchSelect
								value={customer}
								onChange={setCustomer}
								options={customers}
								placeholder="Search customers…"
								onCreate={() => setQuickCreate('customer')}
								createLabel="New customer"
							/>
						</Field>
						<Field label="Order date">
							<TextInput type="date" value={orderDate} onChange={setOrderDate} />
						</Field>
						<Field label="Expected delivery" required>
							<TextInput type="date" value={deliveryDate} onChange={setDeliveryDate} />
						</Field>
						<Field label="Currency" required>
							<SearchSelect value={currency} onChange={setCurrency} options={(ctx?.currencies ?? []).map((c) => ({ value: c }))} placeholder="Search currencies…" />
						</Field>
						<Field
							label="Exchange rate"
							hint={
								isCompanyCurrency
									? 'Company currency — rate is 1'
									: ctx
										? `${currency || 'Deal currency'} → ${ctx.company_currency}`
										: undefined
							}
						>
							<TextInput
								type="number"
								mono
								value={isCompanyCurrency ? '1' : rate}
								disabled={isCompanyCurrency}
								onChange={(v) => {
									setRateTouched(true);
									setRate(v);
								}}
							/>
						</Field>
						<Field label="Incoterm">
							<SearchSelect value={incoterm} onChange={setIncoterm} options={(ctx?.incoterms ?? []).map((i) => ({ value: i }))} placeholder="Search incoterms…" />
						</Field>
						<Field label="Delivery port" hint="Pick a port or type any place">
							<TextInput value={namedPlace} onChange={setNamedPlace} listId="ef-ports" placeholder="e.g. Jebel Ali" />
							<datalist id="ef-ports">
								{(ctx?.ports ?? []).map((p) => (
									<option key={p.name} value={p.unlocode ? `${p.name} · ${p.unlocode}` : p.name}>
										{[p.city, p.country, p.mode].filter(Boolean).join(' · ')}
									</option>
								))}
							</datalist>
						</Field>
						<div className="span2">
							<Field label="Payment terms" hint="As negotiated, e.g. 30% advance, 70% against B/L copy">
								<TextArea value={paymentTerms} onChange={setPaymentTerms} rows={2} />
							</Field>
						</div>
						<Field label="Terms template" hint="Sales templates — manage in Settings">
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
							<Field label="Terms &amp; conditions text">
								<TextArea value={tcText} onChange={setTcText} rows={3} placeholder="Boilerplate payment, delivery, quality and documentation conditions…" />
							</Field>
						</div>
					</div>

					<div className="reqhead" style={{ borderTop: '1px solid var(--hairline)', gridTemplateColumns: '2fr 110px 80px 130px 130px 34px' }}>
						<span>Item</span>
						<span>Qty</span>
						<span>UOM</span>
						<span>Rate</span>
						<span style={{ textAlign: 'right' }}>Amount</span>
						<span />
					</div>
					{rows.map((r, i) => (
						<div className="reqrow" key={i} style={{ gridTemplateColumns: '2fr 110px 80px 130px 130px 34px' }}>
							<SearchSelect value={r.item_code} onChange={(v) => void onPickItem(i, v)} options={items} placeholder="Search items…" onCreate={() => setQuickCreate('item')} createLabel="New item master" />
							<TextInput type="number" value={r.qty} onChange={(v) => setRow(i, { qty: v })} />
							<span className="dim" style={{ alignSelf: 'center' }}>{r.uom || '—'}</span>
							<TextInput type="number" value={r.rate} onChange={(v) => setRow(i, { rate: v })} />
							<span className="num" style={{ textAlign: 'right' }}>
								{fmtMoney((Number(r.qty) || 0) * (Number(r.rate) || 0), currency || undefined)}
							</span>
							<button
								type="button"
								className="xbtn"
								aria-label="Remove item"
								onClick={() => setRows((rs) => (rs.length > 1 ? rs.filter((_, idx) => idx !== i) : rs))}
							>
								<Icon name="close" size={14} />
							</button>
						</div>
					))}
					<div style={{ padding: '8px 18px 14px', display: 'flex', gap: 10 }}>
						<button type="button" className="btn" onClick={() => setRows((rs) => [...rs, { ...EMPTY_ROW }])}>
							<Icon name="plus" size={15} /> Add item
						</button>
						<button type="button" className="btn" onClick={() => setQuickCreate('item')}>
							<Icon name="cube" size={15} /> New item master
						</button>
					</div>

					<div className="formfoot">
						{err && <span className="ferr">{err}</span>}
						<span className="spacer" />
						<span className="num" style={{ fontSize: 15 }}>
							{fmtMoney(total, currency || undefined)}
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
					<Card>
						<CHead icon="banknote" title="Summary" />
						<Facts
							rows={[
								{ k: 'Items', v: String(rows.filter((r) => r.item_code).length), data: true },
								{ k: 'Deal value', v: fmtMoney(total, currency || undefined), data: true },
								{
									k: 'In ' + (ctx?.company_currency ?? '—'),
									v: fmtMoney(total * (isCompanyCurrency ? 1 : Number(rate) || 0), ctx?.company_currency),
									data: true,
								},
							]}
						/>
					</Card>
					<Card>
						<CHead icon="truck" title="What happens next" />
						<div className="empty" style={{ padding: '18px 20px', alignItems: 'flex-start', textAlign: 'left' }}>
							<div className="t2">
								Suppliers are decided after the deal is booked. Once negotiations conclude, you'll
								create purchase orders from this sales order — picking the supplier per line — and
								each PO line stays connected to the exact deal line it fulfils.
							</div>
						</div>
					</Card>
				</div>
			</div>

			{quickCreate !== null && (
				<MasterModal
					def={quickCreate === 'customer' ? CUSTOMER_DEF : quickCreate === 'terms' ? TC_DEF : ITEM_DEF}
					options={masterOptions}
					record={null}
					defaults={quickCreate === 'terms' ? { selling: true } : undefined}
					onClose={() => setQuickCreate(null)}
					onSaved={(name) => {
						const which = quickCreate;
						setQuickCreate(null);
						void ctxResult.mutate();
						if (which === 'customer') {
							setCustomer(name);
						} else if (which === 'terms') {
							void onTemplate(name);
						} else {
							// select the new item on the first empty row (or append one)
							setRows((rs) => {
								const idx = rs.findIndex((r) => !r.item_code);
								const next = idx >= 0 ? rs : [...rs, { ...EMPTY_ROW }];
								return next;
							});
							const targetIdx = rows.findIndex((r) => !r.item_code);
							void onPickItem(targetIdx >= 0 ? targetIdx : rows.length, name);
						}
					}}
				/>
			)}

			<footer>
				<b>ExportFlow</b> · DUX Digitech
			</footer>
		</main>
	);
}
