import { useEffect, useState } from 'react';
import { useFrappePostCall } from 'frappe-react-sdk';
import { CheckInput, Field, TextArea, TextInput } from '@/components/form';
import { Icon } from '@/components/Icon';
import { Modal } from '@/components/ui';
import { API, parseServerError, type EmailContext } from '@/lib/api';

/** AI-assisted email composer: resolves the recipient, drafts subject+body with the
 *  self-hosted model, attaches the document PDF, and sends (dev → sandbox). */
export function EmailComposer({
	doctype,
	name,
	purpose,
	title,
	onClose,
}: {
	doctype: string;
	name: string;
	purpose: string;
	title: string;
	onClose: () => void;
}) {
	const { call: ctxCall } = useFrappePostCall<{ message: EmailContext }>(API.emailContext);
	const { call: draftCall } = useFrappePostCall<{ message: { subject: string; body: string } }>(API.emailDraft);
	const { call: sendCall } = useFrappePostCall<{
		message: { sent_to: string[]; sandbox: boolean; intended: string };
	}>(API.emailSend);

	const [loading, setLoading] = useState(true);
	const [drafting, setDrafting] = useState(false);
	const [sending, setSending] = useState(false);
	const [err, setErr] = useState<string | null>(null);
	const [sent, setSent] = useState<string | null>(null);

	const [to, setTo] = useState('');
	const [cc, setCc] = useState('');
	const [subject, setSubject] = useState('');
	const [body, setBody] = useState('');
	const [attach, setAttach] = useState(true);
	const [attachLabel, setAttachLabel] = useState('');
	const [toName, setToName] = useState('');
	const [sandbox, setSandbox] = useState<string | null>(null);

	useEffect(() => {
		let alive = true;
		(async () => {
			try {
				const r = await ctxCall({ doctype, name, purpose });
				if (!alive) return;
				const m = r.message;
				setTo(m.to ?? '');
				setToName(m.to_name ?? '');
				setAttachLabel(m.attachment_label ?? '');
				setSandbox(m.sandbox ?? null);
				setLoading(false);
				void runDraft();
			} catch (e) {
				if (alive) {
					setErr(parseServerError(e));
					setLoading(false);
				}
			}
		})();
		return () => {
			alive = false;
		};
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, []);

	async function runDraft() {
		setDrafting(true);
		setErr(null);
		try {
			const r = await draftCall({ doctype, name, purpose });
			setSubject(r.message.subject);
			setBody(r.message.body);
		} catch (e) {
			setErr(parseServerError(e));
		} finally {
			setDrafting(false);
		}
	}

	async function runSend() {
		setSending(true);
		setErr(null);
		try {
			const r = await sendCall({ doctype, name, purpose, to, cc, subject, body, attach_pdf: attach ? 1 : 0 });
			const m = r.message;
			setSent(
				m.sandbox
					? `Sent to the sandbox (${m.sent_to.join(', ')}) — intended for ${m.intended}.`
					: `Sent to ${m.sent_to.join(', ')}.`,
			);
		} catch (e) {
			setErr(parseServerError(e));
		} finally {
			setSending(false);
		}
	}

	return (
		<Modal title={title} icon="send" onClose={onClose}>
			{loading ? (
				<div className="sub" style={{ padding: 10 }}>Loading…</div>
			) : sent ? (
				<div className="emdone">
					<Icon name="check" size={32} />
					<p>{sent}</p>
					<button type="button" className="btn primary" onClick={onClose}>Done</button>
				</div>
			) : (
				<div className="emform">
					{sandbox && (
						<div className="embanner">
							<Icon name="shield" size={14} /> Dev sandbox is on — this will be sent to <b>{sandbox}</b>, not the
							real recipient.
						</div>
					)}
					<Field label="To" required hint={toName && !to ? `${toName} — no email on file, enter one` : toName || undefined}>
						<TextInput value={to} onChange={setTo} placeholder="recipient@example.com" />
					</Field>
					<Field label="Cc">
						<TextInput value={cc} onChange={setCc} placeholder="optional" />
					</Field>
					<Field label="Subject" required>
						<TextInput value={subject} onChange={setSubject} placeholder={drafting ? 'Drafting…' : ''} />
					</Field>
					<Field label="Message" required hint={drafting ? 'The AI is drafting from the document…' : undefined}>
						<TextArea
							value={body}
							onChange={setBody}
							rows={10}
							disabled={drafting}
							placeholder={drafting ? 'Drafting…' : 'Write the message, or use Regenerate.'}
						/>
					</Field>
					{attachLabel && <CheckInput checked={attach} onChange={setAttach} label={`Attach ${attachLabel}`} />}
					{err && <div className="ferr">{err}</div>}
					<div className="emactions">
						<button type="button" className="btn" onClick={() => void runDraft()} disabled={drafting || sending}>
							<Icon name="sparkle" size={14} /> {drafting ? 'Drafting…' : 'Regenerate'}
						</button>
						<span style={{ flex: 1 }} />
						<button type="button" className="btn" onClick={onClose} disabled={sending}>Cancel</button>
						<button
							type="button"
							className="btn primary"
							onClick={() => void runSend()}
							disabled={sending || drafting || !to || !subject || !body}
						>
							<Icon name="send" size={14} /> {sending ? 'Sending…' : 'Send'}
						</button>
					</div>
				</div>
			)}
		</Modal>
	);
}
