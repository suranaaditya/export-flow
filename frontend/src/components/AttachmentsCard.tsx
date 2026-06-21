import { useRef, useState } from 'react';
import { useFrappeFileUpload, useFrappeGetCall, useFrappePostCall } from 'frappe-react-sdk';
import { Icon } from '@/components/Icon';
import { Card, CHead, EmptyMsg, LRow } from '@/components/ui';
import { API, parseServerError, type DocAttachment } from '@/lib/api';
import { fmtDate } from '@/lib/format';

function fmtSize(bytes: number): string {
	if (!bytes) return '';
	if (bytes < 1024) return `${bytes} B`;
	if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
	return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Multi-file attachments for a Sales/Purchase Order (feedback #17) — generic
 *  Frappe File rows keyed to the document; shared by both detail screens. */
export function AttachmentsCard({
	doctype,
	name,
	canWrite,
}: {
	doctype: 'Sales Order' | 'Purchase Order';
	name: string;
	canWrite: boolean;
}) {
	const { data, mutate, isLoading, error: listError } = useFrappeGetCall<{ message: DocAttachment[] }>(
		API.listDocAttachments,
		{ doctype, name },
	);
	const { upload, loading: uploading } = useFrappeFileUpload();
	const { call: removeAttachment } = useFrappePostCall(API.removeDocAttachment);
	const fileRef = useRef<HTMLInputElement>(null);
	const [err, setErr] = useState<string | null>(null);
	const files = data?.message ?? [];

	async function onUpload(file: File) {
		setErr(null);
		try {
			await upload(file, { doctype, docname: name, isPrivate: true });
			await mutate();
		} catch (e) {
			setErr(parseServerError(e));
		}
	}

	async function onRemove(fileUrl: string) {
		setErr(null);
		try {
			await removeAttachment({ doctype, name, file_url: fileUrl });
			await mutate();
		} catch (e) {
			setErr(parseServerError(e));
		}
	}

	return (
		<Card>
			<CHead
				icon="file-text"
				title="Attachments"
				count={files.length || undefined}
				action={
					canWrite ? (
						<a
							href="#"
							onClick={(e) => {
								e.preventDefault();
								fileRef.current?.click();
							}}
						>
							{uploading ? 'Uploading…' : 'Upload file'}
						</a>
					) : undefined
				}
			/>
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
			{err && (
				<div className="ferr" style={{ padding: '8px 18px' }}>
					{err}
				</div>
			)}
			{listError ? (
				<div className="ferr" style={{ padding: '14px 18px' }}>
					{parseServerError(listError)}
				</div>
			) : isLoading ? (
				<div className="sub" style={{ padding: '14px 18px' }}>
					Loading…
				</div>
			) : files.length === 0 ? (
				<EmptyMsg
					title="No files attached"
					text={
						canWrite ? 'Upload specifications or any reference documents for this order.' : undefined
					}
				/>
			) : (
				files.map((f) => (
					<LRow
						key={f.file_url}
						icon="file-text"
						t1={<span className="data">{f.file_name}</span>}
						t2={[fmtDate(f.creation), fmtSize(f.file_size)].filter(Boolean).join(' · ')}
						right={
							canWrite ? (
								<button
									type="button"
									className="xbtn"
									aria-label={`Remove ${f.file_name}`}
									onClick={(e) => {
										e.stopPropagation();
										void onRemove(f.file_url);
									}}
								>
									<Icon name="close" size={14} />
								</button>
							) : undefined
						}
						onClick={() => window.open(f.file_url, '_blank', 'noopener')}
					/>
				))
			)}
		</Card>
	);
}
