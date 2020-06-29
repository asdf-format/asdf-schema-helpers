from pathlib import Path
import re
import yaml
from urllib.parse import urljoin, urlparse


VALID_YAML_VERSIONS = {"1.1"}
VALID_FILE_FORMAT_VERSIONS = {"1.0.0"}

VALID_SCHEMA_FILENAME_RE = re.compile(r"[a-z0-9_]+-[0-9]+\.[0-9]+\.[0-9]+\.yaml")

METASCHEMA_ID = "http://stsci.edu/schemas/yaml-schema/draft-01"

YAML_TAG_RE = re.compile(r"![a-z/0-9_-]+-[0-9]+\.[0-9]+\.[0-9]")

DESCRIPTION_REF_RE = re.compile(r"\(ref:(.*?)\)")


def load_yaml(path):
    with path.open() as f:
        return yaml.safe_load(f.read())


def assert_yaml_header_and_footer(path):
    with path.open() as f:
        content = f.read()

    assert any(
        content.startswith(f"%YAML {v}\n---\n") for v in VALID_YAML_VERSIONS
    ), f"{path.name} must start with a %YAML directive with a supported version"

    assert content.endswith("\n...\n"), f"{path.name} must end with '...' followed by a single newline"


def split_id(schema_id):
    return schema_id.rsplit("-", 1)


def yaml_tag_to_id(yaml_tag):
    return "http://stsci.edu/schemas/asdf/" + yaml_tag.replace("!", "")


def tag_to_id(tag):
    assert tag.startswith("tag:stsci.edu:asdf/")

    return "http://stsci.edu/schemas/asdf/" + tag.split("tag:stsci.edu:asdf/")[-1]


def list_schema_paths(path):
    return sorted(p for p in path.glob("**/*.yaml") if not p.name.startswith("version_map-"))


def ref_to_id(schema_id, ref):
    return urljoin(schema_id, ref)


def list_refs(schema):
    refs = []
    if isinstance(schema, dict):
        for key, value in schema.items():
            if key == "$ref":
                refs.append(value)
            elif isinstance(value, dict) or isinstance(value, list):
                refs.extend(list_refs(value))
    elif isinstance(schema, list):
        for elem in schema:
            refs.extend(list_refs(elem))
    return refs


def list_example_ids(schema):
    if "examples" in schema:
        example_yaml_tags = set()
        for _, example in schema["examples"]:
            example_yaml_tags.update(YAML_TAG_RE.findall(example))
        return sorted({yaml_tag_to_id(yaml_tag) for yaml_tag in example_yaml_tags})
    else:
        return []


def list_description_ids(schema):
    result = set()
    if "description" in schema:
        for ref in DESCRIPTION_REF_RE.findall(schema["description"]):
            if not ref.startswith("http:"):
                ref = "http://stsci.edu/schemas/asdf/" + ref
            result.add(ref)
    return result


def tag_to_schema(schemas):
    result = {}
    for schema in schemas:
        if "tag" in schema:
            if schema["tag"] not in result:
                result[schema["tag"]] = []
            result[schema["tag"]].append(schema)
    return result


def id_to_schema(schemas):
    result = {}
    for schema in schemas:
        if "id" in schema:
            if schema["id"] not in result:
                result[schema["id"]] = []
            result[schema["id"]].append(schema)
    return result


def assert_schema_correct(path):
    """Assertion helper for schema checks"""
    import asdf

    __tracebackhide__ = True

    resolve = asdf.extension.default_extensions.resolver

    assert VALID_SCHEMA_FILENAME_RE.match(path.name) is not None, f"{path.name} is an invalid schema filename"

    assert_yaml_header_and_footer(path)

    schema = load_yaml(path)

    assert "$schema" in schema, f"{path.name} is missing $schema key"
    assert schema["$schema"] == METASCHEMA_ID, f"{path.name} has wrong $schema value (expected {METASCHEMA_ID})"

    assert "id" in schema, f"{path.name} is missing id key"

    resolved_path_from_id = Path(urlparse(resolve(schema["id"])).path).resolve()
    assert path.samefile(resolved_path_from_id)

    if "tag" in schema:
        resolved_path_from_tag = Path(urlparse(resolve(schema["tag"])).path).resolve()
        assert path.samefile(resolved_path_from_tag)

    assert "title" in schema, f"{path.name} is missing title key"
    assert len(schema["title"].strip()) > 0, f"{path.name} title must have content"

    assert "description" in schema, f"{path.name} is missing description key"
    assert len(schema["description"].strip()) > 0, f"{path.name} description must have content"

    # assert len(id_to_schema(schema["id"])) == 1, f"{path.name} does not have a unique id"

    # if "tag" in schema:
    #     assert len(tag_to_schema[schema["tag"]]) == 1, f"{path.name} does not have a unique tag"

    id_base, _ = split_id(schema["id"])
    for example_id in list_example_ids(schema):
        example_id_base, _ = split_id(example_id)
        if example_id_base == id_base and example_id != schema["id"]:
            assert False, f"{path.name} contains an example with an outdated tag"

    for description_id in list_description_ids(schema):
        if len(description_id.rsplit("-", 1)) > 1:
            description_id_base, _ = split_id(description_id)
            if description_id_base == id_base and description_id != schema["id"]:
                assert False, f"{path.name} descriptioon contains an outdated ref"
