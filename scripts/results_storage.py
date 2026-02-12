#!/usr/bin/env python3
"""
MongoDB results storage module for benchmark test results.
Handles connection to MongoDB (cloud or local) and storage of test run results.
"""

import pymongo
from pymongo import MongoClient
from datetime import datetime
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)

class ResultsStorage:
    """Manages MongoDB connection and storage of benchmark results."""
    
    def __init__(self, connection_string: str, database_name: str = "benchmark_results", 
                 collection_name: str = "test_runs"):
        """
        Initialize results storage.
        
        Args:
            connection_string: MongoDB connection string (e.g., mongodb+srv://...)
            database_name: Name of the database to use
            collection_name: Name of the collection to store results
        """
        self.connection_string = connection_string
        self.database_name = database_name
        self.collection_name = collection_name
        self.client: Optional[MongoClient] = None
        self.db = None
        self.collection = None
        
    def connect(self) -> bool:
        """
        Connect to MongoDB.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.client = MongoClient(self.connection_string, serverSelectionTimeoutMS=5000)
            # Test connection
            self.client.admin.command('ping')
            self.db = self.client[self.database_name]
            self.collection = self.db[self.collection_name]
            
            # Create indexes for better query performance
            self._create_indexes()
            
            logger.info(f"Connected to MongoDB: {self.database_name}.{self.collection_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            return False
    
    def _create_indexes(self):
        """Create indexes on commonly queried fields."""
        try:
            # Index on timestamp for time-based queries
            self.collection.create_index("timestamp")
            # Index on database type for filtering
            self.collection.create_index("database.type")
            # Index on database version for version comparisons
            self.collection.create_index("database.version")
            # Index on test_run_id for grouping test runs
            self.collection.create_index("test_run_id")
            # Compound index for common queries
            self.collection.create_index([("database.type", 1), ("timestamp", -1)])
            logger.info("MongoDB indexes created successfully")
        except Exception as e:
            logger.warning(f"Failed to create indexes (may already exist): {e}")
    
    def store_test_result(self, result_document: Dict[str, Any]) -> Optional[str]:
        """
        Store a single test run result.
        
        Args:
            result_document: Dictionary containing test result data
            
        Returns:
            Inserted document _id as string, or None if failed
        """
        if self.collection is None:
            logger.error("Not connected to MongoDB. Call connect() first.")
            return None
        
        try:
            # Ensure timestamp is a datetime object
            if isinstance(result_document.get('timestamp'), str):
                result_document['timestamp'] = datetime.fromisoformat(result_document['timestamp'])
            elif not isinstance(result_document.get('timestamp'), datetime):
                result_document['timestamp'] = datetime.now()
            
            # Insert document
            result = self.collection.insert_one(result_document)
            logger.info(f"Stored test result: {result.inserted_id}")
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"Failed to store test result: {e}")
            return None
    
    def get_test_results(self, filters: Optional[Dict[str, Any]] = None, 
                        limit: Optional[int] = None, 
                        sort: Optional[List[tuple]] = None) -> List[Dict[str, Any]]:
        """
        Query test results with optional filters.
        
        Args:
            filters: MongoDB query filter dictionary
            limit: Maximum number of results to return
            sort: List of (field, direction) tuples for sorting
            
        Returns:
            List of result documents
        """
        if self.collection is None:
            logger.error("Not connected to MongoDB. Call connect() first.")
            return []
        
        try:
            query = self.collection.find(filters or {})
            
            if sort:
                query = query.sort(sort)
            else:
                # Default sort by timestamp descending
                query = query.sort("timestamp", -1)
            
            if limit:
                query = query.limit(limit)
            
            results = list(query)
            # Convert ObjectId to string for JSON serialization
            for result in results:
                result['_id'] = str(result['_id'])
            
            return results
        except Exception as e:
            logger.error(f"Failed to query test results: {e}")
            return []
    
    def get_test_result_by_id(self, result_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a single test result by ID.
        
        Args:
            result_id: MongoDB document _id as string
            
        Returns:
            Result document or None if not found
        """
        if self.collection is None:
            logger.error("Not connected to MongoDB. Call connect() first.")
            return None
        
        try:
            from bson import ObjectId
            result = self.collection.find_one({"_id": ObjectId(result_id)})
            if result:
                result['_id'] = str(result['_id'])
            return result
        except Exception as e:
            logger.error(f"Failed to get test result by ID: {e}")
            return None
    
    def get_versions(self) -> Dict[str, List[str]]:
        """
        Get list of all unique database and client versions in the collection.
        
        Returns:
            Dictionary with 'database_versions' and 'client_versions' lists
        """
        if self.collection is None:
            logger.error("Not connected to MongoDB. Call connect() first.")
            return {"database_versions": [], "client_versions": []}
        
        try:
            # Get unique database versions
            db_versions = self.collection.distinct("database.version")
            # Get unique client versions
            client_versions = self.collection.distinct("client.version")
            
            return {
                "database_versions": sorted(db_versions),
                "client_versions": sorted(client_versions)
            }
        except Exception as e:
            logger.error(f"Failed to get versions: {e}")
            return {"database_versions": [], "client_versions": []}
    
    def close(self):
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed")


def connect_to_mongodb(connection_string: str, database_name: str = "benchmark_results",
                      collection_name: str = "test_runs") -> Optional[ResultsStorage]:
    """
    Convenience function to create and connect to MongoDB.
    
    Args:
        connection_string: MongoDB connection string
        database_name: Name of the database
        collection_name: Name of the collection
        
    Returns:
        ResultsStorage instance if successful, None otherwise
    """
    storage = ResultsStorage(connection_string, database_name, collection_name)
    if storage.connect():
        return storage
    return None
