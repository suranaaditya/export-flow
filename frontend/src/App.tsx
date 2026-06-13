import { FrappeProvider, useFrappeAuth } from 'frappe-react-sdk';
import type { ReactNode } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { AppShell } from '@/components/AppShell';
import { ThemeProvider } from '@/lib/theme';
import { Compliance } from '@/pages/Compliance';
import { Dashboard } from '@/pages/Dashboard';
import { Documents } from '@/pages/Documents';
import { Sales } from '@/pages/Sales';
import { LetterOfCreditPage } from '@/pages/LetterOfCreditPage';
import { NewSalesOrder } from '@/pages/NewSalesOrder';
import { ProFormaInvoicePage } from '@/pages/ProFormaInvoicePage';
import { NewPurchaseOrder } from '@/pages/NewPurchaseOrder';
import { NewShipment } from '@/pages/NewShipment';
import { PurchaseOrderDetail } from '@/pages/PurchaseOrderDetail';
import { Purchases } from '@/pages/Purchases';
import { ShipmentDetail } from '@/pages/ShipmentDetail';
import { SalesOrderDetail } from '@/pages/SalesOrderDetail';
import { SalesOrders } from '@/pages/SalesOrders';
import { Settings } from '@/pages/Settings';
import { Shipments } from '@/pages/Shipments';

/**
 * The server already redirects guests to /login (www/exportflow.py). This
 * client-side gate re-checks on window focus, so an expired session is caught
 * the next time the user returns to the tab (not instantly mid-session).
 */
function AuthGate({ children }: { children: ReactNode }) {
	const { currentUser, isLoading } = useFrappeAuth({ revalidateOnFocus: true });

	if (isLoading) return null;
	if (!currentUser || currentUser === 'Guest') {
		const deepLink = window.location.pathname + window.location.search;
		window.location.replace('/login?redirect-to=' + encodeURIComponent(deepLink));
		return null;
	}
	return <>{children}</>;
}

export default function App() {
	return (
		// No realtime usage yet — keep the socket off until a later phase
		// injects boot/sitename Raven-style and passes siteName/socketPort.
		<FrappeProvider enableSocket={false}>
			<ThemeProvider>
				<AuthGate>
					<BrowserRouter basename="/exportflow">
						<Routes>
							<Route element={<AppShell />}>
								<Route index element={<Dashboard />} />
								<Route path="sales" element={<Sales />} />
								<Route path="sales-orders" element={<SalesOrders />} />
								<Route path="sales-orders/new" element={<NewSalesOrder />} />
								<Route path="sales-orders/:id" element={<SalesOrderDetail />} />
								<Route path="pfi/new" element={<ProFormaInvoicePage />} />
								<Route path="pfi/:name" element={<ProFormaInvoicePage />} />
								<Route path="lc/new" element={<LetterOfCreditPage />} />
								<Route path="lc/:name" element={<LetterOfCreditPage />} />
								<Route path="purchases" element={<Purchases />} />
								<Route path="purchases/new" element={<NewPurchaseOrder />} />
								<Route path="purchases/:id" element={<PurchaseOrderDetail />} />
								<Route path="shipments" element={<Shipments />} />
								<Route path="shipments/new" element={<NewShipment />} />
								<Route path="shipments/:id" element={<ShipmentDetail />} />
								<Route path="documents" element={<Documents />} />
								<Route path="compliance" element={<Compliance />} />
								<Route path="settings" element={<Settings />} />
							</Route>
						</Routes>
					</BrowserRouter>
				</AuthGate>
			</ThemeProvider>
		</FrappeProvider>
	);
}
