import { useEffect, useState, type ReactNode } from 'react';
import {
	useFrappeGetCall,
	useFrappeGetDoc,
	useFrappeGetDocList,
	useFrappePostCall,
	useFrappeUpdateDoc,
} from 'frappe-react-sdk';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useConfirm } from '@/components/ConfirmDialog';
import { useToast } from '@/components/Toast';
import { DocumentChecklist } from '@/components/DocumentChecklist';
import { IncentiveModal, RealizationModal } from '@/components/financeModals';
import { PackEditor, editToPayload, packToEdit, type PackEdit } from '@/components/packEditor';
import { Icon } from '@/components/Icon';
import { Card, CHead, EmptyMsg, Facts, LRow, Modal, Tag } from '@/components/ui';
import { CheckInput, Field, SearchSelect, SelectInput, TextArea, TextInput } from '@/components/form';
import {
	API,
	GST_EXPORT_MODES,
	THIRD_COUNTRY_CHA,
	TRADE_TYPES,
	incentiveTone,
	isMerchanting,
	lcIsOpen,
	lcTone,
	parseServerError,
	realizationTone,
	urgencyLabel,
	urgencyTone,
	type IncentiveRow,
	type MTTBlock,
	type MttOutlay,
	type RealizationRow,
	type ShipmentDetailData,
	type ShipmentPack,
	type ShipmentFinanceData,
	type ShipmentFinanceSeed,
} from '@/lib/api';
import { daysUntil, fmtDate, fmtMoney } from '@/lib/format';

type ShipmentDoc = ShipmentDetailData['shipment'];

/** Milestones whose arrival means the goods have left the country. */

/** SWR key for a shipment's finance fetch, shared by the finance card and the
 *  MTT card. A refresh nonce is folded in so the parent can force both cards to
 *  re-fetch after a document is generated or the voyage is saved — without a
 *  page reload. (frappe-react-sdk bundles its own swr instance, so a cross-
 *  component global mutate would target the wrong cache; bumping a key the cards
 *  subscribe to is the reliable way to revalidate them from the parent.) */
const financeKey = (shipment: string, nonce: number) =>
	`efx-shipment-finance:${shipment}:${nonce}`;

export function ShipmentDetail() {
	const { id = '' } = useParams<{ id: string }>();
	const navigate = useNavigate();

	const { data, error, isLoading, mutate } = useFrappeGetCall<{ message: ShipmentDetailData }>(
		API.shipmentDetail,
		{ name: id },
	);
	const { call: setMilestone, loading: completing } = useFrappePostCall(API.setMilestone);
	// the finance + MTT cards fetch independently; bumping this nonce (threaded
	// into their SWR key) re-fetches them after a document is generated (a
	// Commercial Invoice auto-creates a realization) or the voyage is saved (the
	// export date / FEMA due fill in)
	const [finNonce, setFinNonce] = useState(0);
	const refreshFinance = () => setFinNonce((n) => n + 1);
	const [actionErr, setActionErr] = useState<string | null>(null);
	const confirm = useConfirm();
	const toast = useToast();
	const [editing, setEditing] = useState(false);
	const [editingShipment, setEditingShipment] = useState(false);

	if (isLoading) {
		return (
			<main className="tight">
				<div className="eyebrow">Logistics · Shipment</div>
				<div className="crumb" style={{ marginTop: 6 }}>
					<Link to="/shipments">Shipments</Link> / <span className="data">{id}</span>
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
					<Link to="/shipments">Shipments</Link> / <span className="data">{id}</span>
				</div>
				<div className="eyebrow" style={{ marginTop: 18 }}>Logistics</div>
				<h1>
					Export <em>shipment</em>
				</h1>
				<div style={{ marginTop: 22 }}>
					<Card>
						<div className="ferr" style={{ padding: '18px 20px' }}>
							{error
								? parseServerError(error)
								: 'This shipment could not be loaded. It may not exist, or you may not have permission to view it.'}
						</div>
					</Card>
				</div>
				<footer>
					<b>ExportFlow</b> · DUX Digitech
				</footer>
			</main>
		);
	}

	const { shipment, milestones, items, packs, lc, sales_orders, can, mtt_outlay } = detail;
	const isAir = shipment.mode === 'Air';
	const merchanting = isMerchanting(shipment.trade_type);

	const nextPending = milestones.find((m) => !m.completed);
	const allDone = milestones.length > 0 && !nextPending;
	// green strictly once the goods have left India (export milestone done)
	const exportDone = !!detail.export_completed_on;
	const headTone: 'ok' | 'pend' = allDone || exportDone ? 'ok' : 'pend';

	const firstContainer =
		shipment.container_numbers?.split(/\r?\n/)[0]?.trim() || null;

	// LC at-risk strip: open LC, ship-by inside the 15-day alert window, goods not yet exported
	const lcDays = lc ? daysUntil(lc.latest_shipment_date) : null;
	const lcAtRisk = !!lc && lcIsOpen(lc.status) && lcDays !== null && lcDays <= 15 && !exportDone;

	// Voyage facts, skipping anything the forwarder has not given us yet
	const vesselLine = [shipment.vessel, shipment.voyage].filter(Boolean).join(' · ');
	const airlineLine = [shipment.airline, shipment.flight_number].filter(Boolean).join(' · ');
	const voyageRows: { k: string; v: ReactNode; data?: boolean }[] = [];
	if (isAir) {
		if (airlineLine) voyageRows.push({ k: 'Airline / flight', v: airlineLine });
		if (shipment.awb_number) voyageRows.push({ k: 'AWB', v: shipment.awb_number, data: true });
	} else {
		if (vesselLine) voyageRows.push({ k: 'Vessel / voyage', v: vesselLine });
		if (firstContainer) voyageRows.push({ k: 'Container', v: firstContainer, data: true });
	}
	if (shipment.port_of_loading) voyageRows.push({ k: 'Port of loading', v: shipment.port_of_loading });
	if (shipment.port_of_discharge) voyageRows.push({ k: 'Discharge', v: shipment.port_of_discharge });
	if (shipment.etd || shipment.eta)
		voyageRows.push({ k: 'ETD / ETA', v: `${fmtDate(shipment.etd)} → ${fmtDate(shipment.eta)}`, data: true });
	if (shipment.cha) voyageRows.push({ k: 'CHA', v: shipment.cha });

	// distinct purchase orders feeding this shipment
	const linkedPos = new Map<string, string | null>();
	for (const it of items) {
		if (it.purchase_order && !linkedPos.has(it.purchase_order)) {
			linkedPos.set(it.purchase_order, it.supplier);
		}
	}

	// the transport document slot: B/L for sea, AWB for air
	const transportDocNumber = isAir ? shipment.awb_number : shipment.bl_number;

	async function onComplete() {
		if (!nextPending) return;
		if (
			!(await confirm({
				title: 'Complete milestone',
				message: `Mark "${nextPending.milestone}" as completed? Completing the departure milestone posts the goods out of stock.`,
				confirmLabel: 'Complete',
			}))
		)
			return;
		setActionErr(null);
		try {
			await setMilestone({ shipment: id, row: nextPending.name, completed: 1 });
			mutate();
			toast.ok(`Milestone "${nextPending.milestone}" completed`);
		} catch (e) {
			setActionErr(parseServerError(e));
			toast.err(parseServerError(e));
		}
	}

	return (
		<main className="tight">
			<div className="eyebrow">Logistics · Shipment</div>
			<div className="crumb" style={{ marginTop: 6 }}>
				<Link to="/shipments">Shipments</Link> / <span className="data">{id}</span>
			</div>

			<div className="titlebar">
				<h1>{shipment.name}</h1>
				<span className="who">· {shipment.customer_name}</span>
				<span style={{ marginTop: 9, display: 'inline-flex', gap: 6 }}>
					<Tag tone={headTone}>{shipment.current_milestone}</Tag>
					{merchanting && (
						<Tag tone="pend">
							<Icon name="globe" size={11} strokeWidth={2} /> Merchanting
						</Tag>
					)}
				</span>
				<span className="spacer" />
				{can.write && (
					<button className="btn" onClick={() => setEditingShipment(true)}>
						<Icon name="sliders" size={15} /> Edit
					</button>
				)}
				{can.write && (
					<button className="btn" onClick={() => setEditing(true)}>
						<Icon name="ship" size={15} /> Update voyage
					</button>
				)}
				{can.write && nextPending && (
					<button className="btn primary" disabled={completing} onClick={() => void onComplete()}>
						<Icon name="circle-check" size={15} />{' '}
						{completing ? 'Completing…' : `Complete: ${nextPending.milestone}`}
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
					<b>Mode</b>
					{shipment.mode}
					{firstContainer ? ' · ' + firstContainer : ''}
				</span>
				<span className="kv">
					<b>Incoterm</b>
					{shipment.incoterm ?? '—'}
				</span>
				{isAir ? (
					shipment.booking_number && (
						<span className="kv">
							<b>Booking</b>
							<span className="data">{shipment.booking_number}</span>
						</span>
					)
				) : (
					<span className="kv">
						<b>Booking</b>
						{shipment.booking_number ? <span className="data">{shipment.booking_number}</span> : '—'}
					</span>
				)}
				{shipment.shipping_bill_number && (
					<span className="kv">
						<b>Shipping bill</b>
						<span className="data">
							{shipment.shipping_bill_number} · {fmtDate(shipment.shipping_bill_date)}
						</span>
					</span>
				)}
				<span className="kv">
					<b>{isAir ? 'AWB' : 'B/L'}</b>
					{transportDocNumber ? (
						<span className="data">{transportDocNumber}</span>
					) : (
						<span style={{ color: 'var(--fg-4)' }}>— after sailing</span>
					)}
				</span>
			</div>

			{lcAtRisk && lc && lcDays !== null && (
				<div className="alert">
					<Icon name="warning" size={16} />
					<span>
						<b>LC at risk</b> — <span className="data">{lc.lc_number}</span> latest shipment date is{' '}
						<span className="data">{fmtDate(lc.latest_shipment_date)}</span>, {urgencyLabel(lcDays)}.
						Chase the CHA today.
					</span>
				</div>
			)}

			<div className="card accent tl-card">
				<div className="tl">
					{milestones.map((m) => {
						const isCur = !m.completed && nextPending?.name === m.name;
						return (
							<div className={m.completed ? 'step done' : isCur ? 'step cur' : 'step'} key={m.name}>
								<span className="dot">
									{m.completed ? <Icon name="check" size={9} strokeWidth={3.4} /> : isCur ? <i /> : null}
								</span>
								<span className="lb">{m.milestone}</span>
								<span className={'dt' + (m.completed ? '' : ' eta')}>
									{m.completed
										? fmtDate(m.actual_date)
										: m.planned_date
											? 'due ' + fmtDate(m.planned_date)
											: isCur
												? 'pending'
												: m.milestone === (isAir ? 'Departed' : 'Shipped on Board') && shipment.etd
													? 'ETD ' + fmtDate(shipment.etd)
													: m.milestone === 'Arrived Destination' && shipment.eta
														? 'ETA ' + fmtDate(shipment.eta)
														: '—'}
								</span>
							</div>
						);
					})}
				</div>
			</div>

			<div className="grid detail">
				<div className="stack">
					<Card>
						<CHead
							icon="package"
							title="Items in this shipment"
							count={`${items.length} ${items.length === 1 ? 'line' : 'lines'}`}
						/>
						<table>
							<thead>
								<tr>
									<th>Item</th>
									<th>Batch</th>
									<th>Qty</th>
									<th>From PO</th>
									<th>Fulfils SO line</th>
								</tr>
							</thead>
							<tbody>
								{items.map((it) => {
									const gstDays = daysUntil(it.gst_export_deadline);
									return (
										<tr key={it.name}>
											<td>
												<div className="c1">{it.item_name}</div>
												{it.pack_description ? <div className="c2">{it.pack_description}</div> : null}
											</td>
											<td className="dim">{it.batch_no ?? '—'}</td>
											<td className="num">{`${it.qty} ${it.uom ?? ''}`.trim()}</td>
											<td>
												{it.purchase_order ? (
													<>
														<span className="id id-sm">{it.purchase_order}</span>
														{it.supplier ? <div className="c2">{it.supplier}</div> : null}
													</>
												) : (
													<span className="dim">—</span>
												)}
												{it.po_cancelled === 1 ? (
												<div style={{ marginTop: 3 }}>
													<Tag tone="err">PO cancelled</Tag>
												</div>
											) : exportDone && it.merchant_export_scheme === 1 ? (
												<div style={{ marginTop: 3 }}>
													<Tag tone="ok">Exported {fmtDate(detail.export_completed_on)}</Tag>
												</div>
											) : (
												it.merchant_export_scheme === 1 &&
												it.gst_export_deadline &&
												gstDays !== null && (
													<div style={{ marginTop: 3 }}>
														<Tag tone={urgencyTone(gstDays) ?? 'ok'}>GST {urgencyLabel(gstDays)}</Tag>
													</div>
												)
											)}
											</td>
											<td>
												<span className="id id-sm">{it.sales_order}</span>
												<div className="c2">
													{it.so_shipped_total} of {it.so_qty} shipped
												</div>
											</td>
										</tr>
									);
								})}
							</tbody>
						</table>
					</Card>

					<PackingCard
						id={id}
						items={items}
						packs={packs}
						canEdit={can.write}
						onSaved={() => mutate()}
					/>

					<DocumentChecklist shipment={id} onGenerated={refreshFinance} />
				</div>

				<div className="stack">
					<Card>
						<CHead icon={isAir ? 'plane' : 'ship'} title="Voyage" />
						{voyageRows.length === 0 ? (
							<EmptyMsg
								title="No voyage details yet"
								text="Use Update voyage once the forwarder confirms the booking."
							/>
						) : (
							<Facts rows={voyageRows} />
						)}
					</Card>

					<Card>
						<CHead icon="link-boxes" title="Linked records" />
						{sales_orders.map((so) => (
							<LRow
								key={so}
								icon="file-text"
								t1={<span className="data">{so}</span>}
								t2="Sales order"
								onClick={() => navigate('/sales-orders/' + so)}
							/>
						))}
						{[...linkedPos.entries()].map(([po, supplier]) => (
							<LRow
								key={po}
								icon="cube"
								t1={<span className="data">{po}</span>}
								t2={supplier ?? 'Purchase order'}
								onClick={() => navigate('/purchases/' + po)}
							/>
						))}
						{lc && (
							<LRow
								icon="calendar"
								t1={<span className="data">{lc.lc_number}</span>}
								t2={lc.issuing_bank ?? 'Letter of credit'}
								right={<Tag tone={lcTone(lc.status)}>{lc.status}</Tag>}
								onClick={() => navigate('/lc/' + lc.name)}
							/>
						)}
					</Card>

					{merchanting && (
						<MTTComplianceCard
						shipment={shipment}
						outlay={mtt_outlay}
						canEdit={can.write}
						nonce={finNonce}
						onSaved={() => mutate()}
					/>
					)}
					<ShipmentFinanceCard shipment={id} merchanting={merchanting} nonce={finNonce} />
				</div>
			</div>

			{editing && (
				<EditVoyageModal
					id={id}
					shipment={shipment}
					onClose={() => setEditing(false)}
					onSaved={() => {
						mutate();
						refreshFinance();
						setEditing(false);
					}}
				/>
			)}

			{editingShipment && (
				<EditShipmentModal
					id={id}
					shipment={shipment}
					items={items}
					onClose={() => setEditingShipment(false)}
					onSaved={() => {
						mutate();
						refreshFinance();
						setEditingShipment(false);
					}}
				/>
			)}

			<footer>
				<b>ExportFlow</b> · DUX Digitech
			</footer>
		</main>
	);
}

/** Incentives + realization attached to this shipment, with inline "Add"
 *  actions that open the finance modals pre-seeded from the shipment + SO.
 *  Full editing also lives on the Finance screen. */
function ShipmentFinanceCard({
	shipment,
	merchanting,
	nonce,
}: {
	shipment: string;
	merchanting: boolean;
	nonce: number;
}) {
	const { data, mutate } = useFrappeGetCall<{ message: ShipmentFinanceData }>(
		API.shipmentFinance,
		{ shipment },
		financeKey(shipment, nonce),
		{ keepPreviousData: true },
	);
	// seed values (export value / currency / date) for the create modals; light
	// query that settles before the user clicks, so the modal opens pre-filled
	const seedQ = useFrappeGetCall<{ message: ShipmentFinanceSeed }>(API.shipmentFinanceSeed, {
		shipment,
	});
	// the open modal carries the row being edited (record) or null when adding
	const [modal, setModal] = useState<
		| { kind: 'incentive'; record: IncentiveRow | null }
		| { kind: 'realization'; record: RealizationRow | null }
		| null
	>(null);

	const fin = data?.message;
	if (!fin) return null;
	const c = fin.can;
	const canRelAdd = c.realization_create;
	// incentives (RoDTEP / drawback) never apply to merchanting trades — but an
	// existing one booked by mistake must still be editable and deletable, so
	// only the "Add" affordance is suppressed, not the row actions
	const canIncAdd = c.incentive_create && !merchanting;
	const hasContent = fin.incentives.length > 0 || fin.realizations.length > 0;
	if (!hasContent && !canRelAdd && !canIncAdd) return null;

	const seed = seedQ.data?.message;
	const seedSettled = seedQ.data !== undefined || !!seedQ.error;
	// a shipment spanning SOs in different currencies has no single FCY invoice
	// value to pre-fill — tell the user to set it by hand
	const currencyConflict = canRelAdd && !!seed?.currency_conflict;

	// link actions inherit the `.chead a` style (iris + hover underline); href="#"
	// keeps them keyboard-focusable, matching the Finance screen's create links.
	// (No "Open finance" link — the sidebar already navigates there, and this card
	// is itself the shipment-scoped finance view; a non-filtered duplicate added
	// nothing.) Rows are clickable to edit; deletion lives inside the modal.
	const actions =
		canRelAdd || canIncAdd ? (
			<span style={{ display: 'inline-flex', gap: 14, alignItems: 'center' }}>
				{seedSettled && canRelAdd && (
					<a href="#" onClick={(e) => { e.preventDefault(); setModal({ kind: 'realization', record: null }); }}>Add realization</a>
				)}
				{seedSettled && canIncAdd && (
					<a href="#" onClick={(e) => { e.preventDefault(); setModal({ kind: 'incentive', record: null }); }}>Add incentive</a>
				)}
			</span>
		) : undefined;

	return (
		<Card>
			<CHead
				icon="banknote"
				title={merchanting ? 'Bank realization' : 'Incentives & realization'}
				action={actions}
			/>
			{currencyConflict && (
				<div className="sub" style={{ padding: '10px 18px 0' }}>
					This shipment spans multiple currencies — set the currency and invoice value
					when adding a realization.
				</div>
			)}
			{!hasContent && (
				<EmptyMsg
					title="No finance records yet"
					text={
						merchanting
							? 'Track export proceeds (FIRC → eBRC) for this trade.'
							: 'Add a RoDTEP / drawback incentive or a bank realization for this shipment.'
					}
				/>
			)}
			{fin.incentives.map((i) => (
				<LRow
					key={i.name}
					icon="shield"
					onClick={c.incentive_write ? () => setModal({ kind: 'incentive', record: i }) : undefined}
					t1={<span>{i.scheme}</span>}
					t2={i.scrip_number || i.scroll_number || i.drawback_serial || 'claim'}
					right={
						<span style={{ textAlign: 'right' }}>
							<span className="num" style={{ display: 'block' }}>
								{i.amount != null ? fmtMoney(i.amount, 'INR') : '—'}
							</span>
							<Tag tone={incentiveTone(i.status)}>{i.status}</Tag>
						</span>
					}
				/>
			))}
			{fin.realizations.map((r) => (
				<LRow
					key={r.name}
					icon="calendar"
					onClick={c.realization_write ? () => setModal({ kind: 'realization', record: r }) : undefined}
					t1={<span className="data">{r.export_invoice ?? r.name}</span>}
					t2={r.due_date ? `due ${fmtDate(r.due_date)}` : 'realization'}
					right={<Tag tone={realizationTone(r)}>{r.overdue ? 'Overdue' : r.status}</Tag>}
				/>
			))}
			{modal?.kind === 'realization' && (
				<RealizationModal
					record={modal.record}
					// pre-fill only when adding; an edit fills from the record itself
					seed={
						modal.record
							? null
							: {
									shipment,
									currency: seed?.currency ?? null,
									invoice_value: seed?.invoice_value ?? null,
									export_date: seed?.export_date ?? null,
								}
					}
					lockShipment
					canDelete={c.realization_delete}
					onClose={() => setModal(null)}
					onSaved={() => {
						setModal(null);
						void mutate();
					}}
					onDeleted={() => {
						setModal(null);
						void mutate();
					}}
				/>
			)}
			{modal?.kind === 'incentive' && (
				<IncentiveModal
					record={modal.record}
					seed={modal.record ? null : { shipment, fob_value: seed?.fob_value_inr ?? null }}
					lockShipment
					canDelete={c.incentive_delete}
					onClose={() => setModal(null)}
					onSaved={() => {
						setModal(null);
						void mutate();
					}}
					onDeleted={() => {
						setModal(null);
						void mutate();
					}}
				/>
			)}
		</Card>
	);
}

interface VoyageForm {
	vessel: string;
	voyage: string;
	booking_number: string;
	container_numbers: string;
	vgm_filed: boolean;
	airline: string;
	flight_number: string;
	awb_number: string;
	awb_date: string;
	shipping_bill_number: string;
	shipping_bill_date: string;
	bl_number: string;
	bl_date: string;
	leo_date: string;
	egm_number: string;
	egm_date: string;
	etd: string;
	eta: string;
	final_destination: string;
}

/** Edit the voyage/customs fields of an Export Shipment. Mode decides which
 *  block shows; the LC link is deliberately not editable here. */
function EditVoyageModal({
	id,
	shipment,
	onClose,
	onSaved,
}: {
	id: string;
	shipment: ShipmentDoc;
	onClose: () => void;
	onSaved: () => void;
}) {
	const isAir = shipment.mode === 'Air';
	const merchanting = isMerchanting(shipment.trade_type);
	const { updateDoc, loading: saving } = useFrappeUpdateDoc();
	const [err, setErr] = useState<string | null>(null);
	// seeded once on mount; the modal unmounts on close, so background
	// revalidation can never clobber in-flight edits
	const [form, setForm] = useState<VoyageForm>(() => ({
		vessel: shipment.vessel ?? '',
		voyage: shipment.voyage ?? '',
		booking_number: shipment.booking_number ?? '',
		container_numbers: shipment.container_numbers ?? '',
		vgm_filed: !!shipment.vgm_filed,
		airline: shipment.airline ?? '',
		flight_number: shipment.flight_number ?? '',
		awb_number: shipment.awb_number ?? '',
		awb_date: shipment.awb_date ?? '',
		shipping_bill_number: shipment.shipping_bill_number ?? '',
		shipping_bill_date: shipment.shipping_bill_date ?? '',
		bl_number: shipment.bl_number ?? '',
		bl_date: shipment.bl_date ?? '',
		leo_date: shipment.leo_date ?? '',
		egm_number: shipment.egm_number ?? '',
		egm_date: shipment.egm_date ?? '',
		etd: shipment.etd ?? '',
		eta: shipment.eta ?? '',
		final_destination: shipment.final_destination ?? '',
	}));

	const set = <K extends keyof VoyageForm>(key: K, value: VoyageForm[K]) =>
		setForm((f) => ({ ...f, [key]: value }));

	async function onSave() {
		setErr(null);
		const orNull = (v: string) => v || null;
		const payload: Record<string, unknown> = {
			etd: orNull(form.etd),
			eta: orNull(form.eta),
			final_destination: form.final_destination,
			// India-customs artefacts do not exist for merchanting trades
			...(merchanting
				? {}
				: {
						shipping_bill_number: form.shipping_bill_number,
						shipping_bill_date: orNull(form.shipping_bill_date),
						leo_date: orNull(form.leo_date),
						egm_number: form.egm_number,
						egm_date: orNull(form.egm_date),
					}),
			...(isAir
				? {
						airline: form.airline,
						flight_number: form.flight_number,
						awb_number: form.awb_number,
						awb_date: orNull(form.awb_date),
					}
				: {
						vessel: form.vessel,
						voyage: form.voyage,
						booking_number: form.booking_number,
						container_numbers: form.container_numbers,
						vgm_filed: form.vgm_filed ? 1 : 0,
						bl_number: form.bl_number,
						bl_date: orNull(form.bl_date),
					}),
		};
		try {
			await updateDoc('Export Shipment', id, payload);
			onSaved();
		} catch (e) {
			setErr(parseServerError(e));
		}
	}

	return (
		<Modal title="Update voyage" icon={isAir ? 'plane' : 'ship'} onClose={onClose}>
			<div className="formgrid">
				{isAir ? (
					<>
						<Field label="Airline">
							<TextInput value={form.airline} onChange={(v) => set('airline', v)} />
						</Field>
						<Field label="Flight number">
							<TextInput value={form.flight_number} onChange={(v) => set('flight_number', v)} />
						</Field>
						<Field label="AWB number">
							<TextInput mono value={form.awb_number} onChange={(v) => set('awb_number', v)} />
						</Field>
						<Field label="AWB date">
							<TextInput type="date" value={form.awb_date} onChange={(v) => set('awb_date', v)} />
						</Field>
					</>
				) : (
					<>
						<Field label="Vessel">
							<TextInput value={form.vessel} onChange={(v) => set('vessel', v)} />
						</Field>
						<Field label="Voyage">
							<TextInput value={form.voyage} onChange={(v) => set('voyage', v)} />
						</Field>
						<Field label="Booking number">
							<TextInput mono value={form.booking_number} onChange={(v) => set('booking_number', v)} />
						</Field>
						<div className="span2">
							<Field label="Container numbers" hint="One container per line">
								<TextArea
									value={form.container_numbers}
									onChange={(v) => set('container_numbers', v)}
									rows={2}
								/>
							</Field>
						</div>
						<div className="span2">
							<CheckInput
								checked={form.vgm_filed}
								onChange={(v) => set('vgm_filed', v)}
								label="VGM filed"
							/>
						</div>
					</>
				)}
				{!merchanting && (
					<>
						<Field label="Shipping bill number">
							<TextInput
								mono
								value={form.shipping_bill_number}
								onChange={(v) => set('shipping_bill_number', v)}
							/>
						</Field>
						<Field label="Shipping bill date">
							<TextInput
								type="date"
								value={form.shipping_bill_date}
								onChange={(v) => set('shipping_bill_date', v)}
							/>
						</Field>
					</>
				)}
				{!isAir && (
					<>
						<Field label="B/L number">
							<TextInput mono value={form.bl_number} onChange={(v) => set('bl_number', v)} />
						</Field>
						<Field label="B/L date">
							<TextInput type="date" value={form.bl_date} onChange={(v) => set('bl_date', v)} />
						</Field>
					</>
				)}
				{!merchanting && (
					<>
						<Field label="LEO date">
							<TextInput type="date" value={form.leo_date} onChange={(v) => set('leo_date', v)} />
						</Field>
						<Field label="EGM number">
							<TextInput mono value={form.egm_number} onChange={(v) => set('egm_number', v)} />
						</Field>
						<Field label="EGM date">
							<TextInput type="date" value={form.egm_date} onChange={(v) => set('egm_date', v)} />
						</Field>
					</>
				)}
				<Field label="ETD">
					<TextInput type="date" value={form.etd} onChange={(v) => set('etd', v)} />
				</Field>
				<Field label="ETA">
					<TextInput type="date" value={form.eta} onChange={(v) => set('eta', v)} />
				</Field>
				<Field label="Final destination">
					<TextInput value={form.final_destination} onChange={(v) => set('final_destination', v)} />
				</Field>
			</div>
			<div className="formfoot">
				{err && <span className="ferr">{err}</span>}
				<span className="spacer" />
				<button type="button" className="btn" onClick={onClose}>
					Cancel
				</button>
				<button type="button" className="btn primary" disabled={saving} onClick={() => void onSave()}>
					{saving ? 'Saving…' : 'Save changes'}
				</button>
			</div>
		</Modal>
	);
}

/** Deadline tone for an MTT clock: rose ≤7d, amber ≤15d, calm beyond. */
const mttTone = (days: number | null): 'ok' | 'pend' | 'err' => urgencyTone(days) ?? 'ok';

const MTT_PMS_OPTIONS = [{ value: '' }, { value: 'Open' }, { value: 'Closed' }, { value: 'Not Required' }];

/** FEMA merchanting-trade compliance for a third-country shipment: the two
 *  RBI clocks, same-AD-bank confirmation, net-FX profit and EDPMS/IDPMS. */
function MTTComplianceCard({
	shipment,
	outlay,
	canEdit,
	nonce,
	onSaved,
}: {
	shipment: ShipmentDoc;
	outlay: MttOutlay | null;
	canEdit: boolean;
	nonce: number;
	onSaved: () => void;
}) {
	const { data, mutate } = useFrappeGetCall<{ message: ShipmentFinanceData }>(
		API.shipmentFinance,
		{ shipment: shipment.name },
		financeKey(shipment.name, nonce),
		{ keepPreviousData: true },
	);
	const mtt: MTTBlock | null = data?.message?.mtt ?? null;
	const [editing, setEditing] = useState(false);

	const rows: { k: string; v: ReactNode; data?: boolean }[] = [];
	if (mtt) {
		rows.push({
			k: '9-month completion',
			v: mtt.completed ? (
				<span>
					Completed <span className="data">{fmtDate(mtt.completion_date)}</span>
				</span>
			) : mtt.completion_due ? (
				<span>
					<span className="data">{fmtDate(mtt.completion_due)}</span>{' '}
					{mtt.completion_days !== null && (
						<Tag tone={mttTone(mtt.completion_days)}>{urgencyLabel(mtt.completion_days)}</Tag>
					)}
				</span>
			) : (
				'—'
			),
		});
		rows.push({
			k: '4-month forex outlay',
			v: !mtt.outlay_open ? (
				<Tag tone="ok">{mtt.import_payment_date ? 'Proceeds received' : 'Not started'}</Tag>
			) : mtt.outlay_due ? (
				<span>
					<span className="data">{fmtDate(mtt.outlay_due)}</span>{' '}
					{mtt.outlay_days !== null && (
						<Tag tone={mttTone(mtt.outlay_days)}>{urgencyLabel(mtt.outlay_days)}</Tag>
					)}
				</span>
			) : (
				<span style={{ color: 'var(--fg-4)' }}>set import payment date</span>
			),
		});
		rows.push({ k: 'AD bank (both legs)', v: mtt.ad_bank ?? '—' });
		rows.push({
			k: 'Same AD bank',
			v: (
				<Tag tone={mtt.same_ad_bank ? 'ok' : 'pend'}>
					{mtt.same_ad_bank ? 'Confirmed' : 'Unconfirmed'}
				</Tag>
			),
		});
		if (mtt.export_proceeds_inr != null)
			rows.push({
				k: 'Export proceeds',
				v: <span className="num">{fmtMoney(mtt.export_proceeds_inr, 'INR')}</span>,
				data: true,
			});
		rows.push({
			k: 'Net FX profit',
			v:
				mtt.net_fx_profit_inr == null ? (
					<span style={{ color: 'var(--fg-4)' }}>
						{mtt.import_value_inr == null ? 'add import outlay' : 'awaiting export proceeds'}
					</span>
				) : (
					<span>
						<span className="num">{fmtMoney(mtt.net_fx_profit_inr, 'INR')}</span>{' '}
						<Tag tone={mtt.net_fx_profit_inr < 0 ? 'err' : 'ok'}>
							{mtt.net_fx_profit_inr < 0 ? 'FX loss' : 'net gain'}
						</Tag>
					</span>
				),
		});
		if (mtt.import_value_inr != null)
			rows.push({
				k: 'Import outlay',
				v: (
					<span>
						<span className="num">{fmtMoney(mtt.import_value_inr, 'INR')}</span>{' '}
						{shipment.mtt_import_value_auto ? <Tag tone="ok">auto from POs</Tag> : null}
					</span>
				),
				data: true,
			});
		if (shipment.mtt_import_value_auto && outlay && outlay.uncosted_lines > 0)
			rows.push({
				k: '',
				v: (
					<span style={{ color: 'var(--fg-3)', fontSize: '12px' }}>
						{outlay.uncosted_lines} line(s) have no PO yet — not counted in the outlay
					</span>
				),
			});
		if (shipment.mtt_import_supplier)
			rows.push({ k: 'Import supplier', v: shipment.mtt_import_supplier });
		rows.push({ k: 'EDPMS / IDPMS', v: `${mtt.edpms_status ?? '—'} / ${mtt.idpms_status ?? '—'}` });
	}

	return (
		<Card>
			<CHead
				icon="globe"
				title="Merchanting (MTT) compliance"
				action={
					canEdit ? (
						<a
							href="#"
							onClick={(e) => {
								e.preventDefault();
								setEditing(true);
							}}
							style={{ fontSize: '12.5px', color: 'var(--iris)', textDecoration: 'none', fontWeight: 500 }}
						>
							Edit
						</a>
					) : undefined
				}
			/>
			{!mtt ? (
				<div className="sub" style={{ padding: '14px 18px', margin: 0 }}>
					Loading…
				</div>
			) : (
				<Facts rows={rows} />
			)}
			{editing && (
				<MTTEditModal
					shipment={shipment}
					outlay={outlay}
					onClose={() => setEditing(false)}
					onSaved={() => {
						setEditing(false);
						void mutate();
						onSaved();
					}}
				/>
			)}
		</Card>
	);
}

interface MTTForm {
	mtt_ad_bank: string;
	mtt_same_ad_bank: boolean;
	mtt_import_supplier: string;
	mtt_import_value_auto: boolean;
	mtt_import_value_inr: string;
	mtt_commencement_date: string;
	mtt_import_payment_date: string;
	mtt_completion_date: string;
	mtt_idpms_status: string;
	mtt_edpms_status: string;
}

function MTTEditModal({
	shipment,
	outlay,
	onClose,
	onSaved,
}: {
	shipment: ShipmentDoc;
	outlay: MttOutlay | null;
	onClose: () => void;
	onSaved: () => void;
}) {
	const { updateDoc, loading: saving } = useFrappeUpdateDoc();
	const [err, setErr] = useState<string | null>(null);
	const suppliers = useFrappeGetDocList<{ name: string; supplier_name: string }>('Supplier', {
		fields: ['name', 'supplier_name'],
		filters: [['disabled', '=', 0]],
		limit: 200,
	});
	const [form, setForm] = useState<MTTForm>(() => ({
		mtt_ad_bank: shipment.mtt_ad_bank ?? '',
		mtt_same_ad_bank: !!shipment.mtt_same_ad_bank,
		mtt_import_supplier: shipment.mtt_import_supplier ?? '',
		mtt_import_value_auto: !!shipment.mtt_import_value_auto,
		mtt_import_value_inr:
			shipment.mtt_import_value_inr != null ? String(shipment.mtt_import_value_inr) : '',
		mtt_commencement_date: shipment.mtt_commencement_date ?? '',
		mtt_import_payment_date: shipment.mtt_import_payment_date ?? '',
		mtt_completion_date: shipment.mtt_completion_date ?? '',
		mtt_idpms_status: shipment.mtt_idpms_status ?? '',
		mtt_edpms_status: shipment.mtt_edpms_status ?? '',
	}));
	const set = <K extends keyof MTTForm>(k: K, v: MTTForm[K]) => setForm((f) => ({ ...f, [k]: v }));
	const supplierName = (name: string) =>
		suppliers.data?.find((s) => s.name === name)?.supplier_name ?? name;
	const auto = form.mtt_import_value_auto;
	// toggling auto OFF seeds the now-editable fields from what was shown under auto
	const toggleAuto = (v: boolean) => {
		set('mtt_import_value_auto', v);
		if (!v && outlay) {
			set('mtt_import_value_inr', outlay.computed ? String(outlay.computed) : '');
			if (outlay.supplier) set('mtt_import_supplier', outlay.supplier);
		}
	};

	async function onSave() {
		setErr(null);
		const orNull = (v: string) => v || null;
		try {
			await updateDoc('Export Shipment', shipment.name, {
				mtt_ad_bank: form.mtt_ad_bank,
				mtt_same_ad_bank: form.mtt_same_ad_bank ? 1 : 0,
				// under auto the server owns these — post what the user is shown so the
				// payload never contradicts the display (the controller still recomputes)
				mtt_import_supplier: auto ? (outlay?.supplier ?? null) : orNull(form.mtt_import_supplier),
				mtt_import_value_auto: auto ? 1 : 0,
				mtt_import_value_inr: auto
					? (outlay?.computed ?? 0)
					: form.mtt_import_value_inr
						? Number(form.mtt_import_value_inr)
						: 0,
				mtt_commencement_date: orNull(form.mtt_commencement_date),
				mtt_import_payment_date: orNull(form.mtt_import_payment_date),
				mtt_completion_date: orNull(form.mtt_completion_date),
				mtt_idpms_status: orNull(form.mtt_idpms_status),
				mtt_edpms_status: orNull(form.mtt_edpms_status),
			});
			onSaved();
		} catch (e) {
			setErr(parseServerError(e));
		}
	}

	return (
		<Modal title="MTT compliance" icon="globe" onClose={onClose}>
			<div className="formgrid">
				<div className="span2">
					<CheckInput
						checked={auto}
						onChange={toggleAuto}
						label="Auto-derive outlay & supplier from the linked purchase orders"
					/>
				</div>
				<Field label="AD bank (both legs)">
					<TextInput value={form.mtt_ad_bank} onChange={(v) => set('mtt_ad_bank', v)} />
				</Field>
				<Field
					label="Import-leg supplier"
					hint={
						auto
							? outlay?.supplier
								? 'From the linked purchase order'
								: (outlay?.suppliers.length ?? 0) > 1
									? 'Several suppliers across the POs — switch off auto to set one'
									: 'No PO linked yet'
							: undefined
					}
				>
					{auto ? (
						<TextInput
							value={outlay?.supplier ? (outlay.supplier_name ?? supplierName(outlay.supplier)) : ''}
							onChange={() => {}}
							placeholder="—"
							disabled
						/>
					) : (
						<SearchSelect
							value={form.mtt_import_supplier}
							onChange={(v) => set('mtt_import_supplier', v)}
							options={(suppliers.data ?? []).map((s) => ({ value: s.name, label: s.supplier_name }))}
							placeholder="Search suppliers…"
						/>
					)}
				</Field>
				<div className="span2">
					<CheckInput
						checked={form.mtt_same_ad_bank}
						onChange={(v) => set('mtt_same_ad_bank', v)}
						label="Both legs routed through the same AD bank"
					/>
				</div>
				<Field label="Trade commenced" hint="9-month completion clock starts here">
					<TextInput
						type="date"
						value={form.mtt_commencement_date}
						onChange={(v) => set('mtt_commencement_date', v)}
					/>
				</Field>
				<Field label="Import leg paid on" hint="4-month forex-outlay clock">
					<TextInput
						type="date"
						value={form.mtt_import_payment_date}
						onChange={(v) => set('mtt_import_payment_date', v)}
					/>
				</Field>
				<Field label="Trade completed on">
					<TextInput
						type="date"
						value={form.mtt_completion_date}
						onChange={(v) => set('mtt_completion_date', v)}
					/>
				</Field>
				<Field
					label="Import outlay (INR)"
					hint={
						form.mtt_import_value_auto
							? outlay && outlay.uncosted_lines > 0
								? `${outlay.costed_lines} line(s) costed · ${outlay.uncosted_lines} without a PO not counted`
								: outlay && outlay.costed_lines === 0
									? 'No linked POs yet — link a PO or switch off auto'
									: 'Summed from the linked PO lines'
							: 'For the net-FX-profit check'
					}
				>
					{form.mtt_import_value_auto ? (
						<TextInput mono value={outlay ? String(outlay.computed) : '0'} onChange={() => {}} disabled />
					) : (
						<TextInput
							type="number"
							mono
							value={form.mtt_import_value_inr}
							onChange={(v) => set('mtt_import_value_inr', v)}
						/>
					)}
				</Field>
				<Field label="EDPMS (export) status">
					<SelectInput
						value={form.mtt_edpms_status}
						onChange={(v) => set('mtt_edpms_status', v)}
						options={MTT_PMS_OPTIONS}
					/>
				</Field>
				<Field label="IDPMS (import) status">
					<SelectInput
						value={form.mtt_idpms_status}
						onChange={(v) => set('mtt_idpms_status', v)}
						options={MTT_PMS_OPTIONS}
					/>
				</Field>
			</div>
			<div className="formfoot">
				{err && <span className="ferr">{err}</span>}
				<span className="spacer" />
				<button type="button" className="btn" onClick={onClose}>
					Cancel
				</button>
				<button type="button" className="btn primary" disabled={saving} onClick={() => void onSave()}>
					{saving ? 'Saving…' : 'Save changes'}
				</button>
			</div>
		</Modal>
	);
}

interface ShipmentLineEdit {
	name: string;
	qty: string;
	batch_no: string;
	pack_description: string;
}

const SHIP_LINE_GRID = '1.8fr 110px 1fr 1fr';

/** Edit a shipment's deal/routing header + existing line qty/batch/pack.
 *  Voyage/customs live in Update voyage; MTT lives in its own card. */
const kg = (n: number) => (n ? n.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '0');

/** Per-batch packing detail — drum ranges, quantities, mfg/exp and net/tare
 *  weights that itemise the invoice and packing list. Grouped by item at print. */
function PackingCard({
	id,
	items,
	packs,
	canEdit,
	onSaved,
}: {
	id: string;
	items: ShipmentDetailData['items'];
	packs: ShipmentPack[];
	canEdit: boolean;
	onSaved: () => void;
}) {
	const [editing, setEditing] = useState(false);
	const itemName = (code: string) => items.find((i) => i.item_code === code)?.item_name ?? code;
	const num = (p: ShipmentPack) => Number(p.num_packages) || 0;
	const net = packs.reduce((s, p) => s + num(p) * (Number(p.net_per) || 0), 0);
	const tare = packs.reduce((s, p) => s + num(p) * (Number(p.tare_per) || 0), 0);
	const totalPkgs = packs.reduce((s, p) => s + num(p), 0);

	return (
		<Card>
			<CHead
				icon="package"
				title="Packing detail"
				count={packs.length ? `${totalPkgs} ${totalPkgs === 1 ? 'pkg' : 'pkgs'}` : undefined}
				action={
					canEdit ? (
						<a href="#" onClick={(e) => { e.preventDefault(); setEditing(true); }}>Edit packing</a>
					) : undefined
				}
			/>
			{packs.length === 0 ? (
				<EmptyMsg
					title="No packing detail yet"
					text={canEdit ? 'Add batches, drum ranges and net/tare weights — they appear on the invoice and packing list.' : undefined}
				/>
			) : (
				<>
					{packs.map((p, i) => (
						<LRow
							key={p.name ?? i}
							icon="box"
							t1={
								<span>
									{itemName(p.item_code)}
									{p.batch_no ? <span className="data"> · {p.batch_no}</span> : null}
								</span>
							}
							t2={`${p.num_packages ?? '—'} ${p.pack_type || 'pkgs'}${p.marks ? ` (nos ${p.marks})` : ''}${p.mfg_date ? ` · Mfg ${fmtDate(p.mfg_date)}` : ''}${p.exp_date ? ` · Exp ${fmtDate(p.exp_date)}` : ''}`}
							right={<span className="num">{kg(num(p) * (Number(p.net_per) || 0))} kg</span>}
						/>
					))}
					<div className="ptot">
						Net <b>{kg(net)}</b> · Tare <b>{kg(tare)}</b> · Gross <b>{kg(net + tare)}</b> kg
					</div>
				</>
			)}
			{editing && (
				<PackingModal
					id={id}
					items={items}
					packs={packs}
					onClose={() => setEditing(false)}
					onSaved={() => { onSaved(); setEditing(false); }}
				/>
			)}
		</Card>
	);
}

function PackingModal({
	id,
	items,
	packs,
	onClose,
	onSaved,
}: {
	id: string;
	items: ShipmentDetailData['items'];
	packs: ShipmentPack[];
	onClose: () => void;
	onSaved: () => void;
}) {
	const { call: update, loading: saving } = useFrappePostCall(API.updateShipment);
	const [err, setErr] = useState<string | null>(null);
	const [rows, setRows] = useState<PackEdit[]>(() => packs.map(packToEdit));
	// the item is a strict pick from THIS shipment's own lines — never free text
	const itemOpts = [...new Map(items.map((i) => [i.item_code, i.item_name])).entries()].map(
		([value, label]) => ({ value, label: label || value }),
	);

	async function onSave() {
		setErr(null);
		try {
			await update({ name: id, payload: { packs: editToPayload(rows) } });
			onSaved();
		} catch (e) {
			setErr(parseServerError(e));
		}
	}

	return (
		<Modal title="Packing detail" icon="package" onClose={onClose}>
			<div className="sub" style={{ padding: '4px 18px 0' }}>
				One row per batch / package group. Net &amp; tare are per package; the totals (net / tare /
				gross) are computed for the invoice and packing list.
			</div>
			<PackEditor rows={rows} onChange={setRows} itemOptions={itemOpts} />
			<div className="formfoot">
				{err && <span className="ferr">{err}</span>}
				<span className="spacer" />
				<button type="button" className="btn" onClick={onClose}>Cancel</button>
				<button type="button" className="btn primary" disabled={saving} onClick={() => void onSave()}>
					{saving ? 'Saving…' : 'Save packing'}
				</button>
			</div>
		</Modal>
	);
}

function EditShipmentModal({
	id,
	shipment,
	items,
	onClose,
	onSaved,
}: {
	id: string;
	shipment: ShipmentDoc;
	items: ShipmentDetailData['items'];
	onClose: () => void;
	onSaved: () => void;
}) {
	const { call: update, loading: saving } = useFrappePostCall(API.updateShipment);
	const [err, setErr] = useState<string | null>(null);
	const [form, setForm] = useState(() => ({
		mode: shipment.mode as 'Sea' | 'Air',
		trade_type: shipment.trade_type as string,
		incoterm: shipment.incoterm ?? '',
		cha: shipment.cha ?? '',
		port_of_loading: shipment.port_of_loading ?? '',
		port_of_discharge: shipment.port_of_discharge ?? '',
		final_destination: shipment.final_destination ?? '',
		letter_of_credit: shipment.letter_of_credit ?? '',
		notes: shipment.notes ?? '',
		// commercial / invoice terms (drive the prints)
		gst_export_mode: shipment.gst_export_mode ?? 'Under LUT (without IGST)',
		igst_rate: shipment.igst_rate != null ? String(shipment.igst_rate) : '18',
		inr_rate: shipment.inr_rate != null ? String(shipment.inr_rate) : '',
		freight_amount: shipment.freight_amount != null ? String(shipment.freight_amount) : '',
		insurance_amount: shipment.insurance_amount != null ? String(shipment.insurance_amount) : '',
		buyer_order_no: shipment.buyer_order_no ?? '',
		buyer_order_date: shipment.buyer_order_date ?? '',
		consignee_to_order: !!shipment.consignee_to_order,
		consignee_name: shipment.consignee_name ?? '',
		consignee_address: shipment.consignee_address ?? '',
		notify_party: shipment.notify_party ?? '',
		// incentive claims booked on this shipment
		claim_rodtep: !!shipment.claim_rodtep,
		rodtep_rate_pct: shipment.rodtep_rate_pct != null ? String(shipment.rodtep_rate_pct) : '',
		claim_drawback: !!shipment.claim_drawback,
		drawback_rate_pct: shipment.drawback_rate_pct != null ? String(shipment.drawback_rate_pct) : '',
	}));
	const [lines, setLines] = useState<ShipmentLineEdit[]>(() =>
		items.map((it) => ({
			name: it.name,
			qty: String(it.qty),
			batch_no: it.batch_no ?? '',
			pack_description: it.pack_description ?? '',
		})),
	);
	const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) =>
		setForm((f) => ({ ...f, [k]: v }));
	const setLine = (i: number, patch: Partial<ShipmentLineEdit>) =>
		setLines((ls) => ls.map((l, idx) => (idx === i ? { ...l, ...patch } : l)));

	const ports = useFrappeGetDocList<{ name: string; mode: string }>('Port', {
		fields: ['name', 'mode'],
		filters: [['disabled', '=', 0]],
		limit: 300,
	});
	const chas = useFrappeGetDocList<{ name: string }>('CHA', { fields: ['name'], limit: 100 });
	const settings = useFrappeGetDoc<{ auto_cha_third_country?: 0 | 1 }>(
		'ExportFlow Settings',
		'ExportFlow Settings',
	);
	const autoCha = !!settings.data?.auto_cha_third_country;
	const chaLocked = autoCha && isMerchanting(form.trade_type);

	// keep the CHA in step with the trade type when the auto rule is on
	useEffect(() => {
		if (!autoCha) return;
		setForm((f) =>
			isMerchanting(f.trade_type)
				? f.cha === THIRD_COUNTRY_CHA
					? f
					: { ...f, cha: THIRD_COUNTRY_CHA }
				: f.cha === THIRD_COUNTRY_CHA
					? { ...f, cha: '' }
					: f,
		);
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [form.trade_type, autoCha]);
	const incoterms = useFrappeGetDocList<{ name: string }>('Incoterm', { fields: ['name'], limit: 100 });
	const lcs = useFrappeGetDocList<{ name: string; lc_number: string }>('Letter of Credit', {
		fields: ['name', 'lc_number'],
		filters: [['customer', '=', shipment.customer]],
		limit: 50,
	});
	const portOpts = (ports.data ?? [])
		.filter((p) => p.mode === form.mode || p.mode === 'Sea & Air')
		.map((p) => ({ value: p.name }));

	async function onSave() {
		setErr(null);
		const orNull = (v: string) => v || null;
		// only persist fields the active mode actually uses, so the stored row
		// can't disagree with the trade type / GST mode / consignee choice
		const merch = isMerchanting(form.trade_type);
		const igstMode = !merch && form.gst_export_mode === 'On payment of IGST';
		try {
			await update({
				name: id,
				payload: {
					mode: form.mode,
					trade_type: form.trade_type,
					incoterm: orNull(form.incoterm),
					cha: orNull(form.cha),
					port_of_loading: orNull(form.port_of_loading),
					port_of_discharge: orNull(form.port_of_discharge),
					final_destination: form.final_destination,
					letter_of_credit: orNull(form.letter_of_credit),
					notes: form.notes,
					gst_export_mode: merch ? null : form.gst_export_mode,
					igst_rate: igstMode ? Number(form.igst_rate) || 0 : 0,
					inr_rate: igstMode ? Number(form.inr_rate) || 0 : 0,
					freight_amount: Number(form.freight_amount) || 0,
					insurance_amount: Number(form.insurance_amount) || 0,
					buyer_order_no: form.buyer_order_no,
					buyer_order_date: orNull(form.buyer_order_date),
					consignee_to_order: form.consignee_to_order ? 1 : 0,
					consignee_name: form.consignee_to_order ? null : form.consignee_name,
					consignee_address: form.consignee_to_order ? null : form.consignee_address,
					notify_party: form.notify_party,
					// incentive claims never apply to merchanting
					claim_rodtep: !merch && form.claim_rodtep ? 1 : 0,
					rodtep_rate_pct: !merch && form.claim_rodtep ? Number(form.rodtep_rate_pct) || 0 : 0,
					claim_drawback: !merch && form.claim_drawback ? 1 : 0,
					drawback_rate_pct: !merch && form.claim_drawback ? Number(form.drawback_rate_pct) || 0 : 0,
					items: lines.map((l) => ({
						name: l.name,
						qty: Number(l.qty),
						batch_no: l.batch_no,
						pack_description: l.pack_description,
					})),
				},
			});
			onSaved();
		} catch (e) {
			setErr(parseServerError(e));
		}
	}

	return (
		<Modal title="Edit shipment" icon="sliders" onClose={onClose}>
			<div className="formgrid">
				<Field label="Mode">
					<SelectInput
						value={form.mode}
						onChange={(v) => set('mode', v as 'Sea' | 'Air')}
						options={[{ value: 'Sea' }, { value: 'Air' }]}
					/>
				</Field>
				<Field label="Trade type">
					<SelectInput
						value={form.trade_type}
						onChange={(v) => set('trade_type', v)}
						options={TRADE_TYPES.map((t) => ({ value: t }))}
					/>
				</Field>
				<Field label="Incoterm">
					<SearchSelect
						value={form.incoterm}
						onChange={(v) => set('incoterm', v)}
						options={(incoterms.data ?? []).map((i) => ({ value: i.name }))}
						placeholder="Search incoterms…"
					/>
				</Field>
				<Field
					label="CHA"
					hint={chaLocked ? 'Auto-set for merchanting trades (see Settings)' : undefined}
				>
					<SearchSelect
						value={form.cha}
						onChange={(v) => set('cha', v)}
						options={(chas.data ?? []).map((c) => ({ value: c.name }))}
						placeholder="Search CHAs…"
						disabled={chaLocked}
					/>
				</Field>
				<Field label="Port of loading">
					<SearchSelect
						value={form.port_of_loading}
						onChange={(v) => set('port_of_loading', v)}
						options={portOpts}
						placeholder="Search ports…"
					/>
				</Field>
				<Field label="Port of discharge">
					<SearchSelect
						value={form.port_of_discharge}
						onChange={(v) => set('port_of_discharge', v)}
						options={portOpts}
						placeholder="Search ports…"
					/>
				</Field>
				<Field label="Final destination">
					<TextInput value={form.final_destination} onChange={(v) => set('final_destination', v)} />
				</Field>
				<Field label="Letter of credit">
					<SearchSelect
						value={form.letter_of_credit}
						onChange={(v) => set('letter_of_credit', v)}
						options={(lcs.data ?? []).map((r) => ({ value: r.name, label: r.lc_number || r.name }))}
						placeholder="Search LCs…"
					/>
				</Field>

				<div className="span2 fdivider">Invoice &amp; terms</div>
				{!isMerchanting(form.trade_type) && (
					<Field label="GST export mode" hint="Drives the invoice declaration">
						<SelectInput
							value={form.gst_export_mode}
							onChange={(v) => set('gst_export_mode', v)}
							options={GST_EXPORT_MODES.map((m) => ({ value: m }))}
						/>
					</Field>
				)}
				{!isMerchanting(form.trade_type) && form.gst_export_mode === 'On payment of IGST' && (
					<Field label="IGST rate %">
						<TextInput type="number" mono value={form.igst_rate} onChange={(v) => set('igst_rate', v)} />
					</Field>
				)}
				{!isMerchanting(form.trade_type) && form.gst_export_mode === 'On payment of IGST' && (
					<Field label="INR conversion rate" hint="For the INR taxable value on the invoice">
						<TextInput type="number" mono value={form.inr_rate} onChange={(v) => set('inr_rate', v)} />
					</Field>
				)}
				<Field label="Freight" hint="Deal currency — adds to the CFR/CIF total">
					<TextInput type="number" mono value={form.freight_amount} onChange={(v) => set('freight_amount', v)} />
				</Field>
				<Field label="Insurance" hint="Deal currency — adds to the CIF total">
					<TextInput type="number" mono value={form.insurance_amount} onChange={(v) => set('insurance_amount', v)} />
				</Field>
				<Field label="Buyer's order no">
					<TextInput value={form.buyer_order_no} onChange={(v) => set('buyer_order_no', v)} />
				</Field>
				<Field label="Buyer's order date">
					<TextInput type="date" value={form.buyer_order_date} onChange={(v) => set('buyer_order_date', v)} />
				</Field>
				<div className="span2">
					<CheckInput
						label='Consignee "to order" (negotiable B/L)'
						checked={form.consignee_to_order}
						onChange={(v) => set('consignee_to_order', v)}
					/>
				</div>
				{!form.consignee_to_order && (
					<Field label="Consignee name" hint="Leave blank to use the buyer">
						<TextInput value={form.consignee_name} onChange={(v) => set('consignee_name', v)} />
					</Field>
				)}
				{!form.consignee_to_order && (
					<Field label="Consignee address">
						<TextArea value={form.consignee_address} onChange={(v) => set('consignee_address', v)} rows={2} />
					</Field>
				)}
				<div className="span2">
					<Field label="Notify party" hint="Shown on the shipping instruction / carrier document">
						<TextArea value={form.notify_party} onChange={(v) => set('notify_party', v)} rows={2} />
					</Field>
				</div>
				<div className="span2">
					<Field label="Notes">
						<TextArea value={form.notes} onChange={(v) => set('notes', v)} rows={2} />
					</Field>
				</div>
				{!isMerchanting(form.trade_type) && (
					<>
						<div className="span2 fdivider">Export incentives</div>
						<Field label="RoDTEP">
							<CheckInput
								checked={form.claim_rodtep}
								onChange={(v) => set('claim_rodtep', v)}
								label="Claim RoDTEP"
							/>
							{form.claim_rodtep && (
								<TextInput
									type="number"
									value={form.rodtep_rate_pct}
									onChange={(v) => set('rodtep_rate_pct', v)}
									placeholder="Rate % of FOB (optional)"
								/>
							)}
						</Field>
						<Field label="Duty Drawback">
							<CheckInput
								checked={form.claim_drawback}
								onChange={(v) => set('claim_drawback', v)}
								label="Claim Drawback"
							/>
							{form.claim_drawback && (
								<TextInput
									type="number"
									value={form.drawback_rate_pct}
									onChange={(v) => set('drawback_rate_pct', v)}
									placeholder="Rate % of FOB (optional)"
								/>
							)}
						</Field>
						<div className="span2 sub" style={{ margin: 0 }}>
							A Pending claim opens automatically when the Commercial Invoice is generated.
						</div>
					</>
				)}
			</div>
			{lines.length > 0 && (
				<>
					<div className="reqhead" style={{ gridTemplateColumns: SHIP_LINE_GRID }}>
						<span>Item</span>
						<span>Qty</span>
						<span>Batch</span>
						<span>Pack</span>
					</div>
					{lines.map((l, i) => (
						<div className="reqrow" key={l.name} style={{ gridTemplateColumns: SHIP_LINE_GRID }}>
							<div>
								<div className="c1">{items[i]?.item_name}</div>
								<div className="c2">{items[i]?.sales_order}</div>
							</div>
							<TextInput type="number" mono value={l.qty} onChange={(v) => setLine(i, { qty: v })} />
							<TextInput mono value={l.batch_no} onChange={(v) => setLine(i, { batch_no: v })} />
							<TextInput
								value={l.pack_description}
								onChange={(v) => setLine(i, { pack_description: v })}
							/>
						</div>
					))}
				</>
			)}
			<div className="formfoot">
				{err && <span className="ferr">{err}</span>}
				<span className="spacer" />
				<button type="button" className="btn" onClick={onClose}>
					Cancel
				</button>
				<button type="button" className="btn primary" disabled={saving} onClick={() => void onSave()}>
					{saving ? 'Saving…' : 'Save changes'}
				</button>
			</div>
		</Modal>
	);
}
