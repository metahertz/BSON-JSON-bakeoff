/**
 * Express server for benchmark results visualization
 */

const express = require('express');
const cors = require('cors');
const path = require('path');
const { connectToMongoDB, closeConnection } = require('./config/mongodb');
const getResultsRoutes = require('./routes/results');

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// MongoDB connection and routes
let db = null;
let collectionName = 'test_runs';

(async () => {
    try {
        const { db: connectedDb, collectionName: collName } = await connectToMongoDB();
        db = connectedDb;
        collectionName = collName || 'test_runs';
        
        // API routes
        app.use('/api/results', getResultsRoutes(db, collectionName));
        
        // Health check
        app.get('/api/health', (req, res) => {
            res.json({ status: 'ok', database: 'connected' });
        });
        
        // Start server
        app.listen(PORT, () => {
            console.log(`Benchmark Results Webapp running on http://localhost:${PORT}`);
            console.log(`API available at http://localhost:${PORT}/api/results`);
        });
    } catch (error) {
        console.error('Failed to start server:', error);
        process.exit(1);
    }
})();

// Graceful shutdown
process.on('SIGINT', async () => {
    console.log('\nShutting down...');
    await closeConnection();
    process.exit(0);
});

process.on('SIGTERM', async () => {
    console.log('\nShutting down...');
    await closeConnection();
    process.exit(0);
});
