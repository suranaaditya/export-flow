import { useState } from 'react';
import { useFrappeCreateDoc, useFrappeDeleteDoc, useFrappeUpdateDoc } from 'frappe-react-sdk';
import { Field, SelectInput, TextArea, TextInput } from '@/components/form';
import { Modal } from '@/components/ui';
import {
	INCENTIVE_STATUSES,
	REALIZATION_STATUSES,
	parseServerError,
	type IncentiveRow,
	type IncentiveStatus,
	type RealizationRow,
	type RealizationStatus,
} from '@/lib/api';

/** Seed for creating an incentive from a shipment (FOB basis pre-filled; the
 *  rate stays manual, the amount auto-computes server-side). */
export interface IncentiveSeed {
	shipment: string;
	fob_value?: number | null;
}

/** Seed for creating a realization from a shipment (invoice value + currency +
 *  export date pre-filled; customer and FEMA due date are derived on save). */
export interface RealizationSeed {
	shipment: string;
	currency?: string | null;
	invoice_value?: number | null;
	export_date?: string | null;
}

const numStr = (v: number | null | undefined) => (v != null ? String(v) : '');

/** Shared modal footer. While editing, a permitted user gets a Delete button
 *  that swaps the footer to an inline two-step confirm (no accidental loss).
 *  Used by both finance modals, so delete works on the Finance screen and the
 *  shipment finance card alike. */
function FinanceModalFoot({
	isNew,
	noun,
	err,
	busy,
	saving,
	canDelete,
	confirmDelete,
	setConfirmDelete,
	deleting,
	onClose,
	onSave,
	onDelete,
}: {
	isNew: boolean;
	noun: string;
	err: string | null;
	busy: boolean;
	saving: boolean;
	canDelete: boolean;
	confirmDelete: boolean;
	setConfirmDelete: (v: boolean) => void;
	deleting: boolean;
	onClose: () => void;
	onSave: () => void;
	onDelete: () => void;
}) {
	if (confirmDelete) {
		return (
			<div className="formfoot">
				<span className="fconfirm">Delete this {noun} permanently? This can’t be undone.</span>
				<span className="spacer" />
				<button type="button" className="btn" disabled={deleting} onClick={() => setConfirmDelete(false)}>Keep</button>
				<button type="button" className="btn danger" disabled={deleting} onClick={onDelete}>{deleting ? 'Deleting…' : 'Yes, delete'}</button>
			</div>
		);
	}
	return (
		<div className="formfoot">
			{err && <span className="ferr">{err}</span>}
			{!isNew && canDelete && (
				<button type="button" className="btn" disabled={busy} onClick={() => setConfirmDelete(true)}>Delete</button>
			)}
			<span className="spacer" />
			<button type="button" className="btn" onClick={onClose}>Cancel</button>
			<button type="button" className="btn primary" disabled={busy} onClick={onSave}>
				{saving ? 'Saving…' : isNew ? 'Create' : 'Save'}
			</button>
		</div>
	);
}

export function IncentiveModal({
	record,
	seed,
	lockShipment,
	canDelete,
	onClose,
	onSaved,
	onDeleted,
}: {
	record: IncentiveRow | null;
	seed?: IncentiveSeed | null;
	lockShipment?: boolean;
	canDelete?: boolean;
	onClose: () => void;
	onSaved: () => void;
	onDeleted?: () => void;
}) {
	const isNew = record === null;
	const [form, setForm] = useState({
		scheme: record?.scheme ?? 'RoDTEP',
		shipment: record?.shipment ?? seed?.shipment ?? '',
		status: (record?.status ?? 'Pending') as IncentiveStatus,
		shipping_bill_no: record?.shipping_bill_no ?? '',
		fob_value: record?.fob_value != null ? String(record.fob_value) : numStr(seed?.fob_value),
		rate_pct: record?.rate_pct != null ? String(record.rate_pct) : '',
		amount: record?.amount != null ? String(record.amount) : '',
		scroll_number: record?.scroll_number ?? '',
		scrip_number: record?.scrip_number ?? '',
		drawback_serial: record?.drawback_serial ?? '',
		amount_received: record?.amount_received != null ? String(record.amount_received) : '',
		remarks: record?.remarks ?? '',
	});
	const [err, setErr] = useState<string | null>(null);
	const [confirmDelete, setConfirmDelete] = useState(false);
	const { createDoc, loading: creating } = useFrappeCreateDoc();
	const { updateDoc, loading: updating } = useFrappeUpdateDoc();
	const { deleteDoc, loading: deleting } = useFrappeDeleteDoc();
	const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) => setForm((f) => ({ ...f, [k]: v }));

	async function onDelete() {
		if (!record) return;
		setErr(null);
		try {
			await deleteDoc('Export Incentive', record.name);
			(onDeleted ?? onSaved)();
		} catch (e) {
			setConfirmDelete(false);
			setErr(parseServerError(e));
		}
	}

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
					<TextInput value={form.shipment} onChange={(v) => set('shipment', v)} placeholder="SHP-…" mono disabled={lockShipment} />
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
			<FinanceModalFoot
				isNew={isNew}
				noun="incentive"
				err={err}
				busy={creating || updating || deleting}
				saving={creating || updating}
				canDelete={!!canDelete}
				confirmDelete={confirmDelete}
				setConfirmDelete={setConfirmDelete}
				deleting={deleting}
				onClose={onClose}
				onSave={() => void onSave()}
				onDelete={() => void onDelete()}
			/>
		</Modal>
	);
}

export function RealizationModal({
	record,
	seed,
	lockShipment,
	canDelete,
	onClose,
	onSaved,
	onDeleted,
}: {
	record: RealizationRow | null;
	seed?: RealizationSeed | null;
	lockShipment?: boolean;
	canDelete?: boolean;
	onClose: () => void;
	onSaved: () => void;
	onDeleted?: () => void;
}) {
	const isNew = record === null;
	const [form, setForm] = useState({
		export_invoice: record?.export_invoice ?? '',
		shipment: record?.shipment ?? seed?.shipment ?? '',
		status: (record?.status ?? 'Awaiting Realization') as RealizationStatus,
		currency: record?.currency ?? seed?.currency ?? '',
		invoice_value:
			record?.invoice_value != null ? String(record.invoice_value) : numStr(seed?.invoice_value),
		export_date: record?.export_date ?? seed?.export_date ?? '',
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
	const [confirmDelete, setConfirmDelete] = useState(false);
	const { createDoc, loading: creating } = useFrappeCreateDoc();
	const { updateDoc, loading: updating } = useFrappeUpdateDoc();
	const { deleteDoc, loading: deleting } = useFrappeDeleteDoc();
	const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) => setForm((f) => ({ ...f, [k]: v }));

	async function onDelete() {
		if (!record) return;
		setErr(null);
		try {
			await deleteDoc('Export Realization', record.name);
			(onDeleted ?? onSaved)();
		} catch (e) {
			setConfirmDelete(false);
			setErr(parseServerError(e));
		}
	}

	// always offer the common currencies plus whatever the deal / record uses,
	// so a seeded currency outside the default trio (e.g. ZAR, AED) stays selectable
	const currencyOptions = [...new Set(['', 'USD', 'EUR', 'INR', form.currency].filter((c) => c != null))].map(
		(value) => ({ value }),
	);

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
				<Field label="Shipment"><TextInput mono value={form.shipment} onChange={(v) => set('shipment', v)} placeholder="SHP-…" disabled={lockShipment} /></Field>
				<Field label="Currency" hint="INR uses the 18-month FEMA window"><SelectInput value={form.currency} onChange={(v) => set('currency', v)} options={currencyOptions} /></Field>
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
			<FinanceModalFoot
				isNew={isNew}
				noun="realization"
				err={err}
				busy={creating || updating || deleting}
				saving={creating || updating}
				canDelete={!!canDelete}
				confirmDelete={confirmDelete}
				setConfirmDelete={setConfirmDelete}
				deleting={deleting}
				onClose={onClose}
				onSave={() => void onSave()}
				onDelete={() => void onDelete()}
			/>
		</Modal>
	);
}
