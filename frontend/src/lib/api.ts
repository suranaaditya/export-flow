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
	ports: { name: string; unlocode: string | null; city: string | null; country: string | null; mode: string }[];
	uoms: string[];
	countries: string[];
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
	createCustomer: 'exportflow.api.create_customer',
	createSupplier: 'exportflow.api.create_supplier',
	createItem: 'exportflow.api.create_item',
	soProcurement: 'exportflow.api.get_so_procurement',
	createPo: 'exportflow.api.create_purchase_order',
	submitPo: 'exportflow.api.submit_purchase_order',
	poList: 'exportflow.api.get_purchase_orders',
	poDetail: 'exportflow.api.get_po_detail',
	shippableLines: 'exportflow.api.get_shippable_lines',
	createShipment: 'exportflow.api.create_shipment',
	shipments: 'exportflow.api.get_shipments',
	shipmentDetail: 'exportflow.api.get_shipment_detail',
	setMilestone: 'exportflow.api.set_shipment_milestone',
	newPoContext: 'exportflow.api.get_new_po_context',
	termsText: 'exportflow.api.get_terms_text',
	createPoDraft: 'exportflow.api.create_purchase_order_draft',
	previewPo: 'exportflow.api.preview_purchase_order',
} as const;

export interface NewPOContext {
	company: string;
	company_currency: string;
	suppliers: { name: string; supplier_name: string; default_merchant_export_scheme: 0 | 1 }[];
	items: { name: string; item_name: string; stock_uom: string }[];
	terms_templates: string[];
	taxes_templates: { name: string; is_default: 0 | 1 }[];
	accounts: { name: string; account_name: string }[];
	sales_orders: { name: string; customer_name: string }[];
	uoms: string[];
	countries: string[];
}

export interface POTaxRow {
	description: string;
	rate: number;
	tax_amount: number;
	total: number;
}

export interface POTotals {
	net_total: number;
	total_taxes_and_charges: number;
	grand_total: number;
	taxes: POTaxRow[];
}

/** Frappe print endpoints, generic. */
export function printPreviewUrl(doctype: string, name: string, format: string): string {
	const params = new URLSearchParams({ doctype, name, format, no_letterhead: '1', _lang: 'en' });
	return `/printview?${params.toString()}`;
}

export function printPdfUrl(doctype: string, name: string, format: string): string {
	const params = new URLSearchParams({ doctype, name, format, no_letterhead: '1' });
	return `/api/method/frappe.utils.print_format.download_pdf?${params.toString()}`;
}

// ---- Phase 3: procurement & logistics shapes (exportflow.api) ----

export interface ProcurementPO {
	name: string;
	supplier: string;
	docstatus: 0 | 1;
	qty: number;
	rate: number;
	merchant_export_scheme: 0 | 1;
	gst_export_deadline: string | null;
}

export interface ProcurementLine {
	so_detail: string;
	item_code: string;
	item_name: string;
	qty: number;
	uom: string | null;
	rate: number;
	ordered_qty: number;
	draft_qty: number;
	remaining: number;
	shipped_qty: number;
	in_transit_qty: number;
	pos: ProcurementPO[];
}

export interface SOProcurement {
	lines: ProcurementLine[];
	company_currency: string;
}

export interface POListRow {
	name: string;
	supplier: string;
	supplier_name: string;
	transaction_date: string;
	grand_total: number;
	currency: string;
	status: string;
	docstatus: 0 | 1;
	merchant_export_scheme: 0 | 1;
	supplier_invoice_no: string | null;
	supplier_invoice_date: string | null;
	gst_export_deadline: string | null;
	sales_orders: string[];
}

export interface PODetailData {
	po: Omit<POListRow, 'sales_orders'> & {
		schedule_date: string | null;
		tc_name: string | null;
		terms: string | null;
	};
	totals: POTotals;
	items: {
		name: string;
		item_code: string;
		item_name: string;
		qty: number;
		uom: string | null;
		rate: number;
		amount: number;
		sales_order: string | null;
		sales_order_item: string | null;
		delivered_by_supplier: 0 | 1;
	}[];
	shipments: { shipment: string; current_milestone: string; mode: string; etd: string | null }[];
}

export interface ShippableLine {
	so_detail: string;
	sales_order: string;
	item_code: string;
	item_name: string;
	qty: number;
	uom: string | null;
	shipped_qty: number;
	remaining: number;
	purchase_order: string | null;
	po_detail: string | null;
	supplier: string | null;
}

export interface ShipmentListRow {
	name: string;
	customer: string;
	customer_name: string;
	mode: 'Sea' | 'Air';
	current_milestone: string;
	etd: string | null;
	eta: string | null;
	port_of_loading: string | null;
	port_of_discharge: string | null;
	milestones_total: number;
	milestones_done: number;
}

export interface ShipmentMilestoneRow {
	name: string;
	milestone: string;
	planned_date: string | null;
	actual_date: string | null;
	completed: 0 | 1;
}

export interface ShipmentItemRow {
	name: string;
	item_code: string;
	item_name: string;
	batch_no: string | null;
	qty: number;
	uom: string | null;
	pack_description: string | null;
	sales_order: string;
	so_detail: string;
	so_qty: number;
	so_shipped_total: number;
	purchase_order: string | null;
	po_cancelled: 0 | 1;
	supplier: string | null;
	merchant_export_scheme: 0 | 1;
	gst_export_deadline: string | null;
}

export interface ShipmentDetailData {
	/** actual date the export milestone (Shipped on Board / Departed) completed */
	export_completed_on: string | null;
	shipment: {
		name: string;
		customer: string;
		customer_name: string;
		mode: 'Sea' | 'Air';
		current_milestone: string;
		incoterm: string | null;
		cha: string | null;
		port_of_loading: string | null;
		port_of_discharge: string | null;
		final_destination: string | null;
		etd: string | null;
		eta: string | null;
		vessel: string | null;
		voyage: string | null;
		booking_number: string | null;
		container_numbers: string | null;
		vgm_filed: 0 | 1;
		shipping_bill_number: string | null;
		shipping_bill_date: string | null;
		leo_date: string | null;
		bl_number: string | null;
		bl_date: string | null;
		egm_number: string | null;
		egm_date: string | null;
		airline: string | null;
		flight_number: string | null;
		awb_number: string | null;
		awb_date: string | null;
		letter_of_credit: string | null;
		notes: string | null;
	};
	milestones: ShipmentMilestoneRow[];
	items: ShipmentItemRow[];
	lc: {
		name: string;
		lc_number: string;
		status: LCStatus;
		expiry_date: string;
		latest_shipment_date: string;
		issuing_bank: string | null;
	} | null;
	sales_orders: string[];
}

/** ERPNext PO workflow status → chip tone. */
export function poTone(status: string, docstatus: 0 | 1): 'ok' | 'pend' | 'err' {
	if (docstatus === 0) return 'pend';
	if (status === 'Delivered' || status === 'Completed' || status === 'Closed') return 'ok';
	if (status === 'Cancelled' || status === 'On Hold') return 'err';
	return 'pend';
}

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
