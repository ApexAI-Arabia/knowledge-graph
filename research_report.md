# Building a Component Knowledge Graph for Automated Architecture Assembly

## Author

***Yasmin Kasem***

B.Sc. in Physics, Mansoura University

---



## 1. Project Overview

This project explores the use of Knowledge Graphs to represent software components, their internal structure, dependencies, and relationships.

The goal is to support automated architecture assembly through graph-based retrieval and Context Bundle construction.

## 2. Technology Stack

- Python
- Python AST
- Neo4j
- Cypher
- Sentence Transformers
- all-MiniLM-L6-v2
- Git
- GitHub

## 3. Dataset

Two open-source Python repositories were selected:

- FastAPI: https://github.com/fastapi/fastapi
- Pydantic: https://github.com/pydantic/pydantic

The repositories were cloned locally and analyzed using a custom Python AST extractor.

## 4. Knowledge Graph Design

The ontology includes the following node types:

- Repository
- Component
- Class
- Function
- API
- Schema
- Documentation

The graph represents relationships such as:

- EXPOSES
- CONTAINS
- DEFINES
- HAS_FUNCTION
- DEPENDS_ON
- CALLS
- USES_TYPE
- IMPLEMENTS
- DOCUMENTED_BY
- PROVIDES_API
- NESTED_IN

## 5. Data Extraction and Ingestion

A Python AST-based extractor was developed to identify:

- Python modules
- Classes
- Functions
- Nested functions
- Function parameters and signatures
- Return type annotations
- Imports and dependencies

The extracted information was stored in JSON and ingested into Neo4j.

### Ingestion Results

| Entity | Count |
|---|---:|
| Repositories | 2 |
| Components | 107 |
| Classes | 312 |
| Functions | 1541 |
| Class functions | 945 |
| Module functions | 487 |
| Nested functions | 109 |
| Dependencies | 117 |

The graph also contains one sample repository and sample entities from the initial database setup. Therefore, raw Neo4j node counts include these additional records.

## 6. Retrieval Prototype

A retrieval prototype was implemented using Cypher queries.

It supports:

- Component lookup
- Class and function retrieval
- Dependency traversal
- Nested function traversal
- Keyword-based capability search

## 7. Semantic and Hybrid Retrieval

Sentence Transformers was used to generate 384-dimensional embeddings for 1542 Function nodes.

The selected model was:

all-MiniLM-L6-v2

A Neo4j vector index was created to support semantic retrieval.

The hybrid retrieval approach combines:

1. Vector similarity.
2. Keyword matching.
3. A combined ranking score.

### Test 1: Middleware Handling

The query "middleware handling" returned relevant FastAPI functions, including:

- FastAPI.middleware
- FastAPI.middleware.decorator
- FastAPI.build_middleware_stack
- AsyncExitStackMiddleware.__call__
- ExceptionTelemetryMiddleware.__call__

### Test 2: Data Validation and Serialization

The query "data validation and serialization" returned relevant functions from both repositories, including:

- serialize_sequence_value
- serialize_response
- ModelField.serialize_json
- field_serializer
- IPvAnyNetwork._validate

These tests demonstrate that semantic retrieval can identify relevant functions even when their names do not directly match the query.

## 8. Context Bundle Construction

The prototype uses the retrieved component as a root node.

It collects:

- Related classes
- Functions and methods
- Nested functions
- Direct dependencies
- Relevant code metadata

This information forms a Context Bundle that can be passed to a downstream architecture assembly system.

## 9. Limitations

The current prototype has several limitations:

- Relative imports are not fully resolved.
- Function-to-component mapping needs improvement for some functions.
- API, Schema, and Documentation extraction is not fully implemented.
- CALLS relationships are not yet extracted.
- The vector query uses a deprecated Neo4j procedure and should be migrated to the newer SEARCH syntax.
- The current retrieval tests use a limited number of capability queries.

## 10. Future Work

### Automatic Graph Updates

GitHub webhooks or GitHub Actions could trigger incremental ingestion whenever repository code changes.

### Optimal Graph Granularity

Further experiments should compare repository-level, module-level, class-level, and function-level representations.

### Documentation Integration

Documentation can be divided into semantic chunks and linked to the corresponding code entities through DOCUMENTED_BY relationships.

### Improved Retrieval

Future work could combine graph traversal, vector similarity, and reranking to improve retrieval quality.

## 11. Conclusion

The project demonstrates a working pipeline for extracting software structure from Python repositories, representing it as a Knowledge Graph, and retrieving relevant functions through keyword and semantic search.

The prototype provides a foundation for building Context Bundles that support automated software architecture assembly.