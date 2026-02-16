/**
 * Frontend logic for the Run Benchmark page.
 * Handles form submission, SSE streaming, and stop control.
 */

(function () {
    const form = document.getElementById('benchmark-form');
    const runBtn = document.getElementById('run-btn');
    const stopBtn = document.getElementById('stop-btn');
    const badge = document.getElementById('status-badge');
    const outputSection = document.getElementById('output-section');
    const outputConsole = document.getElementById('output-console');

    let currentRunId = null;
    let eventSource = null;

    // Toggle cloud config visibility
    document.getElementById('cb-atlas').addEventListener('change', function () {
        document.getElementById('atlas-config').style.display = this.checked ? 'block' : 'none';
    });
    document.getElementById('cb-azure').addEventListener('change', function () {
        document.getElementById('azure-config').style.display = this.checked ? 'block' : 'none';
    });

    function setStatus(status) {
        badge.style.display = 'inline-block';
        badge.textContent = status;
        badge.className = 'status-badge ' + status;
    }

    function appendOutput(text) {
        outputConsole.textContent += text;
        outputConsole.scrollTop = outputConsole.scrollHeight;
    }

    function buildConfig() {
        const getChecked = (name) =>
            Array.from(form.querySelectorAll(`input[name="${name}"]:checked`)).map(el => el.value);

        const config = {
            databases: getChecked('databases'),
            cloud_databases: getChecked('cloud_databases'),
            num_docs: parseInt(form.num_docs.value) || 10000,
            num_runs: parseInt(form.num_runs.value) || 3,
            batch_size: parseInt(form.batch_size.value) || 500,
            index_mode: form.index_mode.value,
            queries: form.queries.checked,
            validate: form.validate.checked,
            monitor: form.monitor.checked,
            randomize_order: form.randomize_order.checked,
            measure_sizes: form.measure_sizes.checked,
            large_items: form.large_items.checked,
        };

        const customSizes = form.custom_sizes.value.trim();
        if (customSizes) {
            config.custom_sizes = customSizes;
        }

        const atlasConn = form.atlas_connection_string.value.trim();
        if (atlasConn) {
            config.atlas_connection_string = atlasConn;
        }

        const azureConn = form.azure_connection_string.value.trim();
        if (azureConn) {
            config.azure_connection_string = azureConn;
        }

        return config;
    }

    function connectSSE(runId) {
        if (eventSource) {
            eventSource.close();
        }
        eventSource = new EventSource('/api/benchmark/stream/' + runId);

        eventSource.addEventListener('output', function (e) {
            appendOutput(e.data + '\n');
        });

        eventSource.addEventListener('status', function (e) {
            const data = JSON.parse(e.data);
            setStatus(data.status);
            if (data.status === 'completed' || data.status === 'failed' || data.status === 'stopped') {
                eventSource.close();
                eventSource = null;
                stopBtn.style.display = 'none';
                runBtn.disabled = false;
            }
        });

        eventSource.onerror = function () {
            // Connection lost — check status once
            eventSource.close();
            eventSource = null;
            fetch('/api/benchmark/status')
                .then(r => r.json())
                .then(data => {
                    if (data.runId === runId && data.status) {
                        setStatus(data.status);
                    }
                })
                .catch(() => {});
            stopBtn.style.display = 'none';
            runBtn.disabled = false;
        };
    }

    form.addEventListener('submit', async function (e) {
        e.preventDefault();
        const config = buildConfig();

        if (config.databases.length === 0 && config.cloud_databases.length === 0) {
            alert('Please select at least one database.');
            return;
        }

        runBtn.disabled = true;
        outputConsole.textContent = '';
        outputSection.style.display = 'block';
        setStatus('running');

        try {
            const res = await fetch('/api/benchmark/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config),
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.error || 'Failed to start benchmark');
            }

            const data = await res.json();
            currentRunId = data.runId;

            stopBtn.style.display = 'inline-block';
            connectSSE(currentRunId);
        } catch (err) {
            appendOutput('Error: ' + err.message + '\n');
            setStatus('failed');
            runBtn.disabled = false;
        }
    });

    stopBtn.addEventListener('click', async function () {
        if (!currentRunId) return;
        stopBtn.disabled = true;
        try {
            await fetch('/api/benchmark/stop/' + currentRunId, { method: 'POST' });
            appendOutput('\n--- Stop signal sent ---\n');
        } catch (err) {
            appendOutput('Error stopping: ' + err.message + '\n');
        }
        stopBtn.disabled = false;
    });

    // On load, check if a benchmark is already running
    fetch('/api/benchmark/status')
        .then(r => r.json())
        .then(data => {
            if (data.runId && data.status === 'running') {
                currentRunId = data.runId;
                outputSection.style.display = 'block';
                setStatus('running');
                stopBtn.style.display = 'inline-block';
                runBtn.disabled = true;
                connectSSE(currentRunId);
            }
        })
        .catch(() => {});
})();
