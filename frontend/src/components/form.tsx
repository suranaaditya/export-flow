import type { ChangeEvent, ReactNode } from 'react';

/**
 * Form primitives styled per the DUX design system's Input spec (42px tall,
 * 12px radius, hairline border, iris focus ring) — see .field/.inp rules in
 * app.css. The approved mockups define no form screens, so these follow the
 * design-system component guidance instead.
 */

export function Field({
	label,
	hint,
	children,
	required,
}: {
	label: string;
	hint?: string;
	children: ReactNode;
	required?: boolean;
}) {
	return (
		<label className="field">
			<span className="flabel">
				{label}
				{required ? <em> *</em> : null}
			</span>
			{children}
			{hint ? <span className="fhint">{hint}</span> : null}
		</label>
	);
}

interface InputProps {
	value: string;
	onChange: (value: string) => void;
	placeholder?: string;
	disabled?: boolean;
	type?: 'text' | 'date' | 'number';
	mono?: boolean;
	step?: string;
}

export function TextInput({ value, onChange, placeholder, disabled, type = 'text', mono, step }: InputProps) {
	return (
		<input
			className={`inp${mono ? ' mono' : ''}`}
			type={type}
			value={value}
			step={step}
			placeholder={placeholder}
			disabled={disabled}
			onChange={(e: ChangeEvent<HTMLInputElement>) => onChange(e.target.value)}
		/>
	);
}

export function SelectInput({
	value,
	onChange,
	options,
	disabled,
	allowEmpty,
}: {
	value: string;
	onChange: (value: string) => void;
	options: { value: string; label?: string }[];
	disabled?: boolean;
	allowEmpty?: boolean;
}) {
	return (
		<select
			className="inp"
			value={value}
			disabled={disabled}
			onChange={(e: ChangeEvent<HTMLSelectElement>) => onChange(e.target.value)}
		>
			{allowEmpty && <option value="" />}
			{options.map((opt) => (
				<option key={opt.value} value={opt.value}>
					{opt.label ?? opt.value}
				</option>
			))}
		</select>
	);
}

export function TextArea({
	value,
	onChange,
	rows = 3,
	placeholder,
	disabled,
}: {
	value: string;
	onChange: (value: string) => void;
	rows?: number;
	placeholder?: string;
	disabled?: boolean;
}) {
	return (
		<textarea
			className="inp area"
			rows={rows}
			value={value}
			placeholder={placeholder}
			disabled={disabled}
			onChange={(e: ChangeEvent<HTMLTextAreaElement>) => onChange(e.target.value)}
		/>
	);
}

export function CheckInput({
	checked,
	onChange,
	label,
	disabled,
}: {
	checked: boolean;
	onChange: (checked: boolean) => void;
	label: string;
	disabled?: boolean;
}) {
	return (
		<label className="checkrow">
			<input
				type="checkbox"
				checked={checked}
				disabled={disabled}
				onChange={(e: ChangeEvent<HTMLInputElement>) => onChange(e.target.checked)}
			/>
			<span>{label}</span>
		</label>
	);
}
