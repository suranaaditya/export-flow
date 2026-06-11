import { PagePlaceholder } from '@/components/PagePlaceholder';

export function Shipments() {
	return (
		<PagePlaceholder
			eyebrow="Logistics"
			title={
				<>
					Live <em>shipments</em>
				</>
			}
			sub="Sea and air consignments with milestones and document checklists."
			emptyTitle="Shipment screens arrive in Phase 3"
			emptyText="The shipment list and the milestone-timeline detail screen (per the approved mockup) are built in the Logistics phase."
		/>
	);
}
