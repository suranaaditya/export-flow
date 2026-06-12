import { useState } from 'react';
import { useFrappeGetCall, useFrappePostCall } from 'frappe-react-sdk';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Icon } from '@/components/Icon';
import { Card, CHead, EmptyMsg, Facts, LRow, Tag } from '@/components/ui';
import {
	API,
	lcIsOpen,
	lcTone,
	parseServerError,
	pfiTone,
	soTone,
	urgencyTone,
	type SOMoneySummary,
} from '@/lib/api';
import { daysUntil, fmtDate, fmtDateLong, fmtMoney } from '@/lib/format';

/** " · "-joined fragments, skipping empty/null parts. */
function dotJoin(parts: (string | null | undefined)[]): string {
	return parts.filter(Boolean).join(' · ');
}

export function SalesOrderDetail() {
	const { id = '' } = useParams<{ id: string }>();
	const navigate = useNavigate();

	const { data, error, isLoading, mutate } = useFrappeGetCall<{ message: SOMoneySummary }>(
		API.soMoneySummary,
		{ sales_order: id },
	);
	const { call: submitSo, loading: submitting } = useFrappePostCall(API.submitSo);
	const [actionErr, setActionErr] = useState<string | null>(null);

	async function onSubmitOrder() {
		setActionErr(null);
		try {
			await submitSo({ name: id });
			mutate();
		} catch (e) {
			setActionErr(parseServerError(e));
		}
	}

	if (isLoading) {
		return (
			<main className="tight">
				<div className="eyebrow">Selling · Sales order</div>
				<div className="crumb" style={{ marginTop: 6 }}>
					<Link to="/sales-orders">Sales orders</Link> / <span className="data">{id}</span>
				</div>
				<div className="sub" style={{ marginTop: 14 }}>
					Loading…
				</div>
			</main>
		);
	}

	const detail = data?.message;
	if (error || !detail) {
		return (
			<main className="tight">
				<div className="crumb">
					<Link to="/sales-orders">Sales orders</Link> / <span className="data">{id}</span>
				</div>
				<div className="eyebrow" style={{ marginTop: 18 }}>Selling</div>
				<h1>
					Sales <em>order</em>
				</h1>
				<div style={{ marginTop: 22 }}>
					<Card>
						<div className="ferr" style={{ padding: '18px 20px' }}>
							This sales order could not be loaded. It may not exist, or you may not have
							permission to view it.
						</div>
					</Card>
				</div>
				<footer>
					<b>ExportFlow</b> · DUX Digitech
				</footer>
			</main>
		);
	}

	const { so, pfis, lcs, summary } = detail;

	return (
		<main className="tight">
			<div className="eyebrow">Selling · Sales order</div>
			<div className="crumb" style={{ marginTop: 6 }}>
				<Link to="/sales-orders">Sales orders</Link> / <span className="data">{id}</span>
			</div>

			<div className="titlebar">
				<h1>{so.name}</h1>
				<span className="who">· {so.customer_name}</span>
				<span style={{ marginTop: 9 }}>
					<Tag tone={soTone(so.status)}>{so.status}</Tag>
				</span>
				<span className="spacer" />
				{so.docstatus === 0 ? (
					<button className="btn primary" disabled={submitting} onClick={() => void onSubmitOrder()}>
						<Icon name="check" size={15} /> {submitting ? 'Submitting…' : 'Submit order'}
					</button>
				) : (
					<>
						<button className="btn" onClick={() => navigate('/lc/new?so=' + id)}>
							<Icon name="calendar" size={15} /> New letter of credit
						</button>
						<button className="btn primary" onClick={() => navigate('/pfi/new?so=' + id)}>
							<Icon name="banknote" size={15} /> New pro forma
						</button>
					</>
				)}
			</div>
			{actionErr && (
				<div className="ferr" style={{ marginBottom: 10 }}>
					{actionErr}
				</div>
			)}

			<div className="metaline">
				<span className="kv">
					<b>Date</b>
					<span className="data">{fmtDateLong(so.transaction_date)}</span>
				</span>
				<span className="kv">
					<b>Incoterm</b>
					{[so.incoterm, so.named_place].filter(Boolean).join(' ') || '—'}
				</span>
				<span className="kv">
					<b>Currency</b>
					<span className="data">{so.currency}</span>
				</span>
				{so.payment_terms_narrative && (
					<span className="kv">
						<b>Payment terms</b>
						{so.payment_terms_narrative}
					</span>
				)}
			</div>

			<div className="grid detail">
				<div className="stack">
					<Card accent>
						<CHead icon="banknote" title="Money" count={so.currency} />
						<Facts
							rows={[
								{ k: 'SO value', v: fmtMoney(summary.so_value, so.currency), data: true },
								{ k: 'PFI raised', v: fmtMoney(summary.raised, so.currency), data: true },
								{ k: 'Received', v: fmtMoney(summary.received, so.currency), data: true },
								{ k: 'Balance', v: fmtMoney(summary.balance, so.currency), data: true },
							]}
						/>
					</Card>

					<Card>
						<CHead
							icon="file-text"
							title="Pro forma invoices"
							count={pfis.length}
							action={so.docstatus === 1 ? <Link to={'/pfi/new?so=' + id}>New</Link> : undefined}
						/>
						{pfis.length === 0 ? (
							<EmptyMsg
								title="No pro forma invoices yet"
								text={
									so.docstatus === 0
										? 'Submit the order first — PFIs are raised against submitted deals.'
										: 'Raise the first PFI against this order to start collecting payment.'
								}
							/>
						) : (
							pfis.map((p) => (
								<LRow
									key={p.name}
									icon="banknote"
									t1={<span className="data">{p.name}</span>}
									t2={dotJoin([p.stage_description, p.expected_payment_method, fmtDate(p.pfi_date)])}
									right={
										<>
											<span className="num">{fmtMoney(p.amount, p.currency)}</span>
											<div style={{ marginTop: 3 }}>
												<Tag tone={pfiTone(p.status)}>{p.status}</Tag>
											</div>
										</>
									}
									onClick={() => navigate('/pfi/' + p.name)}
								/>
							))
						)}
					</Card>
				</div>

				<div className="stack">
					<Card>
						<CHead
							icon="calendar"
							title="Letters of credit"
							count={lcs.length}
							action={so.docstatus === 1 ? <Link to={'/lc/new?so=' + id}>New</Link> : undefined}
						/>
						{lcs.length === 0 ? (
							<EmptyMsg
								title="No letters of credit"
								text={
									so.docstatus === 0
										? 'Submit the order first — LCs are recorded against submitted deals.'
										: 'Record an LC here when the buyer’s bank issues one for this order.'
								}
							/>
						) : (
							lcs.map((lc) => {
								// the ship-by alarm only makes sense while the LC is open
								const days = daysUntil(lc.latest_shipment_date);
								const shipTone = lcIsOpen(lc.status) ? urgencyTone(days) : null;
								return (
									<LRow
										key={lc.name}
										icon="calendar"
										t1={<span className="data">{lc.lc_number}</span>}
										t2={dotJoin([lc.issuing_bank, `Expiry ${fmtDate(lc.expiry_date)}`])}
										right={
											shipTone ? (
												<Tag tone={shipTone}>Ship by {fmtDate(lc.latest_shipment_date)}</Tag>
											) : (
												<Tag tone={lcTone(lc.status)}>{lc.status}</Tag>
											)
										}
										onClick={() => navigate('/lc/' + lc.name)}
									/>
								);
							})
						)}
					</Card>
				</div>
			</div>

			<footer>
				<b>ExportFlow</b> · DUX Digitech
			</footer>
		</main>
	);
}
