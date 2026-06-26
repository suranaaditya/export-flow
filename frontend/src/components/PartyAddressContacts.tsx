import { useState } from 'react';
import { useFrappeGetCall, useFrappePostCall } from 'frappe-react-sdk';

import { Field, TextInput } from '@/components/form';
import { Icon } from '@/components/Icon';
import { API, parseServerError } from '@/lib/api';

interface PartyAddress {
	name: string;
	address_line1?: string;
	address_line2?: string;
	city?: string;
	state?: string;
	pincode?: string;
	country?: string;
	is_primary?: number;
}
interface PartyContact {
	name: string;
	first_name?: string;
	last_name?: string;
	email_id?: string;
	mobile_no?: string;
	designation?: string;
	is_primary?: number;
}

const EMPTY_ADDR = { address_line1: '', address_line2: '', city: '', state: '', pincode: '', country: '', gstin: '' };
const EMPTY_CONT = { contact_person: '', designation: '', mobile: '', email: '' };

const addrLine = (a: PartyAddress) =>
	[a.address_line1, a.address_line2, a.city, a.state, a.pincode, a.country].filter(Boolean).join(', ');
const contLine = (c: PartyContact) =>
	[[c.first_name, c.last_name].filter(Boolean).join(' '), c.designation, c.mobile_no, c.email_id]
		.filter(Boolean)
		.join(' · ');

/** Manage a customer/supplier's multiple addresses + contacts (Phase 2). Rendered in
 *  the master edit modal; the records are native ERPNext Address / Contact, linked via
 *  Dynamic Link, with one marked primary (what the prints use by default). */
export function PartyAddressContacts({ partyType, party }: { partyType: 'Customer' | 'Supplier'; party: string }) {
	const { data, mutate, isLoading } = useFrappeGetCall<{
		message: { addresses: PartyAddress[]; contacts: PartyContact[] };
	}>(API.partyContacts, { party_type: partyType, party });
	const addAddr = useFrappePostCall(API.addPartyAddress);
	const addCont = useFrappePostCall(API.addPartyContact);
	const setPrimAddr = useFrappePostCall(API.setPartyPrimaryAddress);
	const setPrimCont = useFrappePostCall(API.setPartyPrimaryContact);
	const rmAddr = useFrappePostCall(API.removePartyAddress);
	const rmCont = useFrappePostCall(API.removePartyContact);

	const [err, setErr] = useState<string | null>(null);
	const [showAddr, setShowAddr] = useState(false);
	const [showCont, setShowCont] = useState(false);
	const [busy, setBusy] = useState(false);
	const [a, setA] = useState({ ...EMPTY_ADDR });
	const [c, setC] = useState({ ...EMPTY_CONT });

	const addresses = data?.message.addresses ?? [];
	const contacts = data?.message.contacts ?? [];

	const run = async (fn: () => Promise<unknown>) => {
		setErr(null);
		setBusy(true);
		try {
			await fn();
			await mutate();
		} catch (e) {
			setErr(parseServerError(e));
		} finally {
			setBusy(false);
		}
	};

	return (
		<div className="pac">
			<div className="pac-divider">Addresses &amp; contacts</div>

			<div className="pac-block">
				<div className="pac-head">
					<span>Addresses</span>
					<a href="#" onClick={(e) => { e.preventDefault(); setShowAddr((s) => !s); }}>
						{showAddr ? 'Cancel' : '+ Add address'}
					</a>
				</div>
				{isLoading ? (
					<div className="c2">Loading…</div>
				) : addresses.length === 0 && !showAddr ? (
					<div className="c2">No addresses yet.</div>
				) : (
					addresses.map((ad) => (
						<div className="pac-row" key={ad.name}>
							<span className="pac-text">{addrLine(ad) || ad.name}</span>
							<span className="pac-actions">
								{ad.is_primary ? (
									<span className="pac-badge">Primary</span>
								) : (
									<>
										<a href="#" onClick={(e) => { e.preventDefault(); void run(() => setPrimAddr.call({ party_type: partyType, party, address: ad.name })); }}>
											Set primary
										</a>
										<a href="#" className="pac-del" onClick={(e) => { e.preventDefault(); void run(() => rmAddr.call({ party_type: partyType, party, address: ad.name })); }}>
											Remove
										</a>
									</>
								)}
							</span>
						</div>
					))
				)}
				{showAddr && (
					<div className="pac-form formgrid">
						<div className="span2">
							<Field label="Address line 1"><TextInput value={a.address_line1} onChange={(v) => setA({ ...a, address_line1: v })} /></Field>
						</div>
						<div className="span2">
							<Field label="Address line 2"><TextInput value={a.address_line2} onChange={(v) => setA({ ...a, address_line2: v })} /></Field>
						</div>
						<Field label="City"><TextInput value={a.city} onChange={(v) => setA({ ...a, city: v })} /></Field>
						<Field label="State"><TextInput value={a.state} onChange={(v) => setA({ ...a, state: v })} /></Field>
						<Field label="Pincode"><TextInput mono value={a.pincode} onChange={(v) => setA({ ...a, pincode: v })} /></Field>
						<Field label="Country"><TextInput value={a.country} onChange={(v) => setA({ ...a, country: v })} /></Field>
						{partyType === 'Supplier' && (
							<Field label="GSTIN" hint="Optional — derives state"><TextInput mono value={a.gstin} onChange={(v) => setA({ ...a, gstin: v })} /></Field>
						)}
						<div className="span2 pac-formfoot">
							<button type="button" className="btn primary" disabled={busy} onClick={() => void run(async () => {
								await addAddr.call({ party_type: partyType, party, values: a, make_primary: addresses.length === 0 ? 1 : 0 });
								setA({ ...EMPTY_ADDR });
								setShowAddr(false);
							})}>
								{busy ? 'Saving…' : 'Add address'}
							</button>
						</div>
					</div>
				)}
			</div>

			<div className="pac-block">
				<div className="pac-head">
					<span>Contacts</span>
					<a href="#" onClick={(e) => { e.preventDefault(); setShowCont((s) => !s); }}>
						{showCont ? 'Cancel' : '+ Add contact'}
					</a>
				</div>
				{!isLoading && contacts.length === 0 && !showCont ? (
					<div className="c2">No contacts yet.</div>
				) : (
					contacts.map((ct) => (
						<div className="pac-row" key={ct.name}>
							<span className="pac-text">{contLine(ct) || ct.name}</span>
							<span className="pac-actions">
								{ct.is_primary ? (
									<span className="pac-badge">Primary</span>
								) : (
									<>
										<a href="#" onClick={(e) => { e.preventDefault(); void run(() => setPrimCont.call({ party_type: partyType, party, contact: ct.name })); }}>
											Set primary
										</a>
										<a href="#" className="pac-del" onClick={(e) => { e.preventDefault(); void run(() => rmCont.call({ party_type: partyType, party, contact: ct.name })); }}>
											Remove
										</a>
									</>
								)}
							</span>
						</div>
					))
				)}
				{showCont && (
					<div className="pac-form formgrid">
						<Field label="Contact person"><TextInput value={c.contact_person} onChange={(v) => setC({ ...c, contact_person: v })} /></Field>
						<Field label="Designation"><TextInput value={c.designation} onChange={(v) => setC({ ...c, designation: v })} /></Field>
						<Field label="Phone / mobile"><TextInput mono value={c.mobile} onChange={(v) => setC({ ...c, mobile: v })} /></Field>
						<Field label="Email"><TextInput value={c.email} onChange={(v) => setC({ ...c, email: v })} /></Field>
						<div className="span2 pac-formfoot">
							<button type="button" className="btn primary" disabled={busy} onClick={() => void run(async () => {
								await addCont.call({ party_type: partyType, party, values: c, make_primary: contacts.length === 0 ? 1 : 0 });
								setC({ ...EMPTY_CONT });
								setShowCont(false);
							})}>
								{busy ? 'Saving…' : 'Add contact'}
							</button>
						</div>
					</div>
				)}
			</div>

			{err && <div className="ferr" style={{ marginTop: 8 }}><Icon name="alert" size={13} /> {err}</div>}
		</div>
	);
}
