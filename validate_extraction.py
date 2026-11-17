
import json

with open("ast_results.json", encoding="utf-8") as f:
    data = json.load(f)

all_scopes = {}
nested_functions = []
invalid_parents = []
duplicate_ids = []

for file in data:
    for scope in file["scopes"]:
        scope_id = scope["scope_id"]

        if scope_id in all_scopes:
            duplicate_ids.append(scope_id)

        all_scopes[scope_id] = scope

for file in data:
    for scope in file["scopes"]:
        parent_id = scope["parent_scope_id"]

        if parent_id and parent_id not in all_scopes:
            invalid_parents.append(scope)

    for function in file["functions"]:
        if function["parent_function"]:
            nested_functions.append(function)

print("Validation Results")
print("-------------------")
print("Unique scopes:", len(all_scopes))
print("Duplicate IDs:", len(duplicate_ids))
print("Invalid parents:", len(invalid_parents))
print("Nested functions:", len(nested_functions))

print("\nNested Function Samples:")

for function in nested_functions[:10]:
    print(
        function["qualified_name"],
        "-> Parent:",
        function["parent_function"]
    )
