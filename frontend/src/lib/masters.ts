import type { IconName } from '@/components/Icon';
import { API } from '@/lib/api';

/** Option sources resolved at render time from the masters context. */
export type OptionSource =
	| 'currencies'
	| 'incoterms'
	| 'uoms'
	| 'countries'
	| 'grades'
	| 'portModes'
	| 'docCategories'
	| 'docOrigins'
	| 'docParties'
	| 'docAttaches'
	| 'docUnblock'
	| 'itemTaxTemplates';

export interface MasterField {
	key: string;
	label: string;
	required?: boolean;
	type: 'text' | 'select' | 'check' | 'textarea';
	options?: OptionSource;
	hint?: string;
	mono?: boolean;
	/** locked after creation (e.g. naming fields) */
	createOnly?: boolean;
	/** derive the edit value from the full doc when it isn't a plain scalar
	 *  field (e.g. an Item Tax Template stored in the Item.taxes child table) */
	seedFrom?: (doc: Record<string, unknown>) => string;
}

export interface MasterDef {
	doctype: string;
	title: string;
	singular: string;
	icon: IconName;
	/** whitelisted create endpoint; plain createDoc when absent */
	createMethod?: string;
	/** whitelisted update endpoint; plain updateDoc when absent (use when a
	 *  field maps to a child table, e.g. the Item Tax Template) */
	updateMethod?: string;
	listFields: string[];
	columns: { key: string; label: string; dim?: boolean }[];
	fields: MasterField[];
}

export const GRADE_OPTIONS = ['IP', 'BP', 'USP', 'EP', 'JP', 'Ph. Int.', 'Other'];
export const PORT_MODES = ['Sea', 'Air', 'Sea & Air'];
export const DOC_CATEGORIES = ['Commercial', 'Regulatory', 'Quality', 'Logistics', 'Banking', 'Company'];
export const DOC_ORIGINS = ['Generated', 'Tracked'];
export const DOC_PARTIES = ['Us', 'CHA', 'Supplier', 'Shipping Line/Airline', 'Bank', 'Authority', 'Customer'];
export const DOC_ATTACHES = ['Company', 'Sales Order', 'Purchase Order', 'Shipment', 'Batch'];
export const DOC_UNBLOCK = ['Drafted', 'Sent/Filed', 'Received', 'Verified'];

/** Option sources that never come from the server — spread into the
 *  per-screen Record<OptionSource, string[]> maps. */
export const STATIC_OPTIONS: Pick<
	Record<OptionSource, string[]>,
	'grades' | 'portModes' | 'docCategories' | 'docOrigins' | 'docParties' | 'docAttaches' | 'docUnblock'
> = {
	grades: GRADE_OPTIONS,
	portModes: PORT_MODES,
	docCategories: DOC_CATEGORIES,
	docOrigins: DOC_ORIGINS,
	docParties: DOC_PARTIES,
	docAttaches: DOC_ATTACHES,
	docUnblock: DOC_UNBLOCK,
};

export const MASTERS: MasterDef[] = [
	{
		doctype: 'Customer',
		title: 'Customers',
		singular: 'customer',
		icon: 'building',
		createMethod: API.createCustomer,
		listFields: ['name', 'customer_name', 'destination_country', 'default_currency', 'default_incoterm'],
		columns: [
			{ key: 'customer_name', label: 'Customer' },
			{ key: 'destination_country', label: 'Destination', dim: true },
			{ key: 'default_currency', label: 'Currency', dim: true },
			{ key: 'default_incoterm', label: 'Incoterm', dim: true },
		],
		fields: [
			{ key: 'customer_name', label: 'Customer name', type: 'text', required: true, createOnly: true },
			{ key: 'destination_country', label: 'Destination country', type: 'select', options: 'countries' },
			{ key: 'default_currency', label: 'Default currency', type: 'select', options: 'currencies' },
			{ key: 'default_incoterm', label: 'Default incoterm', type: 'select', options: 'incoterms' },
		],
	},
	{
		doctype: 'Supplier',
		title: 'Suppliers',
		singular: 'supplier',
		icon: 'truck',
		createMethod: API.createSupplier,
		listFields: ['name', 'supplier_name', 'country', 'default_merchant_export_scheme'],
		columns: [
			{ key: 'supplier_name', label: 'Supplier' },
			{ key: 'country', label: 'Country', dim: true },
			{ key: 'default_merchant_export_scheme', label: '0.1% scheme', dim: true },
		],
		fields: [
			{ key: 'supplier_name', label: 'Supplier name', type: 'text', required: true, createOnly: true },
			{ key: 'country', label: 'Country', type: 'select', options: 'countries' },
			{
				key: 'default_merchant_export_scheme',
				label: 'Usually supplies under the 0.1% GST scheme',
				type: 'check',
			},
		],
	},
	{
		doctype: 'CHA',
		title: 'CHAs & forwarders',
		singular: 'CHA',
		icon: 'shield',
		listFields: ['name', 'cha_name', 'contact_person', 'mobile_no', 'default_port', 'gstin'],
		columns: [
			{ key: 'cha_name', label: 'CHA / agent' },
			{ key: 'contact_person', label: 'Contact', dim: true },
			{ key: 'mobile_no', label: 'Mobile', dim: true },
			{ key: 'default_port', label: 'Default port', dim: true },
		],
		fields: [
			{ key: 'cha_name', label: 'CHA / agent name', type: 'text', required: true, createOnly: true },
			{ key: 'contact_person', label: 'Contact person', type: 'text' },
			{ key: 'mobile_no', label: 'Mobile', type: 'text', mono: true },
			{ key: 'email_id', label: 'Email', type: 'text' },
			{ key: 'default_port', label: 'Default port', type: 'text' },
			{ key: 'gstin', label: 'GSTIN', type: 'text', mono: true },
			{ key: 'address', label: 'Address', type: 'textarea' },
			{ key: 'notes', label: 'Notes', type: 'textarea' },
		],
	},
	{
		doctype: 'Item',
		title: 'Items',
		singular: 'item',
		icon: 'cube',
		createMethod: API.createItem,
		updateMethod: API.updateItem,
		listFields: ['name', 'item_name', 'stock_uom', 'pharmacopoeia_grade', 'customs_tariff_number'],
		columns: [
			{ key: 'item_name', label: 'Item' },
			{ key: 'pharmacopoeia_grade', label: 'Grade', dim: true },
			{ key: 'stock_uom', label: 'UOM', dim: true },
			{ key: 'customs_tariff_number', label: 'HS code', dim: true },
		],
		fields: [
			{ key: 'item_name', label: 'Item name', type: 'text', required: true, createOnly: true },
			{ key: 'stock_uom', label: 'Unit of measure', type: 'select', options: 'uoms' },
			{ key: 'pharmacopoeia_grade', label: 'Pharmacopoeia grade', type: 'select', options: 'grades' },
			{ key: 'customs_tariff_number', label: 'HS code', type: 'text', mono: true },
			{ key: 'gst_hsn_code', label: 'GST HSN code', type: 'text', mono: true, hint: 'Drives GST autofill on purchase orders' },
			{
				key: 'item_tax_template',
				label: 'Item tax template',
				type: 'select',
				options: 'itemTaxTemplates',
				hint: 'Sets the per-item GST rate; leave blank to use HSN / template defaults',
				seedFrom: (doc) => {
					const taxes = doc.taxes as { item_tax_template?: string }[] | undefined;
					return taxes?.[0]?.item_tax_template ?? '';
				},
			},
			{ key: 'cas_number', label: 'CAS number', type: 'text', mono: true },
			{ key: 'default_pack_size', label: 'Default pack size', type: 'text', hint: 'e.g. 25 kg HDPE drum' },
		],
	},
	{
		doctype: 'UOM',
		title: 'Units of measure',
		singular: 'unit',
		icon: 'layers',
		listFields: ['name', 'uom_name'],
		columns: [{ key: 'uom_name', label: 'Unit' }],
		fields: [{ key: 'uom_name', label: 'Unit name', type: 'text', required: true, createOnly: true }],
	},
	{
		doctype: 'Terms and Conditions',
		title: 'Terms & conditions',
		singular: 'terms template',
		icon: 'file-text',
		listFields: ['name', 'buying', 'selling', 'disabled'],
		columns: [
			{ key: 'name', label: 'Template' },
			{ key: 'buying', label: 'Buying', dim: true },
			{ key: 'selling', label: 'Selling', dim: true },
		],
		fields: [
			{ key: 'title', label: 'Template name', type: 'text', required: true, createOnly: true },
			{ key: 'terms', label: 'Terms text', type: 'textarea' },
			{ key: 'buying', label: 'Use for purchasing', type: 'check' },
			{ key: 'selling', label: 'Use for selling', type: 'check' },
		],
	},
	{
		doctype: 'Export Payment Term',
		title: 'Payment terms',
		singular: 'payment terms template',
		icon: 'banknote',
		listFields: ['name', 'buying', 'selling', 'disabled'],
		columns: [
			{ key: 'name', label: 'Template' },
			{ key: 'buying', label: 'Buying', dim: true },
			{ key: 'selling', label: 'Selling', dim: true },
		],
		fields: [
			{ key: 'template_name', label: 'Template name', type: 'text', required: true, createOnly: true },
			{ key: 'terms', label: 'Payment terms text', type: 'textarea' },
			{ key: 'buying', label: 'Use for purchasing', type: 'check' },
			{ key: 'selling', label: 'Use for selling', type: 'check' },
		],
	},
	{
		doctype: 'Port',
		title: 'Ports',
		singular: 'port',
		icon: 'ship',
		listFields: ['name', 'unlocode', 'mode', 'city', 'country'],
		columns: [
			{ key: 'name', label: 'Port' },
			{ key: 'unlocode', label: 'UN/LOCODE', dim: true },
			{ key: 'mode', label: 'Mode', dim: true },
			{ key: 'city', label: 'City', dim: true },
			{ key: 'country', label: 'Country', dim: true },
		],
		fields: [
			{ key: 'port_name', label: 'Port name', type: 'text', required: true, createOnly: true },
			{ key: 'unlocode', label: 'UN/LOCODE', type: 'text', mono: true, hint: 'e.g. INNSA' },
			{ key: 'mode', label: 'Mode', type: 'select', options: 'portModes' },
			{ key: 'city', label: 'City', type: 'text' },
			{ key: 'country', label: 'Country', type: 'select', options: 'countries' },
			{
				key: 'ad_code',
				label: 'AD code',
				type: 'text',
				mono: true,
				hint: 'Authorised Dealer code registered at this port — printed on export invoices',
			},
		],
	},
	{
		doctype: 'Document Type',
		title: 'Document types',
		singular: 'document type',
		icon: 'file-text-alt',
		listFields: ['name', 'category', 'origin', 'responsible_party', 'is_blocking'],
		columns: [
			{ key: 'name', label: 'Document' },
			{ key: 'category', label: 'Category', dim: true },
			{ key: 'origin', label: 'Origin', dim: true },
			{ key: 'responsible_party', label: 'Responsible', dim: true },
			{ key: 'is_blocking', label: 'Blocking', dim: true },
		],
		fields: [
			{ key: 'document_type_name', label: 'Name', type: 'text', required: true, createOnly: true },
			{ key: 'category', label: 'Category', type: 'select', options: 'docCategories', required: true },
			{ key: 'origin', label: 'Origin', type: 'select', options: 'docOrigins', required: true },
			{ key: 'responsible_party', label: 'Responsible party', type: 'select', options: 'docParties' },
			{ key: 'attaches_to', label: 'Attaches to', type: 'select', options: 'docAttaches' },
			{ key: 'has_expiry', label: 'Has expiry', type: 'check' },
			{
				key: 'is_blocking',
				label: 'An unresolved instance blocks a shipment milestone',
				type: 'check',
			},
			{
				key: 'blocked_milestone',
				label: 'Blocked milestone',
				type: 'text',
				hint: 'e.g. Let Export Order',
			},
			{
				key: 'min_unblock_status',
				label: 'Unblocks at status',
				type: 'select',
				options: 'docUnblock',
			},
			{ key: 'notes', label: 'Notes', type: 'textarea' },
		],
	},
];
