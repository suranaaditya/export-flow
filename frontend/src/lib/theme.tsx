import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';

type Theme = 'light' | 'dark';

const STORAGE_KEY = 'exportflow:theme';

const ThemeContext = createContext<{ theme: Theme; toggle: () => void }>({
	theme: 'light',
	toggle: () => undefined,
});

function getInitialTheme(): Theme {
	try {
		const stored = localStorage.getItem(STORAGE_KEY);
		if (stored === 'dark' || stored === 'light') return stored;
	} catch {
		// localStorage unavailable — fall through to default
	}
	return 'light';
}

export function ThemeProvider({ children }: { children: ReactNode }) {
	const [theme, setTheme] = useState<Theme>(getInitialTheme);

	useEffect(() => {
		document.documentElement.dataset.theme = theme;
		try {
			localStorage.setItem(STORAGE_KEY, theme);
		} catch {
			// ignore
		}
	}, [theme]);

	const toggle = useCallback(() => setTheme((t) => (t === 'dark' ? 'light' : 'dark')), []);

	return <ThemeContext.Provider value={{ theme, toggle }}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
	return useContext(ThemeContext);
}
