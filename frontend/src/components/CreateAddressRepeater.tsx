import { Field, SearchSelect, TextInput } from '@/components/form';

export interface AddressRow {
	address_type: string;
	address_line1: string;
	address_line2: string;
	city: string;
	state: string;
	pincode: string;
	country: string;
	gstin: string;
}

export const emptyAddressRow = (): AddressRow => ({
	address_type: 'Billing',
	address_line1: '',
	address_line2: '',
	city: '',
	state: '',
	pincode: '',
	country: '',
	gstin: '',
});

/** A row carries real address content when it has a street line or a city. */
export const addressRowFilled = (r: AddressRow) => !!(r.address_line1.trim() || r.city.trim());

const TYPES = ['Billing', 'Shipping', 'Other'];

/** Capture one-or-more addresses while creating a customer / supplier. Row 1 is the
 *  party's primary (billing) address; tag any row "Shipping" to set the party's shipping
 *  address (used as the default on the Sales Order's Ship-to picker). Blank country falls
 *  back to the party's country server-side. */
export function CreateAddressRepeater({
	partyType,
	defaultCountry,
	value,
	onChange,
}: {
	partyType: 'Customer' | 'Supplier';
	defaultCountry?: string;
	value: AddressRow[];
	onChange: (rows: AddressRow[]) => void;
}) {
	const rows = value;
	const setRow = (i: number, patch: Partial<AddressRow>) =>
		onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
	const add = () => onChange([...rows, emptyAddressRow()]);
	const remove = (i: number) => onChange(rows.filter((_, j) => j !== i));

	return (
		<div className="pac-repeater" style={{ marginTop: 10 }}>
			<div className="lbl" style={{ marginBottom: 4 }}>Addresses</div>
			{rows.map((r, i) => (
				<div key={i} className="pac-form formgrid" style={{ marginBottom: 8 }}>
					<div className="span2 pac-rowhead">
						<span className="muted">{i === 0 ? 'Primary (billing)' : `Address ${i + 1}`}</span>
						{rows.length > 1 && (
							<a
								href="#"
								className="c2"
								onClick={(e) => {
									e.preventDefault();
									remove(i);
								}}
							>
								Remove
							</a>
						)}
					</div>
					<Field label="Type">
						<SearchSelect
							value={r.address_type}
							onChange={(v) => setRow(i, { address_type: v })}
							options={TYPES.map((t) => ({ value: t }))}
						/>
					</Field>
					<Field label="Country" hint={defaultCountry ? `Defaults to ${defaultCountry}` : undefined}>
						<TextInput value={r.country} onChange={(v) => setRow(i, { country: v })} placeholder={defaultCountry} />
					</Field>
					<div className="span2">
						<Field label="Address line 1">
							<TextInput value={r.address_line1} onChange={(v) => setRow(i, { address_line1: v })} />
						</Field>
					</div>
					<div className="span2">
						<Field label="Address line 2">
							<TextInput value={r.address_line2} onChange={(v) => setRow(i, { address_line2: v })} />
						</Field>
					</div>
					<Field label="City">
						<TextInput value={r.city} onChange={(v) => setRow(i, { city: v })} />
					</Field>
					<Field label="Pincode">
						<TextInput mono value={r.pincode} onChange={(v) => setRow(i, { pincode: v })} />
					</Field>
					<Field label="State" hint="Required for Indian addresses">
						<TextInput value={r.state} onChange={(v) => setRow(i, { state: v })} />
					</Field>
					{partyType === 'Supplier' && (
						<Field label="GSTIN" hint="Domestic supplier — enables 0.1% GST on its POs; derives state">
							<TextInput mono value={r.gstin} onChange={(v) => setRow(i, { gstin: v })} />
						</Field>
					)}
				</div>
			))}
			<a
				href="#"
				className="c2"
				onClick={(e) => {
					e.preventDefault();
					add();
				}}
			>
				+ Add another address
			</a>
		</div>
	);
}
