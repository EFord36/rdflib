"""
JSON-LD Context Spec
"""
from __future__ import annotations

import json
from functools import wraps
from pathlib import Path
from typing import Any, Dict

from rdflib.namespace import PROV, XSD, Namespace
from rdflib.plugins.shared.jsonld import context, errors
from rdflib.plugins.shared.jsonld.context import Context


# exception utility (see also nose.tools.raises)
def _expect_exception(expected_error):
    def _try_wrapper(f):
        @wraps(f)
        def _try():
            try:
                f()
                assert e == expected_error  # noqa: F821
            except Exception as e:
                success = e == expected_error
            else:
                success = False
            assert success, "Expected %r" % expected_error

        return _try

    return _try_wrapper


def test_create_context():
    ctx = Context()
    ctx.add_term("label", "http://example.org/ns/label")
    term = ctx.terms.get("label")

    assert term.name == "label"
    assert ctx.find_term("http://example.org/ns/label") is term


def test_select_term_based_on_value_characteristics():
    ctx = Context()

    ctx.add_term("updated", "http://example.org/ns/updated")
    ctx.add_term(
        "updatedDate",
        "http://example.org/ns/updated",
        coercion="http://www.w3.org/2001/XMLSchema#date",
    )

    assert ctx.find_term("http://example.org/ns/updated").name == "updated"
    assert (
        ctx.find_term(
            "http://example.org/ns/updated",
            coercion="http://www.w3.org/2001/XMLSchema#date",
        ).name
        == "updatedDate"
    )

    # ctx.find_term('http://example.org/ns/title_sv', language='sv')

    # ctx.find_term('http://example.org/ns/authorList', container='@set')

    # ctx.find_term('http://example.org/ns/creator', reverse=True)


def test_getting_keyword_values_from_nodes():
    ctx = Context()
    assert ctx.get_id({"@id": "urn:x:1"}) == "urn:x:1"
    assert ctx.get_language({"@language": "en"}) == "en"


def test_parsing_a_context_expands_prefixes():
    ctx = Context(
        {
            "@vocab": "http://example.org/ns/",
            "x": "http://example.org/ns/",
            "label": "x:label",
            "x:updated": {"@type": "x:date"},
        }
    )

    term = ctx.terms.get("label")

    assert term.id == "http://example.org/ns/label"

    term = ctx.terms.get("x:updated")
    assert term.id == "http://example.org/ns/updated"
    assert term.type == "http://example.org/ns/date"

    # test_expanding_terms():
    assert ctx.expand("term") == "http://example.org/ns/term"
    assert ctx.expand("x:term") == "http://example.org/ns/term"

    # test_shrinking_iris():
    assert ctx.shrink_iri("http://example.org/ns/term") == "x:term"
    assert ctx.to_symbol("http://example.org/ns/term") == "term"


def test_resolving_iris():
    ctx = Context({"@base": "http://example.org/path/leaf"})
    assert ctx.resolve("/") == "http://example.org/"
    assert ctx.resolve("/trail") == "http://example.org/trail"
    assert ctx.resolve("../") == "http://example.org/"
    assert ctx.resolve("../../") == "http://example.org/"


def test_accessing_keyword_values_by_alias():
    ctx = Context({"iri": "@id", "lang": "@language"})
    assert ctx.get_id({"iri": "urn:x:1"}) == "urn:x:1"
    assert ctx.get_language({"lang": "en"}) == "en"

    # test_standard_keywords_still_work():
    assert ctx.get_id({"@id": "urn:x:1"}) == "urn:x:1"

    # test_representing_keywords_by_alias():
    assert ctx.id_key == "iri"
    assert ctx.lang_key == "lang"


def test_creating_a_subcontext():
    ctx = Context()
    ctx4 = ctx.subcontext({"lang": "@language"})
    assert ctx4.get_language({"lang": "en"}) == "en"


def test_prefix_like_vocab():
    ctx = Context({"@vocab": "ex:", "term": "ex:term"})
    term = ctx.terms.get("term")
    assert term.id == "ex:term"


# Mock external sources loading
SOURCES: Dict[str, Dict[str, Any]] = {}
# type error: Module "rdflib.plugins.shared.jsonld.context" does not explicitly export attribute "source_to_json"
_source_to_json = context.source_to_json  # type: ignore[attr-defined]


def _mock_source_loader(f):
    @wraps(f)
    def _wrapper():
        try:
            context.source_to_json = SOURCES.get
            f()
        finally:
            context.source_to_json = _source_to_json

    return _wrapper


@_mock_source_loader
def test_loading_contexts():
    # Given context data:
    source1 = "http://example.org/base.jsonld"
    source2 = "http://example.org/context.jsonld"
    SOURCES[source1] = {"@context": {"@vocab": "http://example.org/vocab/"}}
    SOURCES[source2] = {"@context": [source1, {"n": "name"}]}

    # Create a context:
    ctx = Context(source2)
    assert ctx.expand("n") == "http://example.org/vocab/name"

    # Context can be a list:
    ctx = Context([source2])
    assert ctx.expand("n") == "http://example.org/vocab/name"


@_mock_source_loader
def test_use_base_in_local_context():
    ctx = Context({"@base": "/local"})
    assert ctx.base == "/local"


@_mock_source_loader
def test_override_base():
    ctx = Context(
        base="http://example.org/app/data/item", source={"@base": "http://example.org/"}
    )
    assert ctx.base == "http://example.org/"


@_mock_source_loader
def test_resolve_relative_base():
    ctx = Context(base="http://example.org/app/data/item", source={"@base": "../"})
    assert ctx.base == "http://example.org/app/"
    assert ctx.resolve_iri("../other") == "http://example.org/other"


@_mock_source_loader
def test_set_null_base():
    ctx = Context(base="http://example.org/app/data/item", source={"@base": None})
    assert ctx.base is None
    assert ctx.resolve_iri("../other") == "../other"


@_mock_source_loader
def test_ignore_base_remote_context():
    ctx_url = "http://example.org/remote-base.jsonld"
    SOURCES[ctx_url] = {"@context": {"@base": "/remote"}}
    ctx = Context(ctx_url)
    assert ctx.base is None


@_expect_exception(errors.RECURSIVE_CONTEXT_INCLUSION)
@_mock_source_loader
def test_recursive_context_inclusion_error():
    ctx_url = "http://example.org/recursive.jsonld"
    SOURCES[ctx_url] = {"@context": ctx_url}
    ctx = Context(ctx_url)  # noqa: F841


@_expect_exception(errors.INVALID_REMOTE_CONTEXT)
@_mock_source_loader
def test_invalid_remote_context():
    ctx_url = "http://example.org/recursive.jsonld"
    SOURCES[ctx_url] = {"key": "value"}
    ctx = Context(ctx_url)  # noqa: F841


def test_file_source(tmp_path: Path) -> None:
    """
    A file URI source to `Context` gets processed correctly.
    """
    file = tmp_path / "context.jsonld"
    file.write_text(r"""{ "@context": { "ex": "http://example.com/" } }""")
    ctx = Context(source=file.as_uri())
    assert "http://example.com/" == ctx.terms["ex"].id


def test_dict_source(tmp_path: Path) -> None:
    """
    A dictionary source to `Context` gets processed correctly.
    """
    file = tmp_path / "context.jsonld"
    file.write_text(r"""{ "@context": { "ex": "http://example.com/" } }""")
    ctx = Context(source=[{"@context": file.as_uri()}])
    assert "http://example.com/" == ctx.terms["ex"].id


EG = Namespace("https://example.com/")

DIVERSE_CONTEXT = json.loads(
    """
        {
            "@context": {
                "ex": "https://example.com/",
                "generatedAt": { "@id": "http://www.w3.org/ns/prov#generatedAtTime", "@type": "http://www.w3.org/2001/XMLSchema#dateTime" },
                "graphMap": { "@id": "https://example.com/graphMap", "@container": ["@graph", "@id"] },
                "occupation_en": { "@id": "https://example.com/occupation", "@language": "en" },
                "children": { "@reverse": "https://example.com/parent" }
            }
        }
        """
)


def test_parsing() -> None:
    """
    A `Context` can be parsed from a dict.
    """
    ctx = Context(DIVERSE_CONTEXT)
    assert f"{EG}" == ctx.terms["ex"].id
    assert f"{PROV.generatedAtTime}" == ctx.terms["generatedAt"].id
    assert f"{XSD.dateTime}" == ctx.terms["generatedAt"].type
    assert f"{EG.graphMap}" == ctx.terms["graphMap"].id
    assert {"@graph", "@id"} == ctx.terms["graphMap"].container
    assert f"{EG.occupation}" == ctx.terms["occupation_en"].id
    assert "en" == ctx.terms["occupation_en"].language
    assert False is ctx.terms["occupation_en"].reverse
    assert True is ctx.terms["children"].reverse
    assert f"{EG.parent}" == ctx.terms["children"].id


def test_to_dict() -> None:
    """
    A `Context` can be converted to a dictionary.
    """
    ctx = Context()
    ctx.add_term("ex", f"{EG}")
    ctx.add_term("generatedAt", f"{PROV.generatedAtTime}", coercion=f"{XSD.dateTime}")
    ctx.add_term("graphMap", f"{EG.graphMap}", container=["@graph", "@id"])
    ctx.add_term("occupation_en", f"{EG.occupation}", language="en")
    ctx.add_term("children", f"{EG.parent}", reverse=True)
    result = ctx.to_dict()
    result["graphMap"]["@container"] = sorted(result["graphMap"]["@container"])
    assert DIVERSE_CONTEXT["@context"] == result
