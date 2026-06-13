import { useEffect, useRef, useState } from 'react';
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
	/** id of a <datalist> for type-ahead suggestions with free-text fallback */
	listId?: string;
}

export function TextInput({ value, onChange, placeholder, disabled, type = 'text', mono, step, listId }: InputProps) {
	return (
		<input
			className={`inp${mono ? ' mono' : ''}`}
			type={type}
			value={value}
			step={step}
			list={listId}
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

export interface SearchOption {
	value: string;
	label?: string;
	/** extra muted line under the label (e.g. city · country) */
	sub?: string;
}

/** The standard link picker: searchable combobox with optional quick-create.
 *  Type to filter, click to pick, × to clear. */
export function SearchSelect({
	value,
	onChange,
	options,
	placeholder,
	disabled,
	onCreate,
	createLabel,
}: {
	value: string;
	onChange: (value: string) => void;
	options: SearchOption[];
	placeholder?: string;
	disabled?: boolean;
	onCreate?: () => void;
	createLabel?: string;
}) {
	const [open, setOpen] = useState(false);
	const [query, setQuery] = useState('');
	const wrap = useRef<HTMLDivElement | null>(null);

	useEffect(() => {
		function onDocClick(e: MouseEvent) {
			if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(false);
		}
		document.addEventListener('mousedown', onDocClick);
		return () => document.removeEventListener('mousedown', onDocClick);
	}, []);

	const selected = options.find((o) => o.value === value);
	const q = query.trim().toLowerCase();
	const filtered = (
		q
			? options.filter(
					(o) =>
						o.value.toLowerCase().includes(q) ||
						(o.label ?? '').toLowerCase().includes(q) ||
						(o.sub ?? '').toLowerCase().includes(q),
				)
			: options
	).slice(0, 50);

	return (
		<div className="swrap" ref={wrap}>
			<input
				className="inp"
				value={open ? query : (selected?.label ?? selected?.value ?? value ?? '')}
				placeholder={placeholder ?? 'Search…'}
				disabled={disabled}
				onFocus={() => {
					if (disabled) return;
					setQuery('');
					setOpen(true);
				}}
				onChange={(e) => {
					setQuery(e.target.value);
					if (!open) setOpen(true);
				}}
			/>
			{value && !disabled && (
				<button
					type="button"
					className="sclear"
					aria-label="Clear"
					onMouseDown={(e) => {
						e.preventDefault();
						onChange('');
						setQuery('');
					}}
				>
					×
				</button>
			)}
			{open && !disabled && (
				<div className="sdrop">
					{filtered.length === 0 && <div className="opt mut">No matches</div>}
					{filtered.map((o) => (
						<div
							className="opt"
							key={o.value}
							onMouseDown={(e) => {
								e.preventDefault();
								onChange(o.value);
								setOpen(false);
							}}
						>
							<div className="lbl">{o.label ?? o.value}</div>
							{o.sub && <div className="sub">{o.sub}</div>}
						</div>
					))}
					{onCreate && (
						<div
							className="opt new"
							onMouseDown={(e) => {
								e.preventDefault();
								setOpen(false);
								onCreate();
							}}
						>
							+ {createLabel ?? 'Create new'}
						</div>
					)}
				</div>
			)}
		</div>
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
