import { useRef, useState } from 'react';
import { useFrappeFileUpload, useFrappeGetCall, useFrappePostCall } from 'frappe-react-sdk';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Icon } from '@/components/Icon';
import { SearchSelect } from '@/components/form';
import { Card, CHead, EmptyMsg, Facts, Tag } from '@/components/ui';
import { API, parseServerError, type GRNDetailData } from '@/lib/api';
import { fmtDateLong } from '@/lib/format';

const STATUS_TONE: Record<string, 'ok' | 'pend' | 'err'> = {
	Draft: 'pend',
	Received: 'ok',
	Cancelled: 'err',
};

export function GoodsReceiptNoteDetail() {
	const { id = '' } = useParams<{ id: string }>();
	const navigate = useNavigate();
	const { data, error, isLoading, mutate } = useFrappeGetCall<{ message: GRNDetailData }>(
		API.grnDetail,
		{ name: id },
	);
	const { call: submitGrn, loading: receiving } = useFrappePostCall(API.submitGrn);
	const { call: cancelGrn, loading: cancelling } = useFrappePostCall(API.cancelGrn);
	const { call: attachInvoice } = useFrappePostCall(API.attachGrnInvoice);
	const { call: addDocument, loading: addingDoc } = useFrappePostCall(API.addGrnDocument);
	const { call: removeDocument } = useFrappePostCall(API.removeGrnDocument);
	const { data: docTypesData } = useFrappeGetCall<{ message: { name: string; category: string | null }[] }>(
		API.supplierDocTypes,
		undefined,
	);
	const { upload, loading: uploading } = useFrappeFileUpload();
	const [actionErr, setActionErr] = useState<string | null>(null);
	const [docType, setDocType] = useState('');
	const fileRef = useRef<HTMLInputElement | null>(null);
	const docFileRef = useRef<HTMLInputElement | null>(null);
	const docTypeOptions = (docTypesData?.message ?? []).map((t) => ({
		value: t.name,
		label: t.name,
		sub: t.category ?? undefined,
	}));

	async function onReceive() {
		setActionErr(null);
		try {
			await submitGrn({ name: id });
			await mutate();
		} catch (e) {
			setActionErr(parseServerError(e));
		}
	}

	async function onCancel() {
		setActionErr(null);
		try {
			await cancelGrn({ name: id });
			await mutate();
		} catch (e) {
			setActionErr(parseServerError(e));
		}
	}

	async function onUpload(file: File) {
		setActionErr(null);
		try {
			const res = await upload(file, {
				doctype: 'Goods Receipt Note',
				docname: id,
				fieldname: 'supplier_invoice_file',
				isPrivate: true,
			});
			await attachInvoice({ name: id, file_url: res.file_url });
			await mutate();
		} catch (e) {
			setActionErr(parseServerError(e));
		}
	}

	async function onAddDocument(file: File) {
		setActionErr(null);
		try {
			const res = await upload(file, {
				doctype: 'Goods Receipt Note',
				docname: id,
				fieldname: 'documents',
				isPrivate: true,
			});
			await addDocument({ name: id, document_type: docType, file_url: res.file_url });
			setDocType('');
			await mutate();
		} catch (e) {
			setActionErr(parseServerError(e));
		}
	}

	async function onRemoveDocument(row: string) {
		setActionErr(null);
		try {
			await removeDocument({ name: id, row });
			await mutate();
		} catch (e) {
			setActionErr(parseServerError(e));
		}
	}

	if (isLoading) {
		return (
			<main className="tight">
				<div className="eyebrow">Buying · Goods receipt</div>
				<div className="sub" style={{ marginTop: 14 }}>Loading…</div>
			</main>
		);
	}
	const d = data?.message;
	if (error || !d) {
		return (
			<main className="tight">
				<div className="crumb">
					<Link to="/grns">Goods receipts</Link> / <span className="data">{id}</span>
				</div>
				<div style={{ marginTop: 22 }}>
					<Card>
						<div className="ferr" style={{ padding: '18px 20px' }}>
							This goods receipt could not be loaded.{' '}
							{error ? parseServerError(error) : ''}
						</div>
					</Card>
				</div>
			</main>
		);
	}

	const { grn, items, packs, documents, can } = d;

	return (
		<main className="tight">
			<div className="eyebrow">Buying · Goods receipt</div>
			<div className="crumb" style={{ marginTop: 6 }}>
				<Link to="/grns">Goods receipts</Link> / <span className="data">{grn.name}</span>
			</div>

			<div className="titlebar">
				<h1>{grn.name}</h1>
				<span className="who">· {grn.supplier_name}</span>
				<span style={{ marginTop: 9, display: 'inline-flex', gap: 6 }}>
					<Tag tone={STATUS_TONE[grn.status] ?? 'pend'}>{grn.status}</Tag>
				</span>
				<span className="spacer" />
				{can.edit && (
					<button className="btn" onClick={() => navigate('/grns/' + id + '/edit')}>
						<Icon name="file-text" size={15} /> Edit
					</button>
				)}
				{can.cancel && (
					<button className="btn" disabled={cancelling} onClick={() => void onCancel()}>
						<Icon name="close" size={15} /> {cancelling ? 'Cancelling…' : 'Cancel receipt'}
					</button>
				)}
				{can.receive && (
					<button className="btn primary" disabled={receiving} onClick={() => void onReceive()}>
						<Icon name="check" size={15} /> {receiving ? 'Receiving…' : 'Receive goods'}
					</button>
				)}
			</div>

			{actionErr && <div className="ferr" style={{ marginBottom: 10 }}>{actionErr}</div>}

			<div className="metaline">
				<span className="kv">
					<b>Purchase order</b>
					<Link className="data" to={'/purchases/' + grn.purchase_order}>
						{grn.purchase_order}
					</Link>
				</span>
				<span className="kv">
					<b>Warehouse</b>
					<span className="data">{grn.warehouse}</span>
				</span>
				<span className="kv">
					<b>Received</b>
					<span className="data">{fmtDateLong(grn.posting_date)}</span>
				</span>
			</div>

			<div className="grid detail">
				<div className="stack">
					<Card accent>
						<CHead icon="cube" title="Received items" count={`${items.length} lines`} />
						<table>
							<thead>
								<tr>
									<th>Item</th>
									<th>Ordered</th>
									<th>Received</th>
								</tr>
							</thead>
							<tbody>
								{items.map((it) => (
									<tr key={it.name}>
										<td>
											<div className="c1">{it.item_name}</div>
											<div className="c2">{it.item_code}</div>
										</td>
										<td className="num">{it.ordered_qty || <span className="dim">—</span>}</td>
										<td className="num">
											{it.received_qty} {it.uom ? <span className="dim">{it.uom}</span> : null}
										</td>
									</tr>
								))}
							</tbody>
						</table>
					</Card>

					<Card>
						<CHead icon="copy" title="Pack & batch detail" count={packs.length || undefined} />
						{packs.length === 0 ? (
							<EmptyMsg title="No pack detail" text="Batches recorded here forward to the shipment." />
						) : (
							<table>
								<thead>
									<tr>
										<th>Item</th>
										<th>Batch</th>
										<th>Pkgs</th>
										<th>Pack type</th>
										<th>Mfg</th>
										<th>Exp</th>
									</tr>
								</thead>
								<tbody>
									{packs.map((p, i) => (
										<tr key={p.name ?? i}>
											<td>{p.item_code}</td>
											<td className="id">{p.batch_no || '—'}</td>
											<td className="num">{p.num_packages ?? '—'}</td>
											<td>{p.pack_type || '—'}</td>
											<td>{fmtDateLong(p.mfg_date)}</td>
											<td>{fmtDateLong(p.exp_date)}</td>
										</tr>
									))}
								</tbody>
							</table>
						)}
					</Card>
				</div>

				<div className="stack">
					<Card>
						<CHead icon="file-text" title="Supplier invoice" />
						<Facts
							rows={[
								{ k: 'Invoice no', v: grn.supplier_invoice_no ?? '—', data: true },
								{ k: 'Invoice date', v: fmtDateLong(grn.supplier_invoice_date), data: true },
								{
									k: 'File',
									v: grn.supplier_invoice_file ? (
										<a className="data" href={grn.supplier_invoice_file} target="_blank" rel="noreferrer">
											View file
										</a>
									) : (
										<span className="dim">not uploaded</span>
									),
								},
							]}
						/>
						<div style={{ padding: '4px 18px 16px' }}>
							<input
								ref={fileRef}
								type="file"
								style={{ display: 'none' }}
								onChange={(e) => {
									const f = e.target.files?.[0];
									if (f) void onUpload(f);
									e.target.value = '';
								}}
							/>
							<button className="btn" disabled={uploading} onClick={() => fileRef.current?.click()}>
								<Icon name="upload" size={15} /> {uploading ? 'Uploading…' : 'Upload invoice'}
							</button>
						</div>
					</Card>

					<Card>
						<CHead icon="copy" title="Supplier documents" count={documents.length || undefined} />
						<div style={{ padding: '6px 18px 16px' }}>
							<div className="sub" style={{ marginBottom: documents.length ? 10 : 6 }}>
								Certificate of analysis, MSDS, test certificates… attach what the supplier provides.
								Each one auto-fills the matching document on the shipment — uploaded once, never twice.
							</div>
							{documents.map((doc) => (
								<div
									key={doc.name}
									style={{
										display: 'flex',
										alignItems: 'center',
										gap: 8,
										padding: '8px 0',
										borderTop: '1px solid var(--hairline)',
									}}
								>
									<Icon name="file-text" size={15} />
									<span style={{ flex: 1 }}>
										<span className="c1">{doc.document_type}</span>
										<a className="data" href={doc.file} target="_blank" rel="noreferrer" style={{ display: 'block', fontSize: 12 }}>
											View file
										</a>
									</span>
									<button
										className="xbtn"
										aria-label="Remove document"
										onClick={() => void onRemoveDocument(doc.name)}
									>
										<Icon name="close" size={13} />
									</button>
								</div>
							))}
							<input
								ref={docFileRef}
								type="file"
								style={{ display: 'none' }}
								onChange={(e) => {
									const f = e.target.files?.[0];
									if (f) void onAddDocument(f);
									e.target.value = '';
								}}
							/>
							<div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
								<div style={{ flex: 1 }}>
									<SearchSelect
										value={docType}
										onChange={setDocType}
										options={docTypeOptions}
										placeholder="Document type, e.g. Certificate of Analysis"
									/>
								</div>
								<button
									className="btn"
									disabled={!docType || addingDoc || uploading}
									onClick={() => docFileRef.current?.click()}
								>
									<Icon name="upload" size={15} /> {addingDoc ? 'Adding…' : 'Add file'}
								</button>
							</div>
						</div>
					</Card>

					{grn.remarks && (
						<Card>
							<CHead icon="file-text" title="Remarks" />
							<div className="c2" style={{ padding: '12px 18px', whiteSpace: 'pre-wrap' }}>
								{grn.remarks}
							</div>
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
