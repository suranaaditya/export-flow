import { PagePlaceholder } from '@/components/PagePlaceholder';

function todayEyebrow(): string {
	const now = new Date();
	const formatted = now.toLocaleDateString('en-GB', {
		weekday: 'long',
		day: 'numeric',
		month: 'long',
		year: 'numeric',
	});
	return `Operations · ${formatted}`;
}

export function Dashboard() {
	return (
		<PagePlaceholder
			eyebrow={todayEyebrow()}
			title={
				<>
					Morning <em>review</em>
				</>
			}
			sub="Live shipments, deadlines and documents will appear here."
			emptyTitle="The dashboard arrives in Phase 5"
			emptyText="KPI cards, the live shipments table, deadline feed and pending-documents feed light up once shipments and the documentation engine are in place."
		/>
	);
}
