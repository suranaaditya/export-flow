import { useEffect, useMemo, useRef, useState } from 'react';
import {
	useFrappeGetCall,
	useFrappeGetDoc,
	useFrappeGetDocList,
	useFrappePostCall,
} from 'frappe-react-sdk';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Icon } from '@/components/Icon';
import { MasterModal } from '@/components/MasterModal';
import { Field, SearchSelect, SelectInput, TextInput } from '@/components/form';
import { Card, CHead, EmptyMsg } from '@/components/ui';
import {
	API,
	THIRD_COUNTRY_CHA,
	TRADE_TYPES,
	isMerchanting,
	parseServerError,
	type ShippableLine,
} from '@/lib/api';
import { MASTERS, STATIC_OPTIONS, type OptionSource } from '@/lib/masters';

const CHA_DEF = MASTERS.find((m) => m.doctype === 'CHA')!;

interface LineSel {
	checked: boolean;
	qty: string;
	batch: string;
}

interface ShipmentDefaults {
	customer: string;
	customer_name: string;
	incoterm: string | null;
	named_place: string | null;
	letter_of_credit: string | null;
	lc_number: string | null;
	so_details: string[];
}

const LINE_COLS = '40px 1.8fr 1fr 110px 80px 1fr';

export function NewShipment() {
	const navigate = useNavigate();
	const [searchParams] = useSearchParams();

	// the shipment is booked for ONE customer; one or more of that customer's
	// open sales orders are then added to it (the backend enforces same-customer).
	// A ?so= deep link drives the customer itself, so ignore any ?customer there.
	const soParam = searchParams.get('so');
	const [customer, setCustomer] = useState(soParam ? '' : (searchParams.get('customer') ?? ''));
	const [selectedSos, setSelectedSos] = useState<string[]>([]);
	// SOs added before their shippable lines have loaded (deep-link path) —
	// auto-ticked once the lines arrive
	const [pendingSos, setPendingSos] = useState<string[]>([]);
	const [tradeType, setTradeType] = useState<string>('Export from India');
	const [mode, setModeRaw] = useState('Sea');
	const setMode = (m: string) => {
		setModeRaw(m);
		const ok = (name: string) => {
			const port = (ports.data ?? []).find((p) => p.name === name);
			return !port || port.mode === m || port.mode === 'Sea & Air';
		};
		setPol((v) => (ok(v) ? v : ''));
		setPod((v) => (ok(v) ? v : ''));
	};
	const [incoterm, setIncoterm] = useState('');
	const [cha, setCha] = useState('');
	const [pol, setPol] = useState('');
	const [pod, setPod] = useState('');
	const [finalDestination, setFinalDestination] = useState('');
	const [etd, setEtd] = useState('');
	const [eta, setEta] = useState('');
	const [lc, setLc] = useState('');
	const [sel, setSel] = useState<Record<string, LineSel>>({});
	const [err, setErr] = useState<string | null>(null);
	const [addingCha, setAddingCha] = useState(false);

	// the SO whose deal defaults prefilled the header (incoterm/destination/LC),
	// and the exact values applied — so removing that SO clears the still-untouched
	// prefill instead of silently carrying its (SO-specific) LC onto another deal
	const [prefillSo, setPrefillSo] = useState<string | null>(null);
	const prefilled = useRef<{ incoterm: string; finalDestination: string; lc: string }>({
		incoterm: '',
		finalDestination: '',
		lc: '',
	});
	// the user has made a manual choice — guards the async deep-link prefill from
	// clobbering a customer/SO the user picked while its fetch was in flight
	const touched = useRef(false);
	// only the first SO added (when none are selected) prefills the header — this
	// is claimed synchronously so two rapid adds can't both prefill (LC bleed)
	const prefillClaimed = useRef(false);

	const customers = useFrappeGetDocList<{ name: string; customer_name: string }>('Customer', {
		fields: ['name', 'customer_name'],
		filters: [['disabled', '=', 0]],
		limit: 200,
	});
	// labels for the SO picker — this customer's open deals (the eligible *set*
	// is derived from the shippable lines below, so the two never disagree)
	const salesOrders = useFrappeGetDocList<{
		name: string;
		customer_name: string;
		transaction_date: string;
		currency: string;
		grand_total: number;
	}>(
		'Sales Order',
		{
			fields: ['name', 'customer_name', 'transaction_date', 'currency', 'grand_total'],
			filters: [
				['customer', '=', customer],
				['docstatus', '=', 1],
				['status', '!=', 'Closed'],
			],
			orderBy: { field: 'transaction_date', order: 'desc' },
			limit: 200,
		},
		customer ? undefined : null,
	);
	const { call: fetchDefaults } = useFrappePostCall<{ message: ShipmentDefaults }>(
		API.shipmentDefaults,
	);
	const incoterms = useFrappeGetDocList<{ name: string }>('Incoterm', {
		fields: ['name'],
		limit: 100,
	});
	const chas = useFrappeGetDocList<{ name: string }>('CHA', { fields: ['name'], limit: 100 });
	const settings = useFrappeGetDoc<{ auto_cha_third_country?: 0 | 1 }>(
		'ExportFlow Settings',
		'ExportFlow Settings',
	);
	const autoCha = !!settings.data?.auto_cha_third_country;
	const merchanting = isMerchanting(tradeType);

	// auto-stamp the placeholder CHA on merchanting trades when the setting is on
	useEffect(() => {
		if (!autoCha) return;
		if (isMerchanting(tradeType)) setCha(THIRD_COUNTRY_CHA);
		else setCha((c) => (c === THIRD_COUNTRY_CHA ? '' : c));
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [tradeType, autoCha]);
	const masterOptions: Record<OptionSource, string[]> = {
		currencies: [],
		incoterms: [],
		uoms: [],
		countries: [],
		...STATIC_OPTIONS,
	};
	const ports = useFrappeGetDocList<{ name: string; unlocode: string | null; mode: string }>(
		'Port',
		{
			fields: ['name', 'unlocode', 'mode'],
			filters: [['disabled', '=', 0]],
			limit: 300,
		},
	);
	const lcs = useFrappeGetDocList<{ name: string; lc_number: string }>(
		'Letter of Credit',
		{
			fields: ['name', 'lc_number'],
			filters: customer ? [['customer', '=', customer]] : [],
			limit: 50,
		},
		customer ? undefined : null,
	);

	const linesResult = useFrappeGetCall<{ message: ShippableLine[] }>(
		API.shippableLines,
		{ customer },
		customer ? undefined : null,
	);
	// stable reference so the pending-tick effect doesn't churn every render
	const lines = useMemo(() => linesResult.data?.message ?? [], [linesResult.data]);

	const { call: createShipment, loading: saving } = useFrappePostCall<{
		message: { name: string };
	}>(API.createShipment);

	// one SO line can ship from several POs — each sub-row gets its own key
	const rowKey = (l: ShippableLine) => `${l.so_detail}::${l.po_detail ?? 'none'}`;

	const selFor = (l: ShippableLine): LineSel =>
		sel[rowKey(l)] ?? { checked: false, qty: String(l.remaining), batch: '' };

	const patchSel = (l: ShippableLine, patch: Partial<LineSel>) => {
		setErr(null);
		setSel((s) => ({
			...s,
			[rowKey(l)]: { ...(s[rowKey(l)] ?? selFor(l)), ...patch },
		}));
	};

	/** Tick (pre-select) every shippable sub-row belonging to these sales orders. */
	function tickLinesFor(soList: string[]) {
		const wanted = new Set(soList);
		setSel((s) => {
			const next = { ...s };
			for (const l of lines) {
				if (wanted.has(l.sales_order)) {
					next[rowKey(l)] = {
						checked: true,
						qty: String(l.remaining),
						batch: next[rowKey(l)]?.batch ?? '',
					};
				}
			}
			return next;
		});
	}

	/** Record the header prefill a first/deep-linked SO supplied (non-clobbering). */
	function recordPrefill(so: string, d: ShipmentDefaults) {
		const inc = d.incoterm || '';
		const dest = d.named_place || '';
		const lcv = d.letter_of_credit || '';
		setIncoterm((v) => v || inc);
		setFinalDestination((v) => v || dest);
		setLc((v) => v || lcv);
		setPrefillSo(so);
		prefilled.current = { incoterm: inc, finalDestination: dest, lc: lcv };
	}

	/** Clear the still-untouched prefill that `so` supplied (if any). */
	function clearPrefillFor(so: string) {
		if (so !== prefillSo) return;
		const pf = prefilled.current;
		setIncoterm((v) => (v === pf.incoterm ? '' : v));
		setFinalDestination((v) => (v === pf.finalDestination ? '' : v));
		setLc((v) => (v === pf.lc ? '' : v));
		setPrefillSo(null);
		prefillClaimed.current = false;
		prefilled.current = { incoterm: '', finalDestination: '', lc: '' };
	}

	// SOs added before their lines loaded (deep link) get ticked when lines arrive;
	// any that settle with no lines were fully shipped — drop them so no phantom
	// chip is stranded, and say why
	useEffect(() => {
		// only act on a settled, successful result — never treat a still-loading,
		// failed, or revalidating fetch (data momentarily undefined) as "fully shipped"
		if (
			pendingSos.length === 0 ||
			linesResult.isLoading ||
			linesResult.error ||
			linesResult.data === undefined
		)
			return;
		const ready = pendingSos.filter((so) => lines.some((l) => l.sales_order === so));
		const empty = pendingSos.filter((so) => !lines.some((l) => l.sales_order === so));
		if (ready.length) tickLinesFor(ready);
		if (empty.length) {
			setSelectedSos((p) => p.filter((so) => !empty.includes(so)));
			empty.forEach(clearPrefillFor);
			setErr(`${empty.join(', ')} has nothing left to ship.`);
		}
		setPendingSos([]);
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [lines, pendingSos, linesResult.isLoading, linesResult.error, linesResult.data, prefillSo]);

	function onCustomer(v: string) {
		touched.current = true;
		setCustomer(v);
		setSelectedSos([]);
		setPendingSos([]);
		setSel({});
		setLc('');
		setIncoterm('');
		setFinalDestination('');
		setPrefillSo(null);
		prefillClaimed.current = false;
		prefilled.current = { incoterm: '', finalDestination: '', lc: '' };
		setErr(null);
	}

	/** Add an open sales order to the shipment; the first one prefills the
	 *  shipment header from the deal (overridable). */
	async function addSalesOrder(so: string) {
		if (!so || selectedSos.includes(so)) return;
		touched.current = true;
		setErr(null);
		// claim the prefill slot synchronously so two rapid adds can't both prefill
		const claimPrefill = selectedSos.length === 0 && !prefillClaimed.current;
		if (claimPrefill) prefillClaimed.current = true;
		setSelectedSos((p) => (p.includes(so) ? p : [...p, so]));
		if (lines.some((l) => l.sales_order === so)) tickLinesFor([so]);
		else setPendingSos((p) => (p.includes(so) ? p : [...p, so]));
		if (!claimPrefill) return;
		try {
			const result = await fetchDefaults({ sales_order: so });
			recordPrefill(so, result.message);
		} catch {
			prefillClaimed.current = false; // best-effort — let a later first-add prefill
		}
	}

	function removeSalesOrder(so: string) {
		setSelectedSos((p) => p.filter((x) => x !== so));
		setPendingSos((p) => p.filter((x) => x !== so));
		setSel((s) => {
			const next = { ...s };
			for (const l of lines) if (l.sales_order === so) delete next[rowKey(l)];
			return next;
		});
		clearPrefillFor(so);
	}

	// deep link: /shipments/new?so=SO-xxxx (e.g. from the SO screen) — pull the
	// customer + header from the deal, then add that SO once its lines load
	const soParamApplied = useRef(false);
	useEffect(() => {
		if (!soParam || soParamApplied.current) return;
		soParamApplied.current = true;
		void (async () => {
			try {
				const result = await fetchDefaults({ sales_order: soParam });
				if (touched.current) return; // user already picked something — don't clobber
				const d = result.message;
				touched.current = true; // the deep link's own writes are authoritative
				prefillClaimed.current = true;
				setCustomer(d.customer);
				recordPrefill(soParam, d);
				setSelectedSos([soParam]);
				setPendingSos([soParam]);
			} catch (e) {
				if (touched.current) return;
				setErr(parseServerError(e));
			}
		})();
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, []);

	async function onCreate() {
		if (!customer) return setErr('Pick the customer.');
		if (selectedSos.length === 0) return setErr('Add at least one sales order.');
		const checked = lines.filter(
			(l) => selectedSos.includes(l.sales_order) && selFor(l).checked,
		);
		if (checked.length === 0) return setErr('Tick at least one line to ship.');
		for (const l of checked) {
			const q = Number(selFor(l).qty);
			if (!q || q <= 0) return setErr(`${l.item_name}: quantity to ship is required.`);
			if (q > l.remaining + 1e-6) return setErr(`${l.item_name}: only ${l.remaining} remaining to ship.`);
		}
		// a single SO line can split across several PO sub-rows — mirror the backend's
		// cumulative per-line cap so cross-PO over-shipping is caught inline, not post-submit
		const lineRemaining: Record<string, number> = {};
		for (const l of lines) lineRemaining[l.so_detail] = (lineRemaining[l.so_detail] ?? 0) + l.remaining;
		const tickedQty: Record<string, number> = {};
		for (const l of checked) tickedQty[l.so_detail] = (tickedQty[l.so_detail] ?? 0) + Number(selFor(l).qty);
		for (const l of checked) {
			const cap = lineRemaining[l.so_detail] ?? 0;
			if (tickedQty[l.so_detail] > cap + 1e-6) {
				return setErr(
					`${l.item_name}: shipping ${tickedQty[l.so_detail]} but only ${cap} remaining on the sales order line.`,
				);
			}
		}
		setErr(null);
		try {
			const result = await createShipment({
				payload: {
					customer,
					mode,
					trade_type: tradeType,
					incoterm: incoterm || null,
					cha: cha || null,
					port_of_loading: pol || null,
					port_of_discharge: pod || null,
					final_destination: finalDestination,
					etd: etd || null,
					eta: eta || null,
					letter_of_credit: lc || null,
					items: checked.map((l) => ({
						item_code: l.item_code,
						qty: Number(selFor(l).qty),
						uom: l.uom,
						batch_no: selFor(l).batch,
						sales_order: l.sales_order,
						so_detail: l.so_detail,
						purchase_order: l.purchase_order,
						po_detail: l.po_detail,
					})),
				},
			});
			navigate('/shipments/' + result.message.name);
		} catch (e) {
			setErr(parseServerError(e));
		}
	}

	if (customers.error) {
		return (
			<main className="tight">
				<div className="eyebrow">Logistics · New shipment</div>
				<div className="titlebar">
					<span className="who">New shipment</span>
					<span className="spacer" />
				</div>
				<div style={{ marginTop: 14 }}>
					<Card>
						<div className="ferr" style={{ padding: '18px 20px' }}>
							Could not load the form data. {parseServerError(customers.error)}
						</div>
					</Card>
				</div>
			</main>
		);
	}

	const modePorts = (ports.data ?? []).filter((p) => p.mode === mode || p.mode === 'Sea & Air');
	const portOptions = modePorts.map((p) => ({
		value: p.name,
		label: p.unlocode ? `${p.name} · ${p.unlocode}` : p.name,
	}));

	// the eligible SO set comes straight from the shippable lines (an SO appears
	// only while it still has unshipped quantity), enriched with date/value labels
	const soMeta = new Map((salesOrders.data ?? []).map((s) => [s.name, s]));
	const openSoValues = [...new Set(lines.map((l) => l.sales_order))];
	const soOptions = openSoValues
		.filter((so) => !selectedSos.includes(so))
		.map((so) => {
			const m = soMeta.get(so);
			const sub = m
				? `${m.transaction_date ?? ''}${m.grand_total ? ` · ${m.currency} ${Math.round(m.grand_total).toLocaleString('en-IN')}` : ''}`.trim()
				: undefined;
			return { value: so, sub: sub || undefined };
		});

	// the customer genuinely has nothing open to ship (and nothing is selected) —
	// distinct from "open deals exist, none added yet"
	const noOpenSos =
		!!customer &&
		!linesResult.isLoading &&
		!linesResult.error &&
		openSoValues.length === 0 &&
		selectedSos.length === 0;
	const soHint = !customer
		? 'Pick the customer first'
		: noOpenSos
			? 'This customer has no open sales orders left to ship'
			: soOptions.length === 0
				? 'All open sales orders added'
				: 'Add one or more open deals — all lines ship under one shipment';

	return (
		<main className="tight">
			<div className="eyebrow">Logistics · New shipment</div>
			<div className="crumb" style={{ marginTop: 6 }}>
				<Link to="/shipments">Shipments</Link> / <span>New</span>
			</div>
			<div className="titlebar">
				<span className="who">New shipment</span>
				<span className="spacer" />
			</div>

			<div style={{ marginTop: 14 }}>
				<Card accent>
					<CHead icon="ship" title="Shipment" />
					<div className="formgrid">
						<Field label="Customer" required>
							<SearchSelect
								value={customer}
								onChange={onCustomer}
								options={(customers.data ?? []).map((c) => ({
									value: c.name,
									label: c.customer_name,
								}))}
								placeholder="Search customers…"
							/>
						</Field>
						<Field label="Mode">
							<SelectInput
								value={mode}
								onChange={setMode}
								options={[{ value: 'Sea' }, { value: 'Air' }]}
							/>
						</Field>
						<div className="span2">
							<Field label="Sales orders" required hint={soHint}>
								<SearchSelect
									value=""
									onChange={(v) => void addSalesOrder(v)}
									options={soOptions}
									placeholder={
										linesResult.isLoading
											? 'Loading open deals…'
											: customer
												? 'Add a sales order…'
												: 'Pick the customer first'
									}
									disabled={!customer || linesResult.isLoading || soOptions.length === 0}
								/>
							</Field>
							{selectedSos.length > 0 && (
								<div className="sochips">
									{selectedSos.map((so) => (
										<span className="sochip" key={so}>
											{so}
											<button
												type="button"
												className="x"
												aria-label={`Remove ${so}`}
												onClick={() => removeSalesOrder(so)}
											>
												×
											</button>
										</span>
									))}
								</div>
							)}
						</div>
						<Field
							label="Trade type"
							hint={
								isMerchanting(tradeType)
									? 'Goods ship A→B without entering India — no shipping bill, eBRC or RoDTEP'
									: 'Standard export from India'
							}
						>
							<SelectInput
								value={tradeType}
								onChange={setTradeType}
								options={TRADE_TYPES.map((t) => ({ value: t }))}
							/>
						</Field>
						<Field label="Incoterm">
							<SearchSelect
								value={incoterm}
								onChange={setIncoterm}
								options={(incoterms.data ?? []).map((i) => ({ value: i.name }))}
								placeholder="Search incoterms…"
							/>
						</Field>
						<Field
							label="CHA"
							hint={autoCha && merchanting ? 'Auto-set for merchanting trades (see Settings)' : undefined}
						>
							<SearchSelect
								value={cha}
								onChange={setCha}
								options={(chas.data ?? []).map((c) => ({ value: c.name }))}
								placeholder="Search CHAs…"
								onCreate={() => setAddingCha(true)}
								createLabel="New CHA / forwarder"
								disabled={autoCha && merchanting}
							/>
						</Field>
						<Field
							label="Letter of credit"
							hint={customer ? 'LCs for this customer' : 'Pick the customer first'}
						>
							<SearchSelect
								value={lc}
								onChange={setLc}
								options={(lcs.data ?? []).map((r) => ({
									value: r.name,
									label: r.lc_number || r.name,
								}))}
								disabled={!customer}
							/>
						</Field>
						<Field label="Port of loading">
							<SearchSelect value={pol} onChange={setPol} options={portOptions} placeholder="Search ports…" />
						</Field>
						<Field label="Port of discharge">
							<SearchSelect value={pod} onChange={setPod} options={portOptions} placeholder="Search ports…" />
						</Field>
						<div className="span2">
							<Field label="Final destination">
								<TextInput
									value={finalDestination}
									onChange={setFinalDestination}
									placeholder="e.g. Customer warehouse, Dubai"
								/>
							</Field>
						</div>
						<Field label="ETD">
							<TextInput type="date" value={etd} onChange={setEtd} />
						</Field>
						<Field label="ETA">
							<TextInput type="date" value={eta} onChange={setEta} />
						</Field>
					</div>

					<div
						className="reqhead"
						style={{ borderTop: '1px solid var(--hairline)', gridTemplateColumns: LINE_COLS }}
					>
						<span />
						<span>Item</span>
						<span>Sourced from</span>
						<span>Qty to ship</span>
						<span>Remaining</span>
						<span>Batch no</span>
					</div>
					{!customer ? (
						<EmptyMsg
							title="Pick a customer"
							text="Choose the customer, then add their open sales orders to ship."
						/>
					) : linesResult.error ? (
						<div className="ferr" style={{ padding: '14px 18px' }}>
							Could not load shippable lines. {parseServerError(linesResult.error)}
						</div>
					) : linesResult.isLoading ? (
						<div className="sub" style={{ padding: '14px 18px', margin: 0 }}>
							Loading…
						</div>
					) : noOpenSos ? (
						<EmptyMsg
							title="Nothing to ship"
							text="This customer has no open sales order lines left to ship."
						/>
					) : selectedSos.length === 0 ? (
						<EmptyMsg
							title="Add a sales order"
							text="Pick one or more of this customer's open deals above to choose lines to ship."
						/>
					) : (
						selectedSos.map((so) => {
							// a just-added SO's lines are still settling — the effect will
							// tick or drop it next commit; don't flash an empty group meanwhile
							if (pendingSos.includes(so)) return null;
							const rows = lines.filter((l) => l.sales_order === so);
							return (
								<div key={so}>
									<div className="sogrp">
										<span className="glabel">Sales order</span>
										<span className="gid">{so}</span>
									</div>
									{rows.length === 0 ? (
										<div className="sonote">Nothing left to ship on this order.</div>
									) : (
										rows.map((l) => {
											const s = selFor(l);
											return (
												<div
													className="reqrow"
													key={rowKey(l)}
													style={{ gridTemplateColumns: LINE_COLS }}
												>
													<label className="checkrow" style={{ justifyContent: 'center' }}>
														<input
															type="checkbox"
															aria-label={`Ship ${l.item_name}`}
															checked={s.checked}
															onChange={(e) => patchSel(l, { checked: e.target.checked })}
														/>
													</label>
													<div>
														<div className="c1">{l.item_name}</div>
														<div className="c2">{l.item_code}</div>
													</div>
													<div>
														<div className="dim">{l.purchase_order ?? 'no PO yet'}</div>
														{l.supplier ? <div className="c2">{l.supplier}</div> : null}
													</div>
													<TextInput
														type="number"
														mono
														value={s.qty}
														onChange={(v) => patchSel(l, { qty: v })}
													/>
													<span className="dim">
														{l.remaining} {l.uom ?? ''}
													</span>
													<TextInput
														mono
														value={s.batch}
														onChange={(v) => patchSel(l, { batch: v })}
														placeholder="Batch no"
													/>
												</div>
											);
										})
									)}
								</div>
							);
						})
					)}

					<div className="formfoot">
						{err && <span className="ferr">{err}</span>}
						<span className="spacer" />
						<button
							type="button"
							className="btn primary"
							disabled={saving}
							onClick={() => void onCreate()}
						>
							<Icon name="check" size={15} />
							{saving ? 'Creating…' : 'Create shipment'}
						</button>
					</div>
				</Card>
			</div>

			{addingCha && (
				<MasterModal
					def={CHA_DEF}
					options={masterOptions}
					record={null}
					onClose={() => setAddingCha(false)}
					onSaved={(name) => {
						setAddingCha(false);
						void chas.mutate();
						setCha(name);
					}}
				/>
			)}

			<footer>
				<b>ExportFlow</b> · DUX Digitech
			</footer>
		</main>
	);
}
