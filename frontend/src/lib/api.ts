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
	tc_name: string | null;
	terms: string | null;
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
	item_tax_templates: string[];
	terms_templates: string[];
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

/** Edit affordances mirrored from the user's ERPNext role permissions. */
export interface DocCan {
	docstatus: 0 | 1 | 2;
	write: boolean;
	edit: boolean; // draft the user may write
	submit: boolean;
	cancel: boolean;
	amend: boolean; // submitted doc the user may amend
	close?: boolean; // closeable orders (SO/PO): submitted & not yet closed
	reopen?: boolean; // closeable orders (SO/PO): currently closed
	resume_amend?: boolean; // cancelled order with an in-progress amended draft
}

export interface SOItemLine {
	item_code: string;
	item_name: string;
	qty: number;
	uom: string | null;
	rate: number;
	amount: number;
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
	items: SOItemLine[];
	can: DocCan;
}

export interface SalesOrderForEdit {
	name: string;
	customer: string;
	currency: string;
	conversion_rate: number;
	transaction_date: string;
	delivery_date: string | null;
	incoterm: string | null;
	named_place: string | null;
	payment_terms_narrative: string | null;
	tc_name: string | null;
	terms: string | null;
	docstatus: 0 | 1 | 2;
	items: { item_code: string; item_name: string; qty: number; uom: string | null; rate: number }[];
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
	updateItem: 'exportflow.api.update_item',
	soProcurement: 'exportflow.api.get_so_procurement',
	createPo: 'exportflow.api.create_purchase_order',
	submitPo: 'exportflow.api.submit_purchase_order',
	poList: 'exportflow.api.get_purchase_orders',
	poDetail: 'exportflow.api.get_po_detail',
	shippableLines: 'exportflow.api.get_shippable_lines',
	shipmentDefaults: 'exportflow.api.get_shipment_defaults',
	createShipment: 'exportflow.api.create_shipment',
	shipments: 'exportflow.api.get_shipments',
	shipmentDetail: 'exportflow.api.get_shipment_detail',
	setMilestone: 'exportflow.api.set_shipment_milestone',
	newPoContext: 'exportflow.api.get_new_po_context',
	termsText: 'exportflow.api.get_terms_text',
	createPoDraft: 'exportflow.api.create_purchase_order_draft',
	previewPo: 'exportflow.api.preview_purchase_order',
	poExchangeRate: 'exportflow.api.get_po_exchange_rate',
	shipmentDocuments: 'exportflow.api.get_shipment_documents',
	documentsWorkspace: 'exportflow.api.get_documents_workspace',
	addDocInstance: 'exportflow.api.add_document_instance',
	updateDocInstance: 'exportflow.api.update_document_instance',
	attachDocFile: 'exportflow.api.attach_document_file',
	generateDocument: 'exportflow.api.generate_document',
	generateAllDocuments: 'exportflow.api.generate_shipment_documents',
	checklistRules: 'exportflow.api.get_checklist_rules',
	dashboard: 'exportflow.api.get_dashboard',
	salesDashboard: 'exportflow.api.get_sales_dashboard',
	compliancePermissions: 'exportflow.api.get_compliance_permissions',
	financeWorkspace: 'exportflow.api.get_finance_workspace',
	shipmentFinance: 'exportflow.api.get_shipment_finance',
	shipmentFinanceSeed: 'exportflow.api.get_shipment_finance_seed',
	soForEdit: 'exportflow.api.get_sales_order_for_edit',
	updateSo: 'exportflow.api.update_sales_order',
	updatePo: 'exportflow.api.update_purchase_order_doc',
	updateShipment: 'exportflow.api.update_shipment',
	amendDoc: 'exportflow.api.amend_document',
	amendedDraft: 'exportflow.api.get_amended_draft',
	closeOrder: 'exportflow.api.close_order',
	reopenOrder: 'exportflow.api.reopen_order',
	companyLogo: 'exportflow.api.get_company_logo',
	reportList: 'exportflow.reports.report_list',
	reportData: 'exportflow.reports.report_data',
	emailContext: 'exportflow.ai_email.email_context',
	emailDraft: 'exportflow.ai_email.email_draft',
	emailSend: 'exportflow.ai_email.email_send',
	emailAccountGet: 'exportflow.ai_email.get_email_account',
	emailAccountSave: 'exportflow.ai_email.save_email_account',
	emailAccountTest: 'exportflow.ai_email.test_email_account',
	forwardContracts: 'exportflow.api.get_forward_contracts',
	openForwards: 'exportflow.api.get_open_forwards',
	grns: 'exportflow.api.get_grns',
	grnContext: 'exportflow.api.get_grn_context',
	grnDetail: 'exportflow.api.get_grn_detail',
	createGrn: 'exportflow.api.create_grn',
	updateGrn: 'exportflow.api.update_grn',
	submitGrn: 'exportflow.api.submit_grn',
	cancelGrn: 'exportflow.api.cancel_grn',
	attachGrnInvoice: 'exportflow.api.attach_grn_invoice',
	listDocAttachments: 'exportflow.api.list_doc_attachments',
	removeDocAttachment: 'exportflow.api.remove_doc_attachment',
	grnPacks: 'exportflow.api.get_grn_packs',
	receivablePos: 'exportflow.api.get_receivable_pos',
	addGrnDocument: 'exportflow.api.add_grn_document',
	removeGrnDocument: 'exportflow.api.remove_grn_document',
	supplierDocTypes: 'exportflow.api.get_supplier_document_types',
	syncGrnDocuments: 'exportflow.api.sync_grn_documents',
	returnContext: 'exportflow.api.get_return_context',
	createReturn: 'exportflow.api.create_return',
	updateReturn: 'exportflow.api.update_return',
	submitReturn: 'exportflow.api.submit_return',
	cancelReturn: 'exportflow.api.cancel_return',
	returnDetail: 'exportflow.api.get_return_detail',
	returns: 'exportflow.api.get_returns',
} as const;

export interface ForwardContract {
	name: string;
	contract_no: string;
	ad_bank: string | null;
	currency: string;
	contract_amount: number;
	forward_rate: number;
	inr_value: number;
	booking_date: string | null;
	maturity_date: string | null;
	status: string;
	utilized_amount: number;
	outstanding_amount: number;
	hedge_note: string | null;
	notes: string | null;
	days_to_maturity: number | null;
}
export interface FxExposure {
	currency: string;
	receivable: number;
	hedged: number;
	open_exposure: number;
	hedge_pct: number | null;
	over_hedged: number;
}
export interface OpenForward {
	name: string;
	contract_no: string;
	currency: string;
	forward_rate: number;
	outstanding_amount: number;
	maturity_date: string | null;
	label: string;
}

export interface EmailAccount {
	email: string | null;
	sender_name: string | null;
	host: string;
	port: number;
	use_ssl: boolean;
	has_password: boolean;
	configured: boolean;
}

export interface EmailContext {
	purpose: string;
	to: string | null;
	to_name: string | null;
	party_type: string;
	attachment_label: string;
	facts: Record<string, unknown>;
	sandbox: string | null;
}

export type ReportColType = 'text' | 'id' | 'inr' | 'num' | 'pct' | 'date' | 'days' | 'tag';
export interface ReportColumn {
	key: string;
	label: string;
	type: ReportColType;
}
export interface ReportFilterDef {
	key: string;
	label: string;
	control: 'daterange' | 'select' | 'searchselect' | 'toggle';
	field: string;
}
export interface ReportData {
	title: string;
	columns: ReportColumn[];
	filters: ReportFilterDef[];
	rows: Record<string, string | number | boolean | null>[];
	company: string | null;
	totals?: boolean; // false => line-granularity report, no summed totals row
}
export interface ReportCatalogItem {
	key: string;
	title: string;
	sub: string;
	icon: string;
}

// ---- Phase 6: export incentives + bank realization ----

export type IncentiveScheme = 'RoDTEP' | 'Duty Drawback';
export type IncentiveStatus =
	| 'Pending'
	| 'Scroll Generated'
	| 'Scrip Generated'
	| 'Credited'
	| 'Utilized'
	| 'Not Applicable'
	| 'Cancelled';

export const INCENTIVE_STATUSES: IncentiveStatus[] = [
	'Pending',
	'Scroll Generated',
	'Scrip Generated',
	'Credited',
	'Utilized',
	'Not Applicable',
	'Cancelled',
];

export interface IncentiveRow {
	name: string;
	scheme: IncentiveScheme;
	shipment: string | null;
	status: IncentiveStatus;
	shipping_bill_no: string | null;
	shipping_bill_date: string | null;
	fob_value: number | null;
	rate_pct: number | null;
	amount: number | null;
	scroll_number: string | null;
	scroll_date: string | null;
	scrip_number: string | null;
	scrip_expiry: string | null;
	drawback_serial: string | null;
	amount_received: number | null;
	received_date: string | null;
	remarks: string | null;
	modified: string;
}

export type RealizationStatus =
	| 'Lodged with Bank'
	| 'Awaiting Realization'
	| 'Partially Realized'
	| 'Realized'
	| 'eBRC Closed'
	| 'Overdue'
	| 'Written Off'
	| 'Cancelled';

export const REALIZATION_STATUSES: RealizationStatus[] = [
	'Lodged with Bank',
	'Awaiting Realization',
	'Partially Realized',
	'Realized',
	'eBRC Closed',
	'Overdue',
	'Written Off',
	'Cancelled',
];

export interface RealizationRow {
	name: string;
	export_invoice: string | null;
	shipment: string | null;
	customer: string | null;
	status: RealizationStatus;
	currency: string | null;
	invoice_value: number | null;
	export_date: string | null;
	due_date: string | null;
	ad_bank: string | null;
	fbc_number: string | null;
	firc_no: string | null;
	remittance_date: string | null;
	amount_received: number | null;
	amount_received_inr: number | null;
	bank_charges: number | null;
	conversion_mode: string | null;
	conversion_rate: number | null;
	forward_contract: string | null;
	ebrc_number: string | null;
	ebrc_date: string | null;
	brc_ref: string | null;
	oc_received: 0 | 1;
	remarks: string | null;
	modified: string;
	overdue?: boolean;
}

// ---- Third-country / merchanting (MTT) ----

export const TRADE_TYPES = ['Export from India', 'Third-country / Merchanting'] as const;
export type TradeType = (typeof TRADE_TYPES)[number];

/** Placeholder CHA auto-stamped on merchanting shipments (ExportFlow Settings
 *  toggle) — a merchanting trade has no Indian customs agent. */
export const THIRD_COUNTRY_CHA = 'Third Country';

export function isMerchanting(t: string | null | undefined): boolean {
	return t === 'Third-country / Merchanting';
}

/** FEMA merchanting compliance picture for one shipment (exportflow.mtt.clocks). */
export interface MTTBlock {
	is_merchanting: true;
	commencement_date: string | null;
	completion_due: string | null;
	completion_days: number | null;
	completed: boolean;
	completion_date: string | null;
	outlay_due: string | null;
	outlay_days: number | null;
	outlay_open: boolean;
	import_payment_date: string | null;
	import_value_inr: number | null;
	export_proceeds_inr: number | null;
	net_fx_profit_inr: number | null;
	same_ad_bank: boolean;
	ad_bank: string | null;
	idpms_status: string | null;
	edpms_status: string | null;
}

export interface MTTTrade extends MTTBlock {
	shipment: string;
	customer_name: string | null;
}

export interface FinanceWorkspaceData {
	incentives: IncentiveRow[];
	realizations: RealizationRow[];
	mtt_trades: MTTTrade[];
	kpis: {
		incentive_total?: number;
		incentive_pending?: number;
		realized?: number;
		overdue_count?: number;
		open_count?: number;
		mtt_count?: number;
		mtt_completion_overdue?: number;
		mtt_outlay_overdue?: number;
		mtt_fx_negative?: number;
	};
	can: FinanceCan & {
		incentive_read: boolean;
		realization_read: boolean;
		mtt_read: boolean;
	};
}

/** Per-doctype affordance gating shared by the Finance screen and the shipment
 *  finance card: create → add, write → edit a row, delete → remove a mistake. */
export interface FinanceCan {
	incentive_create: boolean;
	incentive_write: boolean;
	incentive_delete: boolean;
	realization_create: boolean;
	realization_write: boolean;
	realization_delete: boolean;
}

export interface ShipmentFinanceData {
	incentives: IncentiveRow[];
	realizations: RealizationRow[];
	mtt: MTTBlock | null;
	can: FinanceCan;
}

/** Pre-fill values for creating an incentive/realization from a shipment.
 *  Export value = Σ(shipped qty × SO line rate): FCY for the realization
 *  invoice value, INR for the incentive FOB basis. */
export interface ShipmentFinanceSeed {
	shipment: string;
	customer: string | null;
	customer_name: string | null;
	merchanting: boolean;
	currency: string | null;
	currency_conflict: boolean;
	invoice_value: number | null;
	fob_value_inr: number;
	export_date: string | null;
}

/** Incentive status → chip tone. */
export function incentiveTone(s: IncentiveStatus): 'ok' | 'pend' | 'err' {
	if (s === 'Credited' || s === 'Utilized' || s === 'Scrip Generated') return 'ok';
	if (s === 'Cancelled' || s === 'Not Applicable') return 'err';
	return 'pend';
}

/** Realization status → chip tone (overdue overrides). */
export function realizationTone(r: RealizationRow): 'ok' | 'pend' | 'err' {
	if (r.overdue) return 'err';
	if (r.status === 'Realized' || r.status === 'eBRC Closed') return 'ok';
	if (r.status === 'Written Off' || r.status === 'Cancelled') return 'err';
	return 'pend';
}

// ---- Phase 5: sales / financial dashboard ----

export interface SalesDashboardData {
	kpis: {
		export_value_inr?: number;
		export_value_by_currency?: { currency: string; amount: number }[];
		order_count?: number;
		open_value_inr?: number;
		pfi_raised_inr?: number;
		pfi_received_inr?: number;
		pfi_outstanding_inr?: number;
		procurement_inr?: number;
		gross_margin_inr?: number;
		margin_pct?: number;
		incentive_inr?: number;
		incentive_pending_inr?: number;
		realized_inr?: number;
		realization_outstanding_inr?: number;
		realization_overdue?: number;
		net_margin_inr?: number;
	};
	by_customer: { customer: string; value_inr: number; orders: number }[];
	by_country: { country: string; value_inr: number }[];
	by_month: { month: string; value_inr: number }[];
	top_products: { item: string; value_inr: number }[];
	can: { so: boolean; pfi: boolean; po: boolean };
}

// ---- Phase 5: dashboard ----

export interface DashShipmentRow {
	name: string;
	customer_name: string;
	route: string | null;
	mode: 'Sea' | 'Air';
	current_milestone: string;
	milestones_done: number;
	milestones_total: number;
	docs_done: number;
	docs_total: number;
	etd: string | null;
	chip: string;
	tone: 'ok' | 'pend' | 'err';
}

export interface DeadlineRow {
	kind: 'lc' | 'gst' | 'compliance' | 'mtt';
	label: string;
	/** ID rendered mono+cyan (LC number, PO name); null for compliance rows */
	ref: string | null;
	sub: string;
	days: number;
	route: string;
}

export interface DashDocRow {
	document_type: string;
	shipment: string | null;
	status: string;
	responsible_party: string | null;
	days: number | null;
	blocking: 0 | 1;
}

export interface DashPfiRow {
	name: string;
	customer: string;
	stage_description: string | null;
	balance: number;
	currency: string;
	pfi_date: string;
}

export interface DashboardData {
	kpis: {
		live_shipments?: number;
		awaiting_leo?: number;
		in_transit?: number;
		docs_pending?: number;
		docs_blocking?: number;
		docs_with_cha?: number;
		docs_due_soon?: number;
		deadlines_14d?: number;
		lc_at_risk?: number;
		gst_at_risk?: number;
		receivable?: { currency: string; amount: number }[];
		open_pfis?: number;
		export_value_inr?: number;
		realized_inr?: number;
		outstanding_inr?: number;
		realizations_overdue?: number;
		shipments_total?: number;
		mtt_total?: number;
		mtt_completion_overdue?: number;
		mtt_outlay_overdue?: number;
		mtt_fx_negative?: number;
	};
	aging?: { overdue: number; d0_30: number; d30_60: number; d60p: number };
	pipeline?: { stage: string; count: number }[];
	shipments: DashShipmentRow[];
	deadlines: DeadlineRow[];
	documents: DashDocRow[];
	pfis: DashPfiRow[];
	/** per-block read permissions — hide card groups the role cannot see */
	can: {
		shipment: boolean;
		doc: boolean;
		lc: boolean;
		po: boolean;
		pfi: boolean;
		compliance: boolean;
	};
}

export interface NewPOContext {
	company: string;
	company_currency: string;
	suppliers: {
		name: string;
		supplier_name: string;
		default_merchant_export_scheme: 0 | 1;
		default_currency: string | null;
		country: string | null;
	}[];
	items: { name: string; item_name: string; stock_uom: string }[];
	terms_templates: string[];
	taxes_templates: { name: string; is_default: 0 | 1 }[];
	accounts: { name: string; account_name: string }[];
	sales_orders: { name: string; customer_name: string }[];
	uoms: string[];
	countries: string[];
	item_tax_templates: string[];
	currencies: string[];
}

export interface POTaxRow {
	description: string;
	rate: number;
	tax_amount: number;
	total: number;
}

/** Per-item net + tax, aggregated by item code (the dynamic per-item breakup). */
export interface POItemTax {
	item_code: string;
	item_name: string | null;
	net: number;
	tax: number;
}

export interface POTotals {
	net_total: number;
	total_taxes_and_charges: number;
	grand_total: number;
	taxes: POTaxRow[];
	by_item: POItemTax[];
}

/** A file attached to a Sales/Purchase Order (multi-file attachments card). */
export interface DocAttachment {
	name: string;
	file_name: string;
	file_url: string;
	is_private: 0 | 1;
	file_size: number;
	creation: string;
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
	has_grn: boolean;
}

export interface GRNRef {
	name: string;
	warehouse: string;
	status: 'Draft' | 'Received' | 'Cancelled';
	posting_date: string;
	supplier_invoice_no: string | null;
}

export interface PODetailData {
	po: Omit<POListRow, 'sales_orders'> & {
		schedule_date: string | null;
		conversion_rate: number | null;
		merchanting_trade: 0 | 1 | null;
		taxes_and_charges: string | null;
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
		specification: string | null;
		packaging: string | null;
	}[];
	extra_charges: { description: string; account_head: string; amount: number }[];
	shipments: { shipment: string; current_milestone: string; mode: string; etd: string | null }[];
	grns: GRNRef[];
	received: boolean;
	can: DocCan;
}

export interface GRNListRow {
	name: string;
	purchase_order: string;
	supplier_name: string | null;
	warehouse: string;
	status: 'Draft' | 'Received' | 'Cancelled';
	posting_date: string;
	supplier_invoice_no: string | null;
}

export interface ReceivablePO {
	name: string;
	supplier: string;
	supplier_name: string | null;
	transaction_date: string;
	grand_total: number;
	currency: string;
	remaining_lines: number;
}

export interface GRNContextLine {
	po_detail: string;
	item_code: string;
	item_name: string;
	ordered_qty: number;
	already_received: number;
	received_qty: number;
	uom: string | null;
	stock_uom: string | null;
	conversion_factor: number;
}

export interface GRNContext {
	purchase_order: string;
	supplier: string;
	supplier_name: string | null;
	company: string | null;
	warehouses: { name: string; warehouse_name: string; warehouse_type: string | null }[];
	lines: GRNContextLine[];
	fully_received: boolean;
}

export interface GRNDetailData {
	grn: {
		name: string;
		purchase_order: string;
		supplier: string | null;
		supplier_name: string | null;
		company: string | null;
		posting_date: string;
		warehouse: string;
		status: 'Draft' | 'Received' | 'Cancelled';
		supplier_invoice_no: string | null;
		supplier_invoice_date: string | null;
		supplier_invoice_file: string | null;
		remarks: string | null;
	};
	items: {
		name: string;
		item_code: string;
		item_name: string | null;
		po_detail: string | null;
		ordered_qty: number;
		received_qty: number;
		uom: string | null;
	}[];
	packs: ShipmentPack[];
	documents: { name: string; document_type: string; file: string; description: string | null }[];
	returns: { name: string; status: 'Draft' | 'Returned' | 'Cancelled'; posting_date: string }[];
	can: { edit: boolean; receive: boolean; cancel: boolean; return_material: boolean };
}

export interface ReturnContextLine {
	item_code: string;
	item_name: string;
	po_detail: string | null;
	grn_detail: string;
	received_qty: number;
	already_returned: number;
	returnable: number;
	returned_qty: number;
	uom: string | null;
}

export interface ReturnContext {
	goods_receipt_note: string;
	purchase_order: string;
	supplier_name: string | null;
	warehouse: string;
	lines: ReturnContextLine[];
}

export interface ReturnDetailData {
	mr: {
		name: string;
		goods_receipt_note: string;
		purchase_order: string;
		supplier: string | null;
		supplier_name: string | null;
		company: string | null;
		posting_date: string;
		warehouse: string;
		status: 'Draft' | 'Returned' | 'Cancelled';
		reason: string | null;
	};
	items: {
		name: string;
		item_code: string;
		item_name: string | null;
		received_qty: number;
		returned_qty: number;
		uom: string | null;
	}[];
	can: { edit: boolean; confirm: boolean; cancel: boolean };
}

export interface MaterialReturnListRow {
	name: string;
	goods_receipt_note: string;
	purchase_order: string;
	supplier_name: string | null;
	status: 'Draft' | 'Returned' | 'Cancelled';
	posting_date: string;
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
	merchanting: boolean;
	india: boolean;
}

export interface ShipmentListRow {
	name: string;
	customer: string;
	customer_name: string;
	mode: 'Sea' | 'Air';
	trade_type?: string;
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

/** import outlay + supplier derivable from a merchanting shipment's linked POs */
export interface MttOutlay {
	/** Σ(shipped qty × PO line rate), in INR */
	computed: number;
	costed_lines: number;
	/** shipment lines with no PO yet — not included in the outlay */
	uncosted_lines: number;
	suppliers: string[];
	/** the single supplier auto-fill applies; null when ambiguous or none */
	supplier: string | null;
	/** display name of `supplier` (resolves disabled vendors); null when no single */
	supplier_name: string | null;
}

export interface ShipmentDetailData {
	/** actual date the export milestone (Shipped on Board / Departed) completed */
	export_completed_on: string | null;
	/** present for merchanting shipments — drives the auto outlay/supplier fill */
	mtt_outlay: MttOutlay | null;
	shipment: {
		name: string;
		customer: string;
		customer_name: string;
		mode: 'Sea' | 'Air';
		trade_type: TradeType;
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
		gst_export_mode: string | null;
		igst_rate: number | null;
		inr_rate: number | null;
		freight_amount: number | null;
		insurance_amount: number | null;
		buyer_order_no: string | null;
		buyer_order_date: string | null;
		consignee_to_order: 0 | 1;
		consignee_name: string | null;
		consignee_address: string | null;
		notify_party: string | null;
		claim_rodtep: 0 | 1;
		rodtep_rate_pct: number | null;
		claim_drawback: 0 | 1;
		drawback_rate_pct: number | null;
		mtt_ad_bank: string | null;
		mtt_same_ad_bank: 0 | 1;
		mtt_import_supplier: string | null;
		mtt_import_value_auto: 0 | 1;
		mtt_import_value_inr: number | null;
		mtt_commencement_date: string | null;
		mtt_import_payment_date: string | null;
		mtt_completion_date: string | null;
		mtt_idpms_status: string | null;
		mtt_edpms_status: string | null;
	};
	milestones: ShipmentMilestoneRow[];
	items: ShipmentItemRow[];
	packs: ShipmentPack[];
	lc: {
		name: string;
		lc_number: string;
		status: LCStatus;
		expiry_date: string;
		latest_shipment_date: string;
		issuing_bank: string | null;
	} | null;
	sales_orders: string[];
	can: DocCan;
}

/** Per-batch packing detail row (Export Shipment Pack child). net/tare/gross
 *  totals = num_packages × per-package weight, computed at print time. */
export interface ShipmentPack {
	name?: string;
	item_code: string;
	batch_no: string | null;
	marks: string | null;
	num_packages: number | null;
	pack_type: string | null;
	net_per: number | null;
	tare_per: number | null;
	mfg_date: string | null;
	exp_date: string | null;
}

export const GST_EXPORT_MODES = ['Under LUT (without IGST)', 'On payment of IGST'] as const;

// ---- Phase 4: documents (exportflow.api) ----

export type DocStatus =
	| 'Pending'
	| 'Drafted'
	| 'Sent/Filed'
	| 'Received'
	| 'Verified'
	| 'Not Applicable';

export const DOC_STATUSES: DocStatus[] = [
	'Pending',
	'Drafted',
	'Sent/Filed',
	'Received',
	'Verified',
	'Not Applicable',
];

export type DocCategory =
	| 'Commercial'
	| 'Regulatory'
	| 'Quality'
	| 'Logistics'
	| 'Banking'
	| 'Company';

export interface DocInstanceRow {
	name: string;
	document_type: string;
	category: DocCategory | null;
	origin: 'Generated' | 'Tracked' | null;
	status: DocStatus;
	responsible_party: string | null;
	shipment: string | null;
	customer: string | null;
	sales_order: string | null;
	purchase_order: string | null;
	document_number: string | null;
	document_date: string | null;
	due_date: string | null;
	originals: number | null;
	copies: number | null;
	description: string | null;
	remarks: string | null;
	file: string | null;
	blocking: 0 | 1;
	blocked_milestone: string | null;
	min_unblock_status: string | null;
	source: 'Manual' | 'Rule' | 'LC';
	modified: string;
}

export interface DocTypeOption {
	name: string;
	category: DocCategory;
	origin: 'Generated' | 'Tracked';
	responsible_party: string | null;
	default_print_format: string | null;
	format_doc_type: string | null;
}

/** ExportFlow can produce the PDF from the checklist only when the type is
 *  Generated AND its print format targets Document Instance — the Pro Forma
 *  Invoice format targets its own doctype and is produced from the PFI screen. */
export function isGeneratableDoc(t: DocTypeOption | undefined): boolean {
	return (
		!!t &&
		t.origin === 'Generated' &&
		!!t.default_print_format &&
		t.format_doc_type === 'Document Instance'
	);
}

export interface ShipmentDocumentsData {
	documents: DocInstanceRow[];
	document_types: DocTypeOption[];
}

export interface ChecklistRuleRow {
	name: string;
	rule_name: string;
	document_type: string;
	enabled: 0 | 1;
	notes: string | null;
	conditions: { condition_field: string; condition_value: string }[];
}

const DOC_STATUS_INDEX: Record<string, number> = {
	Pending: 0,
	Drafted: 1,
	'Sent/Filed': 2,
	Received: 3,
	Verified: 4,
};

/** A document counts as done once it left our desk (sent/filed or beyond). */
export function docIsDone(d: Pick<DocInstanceRow, 'status'>): boolean {
	return d.status === 'Not Applicable' || DOC_STATUS_INDEX[d.status] >= 2;
}

/** An unresolved blocker (mirrors the server's milestone gate). */
export function docIsBlockingNow(d: DocInstanceRow): boolean {
	if (!d.blocking || d.status === 'Not Applicable') return false;
	return (
		(DOC_STATUS_INDEX[d.status] ?? -1) < (DOC_STATUS_INDEX[d.min_unblock_status ?? 'Received'] ?? 3)
	);
}

/** Checklist tick per the mockup: ok / pend / err / none. */
export function docCkTone(d: DocInstanceRow): 'ok' | 'pend' | 'err' | 'none' {
	if (docIsBlockingNow(d)) return 'err';
	if (d.status === 'Not Applicable') return 'none';
	if (docIsDone(d)) return 'ok';
	if (d.status === 'Drafted') return 'pend';
	return 'none';
}

/** Status chip tone for tables (workspace). */
export function docTagTone(d: DocInstanceRow): 'ok' | 'pend' | 'err' {
	if (docIsBlockingNow(d)) return 'err';
	if (docIsDone(d)) return 'ok';
	return 'pend';
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
