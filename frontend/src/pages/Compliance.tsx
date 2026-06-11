import { PagePlaceholder } from '@/components/PagePlaceholder';

export function Compliance() {
	return (
		<PagePlaceholder
			eyebrow="Registers"
			title={
				<>
					Compliance <em>register</em>
				</>
			}
			sub="IEC, LUT, RCMC, drug licences and AD codes — with renewal alerts."
			emptyTitle="The compliance register arrives in Phase 5"
			emptyText="Company-level records with expiry tracking and 60/30/7-day alerts are built in the Intelligence phase."
		/>
	);
}
