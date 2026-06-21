import { createPortal } from 'react-dom';

/** Full-screen blocking "working…" overlay for slow actions (e.g. Amend, whose
 *  cancel step runs compliance hooks and can take a few seconds) so the user
 *  clearly sees something is happening. Portaled to <body>. */
export function BusyOverlay({ show, message }: { show: boolean; message?: string }) {
	if (!show) return null;
	return createPortal(
		<div className="busyoverlay" role="status" aria-live="assertive" aria-busy="true">
			<div className="busycard">
				<span className="busyspin" aria-hidden="true" />
				<span className="busymsg">{message ?? 'Working…'}</span>
			</div>
		</div>,
		document.body,
	);
}
