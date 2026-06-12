import { useMemo, useRef, useState } from 'react';
import {
	useFrappeCreateDoc,
	useFrappeDeleteDoc,
	useFrappeFileUpload,
	useFrappeGetCall,
	useFrappeGetDocList,
	useFrappeUpdateDoc,
} from 'frappe-react-sdk';
import { Icon } from '@/components/Icon';
import { Field, SearchSelect, SelectInput, TextArea, TextInput } from '@/components/form';
import { Card, CHead, EmptyMsg, Modal, Tag } from '@/components/ui';
import { API, parseServerError } from '@/lib/api';
import { daysUntil, fmtDate } from '@/lib/format';

const COMPLIANCE_TYPES = [
	'IEC',
	'GST Registration',
	'LUT',
	'RCMC Pharmexcil',
	'Wholesale Drug License',
	'AD Code',
	'Bank Details',
	'Other',
];

interface ComplianceRow {
	name: string;
	compliance_type: string;
	title: string;
	status: 'Active' | 'Archived';
	reference_number: string | null;
	issue_date: string | null;
	expiry_date: string | null;
	port: string | null;
	file: string | null;
	notes: string | null;
}

/** Renewal chip: matches the 60/30/7 alert tiers. */
function expiryChip(row: ComplianceRow): { tone: 'ok' | 'pend' | 'err'; label: string } | null {
	if (row.status === 'Archived') return null;
	if (!row.expiry_date) return { tone: 'ok', label: 'No expiry' };
	const days = daysUntil(row.expiry_date);
	if (days === null) return null;
	if (days < 0) return { tone: 'err', label: `${-days}d overdue` };
	if (days <= 30) return { tone: 'err', label: `${days}d left` };
	if (days <= 60) return { tone: 'pend', label: `${days}d left` };
	return { tone: 'ok', label: 'Valid' };
}

export function Compliance() {
	const [showArchived, setShowArchived] = useState(false);
	const [modal, setModal] = useState<'new' | ComplianceRow | null>(null);

	const perms = useFrappeGetCall<{
		message: { can_create: boolean; can_write: boolean; can_delete: boolean };
	}>(API.compliancePermissions, undefined);
	const canCreate = perms.data?.message.can_create ?? false;
	const canWrite = perms.data?.message.can_write ?? false;
	const canDelete = perms.data?.message.can_delete ?? false;

	const { data, error, isLoading, mutate } = useFrappeGetDocList<ComplianceRow>(
		'Compliance Record',
		{
			fields: [
				'name',
				'compliance_type',
				'title',
				'status',
				'reference_number',
				'issue_date',
				'expiry_date',
				'port',
				'file',
				'notes',
			],
			orderBy: { field: 'expiry_date', order: 'asc' },
			limit: 200,
		},
	);

	const rows = useMemo(() => {
		const all = data ?? [];
		return showArchived ? all : all.filter((r) => r.status === 'Active');
	}, [data, showArchived]);

	const expiring = (data ?? []).filter((r) => {
		const days = r.status === 'Active' && r.expiry_date ? daysUntil(r.expiry_date) : null;
		return days !== null && days <= 60;
	}).length;

	return (
		<main>
			<div className="eyebrow">Registers</div>
			<h1>
				Compliance <em>register</em>
			</h1>
			<div className="sub">
				IEC, LUT, RCMC, drug licences and AD codes — renewal alerts fire 60/30/7 days out
				{expiring > 0 ? (
					<>
						{' · '}
						<b>{expiring}</b> within 60 days
					</>
				) : null}
				.
			</div>

			{canCreate && (
				<div
					style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 10, margin: '18px 0 12px' }}
				>
					<button className="btn primary" onClick={() => setModal('new')}>
						<Icon name="plus" size={15} /> New record
					</button>
				</div>
			)}

			<div>
				<Card accent>
					<CHead
						icon="shield-check"
						title="Company registrations"
						count={data ? rows.length : undefined}
						action={
							<a
								href="#"
								onClick={(e) => {
									e.preventDefault();
									setShowArchived((v) => !v);
								}}
							>
								{showArchived ? 'Hide archived' : 'Show archived'}
							</a>
						}
					/>
					{isLoading ? (
						<div className="sub" style={{ padding: '14px 18px' }}>
							Loading…
						</div>
					) : error ? (
						<div className="ferr" style={{ padding: '14px 18px' }}>{parseServerError(error)}</div>
					) : rows.length === 0 ? (
						<EmptyMsg
							title="No records yet"
							text="Add the IEC, GST registration, LUT, RCMC, drug licences, AD codes and bank details here."
						/>
					) : (
						<table className={canWrite ? 'clickable' : undefined}>
							<thead>
								<tr>
									<th>Record</th>
									<th>Reference</th>
									<th>Issued</th>
									<th>Expires</th>
									<th>Renewal</th>
									<th></th>
								</tr>
							</thead>
							<tbody>
								{rows.map((r) => {
									const chip = expiryChip(r);
									return (
										<tr key={r.name} onClick={canWrite ? () => setModal(r) : undefined}>
											<td>
												<div className="c1">{r.title}</div>
												<div className="c2">
													{r.compliance_type}
													{r.port ? ` · ${r.port}` : ''}
												</div>
											</td>
											<td className="dim">{r.reference_number ?? '—'}</td>
											<td className="dim">{fmtDate(r.issue_date)}</td>
											<td className="dim">{fmtDate(r.expiry_date)}</td>
											<td>
												{r.status === 'Archived' ? (
													<Tag tone="err">Archived</Tag>
												) : chip ? (
													<Tag tone={chip.tone}>{chip.label}</Tag>
												) : null}
											</td>
											<td>
												{r.file && (
													<a
														className="act"
														href={r.file}
														target="_blank"
														rel="noreferrer"
														onClick={(e) => e.stopPropagation()}
													>
														File
													</a>
												)}
											</td>
										</tr>
									);
								})}
							</tbody>
						</table>
					)}
				</Card>
			</div>

			{modal !== null && (
				<ComplianceModal
					record={modal === 'new' ? null : modal}
					canDelete={canDelete}
					onClose={() => setModal(null)}
					onSaved={() => {
						setModal(null);
						mutate();
					}}
					onChanged={() => void mutate()}
				/>
			)}

			<footer>
				<b>ExportFlow</b> · DUX Digitech
			</footer>
		</main>
	);
}

function ComplianceModal({
	record,
	canDelete,
	onClose,
	onSaved,
	onChanged,
}: {
	record: ComplianceRow | null;
	canDelete: boolean;
	onClose: () => void;
	onSaved: () => void;
	onChanged?: () => void;
}) {
	const isNew = record === null;
	const [form, setForm] = useState({
		compliance_type: record?.compliance_type ?? '',
		title: record?.title ?? '',
		status: record?.status ?? 'Active',
		reference_number: record?.reference_number ?? '',
		issue_date: record?.issue_date ?? '',
		expiry_date: record?.expiry_date ?? '',
		port: record?.port ?? '',
		notes: record?.notes ?? '',
	});
	const [fileUrl, setFileUrl] = useState<string | null>(record?.file ?? null);
	const [err, setErr] = useState<string | null>(null);
	const fileInput = useRef<HTMLInputElement | null>(null);

	const ports = useFrappeGetDocList<{ name: string }>('Port', {
		fields: ['name'],
		filters: [['disabled', '=', 0]],
		limit: 300,
	});
	const { createDoc, loading: creating } = useFrappeCreateDoc();
	const { updateDoc, loading: updating } = useFrappeUpdateDoc();
	const { deleteDoc, loading: deleting } = useFrappeDeleteDoc();
	const { upload, loading: uploading } = useFrappeFileUpload();
	const busy = creating || updating || deleting || uploading;

	const set = <K extends keyof typeof form>(key: K, value: (typeof form)[K]) =>
		setForm((f) => ({ ...f, [key]: value }));

	function payload() {
		return {
			...form,
			issue_date: form.issue_date || null,
			expiry_date: form.expiry_date || null,
			port: form.port || null,
		};
	}

	async function onSave() {
		if (!form.compliance_type) return setErr('Pick the type.');
		if (!form.title.trim()) return setErr('Title is required.');
		setErr(null);
		try {
			if (isNew) {
				await createDoc('Compliance Record', payload());
			} else {
				await updateDoc('Compliance Record', record.name, payload());
			}
			onSaved();
		} catch (e) {
			setErr(parseServerError(e));
		}
	}

	async function onUpload(file: File) {
		if (!record) return setErr('Save the record first, then attach the file.');
		setErr(null);
		try {
			const res = await upload(file, {
				doctype: 'Compliance Record',
				docname: record.name,
				fieldname: 'file',
				isPrivate: true,
			});
			// frappe's upload never writes the Attach field itself
			await updateDoc('Compliance Record', record.name, { file: res.file_url });
			setFileUrl(res.file_url);
			onChanged?.();
		} catch (e) {
			setErr(parseServerError(e));
		}
	}

	async function onDelete() {
		if (!record) return;
		setErr(null);
		try {
			await deleteDoc('Compliance Record', record.name);
			onSaved();
		} catch (e) {
			setErr(parseServerError(e));
		}
	}

	return (
		<Modal
			title={isNew ? 'New compliance record' : record.title}
			icon="shield-check"
			onClose={onClose}
		>
			<div className="formgrid">
				<Field label="Type" required>
					<SelectInput
						value={form.compliance_type}
						onChange={(v) =>
							// the port belongs to AD Code registrations only
							setForm((f) => ({ ...f, compliance_type: v, port: v === 'AD Code' ? f.port : '' }))
						}
						options={COMPLIANCE_TYPES.map((t) => ({ value: t }))}
						allowEmpty
					/>
				</Field>
				<Field label="Title" required hint="e.g. LUT FY 2026-27">
					<TextInput value={form.title} onChange={(v) => set('title', v)} />
				</Field>
				{form.compliance_type === 'AD Code' && (
					<Field label="Port" required hint="AD codes are registered per port">
						<SearchSelect
							value={form.port}
							onChange={(v) => set('port', v)}
							options={(ports.data ?? []).map((p) => ({ value: p.name }))}
							placeholder="Search ports…"
						/>
					</Field>
				)}
				<Field label="Reference number">
					<TextInput mono value={form.reference_number} onChange={(v) => set('reference_number', v)} />
				</Field>
				<Field label="Issue date">
					<TextInput type="date" value={form.issue_date} onChange={(v) => set('issue_date', v)} />
				</Field>
				<Field label="Expiry / renewal date" hint="Alerts at 60/30/7 days">
					<TextInput type="date" value={form.expiry_date} onChange={(v) => set('expiry_date', v)} />
				</Field>
				<Field label="Status">
					<SelectInput
						value={form.status}
						onChange={(v) => set('status', v as 'Active' | 'Archived')}
						options={[{ value: 'Active' }, { value: 'Archived' }]}
					/>
				</Field>
				<Field label="File" hint={isNew ? 'Save first, then attach' : undefined}>
					<div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
						{fileUrl ? (
							<a className="act" href={fileUrl} target="_blank" rel="noreferrer">
								View attached
							</a>
						) : (
							<span className="fhint">none yet</span>
						)}
						<button
							type="button"
							className="btn"
							style={{ padding: '5px 12px' }}
							disabled={busy || isNew}
							onClick={() => fileInput.current?.click()}
						>
							{uploading ? 'Uploading…' : 'Upload'}
						</button>
						<input
							ref={fileInput}
							type="file"
							style={{ display: 'none' }}
							onChange={(e) => {
								const f = e.target.files?.[0];
								if (f) void onUpload(f);
								e.target.value = '';
							}}
						/>
					</div>
				</Field>
				<div className="span2">
					<Field label="Notes">
						<TextArea value={form.notes} onChange={(v) => set('notes', v)} rows={2} />
					</Field>
				</div>
			</div>
			<div className="formfoot">
				{err && <span className="ferr">{err}</span>}
				{!isNew && canDelete && (
					<button type="button" className="btn" disabled={busy} onClick={() => void onDelete()}>
						{deleting ? 'Removing…' : 'Remove'}
					</button>
				)}
				<span className="spacer" />
				<button type="button" className="btn" onClick={onClose}>
					Cancel
				</button>
				<button type="button" className="btn primary" disabled={busy} onClick={() => void onSave()}>
					{busy && !uploading ? 'Saving…' : isNew ? 'Create record' : 'Save changes'}
				</button>
			</div>
		</Modal>
	);
}
