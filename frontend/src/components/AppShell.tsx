import { useFrappeAuth } from 'frappe-react-sdk';
import { NavLink, Outlet } from 'react-router-dom';
import { Icon } from '@/components/Icon';
import { useTheme } from '@/lib/theme';

const NAV_ITEMS = [
	{ to: '/', label: 'Dashboard' },
	{ to: '/sales-orders', label: 'Sales orders' },
	{ to: '/purchases', label: 'Purchases' },
	{ to: '/shipments', label: 'Shipments' },
	{ to: '/documents', label: 'Documents' },
	{ to: '/compliance', label: 'Compliance' },
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
		<>
			<header className="appbar">
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
				<nav className="mainnav">
					{NAV_ITEMS.map((item) => (
						<NavLink key={item.to} to={item.to} end={item.to === '/'} className={({ isActive }) => (isActive ? 'on' : '')}>
							{item.label}
						</NavLink>
					))}
				</nav>
				<div className="hbtns">
					<button className="icbtn" onClick={toggle} title="Toggle theme" aria-label="Toggle theme">
						<Icon name="moon" size={17} className="ic-moon" />
						<Icon name="sun" size={17} className="ic-sun" />
					</button>
					<div className="usr" title={currentUser ?? ''}>
						{initialsOf(currentUser)}
					</div>
				</div>
			</header>
			<Outlet />
		</>
	);
}
