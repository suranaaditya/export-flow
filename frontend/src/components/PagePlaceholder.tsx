import type { ReactNode } from 'react';

const BRAND = import.meta.env.BASE_URL + 'brand/';

interface PagePlaceholderProps {
	eyebrow: string;
	title: ReactNode;
	sub?: ReactNode;
	emptyTitle: string;
	emptyText: string;
}

/**
 * Shared scaffold for screens whose data layer lands in a later phase.
 * Renders the mockups' page intro plus a card with the DUX empty-state
 * pattern (mascot allowed in empty states only).
 */
export function PagePlaceholder({ eyebrow, title, sub, emptyTitle, emptyText }: PagePlaceholderProps) {
	return (
		<main>
			<div className="eyebrow">{eyebrow}</div>
			<h1>{title}</h1>
			{sub ? <div className="sub">{sub}</div> : null}
			<div className="card" style={{ marginTop: 22 }}>
				<div className="empty">
					<img src={BRAND + 'dux-mascot.png'} alt="" />
					<div className="t1">{emptyTitle}</div>
					<div className="t2">{emptyText}</div>
				</div>
			</div>
			<footer>
				<b>ExportFlow</b> · DUX Digitech
			</footer>
		</main>
	);
}
