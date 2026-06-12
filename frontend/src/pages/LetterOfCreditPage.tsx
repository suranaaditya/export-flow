import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import {
	useFrappeCreateDoc,
	useFrappeGetCall,
	useFrappeGetDoc,
	useFrappeGetDocList,
	useFrappeUpdateDoc,
} from 'frappe-react-sdk';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { Icon } from '@/components/Icon';
import { CheckInput, Field, SelectInput, TextArea, TextInput } from '@/components/form';
import { Card, CHead, Facts, Tag } from '@/components/ui';
import {
	API,
	lcIsOpen,
	lcTone,
	parseServerError,
	urgencyLabel,
	urgencyTone,
	type LCStatus,
	type SOMoneySummary,
} from '@/lib/api';
import { daysUntil, fmtDateLong } from '@/lib/format';

interface LCRequirement {
	name: string | null;
	document_type: string | null;
	description: string | null;
	originals: number | null;
	copies: number | null;
	notes: string | null;
}

interface LCDoc {
	name: string;
	sales_order: string;
	customer_name: string;
	lc_number: string;
	status: LCStatus;
	issuing_bank: string | null;
	advising_bank: string | null;
	negotiating_bank: string | null;
	amount: number;
	currency: string;
	tolerance_percentage: number | null;
	issue_date: string | null;
	expiry_date: string | null;
	latest_shipment_date: string | null;
	place_of_expiry: string | null;
	presentation_period_days: number | null;
	alert_thresholds: string | null;
	partial_shipments_allowed: 0 | 1;
	transhipment_allowed: 0 | 1;
	notes: string | null;
	document_requirements: LCRequirement[];
}

const LC_STATUSES: LCStatus[] = [
	'Received',
	'Active',
	'Documents Presented',
	'Negotiated/Paid',
	'Closed',
	'Expired',
];

interface FormState {
	lc_number: string;
	status: LCStatus;
	issuing_bank: string;
	advising_bank: string;
	negotiating_bank: string;
	amount: string;
	tolerance_percentage: string;
	issue_date: string;
	expiry_date: string;
	latest_shipment_date: string;
	place_of_expiry: string;
	presentation_period_days: string;
	alert_thresholds: string;
	partial_shipments_allowed: boolean;
	transhipment_allowed: boolean;
	notes: string;
}

interface ReqRow {
	/** child row name — kept so saves update rows in place instead of recreating */
	name: string;
	document_type: string;
	description: string;
	originals: string;
	copies: string;
	/** desk-only field, carried through so React saves don't wipe it */
	notes: string;
}

const EMPTY_FORM: FormState = {
	lc_number: '',
	status: 'Received',
	issuing_bank: '',
	advising_bank: '',
	negotiating_bank: '',
	amount: '',
	tolerance_percentage: '',
	issue_date: '',
	expiry_date: '',
	latest_shipment_date: '',
	place_of_expiry: '',
	presentation_period_days: '',
	alert_thresholds: '',
	partial_shipments_allowed: false,
	transhipment_allowed: false,
	notes: '',
};

const EMPTY_REQ: ReqRow = {
	name: '',
	document_type: '',
	description: '',
	originals: '',
	copies: '',
	notes: '',
};

/** Deadline chip via the shared urgency mapping; none for closed LCs. */
function dueChip(date: string, open: boolean): ReactNode {
	if (!open) return null;
	const d = daysUntil(date || null);
	const tone = urgencyTone(d);
	if (d === null || tone === null) return null;
	return <Tag tone={tone}>{urgencyLabel(d)}</Tag>;
}

function dateFact(date: string, open: boolean): ReactNode {
	return (
		<span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
			<span className="data">{fmtDateLong(date || null)}</span>
			{dueChip(date, open)}
		</span>
	);
}

export function LetterOfCreditPage() {
	const { name } = useParams<{ name: string }>();
	const [searchParams] = useSearchParams();
	const navigate = useNavigate();
	const isNew = !name;
	const soParam = searchParams.get('so') ?? '';

	const { data: doc, error, isLoading, mutate } = useFrappeGetDoc<LCDoc>(
		'Letter of Credit',
		name,
		isNew ? null : undefined,
	);
	const { data: docTypes } = useFrappeGetDocList<{ name: string }>('Document Type', {
		fields: ['name'],
		limit: 100,
	});
	// new mode: the deal currency comes from the SO money summary
	const { data: soData } = useFrappeGetCall<{ message: SOMoneySummary }>(
		API.soMoneySummary,
		{ sales_order: soParam },
		isNew && soParam ? undefined : null,
	);
	const { createDoc, loading: creating } = useFrappeCreateDoc();
	const { updateDoc, loading: updating } = useFrappeUpdateDoc();

	const [form, setForm] = useState<FormState>(EMPTY_FORM);
	const [reqs, setReqs] = useState<ReqRow[]>([]);
	const [formErr, setFormErr] = useState<string | null>(null);
	// seed once per doc name so background revalidation never discards edits
	const seededFor = useRef<string | null>(null);

	useEffect(() => {
		if (!doc || seededFor.current === doc.name) return;
		seededFor.current = doc.name;
		setForm({
			lc_number: doc.lc_number ?? '',
			status: doc.status ?? 'Received',
			issuing_bank: doc.issuing_bank ?? '',
			advising_bank: doc.advising_bank ?? '',
			negotiating_bank: doc.negotiating_bank ?? '',
			amount: doc.amount != null ? String(doc.amount) : '',
			tolerance_percentage: doc.tolerance_percentage != null ? String(doc.tolerance_percentage) : '',
			issue_date: doc.issue_date ?? '',
			expiry_date: doc.expiry_date ?? '',
			latest_shipment_date: doc.latest_shipment_date ?? '',
			place_of_expiry: doc.place_of_expiry ?? '',
			presentation_period_days:
				doc.presentation_period_days != null ? String(doc.presentation_period_days) : '',
			alert_thresholds: doc.alert_thresholds ?? '',
			partial_shipments_allowed: !!doc.partial_shipments_allowed,
			transhipment_allowed: !!doc.transhipment_allowed,
			notes: doc.notes ?? '',
		});
		setReqs(
			(doc.document_requirements ?? []).map((r) => ({
				name: r.name ?? '',
				document_type: r.document_type ?? '',
				description: r.description ?? '',
				originals: r.originals != null ? String(r.originals) : '',
				copies: r.copies != null ? String(r.copies) : '',
				notes: r.notes ?? '',
			})),
		);
	}, [doc]);

	const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
		setForm((f) => ({ ...f, [key]: value }));
	const setReq = (i: number, key: keyof ReqRow, value: string) =>
		setReqs((rows) => rows.map((r, idx) => (idx === i ? { ...r, [key]: value } : r)));

	const salesOrder = doc?.sales_order ?? soParam;
	const customerName = doc?.customer_name ?? soData?.message?.so?.customer_name ?? '';
	const currency = doc?.currency ?? soData?.message?.so?.currency ?? '';
	const statusOpen = lcIsOpen(form.status);
	const saving = creating || updating;
	const docTypeOptions = (docTypes ?? []).map((d) => ({ value: d.name }));

	async function onSave() {
		if (!form.lc_number.trim()) {
			setFormErr('LC number is required.');
			return;
		}
		if (!form.amount || Number.isNaN(Number(form.amount)) || Number(form.amount) <= 0) {
			setFormErr('Amount is required.');
			return;
		}
		const keptReqs = reqs.filter((r) => r.document_type || r.description.trim());
		if (keptReqs.some((r) => !r.document_type)) {
			setFormErr('Each requirement row needs a document type.');
			return;
		}
		setFormErr(null);
		const payload: Record<string, unknown> = {
			lc_number: form.lc_number.trim(),
			status: form.status,
			issuing_bank: form.issuing_bank,
			advising_bank: form.advising_bank,
			negotiating_bank: form.negotiating_bank,
			amount: Number(form.amount),
			issue_date: form.issue_date || null,
			expiry_date: form.expiry_date || null,
			latest_shipment_date: form.latest_shipment_date || null,
			place_of_expiry: form.place_of_expiry,
			partial_shipments_allowed: form.partial_shipments_allowed ? 1 : 0,
			transhipment_allowed: form.transhipment_allowed ? 1 : 0,
			notes: form.notes,
			document_requirements: keptReqs.map((r) => ({
				...(r.name ? { name: r.name } : {}),
				document_type: r.document_type,
				description: r.description,
				originals: r.originals ? Number(r.originals) : 0,
				copies: r.copies ? Number(r.copies) : 0,
				notes: r.notes,
			})),
		};
		// omit empty optional numerics so doctype defaults apply (e.g. the
		// 21-day presentation period); 0 would suppress them
		if (form.tolerance_percentage) payload.tolerance_percentage = Number(form.tolerance_percentage);
		if (form.presentation_period_days)
			payload.presentation_period_days = Number(form.presentation_period_days);
		if (form.alert_thresholds.trim()) payload.alert_thresholds = form.alert_thresholds.trim();
		try {
			if (isNew) {
				payload.sales_order = soParam;
				const created = await createDoc('Letter of Credit', payload);
				navigate('/lc/' + created.name);
			} else if (name) {
				await updateDoc('Letter of Credit', name, payload);
				seededFor.current = null; // reseed from the saved doc
				mutate();
			}
		} catch (e) {
			setFormErr(parseServerError(e));
		}
	}

	if (!isNew && isLoading) {
		return (
			<main className="tight">
				<div className="sub">Loading…</div>
			</main>
		);
	}

	if (!isNew && error) {
		return (
			<main className="tight">
				<Card>
					<div className="ferr" style={{ padding: 18 }}>
						Could not load this letter of credit. It may have been deleted.
					</div>
				</Card>
				<footer>
					<b>ExportFlow</b> · DUX Digitech
				</footer>
			</main>
		);
	}

	// an LC is always recorded against a sales order — guard direct URL entry
	if (isNew && !soParam) {
		return (
			<main className="tight">
				<div className="eyebrow">Selling · Letter of credit</div>
				<h1>
					New letter of <em>credit</em>
				</h1>
				<div style={{ marginTop: 22 }}>
					<Card>
						<div className="ferr" style={{ padding: '18px 20px' }}>
							Open from a sales order — a letter of credit is always recorded against one.{' '}
							<Link to="/sales-orders">Go to sales orders</Link>
						</div>
					</Card>
				</div>
				<footer>
					<b>ExportFlow</b> · DUX Digitech
				</footer>
			</main>
		);
	}

	return (
		<main className="tight">
			<div className="eyebrow">Selling · Letter of credit</div>
			<div className="crumb">
				<Link to="/sales-orders">Sales orders</Link>
				{salesOrder && (
					<>
						{' / '}
						<Link to={`/sales-orders/${salesOrder}`} className="data">
							{salesOrder}
						</Link>
					</>
				)}
				{' / '}
				{isNew ? <span>New</span> : <span className="data">{form.lc_number || name}</span>}
			</div>
			<div className="titlebar">
				{isNew ? (
					<span className="who">New letter of credit</span>
				) : (
					<h1>{form.lc_number || name}</h1>
				)}
				{customerName && <span className="who">{customerName}</span>}
				<span style={{ marginTop: 7 }}>
					<Tag tone={lcTone(form.status)}>{form.status}</Tag>
				</span>
				<span className="spacer" />
			</div>

			<div className="grid detail" style={{ marginTop: 18 }}>
				<Card>
					<CHead icon="calendar" title={isNew ? 'New letter of credit' : form.lc_number || 'Letter of credit'} />
					<div className="formgrid">
						<Field label="LC number" required>
							<TextInput mono value={form.lc_number} onChange={(v) => set('lc_number', v)} placeholder="e.g. ILC-2026-00142" />
						</Field>
						<Field label="Status">
							<SelectInput
								value={form.status}
								onChange={(v) => set('status', v as LCStatus)}
								options={LC_STATUSES.map((s) => ({ value: s }))}
							/>
						</Field>
						<Field label="Issuing bank">
							<TextInput value={form.issuing_bank} onChange={(v) => set('issuing_bank', v)} />
						</Field>
						<Field label="Advising bank">
							<TextInput value={form.advising_bank} onChange={(v) => set('advising_bank', v)} />
						</Field>
						<Field label="Negotiating bank">
							<TextInput value={form.negotiating_bank} onChange={(v) => set('negotiating_bank', v)} />
						</Field>
						<Field label="Amount" required hint={currency ? `In ${currency}` : undefined}>
							<TextInput type="number" value={form.amount} onChange={(v) => set('amount', v)} />
						</Field>
						<Field label="Tolerance %">
							<TextInput type="number" step="0.5" value={form.tolerance_percentage} onChange={(v) => set('tolerance_percentage', v)} />
						</Field>
						<Field label="Issue date">
							<TextInput type="date" value={form.issue_date} onChange={(v) => set('issue_date', v)} />
						</Field>
						<Field label="Expiry date">
							<TextInput type="date" value={form.expiry_date} onChange={(v) => set('expiry_date', v)} />
						</Field>
						<Field label="Latest shipment date">
							<TextInput type="date" value={form.latest_shipment_date} onChange={(v) => set('latest_shipment_date', v)} />
						</Field>
						<Field label="Place of expiry">
							<TextInput value={form.place_of_expiry} onChange={(v) => set('place_of_expiry', v)} />
						</Field>
						<Field label="Presentation period days">
							<TextInput type="number" value={form.presentation_period_days} onChange={(v) => set('presentation_period_days', v)} />
						</Field>
						<Field label="Alert thresholds" hint="Days before dates to alert, e.g. 15,7,3">
							<TextInput mono value={form.alert_thresholds} onChange={(v) => set('alert_thresholds', v)} />
						</Field>
						<div style={{ paddingTop: 22 }}>
							<CheckInput
								checked={form.partial_shipments_allowed}
								onChange={(v) => set('partial_shipments_allowed', v)}
								label="Partial shipments allowed"
							/>
						</div>
						<CheckInput
							checked={form.transhipment_allowed}
							onChange={(v) => set('transhipment_allowed', v)}
							label="Transhipment allowed"
						/>
						<div className="span2">
							<Field label="Notes">
								<TextArea value={form.notes} onChange={(v) => set('notes', v)} />
							</Field>
						</div>
					</div>

					<div className="reqhead" style={{ borderTop: '1px solid var(--hairline)' }}>
						<span>Document type</span>
						<span>As worded in the LC</span>
						<span>Orig.</span>
						<span>Copies</span>
						<span />
					</div>
					{reqs.map((r, i) => (
						<div className="reqrow" key={i}>
							<SelectInput
								value={r.document_type}
								onChange={(v) => setReq(i, 'document_type', v)}
								options={docTypeOptions}
								allowEmpty
							/>
							<TextInput value={r.description} onChange={(v) => setReq(i, 'description', v)} placeholder="As worded in the LC" />
							<TextInput type="number" value={r.originals} onChange={(v) => setReq(i, 'originals', v)} />
							<TextInput type="number" value={r.copies} onChange={(v) => setReq(i, 'copies', v)} />
							<button
								type="button"
								className="xbtn"
								aria-label="Remove requirement"
								onClick={() => setReqs((rows) => rows.filter((_, idx) => idx !== i))}
							>
								<Icon name="close" size={14} />
							</button>
						</div>
					))}
					<div style={{ padding: '8px 18px 14px' }}>
						<button type="button" className="btn" onClick={() => setReqs((rows) => [...rows, { ...EMPTY_REQ }])}>
							<Icon name="plus" size={15} />
							Add requirement
						</button>
					</div>

					<div className="formfoot">
						{formErr && <span className="ferr">{formErr}</span>}
						<span className="spacer" />
						<button type="button" className="btn primary" disabled={saving} onClick={onSave}>
							<Icon name="check" size={15} />
							{saving ? 'Saving…' : isNew ? 'Create LC' : 'Save changes'}
						</button>
					</div>
				</Card>

				<div className="stack">
					<Card>
						<CHead icon="clock" title="Dates" />
						<Facts
							rows={[
								{ k: 'Latest shipment', v: dateFact(form.latest_shipment_date, statusOpen) },
								{ k: 'Expiry', v: dateFact(form.expiry_date, statusOpen) },
								{
									k: 'Presentation period',
									v: form.presentation_period_days
										? `${form.presentation_period_days} days after B/L`
										: '—',
									data: true,
								},
							]}
						/>
					</Card>
					<Card>
						<CHead icon="link-boxes" title="Linked" />
						<Facts
							rows={[
								{
									k: 'Sales order',
									v: salesOrder ? (
										<Link to={`/sales-orders/${salesOrder}`} className="data">
											{salesOrder}
										</Link>
									) : (
										'—'
									),
								},
								{ k: 'Customer', v: customerName || '—' },
							]}
						/>
					</Card>
				</div>
			</div>

			<footer>
				<b>ExportFlow</b> · DUX Digitech
			</footer>
		</main>
	);
}
