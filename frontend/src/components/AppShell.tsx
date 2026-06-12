import { useFrappeAuth } from 'frappe-react-sdk';
import { NavLink, Outlet } from 'react-router-dom';
import { Icon, type IconName } from '@/components/Icon';
import { useTheme } from '@/lib/theme';

const NAV_ITEMS: { to: string; label: string; icon: IconName }[] = [
	{ to: '/', label: 'Dashboard', icon: 'layers' },
	{ to: '/sales-orders', label: 'Sales orders', icon: 'file-text' },
	{ to: '/purchases', label: 'Purchases', icon: 'cube' },
	{ to: '/shipments', label: 'Shipments', icon: 'ship' },
	{ to: '/documents', label: 'Documents', icon: 'copy' },
	{ to: '/compliance', label: 'Compliance', icon: 'shield-check' },
];

const BRAND = import.meta.env.BASE_URL + 'brand/';

function initialsOf(user: string | null | undefined): string {
	if (!user) return '·';
	const local = user.split('@')[0];
	const parts = local.split(/[._\-\s]+/).filter(Boolean);
	const letters = parts.length >= 2 ? parts[0][0] + parts[1][0] : local.slice(0, 2);
	return letters.toUpperCase();
}

export function AppShell() {
	const { toggle } = useTheme();
	const { currentUser } = useFrappeAuth();

	return (
		<div className="layout">
			<aside className="sidebar">
				<div className="brand">
					<img className="mk-l" src={BRAND + 'dux-mark.png'} alt="DUX" />
					<img className="mk-w" src={BRAND + 'dux-mark-white.png'} alt="DUX" />
					<div>
						<div className="nm">
							Export<em>Flow</em>
						</div>
						<div className="by">DUX Digitech</div>
					</div>
				</div>
				<nav className="snav">
					{NAV_ITEMS.map((item) => (
						<NavLink key={item.to} to={item.to} end={item.to === '/'} className={({ isActive }) => (isActive ? 'on' : '')}>
							<Icon name={item.icon} size={16} />
							<span className="lbl">{item.label}</span>
						</NavLink>
					))}
					<div className="push" />
					<NavLink to="/settings" className={({ isActive }) => (isActive ? 'on' : '')}>
						<Icon name="sliders" size={16} />
						<span className="lbl">Settings</span>
					</NavLink>
				</nav>
				<div className="sfoot">
					<button className="icbtn" onClick={toggle} title="Toggle theme" aria-label="Toggle theme">
						<Icon name="moon" size={17} className="ic-moon" />
						<Icon name="sun" size={17} className="ic-sun" />
					</button>
					<div className="usr" title={currentUser ?? ''}>
						{initialsOf(currentUser)}
					</div>
				</div>
			</aside>
			<div className="content">
				<Outlet />
			</div>
		</div>
	);
}
