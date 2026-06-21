import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react';
import { type IconName } from '@/components/Icon';
import { Modal } from '@/components/ui';

export interface ConfirmOpts {
	title: string;
	message: ReactNode;
	confirmLabel?: string;
	cancelLabel?: string;
	/** red confirm button for destructive / irreversible actions */
	danger?: boolean;
	icon?: IconName;
}
type ConfirmFn = (opts: ConfirmOpts) => Promise<boolean>;

const ConfirmCtx = createContext<ConfirmFn | null>(null);

/** Promise-based confirmation dialog (feedback #22) — `await confirm({...})`
 *  returns true/false. Built on the shared Modal so it inherits the DUX card
 *  language and the body portal. */
export function useConfirm(): ConfirmFn {
	const fn = useContext(ConfirmCtx);
	if (!fn) throw new Error('useConfirm must be used within a ConfirmProvider');
	return fn;
}

export function ConfirmProvider({ children }: { children: ReactNode }) {
	const [opts, setOpts] = useState<ConfirmOpts | null>(null);
	const resolver = useRef<((v: boolean) => void) | null>(null);

	const confirm = useCallback<ConfirmFn>((o) => {
		// settle any in-flight confirm as cancelled, so a second call can never
		// leave the first `await confirm()` hanging forever
		resolver.current?.(false);
		setOpts(o);
		return new Promise<boolean>((resolve) => {
			resolver.current = resolve;
		});
	}, []);

	const settle = (v: boolean) => {
		resolver.current?.(v);
		resolver.current = null;
		setOpts(null);
	};

	return (
		<ConfirmCtx.Provider value={confirm}>
			{children}
			{opts && (
				<Modal
					title={opts.title}
					icon={opts.icon ?? (opts.danger ? 'warning' : 'exclamation')}
					onClose={() => settle(false)}
				>
					<div className="confirmbody">{opts.message}</div>
					<div className="formfoot">
						<span className="spacer" />
						<button type="button" className="btn" onClick={() => settle(false)}>
							{opts.cancelLabel ?? 'Cancel'}
						</button>
						<button
							type="button"
							className={`btn ${opts.danger ? 'danger' : 'primary'}`}
							onClick={() => settle(true)}
						>
							{opts.confirmLabel ?? 'Confirm'}
						</button>
					</div>
				</Modal>
			)}
		</ConfirmCtx.Provider>
	);
}
