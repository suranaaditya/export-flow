import { useMemo, useState } from 'react';
import { useFrappeCreateDoc, useFrappeDeleteDoc, useFrappeGetCall, useFrappeUpdateDoc } from 'frappe-react-sdk';
import { Field, SelectInput, TextArea, TextInput } from '@/components/form';
import { Card, CHead, EmptyMsg, Modal, Tag } from '@/components/ui';
import { API, parseServerError, type ForwardContract, type FxExposure } from '@/lib/api';
import { fmtDate, fmtMoney } from '@/lib/format';

const CURRENCIES = ['USD', 'EUR', 'GBP', 'AED', 'JPY', 'CNY', 'INR'];
const STATUSES = ['Open', 'Partially Utilized', 'Fully Utilized', 'Matured', 'Cancelled'];

function statusTone(s: string): 'ok' | 'pend' | 'err' {
	if (s === 'Fully Utilized') return 'ok';
	if (s === 'Cancelled' || s === 'Matured') return 'err';
	return 'pend';
}
const fcy = (ccy: string, n: number) => `${ccy} ${Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;

export function ForwardContracts() {
	const { data, error, isLoading, mutate } = useFrappeGetCall<{
		message: { contracts: ForwardContract[]; exposure: FxExposure[]; can: { write: boolean; delete: boolean } };
	}>(API.forwardContracts, undefined);
	const d = data?.message;
	const contracts = useMemo(() => d?.contracts ?? [], [d]);
	const exposure = d?.exposure ?? [];
	const can = d?.can ?? { write: false, delete: false };
	const [editing, setEditing] = useState<ForwardContract | 'new' | null>(null);

	return (
		<main>
			<div className="eyebrow">Treasury · FX</div>
			<h1>
				Forward <em>contracts</em>
			</h1>
			<div className="sub">
				Hedge foreign-currency export proceeds at a locked rate — realizations draw down against a booked forward.
			</div>

			{isLoading ? (
				<div className="sub" style={{ marginTop: 22 }}>Loading…</div>
			) : error ? (
				<div className="ferr" style={{ marginTop: 22 }}>{parseServerError(error)}</div>
			) : (
				<>
					<Card accent>
						<CHead icon="shield" title="FX exposure" count={`${exposure.length} ${exposure.length === 1 ? 'currency' : 'currencies'}`} />
						{exposure.length === 0 ? (
							<EmptyMsg title="No open exposure" text="Open export receivables and forward cover appear here by currency." />
						) : (
							<div className="reptable">
								<table>
									<thead>
										<tr>
											<th>Currency</th>
											<th className="num">Open receivable</th>
											<th className="num">Forward cover</th>
											<th className="num">Unhedged</th>
											<th style={{ width: 180 }}>Hedged</th>
										</tr>
									</thead>
									<tbody>
										{exposure.map((e) => (
											<tr key={e.currency}>
												<td><b>{e.currency}</b></td>
												<td className="num">{fcy(e.currency, e.receivable)}</td>
												<td className="num">{fcy(e.currency, e.hedged)}</td>
												<td className="num" style={{ color: e.open_exposure > 0 ? 'var(--err)' : undefined }}>
													{fcy(e.currency, e.open_exposure)}
												</td>
												<td>
													<div className="hbar">
														<i style={{ width: `${Math.min(100, e.hedge_pct ?? 0)}%` }} />
														<span>{e.hedge_pct == null ? '—' : `${e.hedge_pct}%`}</span>
													</div>
												</td>
											</tr>
										))}
									</tbody>
								</table>
							</div>
						)}
					</Card>

					<Card>
						<CHead
							icon="banknote"
							title="Forward contracts"
							count={contracts.length}
							action={can.write ? <a href="#" onClick={(ev) => { ev.preventDefault(); setEditing('new'); }}>+ Book forward</a> : undefined}
						/>
						{contracts.length === 0 ? (
							<EmptyMsg title="No forward contracts" text="Book a forward to lock the INR value of your export proceeds." />
						) : (
							<div className="reptable">
								<table>
									<thead>
										<tr>
											<th>Contract no.</th>
											<th>Bank</th>
											<th>Ccy</th>
											<th className="num">Amount</th>
											<th className="num">Rate</th>
											<th className="num">Utilized</th>
											<th className="num">Outstanding</th>
											<th>Maturity</th>
											<th>Status</th>
										</tr>
									</thead>
									<tbody>
										{contracts.map((c) => (
											<tr key={c.name} style={{ cursor: can.write ? 'pointer' : undefined }} onClick={() => can.write && setEditing(c)}>
												<td><span className="id id-sm">{c.contract_no}</span></td>
												<td>{c.ad_bank ?? '—'}</td>
												<td>{c.currency}</td>
												<td className="num">{Number(c.contract_amount).toLocaleString('en-IN')}</td>
												<td className="num">{Number(c.forward_rate).toLocaleString('en-IN', { maximumFractionDigits: 4 })}</td>
												<td className="num">{Number(c.utilized_amount).toLocaleString('en-IN')}</td>
												<td className="num">{Number(c.outstanding_amount).toLocaleString('en-IN')}</td>
												<td>
													{c.maturity_date ? fmtDate(c.maturity_date) : '—'}
													{c.days_to_maturity != null && c.days_to_maturity >= 0 && c.days_to_maturity <= 14 && c.status !== 'Fully Utilized' && c.status !== 'Cancelled' ? (
														<span className="dim" style={{ color: 'var(--err)' }}> · {c.days_to_maturity}d</span>
													) : null}
												</td>
												<td><Tag tone={statusTone(c.status)}>{c.status}</Tag></td>
											</tr>
										))}
									</tbody>
								</table>
							</div>
						)}
					</Card>
				</>
			)}

			{editing && (
				<ForwardModal
					record={editing === 'new' ? null : editing}
					canDelete={can.delete}
					onClose={() => setEditing(null)}
					onSaved={() => { mutate(); setEditing(null); }}
				/>
			)}

			<footer>
				<b>ExportFlow</b> · DUX Digitech
			</footer>
		</main>
	);
}

function ForwardModal({
	record,
	canDelete,
	onClose,
	onSaved,
}: {
	record: ForwardContract | null;
	canDelete: boolean;
	onClose: () => void;
	onSaved: () => void;
}) {
	const isNew = !record;
	const { createDoc, loading: creating } = useFrappeCreateDoc();
	const { updateDoc, loading: updating } = useFrappeUpdateDoc();
	const { deleteDoc, loading: deleting } = useFrappeDeleteDoc();
	const [confirmDelete, setConfirmDelete] = useState(false);
	const [err, setErr] = useState<string | null>(null);
	const [form, setForm] = useState({
		contract_no: record?.contract_no ?? '',
		ad_bank: record?.ad_bank ?? '',
		currency: record?.currency ?? 'USD',
		contract_amount: record?.contract_amount != null ? String(record.contract_amount) : '',
		forward_rate: record?.forward_rate != null ? String(record.forward_rate) : '',
		booking_date: record?.booking_date ?? '',
		maturity_date: record?.maturity_date ?? '',
		status: record?.status ?? 'Open',
		notes: record?.notes ?? '',
	});
	const set = (k: keyof typeof form, v: string) => setForm((f) => ({ ...f, [k]: v }));
	const busy = creating || updating || deleting;

	async function save() {
		setErr(null);
		const payload = {
			contract_no: form.contract_no.trim(),
			ad_bank: form.ad_bank.trim() || null,
			currency: form.currency,
			contract_amount: Number(form.contract_amount) || 0,
			forward_rate: Number(form.forward_rate) || 0,
			booking_date: form.booking_date || null,
			maturity_date: form.maturity_date || null,
			status: form.status,
			notes: form.notes.trim() || null,
		};
		try {
			if (isNew) await createDoc('Forward Contract', payload);
			else await updateDoc('Forward Contract', record!.name, payload);
			onSaved();
		} catch (e) {
			setErr(parseServerError(e));
		}
	}
	async function remove() {
		setErr(null);
		try {
			await deleteDoc('Forward Contract', record!.name);
			onSaved();
		} catch (e) {
			setErr(parseServerError(e));
		}
	}

	return (
		<Modal title={isNew ? 'Book forward contract' : record!.contract_no} icon="banknote" onClose={onClose} locked={busy}>
			<div className="fcform">
				<Field label="Forward contract no." required>
					<TextInput mono value={form.contract_no} onChange={(v) => set('contract_no', v)} placeholder="20-XXXX XXX" />
				</Field>
				<Field label="AD bank">
					<TextInput value={form.ad_bank} onChange={(v) => set('ad_bank', v)} placeholder="BOI" />
				</Field>
				<div className="row2">
					<Field label="Currency" required>
						<SelectInput value={form.currency} onChange={(v) => set('currency', v)} options={CURRENCIES.map((c) => ({ value: c }))} />
					</Field>
					<Field label="Contract amount (FCY)" required>
						<TextInput type="number" mono value={form.contract_amount} onChange={(v) => set('contract_amount', v)} />
					</Field>
				</div>
				<Field label="Forward rate (INR)" required hint="Realizations on this contract settle at this locked rate">
					<TextInput type="number" mono value={form.forward_rate} onChange={(v) => set('forward_rate', v)} />
				</Field>
				<div className="row2">
					<Field label="Booking date">
						<TextInput type="date" value={form.booking_date} onChange={(v) => set('booking_date', v)} />
					</Field>
					<Field label="Maturity / delivery date">
						<TextInput type="date" value={form.maturity_date} onChange={(v) => set('maturity_date', v)} />
					</Field>
				</div>
				<Field label="Status" hint="Auto from utilization & maturity; set Cancelled to retire the contract">
					<SelectInput value={form.status} onChange={(v) => set('status', v)} options={STATUSES.map((s) => ({ value: s }))} />
				</Field>
				{!isNew && (
					<div className="fcstat">
						Utilized <b>{fcy(record!.currency, record!.utilized_amount)}</b> · outstanding{' '}
						<b>{fcy(record!.currency, record!.outstanding_amount)}</b> · locked INR{' '}
						<b>{fmtMoney(record!.inr_value, 'INR')}</b>
					</div>
				)}
				<Field label="Notes">
					<TextArea value={form.notes} onChange={(v) => set('notes', v)} rows={2} />
				</Field>
				{err && <div className="ferr">{err}</div>}
				<div className="formfoot">
					<button className="btn primary" onClick={() => void save()} disabled={busy || !form.contract_no || !form.contract_amount || !form.forward_rate}>
						{creating || updating ? 'Saving…' : isNew ? 'Book' : 'Save'}
					</button>
					{!isNew && canDelete && !confirmDelete && (
						<button className="btn" onClick={() => setConfirmDelete(true)} disabled={busy}>Delete</button>
					)}
					{!isNew && canDelete && confirmDelete && (
						<>
							<span className="sub" style={{ margin: 0 }}>Delete permanently?</span>
							<button className="btn" onClick={() => setConfirmDelete(false)} disabled={busy}>Keep</button>
							<button className="btn danger" onClick={() => void remove()} disabled={busy}>{deleting ? 'Deleting…' : 'Yes, delete'}</button>
						</>
					)}
					<span className="spacer" />
					<button className="btn" onClick={onClose} disabled={busy}>Cancel</button>
				</div>
			</div>
		</Modal>
	);
}
