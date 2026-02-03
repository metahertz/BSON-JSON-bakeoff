package com.mongodb;

import org.json.JSONObject;

import java.util.List;

public interface DatabaseOperations {
    void initializeDatabase(String connectionString);
    void dropAndCreateCollections(List<String> collectionNames);
    long insertDocuments(String collectionName, List<JSONObject> documents, int dataSize, boolean splitPayload);
    int queryDocumentsById(String collectionName, String id);
    int queryDocumentsByIdWithInCondition(String collectionName, JSONObject document);
    int queryDocumentsByIdUsingLookup(String collectionName, String id);

    /**
     * Get the average document size in bytes for the given collection.
     * For MongoDB, this returns BSON size. For Oracle, this returns OSON size.
     * @param collectionName The collection/table name
     * @return Average document size in bytes, or -1 if not supported or error
     */
    long getAverageDocumentSize(String collectionName);

    /**
     * Get the total number of documents in the collection.
     * Used for validation to verify insertion counts.
     * @param collectionName The collection/table name
     * @return Number of documents, or -1 if error
     */
    long getDocumentCount(String collectionName);

    /**
     * Validate that a document exists and matches expected content.
     * Used for sample validation after insertion.
     * @param collectionName The collection/table name
     * @param id The document ID to validate
     * @param expected The expected document content (at minimum, _id should match)
     * @return true if document exists and key fields match, false otherwise
     */
    boolean validateDocument(String collectionName, String id, JSONObject expected);

    void close();
}