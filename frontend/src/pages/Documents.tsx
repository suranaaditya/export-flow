import { PagePlaceholder } from '@/components/PagePlaceholder';

export function Documents() {
	return (
		<PagePlaceholder
			eyebrow="Documentation"
			title={
				<>
					Documents <em>workspace</em>
				</>
			}
			sub="Every generated and tracked document across shipments, orders and batches."
			emptyTitle="The documents workspace arrives in Phase 4"
			emptyText="Checklist rules, document instances, PDF generation and blocking logic are the heart of the build — they come online in the Documents phase."
		/>
	);
}
