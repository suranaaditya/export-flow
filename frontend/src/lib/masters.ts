import type { IconName } from '@/components/Icon';
import { API } from '@/lib/api';

/** Option sources resolved at render time from the masters context. */
export type OptionSource = 'currencies' | 'incoterms' | 'uoms' | 'countries' | 'grades' | 'portModes';

export interface MasterField {
	key: string;
	label: string;
	required?: boolean;
	type: 'text' | 'select' | 'check';
	options?: OptionSource;
	hint?: string;
	mono?: boolean;
	/** locked after creation (e.g. naming fields) */
	createOnly?: boolean;
}

export interface MasterDef {
	doctype: string;
	title: string;
	singular: string;
	icon: IconName;
	/** whitelisted create endpoint; plain createDoc when absent */
	createMethod?: string;
	listFields: string[];
	columns: { key: string; label: string; dim?: boolean }[];
	fields: MasterField[];
}

export const GRADE_OPTIONS = ['IP', 'BP', 'USP', 'EP', 'JP', 'Ph. Int.', 'Other'];
export const PORT_MODES = ['Sea', 'Air', 'Sea & Air'];

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
		doctype: 'Item',
		title: 'Items',
		singular: 'item',
		icon: 'cube',
		createMethod: API.createItem,
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
		],
	},
];
