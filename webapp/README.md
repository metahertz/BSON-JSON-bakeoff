# Benchmark Results Webapp

Visualization webapp for viewing and analyzing benchmark test results stored in MongoDB.

## Setup

1. Install dependencies:
```bash
npm install
```

2. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your MongoDB connection string
```

3. Start the server:
```bash
npm start
```

For development with auto-reload:
```bash
npm run dev
```

## Usage

1. Open http://localhost:3000 in your browser
2. Use the filters to select database type, version, date range, etc.
3. View performance charts and detailed results table
4. Export data as CSV for further analysis

## API Endpoints

- `GET /api/results` - Query results with filters
- `GET /api/results/:id` - Get single test result
- `GET /api/results/meta/versions` - Get list of all versions
- `GET /api/results/meta/comparison` - Compare performance across versions
- `GET /api/health` - Health check

## Environment Variables

- `MONGODB_CONNECTION_STRING` - MongoDB connection string
- `MONGODB_DATABASE_NAME` - Database name (default: benchmark_results)
- `MONGODB_COLLECTION_NAME` - Collection name (default: test_runs)
- `PORT` - Server port (default: 3000)
