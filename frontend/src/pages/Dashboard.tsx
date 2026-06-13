import type { ReactNode } from 'react';
import { useFrappeGetCall } from 'frappe-react-sdk';
import { Link, useNavigate } from 'react-router-dom';
import { Icon, type IconName } from '@/components/Icon';
import { Card, CHead, EmptyMsg, Tag } from '@/components/ui';
import { API, parseServerError, type DashboardData, type DeadlineRow } from '@/lib/api';
import { fmtDate, fmtMoney } from '@/lib/format';

/** "6d" / "today" / "3d over" — feed badge copy per the mockup. */
function whenLabel(days: number): string {
	if (days === 0) return 'today';
	if (days < 0) return `${-days}d over`;
	return `${days}d`;
}

function whenClass(days: number): string {
	if (days <= 7) return 'when bad';
	if (days <= 14) return 'when warn';
	return 'when mut';
}

function glyphClass(days: number | null, blocking?: boolean): string {
	if (blocking || (days !== null && days <= 7)) return 'glyph bad';
	if (days !== null && days <= 14) return 'glyph warn';
	return 'glyph neut';
}

const DEADLINE_ICONS: Record<DeadlineRow['kind'], IconName> = {
	lc: 'calendar',
	gst: 'clock',
	compliance: 'shield',
	mtt: 'globe',
};

function todayLine(): string {
	return new Date().toLocaleDateString('en-GB', {
		weekday: 'long',
		day: '2-digit',
		month: 'long',
		year: 'numeric',
	});
}

/** Calm error → loading → empty → content ladder shared by every card. */
function CardBody({
	error,
	isLoading,
	empty,
	emptyNode,
	children,
}: {
	error: unknown;
	isLoading: boolean;
	empty: boolean;
	emptyNode: ReactNode;
	children: ReactNode;
}) {
	if (error)
		return (
			<div className="ferr" style={{ padding: '14px 18px' }}>
				{parseServerError(error)}
			</div>
		);
	if (isLoading)
		return (
			<div className="sub" style={{ padding: '14px 18px' }}>
				Loading…
			</div>
		);
	if (empty) return <>{emptyNode}</>;
	return <>{children}</>;
}

export function Dashboard() {
	const navigate = useNavigate();
	const { data, error, isLoading } = useFrappeGetCall<{ message: DashboardData }>(
		API.dashboard,
		undefined,
	);
	const d = data?.message;
	const kpis = d?.kpis ?? {};

	const receivable = kpis.receivable ?? [];
	const primaryReceivable = receivable.length
		? receivable.reduce((a, b) => (b.amount > a.amount ? b : a))
		: null;
	const attention =
		(kpis.docs_blocking ?? 0) + (kpis.lc_at_risk ?? 0) + (kpis.awaiting_leo ?? 0);

	return (
		<main>
			<div className="eyebrow">Operations · {todayLine()}</div>
			<h1>
				Morning <em>review</em>
			</h1>
			<div className="sub">
				{isLoading ? (
					'Pulling the day together…'
				) : error ? (
					parseServerError(error)
				) : (
					<>
						<b>{kpis.live_shipments ?? 0}</b> live shipment
						{(kpis.live_shipments ?? 0) === 1 ? '' : 's'}
						{attention > 0 ? (
							<>
								{' '}
								— <b>{attention}</b> need{attention === 1 ? 's' : ''} your attention today.
							</>
						) : (
							' — nothing is on fire.'
						)}
					</>
				)}
			</div>

			<div className="kpis">
				<div className="card kpi">
					<div className="lb">
						<Icon name="ship" size={14} /> Live shipments
					</div>
					<div className="v">{kpis.live_shipments ?? '—'}</div>
					<div className="d">
						{!d ? (
							'—'
						) : (
							<>
								{(kpis.awaiting_leo ?? 0) > 0 ? (
									<span className="warn">{kpis.awaiting_leo} awaiting LEO</span>
								) : (
									'none awaiting LEO'
								)}
								{' · '}
								{kpis.in_transit ?? 0} in transit
							</>
						)}
					</div>
				</div>
				<div className="card kpi">
					<div className="lb">
						<Icon name="file-text" size={14} /> Documents pending
					</div>
					<div className="v">{kpis.docs_pending ?? '—'}</div>
					<div className="d">
						{!d ? (
							'—'
						) : (
							<>
								{(kpis.docs_blocking ?? 0) > 0 ? (
									<span className="bad">{kpis.docs_blocking} blocking</span>
								) : (
									'none blocking'
								)}
								{' · '}
								{kpis.docs_with_cha ?? 0} with CHA
							</>
						)}
					</div>
				</div>
				<div className="card kpi">
					<div className="lb">
						<Icon name="banknote" size={14} /> Receivable
					</div>
					<div className="v">
						{primaryReceivable ? fmtMoney(primaryReceivable.amount, primaryReceivable.currency) : '—'}
					</div>
					<div className="d">
						{!d ? (
							'—'
						) : (
							<>
								Across{' '}
								<span className="data" style={{ fontSize: 12 }}>
									{kpis.open_pfis ?? 0}
								</span>{' '}
								open PFI{(kpis.open_pfis ?? 0) === 1 ? '' : 's'}
								{receivable.length > 1
									? ` · +${receivable.length - 1} more currenc${receivable.length === 2 ? 'y' : 'ies'}`
									: ''}
							</>
						)}
					</div>
				</div>
				<div className="card kpi">
					<div className="lb">
						<Icon name="calendar" size={14} /> Deadlines · 14 days
					</div>
					<div className="v">{kpis.deadlines_14d ?? '—'}</div>
					<div className="d">
						{!d ? (
							'—'
						) : (
							<>
								{(kpis.lc_at_risk ?? 0) > 0 ? (
									<span className="bad">{kpis.lc_at_risk} LC at risk</span>
								) : (
									'no LC at risk'
								)}
								{' · '}
								{kpis.gst_at_risk ?? 0} GST clock{(kpis.gst_at_risk ?? 0) === 1 ? '' : 's'}
							</>
						)}
					</div>
				</div>
			</div>

			<div className="grid">
				<Card accent>
					<CHead
						icon="ship"
						title="Live shipments"
						count={
							d ? `${d.shipments.length} of ${kpis.live_shipments ?? d.shipments.length}` : undefined
						}
						action={<Link to="/shipments">Open all</Link>}
					/>
					<CardBody
						error={error}
						isLoading={isLoading}
						empty={!d || d.shipments.length === 0}
						emptyNode={
							<EmptyMsg
								title="No live shipments"
								text="Book one from a sales order — it lands here with its checklist."
							/>
						}
					>
						<table className="clickable">
							<thead>
								<tr>
									<th>Shipment</th>
									<th>Customer</th>
									<th>Mode</th>
									<th>Milestone</th>
									<th>Docs</th>
									<th>ETD</th>
									<th>Status</th>
								</tr>
							</thead>
							<tbody>
								{(d?.shipments ?? []).map((s) => (
									<tr key={s.name} onClick={() => navigate('/shipments/' + s.name)}>
										<td>
											<span className="id">{s.name}</span>
										</td>
										<td>
											<div className="c1">{s.customer_name}</div>
											{s.route && <div className="c2">{s.route}</div>}
										</td>
										<td>
											<span className="mode">
												<Icon name={s.mode === 'Air' ? 'plane' : 'ship'} size={14} /> {s.mode}
											</span>
										</td>
										<td>
											<div className="mile">
												<span className="nm">{s.current_milestone}</span>
												<span className="seg">
													{Array.from({ length: s.milestones_total || 9 }, (_, i) => (
														<i key={i} className={i < s.milestones_done ? 'f' : ''} />
													))}
												</span>
											</div>
										</td>
										<td>
											<div className="docs">
												<span className="dim">
													{s.docs_done}/{s.docs_total}
												</span>
												<span className="bar">
													<i
														style={{
															width: `${s.docs_total ? (s.docs_done / s.docs_total) * 100 : 0}%`,
														}}
													/>
												</span>
											</div>
										</td>
										<td>
											<span className="dim">{fmtDate(s.etd)}</span>
										</td>
										<td>
											<Tag tone={s.tone}>{s.chip}</Tag>
										</td>
									</tr>
								))}
							</tbody>
						</table>
					</CardBody>
				</Card>

				<div className="stack">
					{(!d || d.can.lc || d.can.po || d.can.compliance || d.can.shipment) && (
						<Card>
							<CHead icon="calendar" title="Deadlines" count="upcoming" />
							<CardBody
								error={error}
								isLoading={isLoading}
								empty={!d || d.deadlines.length === 0}
								emptyNode={
									<EmptyMsg title="Nothing due" text="LC dates, GST clocks and renewals appear here." />
								}
							>
								<div className="rows">
									{(d?.deadlines ?? []).map((row, i) => (
										<div className="row" key={i} onClick={() => navigate(row.route)}>
											<span className={glyphClass(row.days)}>
												<Icon name={DEADLINE_ICONS[row.kind]} size={15} />
											</span>
											<span className="tx">
												<span className="t1" style={{ display: 'block' }}>
													{row.label}
													{row.ref && (
														<>
															{' — '}
															<span className="data">{row.ref}</span>
														</>
													)}
												</span>
												<span className="t2" style={{ display: 'block' }}>
													{row.sub}
												</span>
											</span>
											<span className={whenClass(row.days)}>{whenLabel(row.days)}</span>
										</div>
									))}
								</div>
							</CardBody>
						</Card>
					)}

					{(!d || d.can.doc) && (
						<Card>
							<CHead
								icon="file-text"
								title="Documents pending"
								count={kpis.docs_pending !== undefined ? `${kpis.docs_pending} open` : undefined}
								action={<Link to="/documents">Open all</Link>}
							/>
							<CardBody
								error={error}
								isLoading={isLoading}
								empty={!d || d.documents.length === 0}
								emptyNode={
									<EmptyMsg title="All paperwork moving" text="Open documents surface here by urgency." />
								}
							>
								<div className="rows">
									{(d?.documents ?? []).map((row, i) => (
										<div
											className="row"
											key={i}
											onClick={() =>
												navigate(
													row.shipment
														? `/documents?shipment=${encodeURIComponent(row.shipment)}`
														: '/documents',
												)
											}
										>
											<span className={glyphClass(row.days, row.blocking === 1)}>
												<Icon name={row.blocking ? 'warning' : 'file'} size={15} />
											</span>
											<span className="tx">
												<span className="t1" style={{ display: 'block' }}>
													{row.document_type}
													{row.shipment ? (
														<>
															{' · '}
															<span className="data">{row.shipment}</span>
														</>
													) : null}
												</span>
												<span className="t2" style={{ display: 'block' }}>
													{row.blocking ? 'blocking · ' : ''}
													{row.status.toLowerCase()}
													{row.responsible_party ? ` · ${row.responsible_party}` : ''}
												</span>
											</span>
											{row.days !== null && (
												<span className={whenClass(row.days)}>{whenLabel(row.days)}</span>
											)}
										</div>
									))}
								</div>
							</CardBody>
						</Card>
					)}

					{(!d || d.can.pfi) && (
						<Card>
							<CHead icon="banknote" title="Pro forma invoices" count="awaiting payment" />
							<CardBody
								error={error}
								isLoading={isLoading}
								empty={!d || d.pfis.length === 0}
								emptyNode={<EmptyMsg title="Nothing outstanding" text="Sent PFIs await payment here." />}
							>
								<div className="rows">
									{(d?.pfis ?? []).map((p) => (
										<div className="row" key={p.name} onClick={() => navigate('/pfi/' + p.name)}>
											<span className="glyph warn">
												<Icon name="banknote" size={15} />
											</span>
											<span className="tx">
												<span className="t1" style={{ display: 'block' }}>
													<span className="data">{p.name}</span> · {p.customer}
												</span>
												<span className="t2" style={{ display: 'block' }}>
													{p.stage_description || `raised ${fmtDate(p.pfi_date)}`}
												</span>
											</span>
											<span className="when warn">{fmtMoney(p.balance, p.currency)}</span>
										</div>
									))}
								</div>
							</CardBody>
						</Card>
					)}
				</div>
			</div>

			<footer>
				<b>ExportFlow</b> · DUX Digitech
			</footer>
		</main>
	);
}
