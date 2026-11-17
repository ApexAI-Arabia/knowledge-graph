
import ast
import json
from pathlib import Path


REPOSITORIES = {
    "fastapi": Path("repositories/fastapi/fastapi"),
    "pydantic": Path("repositories/pydantic/pydantic"),
}


def extract_file(file_path, repo_name):
    source = file_path.read_text(encoding="utf-8")

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    file_id = f"{repo_name}:{file_path.as_posix()}"

    result = {
        "repository": repo_name,
        "file_path": file_path.as_posix(),
        "module_scope_id": f"{file_id}:module",
        "scopes": [],
        "classes": [],
        "functions": [],
        "imports": [],
    }

    module_scope = {
        "scope_id": result["module_scope_id"],
        "name": file_path.stem,
        "type": "module",
        "parent_scope_id": None,
        "qualified_name": file_path.stem,
        "line": 1,
    }

    result["scopes"].append(module_scope)

    def get_scope_info(scope_stack):
        return {
            "parent_scope_id": (
                scope_stack[-1]["scope_id"]
                if scope_stack else None
            ),
            "parent_class": next(
                (
                    scope["name"]
                    for scope in reversed(scope_stack)
                    if scope["type"] == "class"
                ),
                None,
            ),
            "parent_function": next(
                (
                    scope["name"]
                    for scope in reversed(scope_stack)
                    if scope["type"] == "function"
                ),
                None,
            ),
        }

    def get_qualified_name(scope_stack, name):
        parts = [
            scope["name"]
            for scope in scope_stack
            if scope["type"] != "module"
        ]
        parts.append(name)
        return ".".join(parts)

    def create_scope(node, scope_stack, scope_type):
        name = node.name

        qualified_name = get_qualified_name(
            scope_stack, name
        )

        parent_id = scope_stack[-1]["scope_id"]

        scope_id = (
            f"{file_id}:{scope_type}:"
            f"{qualified_name}:{node.lineno}"
        )

        scope = {
            "scope_id": scope_id,
            "name": name,
            "type": scope_type,
            "parent_scope_id": parent_id,
            "qualified_name": qualified_name,
            "line": node.lineno,
        }

        result["scopes"].append(scope)

        return scope

    def visit(node, scope_stack):

        if isinstance(node, ast.ClassDef):

            scope = create_scope(
                node, scope_stack, "class"
            )

            parent_info = get_scope_info(scope_stack)

            result["classes"].append({
                "name": node.name,
                "line": node.lineno,
                "scope_id": scope["scope_id"],
                "qualified_name": scope["qualified_name"],
                "parent_scope_id": parent_info["parent_scope_id"],
                "parent_class": parent_info["parent_class"],
                "parent_function": parent_info["parent_function"],
                "bases": [
                    ast.unparse(base)
                    for base in node.bases
                ],
                "decorators": [
                    ast.unparse(decorator)
                    for decorator in node.decorator_list
                ],
            })

            # Class headers are evaluated in the parent scope
            for child in (
                list(node.decorator_list)
                + list(node.bases)
                + [keyword.value for keyword in node.keywords]
            ):
                visit(child, scope_stack)

            # Class body belongs to the class scope
            for child in node.body:
                visit(child, scope_stack + [scope])

        elif isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef)
        ):

            scope = create_scope(
                node, scope_stack, "function"
            )

            parent_info = get_scope_info(scope_stack)

            all_parameters = (
                node.args.posonlyargs
                + node.args.args
                + node.args.kwonlyargs
            )

            if node.args.vararg:
                all_parameters.append(node.args.vararg)

            if node.args.kwarg:
                all_parameters.append(node.args.kwarg)

            result["functions"].append({
                "name": node.name,
                "line": node.lineno,
                "scope_id": scope["scope_id"],
                "qualified_name": scope["qualified_name"],
                "parent_scope_id": parent_info["parent_scope_id"],
                "parent_class": parent_info["parent_class"],
                "parent_function": parent_info["parent_function"],
                "is_async": isinstance(
                    node, ast.AsyncFunctionDef
                ),
                "return_type": (
                    ast.unparse(node.returns)
                    if node.returns else None
                ),
                "parameters": [
                    arg.arg for arg in all_parameters
                ],
                "decorators": [
                    ast.unparse(decorator)
                    for decorator in node.decorator_list
                ],
            })

            # Defaults, annotations and decorators belong
            # to the enclosing scope, not the function scope
            for decorator in node.decorator_list:
                visit(decorator, scope_stack)

            for default in (
                node.args.defaults + [
                    item for item in node.args.kw_defaults
                    if item is not None
                ]
            ):
                visit(default, scope_stack)

            for arg in all_parameters:
                if arg.annotation:
                    visit(arg.annotation, scope_stack)

            if node.returns:
                visit(node.returns, scope_stack)

            # Function body belongs to its own scope
            for child in node.body:
                visit(child, scope_stack + [scope])

        elif isinstance(node, ast.Import):

            for alias in node.names:
                result["imports"].append({
                    "module": alias.name,
                    "alias": alias.asname,
                    "type": "import",
                    **get_scope_info(scope_stack),
                })

        elif isinstance(node, ast.ImportFrom):

            result["imports"].append({
                "module": node.module,
                "level": node.level,
                "names": [
                    {
                        "name": alias.name,
                        "alias": alias.asname,
                    }
                    for alias in node.names
                ],
                "type": "from_import",
                **get_scope_info(scope_stack),
            })

        else:
            # Generic traversal handles if, loops, try,
            # with, match, exception handlers and other blocks
            for child in ast.iter_child_nodes(node):
                visit(child, scope_stack)

    # Start traversal from module scope
    for node in tree.body:
        visit(node, [module_scope])

    return result


def extract_repository(repo_name, repo_path):
    files_data = []

    for file_path in repo_path.rglob("*.py"):

        if any(
            part in {"tests", "__pycache__"}
            for part in file_path.parts
        ):
            continue

        data = extract_file(file_path, repo_name)

        if data is not None:
            files_data.append(data)

    return files_data


def main():
    all_results = []

    for repo_name, repo_path in REPOSITORIES.items():

        print(f"Analyzing {repo_name}...")

        repository_data = extract_repository(
            repo_name, repo_path
        )

        all_results.extend(repository_data)

        print(f"Files analyzed: {len(repository_data)}")

    output_path = Path("ast_results.json")

    output_path.write_text(
        json.dumps(
            all_results,
            indent=4,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print("\nResults saved to ast_results.json")

    total_scopes = sum(
        len(file["scopes"])
        for file in all_results
    )

    total_classes = sum(
        len(file["classes"])
        for file in all_results
    )

    total_functions = sum(
        len(file["functions"])
        for file in all_results
    )

    print(f"Total scopes: {total_scopes}")
    print(f"Total classes: {total_classes}")
    print(f"Total functions: {total_functions}")


if __name__ == "__main__":
    main()
