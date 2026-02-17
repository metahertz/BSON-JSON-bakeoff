/**
 * Express router for running benchmarks from the webapp.
 *
 * Endpoints:
 *   POST /api/benchmark/run          - Start a benchmark run
 *   GET  /api/benchmark/stream/:id   - SSE stream of stdout/stderr
 *   POST /api/benchmark/stop/:id     - Send SIGTERM to running benchmark
 *   GET  /api/benchmark/status       - Current/recent run status
 */

const express = require('express');
const { spawn } = require('child_process');
const crypto = require('crypto');
const path = require('path');
const fs = require('fs');
const os = require('os');

const router = express.Router();

// In-memory state for the current/most-recent run
let currentRun = null;

// SSE clients waiting for output
const sseClients = new Map(); // runId -> Set<res>

// ── helpers ──────────────────────────────────────────────────────────

function projectRoot() {
    // webapp/ is one level below project root
    return path.resolve(__dirname, '..', '..');
}

/**
 * Build a temporary benchmark_config.ini that ensures cloud databases are enabled
 * when selected in the webapp.  If the user supplies a connection string it takes
 * precedence; otherwise the value from the base config file is kept (but `enabled`
 * is forced to `true`).  Returns the path to the temp file, or null if no cloud
 * databases were selected.
 */
function buildTempConfig(body) {
    const cloudDbs = body.cloud_databases || [];
    const wantsAtlas = cloudDbs.includes('mongodb-atlas');
    const wantsAzure = cloudDbs.includes('azure-documentdb');

    if (!wantsAtlas && !wantsAzure) {
        return null;
    }

    // Read existing config to preserve results_storage and other sections
    const baseConfigPath = path.join(projectRoot(), 'config', 'benchmark_config.ini');
    let content = '';
    if (fs.existsSync(baseConfigPath)) {
        content = fs.readFileSync(baseConfigPath, 'utf8');
    }

    // Helper: replace or append an INI section
    function upsertSection(sectionName, kvPairs) {
        const header = `[${sectionName}]`;
        const lines = kvPairs.map(([k, v]) => `${k} = ${v}`).join('\n');
        const block = `${header}\n${lines}\n`;
        if (content.includes(header)) {
            content = content.replace(new RegExp(`\\[${sectionName}\\][^\\[]*`), block);
        } else {
            content += '\n' + block;
        }
    }

    // Extract an existing value from the raw INI text (simple key = value match)
    function existingValue(sectionName, key) {
        const sectionRe = new RegExp(`\\[${sectionName}\\]([^\\[]*)`);
        const m = content.match(sectionRe);
        if (!m) return null;
        const lineRe = new RegExp(`^\\s*${key}\\s*=\\s*(.+)`, 'm');
        const lm = m[1].match(lineRe);
        return lm ? lm[1].trim() : null;
    }

    if (wantsAtlas) {
        const connStr = body.atlas_connection_string || existingValue('mongodb_atlas', 'connection_string');
        if (connStr) {
            upsertSection('mongodb_atlas', [['enabled', 'true'], ['connection_string', connStr]]);
        }
        // If no connection string at all, the Python script will warn about it
    }

    if (wantsAzure) {
        const connStr = body.azure_connection_string || existingValue('azure_documentdb', 'connection_string');
        if (connStr) {
            upsertSection('azure_documentdb', [['enabled', 'true'], ['connection_string', connStr]]);
        }
    }

    const tmpFile = path.join(os.tmpdir(), `benchmark_config_${crypto.randomUUID()}.ini`);
    fs.writeFileSync(tmpFile, content, { mode: 0o600 });
    return tmpFile;
}

/**
 * Turn the validated request body into CLI args for run_article_benchmarks_docker.py
 */
function buildCliArgs(body) {
    const args = [];
    const scriptPath = path.join(projectRoot(), 'scripts', 'run_article_benchmarks_docker.py');
    args.push(scriptPath);

    // Docker databases
    const dbs = body.databases || [];
    for (const db of dbs) {
        args.push('--' + db);  // e.g. --mongodb, --postgresql
    }

    // Cloud databases
    const cloudDbs = body.cloud_databases || [];
    for (const db of cloudDbs) {
        args.push('--' + db);  // e.g. --mongodb-atlas, --azure-documentdb
    }

    // Test parameters
    if (body.num_docs) args.push('--num-docs', String(body.num_docs));
    if (body.num_runs) args.push('--num-runs', String(body.num_runs));
    if (body.batch_size) args.push('--batch-size', String(body.batch_size));

    // Index mode
    if (body.index_mode === 'no-index') args.push('--no-index');
    else if (body.index_mode === 'full-comparison') args.push('--full-comparison');

    // Boolean flags
    if (body.queries) args.push('--queries');
    if (body.validate) args.push('--validate');
    if (body.large_items) args.push('--large-items');
    if (body.randomize_order) args.push('--randomize-order');
    if (body.measure_sizes) args.push('--measure-sizes');

    // Monitoring
    if (body.monitor === false) args.push('--no-monitor');

    return args;
}

function broadcast(runId, event, data) {
    const clients = sseClients.get(runId);
    if (!clients) return;
    // SSE protocol: newlines inside a data field terminate the field, so raw
    // multiline chunks would lose every line after the first.  Split into
    // individual lines and send each as a separate SSE message.
    const lines = data.split('\n');
    for (const res of clients) {
        for (const line of lines) {
            res.write(`event: ${event}\ndata: ${line}\n\n`);
        }
    }
}

// ── routes ───────────────────────────────────────────────────────────

// POST /api/benchmark/run
router.post('/run', (req, res) => {
    if (currentRun && currentRun.status === 'running') {
        return res.status(409).json({ error: 'A benchmark is already running' });
    }

    const body = req.body || {};
    const runId = crypto.randomUUID();
    const cliArgs = buildCliArgs(body);

    // Prepare environment — propagate current env, optionally override config path
    const env = { ...process.env };
    // Force Python to use unbuffered stdout/stderr so output streams line-by-line
    // instead of being block-buffered (~8KB) when piped to a subprocess.
    env.PYTHONUNBUFFERED = '1';
    const tmpConfig = buildTempConfig(body);
    if (tmpConfig) {
        env.BENCHMARK_CONFIG_PATH = tmpConfig;
    }

    const proc = spawn('python3', cliArgs, {
        cwd: projectRoot(),
        env,
        stdio: ['ignore', 'pipe', 'pipe'],
    });

    currentRun = {
        runId,
        status: 'running',
        pid: proc.pid,
        startedAt: new Date().toISOString(),
        process: proc,
        tmpConfig,
    };

    sseClients.set(runId, new Set());

    const onData = (chunk) => {
        // Strip trailing newline to avoid an extra blank line per chunk;
        // broadcast() handles splitting on any embedded newlines.
        broadcast(runId, 'output', chunk.toString().replace(/\n$/, ''));
    };

    proc.stdout.on('data', onData);
    proc.stderr.on('data', onData);

    proc.on('close', (code) => {
        if (currentRun && currentRun.runId === runId) {
            currentRun.status = code === 0 ? 'completed' : (currentRun.status === 'stopped' ? 'stopped' : 'failed');
            currentRun.exitCode = code;
            currentRun.process = null;
        }
        broadcast(runId, 'status', JSON.stringify({ status: currentRun ? currentRun.status : 'failed' }));

        // Clean up temp config
        if (tmpConfig) {
            try { fs.unlinkSync(tmpConfig); } catch (_) {}
        }

        // Close SSE connections after a short delay so clients receive the final status
        setTimeout(() => {
            const clients = sseClients.get(runId);
            if (clients) {
                for (const c of clients) {
                    c.end();
                }
                sseClients.delete(runId);
            }
        }, 2000);
    });

    res.json({ runId, status: 'running' });
});

// GET /api/benchmark/stream/:id
router.get('/stream/:id', (req, res) => {
    const runId = req.params.id;

    res.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
    });
    res.write('\n');

    let clients = sseClients.get(runId);
    if (!clients) {
        clients = new Set();
        sseClients.set(runId, clients);
    }
    clients.add(res);

    // If already finished, send status immediately
    if (currentRun && currentRun.runId === runId && currentRun.status !== 'running') {
        res.write(`event: status\ndata: ${JSON.stringify({ status: currentRun.status })}\n\n`);
    }

    req.on('close', () => {
        clients.delete(res);
    });
});

// POST /api/benchmark/stop/:id
router.post('/stop/:id', (req, res) => {
    const runId = req.params.id;
    if (!currentRun || currentRun.runId !== runId) {
        return res.status(404).json({ error: 'Run not found' });
    }
    if (currentRun.status !== 'running' || !currentRun.process) {
        return res.status(409).json({ error: 'Run is not active' });
    }

    currentRun.status = 'stopped';
    currentRun.process.kill('SIGTERM');
    res.json({ status: 'stopped' });
});

// GET /api/benchmark/status
router.get('/status', (req, res) => {
    if (!currentRun) {
        return res.json({ runId: null, status: null });
    }
    res.json({
        runId: currentRun.runId,
        status: currentRun.status,
        startedAt: currentRun.startedAt,
        exitCode: currentRun.exitCode || null,
    });
});

module.exports = router;
