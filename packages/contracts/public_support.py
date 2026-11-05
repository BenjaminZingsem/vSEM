"""Frontier-owned validation of fixed public contracts; no physical state or I/O.

Only this sealed schema vocabulary is supported. Callers cannot supply a schema.
Wire decoding is bounded and rejects duplicate keys and nonfinite constants.
"""
import copy
import datetime
import json
import math
import re
from .public_schema_data import SCHEMAS, REGISTRY


def _equal(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    return a == b


def _matches(value, schema):
    try:
        _validate(value, schema)
        return True
    except ValueError:
        return False


def _validate(value, schema):
    types = schema.get('type', [])
    if isinstance(types, str):
        types = [types]
    number = type(value) is int or (type(value) is float and math.isfinite(value))
    kinds = {'null': value is None, 'boolean': type(value) is bool,
             'number': number, 'integer': number and (type(value) is int or value.is_integer()),
             'string': type(value) is str, 'object': type(value) is dict, 'array': type(value) is list}
    if types and not any(kinds[t] for t in types):
        raise ValueError('invalid public field type')
    if 'const' in schema and not _equal(value, schema['const']):
        raise ValueError('invalid constant')
    if 'enum' in schema and not any(_equal(value, item) for item in schema['enum']):
        raise ValueError('invalid enumeration')
    if number:
        if ('minimum' in schema and value < schema['minimum']) or ('maximum' in schema and value > schema['maximum']):
            raise ValueError('public value outside range')
    if type(value) is str:
        if not schema.get('minLength', 0) <= len(value) <= schema.get('maxLength', len(value)):
            raise ValueError('invalid string length')
        if 'pattern' in schema and re.search(schema['pattern'], value) is None:
            raise ValueError('invalid string pattern')
        if schema.get('format') == 'date-time':
            # Frozen wire profile is RFC3339 with numeric offset, seconds and optional fraction.
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})', value):
                raise ValueError('invalid timestamp')
            try:
                datetime.datetime.fromisoformat(value.replace('t', 'T').replace('z', 'Z').replace('Z', '+00:00'))
            except ValueError as exc:
                raise ValueError('invalid timestamp') from exc
    if type(value) is dict:
        props = schema.get('properties', {})
        if any(type(k) is not str for k in value) or any(k not in value for k in schema.get('required', [])):
            raise ValueError('invalid public object keys')
        if schema.get('additionalProperties') is False and any(k not in props for k in value):
            raise ValueError('unknown public field')
        for k, child in props.items():
            if k in value:
                _validate(value[k], child)
    if type(value) is list:
        if not schema.get('minItems', 0) <= len(value) <= schema.get('maxItems', len(value)):
            raise ValueError('invalid array length')
        if 'items' in schema:
            for item in value:
                _validate(item, schema['items'])
    for child in schema.get('allOf', []):
        _validate(value, child)
    if 'oneOf' in schema and sum(_matches(value, child) for child in schema['oneOf']) != 1:
        raise ValueError('invalid public variant')
    if 'not' in schema and _matches(value, schema['not']):
        raise ValueError('invalid prohibited value')
    if 'if' in schema and _matches(value, schema['if']) and 'then' in schema:
        _validate(value, schema['then'])


def validate_public(value, kind):
    if type(kind) is not str or kind not in {'ui_intent', 'instrument_command', 'image', 'ui_observation', 'instrument_observation'}:
        raise ValueError('unknown public contract')
    _validate(value, SCHEMAS[kind])
    if kind.endswith('_observation'):
        channel = kind.split('_')[0]
        if value['protocol'] != channel + '.observation.v1':
            raise ValueError('wrong observation transport')
        names = [r['field'] for r in value['readbacks']]
        if len(set(names)) != len(names):
            raise ValueError('duplicate observable field')
    return copy.deepcopy(value)


def validate_arguments(command, arguments):
    if type(command) is not str or command not in SCHEMAS['arguments']:
        raise ValueError('unknown command')
    _validate(arguments, SCHEMAS['arguments'][command])
    return copy.deepcopy(arguments)


def _pairs(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError('duplicate JSON key')
        result[name] = value
    return result


def decode_public(text, kind):
    if type(text) is not str:
        raise ValueError('wire input must be text')
    try:
        if len(text.encode('utf-8')) > 131072:
            raise ValueError('wire input exceeds 128 KiB')
        value = json.loads(text, object_pairs_hook=_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
        return validate_public(value, kind)
    except (RecursionError, UnicodeError, OverflowError) as exc:
        raise ValueError('invalid public JSON') from exc


def encode_public(value, kind):
    try:
        text = json.dumps(validate_public(value, kind), sort_keys=True, separators=(',', ':'),
                          ensure_ascii=True, allow_nan=False)
        if len(text.encode('utf-8')) > 131072:
            raise ValueError('wire output exceeds 128 KiB')
        return text
    except (RecursionError, UnicodeError, OverflowError) as exc:
        raise ValueError('invalid public JSON') from exc
