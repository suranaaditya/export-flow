import { useEffect, useState } from 'react';
import { useFrappeGetCall, useFrappePostCall } from 'frappe-react-sdk';

import { Field, SearchSelect, TextInput } from '@/components/form';
import { API, parseServerError } from '@/lib/api';

export interface PickerAddress {
	name: string;
	address_line1?: string;
	address_line2?: string;
	city?: string;
	state?: string;
	pincode?: string;
	country?: string;
	is_primary?: number;
	is_shipping_address?: number;
	address_type?: string;
}

export const addressLine = (a: PickerAddress) =>
	[a.address_line1, a.address_line2, a.city, a.state, a.pincode, a.country].filter(Boolean).join(', ');

/** Multi-line address block (for storing a snapshot in a free-text field, e.g. the
 *  shipment's consignee_address). */
export const addressBlock = (a: PickerAddress) =>
	[
		a.address_line1,
		a.address_line2,
		[a.city, a.state, a.pincode].filter(Boolean).join(' '),
		a.country,
	]
		.filter(Boolean)
		.join('\n');

const EMPTY = { address_line1: '', address_line2: '', city: '', state: '', pincode: '', country: '', gstin: '' };

/** Pick which of a party's addresses an order uses (defaults to the party's primary).
 *  The chosen address is stored on the SO/PO/shipment so the printed doc uses it, not
 *  just the default. Includes an inline "+ Add address" (Phase 3). */
export function PartyAddressPicker({
	partyType,
	party,
	value,
	onChange,
	label = 'Address',
	hint,
	prefer = 'billing',
}: {
	partyType: 'Customer' | 'Supplier';
	party: string;
	value: string;
	onChange: (name: string, addr: PickerAddress | null) => void;
	label?: string;
	hint?: string;
	/** which address to default to when the party changes — the primary billing address,
	 *  or the one flagged for shipping (falling back to primary). */
	prefer?: 'billing' | 'shipping';
}) {
	const { data, mutate } = useFrappeGetCall<{ message: { addresses: PickerAddress[] } }>(
		API.partyContacts,
		{ party_type: partyType, party },
		party ? undefined : null,
	);
	const addresses = data?.message.addresses ?? [];
	const addAddr = useFrappePostCall<{ message: { name: string } }>(API.addPartyAddress);

	const [show, setShow] = useState(false);
	const [err, setErr] = useState<string | null>(null);
	const [busy, setBusy] = useState(false);
	const [a, setA] = useState({ ...EMPTY });

	// default to the party's primary (or shipping) address when the party changes and
	// nothing valid is chosen
	useEffect(() => {
		if (!party || !addresses.length) return;
		if (value && addresses.some((x) => x.name === value)) return;
		const def =
			prefer === 'shipping'
				? addresses.find((x) => x.is_shipping_address) ??
					addresses.find((x) => x.is_primary) ??
					addresses[0]
				: addresses.find((x) => x.is_primary) ?? addresses[0];
		if (def) onChange(def.name, def);
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [party, addresses.length]);

	const opts = addresses.map((x) => ({
		value: x.name,
		label: addressLine(x) || x.name,
		sub: x.is_primary ? 'Primary' : x.is_shipping_address ? 'Shipping' : undefined,
	}));

	return (
		<Field label={label} hint={hint}>
			<SearchSelect
				value={value}
				onChange={(v) => onChange(v, addresses.find((x) => x.name === v) ?? null)}
				options={opts}
				placeholder={party ? 'Use the primary address…' : 'Pick the party first'}
				disabled={!party}
			/>
			{party && (
				<a
					href="#"
					className="c2"
					style={{ display: 'inline-block', marginTop: 4 }}
					onClick={(e) => {
						e.preventDefault();
						setShow((s) => !s);
					}}
				>
					{show ? 'Cancel' : '+ Add address'}
				</a>
			)}
			{show && (
				<div className="pac-form formgrid" style={{ marginTop: 6 }}>
					<div className="span2">
						<Field label="Address line 1"><TextInput value={a.address_line1} onChange={(v) => setA({ ...a, address_line1: v })} /></Field>
					</div>
					<Field label="City"><TextInput value={a.city} onChange={(v) => setA({ ...a, city: v })} /></Field>
					<Field label="Pincode"><TextInput mono value={a.pincode} onChange={(v) => setA({ ...a, pincode: v })} /></Field>
					<Field label="State" hint="Required for Indian addresses"><TextInput value={a.state} onChange={(v) => setA({ ...a, state: v })} /></Field>
					<Field label="Country"><TextInput value={a.country} onChange={(v) => setA({ ...a, country: v })} /></Field>
					{partyType === 'Supplier' && (
						<Field label="GSTIN" hint="Optional — derives state"><TextInput mono value={a.gstin} onChange={(v) => setA({ ...a, gstin: v })} /></Field>
					)}
					<div className="span2 pac-formfoot">
						<button
							type="button"
							className="btn primary"
							disabled={busy}
							onClick={async () => {
								setErr(null);
								setBusy(true);
								try {
									// an address added from a shipping picker is tagged for shipping
									const vals =
										prefer === 'shipping'
											? { ...a, address_type: 'Shipping', is_shipping_address: 1 }
											: a;
									const r = await addAddr.call({ party_type: partyType, party, values: vals });
									await mutate();
									onChange(r.message.name, { name: r.message.name, ...a });
									setA({ ...EMPTY });
									setShow(false);
								} catch (e) {
									setErr(parseServerError(e));
								} finally {
									setBusy(false);
								}
							}}
						>
							{busy ? 'Saving…' : 'Add address'}
						</button>
					</div>
					{err && <div className="ferr span2">{err}</div>}
				</div>
			)}
		</Field>
	);
}
