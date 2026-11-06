"""Validate catalog references and declared implementation paths, not software completeness."""
import json
from pathlib import Path


def validate(value, root):
    components = {item["id"]: item for item in value["components"]}
    disciplines = {item["id"]: item for item in value["disciplines"]}
    assert len(value["components"]) == len(components) == 100
    assert len(value["disciplines"]) == len(disciplines) == 100
    assert set(components) == {f"C{i:03}" for i in range(1, 101)}
    assert set(disciplines) == {f"D{i:03}" for i in range(1, 101)}
    assert len({d["name"] for d in disciplines.values()}) == 100
    visiting, visited = set(), set()

    def visit(identifier):
        assert identifier not in visiting, "dependency cycle"
        if identifier in visited:
            return
        visiting.add(identifier)
        for dependency in components[identifier]["depends_on"]:
            assert dependency in components, "unknown dependency"
            visit(dependency)
        visiting.remove(identifier)
        visited.add(identifier)

    partial = 0
    for identifier, item in components.items():
        visit(identifier)
        assert identifier == "C001" or item["depends_on"], "unconnected root"
        for key in ("name", "inputs", "outputs", "acceptance", "technology_candidate", "implementation_scope"):
            assert isinstance(item[key], str) and item[key].strip()
        assert item["disciplines"]
        for discipline in item["disciplines"]:
            assert identifier in disciplines[discipline]["applied_to"]
        assert item["status"] in ("planned", "bounded_partial")
        if item["status"] == "planned":
            assert item["implementation"] is None
        else:
            path = (root / item["implementation"]).resolve()
            assert path.is_relative_to(root.resolve()) and path.is_file()
            partial += 1
    for identifier, item in disciplines.items():
        assert item["applied_to"] and item["deliverable"] and item["competency_check"]
        for component in item["applied_to"]:
            assert identifier in components[component]["disciplines"]
    assert value["fully_completed_components"] == 0
    return {"catalog_valid": True, "components": 100, "disciplines": 100,
            "bounded_partial_components": partial, "planned_components": 100 - partial,
            "fully_completed_components": 0, "dependency_graph_acyclic": True,
            "runtime_integration_of_planned_components_verified": False}


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(validate(json.loads((root / "docs/operational_catalog_100.json").read_text()), root), indent=2))
