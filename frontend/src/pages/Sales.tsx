import { useFrappeGetCall } from 'frappe-react-sdk';
import { useNavigate } from 'react-router-dom';
import { Icon, type IconName } from '@/components/Icon';
import { Card, CHead, EmptyMsg } from '@/components/ui';
import { API, parseServerError, type SalesDashboardData } from '@/lib/api';
import { fmtMoney } from '@/lib/format';

/** Compact INR money for KPIs — lakh/crore grouping matches the deal currency
 *  helper's Indian convention. */
function inr(value: number | undefined): string {
	if (value === undefined) return '—';
	return fmtMoney(value, 'INR');
}

function monthLabel(ym: string): string {
	const [y, m] = ym.split('-');
	const date = new Date(Number(y), Number(m) - 1, 1);
	return date.toLocaleDateString('en-GB', { month: 'short', year: '2-digit' });
}

function Kpi({
	icon,
	label,
	value,
	detail,
	tone,
}: {
	icon: IconName;
	label: string;
	value: string;
	detail?: React.ReactNode;
	tone?: 'warn' | 'bad';
}) {
	return (
		<div className="card kpi">
			<div className="lb">
				<Icon name={icon} size={14} /> {label}
			</div>
			<div className="v">{value}</div>
			{detail !== undefined && (
				<div className="d">{tone ? <span className={tone}>{detail}</span> : detail}</div>
			)}
		</div>
	);
}

/** Horizontal bar row for the breakdown cards. */
function BarRow({
	label,
	sub,
	value,
	max,
	onClick,
}: {
	label: string;
	sub?: string;
	value: number;
	max: number;
	onClick?: () => void;
}) {
	return (
		<div
			className="row"
			style={{ cursor: onClick ? 'pointer' : 'default', alignItems: 'center' }}
			onClick={onClick}
		>
			<span className="tx">
				<span className="t1" style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
					<span>{label}</span>
					<span className="data">{inr(value)}</span>
				</span>
				<span
					className="seg"
					style={{ marginTop: 6, height: 4, borderRadius: 3, background: 'var(--surface-3)' }}
				>
					<i
						className="f"
						style={{
							display: 'block',
							height: '100%',
							borderRadius: 3,
							width: `${max ? Math.max(3, (value / max) * 100) : 0}%`,
							background: 'var(--brand-grad)',
						}}
					/>
				</span>
				{sub && (
					<span className="t2" style={{ display: 'block', marginTop: 3 }}>
						{sub}
					</span>
				)}
			</span>
		</div>
	);
}

export function Sales() {
	const navigate = useNavigate();
	const { data, error, isLoading } = useFrappeGetCall<{ message: SalesDashboardData }>(
		API.salesDashboard,
		undefined,
	);
	const d = data?.message;
	const kpis = d?.kpis ?? {};

	const byCurrency = kpis.export_value_by_currency ?? [];
	const custMax = Math.max(1, ...(d?.by_customer ?? []).map((c) => c.value_inr));
	const countryMax = Math.max(1, ...(d?.by_country ?? []).map((c) => c.value_inr));
	const monthMax = Math.max(1, ...(d?.by_month ?? []).map((m) => m.value_inr));

	const marginTone =
		kpis.gross_margin_inr !== undefined && kpis.gross_margin_inr < 0 ? 'bad' : undefined;

	return (
		<main>
			<div className="eyebrow">Sales · Financial</div>
			<h1>
				Sales <em>performance</em>
			</h1>
			<div className="sub">
				{isLoading ? (
					'Tallying the books…'
				) : error ? (
					parseServerError(error)
				) : (
					<>
						<b>{fmtMoney(kpis.export_value_inr, 'INR')}</b> exported across{' '}
						<b>{kpis.order_count ?? 0}</b> order{(kpis.order_count ?? 0) === 1 ? '' : 's'}.
					</>
				)}
			</div>

			<div className="kpis">
				<Kpi
					icon="banknote"
					label="Export value"
					value={inr(kpis.export_value_inr)}
					detail={
						byCurrency.length
							? byCurrency.map((c) => `${fmtMoney(c.amount, c.currency)}`).join(' · ')
							: '—'
					}
				/>
				<Kpi
					icon="download"
					label="Received"
					value={inr(kpis.pfi_received_inr)}
					detail={
						kpis.pfi_outstanding_inr !== undefined ? (
							<>{inr(kpis.pfi_outstanding_inr)} outstanding</>
						) : (
							'—'
						)
					}
					tone={kpis.pfi_outstanding_inr && kpis.pfi_outstanding_inr > 0 ? 'warn' : undefined}
				/>
				<Kpi
					icon="cube"
					label="Procurement cost"
					value={inr(kpis.procurement_inr)}
					detail={`${kpis.order_count ?? 0} orders sourced`}
				/>
				<Kpi
					icon="layers"
					label="Gross margin"
					value={inr(kpis.gross_margin_inr)}
					detail={
						kpis.margin_pct !== undefined ? `${kpis.margin_pct}% indicative` : 'needs procurement'
					}
					tone={marginTone}
				/>
			</div>

			{(kpis.incentive_inr !== undefined || kpis.realized_inr !== undefined) && (
				<div className="kpis">
					<Kpi
						icon="shield"
						label="Incentives earned"
						value={inr(kpis.incentive_inr)}
						detail={
							kpis.incentive_pending_inr ? `${inr(kpis.incentive_pending_inr)} pending` : 'RoDTEP + drawback'
						}
						tone={kpis.incentive_pending_inr && kpis.incentive_pending_inr > 0 ? 'warn' : undefined}
					/>
					<Kpi
						icon="circle-check"
						label="Proceeds realized"
						value={inr(kpis.realized_inr)}
						detail={
							kpis.realization_outstanding_inr !== undefined
								? `${inr(kpis.realization_outstanding_inr)} outstanding`
								: 'eBRC closure'
						}
						tone={kpis.realization_outstanding_inr && kpis.realization_outstanding_inr > 0 ? 'warn' : undefined}
					/>
					<Kpi
						icon="warning"
						label="Realization overdue"
						value={String(kpis.realization_overdue ?? 0)}
						detail="past the FEMA window"
						tone={kpis.realization_overdue && kpis.realization_overdue > 0 ? 'bad' : undefined}
					/>
					<Kpi
						icon="rupee"
						label="Net margin"
						value={inr(kpis.net_margin_inr)}
						detail="incl. incentives"
						tone={kpis.net_margin_inr !== undefined && kpis.net_margin_inr < 0 ? 'bad' : undefined}
					/>
				</div>
			)}

			<div className="grid">
				<div className="stack">
					<Card accent>
						<CHead
							icon="building"
							title="Top customers"
							count={d ? `${d.by_customer.length}` : undefined}
						/>
						{isLoading ? (
							<div className="sub" style={{ padding: '14px 18px' }}>
								Loading…
							</div>
						) : error ? (
							<div className="ferr" style={{ padding: '14px 18px' }}>{parseServerError(error)}</div>
						) : !d || d.by_customer.length === 0 ? (
							<EmptyMsg title="No orders yet" text="Booked sales orders rank here by value." />
						) : (
							<div className="rows">
								{d.by_customer.map((c) => (
									<BarRow
										key={c.customer}
										label={c.customer}
										sub={`${c.orders} order${c.orders === 1 ? '' : 's'}`}
										value={c.value_inr}
										max={custMax}
									/>
								))}
							</div>
						)}
					</Card>

					<Card>
						<CHead icon="ship" title="Export value by month" count="last 12" />
						{!d || d.by_month.length === 0 ? (
							<EmptyMsg title="No history yet" text="Monthly export value plots here." />
						) : (
							<div style={{ display: 'flex', alignItems: 'flex-end', gap: 8, padding: '20px 18px', height: 180 }}>
								{d.by_month.map((m) => (
									<div
										key={m.month}
										style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, minWidth: 0 }}
										title={`${monthLabel(m.month)} · ${inr(m.value_inr)}`}
									>
										<div
											style={{
												width: '100%',
												height: `${Math.max(2, (m.value_inr / monthMax) * 120)}px`,
												borderRadius: '4px 4px 0 0',
												background: 'var(--brand-grad)',
											}}
										/>
										<span className="dim" style={{ fontSize: 10.5, whiteSpace: 'nowrap' }}>
											{monthLabel(m.month)}
										</span>
									</div>
								))}
							</div>
						)}
					</Card>
				</div>

				<div className="stack">
					<Card>
						<CHead icon="package" title="By destination" />
						{!d || d.by_country.length === 0 ? (
							<EmptyMsg title="No destinations yet" />
						) : (
							<div className="rows">
								{d.by_country.map((c) => (
									<BarRow key={c.country} label={c.country} value={c.value_inr} max={countryMax} />
								))}
							</div>
						)}
					</Card>

					<Card>
						<CHead icon="banknote" title="Realization" count="PFI" />
						{kpis.pfi_raised_inr === undefined ? (
							<EmptyMsg title="No proforma invoices" text="Raised vs received shows here." />
						) : (
							<div className="facts">
								<div className="f">
									<span className="k">Raised</span>
									<span className="v data">{inr(kpis.pfi_raised_inr)}</span>
								</div>
								<div className="f">
									<span className="k">Received</span>
									<span className="v data">{inr(kpis.pfi_received_inr)}</span>
								</div>
								<div className="f">
									<span className="k">Outstanding</span>
									<span className="v data">{inr(kpis.pfi_outstanding_inr)}</span>
								</div>
							</div>
						)}
					</Card>

					<Card>
						<CHead icon="file-text" title="Order book" />
						<div className="facts">
							<div className="f">
								<span className="k">Open order value</span>
								<span className="v data">{inr(kpis.open_value_inr)}</span>
							</div>
							<div className="f">
								<span className="k">Total orders</span>
								<span className="v data">{kpis.order_count ?? 0}</span>
							</div>
						</div>
						<div style={{ padding: '0 18px 16px' }}>
							<button className="btn" onClick={() => navigate('/sales-orders')}>
								<Icon name="file-text" size={15} /> Open sales orders
							</button>
						</div>
					</Card>
				</div>
			</div>

			<footer>
				<b>ExportFlow</b> · DUX Digitech
			</footer>
		</main>
	);
}
