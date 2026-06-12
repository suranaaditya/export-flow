/** Types for the exportflow whitelisted API (exportflow/api.py). */

export interface SOHeader {
	name: string;
	customer: string;
	customer_name: string;
	currency: string;
	grand_total: number;
	transaction_date: string;
	delivery_date: string | null;
	status: string;
	docstatus: 0 | 1 | 2;
	incoterm: string | null;
	named_place: string | null;
	payment_terms_narrative: string | null;
	company: string;
}

export interface NewSOContext {
	company: string;
	company_currency: string;
	customers: {
		name: string;
		customer_name: string;
		default_currency: string | null;
		default_incoterm: string | null;
	}[];
	suppliers: { name: string; supplier_name: string }[];
	items: { name: string; item_name: string; stock_uom: string; pharmacopoeia_grade: string | null }[];
	incoterms: string[];
	currencies: string[];
}

export interface ItemInfo {
	item_name: string;
	stock_uom: string;
	standard_rate: number | null;
	default_supplier: string | null;
}

export interface PFIRow {
	name: string;
	status: PFIStatus;
	amount: number;
	paid_amount: number;
	stage_description: string | null;
	pfi_date: string;
	expected_payment_method: string | null;
	currency: string;
}

export interface LCRow {
	name: string;
	lc_number: string;
	status: LCStatus;
	amount: number;
	currency: string;
	issuing_bank: string | null;
	expiry_date: string;
	latest_shipment_date: string;
}

export interface SOMoneySummary {
	so: SOHeader;
	pfis: PFIRow[];
	lcs: LCRow[];
	summary: {
		so_value: number;
		raised: number;
		received: number;
		balance: number;
	};
}

export type PFIStatus = 'Draft' | 'Sent' | 'Partially Paid' | 'Paid' | 'Cancelled';
export type LCStatus =
	| 'Received'
	| 'Active'
	| 'Documents Presented'
	| 'Negotiated/Paid'
	| 'Closed'
	| 'Expired';

export const API = {
	soMoneySummary: 'exportflow.api.get_so_money_summary',
	soItems: 'exportflow.api.get_so_items',
	pfiSetStatus: 'exportflow.api.pfi_set_status',
	newSoContext: 'exportflow.api.get_new_so_context',
	itemInfo: 'exportflow.api.get_item_info',
	exchangeRate: 'exportflow.api.get_exchange_rate_to_company',
	createSo: 'exportflow.api.create_export_sales_order',
	submitSo: 'exportflow.api.submit_sales_order',
} as const;

/** Status → mockup chip tone (.tag.ok / .tag.pend / .tag.err). */
export function pfiTone(status: PFIStatus): 'ok' | 'pend' | 'err' {
	if (status === 'Paid') return 'ok';
	if (status === 'Cancelled') return 'err';
	return 'pend';
}

export function lcTone(status: LCStatus): 'ok' | 'pend' | 'err' {
	// green strictly means money arrived (DUX triad: green = approved/paid)
	if (status === 'Negotiated/Paid' || status === 'Closed') return 'ok';
	if (status === 'Expired') return 'err';
	return 'pend';
}

/** LC statuses in which date deadlines still matter. */
export function lcIsOpen(status: LCStatus): boolean {
	return status === 'Received' || status === 'Active';
}

/** Shared deadline urgency mapping (matches backend alert tiers 15/7/3):
 *  overdue or ≤7 days = rose, ≤15 days = amber, otherwise no chip. */
export function urgencyTone(days: number | null): 'ok' | 'pend' | 'err' | null {
	if (days === null || days > 15) return null;
	if (days <= 7) return 'err';
	return 'pend';
}

/** Human copy for a deadline chip: "5d left" / "Today" / "4d overdue". */
export function urgencyLabel(days: number): string {
	if (days === 0) return 'Today';
	if (days < 0) return `${-days}d overdue`;
	return `${days}d left`;
}

/** Extract the human message from a frappe-react-sdk error object.
 *  Frappe v16 error bodies carry `_server_messages` (a JSON array of JSON
 *  strings); the SDK's own `message` is a generic fallback. */
export function parseServerError(e: unknown): string {
	const err = e as {
		_server_messages?: string;
		exception?: string;
		message?: string;
	} | null;
	if (!err) return 'Something went wrong.';
	if (err._server_messages) {
		try {
			const parts = JSON.parse(err._server_messages) as string[];
			const texts = parts
				.map((p) => {
					try {
						return (JSON.parse(p) as { message?: string }).message ?? '';
					} catch {
						return p;
					}
				})
				.filter(Boolean)
				.map((t) => t.replace(/<[^>]*>/g, ''));
			if (texts.length) return texts.join(' ');
		} catch {
			// fall through to the generic fields
		}
	}
	if (err.exception) {
		const tail = err.exception.split(':').slice(1).join(':').trim();
		if (tail) return tail;
	}
	return err.message ?? 'Something went wrong.';
}

export function soTone(status: string): 'ok' | 'pend' | 'err' {
	if (status === 'Completed' || status === 'To Bill') return 'ok';
	if (status === 'Cancelled' || status === 'On Hold') return 'err';
	return 'pend';
}

/** Frappe print endpoints for the PFI PDF. */
export function pfiPrintPreviewUrl(name: string): string {
	const params = new URLSearchParams({
		doctype: 'Pro Forma Invoice',
		name,
		format: 'Pro Forma Invoice',
		no_letterhead: '1',
		_lang: 'en',
	});
	return `/printview?${params.toString()}`;
}

export function pfiPdfUrl(name: string): string {
	const params = new URLSearchParams({
		doctype: 'Pro Forma Invoice',
		name,
		format: 'Pro Forma Invoice',
		no_letterhead: '1',
	});
	return `/api/method/frappe.utils.print_format.download_pdf?${params.toString()}`;
}
