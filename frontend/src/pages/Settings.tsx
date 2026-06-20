import { useEffect, useMemo, useState } from 'react';
import {
	useFrappeCreateDoc,
	useFrappeDeleteDoc,
	useFrappeFileUpload,
	useFrappeGetCall,
	useFrappeGetDoc,
	useFrappeGetDocList,
	useFrappePostCall,
	useFrappeUpdateDoc,
} from 'frappe-react-sdk';
import { Icon, type IconName } from '@/components/Icon';
import { MasterModal } from '@/components/MasterModal';
import { CheckInput, Field, SearchSelect, SelectInput, TextArea, TextInput } from '@/components/form';
import { Card, CHead, EmptyMsg, Modal, Tag } from '@/components/ui';
import { API, parseServerError, type ChecklistRuleRow, type EmailAccount, type NewSOContext } from '@/lib/api';
import { MASTERS, STATIC_OPTIONS, type MasterDef, type OptionSource } from '@/lib/masters';

type Row = Record<string, unknown> & { name: string };

function MasterPanel({
	def,
	options,
	canEdit,
}: {
	def: MasterDef;
	options: Record<OptionSource, string[]>;
	canEdit: boolean;
}) {
	const [query, setQuery] = useState('');
	const [modal, setModal] = useState<'new' | Row | null>(null);

	const { data, error, mutate } = useFrappeGetDocList<Row>(def.doctype, {
		fields: def.listFields,
		orderBy: { field: 'modified', order: 'desc' },
		limit: 0, // all records — the list is browsable, not search-only
	});

	const rows = useMemo(() => {
		const all = data ?? [];
		const q = query.trim().toLowerCase();
		if (!q) return all;
		return all.filter((r) =>
			def.columns.some((c) => String(r[c.key] ?? '').toLowerCase().includes(q)) ||
			r.name.toLowerCase().includes(q),
		);
	}, [data, query, def.columns]);

	return (
		<Card>
			<CHead
				icon={def.icon}
				title={def.title}
				count={data ? data.length : undefined}
				action={
					canEdit ? (
						<a
							onClick={(e) => {
								e.preventDefault();
								setModal('new');
							}}
							href="#"
						>
							New
						</a>
					) : undefined
				}
			/>
			{(data?.length ?? 0) > 6 && (
				<div style={{ padding: '10px 18px 0' }}>
					<div className="field" style={{ width: 260 }}>
						<TextInput value={query} onChange={setQuery} placeholder={`Search ${def.title.toLowerCase()}`} />
					</div>
				</div>
			)}
			{error ? (
				<div className="ferr" style={{ padding: '14px 18px' }}>
					Could not load {def.title.toLowerCase()} — check permissions.
				</div>
			) : rows.length === 0 ? (
				<EmptyMsg title={query ? 'No matches' : `No ${def.title.toLowerCase()} yet`} />
			) : (
				<div className="tablescroll">
					<table className={canEdit ? 'clickable' : undefined}>
						<thead>
							<tr>
								{def.columns.map((c) => (
									<th key={c.key}>{c.label}</th>
								))}
							</tr>
						</thead>
						<tbody>
							{rows.map((r) => (
								<tr key={r.name} onClick={canEdit ? () => setModal(r) : undefined}>
									{def.columns.map((c) => {
										const v = r[c.key];
										const isCheck = def.fields.find((f) => f.key === c.key)?.type === 'check';
										return (
											<td key={c.key} className={c.dim ? 'dim' : 'c1'}>
												{isCheck ? (v ? 'Yes' : '—') : v != null && v !== '' ? String(v) : '—'}
											</td>
										);
									})}
								</tr>
							))}
						</tbody>
					</table>
				</div>
			)}
			{modal !== null && (
				<MasterModal
					def={def}
					options={options}
					record={modal === 'new' ? null : modal}
					onClose={() => setModal(null)}
					onSaved={() => {
						setModal(null);
						mutate();
					}}
				/>
			)}
		</Card>
	);
}

const CONDITION_FIELDS = [
	'mode',
	'incoterm',
	'destination_country',
	'customer',
	'letter_of_credit',
	'merchant_export_scheme',
	'trade_type',
];

function conditionsSummary(rule: ChecklistRuleRow): string {
	if (!rule.conditions.length) return 'always';
	return rule.conditions.map((c) => `${c.condition_field} = ${c.condition_value}`).join(' · ');
}

/** Checklist rules — the §5.3 engine's data. Conditions AND together; a rule
 *  with none applies to every shipment. */
function ChecklistRulesPanel({ canEdit }: { canEdit: boolean }) {
	const { data, error, isLoading, mutate } = useFrappeGetCall<{ message: ChecklistRuleRow[] }>(
		API.checklistRules,
		undefined,
	);
	const docTypes = useFrappeGetDocList<{ name: string; category: string }>('Document Type', {
		fields: ['name', 'category'],
		orderBy: { field: 'name', order: 'asc' },
		limit: 300,
	});
	const [modal, setModal] = useState<'new' | ChecklistRuleRow | null>(null);

	const rules = data?.message ?? [];

	return (
		<Card>
			<CHead
				icon="sliders"
				title="Checklist rules"
				count={data ? rules.length : undefined}
				action={
					canEdit ? (
						<a
							href="#"
							onClick={(e) => {
								e.preventDefault();
								setModal('new');
							}}
						>
							New
						</a>
					) : undefined
				}
			/>
			{isLoading ? (
				<div className="sub" style={{ padding: '14px 18px' }}>
					Loading…
				</div>
			) : error ? (
				<div className="ferr" style={{ padding: '14px 18px' }}>{parseServerError(error)}</div>
			) : rules.length === 0 ? (
				<EmptyMsg
					title="No checklist rules"
					text="Rules decide which documents every shipment owes — they seed on install."
				/>
			) : (
				<table className={canEdit ? 'clickable' : undefined}>
					<thead>
						<tr>
							<th>Rule</th>
							<th>Requires</th>
							<th>When</th>
							<th>State</th>
						</tr>
					</thead>
					<tbody>
						{rules.map((r) => (
							<tr key={r.name} onClick={canEdit ? () => setModal(r) : undefined}>
								<td className="c1">{r.rule_name}</td>
								<td className="c2">{r.document_type}</td>
								<td className="c2">{conditionsSummary(r)}</td>
								<td>
									<Tag tone={r.enabled ? 'ok' : 'err'}>{r.enabled ? 'Enabled' : 'Disabled'}</Tag>
								</td>
							</tr>
						))}
					</tbody>
				</table>
			)}
			{modal !== null && (
				<RuleModal
					rule={modal === 'new' ? null : modal}
					docTypes={docTypes.data ?? []}
					onClose={() => setModal(null)}
					onSaved={() => {
						setModal(null);
						mutate();
					}}
				/>
			)}
		</Card>
	);
}

function RuleModal({
	rule,
	docTypes,
	onClose,
	onSaved,
}: {
	rule: ChecklistRuleRow | null;
	docTypes: { name: string; category: string }[];
	onClose: () => void;
	onSaved: () => void;
}) {
	const isNew = rule === null;
	const [ruleName, setRuleName] = useState(rule?.rule_name ?? '');
	const [docType, setDocType] = useState(rule?.document_type ?? '');
	const [enabled, setEnabled] = useState(rule ? !!rule.enabled : true);
	const [notes, setNotes] = useState(rule?.notes ?? '');
	const [conditions, setConditions] = useState(
		rule?.conditions.map((c) => ({ ...c })) ?? [],
	);
	const [err, setErr] = useState<string | null>(null);

	const { createDoc, loading: creating } = useFrappeCreateDoc();
	const { updateDoc, loading: updating } = useFrappeUpdateDoc();
	const { deleteDoc, loading: deleting } = useFrappeDeleteDoc();
	const busy = creating || updating || deleting;

	async function onSave() {
		if (!ruleName.trim()) return setErr('Rule name is required.');
		if (!docType) return setErr('Pick the document type this rule requires.');
		if (conditions.some((c) => !c.condition_field || !c.condition_value.trim())) {
			return setErr('Every condition needs a field and a value.');
		}
		setErr(null);
		const payload = {
			document_type: docType,
			enabled: enabled ? 1 : 0,
			notes: notes.trim(),
			conditions,
		};
		try {
			if (isNew) {
				await createDoc('Document Checklist Rule', { rule_name: ruleName.trim(), ...payload });
			} else {
				await updateDoc('Document Checklist Rule', rule.name, payload);
			}
			onSaved();
		} catch (e) {
			setErr(parseServerError(e));
		}
	}

	async function onDelete() {
		if (!rule) return;
		setErr(null);
		try {
			await deleteDoc('Document Checklist Rule', rule.name);
			onSaved();
		} catch (e) {
			setErr(parseServerError(e));
		}
	}

	return (
		<Modal title={isNew ? 'New checklist rule' : rule.rule_name} icon="sliders" onClose={onClose}>
			<div className="formgrid">
				<Field label="Rule name" required>
					<TextInput value={ruleName} disabled={!isNew} onChange={setRuleName} />
				</Field>
				<Field label="Requires document" required>
					<SearchSelect
						value={docType}
						onChange={setDocType}
						placeholder="Search document types…"
						options={docTypes.map((t) => ({ value: t.name, sub: t.category }))}
					/>
				</Field>
				<div className="span2">
					<CheckInput checked={enabled} onChange={setEnabled} label="Enabled" />
				</div>
			</div>
			<div className="reqhead" style={{ gridTemplateColumns: '1fr 1.4fr 34px' }}>
				<span>Condition field</span>
				<span>Value</span>
				<span />
			</div>
			{conditions.length === 0 && (
				<div className="fhint" style={{ padding: '0 18px 6px' }}>
					No conditions — this rule applies to every shipment.
				</div>
			)}
			{conditions.map((c, i) => (
				<div className="reqrow" style={{ gridTemplateColumns: '1fr 1.4fr 34px' }} key={i}>
					<SelectInput
						value={c.condition_field}
						onChange={(v) =>
							setConditions((cs) => cs.map((row, j) => (j === i ? { ...row, condition_field: v } : row)))
						}
						options={CONDITION_FIELDS.map((f) => ({ value: f }))}
						allowEmpty
					/>
					<TextInput
						value={c.condition_value}
						onChange={(v) =>
							setConditions((cs) => cs.map((row, j) => (j === i ? { ...row, condition_value: v } : row)))
						}
						placeholder="e.g. CIF, CIP — or Yes"
					/>
					<button
						type="button"
						className="xbtn"
						aria-label="Remove condition"
						onClick={() => setConditions((cs) => cs.filter((_, j) => j !== i))}
					>
						<Icon name="close" size={13} />
					</button>
				</div>
			))}
			<div style={{ padding: '6px 18px 10px' }}>
				<button
					type="button"
					className="btn"
					style={{ padding: '5px 12px' }}
					onClick={() =>
						setConditions((cs) => [...cs, { condition_field: 'mode', condition_value: '' }])
					}
				>
					<Icon name="plus" size={13} /> Add condition
				</button>
			</div>
			<div className="formgrid" style={{ paddingTop: 0 }}>
				<div className="span2">
					<Field label="Notes">
						<TextArea value={notes} onChange={setNotes} rows={2} />
					</Field>
				</div>
			</div>
			<div className="formfoot">
				{err && <span className="ferr">{err}</span>}
				{!isNew && (
					<button type="button" className="btn" disabled={busy} onClick={() => void onDelete()}>
						{deleting ? 'Deleting…' : 'Delete rule'}
					</button>
				)}
				<span className="spacer" />
				<button type="button" className="btn" onClick={onClose}>
					Cancel
				</button>
				<button type="button" className="btn primary" disabled={busy} onClick={() => void onSave()}>
					{busy ? 'Saving…' : isNew ? 'Create rule' : 'Save changes'}
				</button>
			</div>
		</Modal>
	);
}

interface ExporterProfile {
	iec_number: string;
	gstin: string;
	exporter_address: string;
	lut_number: string;
	lut_valid_upto: string;
	signatory_name: string;
	signatory_designation: string;
	scomet_text: string;
	bank_account_no: string;
	bank_name: string;
	bank_branch_address: string;
	bank_ifsc: string;
	bank_swift: string;
	bank_correspondent: string;
}

const EMPTY_PROFILE: ExporterProfile = {
	iec_number: '',
	gstin: '',
	exporter_address: '',
	lut_number: '',
	lut_valid_upto: '',
	signatory_name: '',
	signatory_designation: '',
	scomet_text: '',
	bank_account_no: '',
	bank_name: '',
	bank_branch_address: '',
	bank_ifsc: '',
	bank_swift: '',
	bank_correspondent: '',
};

/** Exporter identity printed on every §5.2 document (IEC, GSTIN, LUT…). */
function ExporterProfilePanel({ canEdit }: { canEdit: boolean }) {
	const { data, error, isLoading, mutate } = useFrappeGetDoc<
		Partial<ExporterProfile> & {
			company_logo?: string | null;
			logo_nav_height?: number;
		}
	>('ExportFlow Settings', 'ExportFlow Settings');
	const { updateDoc, loading: saving } = useFrappeUpdateDoc();
	const { upload, loading: logoBusy } = useFrappeFileUpload();
	// the logo is shown as an embedded data URI (the /files web route is broken on
	// this bench), so the preview is fetched rather than built from the file_url
	const logoUri = useFrappeGetCall<{ message: { logo: string | null } }>(API.companyLogo, {});
	const [form, setForm] = useState<ExporterProfile>(EMPTY_PROFILE);
	const [navHeight, setNavHeight] = useState(28);
	const [logo, setLogo] = useState<string | null>(null);
	const [seeded, setSeeded] = useState(false);
	const [err, setErr] = useState<string | null>(null);
	const [savedTick, setSavedTick] = useState(false);

	// seed exactly once — background revalidation must never clobber edits
	useEffect(() => {
		if (!data || seeded) return;
		setForm((f) => ({
			...f,
			...Object.fromEntries(
				(Object.keys(EMPTY_PROFILE) as (keyof ExporterProfile)[]).map((k) => [k, data[k] ?? '']),
			),
		}));
		setLogo(data.company_logo ?? null);
		setNavHeight(Number(data.logo_nav_height) || 28);
		setSeeded(true);
	}, [data, seeded]);

	async function onLogoUpload(file: File) {
		setErr(null);
		try {
			const res = await upload(file, {
				doctype: 'ExportFlow Settings',
				docname: 'ExportFlow Settings',
				fieldname: 'company_logo',
				isPrivate: false,
			});
			await updateDoc('ExportFlow Settings', 'ExportFlow Settings', { company_logo: res.file_url });
			setLogo(res.file_url);
			mutate();
			logoUri.mutate();
		} catch (e) {
			setErr(parseServerError(e));
		}
	}

	async function onLogoRemove() {
		setErr(null);
		try {
			await updateDoc('ExportFlow Settings', 'ExportFlow Settings', { company_logo: null });
			setLogo(null);
			mutate();
			logoUri.mutate();
		} catch (e) {
			setErr(parseServerError(e));
		}
	}

	const set = <K extends keyof ExporterProfile>(key: K, value: string) => {
		setSavedTick(false);
		setForm((f) => ({ ...f, [key]: value }));
	};

	async function onSave() {
		setErr(null);
		setSavedTick(false);
		try {
			await updateDoc('ExportFlow Settings', 'ExportFlow Settings', {
				...form,
				lut_valid_upto: form.lut_valid_upto || null,
				logo_nav_height: navHeight || 28,
			});
			setSavedTick(true);
			mutate();
			logoUri.mutate();
		} catch (e) {
			setErr(parseServerError(e));
		}
	}

	return (
		<Card>
			<CHead icon="shield" title="Exporter profile" />
			{isLoading ? (
				<div className="sub" style={{ padding: '14px 18px' }}>
					Loading…
				</div>
			) : error ? (
				<div className="ferr" style={{ padding: '14px 18px' }}>{parseServerError(error)}</div>
			) : (
				<>
					<div className="formgrid">
						<div className="span2">
							<Field
								label="Company logo"
								hint="Shown in the top-left nav and on every print's exporter block"
							>
								<div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
									{logoUri.data?.message?.logo ? (
										<img
											src={logoUri.data.message.logo}
											alt=""
											style={{ height: navHeight, maxWidth: 220, borderRadius: 4, border: '1px solid var(--hairline)' }}
										/>
									) : (
										<span className="dim">{logo ? 'Loading…' : 'No logo set'}</span>
									)}
									{canEdit && (
										<>
											<label className="btn" style={{ cursor: 'pointer' }}>
												<Icon name="upload" size={14} /> {logo ? 'Change' : 'Upload'}
												<input
													type="file"
													accept="image/png,image/jpeg,image/svg+xml,image/webp"
													style={{ display: 'none' }}
													onChange={(e) => {
														const f = e.target.files?.[0];
														e.target.value = '';
														if (f) void onLogoUpload(f);
													}}
												/>
											</label>
											{logo && (
												<button type="button" className="btn" onClick={() => void onLogoRemove()}>
													<Icon name="x" size={14} /> Remove
												</button>
											)}
											{logoBusy && <span className="dim">Uploading…</span>}
										</>
									)}
								</div>
								{logo && canEdit && (
									<div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 12 }}>
										<span className="dim" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
											Nav size
										</span>
										<input
											type="range"
											min={18}
											max={56}
											value={navHeight}
											onChange={(e) => {
												setSavedTick(false);
												setNavHeight(Number(e.target.value));
											}}
											style={{ flex: 1, maxWidth: 240, accentColor: 'var(--iris)' }}
										/>
										<span className="mono dim" style={{ fontSize: 12, width: 38 }}>
											{navHeight}px
										</span>
									</div>
								)}
							</Field>
						</div>
						<Field label="IEC number">
							<TextInput mono value={form.iec_number} onChange={(v) => set('iec_number', v)} />
						</Field>
						<Field label="GSTIN">
							<TextInput mono value={form.gstin} onChange={(v) => set('gstin', v)} />
						</Field>
						<div className="span2">
							<Field
								label="Exporter address"
								hint="Address block as printed on invoices and declarations"
							>
								<TextArea
									value={form.exporter_address}
									onChange={(v) => set('exporter_address', v)}
									rows={3}
								/>
							</Field>
						</div>
						<Field
							label="LUT ARN / number"
							hint="When set, invoices carry the LUT-without-IGST declaration"
						>
							<TextInput mono value={form.lut_number} onChange={(v) => set('lut_number', v)} />
						</Field>
						<Field label="LUT valid upto">
							<TextInput
								type="date"
								value={form.lut_valid_upto}
								onChange={(v) => set('lut_valid_upto', v)}
							/>
						</Field>
						<Field label="Signatory name">
							<TextInput value={form.signatory_name} onChange={(v) => set('signatory_name', v)} />
						</Field>
						<Field label="Signatory designation">
							<TextInput
								value={form.signatory_designation}
								onChange={(v) => set('signatory_designation', v)}
							/>
						</Field>
						<div className="span2 fdivider">Bank details · for invoice remittance</div>
						<Field label="Bank name">
							<TextInput value={form.bank_name} onChange={(v) => set('bank_name', v)} />
						</Field>
						<Field label="Account number">
							<TextInput mono value={form.bank_account_no} onChange={(v) => set('bank_account_no', v)} />
						</Field>
						<Field label="IFSC code">
							<TextInput mono value={form.bank_ifsc} onChange={(v) => set('bank_ifsc', v)} />
						</Field>
						<Field label="SWIFT code">
							<TextInput mono value={form.bank_swift} onChange={(v) => set('bank_swift', v)} />
						</Field>
						<div className="span2">
							<Field label="Branch" hint="Branch name / address">
								<TextInput value={form.bank_branch_address} onChange={(v) => set('bank_branch_address', v)} />
							</Field>
						</div>
						<div className="span2">
							<Field label="Correspondent bank" hint="Intermediary bank & routing, for inward foreign remittance">
								<TextArea value={form.bank_correspondent} onChange={(v) => set('bank_correspondent', v)} rows={2} />
							</Field>
						</div>
						<div className="span2">
							<Field label="SCOMET declaration override" hint="Leave blank for the standard wording">
								<TextArea value={form.scomet_text} onChange={(v) => set('scomet_text', v)} rows={2} />
							</Field>
						</div>
					</div>
					<div className="formfoot">
						{err && <span className="ferr">{err}</span>}
						{savedTick && !err && <span className="fhint">Saved.</span>}
						<span className="spacer" />
						<button
							type="button"
							className="btn"
							disabled={saving || !canEdit}
							onClick={() => void onSave()}
						>
							{saving ? 'Saving…' : 'Save profile'}
						</button>
					</div>
				</>
			)}
		</Card>
	);
}

/** Lifecycle automation toggles + the FEMA merchanting clocks (split out of the
 *  exporter profile so each settings section stays focused). */
function AutomationPanel({ canEdit }: { canEdit: boolean }) {
	const { data, isLoading, error, mutate } = useFrappeGetDoc<{
		mtt_completion_months?: number;
		mtt_outlay_months?: number;
		auto_cha_third_country?: 0 | 1;
		auto_create_realization?: 0 | 1;
		auto_create_incentive?: 0 | 1;
		email_digest_enabled?: 0 | 1;
	}>('ExportFlow Settings', 'ExportFlow Settings');
	const { updateDoc, loading: saving } = useFrappeUpdateDoc();
	const [completion, setCompletion] = useState('');
	const [outlay, setOutlay] = useState('');
	const [autoCha, setAutoCha] = useState(false);
	const [autoRealization, setAutoRealization] = useState(true);
	const [autoIncentive, setAutoIncentive] = useState(true);
	const [emailDigest, setEmailDigest] = useState(false);
	const [seeded, setSeeded] = useState(false);
	const [err, setErr] = useState<string | null>(null);
	const [savedTick, setSavedTick] = useState(false);

	useEffect(() => {
		if (!data || seeded) return;
		setCompletion(data.mtt_completion_months != null ? String(data.mtt_completion_months) : '');
		setOutlay(data.mtt_outlay_months != null ? String(data.mtt_outlay_months) : '');
		setAutoCha(!!data.auto_cha_third_country);
		// default ON — an unset Single field reads back null/undefined
		setAutoRealization(data.auto_create_realization == null ? true : !!data.auto_create_realization);
		setAutoIncentive(data.auto_create_incentive == null ? true : !!data.auto_create_incentive);
		setEmailDigest(!!data.email_digest_enabled);
		setSeeded(true);
	}, [data, seeded]);

	const touch = <T,>(fn: (v: T) => void) => (v: T) => {
		setSavedTick(false);
		fn(v);
	};

	async function onSave() {
		setErr(null);
		setSavedTick(false);
		try {
			await updateDoc('ExportFlow Settings', 'ExportFlow Settings', {
				mtt_completion_months: Number(completion) || 9,
				mtt_outlay_months: Number(outlay) || 4,
				auto_cha_third_country: autoCha ? 1 : 0,
				auto_create_realization: autoRealization ? 1 : 0,
				auto_create_incentive: autoIncentive ? 1 : 0,
				email_digest_enabled: emailDigest ? 1 : 0,
			});
			setSavedTick(true);
			mutate();
		} catch (e) {
			setErr(parseServerError(e));
		}
	}

	return (
		<Card accent>
			<CHead icon="sparkle" title="Automation & alerts" />
			{isLoading ? (
				<div className="sub" style={{ padding: '14px 18px' }}>Loading…</div>
			) : error ? (
				<div className="ferr" style={{ padding: '14px 18px' }}>{parseServerError(error)}</div>
			) : (
				<>
					<div className="formgrid">
						<div className="span2">
							<CheckInput
								checked={autoRealization}
								onChange={touch(setAutoRealization)}
								label="Open a bank realization automatically when a Commercial Invoice is generated"
							/>
						</div>
						<div className="span2">
							<CheckInput
								checked={autoIncentive}
								onChange={touch(setAutoIncentive)}
								label="Open RoDTEP / Drawback incentive claims automatically when a Commercial Invoice is generated (never for merchanting)"
							/>
						</div>
						<div className="span2">
							<CheckInput
								checked={autoCha}
								onChange={touch(setAutoCha)}
								label="Set CHA to “Third Country” automatically on merchanting shipments"
							/>
						</div>
						<div className="span2">
							<CheckInput
								checked={emailDigest}
								onChange={touch(setEmailDigest)}
								label="Send a daily email digest of open alerts to the export team"
							/>
						</div>
						<div className="span2 fdivider">Merchanting (FEMA) clocks</div>
						<Field
							label="MTT completion window (months)"
							hint="FEMA merchanting — default 9; FEM Regs 2026 may revise"
						>
							<TextInput type="number" mono value={completion} onChange={touch(setCompletion)} placeholder="9" />
						</Field>
						<Field label="MTT forex-outlay window (months)" hint="Default 4">
							<TextInput type="number" mono value={outlay} onChange={touch(setOutlay)} placeholder="4" />
						</Field>
					</div>
					<div className="formfoot">
						{err && <span className="ferr">{err}</span>}
						{savedTick && !err && <span className="fhint">Saved.</span>}
						<span className="spacer" />
						<button type="button" className="btn" disabled={saving || !canEdit} onClick={() => void onSave()}>
							{saving ? 'Saving…' : 'Save'}
						</button>
					</div>
				</>
			)}
		</Card>
	);
}

const DOC_MASTER = MASTERS.find((m) => m.doctype === 'Document Type')!;
const DATA_MASTERS = MASTERS.filter((m) => m.doctype !== 'Document Type');

type SettingsSection = 'company' | 'automation' | 'email' | 'documents' | 'data';
const SETTINGS_SECTIONS: { key: SettingsSection; label: string; icon: IconName; count?: number }[] = [
	{ key: 'company', label: 'Company profile', icon: 'building' },
	{ key: 'automation', label: 'Automation & alerts', icon: 'sparkle' },
	{ key: 'email', label: 'Email account', icon: 'send' },
	{ key: 'documents', label: 'Documents & rules', icon: 'file-text' },
	{ key: 'data', label: 'Master data', icon: 'box', count: DATA_MASTERS.length },
];


function EmailAccountPanel() {
	// gated on this panel's OWN endpoint (write-only) — an `error` here means the user
	// lacks ExportFlow Settings write, so the form is never shown to them
	const { data, isLoading, error, mutate } = useFrappeGetCall<{ message: EmailAccount }>(API.emailAccountGet, undefined);
	const acc = data?.message;
	const { call: saveCall, loading: saving } = useFrappePostCall<{ message: { ok: boolean; configured: boolean } }>(API.emailAccountSave);
	const { call: testCall, loading: testing } = useFrappePostCall<{ message: { ok: boolean; email: string } }>(API.emailAccountTest);

	const [email, setEmail] = useState('');
	const [senderName, setSenderName] = useState('');
	const [host, setHost] = useState('smtp.gmail.com');
	const [port, setPort] = useState('465');
	const [useSsl, setUseSsl] = useState(true);
	const [password, setPassword] = useState('');
	const [hasPassword, setHasPassword] = useState(false);
	const [seeded, setSeeded] = useState(false);
	const [err, setErr] = useState<string | null>(null);
	const [msg, setMsg] = useState<string | null>(null);

	useEffect(() => {
		if (!acc || seeded) return;
		setEmail(acc.email ?? '');
		setSenderName(acc.sender_name ?? '');
		setHost(acc.host || 'smtp.gmail.com');
		setPort(String(acc.port || 465));
		setUseSsl(acc.use_ssl);
		setHasPassword(acc.has_password);
		setSeeded(true);
	}, [acc, seeded]);

	// editing the form clears any stale Saved / Connected / error message
	const touch = <T,>(fn: (v: T) => void) => (v: T) => {
		setMsg(null);
		setErr(null);
		fn(v);
	};

	async function onSave() {
		setErr(null);
		setMsg(null);
		try {
			const r = await saveCall({ email, sender_name: senderName, host, port, use_ssl: useSsl ? 1 : 0, password: password || undefined });
			setMsg(r.message.configured ? 'Saved — account connected.' : 'Saved.');
			if (password) setHasPassword(true);
			setPassword('');
			mutate();
		} catch (e) {
			setErr(parseServerError(e));
		}
	}
	async function onTest() {
		setErr(null);
		setMsg(null);
		try {
			// test the LIVE values being edited, not the stale saved account
			const r = await testCall({ email, host, port, use_ssl: useSsl ? 1 : 0, password: password || undefined });
			setMsg(`Connected ✓ — ${r.message.email}`);
		} catch (e) {
			setErr(parseServerError(e));
		}
	}

	return (
		<Card accent>
			<CHead icon="send" title="Email sending account" action={acc?.configured ? <Tag tone="ok">Connected</Tag> : undefined} />
			{isLoading ? (
				<div className="sub" style={{ padding: '14px 18px' }}>Loading…</div>
			) : error ? (
				<div className="ferr" style={{ padding: '14px 18px' }}>{parseServerError(error)}</div>
			) : (
				<div style={{ padding: '6px 18px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
					<div className="sub" style={{ margin: 0 }}>
						The address outbound emails (purchase orders, proforma invoices) are sent from. Self-contained — it does not
						change this site's other apps. For Gmail/Workspace use an <b>App Password</b>, not your login password.
					</div>
					<Field label="From email address" required>
						<TextInput value={email} onChange={touch(setEmail)} placeholder="exports@yourcompany.com" />
					</Field>
					<Field label="Sender name">
						<TextInput value={senderName} onChange={touch(setSenderName)} placeholder="MN Globex Exports" />
					</Field>
					<div style={{ display: 'flex', gap: 12 }}>
						<div style={{ flex: 2 }}>
							<Field label="SMTP host"><TextInput value={host} onChange={touch(setHost)} /></Field>
						</div>
						<div style={{ flex: 1 }}>
							<Field label="Port"><TextInput value={port} onChange={touch(setPort)} type="number" /></Field>
						</div>
					</div>
					<CheckInput checked={useSsl} onChange={touch(setUseSsl)} label="Use SSL (port 465; uncheck for STARTTLS / 587)" />
					<Field label="App password" hint={hasPassword ? 'A password is saved — leave blank to keep it.' : 'Required to send.'}>
						<TextInput value={password} onChange={touch(setPassword)} type="password" placeholder={hasPassword ? '••••••••  (unchanged)' : 'app password'} />
					</Field>
					{err && <div className="ferr">{err}</div>}
					{msg && <div className="sub" style={{ margin: 0, color: 'var(--iris)' }}>{msg}</div>}
					<div className="formfoot">
						<button className="btn primary" onClick={() => void onSave()} disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
						<button
							className="btn"
							onClick={() => void onTest()}
							disabled={testing || !email || (!password && !hasPassword)}
						>
							{testing ? 'Testing…' : 'Test connection'}
						</button>
						<span className="spacer" />
					</div>
				</div>
			)}
		</Card>
	);
}

export function Settings() {
	// the SO-context endpoint doubles as the masters option source; viewers
	// without create rights still browse the lists below read-only
	const ctxResult = useFrappeGetCall<{ message: NewSOContext }>(API.newSoContext, undefined);
	const ctx = ctxResult.data?.message;
	const canEdit = !ctxResult.error;

	const options: Record<OptionSource, string[]> = {
		currencies: ctx?.currencies ?? [],
		incoterms: ctx?.incoterms ?? [],
		uoms: ctx?.uoms ?? [],
		countries: ctx?.countries ?? [],
		itemTaxTemplates: ctx?.item_tax_templates ?? [],
		...STATIC_OPTIONS,
	};

	const [section, setSection] = useState<SettingsSection>('company');
	const [activeMaster, setActiveMaster] = useState(DATA_MASTERS[0].doctype);
	const master = DATA_MASTERS.find((m) => m.doctype === activeMaster) ?? DATA_MASTERS[0];

	return (
		<main>
			<div className="eyebrow">Workspace</div>
			<h1>
				Masters & <em>settings</em>
			</h1>
			<div className="sub">Everything the deal, shipment and document screens pick from.</div>

			<div className="setwrap">
				<nav className="setnav" aria-label="Settings sections">
					{SETTINGS_SECTIONS.map((s) => (
						<a
							key={s.key}
							className={section === s.key ? 'on' : ''}
							role="button"
							tabIndex={0}
							onClick={() => setSection(s.key)}
							onKeyDown={(e) => {
								if (e.key === 'Enter' || e.key === ' ') {
									e.preventDefault();
									setSection(s.key);
								}
							}}
						>
							<Icon name={s.icon} size={17} />
							<span className="lbl">{s.label}</span>
							{s.count ? <span className="cnt">{s.count}</span> : null}
						</a>
					))}
				</nav>

				<div className="setbody">
					{section === 'company' && <ExporterProfilePanel canEdit={canEdit} />}
					{section === 'automation' && <AutomationPanel canEdit={canEdit} />}
					{section === 'email' && <EmailAccountPanel />}
					{section === 'documents' && (
						<div className="stack">
							<MasterPanel def={DOC_MASTER} options={options} canEdit={canEdit} />
							<ChecklistRulesPanel canEdit={canEdit} />
						</div>
					)}
					{section === 'data' && (
						<>
							<div className="setsub" role="tablist" aria-label="Master lists">
								{DATA_MASTERS.map((m) => (
									<button
										key={m.doctype}
										type="button"
										role="tab"
										aria-selected={activeMaster === m.doctype}
										className={activeMaster === m.doctype ? 'on' : ''}
										onClick={() => setActiveMaster(m.doctype)}
									>
										{m.title}
									</button>
								))}
							</div>
							<MasterPanel key={master.doctype} def={master} options={options} canEdit={canEdit} />
						</>
					)}
				</div>
			</div>

			<footer>
				<b>ExportFlow</b> · DUX Digitech
			</footer>
		</main>
	);
}
