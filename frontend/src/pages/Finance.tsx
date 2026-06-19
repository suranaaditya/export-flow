import { useState } from 'react';
import { useFrappeGetCall } from 'frappe-react-sdk';
import { useNavigate } from 'react-router-dom';
import { Icon, type IconName } from '@/components/Icon';
import { IncentiveModal, RealizationModal } from '@/components/financeModals';
import { TextInput } from '@/components/form';
import { FilterBar, applyFilters, useFilterState, type FilterDef } from '@/components/FilterBar';
import { Card, CHead, EmptyMsg, Tag } from '@/components/ui';
import {
	API,
	incentiveTone,
	realizationTone,
	parseServerError,
	urgencyLabel,
	urgencyTone,
	type FinanceWorkspaceData,
	type IncentiveRow,
	type MTTTrade,
	type RealizationRow,
} from '@/lib/api';
import { fmtDate, fmtMoney } from '@/lib/format';

function mttRowStatus(t: MTTTrade): { tone: 'ok' | 'pend' | 'err'; label: string } {
	if (!t.completed && t.completion_days != null && t.completion_days < 0)
		return { tone: 'err', label: 'Completion overdue' };
	if (t.outlay_open && t.outlay_days != null && t.outlay_days < 0)
		return { tone: 'err', label: 'Outlay overdue' };
	if (t.net_fx_profit_inr != null && t.net_fx_profit_inr < 0) return { tone: 'err', label: 'FX loss' };
	if (t.completed) return { tone: 'ok', label: 'Completed' };
	return { tone: 'pend', label: 'In progress' };
}

const inr = (v: number | null | undefined) => (v == null ? '—' : fmtMoney(v, 'INR'));

const INC_FILTERS: FilterDef<IncentiveRow>[] = [
	{
		key: 'scheme',
		label: 'Scheme',
		control: 'select',
		get: (i) => i.scheme,
		options: [
			{ value: 'RoDTEP', label: 'RoDTEP' },
			{ value: 'Duty Drawback', label: 'Duty Drawback' },
		],
	},
	{ key: 'status', label: 'Status', control: 'select', get: (i) => i.status },
];

const REAL_FILTERS: FilterDef<RealizationRow>[] = [
	{ key: 'status', label: 'Status', control: 'select', get: (r) => r.status },
	{ key: 'overdue', label: 'Overdue only', control: 'toggle', get: (r) => !!r.overdue },
];

function Kpi({ icon, label, value, detail, tone }: { icon: IconName; label: string; value: string; detail: string; tone?: 'warn' | 'bad' }) {
	return (
		<div className="card kpi">
			<div className="lb">
				<Icon name={icon} size={14} /> {label}
			</div>
			<div className="v">{value}</div>
			<div className="d">{tone ? <span className={tone}>{detail}</span> : detail}</div>
		</div>
	);
}

export function Finance() {
	const navigate = useNavigate();
	const { data, error, isLoading, mutate } = useFrappeGetCall<{ message: FinanceWorkspaceData }>(
		API.financeWorkspace,
		undefined,
	);
	const [incModal, setIncModal] = useState<'new' | IncentiveRow | null>(null);
	const [relModal, setRelModal] = useState<'new' | RealizationRow | null>(null);

	const d = data?.message;
	const kpis = d?.kpis ?? {};
	const mttTrades = d?.mtt_trades ?? [];
	const mttOverdue = (kpis.mtt_completion_overdue ?? 0) + (kpis.mtt_outlay_overdue ?? 0);

	// one search box spans all three tables; status/scheme/overdue scope per table
	const [query, setQuery] = useState('');
	const incFilter = useFilterState();
	const relFilter = useFilterState();
	const q = query.trim().toLowerCase();
	const hit = (...vals: (string | null | undefined)[]) =>
		!q || vals.some((v) => (v ?? '').toLowerCase().includes(q));
	const incSearched = (d?.incentives ?? []).filter((i) =>
		hit(i.shipment, i.shipping_bill_no, i.scrip_number, i.scroll_number, i.scheme),
	);
	const incentives = applyFilters(incSearched, INC_FILTERS, incFilter.state);
	const relSearched = (d?.realizations ?? []).filter((r) =>
		hit(r.export_invoice, r.shipment, r.firc_no, r.ebrc_number, r.customer),
	);
	const realizations = applyFilters(relSearched, REAL_FILTERS, relFilter.state);
	const mttFiltered = mttTrades.filter((t) => hit(t.shipment, t.customer_name));
	const incFiltering = !!q || INC_FILTERS.some((f) => incFilter.state[f.key]);
	const relFiltering = !!q || REAL_FILTERS.some((f) => relFilter.state[f.key]);
	// create gates the "New" actions; write makes rows editable; delete is gated
	// inside the modal — each is the user's real ERPNext permission
	const can = d?.can;
	const canIncNew = can?.incentive_create;
	const canIncEdit = can?.incentive_write;
	const canRelNew = can?.realization_create;
	const canRelEdit = can?.realization_write;
	const loading = isLoading || !d;
	const dash = (s: string) => (loading ? '—' : s);

	return (
		<main>
			<div className="eyebrow">Finance · Incentives & realization</div>
			<h1>
				Export <em>finance</em>
			</h1>
			<div className="sub">
				RoDTEP & drawback incentives and bank realization (FIRC → eBRC) — the money trail that
				closes every export.
			</div>

			<div className="kpis">
				<Kpi icon="shield" label="Incentives earned" value={inr(kpis.incentive_total)} detail={dash(kpis.incentive_pending ? `${inr(kpis.incentive_pending)} pending` : 'RoDTEP + drawback')} tone={kpis.incentive_pending ? 'warn' : undefined} />
				<Kpi icon="banknote" label="Proceeds realized" value={inr(kpis.realized)} detail={dash(`${kpis.open_count ?? 0} still open`)} />
				<Kpi icon="warning" label="Overdue" value={loading ? '—' : String(kpis.overdue_count ?? 0)} detail="past FEMA window" tone={kpis.overdue_count ? 'bad' : undefined} />
				<Kpi icon="file-text" label="Realizations" value={loading ? '—' : String(d?.realizations.length ?? 0)} detail="export invoices tracked" />
				{!loading && (kpis.mtt_count ?? 0) > 0 && (
					<Kpi
						icon="globe"
						label="Merchanting trades"
						value={String(kpis.mtt_count ?? 0)}
						detail={mttOverdue ? `${mttOverdue} clock${mttOverdue === 1 ? '' : 's'} overdue` : 'FEMA MTT compliance'}
						tone={mttOverdue ? 'bad' : undefined}
					/>
				)}
			</div>

			{!error && (
				<div className="field" style={{ width: 300, margin: '2px 0 14px' }}>
					<TextInput value={query} onChange={setQuery} placeholder="Search invoice, shipment, SB or eBRC" />
				</div>
			)}

			{error ? (
				<Card>
					<div className="ferr" style={{ padding: '18px 20px' }}>{parseServerError(error)}</div>
				</Card>
			) : (
				<div className="stack">
					<Card accent>
						<CHead
							icon="shield"
							title="Export incentives"
							count={d ? `${incentives.length}` : undefined}
							action={canIncNew ? <a href="#" onClick={(e) => { e.preventDefault(); setIncModal('new'); }}>New incentive</a> : undefined}
						/>
						{d && d.incentives.length > 0 && (
							<div style={{ padding: '12px 18px 0' }}>
								<FilterBar rows={incSearched} defs={INC_FILTERS} state={incFilter.state} onChange={incFilter.set} onClear={incFilter.clear} />
							</div>
						)}
						{isLoading ? (
							<div className="sub" style={{ padding: '14px 18px' }}>Loading…</div>
						) : !d || incentives.length === 0 ? (
							<EmptyMsg
								title={incFiltering ? 'No matching incentives' : 'No incentives yet'}
								text={incFiltering ? 'Try a different search or clear the filters.' : 'RoDTEP and drawback claims per shipment land here.'}
							/>
						) : (
							<table className={canIncEdit ? 'clickable' : undefined}>
								<thead>
									<tr><th>Scheme</th><th>Shipment</th><th>SB no</th><th>Amount</th><th>Scroll / scrip</th><th>Status</th></tr>
								</thead>
								<tbody>
									{incentives.map((i) => (
										<tr key={i.name} onClick={canIncEdit ? () => setIncModal(i) : undefined}>
											<td className="c1">{i.scheme}</td>
											<td>{i.shipment ? <span className="id id-sm">{i.shipment}</span> : <span className="dim">—</span>}</td>
											<td className="dim">{i.shipping_bill_no ?? '—'}</td>
											<td className="num">{inr(i.amount)}</td>
											<td className="dim">{i.scrip_number || i.scroll_number || '—'}</td>
											<td><Tag tone={incentiveTone(i.status)}>{i.status}</Tag></td>
										</tr>
									))}
								</tbody>
							</table>
						)}
					</Card>

					<Card accent>
						<CHead
							icon="banknote"
							title="Bank realization"
							count={d ? `${realizations.length}` : undefined}
							action={canRelNew ? <a href="#" onClick={(e) => { e.preventDefault(); setRelModal('new'); }}>New realization</a> : undefined}
						/>
						{d && d.realizations.length > 0 && (
							<div style={{ padding: '12px 18px 0' }}>
								<FilterBar rows={relSearched} defs={REAL_FILTERS} state={relFilter.state} onChange={relFilter.set} onClear={relFilter.clear} />
							</div>
						)}
						{isLoading ? (
							<div className="sub" style={{ padding: '14px 18px' }}>Loading…</div>
						) : !d || realizations.length === 0 ? (
							<EmptyMsg
								title={relFiltering ? 'No matching realizations' : 'No realizations yet'}
								text={relFiltering ? 'Try a different search or clear the filters.' : 'Export-proceeds tracking (FIRC, eBRC, due dates) appears here.'}
							/>
						) : (
							<table className={canRelEdit ? 'clickable' : undefined}>
								<thead>
									<tr><th>Invoice</th><th>Shipment</th><th>Received</th><th>Due</th><th>eBRC</th><th>Status</th></tr>
								</thead>
								<tbody>
									{realizations.map((r) => (
										<tr key={r.name} onClick={canRelEdit ? () => setRelModal(r) : undefined}>
											<td className="id">{r.export_invoice ?? r.name}</td>
											<td>{r.shipment ? <span className="id id-sm">{r.shipment}</span> : <span className="dim">—</span>}</td>
											<td className="num">{inr(r.amount_received_inr)}</td>
											<td className="dim">{r.due_date ? fmtDate(r.due_date) : '—'}</td>
											<td className="dim">{r.ebrc_number ?? '—'}</td>
											<td><Tag tone={realizationTone(r)}>{r.overdue && r.status !== 'Overdue' ? `Overdue · ${r.status}` : r.status}</Tag></td>
										</tr>
									))}
								</tbody>
							</table>
						)}
					</Card>

					{mttFiltered.length > 0 && (
						<Card accent>
							<CHead icon="globe" title="Third-country / merchanting" count={`${mttFiltered.length}`} />
							<table className="clickable">
								<thead>
									<tr>
										<th>Shipment</th>
										<th>Customer</th>
										<th>Completion due</th>
										<th>Outlay due</th>
										<th>Net FX (INR)</th>
										<th>Status</th>
									</tr>
								</thead>
								<tbody>
									{mttFiltered.map((t) => {
										const st = mttRowStatus(t);
										return (
											<tr key={t.shipment} onClick={() => navigate(`/shipments/${t.shipment}`)}>
												<td>
													<span className="id id-sm">{t.shipment}</span>
												</td>
												<td className="c1">{t.customer_name ?? '—'}</td>
												<td className="dim">
													{t.completed ? (
														<Tag tone="ok">done</Tag>
													) : t.completion_due ? (
														<>
															{fmtDate(t.completion_due)}{' '}
															{t.completion_days != null && (
																<Tag tone={urgencyTone(t.completion_days) ?? 'ok'}>
																	{urgencyLabel(t.completion_days)}
																</Tag>
															)}
														</>
													) : (
														'—'
													)}
												</td>
												<td className="dim">
													{!t.outlay_open ? (
														<span className="dim">—</span>
													) : t.outlay_due ? (
														<>
															{fmtDate(t.outlay_due)}{' '}
															{t.outlay_days != null && (
																<Tag tone={urgencyTone(t.outlay_days) ?? 'ok'}>
																	{urgencyLabel(t.outlay_days)}
																</Tag>
															)}
														</>
													) : (
														'—'
													)}
												</td>
												<td className="num">{t.net_fx_profit_inr == null ? '—' : inr(t.net_fx_profit_inr)}</td>
												<td>
													<Tag tone={st.tone}>{st.label}</Tag>
												</td>
											</tr>
										);
									})}
								</tbody>
							</table>
						</Card>
					)}
				</div>
			)}

			{incModal !== null && (
				<IncentiveModal
					record={incModal === 'new' ? null : incModal}
					canDelete={can?.incentive_delete}
					onClose={() => setIncModal(null)}
					onSaved={() => { setIncModal(null); mutate(); }}
					onDeleted={() => { setIncModal(null); mutate(); }}
				/>
			)}
			{relModal !== null && (
				<RealizationModal
					record={relModal === 'new' ? null : relModal}
					canDelete={can?.realization_delete}
					onClose={() => setRelModal(null)}
					onSaved={() => { setRelModal(null); mutate(); }}
					onDeleted={() => { setRelModal(null); mutate(); }}
				/>
			)}

			<footer><b>ExportFlow</b> · DUX Digitech</footer>
		</main>
	);
}
