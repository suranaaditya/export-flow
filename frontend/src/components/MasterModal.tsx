import { useEffect, useState } from 'react';
import {
	useFrappeCreateDoc,
	useFrappeGetDoc,
	useFrappePostCall,
	useFrappeUpdateDoc,
} from 'frappe-react-sdk';
import { CheckInput, Field, SearchSelect, TextArea, TextInput } from '@/components/form';
import { Modal } from '@/components/ui';
import { parseServerError } from '@/lib/api';
import type { MasterDef, OptionSource } from '@/lib/masters';

type Values = Record<string, string | boolean>;

function seed(
	def: MasterDef,
	record: Record<string, unknown> | null,
	defaults?: Values,
): Values {
	const v: Values = {};
	for (const f of def.fields) {
		// a field can derive its value from the full doc when it isn't a plain
		// scalar (e.g. the Item Tax Template lives in the Item.taxes child table)
		if (f.seedFrom) {
			v[f.key] = record ? f.seedFrom(record) : '';
			continue;
		}
		const raw = record?.[f.key];
		if (raw == null && !record && defaults && f.key in defaults) {
			// create-mode seed value (e.g. default a Terms template to selling/buying
			// for the form that opened the quick-create)
			v[f.key] = f.type === 'check' ? !!defaults[f.key] : String(defaults[f.key] ?? '');
			continue;
		}
		v[f.key] = f.type === 'check' ? !!raw : raw != null ? String(raw) : '';
	}
	return v;
}

/** Create/edit dialog for a master, config-driven — shared by the Settings
 *  panels and the deal form's quick-create buttons. */
export function MasterModal({
	def,
	options,
	record,
	defaults,
	onClose,
	onSaved,
}: {
	def: MasterDef;
	options: Record<OptionSource, string[]>;
	record: Record<string, unknown> | null;
	/** create-mode seed values (e.g. default a new Terms template to selling/buying) */
	defaults?: Values;
	onClose: () => void;
	onSaved: (name: string) => void;
}) {
	const isNew = record === null;
	const recordName = record ? String(record.name) : null;
	// the list row only carries listFields — saving from it would blank every
	// other editable field, so editing always seeds from the full document
	const fullDoc = useFrappeGetDoc<Record<string, unknown>>(
		def.doctype,
		recordName ?? '',
		recordName ? undefined : null,
	);
	const [values, setValues] = useState<Values>(() => seed(def, record, defaults));
	const [err, setErr] = useState<string | null>(null);
	useEffect(() => {
		if (fullDoc.data) setValues(seed(def, fullDoc.data));
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [fullDoc.data]);
	const notReady = !isNew && !fullDoc.data;

	const { call: createViaMethod, loading: creating } = useFrappePostCall<{
		message: { name: string };
	}>(def.createMethod ?? 'frappe.ping');
	const { call: updateViaMethod, loading: updatingMethod } = useFrappePostCall<{
		message: { name: string };
	}>(def.updateMethod ?? 'frappe.ping');
	const { createDoc, loading: creatingDoc } = useFrappeCreateDoc();
	const { updateDoc, loading: updating } = useFrappeUpdateDoc();
	const saving = creating || creatingDoc || updating || updatingMethod;

	const set = (key: string, value: string | boolean) => setValues((v) => ({ ...v, [key]: value }));

	async function onSave() {
		for (const f of def.fields) {
			if (f.required && isNew && !String(values[f.key] ?? '').trim()) {
				return setErr(`${f.label} is required.`);
			}
		}
		setErr(null);
		const payload: Record<string, unknown> = {};
		for (const f of def.fields) {
			if (!isNew && f.createOnly) continue;
			payload[f.key] = f.type === 'check' ? (values[f.key] ? 1 : 0) : String(values[f.key] ?? '').trim();
		}
		try {
			if (isNew) {
				const name = def.createMethod
					? (await createViaMethod({ values: payload })).message.name
					: (await createDoc(def.doctype, payload)).name;
				onSaved(name);
			} else {
				const name = String(record.name);
				if (def.updateMethod) {
					await updateViaMethod({ name, values: payload });
				} else {
					await updateDoc(def.doctype, name, payload);
				}
				onSaved(name);
			}
		} catch (e) {
			setErr(parseServerError(e));
		}
	}

	return (
		<Modal title={isNew ? `New ${def.singular}` : String(record?.name ?? def.singular)} icon={def.icon} onClose={onClose}>
			<div className="formgrid">
				{def.fields.map((f) => {
					const disabled = !isNew && !!f.createOnly;
					if (f.type === 'check') {
						return (
							<div className="span2" key={f.key}>
								<CheckInput checked={!!values[f.key]} disabled={disabled} onChange={(v) => set(f.key, v)} label={f.label} />
							</div>
						);
					}
					if (f.type === 'textarea') {
						return (
							<div className="span2" key={f.key}>
								<Field label={f.label} hint={f.hint} required={f.required}>
									<TextArea
										value={String(values[f.key] ?? '')}
										disabled={disabled}
										rows={5}
										onChange={(v) => set(f.key, v)}
									/>
								</Field>
							</div>
						);
					}
					if (f.type === 'select') {
						return (
							<Field key={f.key} label={f.label} hint={f.hint} required={f.required}>
								<SearchSelect
									value={String(values[f.key] ?? '')}
									disabled={disabled}
									onChange={(v) => set(f.key, v)}
									options={(f.options ? options[f.options] : []).map((o) => ({ value: o }))}
								/>
							</Field>
						);
					}
					return (
						<Field key={f.key} label={f.label} hint={f.hint} required={f.required}>
							<TextInput value={String(values[f.key] ?? '')} mono={f.mono} disabled={disabled} onChange={(v) => set(f.key, v)} />
						</Field>
					);
				})}
			</div>
			<div className="formfoot">
				{err && <span className="ferr">{err}</span>}
				<span className="spacer" />
				<button type="button" className="btn" onClick={onClose}>
					Cancel
				</button>
				<button
					type="button"
					className="btn primary"
					disabled={saving || notReady}
					onClick={() => void onSave()}
				>
					{saving ? 'Saving…' : notReady ? 'Loading…' : isNew ? `Create ${def.singular}` : 'Save changes'}
				</button>
			</div>
		</Modal>
	);
}
