import { useState } from 'react';
import { useFrappeGetCall } from 'frappe-react-sdk';
import { Icon, type IconName } from '@/components/Icon';
import { ReportView } from '@/components/ReportView';
import { EmptyMsg } from '@/components/ui';
import { API, parseServerError, type ReportCatalogItem } from '@/lib/api';

export function Reports() {
	const { data, error, isLoading } = useFrappeGetCall<{ message: ReportCatalogItem[] }>(
		API.reportList,
		undefined,
	);
	const reports = data?.message ?? [];
	const [active, setActive] = useState<string | null>(null);
	const current = active ?? reports[0]?.key ?? null;

	return (
		<main>
			<div className="eyebrow">Workspace</div>
			<h1>
				Reports & <em>registers</em>
			</h1>
			<div className="sub">
				Filterable registers for compliance, finance and management — export any to Excel or PDF.
			</div>

			{isLoading ? (
				<div className="sub" style={{ marginTop: 22 }}>Loading…</div>
			) : error ? (
				<div className="ferr" style={{ marginTop: 22 }}>{parseServerError(error)}</div>
			) : reports.length === 0 ? (
				<EmptyMsg
					title="No reports available"
					text="Your role does not have read access to any report source."
				/>
			) : (
				<div className="setwrap">
					<nav className="setnav" aria-label="Reports">
						{reports.map((r) => (
							<a
								key={r.key}
								className={current === r.key ? 'on' : ''}
								role="button"
								tabIndex={0}
								onClick={() => setActive(r.key)}
								onKeyDown={(e) => {
									if (e.key === 'Enter' || e.key === ' ') {
										e.preventDefault();
										setActive(r.key);
									}
								}}
							>
								<Icon name={r.icon as IconName} size={17} />
								<span className="lbl">
									<span style={{ display: 'block' }}>{r.title}</span>
									<span style={{ display: 'block', fontSize: 11, color: 'var(--fg-3)' }}>{r.sub}</span>
								</span>
							</a>
						))}
					</nav>
					<div className="setbody">{current && <ReportView key={current} report={current} />}</div>
				</div>
			)}

			<footer>
				<b>ExportFlow</b> · DUX Digitech
			</footer>
		</main>
	);
}
