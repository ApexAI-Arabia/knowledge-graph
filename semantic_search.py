
import re
from getpass import getpass

from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer


URI = "bolt://127.0.0.1:7687"
USERNAME = "neo4j"

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
INDEX_NAME = "function_embedding"
DIMENSIONS = 384
TOP_K = 10


def build_function_text(function):
    """Build searchable text from a Function node."""

    parts = [
        function.get("name") or "",
        function.get("qualified_name") or "",
        function.get("signature") or "",
        function.get("return_type") or "",
        " ".join(function.get("parameters") or []),
        function.get("parent_class") or "",
        function.get("parent_function") or "",
    ]

    return " ".join(str(part) for part in parts if part)


def create_embeddings(session, model):
    """Generate and save embeddings for all Function nodes."""

    records = session.run("""
        MATCH (f:Function)
        RETURN
            f.id AS id,
            f.name AS name,
            f.qualified_name AS qualified_name,
            f.signature AS signature,
            f.return_type AS return_type,
            f.parameters AS parameters,
            f.parent_class AS parent_class,
            f.parent_function AS parent_function
    """).data()

    print(f"Generating embeddings for {len(records)} functions...")

    batch_size = 100

    for start in range(0, len(records), batch_size):
        batch = records[start:start + batch_size]

        texts = [build_function_text(row) for row in batch]

        vectors = model.encode(
            texts,
            normalize_embeddings=True
        ).tolist()

        rows = [
            {
                "id": row["id"],
                "embedding": vector,
            }
            for row, vector in zip(batch, vectors)
        ]

        session.run("""
            UNWIND $rows AS row
            MATCH (f:Function {id: row.id})
            SET f.embedding = row.embedding
        """, rows=rows).consume()

        print(
            f"Processed {min(start + batch_size, len(records))}"
            f" / {len(records)}"
        )

    print("Embeddings saved successfully.")


def create_vector_index(session):
    """Create a vector index for Function embeddings."""

    session.run(f"""
        CREATE VECTOR INDEX {INDEX_NAME} IF NOT EXISTS
        FOR (f:Function)
        ON (f.embedding)
        OPTIONS {{
            indexConfig: {{
                `vector.dimensions`: {DIMENSIONS},
                `vector.similarity_function`: 'cosine'
            }}
        }}
    """).consume()

    session.run(
        "CALL db.awaitIndex($index_name, 300)",
        index_name=INDEX_NAME
    ).consume()

    print("Vector index is ready.")


def get_context(session, function_id):
    """Retrieve the function, its owner, component, and dependencies."""

    result = session.run("""
        MATCH (f:Function {id: $function_id})

        OPTIONAL MATCH (f)-[:NESTED_IN]->(parent:Function)

        WITH f, coalesce(parent, f) AS owner

        OPTIONAL MATCH (c1:Component)-[:HAS_FUNCTION]->(owner)

        OPTIONAL MATCH
            (c2:Component)-[:CONTAINS]->(:Class)-[:DEFINES]->(owner)

        WITH f, owner, coalesce(c1, c2) AS component

        OPTIONAL MATCH (component)-[:DEPENDS_ON]->(dep:Component)

        RETURN
            f.name AS function,
            f.qualified_name AS qualified_name,
            f.signature AS signature,
            owner.qualified_name AS parent_function,
            component.name AS component,
            collect(DISTINCT dep.name) AS dependencies
    """, function_id=function_id).single()

    return dict(result) if result else {}


def hybrid_search(session, model, user_query):
    """Combine vector search and keyword search."""

    query_vector = model.encode(
        user_query,
        normalize_embeddings=True
    ).tolist()

    # Semantic search using vector similarity.
    vector_results = session.run("""
        CALL db.index.vector.queryNodes(
            $index_name,
            $top_k,
            $embedding
        )
        YIELD node, score

        RETURN node.id AS id, score
    """,
        index_name=INDEX_NAME,
        top_k=TOP_K,
        embedding=query_vector
    ).data()

    # Keyword search using query terms.
    terms = [
        term.lower()
        for term in re.findall(r"\w+", user_query)
        if len(term) >= 3
    ]

    keyword_results = []

    if terms:
        keyword_results = session.run("""
            MATCH (f:Function)

            WHERE any(
                term IN $terms
                WHERE
                    toLower(coalesce(f.name, '')) CONTAINS term
                    OR toLower(coalesce(f.qualified_name, '')) CONTAINS term
                    OR toLower(coalesce(f.signature, '')) CONTAINS term
                    OR toLower(coalesce(f.return_type, '')) CONTAINS term
            )

            RETURN f.id AS id
            LIMIT 50
        """, terms=terms).data()

    # Merge results and avoid duplicates.
    combined = {}

    for row in vector_results:
        combined[row["id"]] = {
            "id": row["id"],
            "vector_score": row["score"],
            "keyword_match": False,
        }

    for row in keyword_results:
        function_id = row["id"]

        if function_id not in combined:
            combined[function_id] = {
                "id": function_id,
                "vector_score": 0,
                "keyword_match": True,
            }
        else:
            combined[function_id]["keyword_match"] = True

    # Give keyword matches a ranking boost.
    results = list(combined.values())

    for result in results:
        result["hybrid_score"] = (
            result["vector_score"]
            + (0.15 if result["keyword_match"] else 0)
        )

    results.sort(
        key=lambda item: item["hybrid_score"],
        reverse=True
    )

    return results[:TOP_K]


def main():
    password = getpass("Enter Neo4j password: ")

    print("Loading embedding model...")
    model = SentenceTransformer(MODEL_NAME)

    driver = GraphDatabase.driver(
        URI,
        auth=(USERNAME, password)
    )

    try:
        driver.verify_connectivity()

        with driver.session(database="neo4j") as session:

            # Generate embeddings and create the vector index.
            create_embeddings(session, model)
            create_vector_index(session)

            print("\nHybrid Search is ready.")

            while True:
                user_query = input(
                    "\nEnter a capability to search "
                    "(or type exit): "
                ).strip()

                if user_query.lower() == "exit":
                    break

                if not user_query:
                    continue

                results = hybrid_search(
                    session,
                    model,
                    user_query
                )

                if not results:
                    print("No matching functions found.")
                    continue

                print("\nSearch Results")

                for number, item in enumerate(results, start=1):
                    context = get_context(session, item["id"])

                    print(f"\nResult {number}")
                    print(f"Function: {context.get('function')}")
                    print(
                        f"Qualified name: "
                        f"{context.get('qualified_name')}"
                    )
                    print(f"Signature: {context.get('signature')}")
                    print(f"Component: {context.get('component')}")
                    print(
                        f"Parent: "
                        f"{context.get('parent_function')}"
                    )
                    print(
                        f"Dependencies: "
                        f"{context.get('dependencies')}"
                    )
                    print(
                        f"Vector score: "
                        f"{item['vector_score']:.4f}"
                    )
                    print(
                        f"Keyword match: "
                        f"{item['keyword_match']}"
                    )
                    print(
                        f"Hybrid score: "
                        f"{item['hybrid_score']:.4f}"
                    )

    finally:
        driver.close()


if __name__ == "__main__":
    main()
