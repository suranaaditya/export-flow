import { useMemo, useState } from 'react';
import { useFrappeGetCall, useFrappePostCall } from 'frappe-react-sdk';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Icon } from '@/components/Icon';
import { CheckInput, Field, SelectInput, TextArea, TextInput } from '@/components/form';
import { Card, CHead, EmptyMsg, Facts } from '@/components/ui';
import {
	API,
	parseServerError,
	type NewPOContext,
	type SOProcurement,
} from '@/lib/api';
import { fmtMoney } from '@/lib/format';

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

const GRID = '1.8fr 1fr 90px 70px 120px 120px 34px';

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
	const [rows, setRows] = useState<PORow[]>([]);
	const [soPick, setSoPick] = useState(searchParams.get('so') ?? '');
	const [err, setErr] = useState<string | null>(null);

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
	const { call: createPo, loading: saving } = useFrappePostCall<{
		message: { name: string; docstatus: number };
	}>(API.createPoDraft);

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
		const row: PORow = {
			item_code: itemCode,
			item_name: listed?.item_name ?? itemCode,
			qty: '',
			uom: listed?.stock_uom ?? '',
			rate: '',
			sales_order: null,
			so_detail: null,
			max_qty: null,
		};
		setRows((rs) => [...rs, row]);
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

	const total = useMemo(
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
		setErr(null);
		try {
			const result = await createPo({
				podata: {
					supplier,
					transaction_date: orderDate,
					schedule_date: requiredBy || null,
					merchant_export_scheme: mes ? 1 : 0,
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
				},
			});
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

	const suppliers = (ctx?.suppliers ?? []).map((s) => ({ value: s.name, label: s.supplier_name }));
	const soOptions = (ctx?.sales_orders ?? []).map((s) => ({
		value: s.name,
		label: `${s.name} · ${s.customer_name}`,
	}));
	const freeItems = (ctx?.items ?? []).map((i) => ({ value: i.name, label: i.item_name }));

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
							<SelectInput value={supplier} onChange={onSupplier} options={suppliers} allowEmpty />
						</Field>
						<div style={{ paddingTop: 22 }}>
							<CheckInput
								checked={mes}
								onChange={setMes}
								label="Merchant export scheme (0.1% GST)"
							/>
						</div>
						<Field label="Order date">
							<TextInput type="date" value={orderDate} onChange={setOrderDate} />
						</Field>
						<Field label="Required by" hint="Defaults to 15 days out">
							<TextInput type="date" value={requiredBy} onChange={setRequiredBy} />
						</Field>
						<Field label="Terms template" hint="Manage templates in Settings">
							<SelectInput
								value={tcName}
								onChange={(v) => void onTemplate(v)}
								options={(ctx?.terms_templates ?? []).map((t) => ({ value: t }))}
								allowEmpty
							/>
						</Field>
						<div className="span2">
							<Field label="Terms & conditions">
								<TextArea value={terms} onChange={setTerms} rows={4} placeholder="Payment, delivery, quality and documentation conditions…" />
							</Field>
						</div>
					</div>

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
						<EmptyMsg
							title="No items yet"
							text="Pull lines from a sales order below, or add a free item."
						/>
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

					<div style={{ padding: '12px 18px', borderTop: '1px solid var(--hairline)', display: 'grid', gap: 10 }}>
						<div style={{ display: 'flex', gap: 10, alignItems: 'flex-end', flexWrap: 'wrap' }}>
							<div className="field" style={{ minWidth: 260, flex: 1 }}>
								<span className="flabel">Pull lines from a sales order</span>
								<SelectInput value={soPick} onChange={setSoPick} options={soOptions} allowEmpty />
							</div>
							{soPick &&
								(pickableLines.length > 0 ? (
									<div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
										{pickableLines.map((l) => (
											<button
												type="button"
												key={l.so_detail}
												className="btn"
												onClick={() => addSoLine(l.so_detail)}
											>
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
						<div className="field" style={{ maxWidth: 320 }}>
							<span className="flabel">Add a free item (no SO link)</span>
							<SelectInput value="" onChange={(v) => void addFreeRow(v)} options={freeItems} allowEmpty />
						</div>
					</div>

					<div className="formfoot">
						{err && <span className="ferr">{err}</span>}
						<span className="spacer" />
						<span className="num" style={{ fontSize: 15 }}>
							{fmtMoney(total, currency)}
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
					<Card>
						<CHead icon="banknote" title="Summary" />
						<Facts
							rows={[
								{ k: 'Lines', v: String(rows.length), data: true },
								{ k: 'Of which for SOs', v: String(rows.filter((r) => r.sales_order).length), data: true },
								{ k: 'Order value', v: fmtMoney(total, currency), data: true },
							]}
						/>
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

			<footer>
				<b>ExportFlow</b> · DUX Digitech
			</footer>
		</main>
	);
}
