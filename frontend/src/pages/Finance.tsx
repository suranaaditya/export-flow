import { useState } from 'react';
import { useFrappeCreateDoc, useFrappeGetCall, useFrappeUpdateDoc } from 'frappe-react-sdk';
import { Icon, type IconName } from '@/components/Icon';
import { Field, SelectInput, TextArea, TextInput } from '@/components/form';
import { Card, CHead, EmptyMsg, Modal, Tag } from '@/components/ui';
import {
	API,
	INCENTIVE_STATUSES,
	REALIZATION_STATUSES,
	incentiveTone,
	realizationTone,
	parseServerError,
	type FinanceWorkspaceData,
	type IncentiveRow,
	type IncentiveStatus,
	type RealizationRow,
	type RealizationStatus,
} from '@/lib/api';
import { fmtDate, fmtMoney } from '@/lib/format';

const inr = (v: number | null | undefined) => (v == null ? '—' : fmtMoney(v, 'INR'));

function Kpi({ icon, label, value, detail, tone }: { icon: IconName; label: string; value: string; detail: string; tone?: 'warn' | 'bad' }) {
	return (
		<div className="card kpi">
			<div className="lb">
				<Icon name={icon} size={14} /> {label}
			</div>
			<div className="v">{value}</div>
			<div className="d">{tone ? <span className={tone}>{detail}</span> : detail}</div>
		</div>
	);
}

export function Finance() {
	const { data, error, isLoading, mutate } = useFrappeGetCall<{ message: FinanceWorkspaceData }>(
		API.financeWorkspace,
		undefined,
	);
	const [incModal, setIncModal] = useState<'new' | IncentiveRow | null>(null);
	const [relModal, setRelModal] = useState<'new' | RealizationRow | null>(null);

	const d = data?.message;
	const kpis = d?.kpis ?? {};
	const canIncW = d?.can.incentive_write;
	const canRelW = d?.can.realization_write;
	const loading = isLoading || !d;
	const dash = (s: string) => (loading ? '—' : s);

	return (
		<main>
			<div className="eyebrow">Finance · Incentives & realization</div>
			<h1>
				Export <em>finance</em>
			</h1>
			<div className="sub">
				RoDTEP & drawback incentives and bank realization (FIRC → eBRC) — the money trail that
				closes every export.
			</div>

			<div className="kpis">
				<Kpi icon="shield" label="Incentives earned" value={inr(kpis.incentive_total)} detail={dash(kpis.incentive_pending ? `${inr(kpis.incentive_pending)} pending` : 'RoDTEP + drawback')} tone={kpis.incentive_pending ? 'warn' : undefined} />
				<Kpi icon="banknote" label="Proceeds realized" value={inr(kpis.realized)} detail={dash(`${kpis.open_count ?? 0} still open`)} />
				<Kpi icon="warning" label="Overdue" value={loading ? '—' : String(kpis.overdue_count ?? 0)} detail="past FEMA window" tone={kpis.overdue_count ? 'bad' : undefined} />
				<Kpi icon="file-text" label="Realizations" value={loading ? '—' : String(d?.realizations.length ?? 0)} detail="export invoices tracked" />
			</div>

			{error ? (
				<Card>
					<div className="ferr" style={{ padding: '18px 20px' }}>{parseServerError(error)}</div>
				</Card>
			) : (
				<div className="stack">
					<Card accent>
						<CHead
							icon="shield"
							title="Export incentives"
							count={d ? `${d.incentives.length}` : undefined}
							action={canIncW ? <a href="#" onClick={(e) => { e.preventDefault(); setIncModal('new'); }}>New incentive</a> : undefined}
						/>
						{isLoading ? (
							<div className="sub" style={{ padding: '14px 18px' }}>Loading…</div>
						) : !d || d.incentives.length === 0 ? (
							<EmptyMsg title="No incentives yet" text="RoDTEP and drawback claims per shipment land here." />
						) : (
							<table className={canIncW ? 'clickable' : undefined}>
								<thead>
									<tr><th>Scheme</th><th>Shipment</th><th>SB no</th><th>Amount</th><th>Scroll / scrip</th><th>Status</th></tr>
								</thead>
								<tbody>
									{d.incentives.map((i) => (
										<tr key={i.name} onClick={canIncW ? () => setIncModal(i) : undefined}>
											<td className="c1">{i.scheme}</td>
											<td>{i.shipment ? <span className="id id-sm">{i.shipment}</span> : <span className="dim">—</span>}</td>
											<td className="dim">{i.shipping_bill_no ?? '—'}</td>
											<td className="num">{inr(i.amount)}</td>
											<td className="dim">{i.scrip_number || i.scroll_number || '—'}</td>
											<td><Tag tone={incentiveTone(i.status)}>{i.status}</Tag></td>
										</tr>
									))}
								</tbody>
							</table>
						)}
					</Card>

					<Card accent>
						<CHead
							icon="banknote"
							title="Bank realization"
							count={d ? `${d.realizations.length}` : undefined}
							action={canRelW ? <a href="#" onClick={(e) => { e.preventDefault(); setRelModal('new'); }}>New realization</a> : undefined}
						/>
						{isLoading ? (
							<div className="sub" style={{ padding: '14px 18px' }}>Loading…</div>
						) : !d || d.realizations.length === 0 ? (
							<EmptyMsg title="No realizations yet" text="Export-proceeds tracking (FIRC, eBRC, due dates) appears here." />
						) : (
							<table className={canRelW ? 'clickable' : undefined}>
								<thead>
									<tr><th>Invoice</th><th>Shipment</th><th>Received</th><th>Due</th><th>eBRC</th><th>Status</th></tr>
								</thead>
								<tbody>
									{d.realizations.map((r) => (
										<tr key={r.name} onClick={canRelW ? () => setRelModal(r) : undefined}>
											<td className="id">{r.export_invoice ?? r.name}</td>
											<td>{r.shipment ? <span className="id id-sm">{r.shipment}</span> : <span className="dim">—</span>}</td>
											<td className="num">{inr(r.amount_received_inr)}</td>
											<td className="dim">{r.due_date ? fmtDate(r.due_date) : '—'}</td>
											<td className="dim">{r.ebrc_number ?? '—'}</td>
											<td><Tag tone={realizationTone(r)}>{r.overdue && r.status !== 'Overdue' ? `Overdue · ${r.status}` : r.status}</Tag></td>
										</tr>
									))}
								</tbody>
							</table>
						)}
					</Card>
				</div>
			)}

			{incModal !== null && (
				<IncentiveModal
					record={incModal === 'new' ? null : incModal}
					onClose={() => setIncModal(null)}
					onSaved={() => { setIncModal(null); mutate(); }}
				/>
			)}
			{relModal !== null && (
				<RealizationModal
					record={relModal === 'new' ? null : relModal}
					onClose={() => setRelModal(null)}
					onSaved={() => { setRelModal(null); mutate(); }}
				/>
			)}

			<footer><b>ExportFlow</b> · DUX Digitech</footer>
		</main>
	);
}

function IncentiveModal({ record, onClose, onSaved }: { record: IncentiveRow | null; onClose: () => void; onSaved: () => void }) {
	const isNew = record === null;
	const [form, setForm] = useState({
		scheme: record?.scheme ?? 'RoDTEP',
		shipment: record?.shipment ?? '',
		status: (record?.status ?? 'Pending') as IncentiveStatus,
		shipping_bill_no: record?.shipping_bill_no ?? '',
		fob_value: record?.fob_value != null ? String(record.fob_value) : '',
		rate_pct: record?.rate_pct != null ? String(record.rate_pct) : '',
		amount: record?.amount != null ? String(record.amount) : '',
		scroll_number: record?.scroll_number ?? '',
		scrip_number: record?.scrip_number ?? '',
		drawback_serial: record?.drawback_serial ?? '',
		amount_received: record?.amount_received != null ? String(record.amount_received) : '',
		remarks: record?.remarks ?? '',
	});
	const [err, setErr] = useState<string | null>(null);
	const { createDoc, loading: creating } = useFrappeCreateDoc();
	const { updateDoc, loading: updating } = useFrappeUpdateDoc();
	const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) => setForm((f) => ({ ...f, [k]: v }));

	async function onSave() {
		setErr(null);
		const payload = {
			scheme: form.scheme,
			shipment: form.shipment || null,
			status: form.status,
			shipping_bill_no: form.shipping_bill_no,
			fob_value: Number(form.fob_value) || 0,
			rate_pct: Number(form.rate_pct) || 0,
			amount: Number(form.amount) || 0,
			scroll_number: form.scroll_number,
			scrip_number: form.scrip_number,
			drawback_serial: form.drawback_serial,
			amount_received: Number(form.amount_received) || 0,
			remarks: form.remarks,
		};
		// leave amount unset (auto-compute) only when truly blank; a typed 0 sticks
		if (form.amount.trim() === '') (payload as Record<string, unknown>).amount = null;
		try {
			if (isNew) await createDoc('Export Incentive', payload);
			else await updateDoc('Export Incentive', record.name, payload);
			onSaved();
		} catch (e) {
			setErr(parseServerError(e));
		}
	}

	return (
		<Modal title={isNew ? 'New incentive' : record.name} icon="shield" onClose={onClose}>
			<div className="formgrid">
				<Field label="Scheme" required>
					<SelectInput value={form.scheme} onChange={(v) => set('scheme', v as 'RoDTEP' | 'Duty Drawback')} options={[{ value: 'RoDTEP' }, { value: 'Duty Drawback' }]} />
				</Field>
				<Field label="Status">
					<SelectInput value={form.status} onChange={(v) => set('status', v as IncentiveStatus)} options={INCENTIVE_STATUSES.map((s) => ({ value: s }))} />
				</Field>
				<Field label="Shipment">
					<TextInput value={form.shipment} onChange={(v) => set('shipment', v)} placeholder="SHP-…" mono />
				</Field>
				<Field label="Shipping bill no">
					<TextInput mono value={form.shipping_bill_no} onChange={(v) => set('shipping_bill_no', v)} />
				</Field>
				<Field label="FOB value (INR)">
					<TextInput type="number" mono value={form.fob_value} onChange={(v) => set('fob_value', v)} />
				</Field>
				<Field label="Applied rate %">
					<TextInput type="number" mono value={form.rate_pct} onChange={(v) => set('rate_pct', v)} />
				</Field>
				<Field label="Incentive amount (INR)" hint="Auto from FOB × rate if left blank">
					<TextInput type="number" mono value={form.amount} onChange={(v) => set('amount', v)} />
				</Field>
				{form.scheme === 'RoDTEP' ? (
					<>
						<Field label="Scroll number">
							<TextInput mono value={form.scroll_number} onChange={(v) => set('scroll_number', v)} />
						</Field>
						<Field label="Scrip number">
							<TextInput mono value={form.scrip_number} onChange={(v) => set('scrip_number', v)} />
						</Field>
					</>
				) : (
					<>
						<Field label="Drawback serial / book no">
							<TextInput mono value={form.drawback_serial} onChange={(v) => set('drawback_serial', v)} />
						</Field>
						<Field label="Amount received (INR)">
							<TextInput type="number" mono value={form.amount_received} onChange={(v) => set('amount_received', v)} />
						</Field>
					</>
				)}
				<div className="span2">
					<Field label="Remarks">
						<TextArea value={form.remarks} onChange={(v) => set('remarks', v)} rows={2} />
					</Field>
				</div>
			</div>
			<div className="formfoot">
				{err && <span className="ferr">{err}</span>}
				<span className="spacer" />
				<button type="button" className="btn" onClick={onClose}>Cancel</button>
				<button type="button" className="btn primary" disabled={creating || updating} onClick={() => void onSave()}>
					{creating || updating ? 'Saving…' : isNew ? 'Create' : 'Save'}
				</button>
			</div>
		</Modal>
	);
}

function RealizationModal({ record, onClose, onSaved }: { record: RealizationRow | null; onClose: () => void; onSaved: () => void }) {
	const isNew = record === null;
	const [form, setForm] = useState({
		export_invoice: record?.export_invoice ?? '',
		shipment: record?.shipment ?? '',
		status: (record?.status ?? 'Awaiting Realization') as RealizationStatus,
		currency: record?.currency ?? '',
		invoice_value: record?.invoice_value != null ? String(record.invoice_value) : '',
		export_date: record?.export_date ?? '',
		ad_bank: record?.ad_bank ?? '',
		fbc_number: record?.fbc_number ?? '',
		firc_no: record?.firc_no ?? '',
		remittance_date: record?.remittance_date ?? '',
		amount_received: record?.amount_received != null ? String(record.amount_received) : '',
		amount_received_inr: record?.amount_received_inr != null ? String(record.amount_received_inr) : '',
		bank_charges: record?.bank_charges != null ? String(record.bank_charges) : '',
		ebrc_number: record?.ebrc_number ?? '',
		ebrc_date: record?.ebrc_date ?? '',
		remarks: record?.remarks ?? '',
	});
	const [err, setErr] = useState<string | null>(null);
	const { createDoc, loading: creating } = useFrappeCreateDoc();
	const { updateDoc, loading: updating } = useFrappeUpdateDoc();
	const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) => setForm((f) => ({ ...f, [k]: v }));

	async function onSave() {
		setErr(null);
		const payload = {
			export_invoice: form.export_invoice,
			shipment: form.shipment || null,
			status: form.status,
			currency: form.currency || null,
			invoice_value: Number(form.invoice_value) || 0,
			export_date: form.export_date || null,
			ad_bank: form.ad_bank,
			fbc_number: form.fbc_number,
			firc_no: form.firc_no,
			remittance_date: form.remittance_date || null,
			amount_received: Number(form.amount_received) || 0,
			amount_received_inr: Number(form.amount_received_inr) || 0,
			bank_charges: Number(form.bank_charges) || 0,
			ebrc_number: form.ebrc_number,
			ebrc_date: form.ebrc_date || null,
			remarks: form.remarks,
		};
		try {
			if (isNew) await createDoc('Export Realization', payload);
			else await updateDoc('Export Realization', record.name, payload);
			onSaved();
		} catch (e) {
			setErr(parseServerError(e));
		}
	}

	return (
		<Modal title={isNew ? 'New realization' : record.name} icon="banknote" onClose={onClose}>
			<div className="formgrid">
				<Field label="Export invoice"><TextInput mono value={form.export_invoice} onChange={(v) => set('export_invoice', v)} /></Field>
				<Field label="Status"><SelectInput value={form.status} onChange={(v) => set('status', v as RealizationStatus)} options={REALIZATION_STATUSES.map((s) => ({ value: s }))} /></Field>
				<Field label="Shipment"><TextInput mono value={form.shipment} onChange={(v) => set('shipment', v)} placeholder="SHP-…" /></Field>
				<Field label="Currency" hint="INR uses the 18-month FEMA window"><SelectInput value={form.currency} onChange={(v) => set('currency', v)} options={[{ value: '' }, { value: 'USD' }, { value: 'EUR' }, { value: 'INR' }]} /></Field>
				<Field label="Invoice value (FCY)"><TextInput type="number" mono value={form.invoice_value} onChange={(v) => set('invoice_value', v)} /></Field>
				<Field label="Export date" hint="Starts the FEMA clock"><TextInput type="date" value={form.export_date} onChange={(v) => set('export_date', v)} /></Field>
				<Field label="AD bank"><TextInput value={form.ad_bank} onChange={(v) => set('ad_bank', v)} /></Field>
				<Field label="FBC / FIBCD no"><TextInput mono value={form.fbc_number} onChange={(v) => set('fbc_number', v)} /></Field>
				<Field label="FIRC / IRM no"><TextInput mono value={form.firc_no} onChange={(v) => set('firc_no', v)} /></Field>
				<Field label="Remittance date"><TextInput type="date" value={form.remittance_date} onChange={(v) => set('remittance_date', v)} /></Field>
				<Field label="Amount received (FCY)"><TextInput type="number" mono value={form.amount_received} onChange={(v) => set('amount_received', v)} /></Field>
				<Field label="Amount received (INR)"><TextInput type="number" mono value={form.amount_received_inr} onChange={(v) => set('amount_received_inr', v)} /></Field>
				<Field label="Bank charges (FCY)"><TextInput type="number" mono value={form.bank_charges} onChange={(v) => set('bank_charges', v)} /></Field>
				<Field label="eBRC number"><TextInput mono value={form.ebrc_number} onChange={(v) => set('ebrc_number', v)} /></Field>
				<Field label="eBRC date"><TextInput type="date" value={form.ebrc_date} onChange={(v) => set('ebrc_date', v)} /></Field>
				<div className="span2"><Field label="Remarks"><TextArea value={form.remarks} onChange={(v) => set('remarks', v)} rows={2} /></Field></div>
			</div>
			<div className="formfoot">
				{err && <span className="ferr">{err}</span>}
				<span className="spacer" />
				<button type="button" className="btn" onClick={onClose}>Cancel</button>
				<button type="button" className="btn primary" disabled={creating || updating} onClick={() => void onSave()}>
					{creating || updating ? 'Saving…' : isNew ? 'Create' : 'Save'}
				</button>
			</div>
		</Modal>
	);
}
