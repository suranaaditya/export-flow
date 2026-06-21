import {
	createContext,
	useCallback,
	useContext,
	useEffect,
	useMemo,
	useRef,
	useState,
	type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';
import { Icon } from '@/components/Icon';

type Tone = 'ok' | 'err' | 'info';
interface ToastItem {
	id: number;
	tone: Tone;
	msg: string;
}
interface ToastApi {
	ok: (msg: string) => void;
	err: (msg: string) => void;
	info: (msg: string) => void;
}

const ToastCtx = createContext<ToastApi | null>(null);

/** Success / error / info notifications (feedback #22) — DUX-token chips that
 *  auto-dismiss, portaled to <body>. */
export function useToast(): ToastApi {
	const ctx = useContext(ToastCtx);
	if (!ctx) throw new Error('useToast must be used within a ToastProvider');
	return ctx;
}

const ICON: Record<Tone, 'circle-check' | 'warning' | 'exclamation'> = {
	ok: 'circle-check',
	err: 'warning',
	info: 'exclamation',
};

export function ToastProvider({ children }: { children: ReactNode }) {
	const [items, setItems] = useState<ToastItem[]>([]);
	const seq = useRef(0);
	const timers = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());

	const remove = useCallback((id: number) => {
		const t = timers.current.get(id);
		if (t) {
			clearTimeout(t);
			timers.current.delete(id);
		}
		setItems((xs) => xs.filter((x) => x.id !== id));
	}, []);
	const push = useCallback(
		(tone: Tone, msg: string) => {
			const id = ++seq.current;
			setItems((xs) => [...xs, { id, tone, msg }]);
			// errors linger a little longer than successes
			timers.current.set(id, setTimeout(() => remove(id), tone === 'err' ? 6000 : 3800));
		},
		[remove],
	);
	// clear any pending timers if the provider ever unmounts
	useEffect(() => {
		const map = timers.current;
		return () => map.forEach((t) => clearTimeout(t));
	}, []);

	const api = useMemo<ToastApi>(
		() => ({
			ok: (m) => push('ok', m),
			err: (m) => push('err', m),
			info: (m) => push('info', m),
		}),
		[push],
	);

	return (
		<ToastCtx.Provider value={api}>
			{children}
			{createPortal(
				<div className="toaststack" role="status" aria-live="polite">
					{items.map((t) => (
						<div key={t.id} className={`toast ${t.tone}`}>
							<Icon name={ICON[t.tone]} size={16} />
							<span className="toastmsg">{t.msg}</span>
							<button
								type="button"
								className="toastx"
								aria-label="Dismiss"
								onClick={() => remove(t.id)}
							>
								<Icon name="close" size={13} />
							</button>
						</div>
					))}
				</div>,
				document.body,
			)}
		</ToastCtx.Provider>
	);
}
