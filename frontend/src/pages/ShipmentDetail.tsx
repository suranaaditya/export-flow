import { useState, type ReactNode } from 'react';
import { useFrappeGetCall, useFrappePostCall, useFrappeUpdateDoc } from 'frappe-react-sdk';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { DocumentChecklist } from '@/components/DocumentChecklist';
import { Icon } from '@/components/Icon';
import { Card, CHead, EmptyMsg, Facts, LRow, Modal, Tag } from '@/components/ui';
import { CheckInput, Field, TextArea, TextInput } from '@/components/form';
import {
	API,
	lcIsOpen,
	lcTone,
	parseServerError,
	urgencyLabel,
	urgencyTone,
	type ShipmentDetailData,
} from '@/lib/api';
import { daysUntil, fmtDate } from '@/lib/format';

type ShipmentDoc = ShipmentDetailData['shipment'];

/** Milestones whose arrival means the goods have left the country. */

export function ShipmentDetail() {
	const { id = '' } = useParams<{ id: string }>();
	const navigate = useNavigate();

	const { data, error, isLoading, mutate } = useFrappeGetCall<{ message: ShipmentDetailData }>(
		API.shipmentDetail,
		{ name: id },
	);
	const { call: setMilestone, loading: completing } = useFrappePostCall(API.setMilestone);
	const [actionErr, setActionErr] = useState<string | null>(null);
	const [editing, setEditing] = useState(false);

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

	const { shipment, milestones, items, lc, sales_orders } = detail;
	const isAir = shipment.mode === 'Air';

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
		setActionErr(null);
		try {
			await setMilestone({ shipment: id, row: nextPending.name, completed: 1 });
			mutate();
		} catch (e) {
			setActionErr(parseServerError(e));
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
				<span style={{ marginTop: 9 }}>
					<Tag tone={headTone}>{shipment.current_milestone}</Tag>
				</span>
				<span className="spacer" />
				<button className="btn" onClick={() => setEditing(true)}>
					<Icon name="ship" size={15} /> Update voyage
				</button>
				{nextPending && (
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

					<DocumentChecklist shipment={id} />
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
				</div>
			</div>

			{editing && (
				<EditVoyageModal
					id={id}
					shipment={shipment}
					onClose={() => setEditing(false)}
					onSaved={() => {
						mutate();
						setEditing(false);
					}}
				/>
			)}

			<footer>
				<b>ExportFlow</b> · DUX Digitech
			</footer>
		</main>
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
			shipping_bill_number: form.shipping_bill_number,
			shipping_bill_date: orNull(form.shipping_bill_date),
			leo_date: orNull(form.leo_date),
			egm_number: form.egm_number,
			egm_date: orNull(form.egm_date),
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
				<Field label="LEO date">
					<TextInput type="date" value={form.leo_date} onChange={(v) => set('leo_date', v)} />
				</Field>
				<Field label="EGM number">
					<TextInput mono value={form.egm_number} onChange={(v) => set('egm_number', v)} />
				</Field>
				<Field label="EGM date">
					<TextInput type="date" value={form.egm_date} onChange={(v) => set('egm_date', v)} />
				</Field>
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
