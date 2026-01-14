/**
 * Main application JavaScript
 */

const API_BASE = '/api/results';

let insertionChart = null;
let queryChart = null;
let throughputChart = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    await loadVersions();
    await loadResults();
    setupEventListeners();
});

async function loadVersions() {
    try {
        const response = await fetch(`${API_BASE}/meta/versions`);
        const data = await response.json();
        
        // Populate database type dropdown
        const dbTypeSelect = document.getElementById('database-type');
        data.database_types.forEach(type => {
            const option = document.createElement('option');
            option.value = type;
            option.textContent = type;
            dbTypeSelect.appendChild(option);
        });
        
        // Populate database version dropdown
        const dbVersionSelect = document.getElementById('database-version');
        data.database_versions.forEach(version => {
            const option = document.createElement('option');
            option.value = version;
            option.textContent = version;
            dbVersionSelect.appendChild(option);
        });
    } catch (error) {
        console.error('Error loading versions:', error);
    }
}

async function loadResults() {
    try {
        const filters = getFilters();
        const queryParams = new URLSearchParams();
        
        if (filters.database_type) queryParams.append('database_type', filters.database_type);
        if (filters.database_version) queryParams.append('database_version', filters.database_version);
        if (filters.start_date) queryParams.append('start_date', filters.start_date);
        if (filters.end_date) queryParams.append('end_date', filters.end_date);
        queryParams.append('limit', '100');
        
        const response = await fetch(`${API_BASE}?${queryParams}`);
        const data = await response.json();
        
        updateTable(data.results);
        updateCharts(data.results);
    } catch (error) {
        console.error('Error loading results:', error);
        showError('Failed to load results: ' + error.message);
    }
}

function getFilters() {
    return {
        database_type: document.getElementById('database-type').value,
        database_version: document.getElementById('database-version').value,
        test_type: document.getElementById('test-type').value,
        start_date: document.getElementById('start-date').value,
        end_date: document.getElementById('end-date').value
    };
}

function updateTable(results) {
    const tbody = document.getElementById('results-tbody');
    tbody.innerHTML = '';
    
    if (results.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="loading">No results found</td></tr>';
        return;
    }
    
    results.forEach(result => {
        const row = document.createElement('tr');
        const timestamp = new Date(result.timestamp).toLocaleString();
        const dbType = result.database?.type || 'unknown';
        const dbVersion = result.database?.version || 'unknown';
        const testType = result.test_config?.test_type || 'unknown';
        const payloadSize = result.test_config?.payload_size || 0;
        const insertTime = result.results?.insert_time_ms || '-';
        const insertThroughput = result.results?.insert_throughput || '-';
        const queryTime = result.results?.query_time_ms || '-';
        
        row.innerHTML = `
            <td>${timestamp}</td>
            <td>${dbType}</td>
            <td>${dbVersion}</td>
            <td>${testType}</td>
            <td>${payloadSize}B</td>
            <td>${insertTime}</td>
            <td>${insertThroughput}</td>
            <td>${queryTime}</td>
        `;
        tbody.appendChild(row);
    });
}

function updateCharts(results) {
    // Filter successful results
    const successful = results.filter(r => r.results?.success);
    
    // Group by database type and version
    const grouped = {};
    successful.forEach(result => {
        const key = `${result.database?.type || 'unknown'}-${result.database?.version || 'unknown'}`;
        if (!grouped[key]) {
            grouped[key] = {
                label: key,
                insertTimes: [],
                queryTimes: [],
                throughputs: [],
                payloadSizes: []
            };
        }
        
        if (result.results?.insert_time_ms) {
            grouped[key].insertTimes.push(result.results.insert_time_ms);
            grouped[key].payloadSizes.push(result.test_config?.payload_size || 0);
        }
        
        if (result.results?.query_time_ms) {
            grouped[key].queryTimes.push(result.results.query_time_ms);
        }
        
        if (result.results?.insert_throughput) {
            grouped[key].throughputs.push(result.results.insert_throughput);
        }
    });
    
    // Update insertion chart
    updateInsertionChart(grouped);
    
    // Update query chart
    updateQueryChart(grouped);
    
    // Update throughput chart
    updateThroughputChart(grouped);
}

function updateInsertionChart(grouped) {
    const ctx = document.getElementById('insertion-chart').getContext('2d');
    
    if (insertionChart) {
        insertionChart.destroy();
    }
    
    const datasets = Object.values(grouped).map((group, index) => {
        const colors = ['#667eea', '#764ba2', '#f093fb', '#4facfe'];
        return {
            label: group.label,
            data: group.insertTimes,
            backgroundColor: colors[index % colors.length],
            borderColor: colors[index % colors.length],
            borderWidth: 2
        };
    });
    
    insertionChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: Object.values(grouped)[0]?.payloadSizes.map(s => `${s}B`) || [],
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Time (ms)'
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: 'Payload Size'
                    }
                }
            }
        }
    });
}

function updateQueryChart(grouped) {
    const ctx = document.getElementById('query-chart').getContext('2d');
    
    if (queryChart) {
        queryChart.destroy();
    }
    
    const datasets = Object.values(grouped).map((group, index) => {
        const colors = ['#667eea', '#764ba2', '#f093fb', '#4facfe'];
        return {
            label: group.label,
            data: group.queryTimes,
            backgroundColor: colors[index % colors.length],
            borderColor: colors[index % colors.length],
            borderWidth: 2
        };
    });
    
    queryChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: Object.keys(grouped),
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Query Time (ms)'
                    }
                }
            }
        }
    });
}

function updateThroughputChart(grouped) {
    const ctx = document.getElementById('throughput-chart').getContext('2d');
    
    if (throughputChart) {
        throughputChart.destroy();
    }
    
    const datasets = Object.values(grouped).map((group, index) => {
        const colors = ['#667eea', '#764ba2', '#f093fb', '#4facfe'];
        return {
            label: group.label,
            data: group.throughputs,
            backgroundColor: colors[index % colors.length],
            borderColor: colors[index % colors.length],
            borderWidth: 2
        };
    });
    
    throughputChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: Object.values(grouped)[0]?.payloadSizes.map(s => `${s}B`) || [],
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Throughput (docs/sec)'
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: 'Payload Size'
                    }
                }
            }
        }
    });
}

function setupEventListeners() {
    document.getElementById('apply-filters').addEventListener('click', loadResults);
    document.getElementById('export-data').addEventListener('click', exportData);
}

async function exportData() {
    try {
        const filters = getFilters();
        const queryParams = new URLSearchParams();
        
        if (filters.database_type) queryParams.append('database_type', filters.database_type);
        if (filters.database_version) queryParams.append('database_version', filters.database_version);
        if (filters.start_date) queryParams.append('start_date', filters.start_date);
        if (filters.end_date) queryParams.append('end_date', filters.end_date);
        queryParams.append('limit', '10000'); // Get more for export
        
        const response = await fetch(`${API_BASE}?${queryParams}`);
        const data = await response.json();
        
        // Convert to CSV
        const csv = convertToCSV(data.results);
        downloadCSV(csv, 'benchmark_results.csv');
    } catch (error) {
        console.error('Error exporting data:', error);
        showError('Failed to export data: ' + error.message);
    }
}

function convertToCSV(results) {
    const headers = ['Timestamp', 'Database Type', 'Database Version', 'Test Type', 'Payload Size', 'Insert Time (ms)', 'Insert Throughput', 'Query Time (ms)'];
    const rows = results.map(r => [
        new Date(r.timestamp).toISOString(),
        r.database?.type || '',
        r.database?.version || '',
        r.test_config?.test_type || '',
        r.test_config?.payload_size || '',
        r.results?.insert_time_ms || '',
        r.results?.insert_throughput || '',
        r.results?.query_time_ms || ''
    ]);
    
    return [headers, ...rows].map(row => row.join(',')).join('\n');
}

function downloadCSV(csv, filename) {
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    window.URL.revokeObjectURL(url);
}

function showError(message) {
    const errorDiv = document.createElement('div');
    errorDiv.className = 'error';
    errorDiv.textContent = message;
    document.querySelector('.container').insertBefore(errorDiv, document.querySelector('.filters'));
    setTimeout(() => errorDiv.remove(), 5000);
}
