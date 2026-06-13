import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { Icon, type IconName } from '@/components/Icon';

/** Mockup card shell: hairline border, 16px radius, duxSettle entrance. */
export function Card({
	accent,
	className = '',
	children,
}: {
	accent?: boolean;
	className?: string;
	children: ReactNode;
}) {
	return <div className={`card${accent ? ' accent' : ''} ${className}`.trim()}>{children}</div>;
}

/** Card header per mockups: icon · title · mono count · spacer · action. */
export function CHead({
	icon,
	title,
	count,
	bar,
	action,
}: {
	icon: IconName;
	title: string;
	count?: ReactNode;
	bar?: number; // 0..100 mini progress bar
	action?: ReactNode;
}) {
	return (
		<div className="chead">
			<Icon name={icon} size={16} />
			<span className="ttl">{title}</span>
			{count !== undefined && <span className="cnt">{count}</span>}
			{bar !== undefined && (
				<span className="bar">
					<i style={{ width: `${Math.max(0, Math.min(100, bar))}%` }} />
				</span>
			)}
			<span className="spacer" />
			{action}
		</div>
	);
}

/** Status chip with leading dot (.tag.ok/.pend/.err). */
export function Tag({ tone, children }: { tone: 'ok' | 'pend' | 'err'; children: ReactNode }) {
	return <span className={`tag ${tone}`}>{children}</span>;
}

/** Key/value fact rows (shipment mockup "Voyage" panel pattern). */
export function Facts({
	rows,
}: {
	rows: { k: string; v: ReactNode; data?: boolean }[];
}) {
	return (
		<div className="facts">
			{rows.map((row) => (
				<div className="f" key={row.k}>
					<span className="k">{row.k}</span>
					<span className={`v${row.data ? ' data' : ''}`}>{row.v}</span>
				</div>
			))}
		</div>
	);
}

/** Linked-record row (shipment mockup .lrow pattern). */
export function LRow({
	icon,
	t1,
	t2,
	right,
	onClick,
}: {
	icon: IconName;
	t1: ReactNode;
	t2: ReactNode;
	right?: ReactNode;
	onClick?: () => void;
}) {
	return (
		<a
			className="lrow"
			onClick={(e) => {
				e.preventDefault();
				onClick?.();
			}}
			href="#"
		>
			<span className="glyph">
				<Icon name={icon} size={15} />
			</span>
			<span className="tx">
				<span className="t1" style={{ display: 'block' }}>
					{t1}
				</span>
				<span className="t2" style={{ display: 'block' }}>
					{t2}
				</span>
			</span>
			{right !== undefined && <span className="r">{right}</span>}
		</a>
	);
}

/** Modal dialog in the card language (hairline, 16px radius, settle-in). */
export function Modal({
	title,
	icon,
	onClose,
	children,
}: {
	title: string;
	icon: IconName;
	onClose: () => void;
	children: ReactNode;
}) {
	// Portal to <body>: a modal rendered inside a card (overflow:hidden +
	// transform animation) would otherwise be clipped to the card instead of
	// covering the viewport.
	return createPortal(
		<div
			className="overlay"
			onClick={(e) => {
				if (e.target === e.currentTarget) onClose();
			}}
		>
			<div className="modal" role="dialog" aria-label={title}>
				<div className="chead">
					<Icon name={icon} size={16} />
					<span className="ttl">{title}</span>
					<span className="spacer" />
					<button className="xbtn" onClick={onClose} aria-label="Close">
						<Icon name="close" size={14} />
					</button>
				</div>
				{children}
			</div>
		</div>,
		document.body,
	);
}

/** Centered empty-state body for cards (no mascot variant for data panels). */
export function EmptyMsg({ title, text }: { title: string; text?: string }) {
	return (
		<div className="empty" style={{ padding: '28px 20px' }}>
			<div className="t1">{title}</div>
			{text && <div className="t2">{text}</div>}
		</div>
	);
}
