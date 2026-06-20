import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useFrappeGetCall } from 'frappe-react-sdk';
import { TextInput } from '@/components/form';
import { FilterBar, applyFilters, useFilterState, type FilterDef } from '@/components/FilterBar';
import { Icon } from '@/components/Icon';
import { Card, CHead, EmptyMsg, Tag } from '@/components/ui';
import { API, parseServerError, type ReportColType, type ReportColumn, type ReportData } from '@/lib/api';
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

/** POST the on-screen (filtered) rows + the chosen columns + the active-filter
 *  summary back to be formatted server-side — so the downloaded file matches
 *  exactly what is on screen, including which columns are shown. */
async function downloadReport(
	report: string,
	fmt: 'xlsx' | 'pdf',
	rows: Row[],
	columns: string[],
	subtitle: string,
) {
	const res = await fetch('/api/method/exportflow.reports.report_export', {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			'X-Frappe-CSRF-Token': (window as unknown as { csrf_token?: string }).csrf_token ?? '',
		},
		body: JSON.stringify({
			report,
			fmt,
			rows: JSON.stringify(rows),
			columns: JSON.stringify(columns),
			subtitle,
		}),
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
	const allKeys = useMemo(() => cols.map((c) => c.key), [cols]);

	const [from, setFrom] = useState('');
	const [to, setTo] = useState('');
	const { state, set, clear } = useFilterState();
	const [busy, setBusy] = useState<'xlsx' | 'pdf' | null>(null);
	const [exErr, setExErr] = useState<string | null>(null);

	// which columns are shown on screen and sent to the export (default: all,
	// remembered per report in localStorage)
	const [visible, setVisible] = useState<string[]>([]);
	const [colMenu, setColMenu] = useState(false);
	const [colSearch, setColSearch] = useState('');
	const [menuPos, setMenuPos] = useState<{ top?: number; bottom?: number; right: number; maxH: number }>();
	const btnRef = useRef<HTMLButtonElement>(null);
	const menuElRef = useRef<HTMLDivElement>(null);
	const storeKey = `efx:reportcols:${report}`;

	// the menu is portaled to <body> (a .card clips overflow), so position it from
	// the button rect — drop below, or flip above when the button sits low
	function openMenu() {
		const el = btnRef.current;
		if (!el) return;
		const r = el.getBoundingClientRect();
		const below = window.innerHeight - r.bottom - 12;
		const above = r.top - 12;
		const right = Math.max(8, window.innerWidth - r.right);
		if (below < 220 && above > below) setMenuPos({ bottom: window.innerHeight - r.top + 6, right, maxH: above });
		else setMenuPos({ top: r.bottom + 6, right, maxH: below });
		setColSearch('');
		setColMenu(true);
	}

	useEffect(() => {
		if (!allKeys.length) return;
		let init = allKeys;
		try {
			const raw = localStorage.getItem(storeKey);
			if (raw) {
				const saved = JSON.parse(raw) as string[];
				const keep = allKeys.filter((k) => saved.includes(k));
				if (keep.length) init = keep;
			}
		} catch {
			/* ignore unreadable storage */
		}
		setVisible(init);
	}, [allKeys, storeKey]);

	useEffect(() => {
		if (!colMenu) return;
		const onDown = (e: MouseEvent) => {
			const t = e.target as Node;
			if (btnRef.current?.contains(t) || menuElRef.current?.contains(t)) return;
			setColMenu(false);
		};
		// close on PAGE scroll/resize, but not when scrolling inside the menu's own list
		const onLeave = (e: Event) => {
			if (menuElRef.current?.contains(e.target as Node)) return;
			setColMenu(false);
		};
		document.addEventListener('mousedown', onDown);
		window.addEventListener('scroll', onLeave, true);
		window.addEventListener('resize', onLeave);
		return () => {
			document.removeEventListener('mousedown', onDown);
			window.removeEventListener('scroll', onLeave, true);
			window.removeEventListener('resize', onLeave);
		};
	}, [colMenu]);

	const shownCols = useMemo<ReportColumn[]>(() => {
		if (!visible.length) return cols; // before seeding, show everything
		const s = new Set(visible);
		return cols.filter((c) => s.has(c.key));
	}, [cols, visible]);
	const shownKeys = useMemo(() => new Set(shownCols.map((c) => c.key)), [shownCols]);
	const idCol = shownCols.find((c) => c.type === 'id')?.key;

	function persist(next: string[]) {
		try {
			localStorage.setItem(storeKey, JSON.stringify(next));
		} catch {
			/* ignore */
		}
	}
	function setShown(next: string[]) {
		const ordered = allKeys.filter((k) => next.includes(k));
		setVisible(ordered);
		persist(ordered);
	}
	function toggleCol(key: string) {
		const cur = shownCols.map((c) => c.key);
		const has = cur.includes(key);
		if (has && cur.length === 1) return; // keep at least one column
		setShown(has ? cur.filter((k) => k !== key) : [...cur, key]);
	}

	// filter the picker list by label so the long registers (the MIS workbook has 78
	// columns) stay navigable; the header action then targets the matching subset
	const searchActive = colSearch.trim().length > 0;
	const menuCols = useMemo(() => {
		const q = colSearch.trim().toLowerCase();
		return q ? cols.filter((c) => c.label.toLowerCase().includes(q)) : cols;
	}, [cols, colSearch]);
	function selectAllOrShown() {
		if (searchActive) setShown([...shownCols.map((c) => c.key), ...menuCols.map((c) => c.key)]);
		else setShown(allKeys);
	}
	const selectAllDisabled = searchActive
		? menuCols.length === 0 || menuCols.every((c) => shownKeys.has(c.key))
		: shownCols.length === cols.length;

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
		for (const c of shownCols)
			if (c.type === 'inr') t[c.key] = rows.reduce((s, r) => s + (Number(r[c.key]) || 0), 0);
		return t;
	}, [shownCols, rows]);
	// the "Total" caption goes on the first non-money column (keying it to index 0
	// would lose it when the leading shown column is itself a money column)
	const totalLabelIdx = shownCols.findIndex((c) => !(c.key in totals));

	// human summary of the active filters — stamped under the PDF title so the
	// exported file documents which slice of data produced it
	const filterSummary = useMemo(() => {
		const parts: string[] = [];
		if (dateFilter && (from || to)) {
			const lbl = dateFilter.label;
			if (from && to) parts.push(`${lbl} ${fmtDate(from)} – ${fmtDate(to)}`);
			else if (from) parts.push(`${lbl} from ${fmtDate(from)}`);
			else parts.push(`${lbl} until ${fmtDate(to)}`);
		}
		for (const f of fieldFilters) {
			const v = state[f.key];
			if (!v) continue;
			parts.push(f.control === 'toggle' ? f.label : `${f.label}: ${v}`);
		}
		return parts.join(' · ');
	}, [dateFilter, from, to, fieldFilters, state]);

	async function onExport(fmt: 'xlsx' | 'pdf') {
		setExErr(null);
		setBusy(fmt);
		try {
			await downloadReport(report, fmt, rows, shownCols.map((c) => c.key), filterSummary);
		} catch (e) {
			setExErr(parseServerError(e));
		} finally {
			setBusy(null);
		}
	}

	const anyFilter = !!(from || to) || fieldFilters.some((f) => state[f.key]);

	const toolbar = (
		<div className="rptactions">
			<div className="colpick">
				<button
					ref={btnRef}
					type="button"
					className="cpbtn"
					aria-expanded={colMenu}
					onClick={() => (colMenu ? setColMenu(false) : openMenu())}
				>
					<Icon name="sliders" size={14} />
					Columns <span className="cpc">{shownCols.length}/{cols.length}</span>
					<Icon name="chevron" size={11} />
				</button>
				{colMenu && menuPos &&
					createPortal(
						<div
							className="colmenu"
							role="menu"
							ref={menuElRef}
							style={{ top: menuPos.top, bottom: menuPos.bottom, right: menuPos.right, maxHeight: menuPos.maxH }}
						>
							<div className="cmhd">
								<span>Columns <span className="cmcount">{shownCols.length}/{cols.length}</span></span>
								<button type="button" onClick={selectAllOrShown} disabled={selectAllDisabled}>
									{searchActive ? 'Select shown' : 'Select all'}
								</button>
							</div>
							<div className="cmsearch">
								<Icon name="search" size={13} />
								<input
									autoFocus
									type="text"
									value={colSearch}
									placeholder="Filter columns…"
									onChange={(e) => setColSearch(e.target.value)}
								/>
								{searchActive && (
									<button type="button" className="cmclear" onClick={() => setColSearch('')} aria-label="Clear filter">
										<Icon name="close" size={12} />
									</button>
								)}
							</div>
							<div className="cmlist">
								{menuCols.length === 0 ? (
									<div className="cmempty">No columns match “{colSearch.trim()}”</div>
								) : (
									menuCols.map((c) => {
									const on = shownKeys.has(c.key);
									return (
										<label key={c.key} className="cmrow">
											<input
												type="checkbox"
												checked={on}
												disabled={on && shownCols.length === 1}
												onChange={() => toggleCol(c.key)}
											/>
											<span>{c.label}</span>
										</label>
									);
									})
								)}
							</div>
						</div>,
						document.body,
					)}
			</div>
			{rows.length ? (
				<span className="rptexp">
					<a href="#" onClick={(e) => { e.preventDefault(); if (!busy) void onExport('xlsx'); }}>
						{busy === 'xlsx' ? 'Exporting…' : 'Excel'}
					</a>
					<a href="#" onClick={(e) => { e.preventDefault(); if (!busy) void onExport('pdf'); }}>
						{busy === 'pdf' ? 'Exporting…' : 'PDF'}
					</a>
				</span>
			) : null}
		</div>
	);

	return (
		<Card accent>
			<CHead
				icon="filter"
				title={d?.title ?? 'Report'}
				count={d ? `${rows.length} of ${allRows.length}` : undefined}
				action={d ? toolbar : undefined}
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
										{shownCols.map((c) => (
											<th key={c.key} className={c.type}>{c.label}</th>
										))}
									</tr>
								</thead>
								<tbody>
									{rows.map((r, i) => (
										<tr key={idCol && r[idCol] != null ? `${r[idCol]}-${i}` : i}>
											{shownCols.map((c) => (
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
									{d?.totals !== false && Object.keys(totals).length > 0 && (
										<tr className="reptot">
											{shownCols.map((c, i) => (
												<td key={c.key} className={c.key in totals ? c.type : ''}>
													{c.key in totals ? fmtCell(totals[c.key], 'inr') : i === totalLabelIdx ? 'Total' : ''}
												</td>
											))}
										</tr>
									)}
								</tbody>
							</table>
						</div>
					)}
				</>
			)}
		</Card>
	);
}
