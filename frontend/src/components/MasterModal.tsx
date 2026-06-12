import { useState } from 'react';
import { useFrappeCreateDoc, useFrappePostCall, useFrappeUpdateDoc } from 'frappe-react-sdk';
import { CheckInput, Field, SelectInput, TextInput } from '@/components/form';
import { Modal } from '@/components/ui';
import { parseServerError } from '@/lib/api';
import type { MasterDef, OptionSource } from '@/lib/masters';

type Values = Record<string, string | boolean>;

function seed(def: MasterDef, record: Record<string, unknown> | null): Values {
	const v: Values = {};
	for (const f of def.fields) {
		const raw = record?.[f.key];
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
	onClose,
	onSaved,
}: {
	def: MasterDef;
	options: Record<OptionSource, string[]>;
	record: Record<string, unknown> | null;
	onClose: () => void;
	onSaved: (name: string) => void;
}) {
	const isNew = record === null;
	const [values, setValues] = useState<Values>(() => seed(def, record));
	const [err, setErr] = useState<string | null>(null);

	const { call: createViaMethod, loading: creating } = useFrappePostCall<{
		message: { name: string };
	}>(def.createMethod ?? 'frappe.ping');
	const { createDoc, loading: creatingDoc } = useFrappeCreateDoc();
	const { updateDoc, loading: updating } = useFrappeUpdateDoc();
	const saving = creating || creatingDoc || updating;

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
				await updateDoc(def.doctype, name, payload);
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
					if (f.type === 'select') {
						return (
							<Field key={f.key} label={f.label} hint={f.hint} required={f.required}>
								<SelectInput
									value={String(values[f.key] ?? '')}
									disabled={disabled}
									onChange={(v) => set(f.key, v)}
									options={(f.options ? options[f.options] : []).map((o) => ({ value: o }))}
									allowEmpty={!f.required}
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
				<button type="button" className="btn primary" disabled={saving} onClick={() => void onSave()}>
					{saving ? 'Saving…' : isNew ? `Create ${def.singular}` : 'Save changes'}
				</button>
			</div>
		</Modal>
	);
}
