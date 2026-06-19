import { useMemo, useState } from 'react';
import { useFrappeGetCall } from 'frappe-react-sdk';
import { TextInput } from '@/components/form';
import { FilterBar, applyFilters, useFilterState, type FilterDef } from '@/components/FilterBar';
import { Card, CHead, EmptyMsg, Tag } from '@/components/ui';
import { API, parseServerError, type ReportColType, type ReportData } from '@/lib/api';
import { fmtDate } from '@/lib/format';

type Row = Record<string, string | number | boolean | null>;

function fmtCell(value: Row[string], type: ReportColType): string {
	if (value === null || value === undefined || value === '') return '—';
	if (type === 'inr')
		return '₹' + Number(value).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
	if (type === 'num')
		return Number(value).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
	if (type === 'pct') return `${value}%`;
	if (type === 'date') return fmtDate(String(value));
	if (type === 'days') {
		const d = Number(value);
		return d < 0 ? `${-d}d overdue` : d === 0 ? 'today' : `${d}d`;
	}
	return String(value);
}

// exact mapping (a substring test would mis-colour "Partially Realized" green and
// "Not Applicable" neutral) — kept in step with realizationTone/incentiveTone
const TAG_OK = ['realized', 'ebrc closed', 'completed', 'closed', 'credited', 'utilized', 'scrip generated'];
const TAG_ERR = ['overdue', 'clock breached', 'written off', 'cancelled', 'not applicable'];
function tagTone(status: string): 'ok' | 'pend' | 'err' {
	const s = status.toLowerCase().trim();
	if (TAG_OK.includes(s)) return 'ok';
	if (TAG_ERR.includes(s)) return 'err';
	return 'pend';
}

/** POST the on-screen (filtered) rows back to be formatted server-side — so the
 *  downloaded file always matches exactly what is on screen. */
async function downloadReport(report: string, fmt: 'xlsx' | 'pdf', rows: Row[]) {
	const res = await fetch('/api/method/exportflow.reports.report_export', {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			'X-Frappe-CSRF-Token': (window as unknown as { csrf_token?: string }).csrf_token ?? '',
		},
		body: JSON.stringify({ report, fmt, rows: JSON.stringify(rows) }),
	});
	if (!res.ok) throw new Error(`Export failed (${res.status})`);
	const blob = await res.blob();
	const url = URL.createObjectURL(blob);
	const a = document.createElement('a');
	a.href = url;
	a.download = `${report.replace(/_/g, '-')}-${new Date().toLocaleDateString('en-CA')}.${fmt}`;
	document.body.appendChild(a);
	a.click();
	a.remove();
	URL.revokeObjectURL(url);
}

export function ReportView({ report }: { report: string }) {
	const { data, error, isLoading } = useFrappeGetCall<{ message: ReportData }>(API.reportData, { report });
	const d = data?.message;
	const cols = useMemo(() => d?.columns ?? [], [d]);
	const allRows = useMemo(() => (d?.rows ?? []) as Row[], [d]);
	const idCol = cols.find((c) => c.type === 'id')?.key;

	const [from, setFrom] = useState('');
	const [to, setTo] = useState('');
	const { state, set, clear } = useFilterState();
	const [busy, setBusy] = useState<'xlsx' | 'pdf' | null>(null);
	const [exErr, setExErr] = useState<string | null>(null);

	const dateFilter = d?.filters.find((f) => f.control === 'daterange');
	const fieldFilters: FilterDef<Row>[] = useMemo(
		() =>
			(d?.filters ?? [])
				.filter((f) => f.control !== 'daterange')
				.map((f) => ({
					key: f.key,
					label: f.label,
					control: f.control as FilterDef<Row>['control'],
					get: (r) => r[f.field] as string | number | boolean,
				})),
		[d],
	);

	const rows = useMemo(() => {
		let rs = allRows;
		if (dateFilter && (from || to)) {
			rs = rs.filter((r) => {
				const v = r[dateFilter.field];
				if (!v) return false;
				const dd = String(v);
				if (from && dd < from) return false;
				if (to && dd > to) return false;
				return true;
			});
		}
		return applyFilters(rs, fieldFilters, state);
	}, [allRows, dateFilter, from, to, fieldFilters, state]);

	const totals = useMemo(() => {
		const t: Record<string, number> = {};
		for (const c of cols)
			if (c.type === 'inr') t[c.key] = rows.reduce((s, r) => s + (Number(r[c.key]) || 0), 0);
		return t;
	}, [cols, rows]);

	async function onExport(fmt: 'xlsx' | 'pdf') {
		setExErr(null);
		setBusy(fmt);
		try {
			await downloadReport(report, fmt, rows);
		} catch (e) {
			setExErr(parseServerError(e));
		} finally {
			setBusy(null);
		}
	}

	const anyFilter = !!(from || to) || fieldFilters.some((f) => state[f.key]);

	return (
		<Card accent>
			<CHead
				icon="filter"
				title={d?.title ?? 'Report'}
				count={d ? `${rows.length} of ${allRows.length}` : undefined}
				action={
					rows.length ? (
						<span style={{ display: 'flex', gap: 14 }}>
							<a href="#" onClick={(e) => { e.preventDefault(); if (!busy) void onExport('xlsx'); }}>
								{busy === 'xlsx' ? 'Exporting…' : 'Excel'}
							</a>
							<a href="#" onClick={(e) => { e.preventDefault(); if (!busy) void onExport('pdf'); }}>
								{busy === 'pdf' ? 'Exporting…' : 'PDF'}
							</a>
						</span>
					) : undefined
				}
			/>
			{isLoading ? (
				<div className="sub" style={{ padding: '14px 18px' }}>Loading…</div>
			) : error ? (
				<div className="ferr" style={{ padding: '14px 18px' }}>{parseServerError(error)}</div>
			) : (
				<>
					<div className="repfilters">
						{dateFilter && (
							<div className="repdates">
								<span className="repdlb">{dateFilter.label}</span>
								<div className="field" style={{ width: 150 }}>
									<TextInput type="date" value={from} onChange={setFrom} />
								</div>
								<span className="dim">→</span>
								<div className="field" style={{ width: 150 }}>
									<TextInput type="date" value={to} onChange={setTo} />
								</div>
								{(from || to) && (
									<button type="button" className="fclear" onClick={() => { setFrom(''); setTo(''); }}>
										reset
									</button>
								)}
							</div>
						)}
						<FilterBar rows={allRows} defs={fieldFilters} state={state} onChange={set} onClear={clear} />
					</div>
					{exErr && <div className="ferr" style={{ padding: '0 18px 8px' }}>{exErr}</div>}
					{rows.length === 0 ? (
						<EmptyMsg
							title={anyFilter ? 'No matching rows' : 'Nothing here yet'}
							text={anyFilter ? 'Try a different date range or clear the filters.' : 'Records appear here as they are entered.'}
						/>
					) : (
						<div className="reptable">
							<table>
								<thead>
									<tr>
										{cols.map((c) => (
											<th key={c.key} className={c.type}>{c.label}</th>
										))}
									</tr>
								</thead>
								<tbody>
									{rows.map((r, i) => (
										<tr key={idCol && r[idCol] != null ? `${r[idCol]}-${i}` : i}>
											{cols.map((c) => (
												<td key={c.key} className={c.type}>
													{c.type === 'tag' ? (
														<Tag tone={tagTone(String(r[c.key] ?? ''))}>{String(r[c.key] ?? '—')}</Tag>
													) : c.type === 'id' ? (
														<span className="id id-sm">{r[c.key] ?? '—'}</span>
													) : c.type === 'days' && r[c.key] != null && Number(r[c.key]) < 0 ? (
														<span style={{ color: 'var(--err)', fontWeight: 500 }}>{fmtCell(r[c.key], c.type)}</span>
													) : (
														fmtCell(r[c.key], c.type)
													)}
												</td>
											))}
										</tr>
									))}
									<tr className="reptot">
										{cols.map((c, i) => (
											<td key={c.key} className={c.key in totals ? c.type : ''}>
												{c.key in totals ? fmtCell(totals[c.key], 'inr') : i === 0 ? 'Total' : ''}
											</td>
										))}
									</tr>
								</tbody>
							</table>
						</div>
					)}
				</>
			)}
		</Card>
	);
}
