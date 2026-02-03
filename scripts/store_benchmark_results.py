#!/usr/bin/env python3
"""
Helper script to parse benchmark output and store results in MongoDB.
Used by test.sh to send Docker-based test results to the results database.
"""

import sys
import re
import os
import argparse
import configparser
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import uuid

# Add scripts directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from results_storage import connect_to_mongodb, ResultsStorage


def parse_benchmark_output(output: str, db_type: str, num_docs: int = 10000) -> list:
    """
    Parse Java benchmark output and extract results.

    Args:
        output: Raw stdout from Java benchmark
        db_type: Database type (mongodb, postgresql, etc.)
        num_docs: Number of documents in test (for throughput calculation)

    Returns:
        List of parsed result dictionaries
    """
    results = []

    # Pattern for insertion results
    # "Best time to insert 10000 documents with 100B payload in 1 attribute into indexed: 123ms"
    # "Time taken to insert 10000 documents with 100B payload in 1 attribute into nonindexed: 456ms"
    insert_pattern = r"(?:Best time|Time taken) to insert (\d+) documents with (\d+)B payload in (\d+) attributes? into (\w+): (\d+)ms"

    for match in re.finditer(insert_pattern, output):
        docs = int(match.group(1))
        payload_size = int(match.group(2))
        num_attrs = int(match.group(3))
        index_type = match.group(4)  # "indexed" or "nonindexed"
        time_ms = int(match.group(5))

        throughput = round(docs / (time_ms / 1000), 2) if time_ms > 0 else 0

        results.append({
            "type": "insert",
            "num_docs": docs,
            "payload_size": payload_size,
            "num_attributes": num_attrs,
            "indexed": index_type == "indexed",
            "time_ms": time_ms,
            "throughput": throughput
        })

    # Pattern for query results
    # "Best query time for 10000 ID's with 10 element link arrays...: 789ms"
    query_pattern = r"Best query time for (\d+) ID's with (\d+) element link arrays.*?: (\d+)ms"

    for match in re.finditer(query_pattern, output):
        queries = int(match.group(1))
        link_elements = int(match.group(2))
        time_ms = int(match.group(3))

        throughput = round(queries / (time_ms / 1000), 2) if time_ms > 0 else 0

        results.append({
            "type": "query",
            "queries_executed": queries,
            "link_elements": link_elements,
            "time_ms": time_ms,
            "throughput": throughput
        })

    # Pattern for realistic nested data
    # "Best time to insert 10000 documents with realistic nested data (~100B) into indexed: 123ms"
    realistic_pattern = r"(?:Best time|Time taken) to insert (\d+) documents with realistic nested data \(~(\d+)B\) into (\w+): (\d+)ms"

    for match in re.finditer(realistic_pattern, output):
        docs = int(match.group(1))
        payload_size = int(match.group(2))
        index_type = match.group(3)
        time_ms = int(match.group(4))

        throughput = round(docs / (time_ms / 1000), 2) if time_ms > 0 else 0

        results.append({
            "type": "insert",
            "num_docs": docs,
            "payload_size": payload_size,
            "num_attributes": "realistic",
            "indexed": index_type == "indexed",
            "time_ms": time_ms,
            "throughput": throughput
        })

    return results


def get_db_version_from_output(output: str, db_type: str) -> str:
    """Extract database version from benchmark output if available."""
    # Try to find version info in output
    version_patterns = {
        'mongodb': r'MongoDB version[:\s]+(\d+\.\d+\.\d+)',
        'documentdb': r'DocumentDB version[:\s]+(\d+\.\d+\.\d+)',
        'postgresql': r'PostgreSQL[:\s]+(\d+\.\d+)',
    }

    pattern = version_patterns.get(db_type.lower())
    if pattern:
        match = re.search(pattern, output, re.IGNORECASE)
        if match:
            return match.group(1)

    return "unknown"


def build_mongodb_document(parsed_result: Dict[str, Any], db_type: str,
                          test_run_id: str, db_version: str = "unknown") -> Dict[str, Any]:
    """
    Build a MongoDB document in the standard schema.

    Args:
        parsed_result: Parsed result from benchmark output
        db_type: Database type
        test_run_id: Unique identifier for this test run
        db_version: Database version string

    Returns:
        Document ready for MongoDB insertion
    """
    is_insert = parsed_result.get("type") == "insert"

    # Determine test type based on attributes
    num_attrs = parsed_result.get("num_attributes", 1)
    if num_attrs == "realistic":
        test_type = "realistic_nested"
    elif num_attrs == 1:
        test_type = "single_attr"
    else:
        test_type = "multi_attr"

    doc = {
        "timestamp": datetime.now(timezone.utc),
        "test_run_id": test_run_id,
        "database": {
            "type": db_type,
            "version": db_version
        },
        "client": {
            "library": "mongodb-driver-sync" if db_type in ["mongodb", "documentdb"] else f"{db_type}-jdbc",
            "version": "unknown"
        },
        "test_config": {
            "test_type": test_type,
            "payload_size": parsed_result.get("payload_size", 0),
            "indexed": parsed_result.get("indexed", False),
            "num_attributes": num_attrs if num_attrs != "realistic" else 0,
            "num_docs": parsed_result.get("num_docs", 10000)
        },
        "results": {
            "success": True
        },
        "source": "test.sh"  # Mark as coming from Docker test script
    }

    if is_insert:
        doc["results"]["insert_time_ms"] = parsed_result.get("time_ms")
        doc["results"]["insert_throughput"] = parsed_result.get("throughput")
    else:
        doc["results"]["query_time_ms"] = parsed_result.get("time_ms")
        doc["results"]["query_throughput"] = parsed_result.get("throughput")
        doc["test_config"]["query_links"] = parsed_result.get("link_elements", 0)

    return doc


def load_config() -> Optional[configparser.ConfigParser]:
    """Load configuration from benchmark_config.ini."""
    config = configparser.ConfigParser()

    # Try multiple config locations
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    config_paths = [
        os.path.join(project_root, 'config', 'benchmark_config.ini'),
        os.path.join(project_root, 'benchmark_config.ini'),
        os.path.join(script_dir, 'benchmark_config.ini'),
    ]

    for config_path in config_paths:
        if os.path.exists(config_path):
            config.read(config_path)
            return config

    return None


def main():
    parser = argparse.ArgumentParser(description='Store benchmark results in MongoDB')
    parser.add_argument('--db-type', required=True,
                       choices=['mongodb', 'documentdb', 'postgresql', 'yugabytedb', 'cockroachdb'],
                       help='Database type being tested')
    parser.add_argument('--db-version', default='unknown',
                       help='Database version')
    parser.add_argument('--test-run-id', default=None,
                       help='Test run identifier (auto-generated if not provided)')
    parser.add_argument('--num-docs', type=int, default=10000,
                       help='Number of documents in test')
    parser.add_argument('--input-file', '-f', default=None,
                       help='Read benchmark output from file instead of stdin')
    parser.add_argument('--dry-run', action='store_true',
                       help='Parse and show results without storing to MongoDB')
    parser.add_argument('--connection-string', default=None,
                       help='MongoDB connection string (overrides config file)')

    args = parser.parse_args()

    # Read benchmark output
    if args.input_file:
        with open(args.input_file, 'r') as f:
            output = f.read()
    else:
        output = sys.stdin.read()

    if not output.strip():
        print("Error: No benchmark output provided", file=sys.stderr)
        sys.exit(1)

    # Parse the output
    parsed_results = parse_benchmark_output(output, args.db_type, args.num_docs)

    if not parsed_results:
        print("Warning: No benchmark results found in output", file=sys.stderr)
        print("Output preview:", file=sys.stderr)
        print(output[:500] if len(output) > 500 else output, file=sys.stderr)
        sys.exit(0)

    print(f"Parsed {len(parsed_results)} benchmark results for {args.db_type}")

    # Generate test run ID if not provided
    test_run_id = args.test_run_id or f"test.sh-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"

    # Get database version from output if not provided
    db_version = args.db_version
    if db_version == 'unknown':
        db_version = get_db_version_from_output(output, args.db_type)

    # Build MongoDB documents
    documents = []
    for result in parsed_results:
        doc = build_mongodb_document(result, args.db_type, test_run_id, db_version)
        documents.append(doc)

        if args.dry_run:
            result_type = result.get("type", "unknown")
            time_ms = result.get("time_ms", 0)
            throughput = result.get("throughput", 0)
            print(f"  {result_type}: {time_ms}ms ({throughput:,.0f} ops/sec)")

    if args.dry_run:
        print(f"\nDry run - {len(documents)} documents would be stored")
        print(f"Test run ID: {test_run_id}")
        return

    # Get MongoDB connection string
    connection_string = args.connection_string
    database_name = "benchmark_results"
    collection_name = "test_runs"

    if not connection_string:
        config = load_config()
        if config:
            connection_string = config.get('results_storage', 'mongodb_connection_string', fallback=None)
            database_name = config.get('results_storage', 'database_name', fallback='benchmark_results')
            collection_name = config.get('results_storage', 'collection_name', fallback='test_runs')

    if not connection_string:
        print("Error: No MongoDB connection string provided", file=sys.stderr)
        print("Either:", file=sys.stderr)
        print("  1. Create config/benchmark_config.ini with [results_storage] section", file=sys.stderr)
        print("  2. Use --connection-string argument", file=sys.stderr)
        sys.exit(1)

    # Connect to MongoDB and store results
    storage = connect_to_mongodb(connection_string, database_name, collection_name)

    if not storage:
        print("Error: Failed to connect to MongoDB", file=sys.stderr)
        sys.exit(1)

    try:
        stored_count = 0
        for doc in documents:
            result_id = storage.store_test_result(doc)
            if result_id:
                stored_count += 1

        print(f"Stored {stored_count}/{len(documents)} results to MongoDB")
        print(f"Test run ID: {test_run_id}")
        print(f"Database: {database_name}.{collection_name}")

    finally:
        storage.close()


if __name__ == '__main__':
    main()
