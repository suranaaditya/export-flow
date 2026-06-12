import { useState } from 'react';
import { useFrappeGetCall, useFrappeGetDocList, useFrappePostCall } from 'frappe-react-sdk';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Icon } from '@/components/Icon';
import { Field, SearchSelect, SelectInput, TextInput } from '@/components/form';
import { Card, CHead, EmptyMsg } from '@/components/ui';
import { API, parseServerError, type ShippableLine } from '@/lib/api';

interface LineSel {
	checked: boolean;
	qty: string;
	batch: string;
}

const LINE_COLS = '40px 1.8fr 1fr 110px 80px 1fr';

export function NewShipment() {
	const navigate = useNavigate();
	const [searchParams] = useSearchParams();

	const [customer, setCustomer] = useState(searchParams.get('customer') ?? '');
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

	const customers = useFrappeGetDocList<{ name: string; customer_name: string }>('Customer', {
		fields: ['name', 'customer_name'],
		filters: [['disabled', '=', 0]],
		limit: 200,
	});
	const incoterms = useFrappeGetDocList<{ name: string }>('Incoterm', {
		fields: ['name'],
		limit: 100,
	});
	const chas = useFrappeGetDocList<{ name: string }>('CHA', { fields: ['name'], limit: 100 });
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
	const lines = linesResult.data?.message ?? [];

	const { call: createShipment, loading: saving } = useFrappePostCall<{
		message: { name: string };
	}>(API.createShipment);

	const selFor = (l: ShippableLine): LineSel =>
		sel[l.so_detail] ?? { checked: false, qty: String(l.remaining), batch: '' };

	const patchSel = (l: ShippableLine, patch: Partial<LineSel>) =>
		setSel((s) => ({
			...s,
			[l.so_detail]: { ...(s[l.so_detail] ?? selFor(l)), ...patch },
		}));

	function onCustomer(v: string) {
		setCustomer(v);
		setSel({});
		setLc('');
	}

	async function onCreate() {
		if (!customer) return setErr('Pick the customer.');
		const checked = lines.filter((l) => selFor(l).checked);
		if (checked.length === 0) return setErr('Tick at least one line to ship.');
		for (const l of checked) {
			const q = Number(selFor(l).qty);
			if (!q || q <= 0) return setErr(`${l.item_name}: quantity to ship is required.`);
			if (q > l.remaining + 1e-6) return setErr(`${l.item_name}: only ${l.remaining} remaining to ship.`);
		}
		setErr(null);
		try {
			const result = await createShipment({
				payload: {
					customer,
					mode,
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
						<Field label="Incoterm">
							<SearchSelect
								value={incoterm}
								onChange={setIncoterm}
								options={(incoterms.data ?? []).map((i) => ({ value: i.name }))}
								placeholder="Search incoterms…"
							/>
						</Field>
						<Field label="CHA">
							<SearchSelect
								value={cha}
								onChange={setCha}
								options={(chas.data ?? []).map((c) => ({ value: c.name }))}
								placeholder="Search CHAs…"
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
							text="Shippable sales order lines appear once the customer is chosen."
						/>
					) : linesResult.error ? (
						<div className="ferr" style={{ padding: '14px 18px' }}>
							Could not load shippable lines. {parseServerError(linesResult.error)}
						</div>
					) : linesResult.isLoading ? (
						<div className="sub" style={{ padding: '14px 18px', margin: 0 }}>
							Loading…
						</div>
					) : lines.length === 0 ? (
						<EmptyMsg
							title="Nothing to ship"
							text="This customer has no open sales order lines left to ship."
						/>
					) : (
						lines.map((l) => {
							const s = selFor(l);
							return (
								<div
									className="reqrow"
									key={l.so_detail}
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
										<div className="c2">{l.sales_order}</div>
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

			<footer>
				<b>ExportFlow</b> · DUX Digitech
			</footer>
		</main>
	);
}
