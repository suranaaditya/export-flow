import { useEffect, useState } from 'react';
import { useFrappeAuth, useFrappeGetCall } from 'frappe-react-sdk';
import { NavLink, Outlet } from 'react-router-dom';
import { Icon, type IconName } from '@/components/Icon';
import { API } from '@/lib/api';
import { useTheme } from '@/lib/theme';

const NAV_ITEMS: { to: string; label: string; icon: IconName }[] = [
	{ to: '/', label: 'Dashboard', icon: 'layers' },
	{ to: '/sales', label: 'Sales', icon: 'rupee' },
	{ to: '/sales-orders', label: 'Sales orders', icon: 'file-text' },
	{ to: '/purchases', label: 'Purchases', icon: 'cube' },
	{ to: '/shipments', label: 'Shipments', icon: 'ship' },
	{ to: '/documents', label: 'Documents', icon: 'copy' },
	{ to: '/finance', label: 'Finance', icon: 'banknote' },
	{ to: '/compliance', label: 'Compliance', icon: 'shield-check' },
];

const BRAND = import.meta.env.BASE_URL + 'brand/';
const COLLAPSE_KEY = 'exportflow:nav-collapsed';

function initialsOf(user: string | null | undefined): string {
	if (!user) return '·';
	const local = user.split('@')[0];
	const parts = local.split(/[._\-\s]+/).filter(Boolean);
	const letters = parts.length >= 2 ? parts[0][0] + parts[1][0] : local.slice(0, 2);
	return letters.toUpperCase();
}

// localStorage throws under blocked site data (Safari/iframes) — degrade calmly
function getInitialCollapsed(): boolean {
	try {
		return localStorage.getItem(COLLAPSE_KEY) === '1';
	} catch {
		return false;
	}
}

export function AppShell() {
	const { toggle } = useTheme();
	const { currentUser } = useFrappeAuth();
	const logoResult = useFrappeGetCall<{ message: { logo: string | null; nav_height: number } }>(
		API.companyLogo,
		{},
	);
	const logo = logoResult.data?.message?.logo || null;
	const navHeight = logoResult.data?.message?.nav_height || 28;
	const [collapsed, setCollapsed] = useState(getInitialCollapsed);

	useEffect(() => {
		try {
			localStorage.setItem(COLLAPSE_KEY, collapsed ? '1' : '0');
		} catch {
			// not persistable — the toggle still works for this session
		}
	}, [collapsed]);

	const toggleCollapsed = () => setCollapsed((c) => !c);

	return (
		<div className="layout">
			<aside className={collapsed ? 'sidebar collapsed' : 'sidebar'}>
				<div className="brand">
					{logo ? (
						<img
							className="cologo"
							src={logo}
							alt=""
							style={collapsed ? undefined : { maxHeight: navHeight }}
						/>
					) : (
						<>
							<img className="mk-l" src={BRAND + 'dux-mark.png'} alt="" />
							<img className="mk-w" src={BRAND + 'dux-mark-white.png'} alt="" />
						</>
					)}
					<div className="btext">
						<div className="nm">
							Export<em>Flow</em>
						</div>
					</div>
				</div>
				<nav className="snav">
					{NAV_ITEMS.map((item) => (
						<NavLink
							key={item.to}
							to={item.to}
							end={item.to === '/'}
							className={({ isActive }) => (isActive ? 'on' : '')}
							title={collapsed ? item.label : undefined}
						>
							<Icon name={item.icon} size={16} />
							<span className="lbl">{item.label}</span>
						</NavLink>
					))}
					<div className="push" />
					<NavLink
						to="/settings"
						className={({ isActive }) => (isActive ? 'on' : '')}
						title={collapsed ? 'Settings' : undefined}
					>
						<Icon name="sliders" size={16} />
						<span className="lbl">Settings</span>
					</NavLink>
				</nav>
				<div className="duxcredit" title="Built by DUX Digitech">
					<span className="dxby">Built by</span>
					<img className="dx-l" src={BRAND + 'dux-logo.png'} alt="DUX Digitech" />
					<img className="dx-w" src={BRAND + 'dux-logo-white.png'} alt="DUX Digitech" />
				</div>
				{/* credit block is intentionally non-interactive */}
				<div className="sfoot">
					<button
						className="icbtn collapse-btn"
						onClick={toggleCollapsed}
						title={collapsed ? 'Expand navigation' : 'Collapse navigation'}
						aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'}
						aria-expanded={!collapsed}
					>
						<Icon name="chevron" size={16} />
					</button>
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
