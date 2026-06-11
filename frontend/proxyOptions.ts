import fs from 'node:fs';
import path from 'node:path';

// Dev-server proxy to the local bench (Raven pattern). Reads the bench's
// common_site_config.json when the app lives inside a bench; falls back to 8000.
function getWebserverPort(): number {
	try {
		const configPath = path.resolve(__dirname, '../../../sites/common_site_config.json');
		const config = JSON.parse(fs.readFileSync(configPath, 'utf-8'));
		return config.webserver_port || 8000;
	} catch {
		return 8000;
	}
}

const port = getWebserverPort();

export default {
	'^/(app|api|assets|files|private)': {
		target: `http://127.0.0.1:${port}`,
		ws: true,
		changeOrigin: true,
		router: (req: { headers: { host?: string } }) => `http://${req.headers.host?.split(':')[0]}:${port}`,
	},
};
