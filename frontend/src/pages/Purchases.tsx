import { PagePlaceholder } from '@/components/PagePlaceholder';

export function Purchases() {
	return (
		<PagePlaceholder
			eyebrow="Buying"
			title={
				<>
					Purchase <em>orders</em>
				</>
			}
			sub="Drop-ship procurement mapped to sales orders, with the 90-day GST clock."
			emptyTitle="Purchase screens arrive in Phase 3"
			emptyText="PO lists with merchant-export-scheme chips and GST export deadlines land alongside the shipment module."
		/>
	);
}
