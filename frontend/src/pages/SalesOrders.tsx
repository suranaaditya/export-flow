import { PagePlaceholder } from '@/components/PagePlaceholder';

export function SalesOrders() {
	return (
		<PagePlaceholder
			eyebrow="Selling"
			title={
				<>
					Sales <em>orders</em>
				</>
			}
			sub="Deals, pro forma invoices and payment roll-ups."
			emptyTitle="Sales order screens arrive in Phase 2"
			emptyText="The list and detail views — with PFI summaries, received amounts and balances — are built in the Money phase."
		/>
	);
}
