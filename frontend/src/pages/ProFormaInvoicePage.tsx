import { useEffect, useRef, useState, type ReactNode } from 'react';
import {
	useFrappeCreateDoc,
	useFrappeGetCall,
	useFrappeGetDoc,
	useFrappeGetDocList,
	useFrappePostCall,
	useFrappeUpdateDoc,
} from 'frappe-react-sdk';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useConfirm } from '@/components/ConfirmDialog';
import { EmailComposer } from '@/components/EmailComposer';
import { Icon } from '@/components/Icon';
import { useToast } from '@/components/Toast';
import { Field, SearchSelect, SelectInput, TextArea, TextInput } from '@/components/form';
import { Card, CHead, Facts, Tag } from '@/components/ui';
import {
	API,
	parseServerError,
	pfiPdfUrl,
	pfiPrintPreviewUrl,
	pfiTone,
	type PFIStatus,
	type SOMoneySummary,
} from '@/lib/api';
import { fmtMoney } from '@/lib/format';

/** Pro Forma Invoice doc as returned by frappe.client.get (exportflow doctype). */
interface PFIDoc {
	name: string;
	sales_order?: string;
	customer_name?: string;
	company?: string;
	pfi_date?: string;
	status?: PFIStatus;
	basis?: string;
	percentage?: number;
	currency?: string;
	conversion_rate?: number;
	amount?: number;
	paid_amount?: number;
	stage_description?: string;
	expected_payment_method?: string;
	bank_account?: string;
	terms?: string;
}

/** Writable PFI fields sent on create/update. */
interface PFIWritable {
	sales_order?: string;
	pfi_date?: string;
	basis?: string;
	percentage?: number;
	amount?: number;
	stage_description?: string;
	expected_payment_method?: string;
	bank_account?: string;
	terms?: string;
}

interface BankAccountRow {
	name: string;
	account_name?: string;
	bank?: string;
	is_company_account?: 0 | 1;
}

const BASIS_PCT = 'Percentage of SO';
const BASIS_MANUAL = 'Manual amount';

/** Today as yyyy-mm-dd in local time (toISOString would shift IST evenings). */
function todayISO(): string {
	const d = new Date();
	const m = String(d.getMonth() + 1).padStart(2, '0');
	const day = String(d.getDate()).padStart(2, '0');
	return `${d.getFullYear()}-${m}-${day}`;
}

/** Scaffold for the pre-data states (missing SO param, loading, load error). */
function PageFrame({ children }: { children: ReactNode }) {
	return (
		<main className="tight">
			<div className="eyebrow">Selling · Pro forma invoice</div>
			<h1>
				Pro forma <em>invoice</em>
			</h1>
			{children}
			<footer>
				<b>ExportFlow</b> · DUX Digitech
			</footer>
		</main>
	);
}

export function ProFormaInvoicePage() {
	const { name } = useParams<{ name: string }>();
	const [searchParams] = useSearchParams();
	const navigate = useNavigate();
	const isNew = !name;
	const soParam = searchParams.get('so');

	// Existing doc (skipped in new mode via null SWR key).
	const docResult = useFrappeGetDoc<PFIDoc>('Pro Forma Invoice', name, name ? undefined : null);
	const doc = docResult.data;

	const soId = isNew ? soParam : (doc?.sales_order ?? null);

	// SO money context — skipped until the sales order is known.
	const soResult = useFrappeGetCall<{ message: SOMoneySummary }>(
		API.soMoneySummary,
		{ sales_order: soId ?? '' },
		soId ? undefined : null,
	);
	const so = soResult.data?.message;

	const bankList = useFrappeGetDocList<BankAccountRow>('Bank Account', {
		fields: ['name', 'account_name', 'bank'],
		filters: [['is_company_account', '=', 1]],
		limit: 50,
	});

	// Form state, seeded from the doc once loaded.
	const [pfiDate, setPfiDate] = useState(todayISO);
	const [basis, setBasis] = useState(BASIS_PCT);
	const [percentage, setPercentage] = useState('');
	const [amount, setAmount] = useState('');
	const [stageDescription, setStageDescription] = useState('');
	const [paymentMethod, setPaymentMethod] = useState('');
	const [bankAccount, setBankAccount] = useState('');
	const [terms, setTerms] = useState('');
	const [saveError, setSaveError] = useState<string | null>(null);
	const [actionError, setActionError] = useState<string | null>(null);
	const [emailing, setEmailing] = useState(false);
	const confirm = useConfirm();
	const toast = useToast();

	// Seed form state once per doc name — background revalidation (e.g. after a
	// payment lands) must not clobber in-progress edits.
	const seededFor = useRef<string | null>(null);
	useEffect(() => {
		if (!doc || seededFor.current === doc.name) return;
		seededFor.current = doc.name;
		setPfiDate(doc.pfi_date ?? '');
		setBasis(doc.basis ?? BASIS_PCT);
		setPercentage(doc.percentage != null ? String(doc.percentage) : '');
		setAmount(doc.amount != null ? String(doc.amount) : '');
		setStageDescription(doc.stage_description ?? '');
		setPaymentMethod(doc.expected_payment_method ?? '');
		setBankAccount(doc.bank_account ?? '');
		setTerms(doc.terms ?? '');
	}, [doc]);

	const { createDoc, loading: creating } = useFrappeCreateDoc<PFIWritable>();
	const { updateDoc, loading: updating } = useFrappeUpdateDoc<PFIWritable>();
	const { call: postStatus, loading: statusLoading } = useFrappePostCall(API.pfiSetStatus);
	const saving = creating || updating;

	const status: PFIStatus = doc?.status ?? 'Draft';
	const editable = isNew || status === 'Draft';
	const dis = !editable || saving;
	const isPct = basis === BASIS_PCT;
	const currency = so?.so.currency ?? doc?.currency ?? null;
	const customerName = doc?.customer_name ?? so?.so.customer_name ?? '';

	const soValue = so?.summary.so_value ?? 0;
	const pctNum = Number(percentage) || 0;
	const amtNum = Number(amount) || 0;
	const preview = isPct ? (soValue * pctNum) / 100 : amtNum;

	const paid = doc?.paid_amount ?? 0;
	const canMarkSent = !!name && status === 'Draft';
	const canCancel = !!name && status !== 'Cancelled' && paid === 0;

	const bankOptions = (bankList.data ?? []).map((b) => ({
		value: b.name,
		label: b.bank ? `${b.account_name ?? b.name} — ${b.bank}` : (b.account_name ?? b.name),
	}));

	async function save() {
		setSaveError(null);
		const payload: PFIWritable = {
			pfi_date: pfiDate,
			basis,
			stage_description: stageDescription,
			expected_payment_method: paymentMethod,
			bank_account: bankAccount,
			terms,
		};
		if (isPct) payload.percentage = pctNum;
		else payload.amount = amtNum;
		try {
			if (isNew) {
				if (!soId) return;
				const res = await createDoc('Pro Forma Invoice', { ...payload, sales_order: soId });
				navigate('/pfi/' + res.name);
			} else {
				await updateDoc('Pro Forma Invoice', name ?? null, payload);
				await docResult.mutate();
				await soResult.mutate();
			}
		} catch (e) {
			setSaveError(parseServerError(e));
		}
	}

	async function doStatus(action: 'sent' | 'cancel') {
		if (!name) return;
		if (
			action === 'cancel' &&
			!(await confirm({
				title: 'Cancel pro forma invoice',
				message: 'Cancel this pro forma invoice? This cannot be undone.',
				confirmLabel: 'Cancel PFI',
				danger: true,
			}))
		)
			return;
		setActionError(null);
		try {
			await postStatus({ name, action });
			await docResult.mutate();
			await soResult.mutate();
			toast.ok(action === 'cancel' ? 'Pro forma invoice cancelled' : 'Marked as sent');
		} catch (e) {
			setActionError(parseServerError(e));
			toast.err(parseServerError(e));
		}
	}

	// ---- Pre-data states ----
	if (isNew && !soParam) {
		return (
			<PageFrame>
				<div style={{ marginTop: 14 }}>
					<Card>
						<div style={{ padding: '16px 18px' }}>
							<div className="ferr">Open from a sales order — a pro forma invoice is always raised against one.</div>
							<div style={{ marginTop: 12 }}>
								<Link className="btn" to="/sales-orders">
									Sales orders
								</Link>
							</div>
						</div>
					</Card>
				</div>
			</PageFrame>
		);
	}
	if (!isNew && docResult.error) {
		return (
			<PageFrame>
				<div style={{ marginTop: 14 }}>
					<Card>
						<div className="ferr" style={{ padding: '16px 18px' }}>
							Couldn't load this pro forma invoice. {parseServerError(docResult.error)}
						</div>
					</Card>
				</div>
			</PageFrame>
		);
	}
	if (!isNew && !doc) {
		return (
			<PageFrame>
				<div className="sub" style={{ marginTop: 10 }}>
					Loading…
				</div>
			</PageFrame>
		);
	}
	if (isNew && soResult.error) {
		return (
			<PageFrame>
				<div style={{ marginTop: 14 }}>
					<Card>
						<div className="ferr" style={{ padding: '16px 18px' }}>
							Couldn't load the sales order. {parseServerError(soResult.error)}
						</div>
					</Card>
				</div>
			</PageFrame>
		);
	}

	// ---- Loaded view ----
	return (
		<main className="tight">
			<div className="eyebrow">Selling · Pro forma invoice</div>
			<div className="crumb">
				<Link to="/sales-orders">Sales orders</Link>
				{' / '}
				{soId ? (
					<>
						<Link className="data" to={`/sales-orders/${soId}`}>
							{soId}
						</Link>
						{' / '}
					</>
				) : null}
				{name ? <span className="data">{name}</span> : <span>New</span>}
			</div>
			<div className="titlebar">
				{name ? <h1>{name}</h1> : <span className="who">New pro forma invoice</span>}
				{customerName ? <span className="who">{customerName}</span> : null}
				<span style={{ marginTop: 7 }}>
					<Tag tone={pfiTone(status)}>{status}</Tag>
				</span>
				<span className="spacer" />
			</div>
			{so ? (
				<div className="metaline">
					<span className="kv">
						<b>SO value</b>
						<span className="num">{fmtMoney(so.summary.so_value, currency)}</span>
					</span>
					<span className="kv">
						<b>Raised</b>
						<span className="num">{fmtMoney(so.summary.raised, currency)}</span>
					</span>
					<span className="kv">
						<b>Received</b>
						<span className="num">{fmtMoney(so.summary.received, currency)}</span>
					</span>
					<span className="kv">
						<b>Balance</b>
						<span className="num">{fmtMoney(so.summary.balance, currency)}</span>
					</span>
				</div>
			) : null}
			<div className="grid detail" style={{ marginTop: so ? 0 : 10 }}>
				<Card>
					<CHead icon="banknote" title={name ?? 'New pro forma invoice'} />
					<div className="formgrid">
						<Field label="Date">
							<TextInput type="date" value={pfiDate} onChange={setPfiDate} disabled={dis} />
						</Field>
						<Field label="Basis">
							<SearchSelect
								value={basis}
								onChange={setBasis}
								options={[{ value: BASIS_PCT }, { value: BASIS_MANUAL }]}
								disabled={dis}
							/>
						</Field>
						{isPct ? (
							<Field
								label="Percentage"
								hint={so ? `Of SO value ${fmtMoney(so.summary.so_value, currency)}` : undefined}
							>
								<TextInput
									type="number"
									step="0.01"
									value={percentage}
									onChange={setPercentage}
									disabled={dis}
									placeholder="30"
								/>
							</Field>
						) : (
							<Field label="Amount" hint={currency ? `In ${currency}` : undefined}>
								<TextInput
									type="number"
									step="0.01"
									value={amount}
									onChange={setAmount}
									disabled={dis}
									placeholder="0.00"
								/>
							</Field>
						)}
						<div className="span2">
							<Field label="Stage description">
								<TextInput
									value={stageDescription}
									onChange={setStageDescription}
									disabled={dis}
									placeholder="Advance against order confirmation"
								/>
							</Field>
						</div>
						<Field label="Expected payment method">
							<SelectInput
								value={paymentMethod}
								onChange={setPaymentMethod}
								allowEmpty
								options={[{ value: 'Wire Transfer' }, { value: 'Letter of Credit' }]}
								disabled={dis}
							/>
						</Field>
						<Field label="Bank account">
							<SelectInput
								value={bankAccount}
								onChange={setBankAccount}
								allowEmpty
								options={bankOptions}
								disabled={dis}
							/>
						</Field>
						<div className="span2">
							<Field label="Terms">
								<TextArea value={terms} onChange={setTerms} rows={4} disabled={dis} />
							</Field>
						</div>
					</div>
					{editable ? (
						<div className="formfoot">
							<span className="c2">Computed amount</span>
							<span className="num">{fmtMoney(preview, currency)}</span>
							{saveError ? <span className="ferr">{saveError}</span> : null}
							<span className="spacer" />
							<button className="btn primary" onClick={save} disabled={saving}>
								<Icon name="check" size={15} />
								{saving ? 'Saving…' : 'Save'}
							</button>
						</div>
					) : null}
				</Card>
				<div className="stack">
					<Card>
						<CHead icon="circle-check" title="Status" />
						<Facts
							rows={[
								{ k: 'Status', v: <Tag tone={pfiTone(status)}>{status}</Tag> },
								{ k: 'Amount', v: fmtMoney(isNew ? preview : doc?.amount, currency), data: true },
								{ k: 'Received', v: fmtMoney(doc?.paid_amount, currency), data: true },
								{
									k: 'Sales order',
									v: soId ? (
										<Link className="data" to={`/sales-orders/${soId}`}>
											{soId}
										</Link>
									) : (
										'—'
									),
								},
							]}
						/>
						{name ? (
							<div className="formfoot">
								<button className="btn" onClick={() => setEmailing(true)}>
									<Icon name="send" size={15} />
									Email customer
								</button>
								{canMarkSent ? (
									<button className="btn" onClick={() => doStatus('sent')} disabled={statusLoading}>
										<Icon name="send" size={15} />
										Mark sent
									</button>
								) : null}
								{canCancel ? (
									<button className="btn" onClick={() => doStatus('cancel')} disabled={statusLoading}>
										Cancel PFI
									</button>
								) : null}
								{actionError ? <span className="ferr">{actionError}</span> : null}
								<span className="spacer" />
							</div>
						) : null}
					</Card>
					{name ? (
						<Card>
							<CHead icon="file-text" title="PDF" action={<a href={pfiPdfUrl(name)}>Download</a>} />
							<iframe className="pdfframe" src={pfiPrintPreviewUrl(name)} title="PFI preview" />
						</Card>
					) : null}
					{emailing && name ? (
						<EmailComposer
							doctype="Pro Forma Invoice"
							name={name}
							purpose="pfi_to_customer"
							title="Email customer"
							onClose={() => setEmailing(false)}
						/>
					) : null}
				</div>
			</div>
			<footer>
				<b>ExportFlow</b> · DUX Digitech
			</footer>
		</main>
	);
}
