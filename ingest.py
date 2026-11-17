
import json
from pathlib import Path
from getpass import getpass
from neo4j import GraphDatabase

URI = "bolt://127.0.0.1:7687"
USERNAME = "neo4j"

REPOSITORIES = {
    "fastapi": "https://github.com/fastapi/fastapi",
    "pydantic": "https://github.com/pydantic/pydantic",
}


# Delete the previous FastAPI and Pydantic graph.
# The auth-service sample graph will remain untouched.
def clean_old_graph(tx):
    query = """
    MATCH (n)
    WHERE
        (n:Repository AND n.name IN $repo_names)
        OR (
            n:Component
            AND any(prefix IN $prefixes WHERE n.id STARTS WITH prefix)
        )
        OR (
            n:Class
            AND any(prefix IN $prefixes WHERE n.id STARTS WITH prefix)
        )
        OR (
            n:Function
            AND any(prefix IN $prefixes WHERE n.id STARTS WITH prefix)
        )
    DETACH DELETE n
    """

    tx.run(
        query,
        repo_names=list(REPOSITORIES.keys()),
        prefixes=["fastapi:", "pydantic:"]
    ).consume()


def create_repositories(tx, repositories):
    query = """
    UNWIND $rows AS row
    MERGE (r:Repository {id: row.id})
    SET r.name = row.name,
        r.url = row.url,
        r.language = row.language
    """

    tx.run(query, rows=repositories).consume()


def create_components(tx, components):
    query = """
    UNWIND $rows AS row
    MATCH (r:Repository {id: row.repo_id})
    MERGE (c:Component {id: row.id})
    SET c.name = row.name,
        c.path = row.path
    MERGE (r)-[:EXPOSES]->(c)
    """

    tx.run(query, rows=components).consume()


def create_dependencies(tx, dependencies):
    query = """
    UNWIND $rows AS row
    MATCH (source:Component {id: row.source_id})
    MATCH (target:Component {id: row.target_id})
    MERGE (source)-[:DEPENDS_ON]->(target)
    """

    tx.run(query, rows=dependencies).consume()


def create_classes(tx, classes):
    query = """
    UNWIND $rows AS row
    MATCH (c:Component {id: row.component_id})
    MERGE (cl:Class {id: row.id})
    SET cl.name = row.name,
        cl.line = row.line,
        cl.bases = row.bases,
        cl.scope_id = row.scope_id,
        cl.scope_key = row.scope_key,
        cl.qualified_name = row.qualified_name,
        cl.parent_scope_id = row.parent_scope_id,
        cl.parent_class = row.parent_class,
        cl.parent_function = row.parent_function,
        cl.decorators = row.decorators
    MERGE (c)-[:CONTAINS]->(cl)
    """

    tx.run(query, rows=classes).consume()


def create_functions(tx, functions):
    query = """
    UNWIND $rows AS row
    MERGE (f:Function {id: row.id})
    SET f.name = row.name,
        f.line = row.line,
        f.signature = row.signature,
        f.return_type = row.return_type,
        f.is_async = row.is_async,
        f.parameters = row.parameters,
        f.scope_id = row.scope_id,
        f.scope_key = row.scope_key,
        f.qualified_name = row.qualified_name,
        f.parent_scope_id = row.parent_scope_id,
        f.parent_scope_key = row.parent_scope_key,
        f.parent_class = row.parent_class,
        f.parent_function = row.parent_function,
        f.decorators = row.decorators
    """

    tx.run(query, rows=functions).consume()


def create_class_function_links(tx, functions):
    query = """
    UNWIND $rows AS row
    MATCH (cl:Class {id: row.class_id})
    MATCH (f:Function {id: row.id})
    MERGE (cl)-[:DEFINES]->(f)
    """

    tx.run(query, rows=functions).consume()


def create_module_function_links(tx, functions):
    query = """
    UNWIND $rows AS row
    MATCH (c:Component {id: row.component_id})
    MATCH (f:Function {id: row.id})
    MERGE (c)-[:HAS_FUNCTION]->(f)
    """

    tx.run(query, rows=functions).consume()


def create_nested_function_links(tx, functions):
    query = """
    UNWIND $rows AS row
    MATCH (child:Function {scope_key: row.scope_key})
    MATCH (parent:Function {scope_key: row.parent_scope_key})
    MERGE (child)-[:NESTED_IN]->(parent)
    """

    tx.run(query, rows=functions).consume()


def resolve_module(module, repo_name, module_lookup):
    if not module:
        return None

    parts = module.split(".")

    if parts[0] != repo_name:
        return None

    return module_lookup.get(module)


def main():
    password = getpass("Enter Neo4j password: ")

    with open("ast_results.json", encoding="utf-8") as file:
        ast_data = json.load(file)

    repositories = [
        {
            "id": f"repo_{name}",
            "name": name,
            "url": url,
            "language": "Python",
        }
        for name, url in REPOSITORIES.items()
    ]

    components = []
    classes = []
    functions = []

    class_functions = []
    module_functions = []
    nested_functions = []

    dependencies = []
    module_lookup = {}

    # Build components, classes, and functions.
    for item in ast_data:
        repo_name = item["repository"]
        file_path = Path(item["file_path"]).as_posix()
        component_id = f"{repo_name}:{file_path}"

        components.append({
            "id": component_id,
            "repo_id": f"repo_{repo_name}",
            "name": Path(file_path).stem,
            "path": file_path,
        })

        # Map class scope IDs to their graph IDs.
        class_scope_lookup = {}
        class_name_lookup = {}

        for cls in item.get("classes", []):
            scope_id = cls["scope_id"]
            scope_key = f"{repo_name}:{scope_id}"

            class_id = f"{repo_name}:{scope_id}"

            class_scope_lookup[scope_id] = class_id
            class_name_lookup[cls["name"]] = class_id

            classes.append({
                "id": class_id,
                "component_id": component_id,
                "name": cls["name"],
                "line": cls["line"],
                "bases": cls.get("bases", []),
                "scope_id": scope_id,
                "scope_key": scope_key,
                "qualified_name": cls.get("qualified_name"),
                "parent_scope_id": cls.get("parent_scope_id"),
                "parent_class": cls.get("parent_class"),
                "parent_function": cls.get("parent_function"),
                "decorators": cls.get("decorators", []),
            })

        for func in item.get("functions", []):
            scope_id = func["scope_id"]
            scope_key = f"{repo_name}:{scope_id}"

            parent_scope_id = func.get("parent_scope_id")
            parent_scope_key = (
                f"{repo_name}:{parent_scope_id}"
                if parent_scope_id else None
            )

            function_id = f"{repo_name}:{scope_id}"

            function_name = func["name"]
            parameters = func.get("parameters", [])

            function_data = {
                "id": function_id,
                "name": function_name,
                "line": func["line"],
                "signature": (
                    f"{function_name}({', '.join(parameters)})"
                ),
                "return_type": func.get("return_type"),
                "is_async": func.get("is_async", False),
                "parameters": parameters,
                "scope_id": scope_id,
                "scope_key": scope_key,
                "qualified_name": func.get("qualified_name"),
                "parent_scope_id": parent_scope_id,
                "parent_scope_key": parent_scope_key,
                "parent_class": func.get("parent_class"),
                "parent_function": func.get("parent_function"),
                "decorators": func.get("decorators", []),
            }

            functions.append(function_data)

            parent_class = func.get("parent_class")
            parent_function = func.get("parent_function")

            # Nested function inside another function.
            if parent_function is not None:
                nested_functions.append({
                    "scope_key": scope_key,
                    "parent_scope_key": parent_scope_key,
                })

            # Direct method inside a class.
            elif parent_class is not None:
                class_id = class_scope_lookup.get(parent_scope_id)

                # Fallback for cases where the parent scope is unavailable.
                if not class_id:
                    class_id = class_name_lookup.get(parent_class)

                if class_id:
                    class_functions.append({
                        "id": function_id,
                        "class_id": class_id,
                    })

            # Function directly inside a module.
            else:
                module_functions.append({
                    "id": function_id,
                    "component_id": component_id,
                })

    # Build module lookup for dependency resolution.
    for item in ast_data:
        repo_name = item["repository"]
        file_path = Path(item["file_path"])

        repo_root = Path("repositories") / repo_name
        relative_path = file_path.relative_to(repo_root)

        module_parts = list(relative_path.with_suffix("").parts)

        # Remove the inner package directory.
        if module_parts and module_parts[0] == repo_name:
            module_parts.pop(0)

        # Handle package __init__.py files.
        if module_parts and module_parts[-1] == "__init__":
            module_parts.pop()

        module_name = ".".join(module_parts)

        if module_name:
            module_lookup[f"{repo_name}.{module_name}"] = (
                f"{repo_name}:{file_path.as_posix()}"
            )

    # Resolve internal imports.
    for item in ast_data:
        repo_name = item["repository"]

        source_id = (
            f"{repo_name}:{Path(item['file_path']).as_posix()}"
        )

        for imported in item.get("imports", []):
            # Relative imports are not handled in this version.
            if imported.get("level", 0) != 0:
                continue

            module = imported.get("module")

            if not module:
                continue

            target_id = resolve_module(
                module, repo_name, module_lookup
            )

            # Handle: from fastapi import routing
            if (
                not target_id
                and imported.get("type") == "from_import"
            ):
                for name_info in imported.get("names", []):
                    candidate = f"{module}.{name_info['name']}"

                    target_id = resolve_module(
                        candidate, repo_name, module_lookup
                    )

                    if target_id:
                        break

            if target_id and target_id != source_id:
                dependencies.append({
                    "source_id": source_id,
                    "target_id": target_id,
                })

    # Remove duplicate dependencies.
    unique_dependencies = {
        (row["source_id"], row["target_id"])
        for row in dependencies
    }

    dependencies = [
        {
            "source_id": source,
            "target_id": target,
        }
        for source, target in unique_dependencies
    ]

    # Connect to Neo4j and ingest the graph.
    driver = GraphDatabase.driver(
        URI,
        auth=(USERNAME, password)
    )

    try:
        driver.verify_connectivity()

        with driver.session(database="neo4j") as session:

            # Remove the old code graph before rebuilding it.
            session.execute_write(clean_old_graph)

            session.execute_write(
                create_repositories, repositories
            )

            session.execute_write(
                create_components, components
            )

            if classes:
                session.execute_write(
                    create_classes, classes
                )

            if functions:
                session.execute_write(
                    create_functions, functions
                )

            if class_functions:
                session.execute_write(
                    create_class_function_links, class_functions
                )

            if module_functions:
                session.execute_write(
                    create_module_function_links, module_functions
                )

            if nested_functions:
                session.execute_write(
                    create_nested_function_links, nested_functions
                )

            if dependencies:
                session.execute_write(
                    create_dependencies, dependencies
                )

        print("\nIngestion completed!")
        print(f"Repositories: {len(repositories)}")
        print(f"Components: {len(components)}")
        print(f"Classes: {len(classes)}")
        print(f"Functions: {len(functions)}")
        print(f"Class functions: {len(class_functions)}")
        print(f"Module functions: {len(module_functions)}")
        print(f"Nested functions: {len(nested_functions)}")
        print(f"Dependencies: {len(dependencies)}")

    finally:
        driver.close()


if __name__ == "__main__":
    main()
